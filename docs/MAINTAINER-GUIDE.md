# Maintainer Guide

Start here when onboarding to make changes. It covers the repo layout, local dev setup,
the command cheat sheet, common workflows, and the CI architecture.

## Repository layout

```
background-file-mover/
├── cpp/                      # the implementation — the only one in this branch
│   ├── src/  include/filemover/    # library sources and public headers
│   ├── tests/                # Catch2 suite; "[L3-CPP-NNN]" tags drive the trace matrix
│   ├── fuzz/                 # libFuzzer targets + committed corpora, one set per target
│   ├── scripts/              # verify-vendored, assert-locale-free, assert-compile-db, coverage-summary
│   ├── third_party/          # vendored, hash-pinned, never edited (ADR-0004)
│   └── Makefile  VENDORED.md  README.md
├── scripts/build-trace-matrix.py   # generates docs/TRACE-MATRIX.md (stdlib Python)
├── docs/                     # requirements (L1/L2/L3), ADRs, TRACE-MATRIX, security, roadmap
├── config/file-mover.ini     # RETIRED reference config for the Python build; kept, bannered
├── .githooks/pre-commit      # file hygiene, trace parity, then the C++ gates
└── .github/workflows/        # cpp-ci.yml, cpp-fuzz.yml, codeql.yml, sonarcloud.yml
```

The Python tree (`src/`, `tests/`, `pyproject.toml`, `packaging/`) was removed ahead of
v1.0.0 and remains on `main` and at the `v0.4.2` tag. `scripts/build-trace-matrix.py`
stayed behind: it is repository infrastructure rather than product code, and it imports
only the standard library, so it needs no Python packaging to run.

## Local dev setup

Requires a C++11 compiler, GNU make, and Python 3 for the trace generator. The canonical
checkout lives **inside WSL** on a Linux-native filesystem — `CLAUDE.md` records why
building under `/mnt/c` is both unreliable and ~500× slower for small-file I/O.

Full toolchain setup, including the analyzers and container tiers, is in
`CONTRIBUTING.md`.

## Command cheat sheet

```
cd cpp
make check                       # build + run the suite (-Werror, so this is the compile gate too)
make check SANITIZE=1            # ASan + UBSan + LSan
make check THREAD=1              # ThreadSanitizer
make check-valgrind              # Valgrind memcheck
make verify-vendored             # vendored files match their recorded SHA-256
make locale-free                 # parsers never use <cctype> (L3-CPP-052)
make coverage                    # gcov report
make fuzz-corpus                 # replay every committed seed (the PR gate)
make fuzz-run FUZZ_SECONDS=60    # live fuzzing session, per target
make check-ci                    # every gate above, in a container, as CI runs them
make tidy                        # clang-tidy (needs compile_commands.json)

cd ..
python3 scripts/build-trace-matrix.py          # regenerate docs/TRACE-MATRIX.md
python3 scripts/build-trace-matrix.py --check  # CI drift gate
bash scripts/install-hooks.sh                  # enable the pre-commit hook (once per clone)
```

**Read the tail of `make check-ci` rather than the exit status of a pipeline.** Piping it
to `tail` reports `tail`'s status, which has masked a genuinely failing gate more than
once here.

## Workflow: adding a requirement + test

1. Add the SHALL statement to `docs/L1-REQ.md`, `L2-REQ.md`, or `L3-REQ.md` in the exact
   format the generator parses:
   - L1: `### L1-SYS-NNN` followed by a `**Verification Method**: …` line.
   - L2: `#### L2-CAT-NNN`, a `**Parent**: L1-SYS-NNN` line, and a `**Verification
     Method**:` line.
   - L3: `**L3-CAT-NNN** · Parent: L2-CAT-NNN · Verification: T, I` on one line.
   - If the category is new, add it to `CATEGORIES` in `scripts/build-trace-matrix.py`.
   - On an L1, the `**v1.0.0 Status**:` line must start with a bare word (`Active`,
     `Deferred`, `Partial`, `Rewritten`). The generator reads it to compute
     scope-adjusted coverage, and prose before the word makes it unparseable.
2. Write the test and tag it. **In C++ the tag is a Catch2 tag:**

   ```cpp
   TEST_CASE("rejection errors name the offending byte offset",
             "[json][L3-CPP-019]") { ... }
   ```

   The generator reads requirement ids straight out of the `TEST_CASE` tag string, so a
   tag is the whole mechanism — there is nothing else to register. Catch2 can also select
   on it, which makes the matrix entry a runnable command:
   `./filemover_tests "[L3-CPP-019]"`. The legacy pytest form
   (`@pytest.mark.requirement("L2-CAT-NNN")`) is still understood, for the Python tests
   that live on `main`.

3. Choose the verification method honestly. `T` commits you to a test that can actually
   fail. If the evidence is a build gate rather than an assertion — "compiles clean under
   `-Werror` on GCC 4.8.5" — the method is `D`, not `T`; marking it `T` leaves a
   permanent hole in the matrix against a requirement that is in fact gated on every
   commit. `L3-CPP-013` was exactly this mistake.
4. Regenerate: `python3 scripts/build-trace-matrix.py`, and commit `docs/TRACE-MATRIX.md`
   alongside the change. CI and the pre-commit hook both gate on `--check`.

---

> **The workflows below describe the retired Python implementation** and the modules they
> name (`cli.py`, `diagnostics.py`, `logging_config.py`) are not in this branch. They are
> kept because the *shape* of each workflow — define an option once and let it drive
> validation, docs, and diagnostics; never let a probe raise; keep machine output on
> stdout — is the design the C++ is being built toward. Each gets rewritten as the
> corresponding C++ lands. Tracked in `docs/ROADMAP.md`.

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

## Testing strategy

"Fully pytested" means more than line coverage: **every state transition and every
interruption/destructive boundary must have a test.** That principle — not the raw coverage
number — is the bar. Tests fall into five layers:

- **Unit** — components in isolation: configuration validation, path validation, manifest
  serialization, state transitions, retry backoff, hash calculation, collision policies,
  submission validation, source→destination mapping, error classification.
- **Integration** — real files in temporary directories: atomic claim, copy + publish,
  destination-hash verification, source deletion after success, source retention after
  failure, partial-transfer recovery, identical-destination reuse, conflicting-destination
  rejection, nested directories, and edge inputs (empty files, Unicode names, long-but-legal
  names).
- **Fault-injection** — raise a deterministic failure at each destructive boundary and
  assert the source survives: after claim, after job insert, during source hash, after
  manifest write, during copy, after destination flush, during destination hash, after
  publication, before source deletion, after source deletion, and before the final DB
  update. Filesystem ops, clocks, and repository interfaces are injectable so tests can
  force these exceptions deterministically.
- **Process-recovery** — start the service, interrupt it, and restart it with jobs in each
  non-terminal state; assert the job survives and reconciles (mirrors the acceptance tests
  in `docs/DEPLOYMENT.md`).
- **NFS-representative** — behaviors a local tmpdir cannot reproduce (destination-mount
  loss, stale handles, `ENOSPC`, cross-client visibility, sustained ~100 GB). These are the
  deployment-time **NFS qualification checklist** in `docs/DEPLOYMENT.md`, run against the
  real mounts rather than in CI.

Quality gates — the coverage floor, ruff/mypy/pylint/vulture/bandit, and 100% of
requirements mapped to a test — are enforced by CI and the trace matrix (see the cheat
sheet above and *CI architecture* below).

## CI architecture

`.github/workflows/cpp-ci.yml` carries thirteen jobs; `make check-ci` reproduces all of
them locally in a container, so a red branch is avoidable.

Nine of them — every job that compiles — run inside the toolchain image
`ghcr.io/joey-huckabee/bfm-ci` (built from `.github/ci-image/Dockerfile`), so CI and
`check-ci` execute the *same* toolchain rather than two separately pinned copies of it.
The other four stay on the runner deliberately: the fidelity job drives `docker run`
itself, and the vendored-integrity, trace-matrix, and locale-free gates need no compiler.

- **build & test (g++-14)** — fast feedback on a modern toolchain.
- **build & test (gcc 4.8.5)** — the SLES 12 SP5 fidelity tier, running
  `ghcr.io/joey-huckabee/gcc-4.8:4.8.5`, a mirror of the official `gcc:4.8` image
  republished with a v2s2 manifest. It runs the **full suite**, not just a compile; that
  is what closes the gap between the instrumented build and the shipped one. Do not
  reduce it to `make all`, and do not point it back at the upstream tag — that image
  carries a 2016 schema-1 manifest which modern Docker refuses, and this job silently
  failed at the pull for some time because podman still accepted it locally.
- **ASan + UBSan + LSan** — carries `--cap-add=SYS_PTRACE`. LeakSanitizer uses ptrace and
  containers block it by default; the job needed no capability before it ran in one.
- **ThreadSanitizer** and **Valgrind memcheck** — separate jobs from the sanitizer one.
  TSan cannot share a binary with ASan: their shadow-memory layouts conflict.
- **Vendored file integrity** — SHA-256 against `cpp/VENDORED.md`. A repository-wide edit
  once rewrote an identifier *inside* the vendored Catch2 header and every other gate
  passed; a compiler cannot tell, only a checksum can.
- **Locale-free parsers** — greps the parser sources for `<cctype>` and the `strtoul`
  family (`L3-CPP-052`). A source gate because the runtime test needs a locale the
  runners do not always have.
- **cppcheck** and **clang-tidy** — they disagree often enough to justify both.
  clang-tidy needs a compilation database, and `scripts/assert-compile-db.sh` proves the
  database actually covers the sources: an empty one made the gate skip every file and
  exit zero.
- **Fuzz corpus replay** and **Fuzz (60s)** — the regression gate and a short live
  session. The deep burn-in is nightly, in `cpp-fuzz.yml`.
- **Coverage (gcov)** — reported per PR and consumed by SonarCloud.

`codeql.yml` and `sonarcloud.yml` add security and quality scanning (SonarCloud requires
the repo be onboarded and a `SONAR_TOKEN` secret set). Both are C++-only on this branch.

- **Requirements trace matrix** — `build-trace-matrix.py --check`. This gate used to live
  in the Python workflow and moved here when that was removed: it covers the
  *requirements*, not either implementation, so it outlives both. The pre-commit hook
  runs it too.

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
