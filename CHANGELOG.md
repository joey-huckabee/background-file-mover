# Changelog

All notable changes to Background File Mover are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/joey-huckabee/background-file-mover/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/joey-huckabee/background-file-mover/releases/tag/v0.1.0
