# Chat Capture

This is the original design conversation the specifications were transcribed from. As of
v0.4.0 its content is being **incrementally retired**: each section is removed only once
every claim in it is verified to live in a canonical doc, a requirement ID, a config
option, or code+tests. Nothing is lost — removed content is recoverable from git history,
and the **retirement ledger** below records where each retired section now lives.

Sections still present below have **not yet** been verified/retired. Once retirement
completes, this file becomes the design-history index (the ledger) rather than the
authoritative spec source.

## Retirement ledger

| Retired CAPTURE section | Disposition | Canonical home(s) | Commit |
|-------------------------|-------------|-------------------|--------|
| Recommended Initial Build Order | TRANSCRIBED | `docs/ROADMAP.md` — 16-step order → milestones M1–M8 (§ Milestones + ordering note); "first executable milestone" block → M3 **Done-when**; submission-before-transfer → M5→M6 sequence | `2ee3e73` |
| Initial L1 Requirements | TRANSCRIBED | `docs/L1-REQ.md` — all 10 SHALL statements → `L1-SYS-001…010` (semantic match). Mnemonic titles ("Background Data Movement", …) were conversational labels, intentionally not carried; the SHALL text is authoritative | `8905c81` |
| Example L2 Decomposition | TRANSCRIBED | `docs/L2-REQ.md` — `L2-SW-003.1…7` → `L2-DPR-001…007` (verbatim; dotted IDs normalized to the `DPR` category). "Under L1-SYS-003" linkage → each DPR's `**Parent**: L1-SYS-003`. `PUBLISHED_VERIFIED` state name → file state machine in `jobs/models.py` / ARCHITECTURE | `0f5c2df` |
| Example L3 Decomposition | TRANSCRIBED | `docs/L3-REQ.md` — `L3-INT-003.4.1…7` → `L3-INT-001…007` (verbatim/trivial rewording; canonical version refines each parent to its most precise L2). `INTEGRITY_FAILED` state name → `jobs/models.py` state machine | `c874e0c` |
| Testing Strategy | MIGRATED + TRANSCRIBED | Test taxonomy + fault-injection boundary list + guiding principle **migrated** to `docs/MAINTAINER-GUIDE.md` § Testing strategy (previously undocumented as narrative). NFS-representative tests + process recovery → `docs/DEPLOYMENT.md` (already present). Quality gates → MAINTAINER-GUIDE + `pyproject.toml` + CI | `52ded38` |
| Recommended First Release Boundary | MIGRATED + TRANSCRIBED | In-scope list → delivered milestones M1–M8 (`docs/ROADMAP.md`) + canonical docs. Deferred list → ROADMAP § Deferred / Delivered post-1.0; the 4 never-planned items (Network API, web dashboard, metrics server, advanced scheduling) **migrated** as individual ROADMAP § Deferred bullets. Closing framing → CLAUDE.md overview + ARCHITECTURE | `6b436be` |
| Recommended Architecture | TRANSCRIBED | `docs/ARCHITECTURE.md` — service/systemd model → § Process model; submit→ack→100 GB → § What the system is (L1-SYS-001/002); 10-step flow (incl. manifest write, "accepted" response, prepare-next) → § What the system is + § Durable per-file workflow (manifest = step 2), CLI-REF `submit` (L2-CLI-008), impl `manifests.py`/`submission.py`; deletion principle → ARCHITECTURE (L1-SYS-003) + CLAUDE.md | `e8edbe1` |
| How the Simulation Script Starts the Transfer | TRANSCRIBED | `docs/ARCHITECTURE.md` (§§ Process model, Recovery, Error pipeline, Service readiness, Logging) + `docs/CLI-REFERENCE.md` § `submit` (L2-CLI-008/009); duplicate-process protection → `ProcessLock` (L3-CTL-004). Unit name `background-file-mover.service` superseded by hybrid naming → `file-mover.service` (DEPLOYMENT) | `4f1f839` |
| Communication Between the Orchestration Script and Mover | MIGRATED + TRANSCRIBED | Option 2 (chosen: Unix socket + SQLite + JSON manifests) → ROADMAP locked decisions + `docs/ARCHITECTURE.md` § Process model + `docs/12-FACTOR.md` VII; stdlib module list → L1-SYS-009/L3-PY-001. Option 1 (filesystem spool queue) **migrated** to `docs/ROADMAP.md` § Deferred as a future portability / Windows-support capability | `04089e4` |
| The Most Important Operation: Claiming the Files | MIGRATED + TRANSCRIBED | Mechanic (same-fs atomic `os.replace` into staging dir, EXDEV rule, never `shutil.move`) → `docs/ARCHITECTURE.md` § Claiming (new) + L3-SUB-001 / L3-PY-003. The 6 staging-directory reasons **migrated** to § Claiming. Marker name `.moving` superseded by configurable `[paths] claim_directory_name` (default `.swit-moving`, already implemented + validated) | `0200bff` |
| Preventing the Mover From Claiming Files Still Being Written | TRANSCRIBED (1 deliberate non-adoption) | Readiness contract → `docs/CONFIG-REFERENCE.md` § [stability] note; defensive checks → `SourceValidator` (validation.py: regular-file + symlink + roots + deterministic enumeration, L2 line 442) + `[stability]` (poll_count/interval) + `[paths]` + claimed dev/inode identity (L3-SUB). **Not carried:** "six-host set present when required" — service is agnostic to expected file counts; completeness is the orchestration's responsibility | `a459a81` |
| Durable Job State | MIGRATED + TRANSCRIBED | State machine → `docs/ARCHITECTURE.md` § Job state machine (verbatim); job/file fields → `jobs/models.py` records. Manifest format + why-both rationale **migrated** to ARCHITECTURE § Durable state and the manifest (shipped format — CAPTURE's example was a superseded proposal). `created_at` + integrity now in **both** record and manifest (L2-JOB-007, implemented this batch); per-file manifest hashes → ROADMAP § Deferred | `38cb70a` |
| Hashing and Integrity Modes | MIGRATED + TRANSCRIBED | Modes 1/2/4 → `IntegrityMode` enum + `[integrity] mode` + `transfer/integrity.py`; algorithms (sha256 default / sha512 / blake2b, avoid MD5) → `HashAlgorithm` enum + `[integrity] algorithm`. Mode 3 (streaming hash-while-copy, unbuilt) **migrated** to ROADMAP § Deferred as a source-I/O optimization | `189fe4a` |
| Safe Destination Publication | TRANSCRIBED | `docs/ARCHITECTURE.md` § Durable per-file workflow (temp → copy → flush+fsync → verify → `os.replace` publish → fsync dir → delete source): L2-DPR-001..007, L2-POSIX-007..012, L3-PY-003/004; downstream-never-sees-partial → L2-DST-004. Temp prefix `.partial-` superseded by configurable `[paths] temporary_file_prefix` (default `.swit-partial-`) | `fd7cfb5` |
| Copy Versus Move Semantics | TRANSCRIBED | Near-verbatim in `docs/ARCHITECTURE.md` § What the system is (claim → copy → verify → publish → delete-source; separate NFS mounts, no atomic cross-fs move; transaction-like semantics) + CLAUDE.md | `ffc85ca` |
| Recovery Behavior | TRANSCRIBED (1 superseded) | Per-crash-point reconciliation + observable-state principle → `docs/ARCHITECTURE.md` § Recovery (near-verbatim) + `recovery/manager.py`; L1-SYS-005, L2-CLN-001..005. **Superseded:** the "restart from zero, resume-at-offset later" note — resume shipped in v0.3.0 (L2-RSM-001..003) | `60ec0b8` |
| Duplicate and Collision Handling | MIGRATED + TRANSCRIBED | Compare-and-reuse-or-collide + never-silent-replace → L2-DST-001..003 + `ExistingDestinationPolicy` (`fail`, `verify-and-reuse`) + `JobState.MANUAL_INTERVENTION`. `overwrite` deliberately excluded (enum docstring). `version` policy (unbuilt) **migrated** to ROADMAP § Deferred | `cab7b93` |
| Concurrency | TRANSCRIBED (1 superseded) | Bounded configurable concurrency (`max_concurrent_jobs=1`, `max_concurrent_files=2`, `copy_buffer_size_bytes=8388608`) → `configuration.py` + CONFIG-REFERENCE + ARCHITECTURE § Process model; defaults verbatim. **Superseded:** "throughput limit later" note — bandwidth limiting shipped v0.2.0 (L2-BWL) | `56b371c` |
| Proposed Application Components | MIGRATED + TRANSCRIBED | Superseded proposed layout → actual structure in `docs/ARCHITECTURE.md` § Module map (**completed** this increment: +submission/validation/claiming/manifests/systemd/ratelimit) + MAINTAINER § Repository layout. `FileMoverApplication` not built (→ `BackgroundMoverService`); `FileTransferWorker` → `FileMover` | `1a3fea4` |
| Proposed CLI | TRANSCRIBED | All commands + the subprocess orchestration example + submit-returns-after-durable-record → `docs/CLI-REFERENCE.md` (superset: +stats/throttle/pause/resume/cancel) + `docs/DEPLOYMENT.md`; L2-CLI-008 | `b160e7e` |
| Configuration | MIGRATED + TRANSCRIBED | Superseded proposed schema → shipped config in CONFIG-REFERENCE + `config/file-mover.ini`. Renames: `[validation]`→`[stability]`+`[paths]`, `.moving`→`.swit-moving`, `partial_file_prefix`→`temporary_file_prefix`; removed `log_directory`/`manifest_filename`; `format=json` already in ROADMAP. Unbuilt `minimum_free_space_margin_bytes` **migrated** to ROADMAP § Deferred (proactive free-space check) | `e681b72` |
| "Production Ready, No Panic" | TRANSCRIBED | No-panic list + startup-refusal conditions near-verbatim in `docs/ARCHITECTURE.md` § Error pipeline (L1-SYS-010, L1-ROB-001): classified retry/retain (`ErrorClassifier` + `transfer/retry.py`, L2-RTY), temp-never-final (L2-DST-004), source-deletion-last (L1-SYS-003), recovery (L1-SYS-005), graceful shutdown, SERVICE_FATAL refusal (L3-CTL-004) | `4829d47` |
| file-handler review — round 1 (handler.py) | TRANSCRIBED + MIGRATED + HISTORICAL | Adopted decisions → code/docs: `ErrorDisposition`, `FileMoverError` hierarchy, `SubmissionResult`, error classifier + each-layer-catch/reraise (`transfer/retry.py` + ARCH Error pipeline), no-god-class decomposition (module map), centralized structured logging (L3-PY-013/014), durable state, MOVE_COMPLETE, `JobStatistics`, L3-PY-001. Event publisher → **Draft** `L2-EVT`/`L3-EVT` (flagged in ROADMAP § Known gaps). Durable event/audit log → ROADMAP § Deferred. "Specific Issues in the Current Code" old-code critique = historical | `4210b0c` |
| file-handler review — round 2 (event.py + config_models.py) | TRANSCRIBED + MIGRATED + HISTORICAL | Config subsystem shipped: `ConfigurationLoader`, frozen dataclasses + `ApplicationConfig`, `OptionSpec`/`ConfigurationValidationError`, all cross-field rules, the three enums; source of `L2-CFG-001..007`. Event portion = source of **Draft** `L2-EVT`/`L3-EVT` (L2-EVT-003 principle reflected in coordinator). Migrated to ROADMAP § Deferred: file-size submission policies + regex/filename-filter submission. Pydantic/event.py old-code critique = historical | `ed61b71` |
| file-handler review — round 3 (cli.py) | TRANSCRIBED + MIGRATED + HISTORICAL | Shipped: CLI command set/structure, `ExitCode` enum, `create_parser`/`main`, handler-per-command, exception boundary→INTERNAL_ERROR, stdout/stderr contract, no-config-rewrite (L2-CLI-007), thin-client, `stats`, `__main__` safety, submission-timing Option B (L2-CLI-008/009); source of `L2-CLI-001..011` + `L3-CLI-001..005`. Migrated to ROADMAP § Deferred: per-job policy overrides + persisted per-phase timings. Old cli.py critique = historical | `9fb032d` |
| file-handler review — round 4 (directory_factory.py) | TRANSCRIBED + HISTORICAL (+ gap flagged) | Shipped: load→validate→explain→construct (`ConfigurationLoader`), `OptionSpec`, `ConfigurationValidationError`/`ConfigurationIssue`, no-reflection/no-fallback/no-assert, filesystem identity (dev/inode) + same-device claim + explicit path validation, no fake storage backend; source of `L2-ARC-001..006`, `L2-CFG-008..011`, `L2-FS-001..005`. **Gap:** `L2-FS-001..004`/`L2-ARC-003/004/006`/`L2-CFG-010` `Draft`/untraced → ROADMAP § Known gaps (traceability audit). Old-factory critique = historical | `36bc641` |
| file-handler review — round 5 (local.py) | TRANSCRIBED + HISTORICAL (+ gap broadened) | Shipped: POSIX filesystem ops + cleanup semantics (errno-preserving exceptions, deterministic `os.scandir` inventory, identity-revalidation-before-delete, all-or-nothing inventory, `O_EXCL`/`O_NOFOLLOW`, atomic same-fs publish, idempotent cleanup); source of `L2-POSIX-001..012`, `L2-CLN-001..005`, `L2-STO-001..005`. Storage abstraction + S3 → deferred S3 adapter (ROADMAP). **Gap broadened:** `L2-POSIX-007`/`L2-CLN-005`/etc. (data-safety) `Draft`/untraced → ROADMAP § Known gaps. Performance/Final-Assessment = historical | `2ee9614` |
| file-handler review — round 6 (_directory.py, copy engine) | TRANSCRIBED + HISTORICAL (+ gap extended) | Source of the M6 transfer engine (all shipped): 15-step per-file workflow, `BufferedFileCopyEngine` + kernel strategy, bounded concurrency, temp→atomic-publish, flush+fsync, never-overwrite, classified durable retry, delete-only-claimed-records + identity revalidation; source of `L2-COPY-001..010`, `L2-RTY-001..006`, `L2-DST-001..005`, `L2-DEL-001..004`. Resume shipped v0.3.0; `HashingCopyStrategy` = roadmapped streaming-hash. **Gap:** `L2-COPY-005/008`/`L2-DST-001`/`L2-DEL-001/004` `Draft`/untraced → ROADMAP § Known gaps. Perf/Final-Assessment = historical | `4eace6f` |
| Q&A — interacting with the running service via the CLI | TRANSCRIBED | Control-plane design fully shipped: Unix-socket + JSON request/response → ARCHITECTURE § Process model + `control/` (L2-CTL/L3-CTL); 4-byte framing (L3-PY-006/L3-CTL-001); explicit dispatcher (L3-CTL-002); separate control pool + `[control]` limits; exit-4-unavailable; durable-boundary + idempotent `request_id` (L2-CLI-008/L2-SUB-001); socket perms → DEPLOYMENT. `database inspect`/spool alternatives already on ROADMAP | `b29e4a5` |
| Q&A — setting up the server step by step | TRANSCRIBED | Full server-setup runbook → `docs/DEPLOYMENT.md` (layout, `mover` account, dirs, config, wheel/venv install, `Type=notify` systemd unit, socket verification, acceptance tests) + ARCHITECTURE (components, control plane, startup order, main loop, graceful shutdown) + `control/` + SQLite pragmas (L3-PY-007) + `health`. **Superseded:** `swit-` operator-facing names → hybrid naming; `[logging] log_to_journal`/`log_to_file` removed (twelve-factor); `Type=simple` → `Type=notify` | _this commit_ |

## My Prompt:
I have a new project which needs to be completed today called `Background File Mover` which will be written in Python 3.10. 
Requirements: 
* No External Dependencies for the Application 
* External Dependencies allowed for Development (ruff, etc) 
* Follow PEP statndards 
* Production Ready, No Panic 
* Google Docstrings 
* Module Docstrings 
* Coding Standards and Best Practices 
* Class Based 
* Document L1, L2, L3 Requirements 
* Fully Pytested 

Lets Talk about the requirements more so we can kickstart this project more effectively.  
  
We have a system which runs a scenario/simulation and data is recorded. Those files are recorded locally on each of the Hosts running the simulation. There are six hosts which run the simulation each recording data to the same NFS mount (these are Linux Hosts). There are a collection of python scripts which orchestrate the simulation and at the end part of the process there is a step which gets triggered to move the files from the local NFS mount to a remote data processing NFS mount and compute platform. The problem we are having is the data sets and recordings are totaling around 100 GB of data and it is causing the simulation hosts to pause for a very long period of time while data is being moved at which time the simulation platform can not be prepared for the next run. We need a python application which will be able to run in the background separate from the simulation orchestration python scripts moving the recordings. So the simulation orchestration python scripts will trigger the separate move process with a list of files or a folder which needs to be moved.  
  
How would a python script kick off a process like this? What would this application look like? It must be durable because we cannot lose data during this process. The first step will be to rename the files so they do not get overwritten by the simulation host while they get moved.  
  
I would like to make sure we ensure data movement integrity. Though any sort of hashing would need to be configurable to turn on or off and the hash value would be written into a file before the files were moved to a different location. 
Lets get started designing this up. Explain how all this will work.  
  
## Recommended Architecture

_(§ "Recommended Architecture" retired — see the retirement ledger at the top of this
file. Fully transcribed into `docs/ARCHITECTURE.md` (§ What the system is, § Process
model, § Durable per-file workflow); the deletion principle is a near-verbatim match
there (L1-SYS-003) and in CLAUDE.md.)_

## How the Simulation Script Starts the Transfer

_(§ "How the Simulation Script Starts the Transfer" retired — see the retirement ledger
at the top of this file. Transcribed into `docs/ARCHITECTURE.md` (§§ Process model,
Recovery, Error pipeline, Service readiness, Logging) + `docs/CLI-REFERENCE.md` § submit
(L2-CLI-008/009). Unit name `background-file-mover.service` was superseded by the hybrid
naming decision to `file-mover.service` — see `docs/DEPLOYMENT.md`.)_

## Communication Between the Orchestration Script and Mover

_(§ "Communication Between the Orchestration Script and Mover" retired — see the
retirement ledger at the top of this file. Option 2 (Unix socket + SQLite + JSON
manifests, chosen) → ROADMAP locked decisions + `docs/ARCHITECTURE.md` § Process model +
`docs/12-FACTOR.md` (VII). Option 1 (filesystem spool queue) was migrated to
`docs/ROADMAP.md` § Deferred as a future portability/Windows-support capability.)_

## The Most Important Operation: Claiming the Files

_(§ "The Most Important Operation: Claiming the Files" retired — see the retirement
ledger at the top of this file. Transcribed into `docs/ARCHITECTURE.md` § Claiming
(same-fs atomic `os.replace` into `<claim_directory_name>/<job_id>/`, EXDEV rule, and the
six staging-directory reasons migrated there) + L3-SUB-001 / L3-PY-003. Marker name
`.moving` was superseded by the configurable `[paths] claim_directory_name`, default
`.swit-moving`.)_

## Preventing the Mover From Claiming Files Still Being Written

_(§ "Preventing the Mover From Claiming Files Still Being Written" retired — see the
retirement ledger at the top of this file. Readiness contract → `docs/CONFIG-REFERENCE.md`
§ [stability] note; defensive checks → `SourceValidator` (validation.py) + [stability] +
[paths] (`reject_symbolic_links`, `allowed_source_roots`) + claimed dev/inode identity
(L3-SUB). The 'six-host set present when required' idea was deliberately not carried —
the service is agnostic to expected file counts; job completeness is the orchestration's
responsibility per the readiness contract.)_

## Durable Job State

_(§ "Durable Job State" retired — see the retirement ledger at the top of this file.
State machine → `docs/ARCHITECTURE.md` § Job state machine (verbatim). Job/file record
fields → `jobs/models.py` `JobRecord`/`FileRecord`. Manifest format + SQLite-vs-manifest
rationale → `docs/ARCHITECTURE.md` § Durable state and the manifest (shipped format; note
CAPTURE's example was a superseded proposal). created_at + integrity are now recorded in
BOTH the record and the manifest (L2-JOB-007); per-file hashes in the manifest are a
ROADMAP § Deferred item. Manifest-before-copy-when-hashing → L3-INT-003.)_

## Hashing and Integrity Modes

_(§ "Hashing and Integrity Modes" retired — see the retirement ledger at the top of this
file. Modes 1/2/4 (metadata / source-hash / source-and-destination-hash) → `IntegrityMode`
enum + `[integrity] mode` + `transfer/integrity.py` + ARCHITECTURE. Algorithms (sha256
default, sha512, blake2b; avoid MD5) → `HashAlgorithm` enum + `[integrity] algorithm`.
Mode 3 (streaming hash-while-copy) was not built — migrated to `docs/ROADMAP.md`
§ Deferred as a source-I/O optimization.)_

## Safe Destination Publication

_(§ "Safe Destination Publication" retired — see the retirement ledger at the top of this
file. Transcribed into `docs/ARCHITECTURE.md` § Durable per-file workflow (create O_EXCL
temp → copy → flush+fsync → verify → publish via os.replace → fsync dir → delete source):
L2-DPR-001..007, L2-POSIX-007..012, L3-PY-003/004; downstream-never-sees-partial →
L2-DST-004. Temp prefix `.partial-` superseded by configurable `[paths]
temporary_file_prefix`, default `.swit-partial-`.)_

## Copy Versus Move Semantics

_(§ "Copy Versus Move Semantics" retired — see the retirement ledger at the top of this
file. Transcribed near-verbatim into `docs/ARCHITECTURE.md` § What the system is (the
claim → copy → verify → publish → delete-source workflow; separate NFS mounts with no
atomic cross-filesystem move; transaction-like semantics) and CLAUDE.md.)_

## Recovery Behavior

_(§ "Recovery Behavior" retired — see the retirement ledger at the top of this file.
Per-crash-point reconciliation + the observable-state principle → `docs/ARCHITECTURE.md`
§ Recovery (near-verbatim) + `recovery/manager.py`; L1-SYS-005, L2-CLN-001..005. The
"restart from byte zero, resume-at-offset later" note is superseded: partial-file
byte-offset resume shipped in v0.3.0 (L2-RSM-001..003, ARCHITECTURE § Partial-file
resume).)_

## Duplicate and Collision Handling

_(§ "Duplicate and Collision Handling" retired — see the retirement ledger at the top of
this file. Compare-and-reuse-or-collide + never-silent-replace → L2-DST-001..003 +
`ExistingDestinationPolicy` (`fail`, `verify-and-reuse`) + `JobState.MANUAL_INTERVENTION`.
`overwrite` deliberately excluded (enum docstring). `version` policy (unbuilt) migrated to
`docs/ROADMAP.md` § Deferred.)_

## Concurrency

_(§ "Concurrency" retired — see the retirement ledger at the top of this file. Bounded,
configurable concurrency (`[transfer] max_concurrent_jobs=1`, `max_concurrent_files=2`,
`copy_buffer_size_bytes=8388608`) → `configuration.py` + `docs/CONFIG-REFERENCE.md` +
ARCHITECTURE § Process model (bounded transfer pool); defaults match verbatim. The
"throughput limit later" note is superseded: dynamic bandwidth limiting shipped in v0.2.0
(L2-BWL, `throttle`, ARCHITECTURE § Bandwidth limiting).)_

## Proposed Application Components

_(§ "Proposed Application Components" retired — see the retirement ledger at the top of
this file. This was a proposed layout, superseded by the actual `src/file_mover/`
structure documented in `docs/ARCHITECTURE.md` § Module map (completed this increment) +
`docs/MAINTAINER-GUIDE.md` § Repository layout. Principal classes all shipped except
`FileMoverApplication` (not built — consolidated into `BackgroundMoverService`); the
proposed `FileTransferWorker` shipped as `FileMover` (`transfer/file_mover.py`). The
"class-based where there is state, functions otherwise" principle → ARCHITECTURE module
map note.)_

## Proposed CLI

_(§ "Proposed CLI" retired — see the retirement ledger at the top of this file. All
commands (service run, submit, status, list, retry, doctor, recover) and the
subprocess-based orchestration example → `docs/CLI-REFERENCE.md` (a superset that also
adds stats/throttle/pause/resume/cancel) + `docs/DEPLOYMENT.md`; submit-returns-after-
durable-record → CLI-REFERENCE § submit (L2-CLI-008).)_

## Configuration

_(§ "Configuration" retired — see the retirement ledger at the top of this file. This was
a proposed schema, superseded by the shipped config in `docs/CONFIG-REFERENCE.md` +
`config/file-mover.ini` (sections `[service] [control] [paths] [transfer] [integrity]
[stability] [logging]`). Renames/removals: `[validation]`→`[stability]`+`[paths]`;
`.moving`→`.swit-moving`; `partial_file_prefix`→`temporary_file_prefix`;
`log_directory`/`manifest_filename` removed; `format=json` → ROADMAP. Unbuilt
`minimum_free_space_margin_bytes` (proactive free-space check) migrated to ROADMAP
§ Deferred.)_

## “Production Ready, No Panic”

_(§ "Production Ready, No Panic" retired — see the retirement ledger at the top of this
file. The no-panic list and the deliberate startup-refusal conditions are near-verbatim
in `docs/ARCHITECTURE.md` § Error pipeline (L1-SYS-010, L1-ROB-001): classified retry vs
retain (`ErrorClassifier` + `transfer/retry.py`, L2-RTY), retain-source on
ENOSPC/EACCES/NFS, temp-never-final (L2-DST-004), source-deletion-last (L1-SYS-003),
recovery (L1-SYS-005), graceful shutdown, and SERVICE_FATAL startup refusal
(incl. L3-CTL-004 ProcessLock).)_

_(§ "Initial L1 Requirements" retired — see the retirement ledger at the top of this
file. Fully transcribed into `docs/L1-REQ.md`.)_

_(§ "Example L2 Decomposition" retired — see the retirement ledger at the top of this
file. Fully transcribed into `docs/L2-REQ.md`.)_

_(§ "Example L3 Decomposition" retired — see the retirement ledger at the top of this
file. Fully transcribed into `docs/L3-REQ.md`.)_

## Testing Strategy

_(§ "Testing Strategy" retired — see the retirement ledger at the top of this file.
The testing taxonomy, fault-injection boundary list, and guiding principle were migrated
to `docs/MAINTAINER-GUIDE.md` § Testing strategy; NFS-representative tests and process
recovery live in `docs/DEPLOYMENT.md`; quality gates in MAINTAINER-GUIDE + CI.)_

## Recommended First Release Boundary

_(§ "Recommended First Release Boundary" retired — see the retirement ledger at the
top of this file. The in-scope list → delivered milestones M1–M8 in `docs/ROADMAP.md`
and their canonical docs; the deferred list → ROADMAP § Deferred / Delivered post-1.0
(Network API, web dashboard, metrics server, advanced scheduling added there this
increment); the closing framing → CLAUDE.md overview + ARCHITECTURE.)_

## file-handler review — round 1 (handler.py)

_(The first `file-handler` review round is retired — see the retirement ledger at the top
of this file. Adopted decisions shipped and are transcribed: `ErrorDisposition`
(`jobs/models.py`), the `FileMoverError` hierarchy (`exceptions.py`), typed results
(`SubmissionResult`), the error classifier + each-layer-catch-and-reraise
(`transfer/retry.py` + ARCHITECTURE § Error pipeline), no-god-class decomposition
(ARCHITECTURE module map), centralized structured logging (`logging_config.py` +
LOGGING.md, L3-PY-013/014), durable SQLite state, MOVE_COMPLETE-only-after-all-steps,
configparser-not-dotenv (L3-PY-001), and typed immutable stats (`JobStatistics`). The
event system (TransferEvent / publisher) maps to the **Draft** `L2-EVT`/`L3-EVT`
requirements (specified, not yet built — see ROADMAP § Known gaps). The durable
event/audit log was migrated to ROADMAP § Deferred. The old-code critique ("Specific
Issues in the Current Code") is historical.)_

## file-handler review — round 2 (event.py + config_models.py)

_(Second `file-handler` review round retired — see the retirement ledger at the top of
this file. Config portion shipped and is transcribed: `ConfigurationLoader` (parse →
convert → validate → immutable), the frozen config dataclasses + `ApplicationConfig`,
strict unknown-field rejection (`OptionSpec` + `ConfigurationValidationError`), every
cross-field validation rule, and the `HashAlgorithm`/`IntegrityMode`/
`ExistingDestinationPolicy` enums — this section is the source of `L2-CFG-001..007`. The
event portion is the source of the **Draft** `L2-EVT-001..005` / `L3-EVT-001.1..1.5`
(observational-not-transactional principle L2-EVT-003 is reflected in the coordinator; the
publisher itself is unbuilt — ROADMAP § Known gaps). Two unbuilt ideas migrated to ROADMAP
§ Deferred: file-size submission policies and regex/filename-filter submission. The
Pydantic/event.py old-code critique is historical.)_

## file-handler review — round 3 (cli.py)

_(Third `file-handler` review round retired — see the retirement ledger at the top of this
file. Shipped and transcribed: the CLI command set + structure, the `ExitCode` enum, the
`create_parser`/`main` split, handler-per-command, the top-level exception boundary
(→ INTERNAL_ERROR), the stdout=result / stderr=diagnostics contract, no-config-file-
rewrite (L2-CLI-007), the thin-client model, the `stats` command, `__main__` safety, and
the settled submission-timing **Option B** (claim first, hash in the background, return
after claim — L2-CLI-008/009). This section is the source of `L2-CLI-001..011` and
`L3-CLI-001..005`. Two unbuilt ideas migrated to ROADMAP § Deferred: per-job submission
policy overrides and persisted per-phase job timings. The old-cli.py critique
(config-rewriting, the verbosity bug, hard-coded `__main__`) is historical.)_

## file-handler review — round 4 (directory_factory.py)

_(Fourth `file-handler` review round retired — see the retirement ledger at the top of
this file. Shipped and transcribed: the load→validate→explain→construct pipeline
(`ConfigurationLoader`), `OptionSpec`, `ConfigurationIssue`/`ConfigurationValidationError`
(collect-all), no-reflection explicit construction, no-reduced-validation-fallback,
no-assert-for-safety, filesystem identity (dev/inode/size/mtime) + same-device claim +
explicit lexical/fs path validation, and no fake storage backend. Source of
`L2-ARC-001..006`, `L2-CFG-008..011`, `L2-FS-001..005`. **Finding:** several of these
(`L2-FS-001..004`, `L2-ARC-003/004/006`, `L2-CFG-010`) are `Draft`/untraced in the matrix
though implemented — flagged in ROADMAP § Known gaps for a traceability audit. Old-factory
reflection/fallback/assert critique = historical.)_

## file-handler review — round 5 (local.py)

_(Fifth `file-handler` review round retired — see the retirement ledger at the top of this
file. Shipped and transcribed: the POSIX filesystem operations and cleanup semantics —
errno-preserving exceptions, `pathlib.Path`, per-phase race handling, idempotent deletion,
UTC + `st_mtime_ns`, deterministic `os.scandir` inventory, intent-specific open, identity
revalidation before delete, all-or-nothing inventory, `O_EXCL`/`O_NOFOLLOW`, atomic same-fs
publish. Source of `L2-POSIX-001..012`, `L2-CLN-001..005`, `L2-STO-001..005`. The storage
abstraction (`TransferSource`/`TransferDestination` Protocols) + S3 are the deferred S3
adapter (ROADMAP). **Finding:** many of these — incl. data-safety `L2-POSIX-007`,
`L2-CLN-005`, `L2-FS-*` — are `Draft`/untraced despite being implemented → ROADMAP § Known
gaps (traceability audit). Performance Conclusions / Final Assessment = historical.)_

## file-handler review — round 6 (_directory.py, the copy engine)

_(Sixth `file-handler` review round retired — see the retirement ledger at the top of this
file. This is the source of the transfer-engine requirements, all shipped (M6): the
15-step durable per-file workflow (ARCHITECTURE), the `BufferedFileCopyEngine` bounded
loop + kernel strategy, bounded configurable concurrency (one pool, `max_concurrent_*`),
temp-then-atomic-publish, flush+fsync, never-overwrite-destination, classified durable
retry, and delete-only-claimed-records with identity revalidation. Source of
`L2-COPY-001..010`, `L2-RTY-001..006`, `L2-DST-001..005`, `L2-DEL-001..004`. Whole-file
retry's "resume later" shipped v0.3.0; the copy-strategy `HashingCopyStrategy` is the
roadmapped streaming-hash. **Finding:** several data-safety ones (`L2-COPY-005/008`,
`L2-DST-001`, `L2-DEL-001/004`) are `Draft`/untraced → ROADMAP § Known gaps. Performance
Assessment / Final Assessment = historical.)_

## Q&A — interacting with the running service via the CLI

_(Retired — see the retirement ledger at the top of this file. The control-plane design is
fully shipped and documented: Unix-socket control channel + JSON request/response →
`docs/ARCHITECTURE.md` § Process model + `control/` (L2-CTL, L3-CTL); 4-byte length-prefix
framing → L3-PY-006 / L3-CTL-001; explicit `CommandDispatcher` → L3-CTL-002; separate
control thread pool + `[control]` limits → ARCHITECTURE + CONFIG-REFERENCE;
service-unavailable → exit 4; durable-boundary + idempotent `request_id` submit →
L2-CLI-008 / L2-SUB-001; socket permissions → DEPLOYMENT. The `database inspect --offline`
and spool-directory alternatives it raises are already on the ROADMAP.)_

## Q&A — setting up the server step by step

_(Retired — see the retirement ledger at the top of this file. The full server-setup
runbook is transcribed into `docs/DEPLOYMENT.md` (runtime layout, `mover` service account,
directories, config, wheel/venv install, systemd unit, socket verification, and the
acceptance tests: small transfer / restart recovery / idempotent submit) + `docs/
ARCHITECTURE.md` (server components, control plane, startup order, main loop, graceful
shutdown) + `control/` modules + SQLite pragmas (L3-PY-007) + the `Type=notify` systemd
unit + `health`. **Superseded:** `swit-`-prefixed operator-facing names → hybrid naming
(`file-mover`/`mover`; only on-disk markers keep `swit-`); `[logging] log_to_journal`/
`log_to_file` removed (twelve-factor); `Type=simple` → shipped `Type=notify`.)_

_(§ "Recommended Initial Build Order" retired — see the retirement ledger at the top of
this file. Fully transcribed into `docs/ROADMAP.md`.)_
