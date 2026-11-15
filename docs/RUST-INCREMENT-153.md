# Increment 153: NFS qualification of parallel delivery (step 6)

Step 6 of the parallel delivery plan (increment 148): run the NFS
qualification lab with more than one delivery worker, so the shared
destination custody of increment 151 is exercised on real NFS, and measure
throughput to an NFS destination. Harness changes only; no service change.

Local lab: Podman WSL2 machine, saved E2 NFS server image, kernel
6.18.33.2-microsoft-standard-WSL2. Gates built from the merged source of
increments 151 and 152: production `20261115T082220Z-50214998`, qualification
`20261115T084451Z-eda40f38-nfs-qualification` (both PASSED). Run directories
below are under `rust/validation/` (local evidence, not committed).

## Harness change

- `check-nfs-boundaries.py --delivery-concurrency N` (1-8) runs the runtime,
  shutdown and coordinator-death matrices with `delivery_concurrency` N in each
  case's service config (case labels end in `-cN`).
- New `scripts/nfs_parallel.py`:
  - **SC-160 `--parallel-shutdown`** (needs N >= 2): two 1 GiB jobs deliver at
    once to the NFS destination; the NFS server is stopped while both workers
    copy, so both are held in the kernel (`D`). Shutdown with a 2 s budget must
    report `ShutdownIncomplete` with both workers listed; a competing service
    (own port) must be refused by state ownership; after restoration both
    workers exit, `--status` shows no owner, and a restart delivers both
    recordings with digests equal to the originals. Debug and release.
  - **SC-161 `--parallel-throughput`**: four 256 MiB jobs from a local source
    to the NFS destination (release build), timed from the first submission
    to the last commit, every digest checked.

### Harness drift repaired (independent of parallel delivery)

Since 109dc4e (2026-11-04) the service refuses unenrolled state before any
source access, and the lab had not been run since. Two checks still expected
the earlier first refusal:

- The production startup check now proves the NFS refusal where it happens:
  `--initialize-source` on the NFS source must fail with "filesystem not
  qualified" / "production NFS disabled" and create no state; the plain start
  may refuse with those or `SourceEnrollmentRequired`, also without state.
  Assertion messages now include the actual output.
- The production outage-startup log may show `SourceEnrollmentRequired` (a
  local refusal before any source access).

Not repaired here: the `--isolated-startup` outage check expects a fresh,
unenrolled qualification startup to block in the source bootstrap during an
outage; it now refuses locally first. Restoring that check needs enrolled state
before the outage and a before/after state comparison instead of "no SQLite
created". Parallel runs below therefore omit `--isolated-startup`. Follow-up.

## Results

| Run | Workers | Result |
| --- | --- | --- |
| `nfs-20261115T124908Z-4981df55` runtime matrix (22 cases incl. 3-minute outages) + state checks | 2 | **PASSED** |
| `nfs-20261115T101345Z-07f92425` shutdown matrix SC-093 | 2 | 12/12 cases pass |
| `nfs-20261115T095646Z-5f9101eb` SC-160 parallel shutdown | 4 | 2/2 pass (debug, release) |
| `nfs-20261115T121758Z-8e686fe0` coordinator death SC-092 | 2 | 18/18 cases pass; coverage rule not met (below) |
| `nfs-20261115T114721Z-492a3abf` coordinator death SC-092 (control) | 1 | 18/18 cases pass; same coverage gap |

SC-160 (both builds): two delivery workers held in `D`; `ShutdownIncomplete`
after 2.8 s with both PIDs; competitor refused; both workers gone after
restoration; restart committed both jobs (attempt 2 each) with matching
digests.

Coordinator death: every case passes in both runs, with identical outcome
counts at 1 and 2 workers (6 blocked orphans, 2 terminating orphans and 10
prompt exits retaining ownership). The matrix additionally requires observing a
kernel-closed guard in both profiles (a terminating `verify_read` worker whose
guard the kernel closes), with up to three repetitions; neither run observed
it. Because the single-worker control shows the same gap, this is a timing
property of this lab host, not of parallel delivery. Matrices that earlier
runs' reports qualified are not re-qualified by these local runs; they show no
regression with parallel delivery.

The shutdown and parallel runs end with a status of FAILED only through the
outage-startup drift check fixed afterwards (their matrices passed); the
runtime run includes the fix and is PASSED end to end.

## Throughput to NFS (SC-161, release, 4 x 256 MiB)

| Workers | Time | Rate |
| --- | --- | --- |
| 1 (`nfs-20261115T094623Z-c9d24443`) | 28.3 s | 36.2 MiB/s |
| 4 (`nfs-20261115T095646Z-5f9101eb`) | 23.2 s | 44.1 MiB/s |

About 22% faster with four workers. The lab's NFS server runs on the same
host (no network latency), so this understates the gain over a real network.
