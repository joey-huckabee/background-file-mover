# Increment 154: parallel files within a job (parallel delivery, step 7)

Step 7 of the parallel delivery plan (increment 148). User: jobs hold many
large files, so one job's files should copy at the same time.

## Change

- **`delivery_file_concurrency`** (configuration, 1-8, default 1; never
  derived from CPU count; shown under Settings): files of one job copied at the
  same time. With 1, the file loop is unchanged (one session, files in order).
- **Shared custody.** Several children of one job each need the destination
  custody, so the coordinator uses the shared destination custody of increment
  151 whenever `delivery_concurrency` or `delivery_file_concurrency` is above 1.
  If a job is in the serialized lane (no shared custody: acquisition failed or
  no destination binding), its files stay sequential.
- **Order.** The job's first session opens the destination and sets up file
  0's attempt (allocation creates the recording directory; later files take it
  from file 0's transfer). Then up to K threads, each with its own session
  (child) adopting the shared custody, take files from a shared counter; file
  0's prepared attempt is handed to whichever thread takes it, so no extra
  attempt is made.
- **All-files barrier.** Every file thread, its child and its capacity holds
  finish before the job continues; only then does the existing recheck of every
  published file and the manifest/commit sequence run, unchanged.
- **Failure and cancellation.** The first failure (or a deferral, refusal,
  capacity backoff or cancellation) halts the other files before their next
  step; their sessions are dropped (children killed and reaped) before the
  result is persisted. The first real failure is reported with its file and its
  child's diagnostic and keeps its classification (deferral, binding refusal,
  capacity backoff, cancellation or ordinary failure). Holds of each thread are
  declared before its session, so capacity stays reserved until that child has
  exited.
- **Live speed.** The progress board keys entries by job and file; the
  snapshot still has one row per job, adding up the bytes and speeds of the
  files in progress (`active_files`); a fully verified file drops out. The
  dashboard shows e.g. "3 of 6 files in progress · 50% · 150.00 MiB/s".
- Demo: 4 jobs and 4 files at a time.

## Review fixes

- **Halt at every step boundary.** A file thread checks the halt after its
  (possibly slow) Open and before setup (allocation or restart), and
  `advance_file` checks it at the start of every step, before PublishIntent is
  persisted, as well as before each child step. Unit regression: a verified
  file with the halt set returns `Halted`, records nothing (no transfer saved)
  and sends nothing to its child.
- **Overlap proof excludes the anchor session.** The job's first session stays
  alive for the manifest while file sessions run, so the concurrency test now
  requires three delivery children (two file workers at once).
- **No dispatcher panic on thread exhaustion.** File threads are started with
  fallible scoped spawning; a failure halts the job, the scope joins the
  threads already started (their children reaped), and the attempt fails as an
  ordinary, recorded delivery failure.

## Measurements (WSL demo, local ext4 virtual disk)

`fm-demo bench --jobs 1 --files 4 --size-mb 256`, page cache dropped before
each run, one delivery worker:

| Files at a time | Runs (MiB/s) |
| --- | --- |
| 1 | 46.4, 43.8 |
| 4 | 61.9, 61.6 |

About 37% faster for one job of four large files on one local disk. The gain
over NFS (per-operation latency) is expected to be larger; the NFS throughput
scenario of increment 153 can measure it.

## Tests

- API: one job of six 16 MiB files with three at a time commits once (every
  file attempt 1, contents checked); a sampler thread observes at least two
  delivery children running at once besides the anchor session (two file
  workers overlapping).
- API: five files with three at a time, file 2's held copy no longer matching
  its claim: the attempt fails with file 2 recorded as the cause and a counted
  failure, the other files stop (no later file starts), and no delivery child
  is left.
- Unit: the progress board adds up files of one job, drops fully verified
  files, keeps one row per job.
- Admin UI node test: multi-file speed text.
- New tests resubmit on a retryable 503, as a producer does.
- Local: workspace clippy; API suite (new tests pass under full-suite load;
  the known worker-spawn tests that fail under load pass alone); admin TLS
  tests; file-mover unit tests (five local-only reload tests excepted).
