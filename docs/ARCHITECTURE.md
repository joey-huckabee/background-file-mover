# Architecture

This document describes how the Background File Mover is structured and why. It is the
orientation read before changing the transfer, control, or state code. Requirement IDs
(e.g. L1-SYS-003) refer to `docs/L1-REQ.md` and its L2/L3 children.

## What the system is

Not a file-copy utility — a **durable transfer coordinator with transaction-like move
semantics across two filesystems**. Simulation orchestration submits a completed
recording set and gets an immediate durable acknowledgement once the files are *claimed*;
the service then moves ~100 GB in the background so the simulation hosts can prepare the
next run (L1-SYS-001, L1-SYS-002).

The source and destination are separate NFS mounts, so no atomic cross-filesystem move
exists. The service manufactures reliable move semantics through a controlled workflow:

```
claim  ->  copy (to temp)  ->  verify  ->  publish (atomic rename)  ->  delete source
```

A source file is never deleted merely because a copy was attempted; it is deleted only
after the destination has been written, fsynced, published, and verified per the
configured integrity policy (L1-SYS-003).

## Process model

```
        orchestration script                       systemd
                 │                                     │
        file-mover submit …                    file-mover service run
                 │                                     │
                 ▼                                     ▼
        ┌─────────────────┐   AF_UNIX socket   ┌──────────────────────────┐
        │  CLI (client)   │ ─────────────────► │  BackgroundMoverService   │
        │  cli.py         │  length-prefixed   │  service.py               │
        └─────────────────┘   JSON, per-req id └──────────┬───────────────┘
                                                          │
                    ┌─────────────────────────────────────┼───────────────────────┐
                    ▼                                      ▼                       ▼
          ControlSocketServer                    TransferCoordinator        RecoveryManager
          control/server.py                      transfer/coordinator.py    recovery/manager.py
          (small control pool)                   (bounded transfer pool)    (startup only)
                    │                                      │
                    ▼                                      ▼
             CommandDispatcher                     SQLiteJobRepository  ◄── the durable queue
             control/dispatcher.py                 jobs/sqlite_repository.py
```

Two responsibilities run on **separate thread pools** so a saturated copy pool never
blocks a `status`/`health` query: a control server and a transfer scheduler. SQLite is
the authoritative durable work queue (L1-SYS-007).

## Module map (`src/file_mover/`)

| Module | Responsibility | Milestone |
|--------|----------------|-----------|
| `cli.py` | Argparse surface; thin client handlers | M1 (surface), M2+ |
| `constants.py`, `exceptions.py` | Shared vocabulary; typed error hierarchy | M1 |
| `jobs/models.py` | Job/File/integrity/exit-code enums; records | M1 (enums), M4 |
| `configuration.py` | INI load → validate → frozen `ApplicationConfig` | M2 |
| `logging_config.py` | One-time centralized logging setup | M3 |
| `control/protocol.py` | Length-prefixed JSON framing | M3 |
| `control/server.py`, `client.py`, `dispatcher.py` | Unix-socket control plane | M3 |
| `control/lifecycle.py` | `cancel`/`pause`/`resume` operations (`JobLifecycleService`) | v0.3.0 |
| `service.py` | `BackgroundMoverService` lifecycle + scheduler | M3/M7 |
| `presentation.py` | Control-response record/enum → JSON-wire serialisation | M6 |
| `diagnostics.py` | `doctor` environment capability checks (`EnvironmentDoctor`) | v0.4.0 |
| `jobs/repository.py`, `sqlite_repository.py` | Durable job/file state | M4 |
| `transfer/coordinator.py` | Job-level orchestration: walk files, aggregate, retry/route | M6 |
| `transfer/file_mover.py` | Per-file workflow: copy → verify → publish → delete-source | M6 |
| `transfer/copy_engine.py` | Bounded-memory copy to temp + fsync + resume + interrupt | M6 |
| `transfer/control_signals.py` | Thread-safe pause/cancel delivery to the copy loop | v0.3.0 |
| `transfer/partials.py` | Remove a job's `.swit-partial-` temporaries (cancel/recovery) | v0.3.0 |
| `transfer/integrity.py` | Hashing modes + `hmac.compare_digest` | M6 |
| `transfer/retry.py` | Error classification + backoff scheduling | M6 |
| `recovery/manager.py` | Startup reconciliation | M7 |

Class-based where there is state or a lifecycle; pure helper functions where there is
not. No god class — the legacy `FileHandler` façade is deliberately decomposed.

## Job state machine

Nominal path (L1-SYS-003, L1-SYS-007):

```
SUBMITTED → VALIDATING → CLAIMING → CLAIMED → HASHING_SOURCE → QUEUED
          → COPYING → VERIFYING → PUBLISHING → SOURCE_CLEANUP → COMPLETED
```

Retention terminals (always preserve the claimed source):

```
RETRY_WAIT   SOURCE_UNSTABLE   FAILED_RETAINED   CANCELLED_RETAINED   MANUAL_INTERVENTION
```

Operator lifecycle transitions (see **Lifecycle control** below):

```
QUEUED / RETRY_WAIT / COPYING  →  PAUSED  →  QUEUED        (pause → resume)
QUEUED / RETRY_WAIT / PAUSED / COPYING / … →  CANCELLED_RETAINED   (cancel)
```

`PAUSED` is a non-terminal holding state: it is not runnable, survives a restart, and does
no work until an explicit `resume`. A file counts as fully moved only at `MOVE_COMPLETE`
(copied → verified → published → source-deleted), never merely at `COPIED`.

## Claiming

Before any bytes are copied, `FileClaimManager` (`claiming.py`) **claims** each submitted
file with an atomic **same-filesystem rename** (`os.replace`) into a per-job staging
directory `<source_root>/<claim_directory_name>/<job_id>/` (L3-SUB-001). The staging
directory name defaults to `.swit-moving` and is operator-configurable via
`[paths] claim_directory_name` (validated as a single path component — no separators,
not `.`/`..`). The claim must stay within the source filesystem: a cross-filesystem rename
is not atomic and fails `EXDEV`, so the move to the destination mount is the
`copy → verify → publish → delete` workflow below, never a blind `shutil.move`.

Files are moved into a job-specific staging directory — rather than renamed individually
(e.g. `host01.dat` → `host01.dat.moving.<id>`) — because it:

- preserves the original filenames,
- groups all files belonging to one job,
- makes recovery easier,
- prevents the simulation from re-matching the original source paths,
- keeps partially transferred jobs clearly separated, and
- simplifies job inventory and cleanup.

## Durable per-file workflow (M6)

Each file passes through these steps; a failure at any step retains the source and (where
present) the temporary destination, records the failure, and schedules a retry or manual
intervention:

1. Load the file record; verify the claimed identity (dev/inode/size/mtime_ns).
2. If configured, hash the source; persist and fsync the manifest before copying.
3. Create the `.swit-partial-<job>-<file>` temp destination exclusively (`O_EXCL`,
   `O_NOFOLLOW`).
4. Copy the bytes using the configured strategy (see **Copy strategy** below).
5. `flush()` + `os.fsync()` the temp file.
6. Verify the destination byte count / size.
7. If configured, hash the destination and compare with `hmac.compare_digest`.
8. Atomically publish via `os.replace` within the destination filesystem.
9. `os.fsync` the destination directory where supported.
10. Revalidate the source identity; only then delete the claimed source.
11. Record `MOVE_COMPLETE`.

## Copy strategy

`BufferedFileCopyEngine` supports two byte-copy strategies, selected by the
`[transfer] use_kernel_copy` option; both write to the same exclusively-created
`.swit-partial-` temporary file and both are followed by the identical
fsync → verify → publish → delete steps.

- **Kernel-assisted** (`use_kernel_copy = true`, default). `os.copy_file_range` moves
  bytes directly between the source and destination file descriptors inside the kernel,
  without copying every byte through the mover process — faster for the large recordings.
  It is attempted only when the syscall exists, and any "not supported" outcome — the
  syscall is missing (`ENOSYS`), the filesystem declines it (`EOPNOTSUPP`), or the two
  ends are on different filesystems on an older kernel (`EXDEV`) — discards the partial
  output and falls back to the buffered loop. Genuine I/O errors are **not** masked; they
  propagate to the error pipeline.
- **Buffered** (`use_kernel_copy = false`, and the fallback). A bounded `read`/`write`
  loop copying at most one `copy_buffer_size_bytes` chunk at a time — the well-tested,
  universally-portable path.

Because the source and destination are two separate NFS mounts, the largest kernel-copy
wins (reflink / NFSv4.2 server-side `COPY`) may not apply across the pair; the strategy is
therefore a configurable, benchmark-driven choice (see `docs/DEPLOYMENT.md`), not an
assumed speedup. Integrity is unaffected either way — the destination is re-hashed after
the copy regardless of strategy.

## Bandwidth limiting

`[transfer] max_bytes_per_second` caps how fast the mover moves data, so a large run does
not saturate the link shared with the simulation hosts or the destination processing tier
(L2-BWL-001). It is **dynamic**: `file-mover throttle <bytes-per-second>` retunes the live
ceiling over the control socket without restarting the service, and the change takes effect
on the next copy-loop write — including for copies already in flight (L2-BWL-002). The
current value is reported by `file-mover health`.

### Why not an OS traffic-shaper?

There is no portable syscall to rate-limit ordinary file I/O, and the kernel facilities
that exist do not fit this workload:

| Mechanism | Why it does not fit |
|-----------|---------------------|
| `tc` (HTB/TBF qdiscs) | Shapes a whole network interface, needs root + `iproute2` + out-of-band per-host config, and throttles *all* traffic on the interface, not just the mover. Not standard-library. |
| cgroup v2 `io.max` (`IOWriteBandwidthMax=`) | Limits *block-device* I/O. The transfer is between two **NFS** mounts, so the bytes travel over the network, not a local block device — `io.max` does not govern them. |
| socket pacing (`SO_MAX_PACING_RATE`) | Applies to sockets the process owns, not to file copies through the VFS/NFS client. |

So the limit is enforced **in userspace**, exactly as `rsync --bwlimit`, `scp -l`,
`curl --limit-rate`, and `pv -L` do it.

### Token bucket

`RateLimiter` (`file_mover/transfer/ratelimit.py`) is a thread-safe token bucket that
fills at `max_bytes_per_second` up to a one-second burst. After each buffered write the
copy loop spends tokens for the bytes just written and sleeps only when the bucket runs
dry, keeping the *average* rate at or below the ceiling. One limiter instance is shared by
every concurrent file copy, so the cap is **global across the service**, not per file
(L2-BWL-003). A rate of `0` is unlimited and short-circuits with no overhead (L2-BWL-004).

Because the throttle lives in the userspace read/write loop, an active limit **forces the
buffered copy strategy**: kernel-assisted `copy_file_range` moves bytes entirely inside the
kernel, where there is no loop in which to pace them (L3-PY-011). Setting a limit therefore
trades the kernel-copy fast path for controllable throughput — a deliberate, operator-driven
choice. The clock and sleep function are injectable, so the limiter is verified with
deterministic, wall-clock-free tests.

## Lifecycle control (cancel / pause / resume)

`cancel`, `pause`, and `resume` (`file_mover/control/lifecycle.py`, `JobLifecycleService`)
give operators control over a durable job (L2-LIF-001..005). There is **no operating-system
primitive** to pause or cancel a *regular-file copy* — `SIGSTOP` would freeze the whole
service, not one job — so an in-flight copy is stopped **cooperatively**:

- A command for a job that is **not copying** (queued, retry-waiting, paused, or a retained
  terminal-ish state) is applied directly with a **compare-and-set** transition
  (`transition_job_if`), so a concurrent scheduler pick cannot be clobbered.
- A command for a job that **is copying** records a `ControlSignal` in the thread-safe
  `JobControlSignals` registry. The copy loop polls it once per buffer (the same loop the
  rate limiter runs in) and raises `CopyInterrupted` at that safe point. The coordinator
  then transitions the job — **pause** fsyncs and keeps the partial for resume; **cancel**
  discards the partial. Either way the claimed **source is retained**: cancel never deletes
  source data (L1-SYS-003).

`resume` returns a `PAUSED` job to `QUEUED`; the next scheduler tick continues it. This is
the classic cooperative-cancellation pattern (Go `context`, .NET `CancellationToken`),
checked at safe points rather than forced.

## Partial-file resume

`[transfer] resume_partial_files` (default on) lets an interrupted copy continue from where
it stopped instead of re-copying a large recording from byte zero (L2-RSM-001..003). Unlike
lifecycle control, **this leans on the OS**:

1. `os.stat`/`os.fstat` on the fsynced `.swit-partial-<job>-<file>` gives the resume offset —
   the bytes already durably written.
2. `os.lseek` moves both the source and destination descriptors to that offset.
3. The copy continues with either strategy; for the kernel path, `os.copy_file_range` reads
   and writes from the descriptors' current offsets, and its buffered fallback truncates back
   to the resume offset — **never to zero** — so the already-copied prefix survives (L3-PY-012).

Correctness rests on two guarantees. A **clean pause** fsyncs the partial, so its prefix is
exactly right and resume is lossless. A **crash-torn** partial (a partially-written final
buffer) is caught by the existing full-file hash verification: on a size or hash mismatch the
resumed partial is **discarded** and the file restarts from zero (L2-RSM-003) — unverified
bytes are never published. Startup recovery therefore *keeps* interrupted partials when resume
is enabled and *removes* them when it is disabled (L2-RSM-002).

## Feature interactions

The copy-path behaviours above are independently configurable but interact through two shared
mechanisms, both in `transfer/copy_engine.py`: the **engine choice** made once per file in
`_copy` (`if use_kernel_copy and available and not _rate_limited(): kernel else buffered`), and
the **per-buffer hooks** — `rate_limiter.throttle(...)` (buffered loop only) and
`interrupt_check()` (both loops). The operator-facing consequences and recommendations live in
`docs/FEATURE-INTERACTIONS.md`; the mechanism-level matrix is below.

| Combination | Where | Behaviour |
|-------------|-------|-----------|
| Bandwidth limit + kernel copy | `_copy` engine choice | A non-zero limit forces the **buffered** engine — the kernel loop cannot be paced (L3-PY-011). Chosen per file at copy start. |
| Partial resume + kernel copy | `_copy_via_kernel`, `_open_destination` | Compatible: seek to the offset and `copy_file_range` continues; the fallback truncates to `base_offset`, not zero (L3-PY-012). |
| Pause/cancel + either engine | `interrupt_check()` at both loops | Cooperative stop at the next buffer boundary (~`copy_buffer_size_bytes`), in the kernel *and* buffered loops. |
| Runtime `throttle` + in-flight kernel copy | engine chosen at copy start | The running kernel copy never reads the limiter, so a live rate change applies from the **next** file; a buffered copy honours it immediately (`RateLimiter.set_rate`). |
| Low limit + pause/cancel/shutdown | buffered loop order | `interrupt_check()` runs *after* `throttle()`, so a long throttle sleep delays the stop by up to one chunk. |
| Resume + integrity mode | `FileMover._needs_destination_hash` | Destination content is re-hashed only under `source-and-destination-hash`; a crash-torn resumed prefix is caught **only** in that mode (a clean pause is safe under any mode because the prefix was fsynced). |
| Pause/resume + `resume_partial_files` | `TransferCoordinator._handle_interrupt`, `FileMover.move(resume=...)` | Enabled: pause keeps the fsynced partial and resume continues it. Disabled: pause drops the partial and resume restarts the file from zero (never a collision). |

The remaining sharp edge is that resume's crash-safety is only as strong as the integrity mode
(a torn resumed prefix is caught only under `source-and-destination-hash`); it is called out as a
gotcha in the user guide.

## Logging & observability

Logging is centralized, gated, and context-aware (`logging_config.py`, L3-PY-013/014). Three
concerns are kept separate:

- **Level policy** — `LogGate`, a set of per-level booleans computed once by
  `configure_logging` from `[logging] level` (incl. `OFF`). Call sites read these flags so a
  disabled level costs a single predicted branch — never `isEnabledFor`, argument
  evaluation, formatting, or dispatch.
- **Emission + context** — business classes use stable `file_mover.<area>` loggers and carry
  `job_id`/`file_id` in **structured fields** (`bind(logger, job_id=…, file_id=…)`), not in
  the logger name, so a job or file can be traced across the log.
- **Formatting** — `ContextFormatter` appends bound fields (`… [job_id=… file_id=…]`) and
  leaves context-free records untouched.

**Twelve-factor output.** The service writes its event stream to the standard streams and
lets the environment (systemd's journal, a log shipper) route and store it — it manages no
log files. `INFO`/`DEBUG` go to **stdout** and `WARNING`/`ERROR`/`CRITICAL` to **stderr**
(the daemon has no result stream on stdout to protect; the split preserves the Unix
convention). The **CLI** is separate: stdout is reserved for a command's *result* and its
diagnostics go to stderr. `[logging]` therefore exposes only `level`.

Two performance dials for "no cost when off":

| Guard | Cost when the level is off | Toggle |
|-------|----------------------------|--------|
| `if GATE.info: log.info(...)` (hot paths) | one boolean read + predicted branch | runtime / config |
| `if __debug__ and GATE.debug: log.debug(...)` under `python -O` | **removed from the bytecode entirely** (args included) | build-time (`-O`) |

**Convention:** DEBUG everywhere uses `if __debug__ and GATE.debug:` (strippable under `-O`);
hot-path INFO uses `if GATE.info:`; cold-path INFO/WARNING/ERROR call directly (the
per-call `isEnabledFor` is negligible for infrequent events). Production runs
`python -O -m file_mover` for zero DEBUG overhead; run without `-O` to toggle DEBUG live.
`[logging] level = OFF` disables everything (null handler + all gate flags false).

The full operator/developer guide — the stdout/stderr contract, how to consume logs, and
how to add a log call — is **`docs/LOGGING.md`**; the twelve-factor rationale is
**`docs/12-FACTOR.md`**.

## Environment diagnostics (`doctor`)

`file-mover doctor` verifies the runtime provides the capabilities the service depends on
before an operator relies on it (`diagnostics.py`, L2-ENV-001..003). Each capability is a
small **`EnvironmentCheck`** (a strategy): a name, a `REQUIRED`/`OPTIONAL` level, and a
detection callable that returns `(available, detail)`. **`EnvironmentDoctor`** runs the set
and aggregates a `DiagnosticsReport`; a probe that raises is reported as an unavailable
capability, never propagated (no-panic).

- **Required** (a miss → `FAIL` → `doctor` exits `ENVIRONMENT_UNSUPPORTED`): `AF_UNIX`,
  `fcntl`, SQLite WAL, the configured hash algorithm, Python ≥ 3.10, POSIX signals.
- **Optional** (a miss → `WARN`, never a failure): `O_NOFOLLOW`, and kernel-assisted copy
  (only when `use_kernel_copy` is enabled).

The detection helpers are module-level so they can be simulated present/absent in tests on
any host; rendering (human lines / JSON `environment` array) is a separate concern in the
CLI + `presentation.py`. This makes `doctor` a deploy gate — see `docs/DEPLOYMENT.md`. To
add a check, see `docs/MAINTAINER-GUIDE.md`.

## Error pipeline

Each layer catches only what it can interpret, attaches context, and re-raises a typed
`FileMoverError` (preserving `__cause__`). The `ErrorClassifier` maps the failure to an
`ErrorDisposition`:

| Disposition | Examples | Effect |
|-------------|----------|--------|
| `RETRY` | `ESTALE`, `EIO`, `ETIMEDOUT`, `ECONNRESET`, `EAGAIN` | Backoff, retain source |
| `RETAIN_AND_FAIL` | `ENOSPC`, `EDQUOT`, `EROFS`, `EACCES`, hash mismatch | Retain for operator |
| `REJECT_JOB` | invalid source path, `ENOTDIR`, `EXDEV` on same-fs claim | Reject at submission |
| `SERVICE_FATAL` | corrupt state DB, unwritable state dir | Controlled startup refusal |

"No panic" means no expected operational exception terminates the service: one failed
file does not crash the worker manager, one failed job does not stop the service, and
every exception becomes a defined job/file state (L1-SYS-010). Some conditions
*deliberately* refuse startup (corrupt DB, invalid config, another live instance) — a
controlled fail-safe, not a panic.

## Configuration hierarchy

`compiled defaults < config file < approved per-command CLI override`. The CLI never
rewrites the config file; resolved settings are stored in the job record so recovery
reuses them (L2-CLI-007). Validated configuration is immutable and typed (L2-CFG-005).

## Recovery

At startup, before accepting new work, the `RecoveryManager` inspects every job in a
non-terminal state and reconciles the durable record against observable filesystem state
(claimed source present? temp destination present? published destination present and
verified?). It resumes, retries, or routes to manual intervention — decisions come from
what is on disk, not from assumptions about what the previous process finished
(L1-SYS-005).

## Service readiness (systemd `Type=notify`)

The service integrates with the init system via the `sd_notify` protocol
(`file_mover/systemd.py`), using only a standard-library `AF_UNIX` datagram — no
`libsystemd` dependency (L3-PY-010):

- **Readiness.** Under `Type=notify`, systemd sets `NOTIFY_SOCKET` and waits for a
  `READY=1` datagram before marking the unit started. The service sends it at exactly the
  point it is genuinely serving — lock held, SQLite open, recovery reconciled, scheduler
  running, control socket bound. So `systemctl start`, `After=file-mover` ordering, and
  orchestration keyed off "started" never race the control socket into existence
  (L2-CTL-011). It sends `STOPPING=1` when the drain begins.
- **Liveness.** With `WatchdogSec=` set, the scheduler loop sends `WATCHDOG=1` every tick;
  if the service hangs (e.g. on a wedged NFS mount) and the keep-alives stop, systemd
  restarts it (L2-CTL-012). Keep `[service] poll_interval_seconds` below `WatchdogSec / 2`.

Every notification is a **no-op when `NOTIFY_SOCKET` is unset** (running outside systemd,
in tests, or on a non-POSIX host) and never raises, so the readiness path is invisible to
the rest of the service.

## Logging levels

Configured once at the application boundary; business classes call
`logging.getLogger("file_mover.<area>")` and never install handlers. Job and file IDs
travel as structured `extra` fields, not in the logger name.

- **DEBUG** — per-chunk / per-step internal detail.
- **INFO** — job and file lifecycle transitions.
- **WARNING** — retryable failures and backoff.
- **ERROR** — retained failures and manual-intervention routing (with traceback for
  unexpected defects via `logger.exception`).
