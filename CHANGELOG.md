# Changelog

All notable changes to Background File Mover are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
