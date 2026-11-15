# Increment 148: delivery benchmark (parallel delivery, step 1)

User request 2026-11-14: parallel delivery, with live transfer speeds on the
dashboard. Plan (one PR per step, each with review and both SLES gates):

1. Benchmark and baseline (this increment).
2. Replace the single "job being delivered" slot with a set of active jobs;
   cancellation settlement and online clear stop assuming one delivery.
3. Make the retention capacity check and the reservation one atomic step.
4. Parallel jobs: `delivery_concurrency` (1-8; production default 1, demo 4).
5. Live transfer speed: the delivery worker reports progress while copying;
   in memory only; pushed to the dashboard every ~2 s (per job and total).
6. NFS qualification scenarios with two or more concurrent deliveries.
7. Parallel files within one job (`delivery_file_concurrency`), after the
   first file sets up the recording directory.
8. Configurable copy buffer (L2-COPY-002).
9. Benchmark again; recommend defaults.

Requirements the later steps must meet (from review):
- A job stays registered as active until its worker child has exited and its
  final result is persisted; settlement and online clear read that set inside
  their store transactions, serialized with admission.
- Deletion targets get exclusive acquisition (or one deletion dispatcher):
  `next_deletion_target()` only reads Pending, so two consumers could otherwise
  run the same target.
- Shutdown keeps the established rule for every dispatcher and worker child:
  one original deadline (never reset per worker); a worker still blocked in
  the kernel at that deadline is reported as `ShutdownIncomplete`, and custody
  is kept until that worker has actually exited. Joins are not promised to be
  bounded.
- Step 7: an all-files completion barrier before manifest publication and
  commit, per-file atomic reservations, and draining of the other files on
  cancellation or failure.

## Change

`fm-demo bench [--jobs N] [--files K] [--size-mb M]` (development only):
writes N jobs of K equal files and syncs them to disk (untimed), then submits
all jobs, resubmitting while the service answers `handoff_pending` (as a real
sender does), and polls the operator socket until every job is Committed. It
reports MiB/s, files/s and when all jobs were accepted. Any job that stops for
review or is cancelled fails the run. `write_files` is split out of `submit`.

## Review fixes

- Each benchmark job folder uses a full UUID and is created exclusively, so a
  run never overwrites staged input.
- Arguments are validated before any file is written (1-64 jobs, 1-256 files,
  finite positive size and timeout).
- `--timeout` is passed through to the inner run.

## Baseline (main at 4d7b024, WSL2 demo, local ext4 on a virtual disk)

| Run | Result |
| --- | --- |
| Raw disk: `cp` 1 GiB + sync | ~66 MiB/s |
| Raw disk: cold read 1 GiB | ~79 MiB/s |
| 1 job x 1 file x 512 MiB | 42.1 MiB/s (accepted after 0.4 s) |
| 4 jobs x 4 files x 64 MiB | 27.7 MiB/s, 0.43 files/s (all accepted after 12.1 s) |

Reading: one delivery is disk-bound at about two thirds of a plain copy
(copy, SHA-256, fsync, then a verification re-read). With several jobs,
takeover (one file at a time, each fsynced) and the single delivery thread
share the disk. A local virtual disk understates what parallelism gains on NFS,
where per-operation latency, not disk bandwidth, dominates; step 6 measures
that case.
