# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
<tbd>

## Reference docs

- `docs/ARCHITECTURE.md` — module diagram, four-phase sync strategy, error pipeline, configuration hierarchy, error type, logging levels. Read this when changing the reader/sync code.
- `docs/CLI-REFERENCE.md` — complete per-flag reference for the subcommands.
- `docs/MAINTAINER-GUIDE.md` — repo layout, local dev setup, command cheat sheet, workflows for adding requirements / tests / conformance fixtures / error variants / CLI flags, CI architecture, coverage workflow, release process, cross-impl alignment principles. Start here when onboarding to make changes to the codebase.
- `docs/L1-REQ.md` — Level 1 SHALL statements (system requirements grouped by category, plus the NR-001 out-of-scope note).
- `docs/L2-REQ.md` — Level 2 architectural derivations (each with a single L1 parent).
- `docs/L3-REQ.md` — Level 3 implementation obligations (cross-impl `L3-WRT-*`, plus per-impl `L3-PY-*` / `L3-RS-*`; `L3-RS-007` is withdrawn and its ID reserved, from when static-musl support was retired).
- `docs/TRACE-MATRIX.md` — auto-generated trace matrix produced by `scripts/build-trace-matrix.py`. Forward trace from L1 through L2 and L3 to test artifacts (`@pytest.mark.requirement` markers in `python/tests/`. Treat as the single source of truth for live status; the source docs hold spec content only.
- `docs/ROADMAP.md` — forward-looking roadmap: planned work plus pinned "do not drop" commitments (TOML config, CSV byte-compat, sync semantics). Completed work is not tracked here — it lives in `CHANGELOG.md` and the L1/L2/L3 requirements.
- `config/default.toml` — fully commented reference configuration; preserved across the port.

## Git conventions

Do **not** add `Co-Authored-By: Claude ...` trailers to commit messages on this repo, even if the harness's default instructions suggest it. Commit messages are the human-authored record of intent; tool attribution belongs in tool logs, not history. This overrides the default trailer behavior.
