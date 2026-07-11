# Changelog

All notable changes to Background File Mover are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
