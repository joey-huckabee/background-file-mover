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
| file-handler review — round 6 (_directory.py, copy engine) | TRANSCRIBED + HISTORICAL (+ gap extended) | Source of the M6 transfer engine (all shipped): 15-step per-file workflow, `BufferedFileCopyEngine` + kernel strategy, bounded concurrency, temp→atomic-publish, flush+fsync, never-overwrite, classified durable retry, delete-only-claimed-records + identity revalidation; source of `L2-COPY-001..010`, `L2-RTY-001..006`, `L2-DST-001..005`, `L2-DEL-001..004`. Resume shipped v0.3.0; `HashingCopyStrategy` = roadmapped streaming-hash. **Gap:** `L2-COPY-005/008`/`L2-DST-001`/`L2-DEL-001/004` `Draft`/untraced → ROADMAP § Known gaps. Perf/Final-Assessment = historical | _this commit_ |

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

## My Prompt:
I am curious about something. While the long running service is running how do we interact with it using the CLI?

## Chat Reply:
The CLI should interact with the running service through a local control channel. For this Linux-only first release, the best fit is a Unix domain socket.
```
Simulation script / operator
        │
        │ file-mover submit ...
        ▼
Short-lived CLI process
        │
        │ JSON request over Unix socket
        ▼
/run/file-mover/control.sock
        │
        ▼
Long-running systemd service
        │
        ├── validates request
        ├── updates SQLite
        ├── claims files
        └── returns JSON response
```
#### Why a Unix socket
It provides:

* Direct request/response communication
* Local-only access by default
* Normal Linux file permissions
* No TCP port to manage
* No external dependency
* Immediate feedback from the service
* Separation between the CLI and service implementation

Python 3.10 provides everything needed through `socket`.

#### Example interaction
The operator runs:
```shell
file-mover submit \
    --scenario-id SWIT-001 \
    --source /recordings/run-001 \
    --destination /processing/run-001
```
The CLI does not perform the transfer. It:

1. Loads enough configuration to locate the socket.
2. Connects to:
```
/run/file-mover/control.sock
```
3. Sends a request such as:
```json
{
  "protocol_version": 1,
  "request_id": "4e5ee95d-48da-4899-b2ec-56da9df5afef",
  "command": "submit",
  "arguments": {
    "scenario_id": "SWIT-001",
    "source": "/recordings/run-001",
    "destination": "/processing/run-001"
  }
}
```
4. The service validates and claims the files.
5. The service replies:
```json
{
  "protocol_version": 1,
  "request_id": "4e5ee95d-48da-4899-b2ec-56da9df5afef",
  "success": true,
  "result": {
    "job_id": "d9302beb-87f9-48ee-b403-dd9f30b05047",
    "state": "QUEUED_FOR_HASHING",
    "claimed_file_count": 18,
    "claimed_bytes": 107374182400
  }
}
```
6. The CLI prints the result and exits.

The service continues hashing and moving files after the CLI exits.

#### Status requests
Later:
```
file-mover status d9302beb-87f9-48ee-b403-dd9f30b05047
```

The CLI sends:
```json
{
  "protocol_version": 1,
  "request_id": "...",
  "command": "status",
  "arguments": {
    "job_id": "d9302beb-87f9-48ee-b403-dd9f30b05047"
  }
}
```
The service responds:
```json
{
  "success": true,
  "result": {
    "job_id": "d9302beb-87f9-48ee-b403-dd9f30b05047",
    "state": "COPYING",
    "files_total": 18,
    "files_completed": 11,
    "bytes_total": 107374182400,
    "bytes_completed": 67645734912,
    "current_attempt": 1,
    "last_error": null
  }
}
```
#### Which commands should use the socket
These should normally communicate with the service:
```
submit
status
list
retry
cancel
pause
resume
stats
service-status
```
These can run locally without the service:
```
--help
--version
config validate
```
The `doctor` command may do both:

* Validate local configuration itself.
* Ask the service for its current health and database status.

#### Socket permissions
The systemd unit creates or owns:
```
/run/file-mover/
└── control.sock
```
Example permissions:
```
srw-rw---- root mover control.sock
```
Only:
* The service account
* Root
* Members of the mover group

can submit or modify jobs.

Read-only commands could later use a separate socket or application-level authorization, but one group-controlled socket is adequate initially.

#### Framing messages correctly
Unix sockets are byte streams. One `send()` does not necessarily correspond to one `recv()`.

We need explicit message framing. A simple robust protocol is:

```
4-byte unsigned message length
JSON payload of that length
```
Conceptually:
```
[00 00 01 A4][JSON bytes...]
```
Both client and server must:

* Read exactly four header bytes.
* Decode the payload length.
* Reject oversized messages.
* Read exactly that many payload bytes.
* Decode UTF-8 JSON.
* Validate the protocol version and command.

A newline-delimited JSON protocol is simpler, but length-prefix framing is safer if future messages contain embedded formatting or become larger.

#### Server structure

The long-running service would include a control server:
```
BackgroundMoverService
├── ControlSocketServer
├── JobSubmissionService
├── JobQueryService
├── TransferCoordinator
└── SQLiteJobRepository
```
The socket server should remain small:
```python
class ControlSocketServer:
    """Accept and dispatch local CLI control requests."""

    def serve_forever(self) -> None:
        """Accept requests until shutdown is requested."""

    def handle_connection(self, connection: socket.socket) -> None:
        """Read one request, dispatch it, and send one response."""
```
A request dispatcher maps commands explicitly:
```python
handlers = {
    "submit": submission_handler,
    "status": status_handler,
    "list": list_handler,
    "retry": retry_handler,
}
```
Do not use dynamic method invocation based directly on user-supplied command names.

#### Concurrent CLI requests

The service should be able to handle several quick control requests while transfers run.

For example:
```
Thread 1: control socket accept loop
Thread 2: submit request
Thread 3: status request
Worker 1: copying host01.dat
Worker 2: copying host02.dat
```
Control requests should use a small separate thread pool from transfer workers so a saturated copy pool does not prevent status queries.

Example limits:
```
[control]
max_concurrent_requests = 8
request_timeout_seconds = 30
maximum_message_bytes = 1048576
```

#### What happens when the service is unavailable

When the CLI cannot connect:
```
Error: SWIT Background File Mover service is not available.
Socket: /run/swit-file-mover/control.sock
Check: systemctl status swit-background-file-mover
```
Exit code:
```
4 = service unavailable
```
The CLI should not silently start its own transfer process. That could create competing workers and bypass the singleton service.

#### Could the CLI read SQLite directly?

For read-only operations, technically yes:
```shell
file-mover status ...
```
could open the SQLite database directly.

I would avoid that as the primary design because:

* The CLI becomes coupled to the database schema.
* Authorization is harder to centralize.
* Service-computed progress may be newer than persisted state.
* Schema migrations affect both independently.
* Write commands must use the service anyway.
* Reading through the service gives one consistent control interface.

An emergency offline inspection command could be added later:
```shell
file-mover database inspect --offline
```
but it should not be the normal path.

#### Could we use only a spool directory?

Yes. The CLI could atomically place requests in:
```
/var/lib/swit-file-mover/requests/
```
and poll for a response file.

That is durable and simple, but weaker for interactive commands:

* Status responses are slower.
* Timeouts and response cleanup are awkward.
* Request authentication is mostly filesystem-based.
* Duplicate requests need extra handling.
* There is no immediate connection-level failure.
* Operators may leave stale request files.

A spool directory remains useful internally for manifests or as a fallback, but the Unix socket is better for CLI control.

#### Important durability boundary

The socket itself is not the durable queue.

For `submit`, the service must not respond with success merely because it received the request. It should respond only after:
```
request validated
job record committed
source inventory committed
files claimed
manifest safely written
job queued durably
```
Then the response can safely say:
```
accepted
```
If the socket disconnects after the service committed the job but before the CLI received the response, the orchestration script may not know whether submission succeeded. That is why every request needs a client-generated `request_id`.

The client can retry the same request:
```json
{
  "request_id": "4e5ee95d-48da-4899-b2ec-56da9df5afef"
}
```
The service checks whether that request was already processed and returns the original result instead of creating a duplicate job.

That gives us **idempotent submission**.

#### Recommended protocol rules
```
Transport: Unix domain stream socket
Encoding: UTF-8 JSON
Framing: 4-byte network-order length prefix
Maximum request size: configurable, default 1 MiB
One request per connection initially
Client-generated request ID required
Protocol version required
All responses echo request ID
Submit requests are idempotent
Socket operations have timeouts
Unknown commands are rejected
Malformed messages never terminate the service
```
So the CLI is essentially a short-lived local client, and the background application is both:

1. A durable transfer worker.
2. A small local command server.

That gives the orchestration scripts immediate, scriptable interaction without tying them to the long-running 100 GB transfer.

## My Prompt:
Tell me how I would setup the server - step by step

## Chat Reply:
Set up the server as a **systemd-managed Python service** that owns:

* The Unix domain control socket
* The SQLite job database
* The transfer worker pool
* Recovery after restart
* Graceful shutdown

The CLI remains a separate, short-lived client.

#### 1. Create the Runtime Layout

Use separate directories for configuration, durable state, runtime files, and logs.
```
/etc/file-mover/
└── file-mover.ini

/var/lib/file-mover/
├── jobs.db
├── manifests/
├── claims/
└── recovery/

/run/file-mover/
├── control.sock
└── service.pid

/var/log/file-mover/
└── file-mover.log
```
Purpose:
| Directory                  | Purpose                               |
| -------------------------- | ------------------------------------- |
| `/etc/swit-file-mover`     | Operator-managed configuration        |
| `/var/lib/swit-file-mover` | Durable job and recovery state        |
| `/run/swit-file-mover`     | Temporary runtime socket and PID data |
| `/var/log/swit-file-mover` | Optional file logs                    |
The Unix socket belongs in `/run` because it should be recreated after every reboot.

#### 2. Create a Dedicated Service Account

Do not run the mover as root unless filesystem permissions make that unavoidable.
```shell
sudo groupadd --system mover
sudo useradd \
    --system \
    --gid mover \
    --home-dir /var/lib/file-mover \
    --shell /usr/sbin/nologin \
    mover
```
The simulation orchestration account should be added to the control group:
```shell
sudo usermod -aG swit-mover simulation-user
```
That user must log out and back in before the new group membership applies.

The service account needs:

* Read, rename, and delete access on the source recording NFS mount
* Create, write, rename, and inspect access on the destination NFS mount
* Read/write access to /var/lib/swit-file-mover
* Permission to create the control socket in /run/swit-file-mover

#### 3. Create the Directories
```shell
sudo install \
    --directory \
    --owner=mover \
    --group=mover \
    --mode=0750 \
    /var/lib/file-mover

sudo install \
    --directory \
    --owner=mover \
    --group=mover \
    --mode=0750 \
    /var/lib/file-mover/manifests

sudo install \
    --directory \
    --owner=mover \
    --group=mover \
    --mode=0750 \
    /var/lib/file-mover/recovery

sudo install \
    --directory \
    --owner=root \
    --group=mover \
    --mode=0750 \
    /etc/file-mover

sudo install \
    --directory \
    --owner=mover \
    --group=mover \
    --mode=0750 \
    /var/log/file-mover
```
You normally do not manually create `/run/file-mover`. Let systemd create it on every startup using `RuntimeDirectory=`.

#### 4. Create the Configuration File

Example:
```
[service]
state_directory = /var/lib/swit-file-mover
database_path = /var/lib/swit-file-mover/jobs.db
manifest_directory = /var/lib/swit-file-mover/manifests
socket_path = /run/swit-file-mover/control.sock
shutdown_timeout_seconds = 60

[control]
socket_mode = 0660
max_concurrent_requests = 8
request_timeout_seconds = 30
maximum_message_bytes = 1048576

[paths]
allowed_source_roots = /swit/recordings
allowed_destination_roots = /data-processing/incoming
claim_directory_name = .swit-moving
temporary_file_prefix = .swit-partial-
reject_symbolic_links = true

[transfer]
max_concurrent_jobs = 1
max_concurrent_files = 2
copy_buffer_size_bytes = 8388608
retry_limit = 10
retry_initial_delay_seconds = 10
retry_max_delay_seconds = 900

[integrity]
enabled = true
mode = source-and-destination-hash
algorithm = sha256

[stability]
enabled = true
poll_count = 2
poll_interval_seconds = 5

[logging]
level = INFO
log_to_journal = true
log_to_file = false
```
Secure it:
```shell
sudo chown root:swit-mover /etc/file-mover/file-mover.ini
sudo chmod 0640 /etc/file-mover/file-mover.ini
```

#### 5. Build the Server Components

The service process should contain these primary objects:
```
BackgroundMoverService
├── ControlSocketServer
├── CommandDispatcher
├── SQLiteJobRepository
├── RecoveryManager
├── TransferCoordinator
└── ThreadPoolExecutor
```
A recommended module layout is:
```
src/file_mover/
├── __init__.py
├── __main__.py
├── cli.py
├── configuration.py
├── logging_config.py
├── service.py
├── control/
│   ├── __init__.py
│   ├── protocol.py
│   ├── server.py
│   ├── client.py
│   └── dispatcher.py
├── jobs/
│   ├── models.py
│   ├── repository.py
│   └── sqlite_repository.py
├── transfer/
│   ├── coordinator.py
│   ├── copy_engine.py
│   ├── integrity.py
│   └── retry.py
└── recovery/
    └── manager.py
```

#### 6. Define the Control Protocol

Use one request per socket connection initially.

Each message contains:
```
4-byte unsigned network-order payload length
UTF-8 JSON payload
```
Example request:
```json
{
  "protocol_version": 1,
  "request_id": "9d485205-d587-4c42-ae85-c463de1ddbdd",
  "command": "status",
  "arguments": {
    "job_id": "eb50371a-d93e-40f1-b8e3-cb0b452254b1"
  }
}
```
Example response:
```json
{
  "protocol_version": 1,
  "request_id": "9d485205-d587-4c42-ae85-c463de1ddbdd",
  "success": true,
  "result": {
    "state": "COPYING"
  }
}
```
The protocol module should provide four operations:
```python
encode_message()
send_message()
receive_exactly()
receive_message()
```
The server and CLI client must share this module so framing remains consistent.

#### 7. Implement Exact Socket Reads

Socket reads can return fewer bytes than requested.

Conceptually:
```python
def receive_exactly(sock: socket.socket, byte_count: int) -> bytes:
    """Receive exactly the requested number of bytes.

    Args:
        sock: Connected socket.
        byte_count: Number of bytes to receive.

    Returns:
        The received bytes.

    Raises:
        ConnectionError: If the peer closes the connection early.
    """
    chunks: list[bytes] = []
    remaining = byte_count

    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError(
                f"Connection closed with {remaining} byte(s) remaining."
            )

        chunks.append(chunk)
        remaining -= len(chunk)

    return b"".join(chunks)
```
Then:
```python
header = receive_exactly(sock, 4)
payload_length = struct.unpack("!I", header)[0]
```
Reject the message before allocating memory if it exceeds the configured maximum.

#### 8. Implement the Unix Socket Listener

At service startup:

1. Confirm the configured socket path is beneath `/run/file-mover`.
2. Remove a stale socket only after confirming no service is listening.
3. Create an `AF_UNIX`, `SOCK_STREAM` socket.
4. Bind it.
5. Set permissions.
6. Listen.
7. Accept connections until shutdown.

Conceptually:
```python
server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
server_socket.bind(str(socket_path))
os.chmod(socket_path, 0o660)
server_socket.listen(backlog)
server_socket.settimeout(1.0)
```
The one-second timeout allows the accept loop to periodically check whether shutdown was requested.

Do not use a permanently blocking `accept()` with no shutdown mechanism.

#### 9. Handle Stale Socket Files Safely

After an unclean shutdown, the filesystem entry may still exist.

Do not blindly unlink it.

The startup logic should:

1. Check whether the path exists.
2. Confirm that it is a Unix socket.
3. Attempt to connect to it.
4. If the connection succeeds, another service is already running.
5. If the connection returns `ECONNREFUSED`, treat it as stale.
6. Remove the stale socket.
7. Bind the new service socket.

Possible behavior:
```
socket absent
    → bind normally

socket present and active
    → refuse startup

socket present but connection refused
    → remove stale socket and bind

path present but is a regular file
    → refuse startup
```
Never delete an unexpected regular file at the configured socket path.

#### 10. Dispatch Requests Explicitly

Do not dynamically call methods based on untrusted command strings.

Use an explicit map:
```python
handlers = {
    "submit": self._handle_submit,
    "status": self._handle_status,
    "list": self._handle_list,
    "retry": self._handle_retry,
    "stats": self._handle_stats,
    "health": self._handle_health,
}
```
Unknown commands return:
```json
{
  "success": false,
  "error": {
    "code": "UNKNOWN_COMMAND",
    "message": "Unsupported command: restart-everything"
  }
}
```
Each handler should:

1. Validate the argument structure.
2. Convert arguments into typed request objects.
3. Call the application service.
4. Return a typed result.
5. Avoid implementing transfer logic itself.

#### 11. Keep Control Threads Separate From Copy Threads

Use a small control request pool:
```
Control pool: 4–8 threads
Transfer pool: 1–4 threads
```
Do not run socket request handlers in the transfer executor.

Otherwise, large file operations could prevent:
```shell
file-mover status ...
```
from responding.

Structure:
```python
control_executor = ThreadPoolExecutor(
    max_workers=8,
    thread_name_prefix="swit-control",
)

transfer_executor = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="swit-transfer",
)
```

#### 12. Initialize SQLite Before Accepting Requests

Startup order matters.

Use this sequence:

```
1. Load configuration.
2. Configure logging.
3. Acquire singleton process lock.
4. Validate directories and mounts.
5. Open SQLite.
6. Enable pragmas.
7. Apply schema migrations.
8. Run recovery reconciliation.
9. Start transfer workers.
10. Bind control socket.
11. Report service ready.
```
Do not accept `submit` requests before the database and recovery systems are ready.

Useful SQLite settings may include:
```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;
PRAGMA busy_timeout = 5000;
```
`FULL` synchronization is appropriate for durable job-state transitions, though it should be benchmarked.

Each thread should normally use its own SQLite connection. Do not casually share one connection among worker threads.

#### 13. Run Recovery Before New Work

At startup, inspect jobs in nonterminal states:
```
CLAIMING
HASHING
COPYING
VERIFYING
PUBLISHING
SOURCE_CLEANUP
RETRY_WAIT
```
For each job:

1. Compare database state with filesystem state.
2. Inspect claimed source files.
3. Inspect temporary destination files.
4. Inspect published destination files.
5. Resume, retry, or place the job into manual intervention.
6. Never assume an operation failed merely because the prior service stopped.

Only after reconciliation should the service process new queued work.

#### 14. Implement the Main Service Loop

The service should have two concurrent responsibilities:
```
Control server:
    accepts CLI requests

Transfer scheduler:
    looks for runnable jobs and submits file work
```
A basic scheduler loop can:
```
query next runnable file
claim it transactionally in SQLite
submit it to transfer executor
wait or continue until concurrency limit reached
process completed futures
update durable state
```
Do not rely only on an in-memory queue because queued jobs must survive restart.

SQLite is the durable queue.

#### 15. Add Graceful Shutdown

Systemd sends `SIGTERM` when stopping the service.

Register handlers:
```python
signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)
```
The handler should only set a thread-safe event:
```python
shutdown_event.set()
```
Do not perform complex filesystem or database operations directly inside the signal handler.

Shutdown sequence:
```
1. Stop accepting new socket connections.
2. Reject new submissions with SERVICE_STOPPING.
3. Stop scheduling new transfer files.
4. Allow active workers to reach safe checkpoints.
5. Persist active state.
6. Shut down executors.
7. Close SQLite connections.
8. Close and remove the Unix socket.
9. Release the process lock.
10. Exit.
```
A copy that cannot finish before the systemd timeout should remain recoverable from its temporary destination and durable job state.

#### 16. Implement the CLI Client

The CLI performs:
```
parse arguments
load socket location
connect
send request
receive response
render response
exit
```
Example:
```python
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
    client.settimeout(30.0)
    client.connect("/run/swit-file-mover/control.sock")
    send_message(client, request)
    response = receive_message(client)
```
The CLI must not start transfer workers or open the database for normal commands.

#### 17. Provide a Health Command

Add:
```shell
file-mover health
```
The service response should include:
```
service state
service start time
database available
worker pool state
active jobs
queued jobs
failed-retained jobs
source mount visible
destination mount visible
free destination space
protocol version
application version
```
Example:
```json
{
  "success": true,
  "result": {
    "service_state": "READY",
    "database": "AVAILABLE",
    "active_jobs": 1,
    "queued_jobs": 2,
    "source_mount_available": true,
    "destination_mount_available": true
  }
}
```

#### 18. Create the systemd Unit

Example:
```
[Unit]
Description=Background File Mover
After=network-online.target remote-fs.target
Wants=network-online.target remote-fs.target
RequiresMountsFor=/swit/recordings /data-processing/incoming
ConditionPathExists=/etc/file-mover/file-mover.ini

[Service]
Type=notify
User=mover
Group=mover

ExecStart=/usr/bin/python3.10 -m file_mover \
    --config /etc/file-mover/file-mover.ini \
    service run

ExecReload=/bin/kill -HUP $MAINPID

Restart=on-failure
RestartSec=10

RuntimeDirectory=file-mover
RuntimeDirectoryMode=0750

StateDirectory=file-mover
StateDirectoryMode=0750

LogsDirectory=file-mover
LogsDirectoryMode=0750

UMask=0007

TimeoutStartSec=120
TimeoutStopSec=90
KillSignal=SIGTERM
SendSIGKILL=yes

NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictRealtime=yes
LockPersonality=yes
MemoryDenyWriteExecute=yes

ReadWritePaths=/var/lib/file-mover
ReadWritePaths=/var/log/file-mover
ReadWritePaths=/swit/recordings
ReadWritePaths=/data-processing/incoming

[Install]
WantedBy=multi-user.target
```
`Type=notify` requires sending readiness notifications to systemd. Without implementing that, start with:
```
Type=simple
```
For the first release, `Type=simple` is easier:
```
[Service]
Type=simple
```
Then systemd considers the process started once `ExecStart` is running. The application logs when it reaches `READY`.

#### 19. Install the Application

Assuming the package is staged under `/opt`:
```
/opt/file-mover/
├── bin/
├── lib/
└── src/
```
A simple internal deployment might use:
```shell
sudo install -d -o root -g root -m 0755 /opt/file-mover
sudo cp -R dist/file_mover /opt/file-mover/
```
Then adjust `ExecStart` appropriately.

A cleaner deployment is to build a Python wheel using development tooling and install it into a dedicated virtual environment, even though the application itself has no runtime dependencies:
```shell
sudo python3.10 -m venv /opt/file-mover/venv
sudo /opt/file-mover/venv/bin/pip install file_mover-0.1.0-py3-none-any.whl
```
Then:
```
ExecStart=/opt/file-mover/venv/bin/python \
    -m file_mover \
    --config /etc/file-mover/file-mover.ini \
    service run
```
Using a virtual environment isolates the application from system Python packages even though the program uses only the standard library.

#### 20. Install and Start the Unit
```shell
sudo cp packaging/systemd/background-file-mover.service \
    /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now background-file-mover
```
Check status:
```shell
sudo systemctl status background-file-mover
```
View logs:
```shell
sudo journalctl \
    --unit background-file-mover \
    --follow
```

#### 21. Verify the Socket
```shell
sudo ls -l /run/file-mover/control.sock
```
Expected shape:
```
srw-rw---- 1 mover mover ... control.sock
```
Test the service:
```shell
file-mover list --state active
```

#### 22. Test a Small Transfer First

Create a controlled test dataset:
```shell
mkdir -p /swit/recordings/test-run
printf 'test-data\n' > /swit/recordings/test-run/file-01.dat
```
Submit:
```shell
file-mover submit \
    --scenario-id TEST-001 \
    --source /swit/recordings/test-run \
    --destination /data-processing/incoming/TEST-001
```
Check status:
```shell
file-mover status <job-id>
```
Verify:

* Original source name was claimed quickly.
* Temporary destination name appeared.
* Final file appeared only after verification.
* Source file was deleted only after final publication.
* Manifest was written.
* SQLite contains the completed job.
* Service remained running.

#### 23. Test Restart Recovery

Use a moderately large test file:
```shell
dd if=/dev/urandom \
   of=/swit/recordings/test-recovery/large.dat \
   bs=1M \
   count=4096
```
Submit it, then restart the service during transfer:
```shell
sudo systemctl restart background-file-mover
```
After restart, verify:

* The job remains known.
* The source remains claimed.
* The partial destination is reconciled.
* Transfer restarts or resumes according to policy.
* No final destination is exposed prematurely.
* Source is not lost.
* No duplicate job is created.

#### 24. Validate Idempotent Submission

Submit a request with a fixed request ID, then intentionally simulate a lost CLI response.

Retry the same request ID.

Expected result:

```
same request ID
    → same job ID
    → no duplicate claiming
    → original response returned
```
This is essential because a client can disconnect after the service committed the job but before receiving the acknowledgment.

_(§ "Recommended Initial Build Order" retired — see the retirement ledger at the top of
this file. Fully transcribed into `docs/ROADMAP.md`.)_
