# Changelog

All notable changes to Background File Mover are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- systemd `Type=notify` readiness + watchdog (pre-1.0): a stdlib-only `sd_notify`
  notifier (`file_mover/systemd.py`) that sends `READY=1` once the service is actually
  serving (lock held, state open, recovery done, socket bound), `STOPPING=1` during the
  drain, and a `WATCHDOG=1` keep-alive each scheduler tick. `systemctl start` and
  `After=file-mover` ordering now wait for real readiness instead of racing the control
  socket, and a hung service (e.g. a wedged NFS mount) is detected and restarted. It uses
  a plain `AF_UNIX` datagram to `$NOTIFY_SOCKET` (handling the abstract-namespace `@`
  prefix) and is a safe no-op when unset. The unit switches to `Type=notify` with
  `WatchdogSec=30`. Requirements: L2-CTL-011, L2-CTL-012, L3-PY-010. See
  `docs/ARCHITECTURE.md` (Service readiness) and `docs/DEPLOYMENT.md`.

### Changed

- The systemd unit uses `Type=notify` (was `Type=simple`), with `WatchdogSec` and
  `TimeoutStartSec`.

- Kernel-assisted copy (pre-1.0): `BufferedFileCopyEngine` can copy with
  `os.copy_file_range`, moving bytes directly between the source and destination file
  descriptors in the kernel instead of through the process. It is attempted only when the
  syscall is available and falls back cleanly to the bounded buffered loop on any
  "not supported" outcome (`ENOSYS`/`EOPNOTSUPP`/`EXDEV`/…), discarding partial output;
  genuine I/O errors still propagate. Controlled by the new `[transfer] use_kernel_copy`
  option (default `true`); integrity is unaffected (the destination is re-hashed
  regardless). Requirements: L2-COPY-011, L3-PY-009. See `docs/ARCHITECTURE.md`
  (Copy strategy) and the benchmark step in `docs/DEPLOYMENT.md`.

- Packaging & qualification (Milestone 8) — first-release hardening:
  - No-panic fuzz harness (`tests/test_fuzz.py`, requirement L1-ROB-001): deterministic,
    env-configurable fuzzing of every interaction surface (protocol decode/receive,
    dispatcher, config loader, CLI argv), asserting only documented exceptions ever occur.
    The `fuzz` CI workflow is revived as a scheduled deep burn-in.
  - Fault-injection tests (`tests/test_fault_injection.py`): failures at destructive
    boundaries (publish, manifest write, repository insert) provably retain the source
    data — nothing is lost.
  - Top-level CLI exception boundary: any unexpected error becomes a controlled
    `INTERNAL_ERROR` exit with a logged traceback (L2-CLI-010); the coordinator's
    source-deletion step is hardened against `OSError`.
  - Production systemd unit (`mover` service account, `RequiresMountsFor`,
    Runtime/State/Logs directories, full sandboxing) and `docs/DEPLOYMENT.md` — the
    server-setup runbook, acceptance tests, and NFS-qualification checklist.
  - Requirements: L1-ROB-001, L2-CLI-010.

- Recovery & service integration (Milestone 7) — the service now moves data on its own:
  - `RecoveryManager` — at startup, reconciles interrupted (in-progress) jobs against the
    filesystem: removes their stale `.swit-partial-` temporary files and re-queues them,
    from observable durable state rather than assumptions.
  - `TransferScheduler` — one tick selects runnable jobs (queued, or retry-waiting whose
    retry time has passed) up to the configured concurrency, re-queues due retries, and
    drives each through the coordinator. The coordinator now skips already-moved files, so
    recovery reprocessing is idempotent.
  - `BackgroundMoverService` main loop — `run()` reconciles, then runs the control server
    and a transfer-scheduler thread concurrently, with signal-driven graceful shutdown
    that drains the scheduler. After submitting, orchestration no longer needs to do
    anything: the service transfers the recording set to completion.
  - New `[service] poll_interval_seconds` configuration option.
  - Requirements: L2-REC-001..004, L2-RTY-004; coverage floor raised to 85%.

### Changed

- Coverage gate (`fail_under`) raised from 80% to 85%.

- Transfer engine (Milestone 6) — the durable `copy → verify → publish → delete-source`
  payload engine:
  - `IntegrityVerifier` — `hashlib` bounded-buffer hashing (SHA-256/512/BLAKE2b) with
    constant-time `hmac.compare_digest`.
  - `BufferedFileCopyEngine` — exclusive (`O_CREAT|O_EXCL`, `O_NOFOLLOW` where available)
    `.swit-partial-` temporary write in a bounded loop, `flush`+`os.fsync`, atomic
    `Path.replace` publish, and best-effort destination-directory fsync.
  - `ErrorClassifier` + bounded exponential backoff — classifies errors (transient →
    retry, operator-remediable → retain, request/config → reject) with a conservative
    retain default; errno constants resolved defensively for cross-platform import.
  - `TransferCoordinator` — the per-file workflow (verify claimed identity → optional
    source hash → copy → size/hash verify → publish → dir fsync → revalidate identity →
    delete claimed source) with existing-destination collision handling
    (verify-and-reuse / fail) and integrity-failure retention of both source and temp;
    a source is deleted only after its destination is published and verified.
  - Repository `update_file` / `record_job_progress`; `COPYING → COMPLETED` transition.
  - Requirements: L2-DPR-*, L2-COPY-*, L2-DST-*, L2-DEL-*, L2-RTY-*, L3-INT-*,
    L3-PY-002/003/004.

- Submission & claiming (Milestone 5) — the first milestone that moves real files:
  - `SourceValidator` — deterministic recursive inventory (excludes the claim directory),
    symbolic-link and non-regular-file rejection, path-under-approved-roots enforcement,
    device+inode+size+mtime identity capture, and injectable-sleeper stability polling.
  - `FileClaimManager` — same-filesystem atomic `Path.replace` of each file into a per-job
    `<source>/.swit-moving/<job>/` staging directory, with identity revalidation before
    and after the move.
  - `ManifestWriter` — flush + fsync + atomic-replace JSON manifests.
  - `JobSubmissionService` — idempotent-by-`request_id` orchestration
    (validate → claim → manifest → durably record); any failure retains already-claimed
    source files; returns a typed `SubmissionResult`.
  - `file-mover submit` (directory or `--file-list`) wired over the control socket; a
    durable acknowledgement is returned only after the files are claimed and recorded.
  - Requirements: L2-SUB-001..005, L3-SUB-001..002, plus L2-FS-*, L2-POSIX-002/006,
    L2-CLI-008/009.

- Durable job state (Milestone 4):
  - `SQLiteJobRepository` — the authoritative durable store (WAL, `synchronous=FULL`,
    `foreign_keys=ON`, `busy_timeout`, per-thread connections, idempotent
    `PRAGMA user_version` migrations). Every SQLite error and every corrupt stored value
    is translated to a typed `RepositoryError` so bad state can never crash the service.
  - Frozen `JobRecord`/`FileRecord`/`JobStatistics` models and the explicit allowed
    job-state-transition map with enforcement.
  - `status` / `list` / `stats` commands served over the control socket and rendered by
    the CLI (human and JSON), with `JOB_NOT_FOUND` when a job is absent.
  - Requirements: L2-JOB-001..006, L3-JOB-001..002, L3-PY-007, L2-RTY-003.

- Control plane (Milestone 3) — the first executable slice:
  - Length-prefixed JSON message framing (`control/protocol.py`) that rejects oversized
    frames before allocation and loops on `recv` until a full frame arrives.
  - `CommandDispatcher` with an explicit command→handler map that validates the request
    envelope, rejects unknown commands, echoes the request id, and isolates handler
    failures so a raising handler can never crash the service.
  - `ControlSocketServer` (AF_UNIX, small dedicated thread pool, safe stale-socket
    recovery) and `ControlClient`, plus an `fcntl`-based singleton `ProcessLock`.
  - `BackgroundMoverService` that acquires the lock, binds the socket, answers `health`,
    and shuts down cleanly on SIGTERM/SIGINT; wired to `file-mover service run`.
  - `file-mover health` command and centralized stderr logging (`logging_config.py`).
  - Requirements: L2-CTL-001..010, L3-CTL-001..004, L3-PY-006.

- Configuration subsystem (Milestone 2): a strict `ConfigurationLoader` that parses the
  INI file with `configparser`, rejects unknown sections/options and missing required
  values, converts values to typed fields, validates numeric ranges and cross-field
  constraints, and returns a frozen `ApplicationConfig`. All problems are collected and
  reported together as structured `ConfigurationIssue` records via
  `ConfigurationValidationError`. A single `OptionSpec`-driven `SECTION_SCHEMAS` is the
  one source of truth shared by validation, unknown-option detection, defaults, and
  `describe_schema()` documentation.
- `file-mover config validate` and a partial `doctor` command, with human and JSON
  output (machine JSON on stdout, diagnostics on stderr).

- Project foundation (Milestone 1): Poetry project with a `src/file_mover` package,
  standard-library-only runtime, and the full dev/CI quality battery
  (ruff, mypy --strict, pytest + coverage, pylint, vulture, bandit).
- Requirement baseline: L1 system requirements (`L1-SYS-*`), L2 architectural
  derivations, and L3 implementation obligations, with an auto-generated trace matrix
  (`docs/TRACE-MATRIX.md`) produced by `scripts/build-trace-matrix.py`.
- Declarative core: on-disk/protocol constants, the `FileMoverError` exception hierarchy,
  and the job/file/integrity/exit-code enums.
- CLI parser surface (`file-mover`) with all subcommands, verbosity, and output options;
  `--help` / `--version` functional. Transfer behavior is not yet implemented.
- Reference configuration (`config/file-mover.ini`) and documentation set
  (architecture, CLI, config, maintainer guide, roadmap).
