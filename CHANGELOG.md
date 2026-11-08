# Changelog

All notable changes to Background File Mover are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- Record approved group-51 retry/deletion defaults (API-E133-138/SC-184-189),
  preserving uncleared exact replay and full forgetting at clear. Contract only;
  remaining candidate wire, runtime implementation and qualification stay open.

- Add a versioned offline Rust prototype installation bundle, gated executable
  provenance, locked dependency source/license material, integrity/dependency
  verification, non-overwriting installation and produce/use/recovery instructions.
  Service activation remains explicit; shipping deployment qualification stays open.

- Add strict `--offline` Cargo-libc/SLES validation using cached pinned images
  and locked sources, with no image/download fallback or online provisioner;
  retain full build/test/audit coverage and record observed container networks.

- Consolidate Rust restart/shutdown recovery into a user runbook, covering
  normal and interrupted transfers, systemd timeouts, surviving workers, startup
  refusals, upgrades/reboots, exact handling steps and qualification limits.

- Implement guarded host-local `--clear-history CONFIG JOB_ID... [--confirm]`
  for committed jobs: one transaction forgets every per-job record/replay link
  without touching source/destination payloads or manifests. Refuse active
  daemon/surviving workers and fresh/legacy state; preserve shared enrollment
  and non-reused IDs. Cancellation/admin HTTP integration remains pending.
  See increment 107 for actual validation and limits.

- Approve full file-linkage forgetting on eligible job clear (group 50/
  API-E130-132/SC-181-183), superseding earlier post-clear owner retention.
  Leave files in place but remove mover ownership/accounting/inventories and
  action results. Delete through the mover before clear; later cleanup is
  outside the service. Require every file effect safely stopped before clear.
  Contract only; no runtime/state or physical-file changes performed.

- Consolidate remaining admin-action behavior into a short closeout table:
  distinguish existing approvals from proposed retry/no-work, post-clear receipt
  and latest-deletion-result defaults. Reduce further encoding-only planning;
  no new approval group, runtime implementation or qualification is claimed.

- Specify the candidate Mover-Retry-Context header with canonical encoding,
  ordered lossless job-ID binding, existing-instance precondition and unchanged
  8 KiB aggregate head bound. Add four wire known answers, 52 codec cases and a
  reproducible standard-library checker; extend schema fixtures to 57 and the
  partial OpenAPI to admin retry. Encoding/artifact checks only; outcome/receipt
  policy and API freeze remain pending, with no Rust/service effects.

- Approve existing review-version/audit context in a retry request header
  (group 49/API-E129/SC-180), preserving the job_ids-only body and exact-command
  replay so a delayed request cannot retry a later failure. No new job identifier
  or confirmation dialog. Exact wire/receipt design and implementation pending.

- Add executable P01 contract candidates: partial OpenAPI, 21 JSON Schema
  definitions, 50 structural fixtures, seven immutable-request identity vectors
  and an index of all 128 API cases. Document the reviewed-state retry-context
  recommendation and remaining freeze blockers. Artifact checks only; groups
  1-48, runtime behavior and all release gates retain their existing status.

- Add a consolidated P01 REST route/schema review proposal and four remaining
  decision packages. Preserve groups 1-48 and existing evidence; no runtime
  implementation, OpenAPI freeze or release qualification is claimed.

- Approve dashboard authentication response statuses (group 48/API-E125-128/
  SC-176-179): login 200 with cookie; incorrect credentials 401 with shared
  "Invalid username or password." message; missing/expired session 401 requiring
  sign-in; successful global logout 204 with no body after invalidation. Contract
  documentation only; exact routes/body schemas and implementation pending.

- Approve manual admin sign-out everywhere (group 47/API-E124/SC-175).
  Invalidate every dashboard session across browsers/devices. Clarify that the
  mover service owns transfers independently of dashboard credentials or session
  lifetime; sign-in/out and dashboard credential events do not pause/cancel/restart them.
  Contract documentation only; implementation/qualification and exact wire pending.

- Approve browser session-cookie dashboard sign-in (group 46/API-E123/SC-174).
  Preserve agreed expiry, password-change/restart sign-out and transfer independence.
  Exact cookie/login/logout wire and implementation/qualification remain pending.

- Approve failed-work retry HTTP 202 with accepted_count, failed_count and
  skipped_count for per-entry attempts. Add planned API-E122/SC-173 (group 45);
  preserve actual progress, custody and existing retry/review checks. Contract
  documentation only; remaining wire/login details and implementation pending.

- Replace Rust ZigBuild with pinned cargo-libc 0.2.4 and a digest-pinned Rust
  1.99.0 builder base. Preserve locked dependencies, glibc 2.22, independent
  ELF audits, debug/release SLES tests and retained qualification features.
  Add configuration-stream regression checks and retained CI diagnostics;
  normalize target test sessions to fix the pre-existing CI process-group-zero
  startup failure. Retain the separate Zig C fixture compiler and document
  non-PIE/reproducibility limits. Runtime code and REST decisions are unchanged.

- Capture a portable development handoff with exact pending REST decision,
  release/verification reading map, cloud setup steps and testing limits. Add
  a hash inventory of 205 tracked evidence reports and both retained SLES
  source/artifact baselines. Document that ignored raw packs/caches are not
  transferred by Git; no runtime or new qualification change.

- Approve cancellation HTTP 202 with accepted_count, failed_count and skipped_count for per-entry attempts. Add planned API-E121/SC-172; preserve pending safe-stop status, duplicate failures and silent skips. Documentation only.

- Process duplicate admin job_ids entries again without batch deduplication/state prediction. Per-job cancellation decides the result; a duplicate cancel counts as a failed attempt without failing the job or resetting cancellation. Add planned API-E120/SC-171. Documentation only.

- Approve silently skipping nonexistent job IDs in all four selected admin actions while processing remaining targets. Add planned API-E119/SC-170; preserve retained-data ownership, actual lookup errors and separate single-resource 404 mappings. Documentation only.

- Approve a shared job_ids request for cancel, retry, history clear and manual deletion, each at its own endpoint. Add planned API-E118/SC-169; admin authentication remains separate from action bodies and exact wire/login details are pending. Documentation only.

- Clarify that manual deletion uses the existing job_id and the targeted job's stored state/eligibility; no additional admin identifier scheme is required. Preserve agreed file ownership, confirmation and protection rules. Documentation only.

- Approve manual deletion 202 Accepted with deleted/failed file counts, no automatic retries or special recovery workflow. Add planned API-E117/SC-168 and preserve confirmed scope, ownership/safe-stop and protected-file rules. Documentation only.

- Approve completed history-clear 200 OK with the actual number of jobs cleared, silent ineligible skips and files untouched. Add planned API-E116/SC-167; exact wire/transaction implementation remains pending. Documentation only.

- Approve 202 Accepted for accepted failed-job retry without confirmation; dashboard shows actual progress without implying success. Add planned API-E115/SC-166 and retain original job/custody/review rules. Documentation only.

- Approve admin cancellation HTTP 202 Accepted with Cancellation pending until safe stop, then Cancelled. Add planned API-E114/SC-165; preserve custody/recovery rules and distinguish producer handoff acknowledgement. Documentation only.

- Approve 409 recording_cancelled with retryable false for cancelled producer retries before durable handoff; preserve established 202 replay after handoff. Add planned API-E112/113 and SC-164; no transfer revival or new path release. Documentation only.

- Require no confirmation for eligible failed-work retry. Add planned API-E111/SC-163; retain authentication, original job/custody and existing review checks. Cancel/clear/delete confirmations remain. Documentation only.

- Make cancellation final for the first release, preserving files and keeping eligible failed-work retry separate. Add planned API-E110/SC-162; response mappings and implementation remain pending. Documentation only.

- Approve requesting cancellation only for unfinished selected jobs, skipping completed/already-cancelled jobs without reasons. Add planned API-E109/SC-161; preserve existing pending cancellation and file/history safeguards. Documentation only.

- Require cancellation confirmation displaying selected jobs without explanatory text. Add planned API-E108/SC-160 and preserve file/custody/pending-worker safeguards; terminal/mixed-selection and exact wire behavior remain pending. Documentation only.

- Approve clearing eligible selected history while skipping others without individual reasons or automatic cancellation. Add planned API-E107/SC-159; preserve eligibility/file/UUID rules. Documentation only.

- Require confirmation before history clear, showing selected jobs and explaining forgotten UUIDs with files preserved. Add planned API-E106/SC-158; mixed-selection and exact wire behavior remain pending. Documentation only.

- Approve dashboard sign-out on mover restart while jobs use normal durable recovery. Add planned API-E105/SC-157; session implementation remains pending and runtime/recovery behavior is unchanged.

- Approve configurable dashboard inactivity sign-out, default 30 minutes, without affecting background transfers. Add planned API-E104/SC-156; implementation and session behavior across mover restart remain pending.

- Require password changes to sign out all existing admin dashboard sessions while background transfers continue unaffected. Add planned API-E103/SC-155; activation/session implementation and inactivity timeout remain pending.

- Approve local setup/password changes on the mover host for one admin account. Add planned API-E102/SC-154; remote account-management/reset screens are not required. Session handling and implementation remain pending.

- Select simple admin username/password for the first-release remote dashboard; defer SSO and advanced account management. Add planned API-E101/SC-153, retain action safeguards and leave minimal login/session implementation pending.

- Require admin dashboard access from another computer, separate from recorder access. Add planned API-E100/SC-152 and begin sign-in/authorization design; no authentication method or remote admin listener implemented.

- Approve manual retained-data deletion independently of the automatic-cleanup setting. Add planned API-E99/SC-151; preserve confirmation, safe-stop, file protections and best-effort failure behavior. Documentation only; no production deletion enabled.

- Simplify confirmed retained-data deletion failure handling: best effort, leave failed files and report failures while attempting other safe selected files. No dedicated pause/resume or automatic retry workflow; existing ownership, safe-stop, confirmation and protected-file rules remain. Documentation only.
- Approve confirmed retained-data disposal scope: owned retained source and unfinished destination after safe stop, protecting unclaimed originals and completed output. Add planned SC-149/150 and API-E92-98 for confirmation, ownership, protected data, workers, partial results and UUID reuse. Retry/failure and exact admin access/wire rules remain pending; no physical deletion enabled.

- Approve file preservation on history clear, with separate retained-file ownership/accounting and forgotten UUID recognition. Require a separate explicit admin data-deletion action; add planned SC-147/148 and API-E87-91 for capacity, restart and transition safety. Deletion scope/authorization/recovery and runtime implementation remain pending.

- Approve file-preserving cancellation and document planned SC-146/API-E81-86: keep original/private source, partial staging and published files; reconcile in-flight publication and blocked workers before safe cancellation/clear. Preserve valid manifest/202 and retained capacity. File disposition at history clear remains undecided; no runtime changes.

- Define admin clear as removing detailed history and forgetting its UUID, so later reuse is a new recording. Protect unfinished/errored jobs until cancellation safely completes; only completed or cancelled jobs may clear. Add planned SC-144/145 and API-E76-80 with late-retry, worker and no-clobber cases. Administrative cancellation/data/wire design remains pending; no runtime changes.

- Record manual full detailed-job-history retention until an admin clears it through the dashboard; no automatic expiry or compact-only replacement. Add planned SC-143/API-E75 and scope the requested clear workflow, with post-clear UUID/retry and eligibility still undecided. No runtime/dashboard implementation or qualification changes.

- Approve required UUID recording_id and document planned SC-142/API-E73-74, non-UUID 400 rejection and same-ID retry. Durable uniqueness and precise lexical/schema/state handling remain implementation work; runtime and qualification evidence unchanged. Next review ID retention/concurrency.

- Approve order-independent file-list replay and document planned SC-141/API-E71-72. Preserve original path-to-file/claim mapping and changed-content conflicts; update the handoff to remaining ID syntax/retention/concurrency. No runtime or qualification changes.

- Save the REST contract shutdown handoff with approved groups 1-15, current-size-policy correction, unresolved replay/schema decisions and exact next step. Documentation only; runtime and qualification evidence remain unchanged.

- Define current startup expected-size configuration for existing unfinished recordings, without per-job setting snapshots. Document off-to-on/on-to-off recovery and confirmed-handoff replay in planned SC-140/API-E67-70; preserve actual custody/size/integrity evidence. No runtime or qualification changes.

- Document approved default-disabled expected-size checking: ignore complete supplied expected_sizes_bytes assertions when off; require and compare every listed size when on. Preserve all-or-nothing map validation and actual-size/copy integrity checks. Add planned SC-139 and API-E61-66, including expected 100 versus actual 200 bytes; no runtime or qualification changes.

- Record that the Rust prototype API has no clients: replace its producer wire format directly with the reviewed recording-ID/source-directory/explicit-file form, without a compatibility adapter or deprecation period. Preserve persistent custody and separate legacy stored-state compatibility requirements; exact schema and optional-size representation remain pending. No runtime changes.

- Record approved REST recorder retry timing: honor server delay, then valid Retry-After, then configurable 5/10/20/30-second fallback and five-minute persistent-failure warning. Consolidate API-I01-06 implementation/qualification steps while preserving pending request/schema compatibility. No runtime, retry/review deadline or qualification changes.

- Record REST review groups 10-12: remaining request errors, conservative source-effect refusal, unexpected-server/invalid-success handling and the five-field error envelope. Fifty outcome mappings plus the error format are approved; timing and remaining API schema compatibility details stay open. Runtime and qualification evidence are unchanged.

- Record REST review groups 7-9: remote caller/rate/TLS failures, post-202 delivery/cleanup status, and local operator commands. Nine groups now contain 43 approved outcome mappings; remaining request/response details stay under review. No runtime, registration, NFS enablement or qualification changes.

- Record REST review groups 4-6: custody/permission refusals, temporary database and transport failures, and HTTP request errors. Groups 1-6 now define 29 approved mappings; remaining scenarios/response details stay under review. No runtime or qualification changes.

- Record approval of the first three REST error groups (fourteen mappings), including retryable missing-file 409, validation/source-scope failures and temporary capacity/service errors. Other mappings and wire compatibility remain under review; runtime responses and existing qualification evidence are unchanged.

- Draft sixty REST outcome/error scenarios for user review before implementation. Record current versus proposed codes, same-ID retry and partial-custody behavior, remote/transport/operator distinctions and a bounded implementation sequence. Missing-file 409 and global-ID wire changes remain pending review; no runtime, retry/review, production NFS or source-deletion changes.

- Review all eight Rust release gates against implementation and retained evidence. Establish RC-01-24 acceptance families, P01-12 execution order and explicit profile/capability decisions; next freeze the versioned API/manifest contract. Preserve historical checklist evidence, keep the roadmap forward looking and clarify that default-off source cleanup is required for release. No new runtime behavior or qualification result; production NFS and deletion remain disabled.

- Qualify pre-effect source inode/size refusal after a partial two-file handoff. Preserve existing non-retryable 409, original intent/private custody and no delivery through two unpaused restarts; independently audit sixteen SQLite/WAL snapshots. Document SC-138 and step-by-step testing limits. Both SLES/glibc-2.22 gates pass; production NFS/private-source cleanup remain disabled.

- Qualify two-file partial handoff replay with first claim complete and second LINK/REMOVE pending. Add a qualification-only file-index pause selector; preserve whole-set 202, retry/review behavior and original-state recovery. Document SC-137 and step-by-step testing limits; both SLES/glibc-2.22 gates pass. Production NFS/private-source cleanup remain disabled.

- Qualify one-file source LINK/REMOVE replay and finite queue refusal before HTTP 202; preserve custody, worker ownership and confirmed handoff before producer reuse. Document SC-136, infrastructure and testing limits. Both SLES/glibc-2.22 gates pass; production NFS/private-source cleanup remain disabled.

- Qualify claimed replay, source revalidation and a six-request burst during joint NFS outage with source-space admission off/on. Preserve original custody/recovery and bounded non-release queue refusals; document SC-135, infrastructure and timeout/queued-work limits. Both SLES gates pass; production NFS/private-source cleanup remain disabled.

- Qualify original-file claim sync discovery before LINK/HTTP 202 in four healthy/stopped-NFSD cases, preserving one-link custody and confirmed retry before reuse. Document SC-134, raw RPC limits, infrastructure and retained setup failure. Both SLES/glibc-2.22 gates pass; production NFS/private-source cleanup remain disabled.

- Discover exact source-claim private-file/directory synchronization behavior before HTTP 202 in eight healthy/stopped-NFSD cases; audit raw RPC intervals separately from artificial holds and preserve confirmed retry before recorder reuse. Document SC-133 and step-by-step infrastructure/testing limits. Both SLES/glibc-2.22 gates pass; production NFS/postcommit private-source cleanup remain disabled.

- Qualify source-claim REMOVE coordinator-death recovery before HTTP 202, with original two-name/private custody, pending raw SQLite/WAL receipt proof and confirmed same-ID retry before producer reuse. Retain the initial pre-mount Podman connection failure, SC-132 and step-by-step infrastructure/limits. Both SLES/glibc-2.22 gates pass; production NFS/postcommit private-source cleanup remain disabled.

- Qualify source-claim LINK coordinator-death recovery before HTTP 202, retaining pending local claim evidence, old-worker exclusion and original custody; require confirmed identical-ID retry before producer reuse. Document SC-131, raw proof and step-by-step infrastructure. Both SLES/glibc-2.22 gates pass; production NFS/private-source cleanup remain disabled.

- Qualify selected manifest-LINK coordinator-death recovery across controlled NFS restart, retaining original custody and old-worker exclusion; preserve and independently audit local SQLite/WAL phase evidence. Document SC-130 and the step-by-step lab. Both SLES/glibc-2.22 gates pass; production NFS/source deletion remain disabled.

- Qualify selected payload-LINK coordinator-death recovery across controlled NFS server restart, retaining old-worker exclusion and original-state custody; document SC-129, step-by-step fixture procedure and testing limitations. Both GNU/glibc-2.22 SLES gates pass; production NFS/source deletion remain disabled.

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
