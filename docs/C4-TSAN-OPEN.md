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
