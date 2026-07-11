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
| `service.py` | `BackgroundMoverService` lifecycle + scheduler | M3/M7 |
| `jobs/repository.py`, `sqlite_repository.py` | Durable job/file state | M4 |
| `transfer/coordinator.py` | Drives files through the workflow; owns transitions | M6 |
| `transfer/copy_engine.py` | Bounded-memory copy to temp + fsync | M6 |
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

A file counts as fully moved only at `MOVE_COMPLETE` (copied → verified → published →
source-deleted), never merely at `COPIED`.

## Durable per-file workflow (M6)

Each file passes through these steps; a failure at any step retains the source and (where
present) the temporary destination, records the failure, and schedules a retry or manual
intervention:

1. Load the file record; verify the claimed identity (dev/inode/size/mtime_ns).
2. If configured, hash the source; persist and fsync the manifest before copying.
3. Create the `.swit-partial-<job>-<file>` temp destination exclusively (`O_EXCL`,
   `O_NOFOLLOW`).
4. Copy in a bounded read/write loop; throttle progress reporting.
5. `flush()` + `os.fsync()` the temp file.
6. Verify the destination byte count / size.
7. If configured, hash the destination and compare with `hmac.compare_digest`.
8. Atomically publish via `os.replace` within the destination filesystem.
9. `os.fsync` the destination directory where supported.
10. Revalidate the source identity; only then delete the claimed source.
11. Record `MOVE_COMPLETE`.

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

## Logging levels

Configured once at the application boundary; business classes call
`logging.getLogger("file_mover.<area>")` and never install handlers. Job and file IDs
travel as structured `extra` fields, not in the logger name.

- **DEBUG** — per-chunk / per-step internal detail.
- **INFO** — job and file lifecycle transitions.
- **WARNING** — retryable failures and backoff.
- **ERROR** — retained failures and manual-intervention routing (with traceback for
  unexpected defects via `logger.exception`).
