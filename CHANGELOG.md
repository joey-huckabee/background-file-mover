# Changelog

All notable changes to Background File Mover are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
