# C4 — job manager and worker pool: implementation plan

The first threads in the project. ThreadSanitizer has gated since before any
thread existed (`L2-ARC-008`), deliberately — this is the milestone that finds
out whether that was worth it.

---

## 1. Scope, by requirement ID

C3 taught that estimating a milestone's coverage contribution from its size is
wrong: what matters is how many requirements it is the **first** to verify. So
this plan lists them.

**Newly traced by C4 — 11 requirements, all currently `_(none)_` in the matrix:**

| ID | Substance |
|---|---|
| `L2-MGR-001` | Dispatch to N workers through a mutex/condvar queue |
| `L2-MGR-002` | Every state change goes through the CORE transition function |
| `L2-MGR-003` | Clean shutdown: stop intake, drain, join |
| `L2-LIF-002` | Stop in-flight work cooperatively at a safe point |
| `L2-LIF-004` | Pause and resume; a paused job does no work |
| `L2-LIF-005` | Lifecycle commands reject unknown jobs and invalid transitions with a typed error |
| `L2-RTY-001` | Classify an error before deciding to retry |
| `L2-RTY-002` | Do not retry a permanent error merely because it is an OSError |
| `L2-RTY-003` | Durably persist attempt count, next-retry time, last failure |
| `L2-RTY-005` | Configurable bounded backoff and maximum attempts |
| `L2-RTY-006` | Manual retry of a retained failed job |

**Expected figure: 100 → 111 of 226, about 49%.** Stated as an ID count rather
than a feeling, so a miss is diagnosable.

**Out of scope, and why:**

* `L2-LIF-001`, `L2-LIF-003` — cancellation to a `CANCELLED_RETAINED` state,
  parented to the deferred `L1-SYS-003`. The v1.0.0 state machine has no such
  state (`JobState` is Queued/Renaming/Transferring/Done/Failed), which is
  consistent rather than an oversight.
* `L2-RTY-004` — retry that survives restart, parented to the deferred
  `L1-SYS-005`. v1.0.0 marks interrupted jobs FAILED (`L1-SYS-016`) rather than
  resuming them.

## 2. What "cancel" means at v1.0.0

The roadmap's done-when says the suite must interleave "submit, cancel, and
shutdown", while `L2-LIF-001` and `L2-LIF-003` are deferred. Both are true and
the resolution is worth stating rather than discovering.

**Cancellation at v1.0.0 removes a job that has not started from the runnable
queue and marks it FAILED with a descriptive reason.** It does not introduce
`CANCELLED_RETAINED`, and it never interrupts a job past the commit point.

`L2-LIF-002` — "stop an in-flight copy cooperatively, at a safe buffer
boundary" — is written for a copy engine that does not exist here. The
transferable requirement is *cooperative stopping at a safe point*, and with a
rename engine the safe points are the phase boundaries: before the commit, a
job can be abandoned with the source untouched; after it, the move is real and
must be finished. That is the interpretation implemented, and it is recorded
here so nobody later reads "buffer boundary" and concludes the requirement was
skipped.

## 3. Schema v2 — and the fixture stops being circular

`L2-RTY-003` requires durable attempt count, next-retry time and last failure.
The v1 schema has none of them, so **C4 is the first schema migration**.

```sql
ALTER TABLE job ADD COLUMN attempts        INTEGER NOT NULL DEFAULT 0;
ALTER TABLE job ADD COLUMN next_retry_ms   INTEGER NOT NULL DEFAULT 0;
ALTER TABLE job ADD COLUMN last_error      TEXT    NOT NULL DEFAULT '';
PRAGMA user_version = 2;
```

`last_error` is separate from `error` on purpose: `error` is bound by the
`L2-JOB-010` CHECK constraint to be non-empty if and only if the state is
FAILED, so a job that failed once, is waiting to retry, and is therefore *not*
FAILED cannot record why in that column. Overloading it would mean either
breaking the invariant or losing the diagnosis.

`cpp/tests/fixtures/store-v1.db` was frozen in C1 precisely for this moment,
and the migration test written then — which admitted to proving something
circular — becomes a real test the moment v2 exists. It must now assert that a
v1 store migrates, keeps its four jobs and its sequence, and reports version 2.

## 4. The injected clock

The roadmap calls for one, and retry needs it: a test for "does not run before
`next_retry_ms`" that sleeps is a test that is slow and occasionally wrong.

```
typedef std::int64_t (*ClockFn)(void* user);   // milliseconds
```

Default reads the real clock; tests install a counter they advance by hand.
This also removes the workaround C3 needed — the move engine derives timestamps
from the job record because it had no clock, which is noted in `mover.cpp` as
something C4 would fix.

## 5. Design

```
JobManager
  ctor(store_path, Config, MoveEngine factory)   store path, not a store:
                                                 each worker opens its own
                                                 connection (L2-JOB-003)
  submit(job_id, MoveRequest)      -> typed result
  pause(job_id) / resume(job_id)   -> typed result   (L2-LIF-004)
  cancel(job_id)                   -> typed result   (§2)
  retry(job_id)                    -> typed result   (L2-RTY-006)
  shutdown()                       stop intake, drain, join  (L2-MGR-003)
```

**Threading.** One mutex, one condition variable, a deque of runnable job ids,
and N workers. `L2-JOB-003` requires a connection per thread, so the manager
takes a *path* and each worker opens its own `JobStore` — sharing one handle
across threads is what that requirement exists to prevent.

**`L2-MGR-002`** — every state change goes through the core transition function.
The store already enforces this (`update_state` calls `Job::transition`), so the
manager must never write state by another route. A source gate is not proposed:
`make sql-confined` already prevents anyone reaching the database directly, and
the store is the only path to a state change.

**Retry policy.** `fsops::classify_errno` already returns Retryable / Denied /
Fatal, and `MoveOutcome` already distinguishes abort-before-commit from
halt-after-commit. Retry decisions compose those rather than re-deriving them:

* `AbortedBeforeCommit` with a Retryable cause → schedule a retry
* `AbortedBeforeCommit` with Denied or Fatal → FAILED, no retry (`L2-RTY-002`)
* `HaltedAfterCommit` → never automatically retried; needs an operator
* `FailedExternal` → never retried (`L2-SEC-011` says so explicitly)

## 6. Configuration

`[retry]` joins the schema, which `L3-CPP-036` says grows only by coordinated
change:

```
[retry] max_attempts        optional, default 3,     range 1..100
        backoff_initial_ms  optional, default 1000,  range 1..3600000
        backoff_max_ms      optional, default 60000, range 1..3600000
```

Cross-field validation: `backoff_initial_ms <= backoff_max_ms`, rejected with
both values named.

## 7. Testing

**Latch-based, not sleep-based.** A latch makes an interleaving happen; a sleep
makes it likely. The existing seams are the levers: `MoveEngine`'s phase hook
holds a worker mid-move at a chosen phase, and `JobStore::inject_write_fault`
forces the failures retry policy is about.

Cases that matter:

1. N workers drain a queue of M jobs, each job run exactly once.
2. Shutdown while a worker is held mid-move: intake stops, the in-flight job
   finishes, all workers join, no job is left half-recorded.
3. Pause during dispatch: a paused job is not handed out; resume returns it.
4. Cancel a queued job, and cancel one that is mid-move — the second must be
   refused rather than tearing a move in half.
5. A worker whose job throws or fails hard does not wedge the queue — the
   roadmap's done-when. Verified by making one job fail and asserting the others
   still complete.
6. Retry: a Retryable failure reschedules with backoff and the attempt count is
   durable across a reopen; a Denied failure does not retry.

All of it must be green under ThreadSanitizer. TSan has been gating since before
any thread existed; if that was worthwhile, this is where it pays.

## 8. Sequence

1. Schema v2 migration, and turn the v1 fixture test into a real migration test.
2. `[retry]` configuration.
3. The clock seam.
4. `JobManager` with dispatch and shutdown.
5. Pause, resume, cancel, manual retry.
6. Retry policy composed from `classify_errno` and `MoveOutcome`.
7. Latch-based concurrency suite; TSan.
8. Trace matrix, docs, battery, merge.

Step 1 first because a migration that is wrong is expensive to unpick once
anything depends on the new columns, and because it is the step with a fixture
already waiting to test it.
