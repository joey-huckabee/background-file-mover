# Contributing to Background File Mover

## Current Rust workflow (2026-11-07)

The application is implemented in Rust under `rust/`.

- Start each bounded increment on a short-lived `feature/<increment-name>` or
  `fix/<issue-name>` branch from current `main`. Keep one reviewable objective.
- Read `AGENTS.md`, [Rust direction](docs/RUST-DIRECTION.md), and the
  [agent workflow](docs/AGENT-WORKFLOW.md). Follow existing product approvals
  and release gates; a merge does not grant runtime/deployment authorization.
- The Windows checkout coordinates work. Sync committed source into the
  Linux-native WSL2 test clone as described in the agent workflow.
- Every Rust build/test uses `python3 scripts/check-rust-sles.py` and its
  `--qualification` mode (or the documented WSL wrapper). Both pinned SLES
  debug/release gates and independent ELF audits remain mandatory. Host-only
  Cargo tests do not qualify changes.
- Open a PR into `main`; complete independent review for substantial changes,
  address findings and wait for applicable checks to pass. Preserve validated
  commits/evidence and merge with a merge commit. Keep production releases and
  deployment approvals separate. Do not push implementation directly to `main`.

Current limits and validated results: [increment 112](docs/RUST-INCREMENT-112.md)
and [current source cleanup](docs/RUST-INCREMENT-114.md).


Optional staged-file hygiene: `bash scripts/install-hooks.sh`. The hook performs
no application build; Rust qualification uses the pinned SLES gates above.
