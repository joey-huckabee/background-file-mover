# Open issue: ThreadSanitizer is red on the manager suite

Status at the end of the C4 implementation pass. Everything else in
`docs/C4-PLAN.md` is done and green. §7 of that plan said all of it must be
green under TSan, and it is not yet.

## Shape of the failure

32 warnings, entirely within `[manager]`. The rest of the suite is clean under
TSan, so this is C4's own code and not something inherited.

## What has been established

- **It reproduces in a standalone binary**, outside Catch2 entirely:
  `cpp/tsan_repro.cpp` starts a manager, submits 12 jobs, waits, and shuts
  down. 33 warnings. So this is not an artifact of the test harness recycling
  addresses across 207 tests, which was the leading theory and is now dead.
- **It reproduces with a single worker.** 25 warnings at one worker, 29 at two,
  34 at four. An earlier reading of "only with more than one worker" came from
  comparing manager tests that do very different amounts of work, not from
  varying the worker count with everything else held fixed; the standalone
  repro varies exactly one thing and contradicts it. So this is
  main-thread-versus-worker, and the worker pool size only changes how many
  times it is hit.
- The reported races are on `Impl` members — `runnable`, `active`, `requests` —
  and on the heap nodes those containers allocate. Most are flagged against
  `operator delete`: memory freed by one thread and reused by another.
- **Both sides of every reported race are recorded by TSan as holding the same
  mutex** (`M230`, which is `Impl::mutex`). That should be impossible. A shared
  mutex establishes happens-before and TSan would not report it.
- Alongside them TSan reports a **"double lock"** of that same mutex in
  `run_worker`. A genuine recursive lock of a non-recursive `std::mutex` would
  deadlock, and the suite does not deadlock — the pool completes every job and
  `shutdown()` joins every worker.

## Narrowed, not yet solved (2026-08-06)

Three experiments. The first two are conclusive; the third partly contradicts
the story the first two suggested, and the heading says "narrowed" rather than
"root cause" because of it.

**1. The lock pattern alone is clean.** `cpp/tsan_pattern.cpp` reproduces
`run_worker()`'s exact locking — one `unique_lock` held across the loop,
released around the slow part and retaken, over the same `deque`/`map`/`set`
the manager guards, with the same two condition variables on one mutex — and
does no SQLite or filesystem work. **Zero TSan warnings at four workers.** So
the manager's locking discipline is not the defect, and the reports originate
inside `engine.execute()`.

**2. TSan names the culprit itself.** Every race report carries a third stack
that earlier passes had not looked at:

```
As if synchronized via sleep:
  #1  unixSleep                 sqlite3.c:47354
  #3  sqliteDefaultBusyCallback sqlite3.c:189129
  #6  btreeBeginTrans           sqlite3.c:76966
  #11 JobStore::update_state    store.cpp:555
```

That is SQLite's **busy handler** — the path taken when a connection cannot get
the write lock and waits for another to release it. It fires because the
manager's own connection and the workers' connections contend for the same
database file, exactly as designed: L2-JOB-003 requires one connection per
thread.

SQLite coordinates those connections with POSIX `fcntl` file locks. **TSan does
not model `fcntl` locking as a happens-before edge** — it has no way to know
that a write through connection A is ordered before a read through connection B.
So it sees the accesses as unsynchronised and reports, and the "mutexes: write
M9" on both sides is genuine: the manager's mutex *is* held by both, which is
why the reports look self-contradictory.

The vendored SQLite is correctly instrumented (`-fsanitize=thread` is present on
its compile line, verified by the `__tsan_atomic*` undefined symbols in the
object), so this is not the uninstrumented-dependency case the Makefile warns
about. It is the case TSan cannot handle even with full instrumentation.

**3. But removing the contention only halves the reports.** The reproducer grew
a "no overlap" mode that pauses every job as it is submitted and resumes them
only once all submits are done, so the main thread's SQLite writes never overlap
a worker's:

| configuration | warnings |
|---|---:|
| 4 workers, overlapping submits | 30 |
| 4 workers, no overlap | 26 |
| 1 worker, overlapping submits | 14 |
| **1 worker, no overlap** | **7** |

Contention is clearly *a* contributor — halving it halves the count — but seven
reports survive a configuration with a single worker and no submit-time overlap.
Something else is producing those, and it has not been identified.

**So the reports are NOT yet established as false positives.** The SQLite
explanation accounts for most of the volume and fits the "as if synchronized via
sleep" annotation exactly, but it does not account for the remainder, and the
remainder is the part that matters — a genuine race hiding behind a plausible
story is precisely the failure this project keeps finding. The earlier draft of
this section was headed "Root cause" and claimed the diagnosis was settled; it
was written before experiment 3 ran, and experiment 3 does not support it.

## A real defect found on the way

Independent of TSan, and worth fixing regardless:

**`submit()` holds the manager's mutex across a SQLite write that can block for
five seconds.** `impl_->store.record_intent()` runs under `impl_->mutex`, and
when a worker's connection holds the database write lock, that call waits on
`busy_timeout` — 5000 ms by default. Every worker blocks on the manager mutex
for the duration, because the mutex is what they take to pick up their next job.
One submit arriving at the wrong moment can stall the entire pool.

`retry()` has the same shape, and so does the failure-recording path in
`handle_failure()` / `fail_permanently()`, which call the store while the caller
holds the lock.

The fix is to do the durable write outside the mutex while preserving
L2-JOB-013's ordering — intent recorded before the job becomes runnable — which
needs care rather than a straight move, because two concurrent submits of the
same id must still be refused. Tracked separately.

## Reading of the evidence

The two anomalies are almost certainly one fault. If TSan believes the mutex is
already held when it is taken, its happens-before accounting for that mutex is
broken, and every subsequent access under it looks unsynchronised. The races are
then a consequence of the phantom double lock rather than dozens of independent
defects.

Note what this does **not** yet establish: whether the manager's locking is
actually wrong. Every access TSan complains about is made under the mutex, the
suite passes, and nothing deadlocks. It is equally consistent with a genuine
missing-synchronisation bug that TSan is describing badly, and with correct code
that TSan is mis-tracking. Deciding which is the whole of the remaining work,
and it should be decided before anything is "fixed" — changing locking to
silence a tool that may be wrong is how correct code becomes incorrect.

Chasing the individual race reports is probably wasted effort until the double
lock is explained. That is the thread to pull.

## Ruled out

- **Holding the lock across thread creation in `start()`.** That was a real
  defect and is fixed — it serialized pool startup on the creating thread,
  because every worker's first act is taking the same lock — but it was not
  this. The reports survived the fix.
- **Two scoped `unique_lock`s per loop iteration sharing a stack slot.** The
  worker loop now uses a single lock object, explicitly released around the
  move and retaken after. One fewer warning; the double lock survives.
- **The deadlock detector being at fault.** With `detect_deadlocks=0` the double
  lock report disappears and the race count is unchanged, so the races are not
  merely downstream of that one report being printed.

## What is still owed

The next question is narrow and well-posed: **what produces the seven reports
that survive with one worker and no submit overlap?** Everything else is
downstream of that answer.

1. **Enumerate those seven specifically.** They are few enough to read
   individually rather than in aggregate — which is what the earlier passes did,
   and why the volume kept hiding the signal. Run
   `/tmp/tsan_repro 1 nooverlap` and work through each report's two stacks.
   Candidates not yet excluded: `shutdown()` closing the manager's store while a
   worker is still finishing; `resume()` and `wait_idle()` touching shared state
   concurrently with worker execution; and the raw `syscall(SYS_renameat2, ...)`
   in `fsops.cpp`, which TSan cannot intercept the way it intercepts `renameat`.
2. **Only then decide the remedy.** A `race:sqlite3.c` suppression will NOT work —
   the reported accesses are in the manager's own containers, not in SQLite, so
   the suppression would not match. The realistic options are a
   `called_from_lib`-style suppression, wrapping store calls in
   `AnnotateHappensBefore`/`AnnotateHappensAfter` so TSan can see the ordering
   SQLite provides, or accepting a documented suppression list checked into the
   repository.
3. **Whatever is chosen must be negative-tested**, like every other gate here: a
   suppression that silences a genuine race is strictly worse than a red tier,
   because it converts a loud problem into a silent one. Inject a real race into
   the manager and confirm the suppressed configuration still catches it.

Until step 3 passes, TSan stays red and C4 stays unmerged.

## Next things to try, in order

The repro is `cpp/tsan_repro.cpp`. It is scratch, excluded from the build, and
should be deleted once this is closed. Build and run it with:

```
g++ -Iinclude -isystem third_party -std=c++11 -O1 -g -fsanitize=thread \
    -fno-omit-frame-pointer tsan_repro.cpp \
    build/x86_64-linux-gnu-11-tsan/src/*.o \
    build/x86_64-linux-gnu-11-tsan/third_party/sqlite3.o \
    -o /tmp/tsan_repro -lpthread -lm
/tmp/tsan_repro <worker-count>
```

1. **Explain the double lock first.** Lines 294 and 296 of `manager.cpp` are
   `lock.unlock()` and `lock.lock()` with only `engine.execute()` between them.
   For TSan to call the second one a double lock it must not have seen the
   unlock. Establish whether `execute()` is somehow re-entering the manager's
   mutex, or whether TSan's ownership record for it is being clobbered. A
   `pthread_mutex_lock`/`unlock` breakpoint pair, or an `assert` on
   `lock.owns_lock()` either side, would settle it quickly.
2. **Strip the repro down.** Remove `wait_idle()`, then `shutdown()`, then the
   submit loop, and find the smallest program that still reports. `wait_idle`
   is a good first suspect: it waits on `idle_changed` while workers wait on
   `work_ready`, two condition variables sharing one mutex.
3. **Check whether the vendored SQLite build participates.** It is compiled with
   `-fsanitize=thread` and `SQLITE_THREADSAFE=1`, and every worker opens its own
   connection to the same database file, so SQLite's global inode table is
   shared across all of them. Running the repro against a manager whose workers
   never touch the store would isolate this.

## Why this blocks the merge

TSan has gated this project since before it had a single thread. Suppressing it
at the one milestone where it was ever going to find something would waste every
prior milestone's worth of that discipline. C4 does not merge to main until this
is either root-caused and fixed, or demonstrated to be a harness artifact with
the demonstration written down.
