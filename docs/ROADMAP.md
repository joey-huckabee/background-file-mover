# Roadmap

Forward-looking milestone plan for the Background File Mover. Each milestone is a
vertical, CI-green, fully-pytested slice that advances the requirements in
`docs/L1-REQ.md` / `L2-REQ.md` / `L3-REQ.md`. Completed work lives in `CHANGELOG.md`
and the trace matrix (`docs/TRACE-MATRIX.md`), not here.

The ordering follows the "Recommended Initial Build Order" agreed in `docs/CAPTURE.md`:
build the durable control and state plane first, then submission and claiming, then the
actual bytes-moving transfer engine, then recovery and packaging.

## Locked decisions ("do not drop")

These were settled during design (`docs/CAPTURE.md`) and at project kickoff. Keep them
across all future work:

- **Standard-library-only runtime.** The production package imports only the Python 3.10
  standard library (L1-SYS-009). Dev/CI tooling is dev-group-only.
- **Conservative deletion.** A source file is deleted only after the destination is
  written, fsynced, published, and verified per the configured integrity policy
  (L1-SYS-003). A failure always *retains* the claimed source.
- **Hybrid naming.** Operator-facing name is generic (`file-mover`, `/etc/file-mover`);
  on-disk staging markers are SWIT-prefixed (`.swit-moving`, `.swit-partial-`) so
  in-flight artifacts are unmistakably ours on shared NFS.
- **Unix-socket control plane.** The CLI is a thin client; the service is the durable
  worker and a small local command server over an `AF_UNIX` socket with length-prefixed
  JSON. Submission is idempotent by `request_id`.
- **SQLite is the durable queue.** Authoritative job/file state lives in SQLite (WAL,
  `synchronous=FULL`); recovery decisions are made from observable filesystem state plus
  durable records, never from assumptions.
- **Poetry, root `src/` layout, full quality battery** (ruff, mypy --strict, pytest +
  coverage, pylint, vulture, bandit, CodeQL, SonarCloud, trace-matrix `--check`).

## Milestones

**Status:** M1–M8 are delivered — the product is feature-complete for the first release
(systemd service, submit/claim, durable state, integrity, retry, crash recovery, and the
no-panic fuzz harness). Per-milestone detail lives in `CHANGELOG.md`; the roadmap now
tracks the post-1.0 deferred items below. The milestone descriptions are retained here
for reference.

### M1 — Foundation & Requirements Baseline ✅

Strip the inherited template scaffolding; establish the Poetry/`src` skeleton, the
reference configuration, and the CLI parser surface; author the L1/L2/L3 requirement
docs and the architecture/CLI/config/maintainer references; adapt CI and the
trace-matrix generator to Python-only. Ships declarative code (constants, exception
hierarchy, enums) and a runnable `file-mover --help`; no transfer behavior yet.

### M2 — Configuration Subsystem

`OptionSpec`-driven section schemas; `ConfigurationLoader` (parse → reject-unknown →
convert → validate ranges/cross-field) returning a frozen `ApplicationConfig`;
`ConfigurationValidationError` that collects all issues; `file-mover config validate`
and a partial `doctor`.
Requirements: L2-CFG-001..011, L2-ARC-001..006, L3-PY-001.

### M3 — Control Plane (first executable milestone)

Length-prefixed JSON protocol framing; `ControlSocketServer` + client + stale-socket
recovery; `CommandDispatcher` (static command→handler map); singleton process lock;
`health` command; `service run` skeleton (no transfers). **Done-when:** systemd starts
the service, the CLI reaches it over the socket, `health` succeeds, the service stops
cleanly, and a stale socket is recovered safely.
Requirements: L2-EVT-001..005, L3-EVT-001..005, L3-PY-006, L2-CLI-005/006/010/011.

### M4 — Durable Job State

`SQLiteJobRepository` (schema, WAL/`synchronous=FULL`/`busy_timeout`, per-thread
connections, migrations); `JobRecord`/`FileRecord` dataclasses and the state-machine
transition map; `JobQueryService`; `status`, `list`, `stats`.
Requirements: L1-SYS-007, L2-RTY-003, L3-PY-007.

### M5 — Submission & Claiming

`SourceValidator` (stability polling, symlink rejection, path policy, dev+inode
identity); `FileClaimManager` (same-device atomic rename into `.swit-moving/<job>/`);
`ManifestWriter` (atomic temp+replace); `JobSubmissionService`; idempotent `submit`.
Requirements: L1-SYS-004, L2-FS-001..005, L2-POSIX-001..006, L2-CLI-008/009,
L2-DST-005, L3-INT-003/004, L3-PY-005.

### M6 — Transfer Engine

`BufferedFileCopyEngine` (`.swit-partial-` temp write, bounded buffer, flush+`os.fsync`);
`IntegrityVerifier` (metadata / source-hash / source-and-destination-hash via `hashlib`,
`hmac.compare_digest`); `TransferCoordinator` + bounded worker pool; atomic publish +
directory fsync; source cleanup; `ErrorClassifier` + durable classified retry with
backoff.
Requirements: L1-SYS-001/003/006, L2-DPR-001..007, L2-COPY-001..010,
L2-POSIX-007..012, L2-DST-001..004, L2-DEL-001..004, L2-RTY-001..006,
L3-INT-001..007, L3-PY-002/003/004.

### M7 — Recovery & Service Integration

`RecoveryManager` (reconcile DB vs filesystem across all non-terminal states); the full
`BackgroundMoverService` main loop (transfer scheduler + control server + signal-driven
graceful shutdown); retry that survives restart.
Requirements: L1-SYS-005, L2-CLN-001..005, L2-RTY-004, L2-COPY-010.

### M8 — Packaging & Qualification

Production systemd unit (`Type=simple`) + `mover` service account + deployment guide;
fault-injection tests at every destructive boundary; NFS-qualification checklist; a
Python no-panic/fuzz harness (revives the `fuzz` CI workflow); complete trace-matrix
coverage.
Requirements: L1-SYS-002, L2-STO-001..005, plus test-completeness across all categories.

## Deferred (post-1.0, explicitly out of the first release)

- S3 / object-storage adapter — a separate optional package (`file-mover-s3`); the core
  stays dependency-free (L2-STO-003/005).
- `json-lines` streaming output and an offline `database inspect` command.
- Multi-host active/active movers.
- Network / remote API — a networked control surface beyond the local `AF_UNIX` socket
  (e.g. submitting and monitoring jobs across hosts).
- Web dashboard — a browser UI for job status and operational visibility.
- Metrics server — an exported metrics endpoint (e.g. Prometheus-style) for throughput,
  queue depth, and retry counters.
- Advanced scheduling and transfer prioritization — job priorities and scheduling policy
  beyond the current single-active-job, FIFO model.
- `version` existing-destination collision policy — a third `ExistingDestinationPolicy`
  alongside `fail` and `verify-and-reuse`: on a *differing* destination collision, publish
  the new recording under a versioned name (keeping the existing file) instead of routing
  the job to `MANUAL_INTERVENTION`. Considered in the original design but not built.
  (`overwrite` remains deliberately excluded — recorded simulation data must never be
  silently replaced.)
- Streaming hash-while-copy integrity mode — hash the source **during** the copy loop
  instead of in a separate pre-copy read, so a ~100 GB dataset is read once, not twice
  (roughly halving source I/O for `source-hash` / `source-and-destination-hash` jobs). It
  was deferred in the first design because it cannot persist the *completed* source hash
  before the transfer begins; under `source-and-destination-hash` that is moot since the
  destination is re-hashed and compared regardless. Would add a fourth `[integrity] mode`
  value alongside the current `metadata` / `source-hash` / `source-and-destination-hash`.
- Manifest per-file hashes for standalone downstream verification — record each file's
  source (and destination) hash in the JSON manifest, not only in the SQLite `FileRecord`,
  so a downstream consumer can verify a published recording without the mover's database.
  Requires rewriting the manifest after the `HASHING_SOURCE` step (the manifest is written
  at submission, before the hashes exist). Job `created_at` and integrity policy already
  live in both the record and the manifest (L2-JOB-007); this extends that parity to hashes.
- Filesystem spool-queue control transport — an alternative to the `AF_UNIX` control
  socket in which `submit` writes a JSON job manifest into a spool directory
  (`queue/` → `processing/` → `completed/` / `failed/`) that the service polls, instead of a
  socket request/response. It was weighed during design as the simpler first-version option
  and deferred in favour of the socket (faster acknowledgement, clearer request/response).
  Its future value is **portability**: it needs no `AF_UNIX`, so it is the most likely path
  to **Windows support** (where `doctor` currently reports `ENVIRONMENT_UNSUPPORTED`). Would
  reuse the existing SQLite durable state and JSON manifests unchanged.
- **Logging enhancements (post-12-factor-logging):**
  - **systemd journal priority prefixes** — emit the sd-daemon `<N>` level prefix on the
    service's stdout stream so journald records the correct priority per record.
  - **JSON log-format mode** (`[logging] format = text | json`) — one JSON object per line,
    leveraging the structured `extra={job_id, file_id}` fields, for log shippers.

## Delivered post-1.0

- **Dynamic bandwidth limiting** (v0.2.0) — a userspace token-bucket throughput ceiling
  (`[transfer] max_bytes_per_second`), adjustable live with `file-mover throttle`
  (L2-BWL-001..004, L3-PY-011). See `docs/ARCHITECTURE.md` § *Bandwidth limiting*.
- **Job lifecycle control** (v0.3.0) — `cancel` / `pause` / `resume` commands with
  cooperative cancellation of in-flight copies; cancel always retains the source
  (L2-LIF-001..005). See `docs/ARCHITECTURE.md` § *Lifecycle control*.
- **Partial-file byte-offset resume** (v0.3.0) — resume an interrupted copy from its
  fsynced partial (`[transfer] resume_partial_files`) instead of restarting from zero,
  with a hash-verified restart fallback (L2-RSM-001..003, L3-PY-012). See
  `docs/ARCHITECTURE.md` § *Partial-file resume*.
