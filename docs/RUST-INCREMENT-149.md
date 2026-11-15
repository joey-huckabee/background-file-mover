# Increment 149: active delivery jobs (parallel delivery, step 2)

Step 2 of the parallel delivery plan (see increment 148). Removes the
assumption that only one delivery runs at a time. Delivery concurrency stays at
one, so behavior does not change.

## Change

- **`ActiveJobs`** replaces the single "job the delivery thread is working on"
  slot (`AtomicI64`). It is a set of job IDs: a worker enters a job before its
  first store check of that job (`enter` returns `None` if another worker
  already holds it) and leaves when its block ends, after the worker child has
  been killed/reaped and the job's final result (problem record, deferral,
  failure, capacity backoff) is persisted. Deletion targets enter the same set.
- **Online clear** treats a job as busy while it is in the set (was: equal to
  the one slot).
- **Cancellation settlement** no longer relies on running "between jobs". It
  takes a second predicate, `delivering(job_id)`, evaluated inside its
  immediate transaction: a job a worker is still on stays Pending, every other
  pending job settles. A claim in flight still defers all settlement.
  Ordering argument: a worker enters the set before `deliver`'s first
  cancellation check, so either settlement sees the job as busy, or it settles
  first and the worker's first check stops it before any filesystem work.

## Tests

- New store test: two pending cancellations, one job still being delivered;
  only the idle job settles, a claim in flight defers both, and the busy job
  settles once its worker has stopped. Existing settlement calls pass
  `|_| false` (no worker active), preserving their meaning.
- New unit test: `ActiveJobs` holds one worker per job, jobs are independent,
  and a job is free again after its hold drops.
- Local: workspace clippy, all 95 store tests, file-mover unit tests, and the
  full API suite (107 of 111 in one run; the 4 worker-spawn tests that failed
  under load pass when run alone, as before).
