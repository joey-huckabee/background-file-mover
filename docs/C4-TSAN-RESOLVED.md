# RESOLVED: ThreadSanitizer on the manager suite

**Status: fixed 2026-08-06.** The TSan tier is green — 206 test cases, 8492
assertions, zero warnings — and the fix was negative-tested. Kept as a record
because the investigation retracted two of its own conclusions along the way,
and because the root cause will bite again the next time someone reaches for a
timed condition wait.

## Root cause

`std::condition_variable::wait_until` breaks ThreadSanitizer's accounting for
the mutex passed to it.

`JobManager::wait_idle` used `idle_changed.wait_until(lock, deadline)`. That is
correct C++. It lowers to `pthread_cond_timedwait`, and after it runs TSan
believes the mutex is still held following an explicit `unlock()`. It then
reports a phantom **"double lock"**, and from that point treats every access
guarded by that mutex as unsynchronised — producing race reports in which
**both sides are recorded as holding the same mutex**, which is impossible and
was the clue that took longest to read correctly.

## How it was isolated

`cpp/tsan_pattern.cpp` (deleted with this fix; recoverable from history) was a
standalone program with **no project code**: the same worker loop, the same
`deque`/`map`/`set` under one mutex, the same condition variables. It ran the
idle-wait three ways selected at runtime, so one binary produced all three
measurements and nothing else differed:

| idle wait | warnings (4 workers) |
|---|---:|
| `wait()` | **0** |
| `wait_until()` | 11, 11, 19 across runs |
| bounded poll | **0** |

Reproducible. That is the whole result: one line, three ways, and only the
timed wait reports.

## The fix

`wait_idle` now polls — take the lock, test the predicate, release, sleep 1 ms,
repeat until the deadline. No timed condition wait anywhere in the manager.

Polling is acceptable **here specifically** because this is a test helper for
waiting out quiescence, not a synchronisation mechanism. Nothing depends on the
1 ms granularity and a missed wakeup costs a millisecond rather than
correctness. The project's preference for latches over sleeps is about making an
interleaving *happen*, which is a different problem and is still served by the
phase hook.

The `idle_changed` condition variable was removed with it. Nothing waited on it
any more, and a condvar nobody waits on reads like a synchronisation point.

## The fix was negative-tested

A fix that quiets a checker is worthless unless the checker still works. An
unsynchronised counter was injected — incremented by workers outside the lock,
read by `wait_idle` outside the lock — and TSan caught it: one warning, naming
the exact injected line.

**The first attempt at this negative test failed silently and is worth
recording.** The counter was initially only ever *written*, never read, so the
compiler deleted it as a dead store and TSan reported zero. Zero looked like
"the gate still passes" when it actually meant "there was no race to find". The
injected race has to be observable, or the negative test tests nothing — which
is the same failure mode as the tests this project keeps finding.

## Two conclusions retracted during the investigation

Recorded because a confident wrong diagnosis costs more than an admitted
unknown, and both were written down as settled before they were.

1. **"It is an artifact of the Catch2 harness."** Disproved by a standalone
   reproducer that showed the same reports with no test framework present.
2. **"SQLite's `fcntl` locking is the cause."** Argued from TSan's "as if
   synchronized via sleep" annotation pointing into SQLite's busy handler.
   Disproved by growing the clean model through every SQLite shape — per-worker
   connections on one shared file, writes inside the lock, writes outside it —
   all of which stayed at zero, and by the manager reporting the same set with
   SQLite removed from the worker's unlocked window entirely.

The annotation was real but incidental. It explained the bulk volume at four
workers and none of the residual, which is exactly the shape of an explanation
that is about to be wrong.

## Findings kept from the investigation

**Four threads calling `sqlite3_open` simultaneously as their first SQLite call
do race inside `sqlite3_initialize`.** The manager avoids this by accident:
`start()` opens the manager's own connection before spawning any worker, so
initialization happens single-threaded. Nothing records that the ordering is
load-bearing, and a refactor that opened worker stores first would reintroduce
it.

**`submit()` holds the manager mutex across a blocking SQLite write.** Tracked
separately; unrelated to TSan and still open.

## If a timed wait is needed again

Do not reach for `wait_until` or `wait_for` on a mutex that TSan also guards
data with. Either poll as `wait_idle` now does, or confine the timed wait to a
mutex that guards nothing else. Whichever is chosen, re-run the three-way
comparison above before trusting a green tier.
