# Changelog

All notable changes to Background File Mover are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Incremental retirement of `docs/CAPTURE.md`.** The original design conversation is being
  retired section by section as each is verified to be fully captured in a canonical doc,
  requirement, config option, or code+tests. A retirement ledger at the top of the file
  records where each removed section now lives; git history retains the removed content.
  First retired: *Recommended Initial Build Order* → `docs/ROADMAP.md`.
- **Twelve-factor logging.** The service now writes its event stream to the standard streams
  and lets the environment (systemd's journal, a log shipper) route it — `INFO`/`DEBUG` to
  **stdout**, `WARNING` and above to **stderr** — and no longer manages log files. The CLI is
  unchanged (stdout = command result, stderr = diagnostics) (L3-PY-013).

### Removed

- **`[logging]` destination options `log_to_journal`, `log_to_file`, and `log_directory`.**
  In the twelve-factor model the application does not choose log destinations, so these were
  removed; `[logging]` now exposes only `level` (with `OFF`). **Migration:** delete those
  keys from your INI (strict validation now rejects them), and route/rotate logs at the
  environment level (journald, or redirect the service's stdout/stderr).

### Added

- **`file-mover doctor` now verifies the runtime environment.** It checks the capabilities
  the service depends on — `AF_UNIX` sockets, `fcntl` locking, SQLite WAL, the configured
  hash algorithm, Python ≥ 3.10, POSIX signals (required), plus `O_NOFOLLOW` and
  kernel-assisted copy (optional/advisory) — and reports each with `pass`/`warn`/`fail`.
  A missing **required** capability returns the new `ExitCode.ENVIRONMENT_UNSUPPORTED` (8),
  so a deployment can gate on `doctor` (L2-ENV-001..003).

### Fixed

- **Pausing an in-flight copy with `resume_partial_files = false` no longer fails on resume.**
  The kept partial would previously collide with the exclusive create when the job resumed;
  now a pause under a disabled resume policy drops the partial so the file cleanly restarts
  from byte zero (mirroring startup recovery). With resume enabled the partial is kept and
  continued as before (L2-RSM-002).

### Added

- **Gated, context-aware logging with near-zero overhead when off.** Job/file correlation is
  carried in structured fields (`extra={job_id, file_id}`) via stable `file_mover.<area>`
  loggers and a `ContextFormatter`, and lifecycle DEBUG/INFO events were added across the
  transfer, state, submission, recovery, and control paths (previously the transfer path
  logged nothing). A per-level `LogGate` computed once at startup lets a disabled level cost
  a single boolean — no `isEnabledFor`, argument evaluation, formatting, or dispatch. Hot
  paths guard DEBUG with `if __debug__ and GATE.debug:`, which `python -O` strips from the
  bytecode entirely; `[logging] level = OFF` disables all logging. The systemd unit runs the
  service under `-O` (L3-PY-014).
- **`[logging]` configuration is now applied at service start** — `level`, `log_to_journal`
  (stderr), and `log_to_file` (a size-rotating file under the new `log_directory` option)
  take effect, with an explicit CLI `-v`/`--log-level` taking precedence (L3-PY-013). This
  closes a gap where the section was validated but ignored.
- **`file-mover doctor` now reports advisories** for valid-but-consequential option
  combinations — a bandwidth limit with `use_kernel_copy` (kernel copy is bypassed while
  limited) and `resume_partial_files` without `source-and-destination-hash` (a crash-torn
  resume may go undetected). The same advisories are logged once at service start.

### Documentation

- Added **`docs/LOGGING.md`** (the stdout/stderr + logging architecture, for operators *and*
  developers — the output-stream contract, consuming/routing logs, and how to add a log
  call) and **`docs/12-FACTOR.md`** (twelve-factor alignment and deliberate deviations).
  Documented `doctor`'s environment checks in CLI-REFERENCE, added it as a deploy gate and a
  logs section in DEPLOYMENT, and "add an environment check" / "add a log call" workflows in
  MAINTAINER-GUIDE; ARCHITECTURE gained a diagnostics section and cross-links.
- Added `docs/FEATURE-INTERACTIONS.md`, an operator guide to combining kernel-assisted
  copy, bandwidth limiting, partial-file resume, and pause/cancel/resume — which
  combinations force the buffered engine, how a runtime `throttle` relates to an in-flight
  kernel copy, and the two sharp edges (resume crash-safety depends on `[integrity] mode`;
  `pause`/`resume` relies on `resume_partial_files`). Added a matching *Feature
  interactions* matrix to `docs/ARCHITECTURE.md` and cross-links from the config/CLI
  references and the reference INI.

## [0.3.0] - 2026-07-12

Adds operator **job lifecycle control** (cancel / pause / resume) and **partial-file
byte-offset resume**, alongside a separation-of-concerns refactor of the transfer and
control layers. Zero runtime dependencies; the full CI battery, no-panic fuzz harness,
L1/L2/L3 trace matrix, and SonarCloud quality gate remain green.

### Added

- **Job lifecycle control** — `file-mover pause` / `resume` / `cancel`. A job that is not
  copying is transitioned directly with a compare-and-set; an in-flight copy is stopped
  **cooperatively** at a safe buffer boundary via a thread-safe pause/cancel signal (there
  is no OS primitive to pause a file copy). Cancel always **retains the source** and
  discards only the incomplete partial; resume returns a paused job to the queue. New
  `PAUSED` state and transitions (L2-LIF-001..005).
- **Partial-file byte-offset resume** (`[transfer] resume_partial_files`, default on) — an
  interrupted copy continues from its fsynced `.swit-partial-` offset using `os.stat` /
  `os.lseek` / `os.copy_file_range` rather than restarting a large recording from byte
  zero. Startup recovery preserves interrupted partials when resume is enabled
  (L2-RSM-001/002, L3-PY-012).

### Changed

- **Separation of concerns (Fowler).** Extracted the per-file workflow into `FileMover`
  (job orchestration stays in `TransferCoordinator`), the control-response wire format into
  `presentation.py`, the lifecycle operations into `control/lifecycle.py`, the pause/cancel
  registry into `transfer/control_signals.py`, and partial cleanup into
  `transfer/partials.py` — reducing class/function complexity with no behaviour change.

### Security

- A resumed partial that fails size or hash verification is discarded and the file restarts
  from zero; unverified bytes are never published (L2-RSM-003).

## [0.2.0] - 2026-07-12

Adds dynamic bandwidth limiting — a userspace token-bucket throughput ceiling that is
adjustable live over the control socket — and resolves the first round of static-analysis
findings. Zero runtime dependencies; the full CI battery, no-panic fuzz harness, and
L1/L2/L3 trace matrix remain green.

### Added

- **Dynamic bandwidth limiting.** A configurable aggregate copy-throughput ceiling,
  `[transfer] max_bytes_per_second` (bytes/sec; `0` = unlimited), enforced in userspace by
  a thread-safe token bucket shared across all concurrent copies — no `tc`/cgroup or
  `libsystemd` dependency (L2-BWL-001/003/004, L3-PY-011).
- **`file-mover throttle <bytes-per-second>`** control command that retunes the live limit
  without restarting the service (applies to in-flight copies); accepts SI/IEC suffixes
  (`50MB`, `1GiB`). The current ceiling is reported as `max_bytes_per_second` in
  `file-mover health` (L2-BWL-002).

### Changed

- A non-zero throughput limit forces the buffered copy strategy, because kernel-assisted
  `copy_file_range` moves bytes inside the kernel and cannot be paced from userspace
  (L3-PY-011). An unlimited limit leaves the kernel-copy fast path unaffected.

### Security

- Validate and normalise the operator-supplied configuration path before it is read:
  reject NUL bytes, resolve to an absolute real path, and require an existing regular file,
  closing a path-injection finding.

## [0.1.0] - 2026-07-11

First release. A durable, **standard-library-only** (Python 3.10) background transfer
coordinator that moves completed simulation recordings from a local NFS mount to a remote
processing filesystem independently of the simulation orchestration, with transaction-like
`claim → copy → verify → publish → delete-source` semantics. A source file is never
deleted until its destination has been written, fsynced, published, and verified.

### Added

**Service & operations**

- systemd-managed background service (`file-mover service run`) with a singleton `fcntl`
  process lock, `Type=notify` readiness + `WatchdogSec` liveness, and signal-driven
  graceful shutdown that drains in-flight work.
- Unix-domain-socket control plane: length-prefixed JSON protocol, a `CommandDispatcher`
  with a static command→handler map, and safe stale-socket recovery.
- CLI (`file-mover`): `submit`, `status`, `list`, `stats`, `health`, `config validate`,
  `doctor`, `service run` — with human and JSON output, documented exit codes, and a
  top-level exception boundary.

**Submission & claiming**

- Idempotent-by-`request_id` submission that atomically claims files into a per-source
  `.swit-moving/<job>/` staging directory (same-filesystem `os.replace`, device+inode
  identity checks), writes a durable JSON manifest, and returns only after the job and its
  file inventory are recorded. Directory and `--file-list` submissions; symbolic-link and
  non-regular-file rejection; optional source-stability polling.

**Transfer engine**

- Durable per-file workflow: verify claimed identity → optional source hash → copy to a
  `.swit-partial-` temporary file → size/hash verify → atomic publish → directory fsync →
  revalidate identity → delete the claimed source.
- Configurable integrity (`metadata` / `source-hash` / `source-and-destination-hash`) via
  `hashlib` with constant-time `hmac.compare_digest`.
- Kernel-assisted copy (`os.copy_file_range`, `[transfer] use_kernel_copy`) with a safe
  fallback to a bounded buffered loop; existing-destination collision handling
  (verify-and-reuse / fail); error classification and bounded exponential-backoff retry.

**Durability & recovery**

- SQLite job/file state (WAL, `synchronous=FULL`, `foreign_keys=ON`, per-thread
  connections, idempotent migrations) as the authoritative durable queue, with an
  explicit, enforced job state machine.
- Startup recovery reconciles interrupted jobs against the filesystem (re-queue, remove
  stale temporaries) idempotently; a transfer scheduler drives queued and due-retry jobs
  to completion on its own.

**Robustness ("no panic")**

- Every operational error becomes a typed, classified state; the control dispatcher, the
  SQLite repository, and the CLI never crash on bad input.
- A deterministic no-panic fuzz harness over the protocol, dispatcher, configuration
  loader, and CLI argv (`L1-ROB-001`), plus fault-injection tests proving source retention
  at every destructive boundary.

**Configuration & documentation**

- Strict INI configuration (`configparser`): unknown-section/option rejection,
  missing-required detection, range and cross-field validation, with all issues reported
  together; a single `OptionSpec` schema drives validation and generated docs. A
  fully-commented reference config ships in `config/file-mover.ini`.
- Documentation: architecture, CLI, config, maintainer guide, deployment runbook +
  NFS-qualification checklist, roadmap, and a full L1/L2/L3 requirement set with an
  auto-generated trace matrix.

**Quality**

- CI on Python 3.10–3.14 (Linux) plus Windows smoke: pytest with an 85% coverage floor,
  mypy `--strict`, ruff, pylint, vulture, bandit, CodeQL, SonarCloud, and a scheduled
  no-panic fuzz burn-in.

[Unreleased]: https://github.com/joey-huckabee/background-file-mover/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/joey-huckabee/background-file-mover/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/joey-huckabee/background-file-mover/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/joey-huckabee/background-file-mover/releases/tag/v0.1.0
