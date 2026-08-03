# Roadmap

Forward-looking milestone plan for the Background File Mover. Each milestone is a
vertical, CI-green, fully-pytested slice that advances the requirements in
`docs/L1-REQ.md` / `L2-REQ.md` / `L3-REQ.md`. Completed work lives in `CHANGELOG.md`
and the trace matrix (`docs/TRACE-MATRIX.md`), not here.

The ordering follows the "Recommended Initial Build Order" agreed during design:
build the durable control and state plane first, then submission and claiming, then the
actual bytes-moving transfer engine, then recovery and packaging.

## Locked decisions ("do not drop")

These were settled during design and at project kickoff. Keep them
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
- Per-job submission policy overrides — optional `submit` flags (`--integrity-mode`,
  `--hash-algorithm`, `--stability-check`/`--stability-polls`/`--stability-poll-interval`)
  that tune policy for a single job, each **constrained by system policy** so a submitter can
  never weaken a required setting (e.g. cannot disable hashing when the service mandates it).
  The resolved values are stored in the job record so recovery reuses them.
- Persisted per-phase job timings — record `perf_counter` durations for submission, source
  hashing, copy, verification, and recovery on each completed job and surface them via
  `status`/`stats`, giving operators visibility into where time goes on a ~100 GB transfer.
- File-size submission policies — optional `[validation]`/`[stability]` limits that reject a
  job **before claiming** when a file is empty (`allow_empty_files = false`) or exceeds a
  per-file / per-job size ceiling (`maximum_file_size_bytes`, `maximum_job_size_bytes`,
  `0` = no limit). Guards against a failed recorder (zero-byte file) or an over-size set.
- Regex / filename-filter submission — optional `filename_filter_regex` for directory
  submissions: compiled and validated at startup, anchored against relative paths, recorded
  in the job, and applied **before** claiming. Deferred in the original design (an explicit
  file list or job-specific directory is the safer primary path); add only if orchestration
  needs it.
- Durable job event / audit log — persist every job/file state transition as a typed event
  to a durable events table (and expose a human-readable per-job timeline), giving operators
  an auditable history beyond the current job/file state snapshot. The first design
  downgraded this to "optional observers, never authoritative" (the jobs/files tables are the
  source of truth), so it remains an unbuilt enhancement.
- Proactive free-space margin pre-flight check — before starting a transfer, verify the
  destination filesystem has at least the job's total size plus a configurable margin
  (`statvfs`), and reject or hold the job otherwise, instead of only handling `ENOSPC`
  reactively (source retained) after copying part of a ~100 GB set. Proposed in the
  original design (`minimum_free_space_margin_bytes`) but not built.
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

## Known gaps (decision needed)

A **traceability audit** (v0.4.0) reconciled the trace matrix with the code: every
implemented requirement now carries a `@pytest.mark.requirement` test marker (or a declared
Inspection method), so a `Draft` status in the matrix now means *genuinely unbuilt*, not
merely untested. The claim/filesystem and transfer/deletion data-safety requirements
(`L2-FS-*`, `L2-POSIX-*`, `L2-CLN-001/005`, `L2-COPY-*`, `L2-DST-*`, `L2-DEL-*`) are now
tested. The requirements still `Draft` are unimplemented features specified during design —
each needs an **implement-or-withdraw** decision:

- **Claim-directory cleanup — `L2-CLN-003` / `L2-CLN-004`.** There is no staging-directory
  cleanup step: after a job's claimed sources are deleted, the emptied `.swit-moving/<job>/`
  directory is left in place, and unexpected leftover files are neither surfaced nor routed
  to manual intervention. Implement a deepest-first cleanup that removes the emptied claim
  directory and routes a non-empty one (unexpected files) to `MANUAL_INTERVENTION`, or
  withdraw the requirements.
- **Manual retry — `L2-RTY-006`.** The `retry` CLI subcommand exists in the parser but has
  **no server-side handler** (registered control commands are health/status/list/stats/
  submit/throttle/pause/resume/cancel), so sending `retry` returns `UNKNOWN_COMMAND`. Wire a
  `retry` handler that transitions an eligible retained job back to `QUEUED`, or withdraw it.
- **Event publisher — `L2-EVT-001..005` / `L3-EVT-001..005`.** The in-memory observer /
  event-publisher (snapshot subscribers before dispatch, don't hold the lock during
  callbacks, isolate subscriber failures, reject duplicate registration, unsubscribe reports
  removal) has no implementation and no tests. Its observational-not-transactional *principle*
  is already honoured by the coordinator (it updates SQLite directly); decide whether to build
  the publisher (together with the durable event/audit log above) or withdraw the requirements.

The storage-capability abstraction (`TransferSource`/`TransferDestination` Protocols behind
`L2-STO-001/003`) is likewise unbuilt — the workflow uses POSIX directly — but is tracked as
part of the deferred **S3 adapter** rather than a standalone gap.

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

---

# v1.0.0 — C++ / REST implementation

Tracked on the `v2-cpp` branch. The milestone list above (M1–M8) belongs to the
**Python** implementation and is delivered; it is retained for history. The
inherited external design used its own M1–M12 numbering, which is deliberately
not carried into this repository.

> **The "Locked decisions" section above is stale on this branch.** It asserts
> a standard-library-only Python runtime and an `AF_UNIX` control plane, both
> superseded — see ADR-0001 (C++11) and ADR-0002 (REST). It is left unedited
> because it accurately records what was locked for v0.4.2. A superseded-at-
> v1.0.0 pass is itself a roadmap item below.

## Delivered

| Component | Requirements | Notes |
|---|---|---|
| Core job state machine | `L3-CPP-001..015`, `L3-CPP-041` | Pure logic, clock-free, exhaustive transition table |
| Strict JSON parser | `L3-CPP-016..024` | Project-owned (ADR-0006), fuzzed, hostile-input tested |
| REST API codec | `L3-CPP-025..032` | Strict-reject; parser confined behind it |
| Configuration loader | `L3-CPP-033..040` | Strict schema, all-errors reporting, `[storage]` section |
| CI pipeline | — | Six tiers, toolchains pinned by explicit version |

## Security and file-management architecture

`docs/CYBERSECURITY.md` is the reference. It states a threat model in which
endpoint security, MAC, audit agents, and other NFS clients all touch the same
filesystem, and two assumptions are rejected: that a check stays true, and that
privileged interference is impossible.

**Two scoping constraints for v1.0.0**, taken to remove attack surface:

* **Same filesystem only** (`L1-SEC-007`) — no staging directory, no recursive
  copy, no bottom-up fsync ordering. Every move is one atomic operation.
* **Files only** (`L1-SEC-007`) — no recursive walk, and it avoids depending on
  an atomic no-clobber directory move, which **does not exist over NFS**
  (`linkat` does not work on directories and NFS has no `RENAME_NOREPLACE`).

### Outstanding work, in dependency order

| # | Item | Requirements | Blocked on |
|---|---|---|---|
| 1 | **SQLite durable store** — phase model `intent → committed → source-deleted → complete`, source identity at intent | ADR-0010, `L1-SEC-003`, `L2-JOB-001..012` | Vendor the amalgamation |
| 2 | **fd-relative filesystem layer** — `openat`/`renameat2`/`fstatat`/`unlinkat`, identity re-verification after open | `L2-SEC-001..004` | 1 |
| 3 | **`renameat2` capability detection** + `linkat`/`unlinkat` fallback as a primary tested path | `L2-SEC-007`, `L2-NFS-001..003` | 2 |
| 4 | **Preconditions and path validation** — trusted UID, sticky-bit check, canonicalization | `L2-SEC-005`, `L2-SEC-006` | 2 |
| 5 | **Rename operation** on the fd-relative layer, consuming the delivered template engine | `L1-SYS-013`, `L2-REN-001..003` | 2, 3 |
| 6 | **External-interference tolerance** — per-syscall timeouts, forward progress, failed-external state | `L1-SEC-004`, `L2-SEC-009..011`, `L2-NFS-004..005` | 1, 2 |
| 7 | **Transfer strategies** — local rename, `fork`/`execvp` exec strategy; two-hop delivery | `L1-SYS-015`, `L2-XFR-001..004`, `L2-NFS-007` | 5 |
| 8 | **Worker pool and REST server** | `L2-MGR-001..003`, `L2-CTL-001..016` | 1, 7 |
| 9 | **Crash and fault injection suite** | `L1-SEC-002` | 1–8 |
| 10 | **MAC policy + enforcing-mode CI** — SELinux module (RHEL), AppArmor profile (SLES) | `L1-SEC-005`, `L2-SEC-013` | 8 |
| 11 | **Hardened systemd unit** | `L2-SEC-014` | 8 |
| 12 | **ePO exclusion documentation + startup coverage check** | `L2-SEC-016` | 8 |
| 13 | **NFS qualification on a real export** | `L2-NFS-006`, `L2-NFS-008` | 8 |

### Testing obligations that cannot be deferred

The guarantees live in crash-window behavior, which ordinary tests never
reach. Recovery logic that only runs during disasters is the worst possible
place for untested code.

- [ ] `SIGKILL` between each phase transition, verifying recovery on restart
- [ ] Entry swapped mid-operation (identity mismatch)
- [ ] File removed mid-operation (quarantine simulation)
- [ ] `EEXIST` at commit
- [ ] Both paths missing at recovery → failed-external, no retry
- [ ] Injected `open()` latency → timeout, sibling moves unaffected
- [ ] Full suite under SELinux enforcing / AppArmor enforcing, zero denials
- [ ] `linkat`/`unlinkat` fallback exercised as the primary path, not an edge case

## M7 disposition (transfer adapters)

The inherited M7 delivered three transfer strategies. One is deferred, one is
removed, and the third is superseded by work already scheduled.

| Delivered | Outcome |
|---|---|
| `LocalRenameTransfer` | **Superseded** by roadmap items 2–3. Path-based `link`/`unlink`/`lstat` is the check-then-act pattern `L2-SEC-001` prohibits, and `link`+`unlink` is the NFS *fallback* rather than the primary (`L2-SEC-007`). Same finding as M6's rename operation, same cause. |
| `CopyFsyncRenameTransfer` | **Deferred → v1.1** with cross-filesystem support (`L1-SEC-007`). Its `.part` → `fsync` → atomic-placement pattern independently confirms the two-hop reasoning in `L2-NFS-007`. |
| `ExecTransfer` | **Removed** — ADR-0011. |
| `[transfer]` config growth | **Deferred** with the strategies it configures. |
| Progress callback, validating factory | Retained as interface concepts for the rewrite. |

Nothing from M7 was adopted as code. The subprocess discipline it demonstrated
is retained as `L2-SEC-008`, and its temp-file placement pattern informs
`L2-NFS-007`; both were already specified before the drop arrived.

### On external commands, should the question return

ADR-0011 removes the strategy, not the topic. A genuine future need for a
destination the daemon cannot reach as a filesystem path — another host over
SSH, an object store — is a design conversation with its own threat analysis,
not a configuration key. Two constraints any such design has to satisfy:

* Configuration must remain data. Whatever expresses "send it there" cannot be
  a free-text command, or whoever writes the config gets code execution as the
  service account.
* The commit point must stay ours, or the guarantee has to be explicitly and
  visibly weaker for that destination — not silently weaker for everyone.

## M8 disposition (job manager)

The inherited M8 delivered a threaded JobManager. Its code depends on
`journal.hpp`, `rename.hpp`, and `transfer.hpp` -- all superseded or rejected --
so none of it ports. Its *disciplines* are the most valuable thing any drop has
produced.

| Delivered | Outcome |
|---|---|
| Write-ahead ordering -- intent durable **before** the job exists | **Adopted as `L2-JOB-013`.** Exactly the commit-point ordering whose absence in M6 meant a crash between rename and record loses the file. |
| Phase-blind non-fatal write failures (`L3-CPP-075`) | **Rejected**, replaced by `L2-JOB-014`. A write failure is two conditions wanting opposite handling; treating both as a counter lets the durable record drift from the filesystem. |
| Job sequence feeding `{seq}` | **Adopted as `L2-JOB-015`**, with the gap closed: the sequence must be durable and monotonic across restarts, which the inherited design left unspecified. |
| ThreadSanitizer gate | **Adopted as `L2-ARC-008`**, wired into CI and `make check-ci` before the first thread exists. |
| Latch-based deterministic concurrency tests | **Adopted as practice** -- see CONTRIBUTING. Proving all N workers are simultaneously inside the call beats sleeping and hoping. |
| Injected clock (`std::function<int64_t()>`) | **Adopted as practice.** Consistent with the clock-free core, and it makes ordering exactly checkable rather than probabilistically. |
| Queue / worker / drain semantics | Already specified as `L2-MGR-001..003`; the implementation confirms the shape. |
| `JobManager` code, journal wiring, pipeline | **Not ported.** |

## M11/M12 disposition (dashboard and daemon entry point) — CLOSED

The final drop, and the end of the inherited design series. No code adopted;
four requirements and one compliance fix. Full triage in
`docs/MIGRATION-PROVENANCE.md`.

| Delivered | Outcome |
|---|---|
| `LICENSES/` for vendored dependencies | **Adopted** — and it found a real gap. `catch.hpp` references an "accompanying file `LICENSE_1_0.txt`" that did not exist here. Now vendored, hash-pinned, gated by `make verify-vendored`. |
| `textContent`-only DOM insertion | **Adopted** as `L2-DASH-003`. |
| Signal handler sets only `volatile sig_atomic_t`; `SIGPIPE` ignored | **Adopted** as `L2-CTL-017`, `L2-CTL-018`. |
| `--check` config validation, run as systemd `ExecStartPre` | **Adopted** as `L2-CTL-019`. |
| Ordered startup, reverse-order teardown | **Adopted** as `L2-CTL-020`. |
| `src/main.cpp` | **Not ported** — composes the journal (rejected, ADR-0010), the manager and HTTP server (deferred), and a transfer strategy (`ExecTransfer` removed, ADR-0011). Its 200 ms `nanosleep` wait loop is explicitly **not** the pattern to copy; block on `sigsuspend` or a self-pipe. |
| `deploy/filemover.service` | **Superseded** by `L2-SEC-014`, which is stronger (`ProtectSystem=strict`, `ReadWritePaths=`, `CapabilityBoundingSet=`, `UMask=0077`). |
| `dashboard.cpp` | **Deferred** with the dashboard; `L2-DASH-001..003` hold the obligations. |

**The inherited-design series is now closed.** `transcripts/` is deleted. Eight
snapshots produced one adopted component, two adopted helpers, and ~20
requirements; everything else was superseded, deferred, or rejected. If another
design conversation arrives, recreate `transcripts/` as scratch and follow the
same rubric.

## M9/M10 disposition (HTTP layer and recovery) — CLOSED

The first drop containing code worth adopting beyond a pure helper. ADR-0012
committed the project to a hand-rolled HTTP/1.1 subset, so unlike the previous
four milestones this one builds something we actually need.

**Status: the parser is landed.** `cpp/src/http_parser.cpp`, `L3-CPP-046..052`,
with the three fixes below applied, a second libFuzzer target
(`cpp/fuzz/fuzz_http.cpp`, 37 seeds), and the first component built to
`docs/HAND-ROLLED-COMPONENTS.md`. The routes and server remain deferred with
the job manager; the recovery design remains rejected. What stays open from
this milestone is tracked in **M7** below, not here.

| Delivered | Outcome |
|---|---|
| `parse_request_head`, `content_length_for`, `serialize_response` | **Adopted** — `L3-CPP-046..052`, with the fixes below. Pure functions, strict posture, and the untrusted-input surface ADR-0008 requires fuzzing. |
| `http_routes.cpp` | **Defer.** Depends on the job manager, which does not exist. |
| `http_server.cpp` | **Defer.** Socket loop needs config and manager; also needs review against `L2-SEC-009` (per-syscall timeouts) and `L2-SEC-010` (one stalled connection must not block others — the server is serial-accept). |
| `manager.cpp` recovery | **Reject as written.** Journal-based (ADR-0010 chose SQLite), and its non-fatal write-failure handling contradicts `L2-JOB-014`. |
| Test suite (493 lines) | **Adapted** — the parser's share landed as `cpp/tests/test_http_parser.cpp`, keeping the prefix sweep. The hostile battery is an integration test against a socket, so it is deferred with the server. |

### Fixes applied before adopting the parser

1. **Split the header.** `http.hpp` is monolithic: the pure parser, the route
   handlers, and the socket server share one header that includes
   `config.hpp` and `manager.hpp`. The parser needs neither. Split into
   `http_parser.hpp` (pure, std-only), with routes and server following when
   the manager exists. Same layering fault as M7 putting the journal codec in
   `api_codec.hpp`.

2. **Remove locale dependence.** `valid_header_name` uses `std::isalnum` and
   `lower()` uses `std::tolower`, both **locale-sensitive**. A parser on
   untrusted input must not change behavior because something in the process
   called `setlocale`. Replace with explicit range checks — the same reasoning
   that made the JSON parser use explicit tables.

3. **Renumber** `L3-CPP-079..092` into this repository's sequence — landed as
   `L3-CPP-046..052`.

A fourth change was made that the review had not anticipated: `content_length_for`
used `strtoull`, which accepts leading whitespace and a `+`/`-` sign and reports
overflow through `errno`. Replaced with explicit digit accumulation and an
overflow guard, so the strict-digit rule is enforced by the code rather than by
checking the string first and trusting the conversion afterwards.

### What the parser gets right, and is worth preserving

* **Duplicate headers rejected outright** — added mid-build after noticing a
  map's last-wins overwrite is a request-smuggling vector. Correct, and the
  same class of reasoning that made duplicate JSON keys an error (ADR-0009).
* **Any `Transfer-Encoding` is a 400.** No chunked parsing exists to desync.
* **Bytes beyond the declared `Content-Length` are a 400** — no pipelining, no
  smuggled second request.
* **`NeedMore` for every proper prefix of a valid head**, swept exhaustively in
  the tests. This is the property that makes a streaming parser safe.
* `out` is left unmodified except on success, matching the codec contract.

## Open questions (decision needed)

| Item | Question | Raised |
|---|---|---|
| **`{seq}` template field** | **Answered.** The sequence is the job sequence, and `L2-JOB-015` now requires it be durable and monotonic across restarts -- the inherited design left durability unspecified, which would have made identifiers repeat after every restart. | M6 review, closed M8 |
| **Collision suffix walk** | The inherited design walks `.1`–`.1000`, each probe a `link()` attempt. On NFS that is up to 1000 round-trips per collision, and with a `{name}`-only template collision is the normal case rather than the exception. The cap is also arbitrary. Re-evaluate once the fd-relative layer exists — it may be better addressed by making collisions rare by construction than by walking. | M6 review |
| **cpp-httplib on GCC 4.8.5** | **Answered — rejected.** No tag is viable: it routes with `std::regex`, unimplemented in libstdc++ before GCC 4.9. Measured in the container — a literal route registers, a parameterised one throws `regex_error`, and the latest tag will not compile at all. HTTP is hand-rolled (ADR-0012), which also closes the last TBD in ADR-0004. | ADR-0004, closed M9/M10 |
| **Authentication** | v1.0.0 ships none; the bind address is the only access control (`L1-API-006`). Needs a decision before any non-loopback deployment. | L1 merge |
| **Trace matrix and Catch2** | The generator reads only pytest markers, so the C++ tree reports 0 tested despite thousands of passing assertions. | Requirements merge |
| **Stale locked decisions** | The section at the top of this file still asserts Python-stdlib-only and a Unix-socket control plane. Needs a superseded-at-v1.0.0 pass. | L1 merge |

## Deferred to v1.1

Retained verbatim in the requirements, marked Deferred, never weakened.

| Capability | Requirements |
|---|---|
| Claiming — relocate source so the next run cannot overwrite | `L1-SYS-004`, and `L1-SYS-002` which depends on it |
| Conservative deletion — no delete until published and verified | `L1-SYS-003` |
| Configurable integrity verification | `L1-SYS-006` |
| Recovery by resumption rather than marking failed | `L1-SYS-005` |
| Cross-filesystem moves — staging, recursive fd-relative copy, commit rename | `L1-SEC-007` constrains v1.0.0; the design is retained in `docs/CYBERSECURITY.md` marked **[v1.1]** |
| Directory moves | As above; needs an answer for NFS, which has no atomic no-clobber directory move |
| Bandwidth limiting, partial-file resume, pause/cancel | Python-implementation features not yet ported |
