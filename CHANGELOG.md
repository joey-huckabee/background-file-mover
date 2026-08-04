# Changelog

All notable changes to Background File Mover are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Work toward the C++11 / REST **v1.0.0**, on one branch per milestone off `main`
(currently `c1-durable-store`). The `v2-cpp` branch these entries were originally written
against merged into `main` at the C0 boundary and was retired.

**`main` no longer ships Python.** The implementation to deploy today is the `v0.4.2`
tag, not a branch.

### Added

- **SQLite is vendored and pinned at 3.53.4** (ADR-0010, ADR-0004), filling the last
  `pending` row in `cpp/VENDORED.md`. The zip was authenticated against upstream's
  published SHA3-256 and byte size before extraction, and `sqlite3.c` / `sqlite3.h` are
  hash-pinned individually — `make verify-vendored` checks four files now, not two.
  The latest release proved viable on GCC 4.8.5, so no version step-back was needed.
  It compiles by its own Makefile rule, with `-Werror` intact: `-fno-strict-aliasing`
  removes the type-punning diagnostics at their cause rather than suppressing them, and
  `-Wextra` is dropped because its style warnings can only be satisfied by editing a file
  ADR-0004 forbids editing. Extension loading, double-quoted string literals, and memory
  accounting are compiled out.
- **`tests/test_sqlite_vendor.cpp`**, covering the two things a vendoring commit can get
  wrong that no other gate would catch: `sqlite3.c` and `sqlite3.h` drifting to different
  releases despite each being individually hash-intact, and the compile-time hardening
  silently not taking effect. It carries **no requirement tag** and does not move the
  trace figure — vendoring a dependency verifies no requirement.

### Removed

- **The Python implementation is no longer in the tree.** `src/file_mover/`,
  the pytest suite, `pyproject.toml`, `poetry.lock`, `packaging/systemd/`, and the Python
  CI workflows (`ci.yml`, `fuzz.yml`) were deleted. Nothing is lost: that code is tagged
  `v0.4.2` — on `origin` as well as locally — which remains the version to deploy today.
  `scripts/build-trace-matrix.py` stayed — it is repository infrastructure covering the
  requirements rather than either implementation, and it imports only the standard
  library, so it needs no Python packaging.

### Changed

- **One branch per milestone, replacing the long-lived `v2-cpp` branch.** C0 merged into
  `main` with `--no-ff` and was published; `v2-cpp` was deleted locally and on `origin`.
  Work now happens on `c<N>-<short-name>` branches cut from `main` and deleted at the
  boundary. The cadence, and the `git branch -d` refusal that makes a fully-merged branch
  look unmerged, are documented in `docs/ROADMAP.md`.
- **CI pins a C compiler.** `CC` is set to `gcc-14` alongside `CXX: g++-14`, and the jobs
  that compile now install `gcc-14`. The `g++-14` package alone leaves no usable `cc`, so
  the first build with a C translation unit in it failed with `make: cc: No such file or
  directory`; the runner's default `cc` is gcc-13, a different compiler from the one
  building the C++ objects. The fidelity job blanks `CC` as it already blanked `CXX`.
- **The GCC 4.8.5 fidelity tier runs from a mirror, `ghcr.io/joey-huckabee/gcc-4.8:4.8.5`.**
  `docker.io/library/gcc:4.8` was pushed in 2016 with a Docker manifest v2 *schema 1*,
  which modern Docker disables by default; the CI job had been dying at the pull with
  `exit code 125` before compiling anything, while the same tier passed locally because
  podman still accepts schema 1. The mirror is that image republished with a v2s2
  manifest. Schema 1 is slated for removal outright, so pinning the upstream tag would
  not have survived. **The tier that decides whether the code ships had not actually run
  in CI for some time.**
- **`make check-gcc48` replaces three hand-written container invocations.** `cpp-ci.yml`,
  `CONTRIBUTING.md`, and `CLAUDE.md` each spelled out their own `docker`/`podman` command,
  which is how CI and developers came to pull different images without anyone noticing.
  One target, one `GCC48_IMAGE`, both callers.
- **The CI tiers compile in parallel.** `make -j` across `check-ci`, `check-gcc48`, and
  every compiling workflow job, with `CI_JOBS` defaulting to `nproc`. Measured on a
  16-core host: the default tier went from **97s to 52s** from clean, and five
  consecutive clean parallel builds passed — the test that matters, since a missing
  prerequisite surfaces under `-j` as an intermittent failure rather than a reproducible
  one. It will not scale past this: the vendored `sqlite3.c` is a single 9.5 MB
  translation unit taking **48.8s** against 1.35s for a typical C++ file, so a parallel
  build is now almost exactly "compile sqlite3.c".
- **The vendored SQLite object is cached with ccache.** It is the one source here that
  never changes — ADR-0004 forbids editing vendored files — and the most expensive to
  build, so every one of the five or six rebuilds per `check-ci` run produced a
  byte-identical object at ~49s each. Measured in the CI container: **60s cold, 0s warm.**
  Scoped to that object alone and deliberately not applied to the project's own sources,
  where the saving is a second or two and the coverage tier compiles with `--coverage`,
  which requires ccache to place `.gcno` files where gcov can resolve them — a real risk
  for no measurable gain, in a project whose coverage reporting has already been broken
  once by a path-resolution subtlety.
- **Every compiling CI job runs in the toolchain image.** Nine of the thirteen jobs in
  `cpp-ci.yml` declare it as their `container:` and no longer `apt-get install` anything,
  so CI and `make check-ci` now execute the same toolchain rather than two independently
  pinned copies of it. The ASan job carries `options: --cap-add=SYS_PTRACE`: LeakSanitizer
  uses ptrace, containers block it by default, and it was previously exempt only because
  GitHub's runner is not a container. The remaining four jobs stay on the runner
  deliberately — the fidelity job drives `docker run` itself, and the vendored-integrity,
  trace-matrix, and locale-free gates need no compiler.
- **`make check-ci` runs from a prebuilt toolchain image** (`.github/ci-image/Dockerfile`,
  published as `ghcr.io/joey-huckabee/bfm-ci`) instead of apt-installing the toolchain on
  every invocation. The Makefile used to justify that cost as "the price of not
  maintaining a second distro"; the repository already maintains the GCC 4.8.5 mirror, so
  the trade changed. The image *is* the pin, which is why the package list is not
  duplicated back into the Makefile. Tags are dates, never `latest`, so a run always
  names the toolchain it used. The runtime `locale-gen` became an assertion that
  `tr_TR.UTF-8` exists, so a future image dropping it fails the gate rather than quietly
  downgrading the L3-CPP-052 check to a warning.
- **SonarCloud coverage is ingested rather than silently discarded.** The scanner now runs
  with `sonar.projectBaseDir=cpp`. gcov records the path it compiled with -- `src/config.cpp`,
  relative to `cpp/` -- and scanning from the repository root made SonarCloud look for
  `<root>/src/config.cpp`, log `File not analysed by Sonar, so ignoring coverage` for
  every file, drop the whole report, and let the Zero Coverage Sensor record 0%. The
  analysis still succeeded, so this stayed invisible until a default-branch push waited
  on the Quality Gate and failed it.
- **The trace-matrix generator reads Catch2 tags as well as pytest markers.** A
  requirement id inside a `TEST_CASE` tag string — `TEST_CASE("...",
  "[json][L3-CPP-019]")` — now counts as verification evidence. Until this landed the
  generator scanned only `tests/*.py`, so 49 tagged C++ tests traced to nothing and the
  matrix reported the C++ tree as entirely untested. Removing Python without fixing this
  first would have taken the whole matrix to zero.
- **The matrix reports a v1.0.0 scope-adjusted figure** alongside the unadjusted one.
  Five L1 requirements are annotated `Deferred`, which places 69 L2/L3 requirements
  outside this release; counting those against v1.0.0 reported a gap that is a deliberate
  decision rather than missing work. Both numbers are published — the unadjusted one
  remains the honest total.
- **The pre-commit hook now gates C++** — vendored-file integrity, the locale-free parser
  check, then `make check` — instead of ruff, mypy, and pytest. The file-hygiene and
  trace-matrix parity checks are unchanged.
- **`codeql.yml` and `sonarcloud.yml` are C++-only**, and the requirements trace-matrix
  gate moved into `cpp-ci.yml`. That gate lived in the deleted `ci.yml`; without the move
  the removal would have silently dropped it.
- **Documents describing the Python implementation are retained, not deleted**, each
  behind a banner marking it as source material for the C++ rewrite. The rewrites owed
  are tracked in `docs/ROADMAP.md`. `docs/12-FACTOR.md` is only *partly* superseded and
  now says which parts: factor VII inverted when the `AF_UNIX` socket became a REST port,
  taking the free filesystem-permission authentication with it.

### Fixed

- **The fidelity container was documented as the wrong operating system.** Six places
  described `gcc:4.8` as a Debian Jessie base with glibc 2.19; it is Debian 7.10
  "wheezy" with **glibc 2.13**, confirmed from `/etc/os-release` and `getconf`. The error
  was benign in direction -- 2.13 is *older* than the SLES 12 SP5 target's 2.22, making
  the tier a more conservative floor than advertised rather than a weaker one, so every
  "passes on 4.8.5" conclusion still holds. Corrected in `cpp-ci.yml`, `cpp/README.md`,
  `CONTRIBUTING.md`, `cpp/Makefile`, and ADR-0001 and ADR-0005 (a factual correction to
  their context sections; no decision changed).
- **`L3-CPP-019` was implemented but untested.** The JSON parser has always reported the
  byte offset of a rejection; nothing asserted it. The non-empty half of the requirement
  was covered incidentally by a test helper, which is what disguised the gap.
- **`L3-CPP-013` declared verification by Test for a property no test can assert** — that
  the code compiles clean under `-Werror` on GCC 4.8.5. It is verified by Demonstration
  on every commit by the fidelity CI tier. A modeling error rather than a missing test,
  and it left a permanent hole in the matrix.
- **`L1-SYS-015`'s status line was unparseable.** It read `**Rewritten.**` where every
  other status is a bare word, so status-driven tooling skipped it silently.

## [0.4.2] - 2026-07-12

### Documentation

- **`docs/DEPLOYMENT.md` gained end-to-end platform runbooks.** A complete **Red Hat
  Enterprise Linux 9** walkthrough (install `python3.11`, the `mover` service account, the
  shipped systemd unit, SELinux with `audit2allow`, `doctor` validation) and a separate
  **SUSE Linux Enterprise Server 12** walkthrough (building CPython 3.10 from source — with
  the OpenSSL-1.0.2 caveat that `ssl`/`_hashlib` are skipped but the built-in hashes still
  work — a manually-created state directory and a trimmed systemd-228 unit, and AppArmor).
  Cross-linked `docs/USER-GUIDE.md`, and corrected the vestigial `/var/log` / `log_to_file`
  note left over from twelve-factor logging.

## [0.4.1] - 2026-07-12

### Added

- **`docs/USER-GUIDE.md`** — an install / deploy / use guide. It explains the topology (the
  CLI and the service share **one** virtualenv and **one** config file — the CLI reads it only
  to find the control socket; there is no separate CLI venv or config), the **system-service
  (root)** and **rootless (per-user, `systemctl --user`)** deployment models, a step-by-step
  **Red Hat Enterprise Linux 9** tutorial (Python 3.11, SELinux, NFS permissions), everyday
  CLI usage, and platform notes — including a **SLES 12** assessment (not recommended: no
  Python ≥ 3.10 in-repo, and systemd v228 predates `StateDirectory`/`LogsDirectory`).

### Removed

- **`docs/CAPTURE.md`.** The original design conversation was fully retired into the
  specifications in v0.4.0 and is now deleted; its content remains in git history and the
  v0.4.0 changelog entry. The references in `CLAUDE.md`, `docs/ROADMAP.md`, and
  `docs/MAINTAINER-GUIDE.md` were updated accordingly.

## [0.4.0] - 2026-07-12

Operability, observability, and provenance: `doctor` now gates a deployment on the runtime
environment, logging is twelve-factor and effectively free when off, and every job's
manifest agrees with its durable record — while the original design conversation has been
fully retired into the specifications. Runtime is still Python-3.10 standard library only.

### Added

- **`file-mover doctor` now verifies the runtime environment.** It checks the capabilities
  the service depends on — `AF_UNIX` sockets, `fcntl` locking, SQLite WAL, the configured
  hash algorithm, Python ≥ 3.10, POSIX signals (required), plus `O_NOFOLLOW` and
  kernel-assisted copy (optional/advisory) — and reports each with `pass`/`warn`/`fail`.
  A missing **required** capability returns the new `ExitCode.ENVIRONMENT_UNSUPPORTED` (8),
  so a deployment can gate on `doctor` (L2-ENV-001..003).
- **`file-mover doctor` also reports advisories** for valid-but-consequential option
  combinations — a bandwidth limit with `use_kernel_copy` (kernel copy is bypassed while
  limited) and `resume_partial_files` without `source-and-destination-hash` (a crash-torn
  resume may go undetected). The same advisories are logged once at service start.
- **Manifest ↔ durable-record metadata parity.** Every accepted job now records the **same**
  creation timestamp and integrity policy (mode + hash algorithm) in both the SQLite job
  record and the JSON manifest, so the two never disagree (L2-JOB-007 / L3-JOB-003). The
  `jobs` table gains `hash_algorithm` and `integrity_mode` columns and the manifest gains
  `created_at` and an `integrity: {mode, algorithm}` block, stamped once at submission and
  threaded to both writers. **Schema note:** fresh-schema change (pre-1.0) — new databases
  only; there is no migration for an existing `jobs.db`.
- **Gated, context-aware logging with near-zero overhead when off.** Job/file correlation is
  carried in structured fields (`extra={job_id, file_id}`) via stable `file_mover.<area>`
  loggers and a `ContextFormatter`, and lifecycle DEBUG/INFO events were added across the
  transfer, state, submission, recovery, and control paths (previously the transfer path
  logged nothing). A per-level `LogGate` computed once at startup lets a disabled level cost
  a single boolean — no `isEnabledFor`, argument evaluation, formatting, or dispatch. Hot
  paths guard DEBUG with `if __debug__ and GATE.debug:`, which `python -O` strips from the
  bytecode entirely; `[logging] level = OFF` disables all logging. The systemd unit runs the
  service under `-O` (L3-PY-014).

### Changed

- **Twelve-factor logging.** The service now writes its event stream to the standard streams
  and lets the environment (systemd's journal, a log shipper) route it — `INFO`/`DEBUG` to
  **stdout**, `WARNING` and above to **stderr** — and no longer manages log files. The
  `[logging] level` is now applied at service start (previously the section was validated but
  ignored), with an explicit CLI `-v`/`--log-level` taking precedence. The CLI is unchanged
  (stdout = command result, stderr = diagnostics) (L3-PY-013).
- **`__version__` is derived from the package metadata, not hard-coded.**
  `file_mover.__version__` now reads `importlib.metadata.version("background-file-mover")`
  (standard library), so `pyproject.toml` is the **single source of truth** for the version —
  the CLI `--version`, the `health` response, and the package all follow it. An uninstalled
  source tree falls back to `0.0.0+unknown`.

### Removed

- **`[logging]` destination options `log_to_journal`, `log_to_file`, and `log_directory`.**
  In the twelve-factor model the application does not choose log destinations, so these were
  removed; `[logging]` now exposes only `level` (with `OFF`). **Migration:** delete those
  keys from your INI (strict validation now rejects them), and route/rotate logs at the
  environment level (journald, or redirect the service's stdout/stderr).

### Fixed

- **Pausing an in-flight copy with `resume_partial_files = false` no longer fails on resume.**
  The kept partial would previously collide with the exclusive create when the job resumed;
  now a pause under a disabled resume policy drops the partial so the file cleanly restarts
  from byte zero (mirroring startup recovery). With resume enabled the partial is kept and
  continued as before (L2-RSM-002).

### Documentation & internals

- Added **`docs/LOGGING.md`** (the stdout/stderr + logging architecture, for operators *and*
  developers) and **`docs/12-FACTOR.md`** (twelve-factor alignment and deliberate
  deviations); documented `doctor`'s environment checks and exit code 8 in CLI-REFERENCE and
  DEPLOYMENT, and added "add an environment check" / "add a log call" workflows to
  MAINTAINER-GUIDE. Added **`docs/FEATURE-INTERACTIONS.md`** (combining kernel copy, bandwidth
  limiting, partial resume, and pause/cancel/resume) plus a matching matrix in ARCHITECTURE.
- **Retired `docs/CAPTURE.md` into the specifications.** The original design conversation
  (~6,200 lines) was fully retired section by section — each removed only after its every
  claim was verified to live in a canonical doc, a requirement, a config option, or
  code+tests. CAPTURE is now a **design-history index** (a retirement ledger mapping each
  section to its home and the commit that removed it; git history retains the content).
  Unbuilt-but-valuable ideas surfaced during the review were migrated to `docs/ROADMAP.md`
  (spool-queue transport, streaming hash-while-copy, manifest per-file hashes, `version`
  collision policy, proactive free-space check, durable event/audit log, file-size and regex
  submission policies, per-job overrides, per-phase timings).
- **Requirements traceability audit.** Reconciled the trace matrix with the code — markers on
  existing data-safety tests plus focused new tests (filesystem identity, cross-filesystem
  claim rejection, inventory rules, temp/directory `fsync`, `O_NOFOLLOW`, config errors).
  `Draft` requirements dropped from **48 to 8**; every remaining `Draft` now means *genuinely
  unbuilt*, documented in `docs/ROADMAP.md` § Known gaps (claim-directory cleanup
  `L2-CLN-003/004`, manual-retry handler `L2-RTY-006`, event publisher `L2-EVT-*`) for an
  implement-or-withdraw decision.

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
  `transfer/partials.py` — reducing class/function complexity with no behavior change.

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

- Validate and normalize the operator-supplied configuration path before it is read:
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

[Unreleased]: https://github.com/joey-huckabee/background-file-mover/compare/v0.4.2...HEAD
[0.4.2]: https://github.com/joey-huckabee/background-file-mover/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/joey-huckabee/background-file-mover/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/joey-huckabee/background-file-mover/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/joey-huckabee/background-file-mover/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/joey-huckabee/background-file-mover/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/joey-huckabee/background-file-mover/releases/tag/v0.1.0
