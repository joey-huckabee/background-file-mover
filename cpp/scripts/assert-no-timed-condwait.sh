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

# The SECOND rule this script enforces: wait() must be given a predicate.
#
# `wait(lock)` is correct only inside a loop that re-tests the condition, and
# the loop is the part that gets dropped -- an `if` where a `while` was meant
# compiles, passes, and then wakes spuriously into whatever the condition was
# protecting against. The predicate overload IS that loop, by definition, and
# cannot be written wrong.
#
# Added after SonarCloud's cpp:S5404 caught the bare form a second time, in
# EventPublisher::unsubscribe -- where a spurious wakeup would have returned
# while a publisher still held the subscriber in its snapshot, which is exactly
# the use-after-free that wait exists to prevent. Twice is a pattern, and this
# project's answer to a pattern is a gate rather than a resolution to remember.
#
# Detecting this with one regex does not work, and the first attempt was a
# false positive worth recording: `\.wait[[:space:]]*\([^,)]*\)` matched
# `work_ready.wait(lock.raw(), pred)` because `[^,)]*` stops at the `)` closing
# `raw()`, before ever reaching the comma. A gate with false positives gets
# disabled, so this looks at the text AFTER `.wait(` on the line instead and
# asks whether a comma appears at all.
bare_wait_check() {
    awk '
        /\.wait[ \t]*\(|::wait[ \t]*\(/ {
            line = $0
            at = match(line, /\.wait[ \t]*\(|::wait[ \t]*\(/)
            rest = substr(line, at + RLENGTH)
            if (index(rest, ",") == 0) {
                printf "%d:%s\n", NR, $0
            }
        }
    '
}

status=0
for f in $(find src include -name '*.cpp' -o -name '*.hpp' 2>/dev/null | sort); do
    # Comments stripped first: this rule is worth explaining next to the code it
    # governs, and a gate that fires on its own rationale trains people to
    # delete the rationale.
    stripped=$(sed 's://.*::' "$f")

    hits=$(printf '%s\n' "$stripped" | grep -nE "$banned" || true)
    if [ -n "$hits" ]; then
        echo "assert-no-timed-condwait: $f uses a timed condition wait" >&2
        echo "$hits" | sed "s|^|  $f:|" >&2
        status=1
    fi

    hits=$(printf '%s\n' "$stripped" | bare_wait_check || true)
    if [ -n "$hits" ]; then
        echo "assert-no-timed-condwait: $f waits without a predicate" >&2
        echo "$hits" | sed "s|^|  $f:|" >&2
        echo "  use wait(lock, predicate) -- see cpp:S5404" >&2
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
