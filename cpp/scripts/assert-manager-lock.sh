#!/bin/sh
# Every acquisition of the JobManager mutex must go through ManagerLock.
#
# ManagerLock maintains a thread-local depth count, and store_for_command()
# asserts that count is zero -- enforcing "never touch the store while holding
# the manager mutex". A durable write blocks on busy_timeout for five seconds,
# and that mutex is what every worker takes to pick up its next job, so holding
# one across the other stalls the whole pool.
#
# A raw std::unique_lock or std::lock_guard on that mutex does not update the
# count, so it silently disables the assertion for that path. That is the
# failure this gate exists to prevent, and it is the reason ManagerLock replaces
# unique_lock rather than sitting beside it -- a companion object is something a
# new lock site can forget.
#
# The invariant was a comment before it was an assertion, and two violations
# survived the very commit that introduced the comment: cancel() held the mutex
# across two store calls, and shutdown() across store.close(). Both were found
# by writing the assertion, neither by writing the comment.
#
# store_mutex is a DIFFERENT mutex and is deliberately not covered. It guards
# the manager's own connection, and taking it raw is correct.
#
# Usage:  sh scripts/assert-manager-lock.sh
set -eu

cd "$(dirname "$0")/.."

target=src/manager.cpp
if [ ! -f "$target" ]; then
    echo "assert-manager-lock: $target not found" >&2
    exit 1
fi

# A raw lock naming the manager mutex. store_mutex is excluded by requiring the
# member to be exactly `mutex` -- "->mutex)" or ".mutex)" and not "store_mutex".
banned='(std::unique_lock<std::mutex>|std::lock_guard<std::mutex>)[[:space:]]*[A-Za-z_]*[[:space:]]*\((impl_?->|[A-Za-z_]*\.)mutex\)'

# The ManagerLock implementation itself holds the one legitimate unique_lock.
# It is identified by the member name, so the exemption cannot be borrowed by
# writing a different lock in the same file.
hits=$(sed 's://.*::' "$target" |
       grep -nE "$banned" |
       grep -v 'lock_(m)' || true)

if [ -n "$hits" ]; then
    echo "assert-manager-lock: raw lock on the manager mutex in $target" >&2
    echo "$hits" | sed "s|^|  $target:|" >&2
    echo "" >&2
    echo "Use ManagerLock. A raw unique_lock or lock_guard does not update the" >&2
    echo "thread-local depth count, so store_for_command() stops asserting for" >&2
    echo "that path -- and the whole point of the assertion is that the defect" >&2
    echo "it catches is otherwise silent: no crash, no race, no failing test," >&2
    echo "just degraded throughput under a load a unit test does not produce." >&2
    echo "" >&2
    echo "See docs/C5-PLAN.md section 1.2." >&2
    exit 1
fi

# The assertion is worthless if nothing routes through it.
if ! grep -q 'store_for_command' "$target"; then
    echo "assert-manager-lock: store_for_command() has disappeared from $target" >&2
    echo "The depth count is maintained but nothing asserts on it." >&2
    exit 1
fi

echo "manager-lock OK: the manager mutex is taken only through ManagerLock"
