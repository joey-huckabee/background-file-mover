# Increment 151: parallel delivery of jobs (parallel delivery, step 4)

Step 4 of the parallel delivery plan (increment 148). User decisions: production
default 1, demo 4; jobs hold many large files.

## Change

- **`delivery_concurrency`** (configuration, 1-8, default 1; never derived from
  CPU count): that many delivery worker threads, each delivering one job at a
  time through its own worker child. Shown under Settings (`transfers`).
- **Job selection:** a worker reads up to 64 ready jobs, takes the first one no
  other worker holds (`ActiveJobs`, increment 149), then rechecks that it is
  still ready (`Store::is_delivery_candidate`, the same rule as the candidate
  list), because its list may predate another worker finishing it.
- **Worker 0 alone** settles cancellations and runs deletion targets, so each
  deletion target has exactly one consumer.
- **Shutdown** joins every worker thread; the existing rule is unchanged (one
  original deadline, `ShutdownIncomplete` for kernel-blocked workers, custody
  kept until actual exit).
- **Bookkeeping is per job or per file, never per copied chunk.** The copy loop
  is unchanged.

### Shared destination custody

Each delivery child used to acquire the destination's coordinator lock itself
(an exclusive, non-blocking `flock` on its own open file description), so a
second concurrent delivery was refused with `EAGAIN` and its job stopped for
review. That lock is how the mover keeps a second mover (or a stale worker of
an earlier run) out of the destination, so it stays exclusive per service:

- With `delivery_concurrency` 1 nothing changes: every delivery uses the
  serialized lane and its child acquires the destination itself.
- With more workers, a job with a destination binding uses the coordinator's
  **shared custody** for its destination path. It is acquired once by a new
  supervised child (`--internal-destination-worker`), which validates the
  job's binding and pinned observation, takes the lock and passes the locked
  description back over `SCM_RIGHTS` (the source bootstrap pattern); the
  coordinator itself does no destination filesystem I/O. One acquisition runs
  at a time.
- Delivery children receive that description as stdout and **adopt** it
  (`LocalClaimLock::adopt_destination`): the same binding and pin checks as
  `acquire_destination`, for their own job, then the inherited description
  must be the destination's named coordinator lock and is re-locked on the
  same description. Every later step validates the source/destination pair it
  was started with (`validate_payload_locks`); legacy children keep the
  source/source pair.
- If acquisition fails (destination unavailable, foreign marker, changed pin),
  the job falls back to the **serialized lane**: its child acquires the
  destination itself, one such delivery at a time, held through child reaping
  and final persistence. Destination outages and binding refusals therefore
  keep their existing deferral and review behavior. The serialized lane waits
  for (and then releases) a shared lock of the same path that no delivery is
  using.
- A failed shared delivery drops the coordinator's reference, so the next
  delivery reacquires rather than reusing possibly stale custody.
- Shared `flock` is cooperative custody, not NFS fencing (unchanged).

## Review fixes

- **Draining instead of dropping custody.** A failed shared delivery used to
  remove the coordinator's custody at once, while other deliveries could still
  hold the same description: a third job's acquisition then hit `EAGAIN`, its
  serialized fallback failed too, and it went to review. Now the custody is
  marked draining: no new delivery uses it, new deliveries of that destination
  wait, and once the last delivery using it has exited it is released and
  reacquired. Unit regression (jobs A and B share custody, A fails, C waits
  while B runs and another acquisition is refused, C reacquires after B).
- **Destination lock checks keep the binding-refusal classification.** Source
  (stdin) and destination (stdout) descriptor checks are now separate
  (`validate_source_lock`, `validate_destination_lock`); in shared mode the
  destination check runs inside the destination-binding boundary at Open and
  before and after every step, so a replaced destination coordinator lock is an
  immediate binding review, not an ordinary counted retry. API regression:
  after a shared delivery, the destination's named lock is replaced; the next
  job goes to review with `destination_binding_requires_review`, and a later
  job is delivered after custody is reacquired.

## Performance requirement (user, 2026-11-15)

Status and metrics must not affect the performance of the copy or move. Any
progress reporting (step 5) adds at most a counter and a clock check per copied
chunk, sends at most one small update about every 2 s, never blocks the copy
(an update that cannot be delivered immediately is dropped), and writes nothing
to disk or the database. Acceptance: `fm-demo bench` with and without progress
reporting differs by no more than run-to-run noise (about 2%); results are
recorded in the step 5 increment and rechecked in step 9.

## Measurements (WSL demo, local ext4 virtual disk)

| Run | concurrency 1 | concurrency 4 |
| --- | --- | --- |
| 4 jobs x 4 files x 64 MiB | 26.0 MiB/s (all accepted after 12.8 s) | 30.7 and 31.4 MiB/s (accepted after ~21 s) |

On one local virtual disk the gain is modest (about 20%): the disk is the
bottleneck, and takeover of new submissions now shares it with four
deliveries. Parallelism pays where per-operation latency dominates (NFS);
step 6 measures that with the NFS qualification harness.

For comparison (same disk, 1 GiB in 4 files): `cp` + sync 46-51 MiB/s, `cp` +
sync + SHA-256 of both copies 22-23 MiB/s, the mover (one job) 41-43 MiB/s.
Windows drives (drvfs) are not qualified mover filesystems and are refused.

## Tests

- Config validation: `delivery_concurrency` 0 and 9 refused, 1 and 8 accepted.
- Store: `is_delivery_candidate` agrees with the candidate list (ready,
  committed, unknown, pending cancellation, invalid time).
- API: four worker threads run; six two-file jobs all commit with exactly one
  attempt per file (no job delivered twice).
- API: adopted custody requires the destination's own lock description, the
  job's pin and binding; another acquisition is refused while it is held.
- API: with two workers, an unprovisioned destination is a deferral
  (`destination_unavailable`, 0 failures) and a foreign marker is a review,
  as with one worker; the source copy stays in custody.
- The worker-ownership test now covers the destination worker mode.
- Local: workspace clippy; store suite; API suite (all pass; six worker-spawn
  tests that failed under load pass alone); file-mover unit tests (the five
  known local-only reload tests excepted).
