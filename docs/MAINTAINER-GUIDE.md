# Maintainer Guide

Start here when onboarding to make changes. It covers the repo layout, local dev setup,
the command cheat sheet, common workflows, and the CI architecture.

## Repository layout

```
background-file-mover/
├── pyproject.toml            # Poetry project + all tool config (ruff/mypy/pytest/…)
├── poetry.lock
├── src/file_mover/           # the application package (stdlib-only runtime)
│   ├── cli.py  constants.py  exceptions.py  configuration.py  logging_config.py  service.py
│   ├── control/  jobs/  transfer/  recovery/
├── tests/                    # pytest suite; @pytest.mark.requirement drives the trace matrix
├── config/file-mover.ini     # fully commented reference configuration
├── packaging/systemd/        # systemd unit (filled in at M8)
├── scripts/                  # build-trace-matrix.py, coverage.sh, pytest-by-requirement.py, install-hooks.sh
├── docs/                     # requirements (L1/L2/L3), ARCHITECTURE, CLI/CONFIG refs, ROADMAP, TRACE-MATRIX, CAPTURE
└── .github/workflows/        # CI (ci.yml + codeql.yml + sonarcloud.yml)
```

## Local dev setup

Requires Python 3.10+ and Poetry.

```
poetry install                     # create venv + install dev tooling
poetry run file-mover --help       # smoke-check the CLI
```

The runtime package has **zero** dependencies; everything under `poetry install` is the
dev group (pytest, ruff, mypy, pylint, vulture, bandit).

## Command cheat sheet

```
poetry run pytest                          # run the suite
poetry run pytest --cov                     # with the coverage gate
poetry run ruff check                        # lint
poetry run ruff format                       # format (add --check in CI)
poetry run mypy src                          # strict type check (analysed as py3.10)
poetry run pylint src/file_mover             # lint (must stay 10.00/10)
poetry run vulture                           # dead-code
poetry run bandit -r src/file_mover          # security SAST
python scripts/build-trace-matrix.py         # regenerate docs/TRACE-MATRIX.md
python scripts/build-trace-matrix.py --check # CI drift gate
python scripts/pytest-by-requirement.py L2-CLI-003   # run tests for one requirement id
bash scripts/install-hooks.sh                # enable the pre-commit hook (once per clone)
```

## Workflow: adding a requirement + test

1. Add the SHALL statement to `docs/L1-REQ.md`, `L2-REQ.md`, or `L3-REQ.md` in the exact
   format the generator parses:
   - L1: `### L1-SYS-NNN` followed by a `**Verification Method**: …` line.
   - L2: `#### L2-CAT-NNN`, a `**Parent**: L1-SYS-NNN` line, and a `**Verification
     Method**:` line.
   - L3: `**L3-CAT-NNN** · Parent: L2-CAT-NNN · Verification: T, I` on one line.
   - If the category is new, add it to `CATEGORIES` in `scripts/build-trace-matrix.py`.
2. Write the test and tag it: `@pytest.mark.requirement("L2-CAT-NNN")`.
3. Regenerate: `python scripts/build-trace-matrix.py`, and commit `docs/TRACE-MATRIX.md`
   alongside the change. CI gates on `--check`.

## Workflow: adding a CLI flag

`create_parser()` in `src/file_mover/cli.py` is pure — no I/O, DB, or threads
(L3-CLI-001). Add the argument there, add a handler path, and cover it in
`tests/test_cli.py`. Keep machine output on stdout and diagnostics on stderr.

## Adding a config option

Options are defined once (from M2, via `OptionSpec`) and drive validation, docs, and the
`doctor` output. Update `config/file-mover.ini` and `docs/CONFIG-REFERENCE.md` in the
same change, and add a validation test.

## Adding an environment check (`doctor`)

Environment capabilities are strategies in `src/file_mover/diagnostics.py`. To add one:

1. Write a **detection helper** (module-level, so tests can simulate it):
   `def _my_capability() -> bool: ...`.
2. Write a **probe** returning `(available, detail)`:
   `def _probe_my_capability() -> tuple[bool, str]: return _my_capability(), "…"`.
3. Register it in `default_checks(...)` as an `EnvironmentCheck(name, Requirement.REQUIRED
   | OPTIONAL, probe)` — `REQUIRED` fails `doctor` (exit `ENVIRONMENT_UNSUPPORTED`),
   `OPTIONAL` only warns.
4. Test both branches by monkeypatching the detection helper (see `tests/test_diagnostics.py`),
   and trace it under `L2-ENV-*`. Never let a probe raise — `EnvironmentCheck.run` already
   turns an exception into a reported failure (L2-ENV-003).

## Adding a log call

Follow the convention in **`docs/LOGGING.md`** — stable `file_mover.<area>` logger, context
via `bind(logger, job_id=…, file_id=…)` (not the logger name), and gate by cost: DEBUG uses
`if __debug__ and GATE.debug:` (stripped under `python -O`), hot-path INFO uses
`if GATE.info:`, cold-path INFO/WARNING/ERROR call directly. Use `%`-style args, never
f-strings. Never install handlers — configuration is centralized in `logging_config.py`.

## CI architecture

`.github/workflows/ci.yml` runs, all via `poetry run`:

- **python** — pytest across the 3.10–3.14 matrix (Linux) + 3.12/3.14 (Windows), plus a
  package-build check.
- **python-coverage** — the combined line+branch coverage gate (`fail_under` in
  `pyproject.toml`).
- **mypy** — strict, analysed as Python 3.10.
- **ruff** — `check` + `format --check`.
- **pylint**, **vulture**, **bandit** — lint, dead-code, security.
- **trace-matrix** — `build-trace-matrix.py --check`.

`codeql.yml` and `sonarcloud.yml` add security and quality scanning (SonarCloud requires
the repo be onboarded and a `SONAR_TOKEN` secret set).

The pre-commit hook (`.githooks/pre-commit`, enabled via `scripts/install-hooks.sh`) runs
the cheap file checks plus ruff/mypy/pytest and the trace-matrix parity check, so failures
surface at commit time rather than in CI.

## Cross-cutting principles

- Runtime code imports **stdlib only** (L1-SYS-009). New third-party imports belong in the
  dev group.
- Never delete a source until the destination is published and verified (L1-SYS-003).
- Fail closed: no reduced-validation fallbacks; no `assert` for data-safety checks
  (L2-ARC-004/005).
- Prefer typed dataclasses/enums and narrow Protocols over `Any` and loose dicts.
