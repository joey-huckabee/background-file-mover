#!/bin/sh
# Bans std::condition_variable::wait_for and wait_until in the implementation.
#
# Both are correct C++ and both break ThreadSanitizer's accounting for the mutex
# passed to them. After a timed wait TSan believes the mutex is still held
# following an explicit unlock(), reports a phantom "double lock", and from then
# on treats every access that mutex guards as unsynchronised -- producing race
# reports in which BOTH sides are recorded as holding the same mutex.
#
# Measured, not inferred. A standalone program with no project code, running one
# worker loop three ways selected at runtime so nothing else differed:
#
#     wait()          0 warnings
#     wait_until()    11-19 warnings across runs
#     bounded poll    0 warnings
#
# JobManager::wait_idle was the original offender and cost 32 warnings and three
# investigation passes, two of which reached confidently wrong conclusions. The
# full account is docs/C4-TSAN-RESOLVED.md.
#
# The replacement is not a worse design. A timeout belongs on the thing that can
# block, not on a condition variable guarding shared state:
#
#     socket read/write deadline -> SO_RCVTIMEO / SO_SNDTIMEO, or poll(2)
#     accept loop shutdown       -> poll(2) with a timeout, or a self-pipe
#     periodic tick              -> a thread that nanosleeps, holding no mutex
#     waiting for a free slot    -> do not wait; refuse with 503 (ADR-0013)
#
# L2-SEC-009 asks for a timeout on every potentially blocking SYSCALL. A deadline
# enforced by a condition variable bounds the wait, not the syscall, so it does
# not satisfy that requirement anyway.
#
# If a future change genuinely needs one, delete this gate in the same commit
# and say why. A decision with a diff is the point.
#
# Usage:  sh scripts/assert-no-timed-condwait.sh
set -eu

cd "$(dirname "$0")/.."

# Matches .wait_for( and .wait_until( as member calls, and the qualified forms.
# Not a bare "wait_for" anywhere, so a variable or comment mentioning the word
# does not trip it.
banned='\.(wait_for|wait_until)[[:space:]]*\(|::(wait_for|wait_until)[[:space:]]*\('

status=0
for f in $(find src include -name '*.cpp' -o -name '*.hpp' 2>/dev/null | sort); do
    # Comments stripped first: this rule is worth explaining next to the code it
    # governs, and a gate that fires on its own rationale trains people to
    # delete the rationale.
    hits=$(sed 's://.*::' "$f" | grep -nE "$banned" || true)
    if [ -n "$hits" ]; then
        echo "assert-no-timed-condwait: $f uses a timed condition wait" >&2
        echo "$hits" | sed "s|^|  $f:|" >&2
        status=1
    fi
done

if [ "$status" -ne 0 ]; then
    echo "" >&2
    echo "wait_for/wait_until break ThreadSanitizer's tracking of the mutex" >&2
    echo "passed to them: every access that mutex guards then reads as a race," >&2
    echo "including accesses that correctly hold it." >&2
    echo "" >&2
    echo "Put the timeout on what actually blocks:" >&2
    echo "  socket I/O   -> SO_RCVTIMEO / SO_SNDTIMEO, or poll(2)" >&2
    echo "  accept loop  -> poll(2) with a timeout, or a self-pipe" >&2
    echo "  periodic tick-> a thread that nanosleeps, holding no mutex" >&2
    echo "" >&2
    echo "See docs/C4-TSAN-RESOLVED.md and docs/C5-PLAN.md section 1.1." >&2
    exit 1
fi

echo "no-timed-condwait OK: no wait_for/wait_until in src or include"
