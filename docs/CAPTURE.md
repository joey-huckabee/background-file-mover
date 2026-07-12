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
| Duplicate and Collision Handling | MIGRATED + TRANSCRIBED | Compare-and-reuse-or-collide + never-silent-replace → L2-DST-001..003 + `ExistingDestinationPolicy` (`fail`, `verify-and-reuse`) + `JobState.MANUAL_INTERVENTION`. `overwrite` deliberately excluded (enum docstring). `version` policy (unbuilt) **migrated** to ROADMAP § Deferred | _this commit_ |

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
Six hosts may contribute files, but copying all files concurrently may overload:

* The source NFS mount
* The destination NFS mount
* The network
* Storage controllers
* Simulation host I/O

Concurrency should therefore be configurable.

Example:
```
[transfer]
max_concurrent_jobs = 1
max_concurrent_files = 2
copy_buffer_size_bytes = 8388608
```
I recommend beginning with:
```
One active job
Two concurrently copied files
8 MiB copy buffer
```
These should be tuned through measurement.

The service should also support a configurable throughput limit later, but implementing a dependable bandwidth limiter is not necessarily required for the first release.

## Proposed Application Components
```
background-file-mover/
├── pyproject.toml
├── README.md
├── LICENSE
├── config/
│   └── file-mover.ini
├── docs/
│   ├── architecture.md
│   ├── operations.md
│   ├── recovery.md
│   ├── requirements/
│   │   ├── l1-system-requirements.md
│   │   ├── l2-software-requirements.md
│   │   └── l3-component-requirements.md
│   └── diagrams/
├── packaging/
│   └── systemd/
│       └── background-file-mover.service
├── file_mover/
│   ├── __init__.py
│   ├── __main__.py
│   ├── application.py
│   ├── cli.py
│   ├── configuration.py
│   ├── constants.py
│   ├── exceptions.py
│   ├── logging_config.py
│   ├── models.py
│   ├── service.py
│   ├── submission.py
│   ├── validation.py
│   ├── claiming.py
│   ├── transfer.py
│   ├── integrity.py
│   ├── manifests.py
│   ├── recovery.py
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── job_repository.py
│   │   └── sqlite_job_repository.py
│   └── interfaces/
│       ├── __init__.py
│       ├── clock.py
│       ├── file_system.py
│       └── job_store.py
└── tests/
    ├── unit/
    ├── integration/
    ├── system/
    ├── fault_injection/
    └── fixtures/
```
#### Principal Classes
```
FileMoverApplication
BackgroundMoverService
JobSubmissionService
SourceValidator
FileClaimManager
TransferCoordinator
FileTransferWorker
IntegrityVerifier
ManifestWriter
RecoveryManager
SQLiteJobRepository
ApplicationConfiguration
```
Class-based does not mean every small function should become a class. Pure helper functions remain appropriate when they have no state or lifecycle. The primary behavior and dependency boundaries should be class-oriented.

## Proposed CLI
```shell
# Start the service in the foreground; systemd normally invokes this
file-mover service run

# Submit a directory
file-mover submit \
    --scenario-id FLT-2026-0710-001 \
    --source /recordings/scenario-001 \
    --destination /processing/scenario-001

# Submit an explicit list
file-mover submit \
    --scenario-id FLT-2026-0710-001 \
    --file-list /path/to/files.txt \
    --destination /processing/scenario-001

# Show one job
file-mover status 8f6e4ad6-64f0-4ccd-bf71-92d96ef6190a

# List active jobs
file-mover list --state active

# Retry a retained failed job
file-mover retry 8f6e4ad6-64f0-4ccd-bf71-92d96ef6190a

# Validate configuration and filesystem access
file-mover doctor

# Reconcile state following an unexpected interruption
file-mover recover
```
The orchestration Python code could invoke the CLI:
```python
import subprocess
from pathlib import Path


def submit_recordings(
    scenario_id: str,
    source: Path,
    destination: Path,
) -> None:
    """Submit a completed recording set to the background mover."""
    result = subprocess.run(
        [
            "/usr/bin/file-mover",
            "submit",
            "--scenario-id",
            scenario_id,
            "--source",
            str(source),
            "--destination",
            str(destination),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"File mover rejected scenario {scenario_id}: "
            f"{result.stderr.strip()}"
        )
```
The submit command should return success only after the job and claimed file inventory have been durably recorded.

## Configuration
Use `configparser`, which is included in Python.
```
[service]
state_directory = /var/lib/file-mover
runtime_directory = /run/file-mover
log_directory = /var/log/file-mover
poll_interval_seconds = 2
shutdown_timeout_seconds = 60

[paths]
allowed_source_roots = /recordings
allowed_destination_roots = /processing
claim_directory_name = .moving
partial_file_prefix = .partial-

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
manifest_filename = transfer-manifest.json

[validation]
stability_check_enabled = true
stability_interval_seconds = 5
allow_symbolic_links = false
allow_destination_overwrite = false
minimum_free_space_margin_bytes = 10737418240

[logging]
level = INFO
format = json
```
No runtime package outside Python is necessary.

## “Production Ready, No Panic”
For Python, “no panic” should mean:

* No expected operational exception terminates the service.
* One failed file does not crash the worker manager.
* One failed job does not terminate the service.
* Every exception is translated into a defined job or file state.
* Unhandled top-level exceptions are logged with context.
* The service starts recovery after restart.
* Shutdown signals are handled.
* In-progress data remains recoverable.
* Retries are bounded and use exponential backoff.
* Permanent errors are distinguished from transient errors.
* Disk-full conditions retain the source.
* Permission errors retain the source.
* Network and NFS interruptions retain the source.
* Database transactions are rolled back safely.
* Temporary files are never presented as complete recordings.
* Source deletion is the last destructive operation.

Some exceptional conditions should deliberately stop startup rather than allowing unsafe operation, including:

* Corrupt state database that cannot be recovered
* Invalid configuration
* State directory not writable
* Source and destination policy conflicts
* Another active service instance holding the process lock

That is not a panic; it is a controlled fail-safe startup refusal.

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

## My Prompt:
I have a separate application called "file-handler" which has a lot of good functionality in it which has been developed over the years and has (supposedly) been maximized for file copy performance. Ignore the SMB and S3 portions of the code and yes I understand there are external dependencies in this code, we will not be using this code in our new project here but there is a lot of good functions and exception handling and I would like you to at least take a look and possibly leverage some of what we have:

## Chat Reply:
This first set already shows several ideas worth carrying forward, but the new mover should not reproduce the `FileHandler` abstraction directly. The existing class is designed as a synchronous, in-process façade around storage back ends; `Background File Mover` needs durable jobs, restart recovery, explicit state transitions, and conservative deletion rules.

## What We Should Reuse Conceptually
#### Centralized operation lifecycle
The event flow is useful:
```
operation start
operation progress
operation complete
```
For the new project, this should become a durable lifecycle rather than only an in-memory event system:
```
job submitted
job validated
files claimed
manifest created
file copy started
file copy retried
file copied
file verified
file published
source deleted
job completed
```
These events should update:

* The SQLite job database
* Structured application logs
* In-memory operational counters
* Potentially a human-readable job event log

The existing callbacks demonstrate good separation between file operations and operation reporting. We should retain that separation, but use typed event objects instead of loosely structured arguments and dictionaries.

For example:
```python
@dataclass(frozen=True)
class TransferEvent:
    """Describe a state change during a file transfer."""

    job_id: str
    event_type: TransferEventType
    timestamp: datetime
    source_path: Path | None = None
    destination_path: Path | None = None
    attempt_number: int = 1
    bytes_processed: int = 0
    error_type: str | None = None
    error_message: str | None = None
```
That is safer than:
```python
details: Optional[Dict[str, Any]]
**kwargs: Any
```

## Retry progress reporting
This is useful:
```python
if status == "warning_retrying" and details:
    attempt = details.get("attempt_number", "?")
    wait = details.get("wait_time", "?")
```
The new mover should report retry attempts, delays, and causes. It should also distinguish retryable and non-retryable failures.

Examples:
| Condition                           | Classification                        |
| ----------------------------------- | ------------------------------------- |
| Temporary NFS unavailability        | Retryable                             |
| `ESTALE` stale NFS handle           | Retryable after reopening             |
| Temporary I/O failure               | Usually retryable                     |
| Destination temporarily unavailable | Retryable                             |
| Destination out of space            | Retryable only after operator action  |
| Permission denied                   | Normally permanent                    |
| Invalid source path                 | Permanent                             |
| Source changes after claiming       | Integrity failure                     |
| Destination hash mismatch           | Integrity failure requiring retention |
| Destination filename collision      | Policy failure                        |

Rather than testing arbitrary exception classes at each call site, the project should have an error classifier:
```python
class ErrorDisposition(Enum):
    """Describe how an operational error should be handled."""

    RETRY = auto()
    RETAIN_AND_FAIL = auto()
    REJECT_JOB = auto()
    SERVICE_FATAL = auto()
```

## Externally supplied logger
This is a good practice:
```python
logger: Optional[logging.Logger] = None
```
Classes in the new project should accept a logger or call:
```python
logging.getLogger(__name__)
```
However, individual business classes should not configure handlers. Logger configuration should happen once at the application boundary.

Recommended separation:
```
cli.py / service.py
    configures logging

transfer.py
    obtains or receives logger
    emits records

repository.py
    obtains or receives logger
    emits records
```

## Explicit precondition handling
The existing methods recognize that setup failures are different from file-operation failures:
```python
except (ValueError, ConnectionError, ImportError, FileNotFoundError) as err:
```
That distinction should remain. In the new system, we should define a typed exception hierarchy:
```
FileMoverError
├── ConfigurationError
├── SubmissionError
│   ├── InvalidSourceError
│   ├── InvalidDestinationError
│   ├── SourceNotStableError
│   └── DuplicateSubmissionError
├── ClaimError
├── ManifestError
├── TransferError
│   ├── CopyError
│   ├── DestinationWriteError
│   └── DestinationPublishError
├── IntegrityError
│   ├── SizeMismatchError
│   ├── HashMismatchError
│   └── SourceChangedError
├── RepositoryError
└── RecoveryError
```
The service can then convert these exceptions into well-defined states instead of terminating.

## Operation and cumulative statistics
The existing statistics are helpful operationally:
```python
"total_files_copied"
"total_files_moved"
"total_files_deleted"
"total_file_op_errors"
```
The new project should expand this into more meaningful transfer metrics:
```
jobs_submitted
jobs_completed
jobs_failed_retained
jobs_waiting_retry
files_claimed
files_copied
files_verified
files_published
source_files_deleted
copy_retries
bytes_copied
hash_bytes_read
integrity_failures
destination_collisions
recovery_actions
```
These should not exist only in a process-local dictionary because they disappear after restart. Current-run counters can remain in memory, but authoritative job statistics should come from the SQLite repository.

## Subscription cleanup
The use of `finally` to unsubscribe is correct in principle:
```python
finally:
    if src_dir:
        self._unsubscribe(src_dir)
```
This shows attention to lifecycle cleanup. The new project should consistently use:

* Context managers
* try/finally
* Explicit resource ownership
* Deterministic database transaction boundaries
* Deterministic file descriptor closure
* Graceful executor shutdown

## What We Should Not Carry Forward
#### 1. A single high-level FileHandler façade

This class owns too many responsibilities:
* Logger setup
* Event subscription
* Statistics
* Directory creation
* Copy orchestration
* Move orchestration
* Scanning
* Error translation

For the new application, these should be separate:
```
JobSubmissionService
SourceClaimService
TransferCoordinator
FileCopier
IntegrityVerifier
ManifestRepository
JobRepository
RecoveryService
TransferEventPublisher
```
This avoids creating another “god class.”

#### 2. In-memory operation state as the authoritative record
These members are unsuitable for durable processing:
```python
self.current_operation_logs
self.current_operation_stats
self.last_operation_errors
self.cumulative_stats
```
They are useful for a synchronous library call but insufficient for a background service. If the process exits, all state disappears.

For `Background File Mover`, durable state must be written before acknowledgment and at every important transition.

#### 3. Returning exceptions as data
The current API returns:
```python
Tuple[int, List[Tuple[str, Exception]]]
```
That creates several problems:

* Exception instances are not durable or easily serializable.
* Callers must interpret arbitrary exception objects.
* The result does not express partial states clearly.
* It does not identify which operation stages succeeded.
* It encourages the caller to infer overall status from counts.

The new project should return typed result objects:

```python
@dataclass(frozen=True)
class SubmissionResult:
    """Represent the outcome of submitting a transfer job."""

    accepted: bool
    job_id: str | None
    state: JobState
    claimed_file_count: int
    claimed_bytes: int
    error_code: str | None = None
    error_message: str | None = None
```
Internally, errors should be persisted in a serializable format:
```
error_code
exception_type
message
errno
operation
source_path
destination_path
attempt_number
occurred_at
traceback
```
Tracebacks should be logged, but the normal CLI response should remain concise.

#### 4. Broad mutable dictionaries and Any
These types weaken the implementation:
```python
Dict[str, Any]
Directory[Any]
**kwargs: Any
```
For a production transfer system, critical data should use:

* `dataclasses`
* `Enum`
* `Path`
* Narrow protocols
* Explicit return types
* Immutable event and request objects where practical

Configuration can be represented with frozen dataclasses:
```python
@dataclass(frozen=True)
class IntegrityConfiguration:
    """Configure file integrity verification."""

    enabled: bool
    algorithm: HashAlgorithm
    precompute_source_hash: bool
    verify_destination_hash: bool
    buffer_size_bytes: int
```

#### 5. Logger configuration inside every instance
This code may create many separately named loggers:
```python
logging.getLogger(
    f"{self.__class__.__name__}_{uuid.uuid4().hex[:6]}"
)
```
That makes centralized filtering and correlation harder. Random logger names also do not replace job correlation.

Instead:
```python
logger = logging.getLogger("file_mover.transfer")
```
and include the job information in structured fields:
```python
logger.info(
    "File copy started",
    extra={
        "job_id": job.job_id,
        "file_id": file_record.file_id,
        "source_path": str(file_record.source_path),
    },
)
```
The job ID should identify the operation, not the logger name.

#### 6. `load_dotenv()` inside a business object
This will not be carried forward:
```python
load_dotenv(override=True)
```
Reasons:

* It is an external runtime dependency.
* Configuration loading should occur once at startup.
* `override=True` can silently replace environment configuration.
* Instantiating a file operation class should not alter process configuration.

We will use `configparser` and explicit configuration injection.

#### 7. Catching only selected setup exceptions and converting everything to a count
The existing code catches:
```python
(ValueError, ConnectionError, ImportError, FileNotFoundError)
```
This is too narrow in some ways and too broad in others.

For filesystem operations, relevant failures include:

* `PermissionError`
* `TimeoutError`
* `NotADirectoryError`
* `IsADirectoryError`
* `OSError` with meaningful `errno`
* SQLite failures
* Serialization failures
* Invalid state transitions

We should not merely add more exceptions to one large tuple. Each layer should catch only errors it can interpret, add context, and re-raise a project-specific exception.

Example:
```python
try:
    os.replace(source_path, claimed_path)
except OSError as error:
    raise FileClaimError(
        job_id=job_id,
        source_path=source_path,
        claimed_path=claimed_path,
        errno_value=error.errno,
    ) from error
```
The coordinator then determines whether the job is retryable or retained for intervention.

## Specific Issues in the Current Code
These are useful lessons for the new project.

#### Statistics keys appear inconsistent
Progress records failure under:

```python
self.current_operation_stats["file_op_errors"]
```
But completion aggregates:
```python
stats.get("copy_errors", 0)
stats.get("delete_errors", 0)
```
As shown, failures may not be reflected in cumulative totals.

That is exactly the type of problem enums and typed counters prevent.

#### Move count may not actually mean completed moves
For move operations:
```python
self.cumulative_stats["total_files_moved"] += stats.get(
    "files_copied_successfully", 0
)
```
A file might have copied successfully but failed source deletion. Such a file was not fully moved.

The new mover must distinguish:
```
COPIED
VERIFIED
PUBLISHED
SOURCE_DELETED
MOVE_COMPLETE
```
A file should count as moved only after the final required state.

#### Multiple locks are acquired for one event update
The method repeatedly enters:

```python
with self._lock:
```
This is not necessarily incorrect, but the event update is not treated as a single coherent atomic operation.

For the new service, related counters and state changes should be performed together where consistency matters.

#### Returned collections expose internal mutable state
These methods return the internal objects directly:
```python
return self.current_operation_logs
return self.current_operation_stats
return self.cumulative_stats
```
A caller can mutate them.

Safer approaches include:
```python
return tuple(self.current_operation_logs)
return self.current_operation_stats.copy()
```
For the new project, immutable snapshots are preferable.

#### The scan callback has a local typing inconsistency
The declared list is:
```python
scanned: List[str] = []
```
But this can append a non-string:
```python
scanned.append(file_src)
```
because `file_src` is typed as:
```python
str | Any
```
This illustrates why `Any` should be minimized.

#### `scan()` appears to generate duplicate lifecycle events
It subscribes to directory lifecycle events and then manually calls:
```python
self._on_operation_start(...)
```
and:
```python
self._on_operation_complete(...)
```
Depending on what `directory.scan()` emits, this could duplicate start or completion handling.

In the new design, ownership of state transitions must be explicit: one component is responsible for emitting each transition.

#### Error details are logged without guaranteed traceback context
This:
```python
self.logger.error(
    "  - Context '%s': %s(%s)",
    tag,
    type(exc).__name__,
    exc,
)
```
records the exception type and message but not necessarily the stack trace.

For unexpected failures, the new application should use:
```python
logger.exception(...)
```
inside an active exception handler, or explicitly store formatted traceback details.

Routine expected failures should not flood logs with unnecessary tracebacks, so we will distinguish expected operational failures from software defects.

## How This Influences the New Architecture
Based on these first files, I would add the following components to our design:
```
TransferEvent
    Typed immutable description of operational progress

TransferEventRecorder
    Persists events and writes structured logs

TransferStatistics
    Typed counters for service-runtime statistics

ErrorClassifier
    Determines retry, retention, rejection, or fatal behavior

TransferResult
    Typed outcome rather than tuples of exception objects

ApplicationLogging
    One centralized logging configuration

OperationContext
    Carries job ID, file ID, attempt, source, and destination
```
The flow becomes:
```
TransferCoordinator
    │
    ├── updates JobRepository
    ├── performs work through FileCopier / IntegrityVerifier
    └── publishes typed TransferEvent objects
             │
             ├── structured log
             ├── durable event table
             └── runtime statistics
```
#### Preliminary Decision Record
From this review, I would record these design decisions:
| Decision             | New-project approach                                       |
| -------------------- | ---------------------------------------------------------- |
| Runtime dependencies | Python 3.10 standard library only                          |
| Configuration        | `configparser`, loaded once                                |
| Logging              | Centralized standard-library logging                       |
| Events               | Typed dataclass events                                     |
| State                | SQLite, not process memory                                 |
| Errors               | Project exception hierarchy plus error classification      |
| Results              | Typed result dataclasses                                   |
| Metrics              | Typed counters plus durable repository queries             |
| Correlation          | Job and file IDs, not randomized logger names              |
| Move completion      | Counted only after verified publication and source cleanup |
| Callbacks            | Optional internal observers; never authoritative state     |

The `handler.py` file is useful mainly as an operational-pattern reference: lifecycle callbacks, retry visibility, centralized reporting, and statistics. Its synchronous façade, mutable state, loose event payloads, and exception-return model should not form the foundation of the new durable mover.

Send the next files that contain the actual local filesystem directory implementation, copy loop, retry logic, buffering, or move/delete behavior. Those are likely to contain the performance and failure-handling details most relevant to this project.

## My Prompt:
file_handler/event.py

## Chat Reply:
These files reinforce two useful ideas—strict configuration validation and decoupled event reporting—but both need to be reshaped for a durable, multithreaded background service.

## `event.py` Review
#### What Is Worth Keeping
The publisher/subscriber pattern is useful because the transfer engine should not directly own every secondary concern.

For example, a copy worker can emit:
```
FILE_COPY_STARTED
FILE_COPY_PROGRESS
FILE_COPY_RETRY
FILE_COPY_COMPLETED
FILE_VERIFICATION_FAILED
```
Separate subscribers could then:

* Write structured logs
* Update runtime counters
* Persist an audit event
* Report progress to a CLI status command

This keeps the actual file-copy logic focused.

## Problems With the Current Event Class
#### 1. It is not thread-safe
The new mover will probably use multiple worker threads. These operations are unsafe if they happen concurrently:

```python
self._subs.append(func)
self._subs.remove(func)

for func in self._subs:
    func(...)
```
A subscriber could be added or removed while emit() is iterating.

A lock or immutable subscriber snapshot would be needed:
```python
with self._lock:
    subscribers = tuple(self._subscribers)

for subscriber in subscribers:
    subscriber(event)
```
The lock should not remain held while subscriber code runs because a slow or recursive subscriber could block the event system.

#### 2. One subscriber failure stops later subscribers
Currently:

```python
for func in self._subs:
    func(*args, **kwargs)
```
If the first callback raises an exception, remaining subscribers never receive the event.

That is dangerous for the mover. A statistics callback failure must not prevent the audit recorder from receiving the event, and no callback failure should interrupt the file transfer itself.

The event publisher should isolate subscribers:

```python
for subscriber in subscribers:
    try:
        subscriber(event)
    except Exception:
        logger.exception(
            "Transfer event subscriber failed",
            extra={"subscriber": repr(subscriber)},
        )
```
However, durable state changes should not depend exclusively on best-effort event subscribers. The transfer coordinator must update SQLite directly before emitting informational events.

#### 3. `Callable[..., Any]` and arbitrary arguments are too loose
This provides no enforceable event contract:
```python
list[Callable[..., Any]]
```
The mismatch seen earlier between callback signatures is a consequence of this design.

The new application should use one typed event object:
```python
from collections.abc import Callable

TransferEventSubscriber = Callable[["TransferEvent"], None]
```
Then:
```python
class EventPublisher:
    """Publish typed transfer events to registered subscribers."""

    def subscribe(self, subscriber: TransferEventSubscriber) -> None:
        ...

    def emit(self, event: TransferEvent) -> None:
        ...
```
A subscriber cannot accidentally expect `file_src` while the publisher supplies `file_path`.

#### 4. Silent unsubscribe failures can hide lifecycle defects
This code:
```python
except ValueError:
    pass
```
may be acceptable for idempotent cleanup, but silently ignoring it can obscure a programming mistake.

For the new application, `unsubscribe()` could return a Boolean:
```python
removed = publisher.unsubscribe(callback)
```
or log at debug level when the subscriber was not registered.

#### 5. Bound methods have lifecycle concerns
Subscribing an instance method retains a strong reference to the instance. A long-running service can accidentally retain objects indefinitely if they are not unsubscribed.

For this project, the event subscriber set should be stable and established during application startup. We should avoid dynamically subscribing per transfer job wherever possible.

## Recommended Event Role
Events should be **observational**, not transactional.

Bad design:
```
copy succeeds
    → event subscriber updates database
```
If the subscriber fails, durable state becomes incorrect.

Recommended design:

```
copy succeeds
    → coordinator transactionally updates database
    → coordinator emits FILE_COPIED event
```
The database is authoritative. Events provide visibility.

## `config_models.py` Review
The strongest lesson here is the use of explicit configuration models and rejection of unknown fields:

```python
extra = "forbid"
```
That behavior is absolutely appropriate for `Background File Mover`.

A misspelled production option must not be silently ignored.

For example:
```
[integrity]
enable = true
```
should fail if the actual option is:
```
enabled = true
```
Silent fallback could cause hashing to be unexpectedly disabled.

Because the new application cannot use Pydantic at runtime, we will implement equivalent validation using frozen dataclasses and explicit parsing.

## Configuration Structure for the New Project
A likely model hierarchy is:

```python
@dataclass(frozen=True)
class ServiceConfig:
    """Configure background service operation."""

    state_directory: Path
    runtime_directory: Path
    poll_interval_seconds: float
    graceful_shutdown_seconds: float


@dataclass(frozen=True)
class PathPolicyConfig:
    """Configure permitted source and destination paths."""

    allowed_source_roots: tuple[Path, ...]
    allowed_destination_roots: tuple[Path, ...]
    claim_directory_name: str
    partial_file_prefix: str
    skip_symbolic_links: bool


@dataclass(frozen=True)
class TransferConfig:
    """Configure file transfer behavior."""

    max_concurrent_jobs: int
    max_concurrent_files: int
    buffer_size_bytes: int
    retry_limit: int
    retry_initial_delay_seconds: float
    retry_max_delay_seconds: float


@dataclass(frozen=True)
class IntegrityConfig:
    """Configure transfer integrity validation."""

    enabled: bool
    algorithm: HashAlgorithm
    mode: IntegrityMode
    buffer_size_bytes: int


@dataclass(frozen=True)
class StabilityConfig:
    """Configure source-file stability validation."""

    enabled: bool
    poll_count: int
    poll_interval_seconds: float


@dataclass(frozen=True)
class ApplicationConfig:
    """Contain complete validated application configuration."""

    service: ServiceConfig
    paths: PathPolicyConfig
    transfer: TransferConfig
    integrity: IntegrityConfig
    stability: StabilityConfig
```
The parser should be separate:
```python
class ConfigurationLoader:
    """Load and validate application configuration."""

    def load(self, path: Path) -> ApplicationConfig:
        ...
```
This separates:
```
raw INI parsing
        ↓
type conversion
        ↓
semantic validation
        ↓
immutable runtime configuration
```

## Useful Existing Configuration Fields
Several fields in `BaseDirectoryConfig` apply directly to our mover.

#### Filename filtering
```python
filename_filter_regex: Optional[str]
```
This may be useful, but it should not be the primary way orchestration identifies recordings.

For safety, submission should preferably provide:

* A job-specific directory
* An explicit list of files
* A manifest generated by the orchestration system

A regex scan can accidentally claim unrelated files.

If regex filtering is supported, it should be:

* Optional
* Anchored against relative paths
* Compiled and validated during startup
* Recorded in the submitted job
* Applied before claiming anything

I would defer regex-driven submission unless the current orchestration needs it.

#### Symlink policy
```python
skip_symlinks: bool = False
```
For the new mover, the safe default should be the opposite:
```
skip_symbolic_links = true
```
Or, more strictly:
```
reject_symbolic_links = true
```
Following symbolic links creates risks:

* A link could escape the approved recording root.
* The target could change between validation and copy.
* Multiple links could reference the same file.
* A link could point onto the destination filesystem.
* Recursive directory links could create cycles.

For the initial release, I recommend rejecting symbolic links entirely.

#### Minimum and maximum file size
```python
min_file_size
max_file_size
```
These can be useful as submission policies, but we should distinguish:

* A zero-byte file that is legitimate
* A zero-byte file indicating a failed recorder
* A file larger than operational expectations
* A hard technical limit

Recommended configuration:

```
[validation]
allow_empty_files = false
maximum_file_size_bytes = 0
maximum_job_size_bytes = 0
```
A value of zero could mean “no configured maximum.”

These conditions should reject a job before claiming unless a project-specific policy says otherwise.

#### Stability checks
These are particularly relevant:
```python
stability_time
stability_polls
stability_poll_interval
```
The current names and meanings overlap somewhat. For the new project, I would simplify them to:
```
[stability]
enabled = true
poll_count = 2
poll_interval_seconds = 5.0
compare_size = true
compare_mtime = true
```
The implementation would collect a fingerprint:
```python
@dataclass(frozen=True)
class FileObservation:
    """Record metadata used to determine whether a file is stable."""

    size_bytes: int
    modified_time_ns: int
    device_id: int
    inode: int
```
A file is stable only if all configured observations match.

Checking inode and device helps detect replacement of the path between polls.

#### Important limitation

A stability poll does not prove the writer has closed the file. A process could pause longer than the polling window and resume later.

Therefore, our requirements should explicitly state:

> Stability validation is a defensive check and shall not replace the orchestration system's responsibility to submit only completed recordings.

## What We Should Not Copy From the Pydantic Models

#### 1. Configuration objects should not resolve external state during validation

The current models call:
```python
os.getenv(...)
```
inside model validators.

For our project, configuration construction should be deterministic. Parsing an INI file should not quietly inspect unrelated process state unless a configuration option explicitly requests environment expansion.

Since this system has no credentials requirement, we probably do not need environment-derived fields at all.

#### 2. Models should not mutate themselves during validation
The Pydantic models populate fields such as:

```python
self.bucket_name = ...
self.prefix = ...
```
For our frozen standard-library dataclasses, derived values should be computed before object construction or returned by dedicated parsing functions.

This produces easier reasoning and testing.

#### 3. `Optional` should not be used where there is a real default
Several fields are optional even though the application likely expects a defined value:

```python
stability_time: Optional[float] = None
min_file_size: Optional[int] = None
```
In the new project:

* Truly optional values may use `None`.
* Enabled features should have complete validated configuration.
* Disabled features should not require placeholder values.
* Defaults should be explicit and documented.

#### 4. Avoid unconstrained `str` for finite choices
The existing discriminator is good:
```python
Literal["local"]
Literal["s3"]
Literal["smb"]
```
For the new project, finite operational choices should use enums:
```python
class HashAlgorithm(str, Enum):
    """Supported file hashing algorithms."""

    SHA256 = "sha256"
    SHA512 = "sha512"
    BLAKE2B = "blake2b"


class IntegrityMode(str, Enum):
    """Supported integrity-verification workflows."""

    METADATA = "metadata"
    SOURCE_HASH = "source-hash"
    SOURCE_AND_DESTINATION_HASH = "source-and-destination-hash"
```
Likewise:
```python
class ExistingDestinationPolicy(str, Enum):
    FAIL = "fail"
    VERIFY_AND_REUSE = "verify-and-reuse"
```

#### Strict Unknown-Option Validation
`configparser` does not reject unknown fields automatically. We should add that behavior deliberately.

Conceptually:
```python
_ALLOWED_OPTIONS = {
    "service": {
        "state_directory",
        "runtime_directory",
        "poll_interval_seconds",
        "graceful_shutdown_seconds",
    },
    "transfer": {
        "max_concurrent_jobs",
        "max_concurrent_files",
        "buffer_size_bytes",
        "retry_limit",
        "retry_initial_delay_seconds",
        "retry_max_delay_seconds",
    },
}
```
Then reject:

* Unknown sections
* Unknown keys
* Duplicate sections
* Missing required sections
* Missing required keys
* Invalid booleans
* Invalid numeric ranges
* Invalid enum values

This preserves the best aspect of:
```python
extra = "forbid"
```
without adding a runtime dependency.

#### Validation Rules We Should Add
The current models primarily validate shape and path syntax. Our mover requires stronger cross-field validation.

Examples:
```
max_concurrent_jobs >= 1
max_concurrent_files >= 1
buffer_size_bytes >= 64 KiB
retry_limit >= 0
retry_initial_delay_seconds > 0
retry_max_delay_seconds >= retry_initial_delay_seconds
stability poll_count >= 2
stability poll_interval_seconds > 0
claim directory name contains no path separators
partial prefix is nonempty
state directory is not inside an allowed source recording directory
source and destination roots do not overlap
source and destination roots are absolute
hash algorithm is supported by hashlib
destination-overwrite policy is never implicit
```
Some checks happen during configuration loading. Others require filesystem access and belong in the `doctor` command or service startup validation.

## Requirements Suggested by These Files
I would add the following requirements to our working set.

#### L2 Configuration Requirements
##### L2-CFG-001

The software shall load runtime configuration using only Python standard-library functionality.

##### L2-CFG-002

The software shall reject unrecognized configuration sections and options.

##### L2-CFG-003

The software shall reject missing required configuration values.

##### L2-CFG-004

The software shall validate numeric ranges and cross-field constraints before starting the service.

##### L2-CFG-005

The software shall represent validated runtime configuration using immutable typed objects.

##### L2-CFG-006

The software shall not begin processing transfer jobs when configuration validation fails.

##### L2-CFG-007

The software shall provide a command that validates configuration without starting the transfer service.

#### L2 Event Requirements
##### L2-EVT-001

The software shall represent operational events using typed immutable event records.

##### L2-EVT-002

The software shall isolate event-subscriber failures so one subscriber cannot prevent delivery to other subscribers.

##### L2-EVT-003

The software shall not rely on event subscribers to perform authoritative job-state transitions.

##### L2-EVT-004

The event publisher shall support concurrent event emission safely.

##### L2-EVT-005

Each transfer event shall include a job identifier and, when applicable, a file identifier.

#### L3 Event Component Requirements
##### L3-EVT-001.1

The `TransferEventPublisher` shall take a snapshot of registered subscribers before invoking callbacks.

##### L3-EVT-001.2

The `TransferEventPublisher` shall not hold its subscriber lock while invoking callbacks.

##### L3-EVT-001.3

The `TransferEventPublisher` shall catch and log subscriber exceptions without propagating them into the transfer coordinator.

##### L3-EVT-001.4

The `TransferEventPublisher` shall reject duplicate subscriber registrations.

##### L3-EVT-001.5

The `TransferEventPublisher.unsubscribe()` method shall indicate whether a subscriber was removed.

## Updated Architectural Direction
The event functionality belongs in the project, but as a small supporting mechanism:
```
TransferCoordinator
      │
      ├── performs authoritative repository update
      │
      └── emits TransferEvent
                 │
                 ├── StructuredLogSubscriber
                 ├── RuntimeStatisticsSubscriber
                 └── OptionalAuditSubscriber
```
Configuration becomes:
```
ConfigurationLoader
      │
      ├── reads INI
      ├── rejects unknown fields
      ├── converts values
      ├── validates ranges and relationships
      └── returns frozen ApplicationConfig
```
The most useful details in this batch are the strict-extra-field policy, the stability-check configuration, and the separation between operation execution and event listeners. We should retain all three concepts, while replacing Pydantic and the untyped event implementation with standard-library, immutable, thread-safe equivalents.

## My Prompt:
file_handler/cli.py

## Chat Reply:
This CLI contains several useful structural patterns, but it also confirms that the new mover needs a different command model. `file-handler` performs a synchronous operation and waits for completion. `Background File Mover` must distinguish between:
```
submit a durable job
run the background service
inspect job state
retry or recover a job
validate the installation
```
The CLI should therefore act primarily as a control interface to the durable service rather than as the transfer engine itself.

## Useful Patterns to Retain
#### 1. Separate parser construction from execution
This is good:
```python
def create_parser() -> argparse.ArgumentParser:
```
It makes parser behavior easy to test without launching a subprocess.

The new project should keep:
```python
def create_parser() -> argparse.ArgumentParser:
    """Create and configure the command-line argument parser."""
```
and:
```python
def main(argv: Sequence[str] | None = None) -> int:
    """Execute the command-line interface."""
```
This allows tests such as:
```python
args = create_parser().parse_args(
    [
        "submit",
        "--scenario-id",
        "scenario-001",
        "--source",
        "/recordings/run-001",
        "--destination",
        "/processing/run-001",
    ]
)
```

#### 2. Handler functions per command
This is also a useful pattern:
```python
parser_scan.set_defaults(func=handle_scan)
parser_copy.set_defaults(func=handle_copy)
parser_move.set_defaults(func=handle_move)
```
For the new application, command handlers might be:
```
handle_submit
handle_status
handle_list
handle_retry
handle_cancel
handle_doctor
handle_recover
handle_service_run
```
Each command handler should remain thin. It should:

1. Convert parsed arguments into a typed request.
2. Call an application service.
3. Render the result.
4. Return an exit code.

It should not contain file-copy logic.

#### 3. Explicit exit codes
The current CLI returns integers consistently. We should retain that, but define named exit codes.

For example:
```python
class ExitCode(IntEnum):
    """Process exit codes returned by the command-line interface."""

    SUCCESS = 0
    OPERATION_FAILED = 1
    INVALID_ARGUMENT = 2
    CONFIGURATION_ERROR = 3
    SERVICE_UNAVAILABLE = 4
    JOB_REJECTED = 5
    JOB_NOT_FOUND = 6
    PARTIAL_SUCCESS = 7
    INTERNAL_ERROR = 10
```
This is better than treating every failure as `1`.

The simulation orchestration script can then distinguish:
```
job accepted
job rejected
service unavailable
invalid request
unexpected internal failure
```
That distinction matters operationally.

#### 4. Centralized top-level exception boundary
This pattern is appropriate:
```python
except Exception:
    logger.error(
        "An unexpected error occurred during the operation.",
        exc_info=True,
    )
```
There should be one broad exception boundary at the CLI entry point so an unexpected defect produces:

* A nonzero exit code
* A traceback in service logs
* A concise user-facing message
* No raw Python traceback printed by default to orchestration output

Broad exception handling is appropriate at application boundaries, but not throughout the core transfer implementation.

#### 5. `perf_counter()` for elapsed duration
This is correct for measuring operation duration:
```python
start_time = time.perf_counter()
```
The new application can use it for:

* Submission latency
* Source hashing duration
* Copy duration
* Verification duration
* Recovery duration

Durations should also be persisted for completed jobs.

## Problems We Should Avoid
#### 1. The CLI modifies configuration files in place
This is the most concerning behavior in this file:
```python
_apply_stability_time_to_yaml(...)
```
and:
```python
yaml_path.write_text(...)
```
A command-line override should never rewrite the underlying production configuration unless the user explicitly runs a configuration-edit command.

Problems include:

* The original setting is lost.
* Concurrent commands can race.
* File permissions or ownership may change.
* A partially written configuration can break later runs.
* A one-time override becomes permanent.
* The source and destination configurations are unexpectedly modified.
* Comments and formatting may be lost during serialization.

For the new mover:
```shell
file-mover submit --stability-interval 10
```
should apply only to that submitted job or invocation.

It should not edit:
```
/etc/file-mover/config.ini
```
Configuration precedence should be explicit:
```
compiled defaults
    <
configuration file
    <
approved CLI override
```
The resulting resolved settings should be stored in the job record so recovery uses the same values after restart.

#### 2. Configuration for source and destination should not be duplicated
The current design uses:
```
src.yaml
dest.yaml
```
For our application, both are normal POSIX paths on mounted filesystems. We do not need separate storage-backend configuration documents.

A submission request should contain:
```
For our application, both are normal POSIX paths on mounted filesystems. We do not need separate storage-backend configuration documents.

A submission request should contain:
```
System-level policy remains in the central configuration file.

#### 3. Verbosity meanings are inconsistent
The CLI help says:
```
1=errors, 2=info, 3=debug
```
but `FileHandler` says:
```
1 = warnings only, 2 = info, 3 = debug
```
Elsewhere `_setup_logging()` maps:
```python
{0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
```
although parser choices are `1`, `2`, and `3`.

That means:
```
verbosity 1 → INFO
verbosity 2 → DEBUG
verbosity 3 → DEBUG
```
This is inconsistent with the help text and handler behavior.

For the new CLI, use repeatable flags:
```shell
-v
-vv
```
with:
```
no -v  → WARNING
-v     → INFO
-vv    → DEBUG
```
Or use a clear explicit option:
```shell
--log-level INFO
```
I prefer supporting both globally:
```shell
file-mover --log-level INFO submit ...
```
The configuration file should define the service default. A foreground administrative command may override it.

#### 4. Logging should not normally go to stdout
This code uses:

```python
logging.StreamHandler(sys.stdout)
```

For command-line tools:

* Structured or requested command output belongs on stdout.
* Diagnostics and logging belong on stderr.

This matters because orchestration may parse command output.

Recommended behavior:

```
stdout:
{"accepted": true, "job_id": "...", "state": "CLAIMED"}

stderr:
warning and error messages
```
Human-readable output can remain the default, with optional JSON:
```shell
file-mover submit ... --output json
```
The result channel must remain clean enough for scripts.

#### 5. The CLI should not instantiate the entire transfer engine for every control command
This currently does:
```python
handler = FileHandler(...)
```
for every command, even for scan operations.

For the new project:

* `service run` builds the complete service runtime.
* `submit` builds only submission/control components.
* `status` builds only the read repository or control client.
* `doctor` builds validation components.
* `recover` invokes the recovery service.

We should use a small application factory rather than one universal handler object.

Example:

```python
class ApplicationFactory:
    """Create configured application services for CLI commands."""

    def create_submission_service(self) -> JobSubmissionService:
        ...

    def create_status_service(self) -> JobQueryService:
        ...

    def create_background_service(self) -> BackgroundMoverService:
        ...
```

#### 6. Broad result typing weakens the CLI contract
This signature is too loose:
```python
Callable[[], Tuple[Any, List[Tuple[str, Exception]]]]
```
The generic executor assumes all operations have roughly the same result structure, but scan, copy, and move do not actually return the same type of result.

For our CLI, each command should return its own typed model:
```python
SubmissionResult
JobStatusResult
RetryResult
DoctorResult
RecoveryResult
```
A small rendering layer can handle them through explicit formatters rather than `Any`.

#### 7. Cumulative in-memory stats are not useful for short-lived CLI calls
At the end:

```python
stats = handler.get_cumulative_stats()
```
Because the CLI process performs one operation and exits, these are essentially per-process statistics.

For the new system:

* The service maintains runtime counters.
* The SQLite database maintains job history.
* `status` shows one job.
* `list` shows job summaries.
* `stats` can query durable aggregate statistics.

A separate command may be useful:
```shell
file-mover stats
```
with output such as:
```
Jobs submitted:          84
Jobs completed:          81
Jobs failed-retained:     2
Jobs active:              1
Files completed:        972
Bytes moved:          8.14 TB
Integrity failures:       1
```

#### 8. The `__main__` behavior is dangerous
This code is clearly development residue:
```python
if __name__ == "__main__":
    sys.exit(main(["scan", "dest.yaml", "--verbosity=2", "--stability-time=0"]))
```
Running the module directly ignores actual command-line arguments and executes a hard-coded command.

For the new application:
```python
if __name__ == "__main__":
    raise SystemExit(main())
```
The package-level `__main__.py` should do the same.

A test should verify that no hard-coded development arguments exist.

## Recommended CLI Structure
```
file-mover
├── submit
├── status
├── list
├── retry
├── cancel
├── doctor
├── recover
├── stats
└── service
    └── run
```
#### `submit`
Submit a completed recording directory:
```shell
file-mover submit \
    --scenario-id SWIT-20260710-001 \
    --source /swit/recordings/run-001 \
    --destination /data-processing/incoming/run-001
```
Submit explicit files:
```shell
file-mover submit \
    --scenario-id SWIT-20260710-001 \
    --file-list /tmp/run-001-files.txt \
    --source-root /swit/recordings \
    --destination /data-processing/incoming/run-001
```
Possible job-specific overrides:
```shell
--integrity-mode source-and-destination-hash
--hash-algorithm sha256
--stability-check
--stability-polls 3
--stability-poll-interval 5
```
These overrides must be constrained by system policy. For example, if the service configuration requires hashing, a submitter should not be able to disable it.

#### `status`
```shell
file-mover status 8f6e4ad6
```
Possible output:
```
Job ID:              8f6e4ad6-64f0-4ccd-bf71-92d96ef6190a
Scenario ID:         SWIT-20260710-001
State:               COPYING
Files:               4 of 6 complete
Bytes:               71.8 GB of 103.4 GB
Current file:        host05/recording.dat
Attempt:             1
Submitted:           2026-07-10 11:03:17
Last update:         2026-07-10 11:21:44
```

#### `list`
```shell
file-mover list --state active
file-mover list --state failed-retained
file-mover list --scenario-id SWIT-20260710-001
```

#### `retry`
```shell
file-mover retry 8f6e4ad6
```
This should not directly copy anything. It should transition an eligible retained job back to a queued state.

#### `cancel`
Cancellation needs careful semantics.
```shell
file-mover cancel 8f6e4ad6
```
Recommended initial behavior:

* Stop future file processing.
* Allow the current copy chunk or current file to stop at a safe checkpoint.
* Retain claimed source files.
* Retain or remove temporary destination files according to policy.
* Never restore original filenames automatically unless a specific release command is defined.

I would not include cancellation in the first minimum release unless operations requires it.

#### `doctor`
```shell
file-mover doctor
```

Checks should include:

* Configuration syntax
* Unknown configuration keys
* State directory permissions
* SQLite database access
* Source root visibility
* Destination root visibility
* Same-filesystem capability for source claiming
* Destination temporary-file creation
* Atomic rename within destination
* Available disk space
* Hash algorithm support
* Lock acquisition
* Existing active service instance

The doctor command should avoid altering real recording data. It may create a small test file in configured diagnostic directories and remove it afterward.

#### `service run`
```shell
file-mover service run
```
This is the process started by `systemd`.

It should:

1. Load and validate configuration.
2. Acquire a singleton process lock.
3. Open and migrate the SQLite database.
4. Reconcile interrupted jobs.
5. Start worker threads.
6. Process queued jobs.
7. Handle SIGTERM and SIGINT.
8. Stop accepting new work during shutdown.
9. Complete or safely pause active work.
10. Close resources and exit.

## How the Orchestration Script Should Submit Jobs
The orchestration script can invoke the CLI synchronously because submission should be quick. It is the 100 GB transfer that is asynchronous, not the acceptance operation.

```python
"""Integration helper for submitting SWIT recording transfers."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileMoverSubmission:
    """Represent an accepted background file-mover job."""

    job_id: str
    state: str
    claimed_file_count: int
    claimed_bytes: int


def submit_recordings(
    scenario_id: str,
    source: Path,
    destination: Path,
) -> FileMoverSubmission:
    """Submit completed scenario recordings to the background mover.

    Args:
        scenario_id: Unique identifier for the completed scenario.
        source: Directory containing completed recording files.
        destination: Final processing-platform destination directory.

    Returns:
        Details for the accepted background transfer job.

    Raises:
        RuntimeError: If the mover rejects the request or cannot be reached.
    """
    command = [
        "/usr/bin/swit-file-mover",
        "--output",
        "json",
        "submit",
        "--scenario-id",
        scenario_id,
        "--source",
        str(source),
        "--destination",
        str(destination),
    ]

    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(
            f"SWIT file mover rejected scenario {scenario_id}: {message}"
        )

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "SWIT file mover returned an invalid response."
        ) from error

    return FileMoverSubmission(
        job_id=str(payload["job_id"]),
        state=str(payload["state"]),
        claimed_file_count=int(payload["claimed_file_count"]),
        claimed_bytes=int(payload["claimed_bytes"]),
    )
```
This call should return only after the following are true:
```
request validated
job ID allocated
file inventory recorded
source files claimed
manifest written when required
SQLite transaction committed
job placed into the durable queue
```
At that point, the simulation orchestration can safely continue preparing the next run.

## Important Submission Timing Question
There is one architectural nuance we should settle in the requirements:

#### Option A: Return only after all files are claimed
```
submit
    → enumerate 100 GB dataset
    → validate files
    → optionally hash before copy
    → rename files into staging
    → return accepted
```
If source hashing is required before the command returns, the simulation could still wait a long time because hashing 100 GB may take minutes.

#### Option B: Claim first, hash in the background
```
submit
    → enumerate files
    → validate stability
    → atomically rename into staging
    → persist manifest without hashes
    → return accepted
    → background service computes source hashes
    → update manifest
    → begin copy
```
This better meets the goal of releasing simulation hosts quickly while still ensuring the hash is written before copying to the remote destination.

I recommend **Option B**.

The exact required ordering would be:
```
1. Stop/close recording writers.
2. Submit job.
3. Validate and claim source files.
4. Persist the claimed inventory.
5. Return acceptance to orchestration.
6. Compute source hashes in the background.
7. Persist and fsync the completed hash manifest.
8. Begin remote copying.
```
This satisfies:

> The hash value is written into a file before the files are moved to the different destination.

without requiring hashing to finish before the simulation orchestration can proceed.

## CLI Output Formats
The CLI should support:
```shell
--output human
--output json
```
Potentially later:
```
--output json-lines
```
Human output:
```
Transfer job accepted.
Job ID: 8f6e4ad6-64f0-4ccd-bf71-92d96ef6190a
Files claimed: 34
Bytes claimed: 103.4 GB
State: QUEUED_FOR_HASHING
```
JSON output:
```json
{
  "accepted": true,
  "job_id": "8f6e4ad6-64f0-4ccd-bf71-92d96ef6190a",
  "state": "QUEUED_FOR_HASHING",
  "claimed_file_count": 34,
  "claimed_bytes": 111025274880
}
```
JSON output should contain no logging noise.

## Additional Requirements Derived From This CLI
#### L2 CLI Requirements
##### L2-CLI-001

The software shall provide an `argparse`-based command-line interface using only Python standard-library modules.

##### L2-CLI-002

The CLI shall provide separate commands for job submission, status inspection, job listing, retry, diagnostics, recovery, statistics, and service execution.

##### L2-CLI-003

The CLI shall return documented exit codes that distinguish configuration errors, rejected submissions, unavailable services, missing jobs, operational failures, and internal failures.

##### L2-CLI-004

The CLI shall support human-readable and machine-readable JSON output.

##### L2-CLI-005

Machine-readable output shall be written to standard output without interleaved application logging.

##### L2-CLI-006

Diagnostic and log messages shall be written to standard error.

##### L2-CLI-007

CLI policy overrides shall apply only to the current command or submitted job and shall not modify the application configuration file.

##### L2-CLI-008

The submit command shall return success only after the transfer job has been durably recorded and all accepted source files have been claimed.

##### L2-CLI-009

The submit command shall not wait for source hashing, remote copying, destination verification, or source deletion after the files have been safely claimed.

##### L2-CLI-010

The CLI shall convert all unexpected top-level exceptions into a controlled nonzero exit code and log the associated traceback.

##### L2-CLI-011

The package entry point shall process the actual supplied command-line arguments and shall contain no hard-coded development commands.

#### L3 Parser Requirements
##### L3-CLI-001.1

The `create_parser()` function shall construct the parser without performing file operations, loading the database, or starting worker threads.

##### L3-CLI-001.2

Each subcommand shall delegate to a dedicated command-handler function.

##### L3-CLI-001.3

Command handlers shall convert `argparse.Namespace` values into typed request objects before calling application services.

##### L3-CLI-001.4

The output renderer shall be separate from command execution logic.

##### L3-CLI-001.5

The CLI parser shall reject unsupported arguments and invalid choices before application services are invoked.

## Testing Suggested by This File
The CLI test suite should include:
```
parser accepts every valid command
parser rejects missing required arguments
parser rejects invalid integrity modes
parser rejects invalid log levels
submit returns correct success exit code
submit returns correct rejection exit code
status returns job-not-found exit code
JSON output is valid JSON
JSON output contains no log text
logging goes to stderr
CLI overrides do not modify configuration files
unexpected exception maps to INTERNAL_ERROR
main(None) uses real sys.argv
hard-coded development arguments are absent
```
Tests should call `main([...])` directly wherever possible. A smaller number of subprocess tests should verify the installed module entry point:
```shell
python -m swit_file_mover --help
```
The most important design decision from this file is that our submission CLI should remain synchronous only through the **durable claim boundary**. It should not detach a subprocess itself, rewrite configuration files, or perform the long-running copy. The already-running systemd service owns the background work.

## My Prompt:
file_handler/directory_factory.py

## Chat Reply:
This factory has several strong ideas we should preserve—especially rich validation errors, explicit object construction, and separating configuration loading from instance creation. However, the new mover does not need a general storage-backend factory. It only operates on mounted POSIX filesystems, so we can simplify considerably and gain stronger guarantees.

## What We Should Reuse
#### 1. Layered configuration processing
The current flow is good:
```
load raw configuration
        ↓
validate configuration
        ↓
construct typed model
        ↓
create runtime object
```
That separation should carry forward.

For `Background File Mover`, the equivalent would be:
```
ConfigurationFileReader
        ↓
ConfigurationParser
        ↓
ConfigurationValidator
        ↓
ApplicationConfig
        ↓
ApplicationFactory
```
Each step should have one responsibility.

For example:
```python
class ConfigurationLoader:
    """Load and validate application configuration."""

    def load(self, path: Path) -> ApplicationConfig:
        """Load application configuration from an INI file.

        Args:
            path: Path to the application configuration file.

        Returns:
            A validated immutable application configuration.

        Raises:
            ConfigurationFileError: If the file cannot be read.
            ConfigurationSyntaxError: If the INI content is invalid.
            ConfigurationValidationError: If values violate application rules.
        """
```

#### 2. Helpful validation messages
This file does more than say configuration is invalid. It identifies:

* The location of the error
* The validation message
* The expected model
* Valid fields
* Required versus optional fields
* Default values

That is excellent operational behavior.

We should preserve the same user experience without recreating Pydantic reflection.

An error should look like:
```
Configuration validation failed:

  Section: [transfer]
  Option: max_concurrent_files
  Value: 0
  Error: must be greater than or equal to 1

Valid options for [transfer]:
  max_concurrent_jobs = integer, default 1
  max_concurrent_files = integer, default 2
  copy_buffer_size_bytes = integer, default 8388608
  retry_limit = integer, default 10
  retry_initial_delay_seconds = float, default 10.0
  retry_max_delay_seconds = float, default 900.0
```
This is much better than a raw `ValueError`.

#### 3. Centralized construction
The current factory ensures callers do not construct directory implementations inconsistently.

That same idea applies to our service components:
```python
class ApplicationFactory:
    """Construct configured application services and infrastructure."""

    def create_submission_service(self) -> JobSubmissionService:
        ...

    def create_transfer_service(self) -> TransferCoordinator:
        ...

    def create_recovery_service(self) -> RecoveryService:
        ...

    def create_job_query_service(self) -> JobQueryService:
        ...
```
This allows centralized control of:

* Repository creation
* Clock injection
* Filesystem adapter injection
* Logging
* Event publishing
* Retry policy
* Integrity configuration
* Thread pools

It will also make tests much easier because the factory can accept test doubles.

#### 4. Dependency injection for external clients
The current factory supports:
```python
s3_client_override
```
We will not have an S3 client, but the underlying pattern is valuable.

For the new mover, injectable dependencies should include:
```
FileSystem
Clock
Sleeper
JobRepository
ManifestRepository
HashCalculator
TransferEventPublisher
DiskSpaceProvider
ProcessLock
```
Production uses standard-library implementations. Tests use controlled fakes.

For example:
```python
class ApplicationFactory:
    """Construct application components."""

    def __init__(
        self,
        config: ApplicationConfig,
        file_system: FileSystem | None = None,
        clock: Clock | None = None,
        sleeper: Sleeper | None = None,
    ) -> None:
        self._config = config
        self._file_system = file_system or PosixFileSystem()
        self._clock = clock or SystemClock()
        self._sleeper = sleeper or SystemSleeper()
```
This is one of the most useful architectural concepts from the current factory.

## What We Should Not Carry Forward
#### 1. Dynamic constructor inspection
This code is clever:
```python
params = signature(directory_class).parameters
filtered = {
    k: v
    for k, v in config.model_dump().items()
    if k in params and v is not None
}
```
But it hides the mapping between configuration and runtime objects.

Problems include:

* Renaming a constructor argument may silently stop passing a configuration value.
* A typo may be silently filtered out.
* Required parameters are discovered only at runtime.
* Static type checking cannot validate the mapping.
* Constructor behavior becomes coupled to reflection.
* Configuration fields may be unintentionally passed merely because names happen to match.

For the new project, construction should be explicit:

```python
transfer_config = TransferConfig(
    max_concurrent_jobs=parse_positive_int(
        section="transfer",
        option="max_concurrent_jobs",
        value=parser["transfer"]["max_concurrent_jobs"],
    ),
    max_concurrent_files=parse_positive_int(
        section="transfer",
        option="max_concurrent_files",
        value=parser["transfer"]["max_concurrent_files"],
    ),
    copy_buffer_size_bytes=parse_buffer_size(
        parser["transfer"]["copy_buffer_size_bytes"]
    ),
)
```
This is longer, but much safer for a data-preservation application.

#### 2. Fallback implementations for missing required dependencies
This block is dangerous:
```python
except ImportError:
    class ValidationError(ValueError):
        ...
```
The fallback does not provide equivalent validation. It can return the raw dictionary:
```python
return data
```
Later code expects a Pydantic model with methods such as:
```python
model_dump()
```
So the fallback is not actually a reliable fallback.

More importantly, silently operating with reduced validation is unacceptable for our mover.

For `Background File Mover`:

* All production functionality is standard library.
* Missing required standard-library capabilities should cause controlled startup failure.
* There should be no degraded validation mode.
* There should be no “best effort” fallback that bypasses safety checks.

Failing safely is preferable to silently weakening validation.

#### 3. Assertions for runtime validation
The current code uses:
```python
assert config.bucket_name is not None
```
Assertions are inappropriate for operational validation because Python can disable them with optimization:
```shell
python -O
```
The new project should never rely on `assert` for:

* Path safety
* Job-state validity
* Integrity checks
* Configuration completeness
* Source deletion preconditions
* Destination publication preconditions

Use explicit checks:

```python
if file_record.state is not FileState.PUBLISHED_VERIFIED:
    raise InvalidStateTransitionError(
        current_state=file_record.state,
        requested_state=FileState.SOURCE_DELETED,
    )
```
Assertions may still be used sparingly for genuine programmer invariants in tests, but not for production safety decisions.

#### 4. Returning broad `Any` types
Several APIs use:
```python
Any
Directory[Any]
Optional[Any]
```
The new application should keep infrastructure interfaces narrow.

For example:
```python
class FileSystem(Protocol):
    """Define filesystem operations required by the mover."""

    def stat(self, path: Path, *, follow_symlinks: bool = False) -> os.stat_result:
        ...

    def replace(self, source: Path, destination: Path) -> None:
        ...

    def open_binary_reader(self, path: Path) -> BinaryIO:
        ...

    def open_binary_writer_exclusive(self, path: Path) -> BinaryIO:
        ...

    def unlink(self, path: Path) -> None:
        ...
```
This tells us exactly what the mover depends on.

#### 5. One factory for unrelated storage types
The current factory supports local, SMB, and S3 through a shared abstraction. That makes sense for `file-handler`.

Our new project does not need that flexibility. Both NFS mounts are visible as normal Linux paths.

We should not create abstractions such as:
```
NfsDirectory
LocalDirectory
RemoteDirectory
StorageBackend
```
unless behavior actually differs.

From Python’s perspective, mounted NFS is accessed through normal POSIX filesystem calls. The important differences are operational:

* Remote availability
* NFS error codes
* Rename atomicity only within a mount
* Stale handles
* Write durability semantics
* Mount-point verification

These should be handled by filesystem policy and error classification, not a fake “NFS backend” class.

## A Better Factory Boundary for This Project
The new factory should not create generic directory objects. It should assemble application capabilities.
```
ApplicationFactory
│
├── create_job_repository()
├── create_manifest_repository()
├── create_source_claim_service()
├── create_integrity_service()
├── create_file_copier()
├── create_transfer_coordinator()
├── create_recovery_service()
├── create_submission_service()
└── create_background_service()
```
A possible implementation structure:
```python
class ApplicationFactory:
    """Create configured SWIT file mover application services."""

    def __init__(
        self,
        config: ApplicationConfig,
        logger_factory: LoggerFactory | None = None,
        clock: Clock | None = None,
        sleeper: Sleeper | None = None,
        file_system: FileSystem | None = None,
    ) -> None:
        """Initialize the application factory.

        Args:
            config: Validated application configuration.
            logger_factory: Optional logger provider.
            clock: Optional time provider used for testing.
            sleeper: Optional delay provider used for testing.
            file_system: Optional filesystem implementation.
        """
        self._config = config
        self._clock = clock or SystemClock()
        self._sleeper = sleeper or SystemSleeper()
        self._file_system = file_system or PosixFileSystem()
        self._logger_factory = logger_factory or StandardLoggerFactory()

    def create_job_repository(self) -> SQLiteJobRepository:
        """Create the SQLite-backed job repository."""
        return SQLiteJobRepository(
            database_path=self._config.service.database_path,
            clock=self._clock,
        )

    def create_file_copier(self) -> BufferedFileCopier:
        """Create the configured file-copy implementation."""
        return BufferedFileCopier(
            file_system=self._file_system,
            buffer_size_bytes=self._config.transfer.copy_buffer_size_bytes,
        )

    def create_transfer_coordinator(self) -> TransferCoordinator:
        """Create the transfer workflow coordinator."""
        repository = self.create_job_repository()
        return TransferCoordinator(
            repository=repository,
            file_system=self._file_system,
            copier=self.create_file_copier(),
            integrity_verifier=self.create_integrity_verifier(),
            retry_policy=self.create_retry_policy(),
            clock=self._clock,
            sleeper=self._sleeper,
        )
```
We should avoid creating multiple repository connections accidentally each time a factory method is called. The final implementation may use scoped or cached infrastructure instances, but the mappings should remain explicit.

## Configuration Schema Without Pydantic Reflection
The current file dynamically generates model schema hints. We can achieve similar behavior with declarative standard-library specifications.

For example:
```python
@dataclass(frozen=True)
class OptionSpec:
    """Describe one supported configuration option."""

    name: str
    value_type: str
    required: bool
    default_display: str | None
    description: str
```
Then:
```python
TRANSFER_OPTION_SPECS = (
    OptionSpec(
        name="max_concurrent_jobs",
        value_type="integer >= 1",
        required=False,
        default_display="1",
        description="Maximum number of jobs processed simultaneously.",
    ),
    OptionSpec(
        name="max_concurrent_files",
        value_type="integer >= 1",
        required=False,
        default_display="2",
        description="Maximum number of files copied simultaneously per service.",
    ),
)
```
The same specification can support:

* Unknown-option detection
* Error hints
* Configuration documentation generation
* Sample configuration generation
* `doctor` output
* Unit tests

This is a good opportunity to avoid duplicating configuration knowledge across code and documentation.

## Configuration Error Model
Rather than turning everything into `ValueError`, define structured issues.
```python
@dataclass(frozen=True)
class ConfigurationIssue:
    """Describe one invalid configuration value."""

    section: str
    option: str | None
    value: str | None
    message: str


class ConfigurationValidationError(SwitFileMoverError):
    """Indicate that application configuration is invalid."""

    def __init__(self, issues: Sequence[ConfigurationIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        lines = ["Configuration validation failed:"]
        for issue in self.issues:
            location = f"[{issue.section}]"
            if issue.option:
                location += f" {issue.option}"
            lines.append(f"  - {location}: {issue.message}")
        return "\n".join(lines)
```
This allows the CLI to render human-readable output while JSON mode can return structured errors:
```json
{
  "success": false,
  "error_code": "CONFIGURATION_INVALID",
  "issues": [
    {
      "section": "transfer",
      "option": "max_concurrent_files",
      "value": "0",
      "message": "must be greater than or equal to 1"
    }
  ]
}
```
## Path Construction Must Be Explicit
The existing factory accepts a configured `path` and builds a directory object. Our application needs stronger path normalization and policy enforcement.

We should separate lexical path validation from filesystem validation.

#### Lexical validation

Performed without touching the filesystem:
```
Path must be absolute.
Path must not contain a NUL character.
Source and destination must not be identical.
Destination must not be lexically beneath the source.
Claim directory name must be a single path component.
Temporary prefix must not contain separators.
```
#### Filesystem validation

Performed using actual metadata:
```
Source root exists.
Source root is a directory.
Source root is on an approved mount.
Destination root exists or its approved parent exists.
Source claim operation remains on the same device.
Source and destination are on different configured filesystem roots.
State directory is not on the recording source tree.
Paths do not resolve through symbolic links when symlinks are forbidden.
```
We should be careful with `Path.resolve()` because resolving symlinks can itself violate the “do not follow symlinks” policy. The filesystem layer may need component-by-component `lstat()` validation.

## Important New Concept: Filesystem Identity
Because source claiming must remain on the same filesystem, the application should record filesystem identity.

A file observation can include:
```python
@dataclass(frozen=True)
class FileIdentity:
    """Identify a filesystem object at a point in time."""

    device_id: int
    inode: int
    size_bytes: int
    modified_time_ns: int
```
Before and after claiming, we can verify:
```
device ID unchanged
inode unchanged
size unchanged
mtime unchanged
```
This confirms the claimed path refers to the same source object.

For directories, we should also verify the staging directory has the same `st_dev` as the source file before attempting the rename.

## Requirements Derived From This Factory
#### L2 Factory and Construction Requirements
##### L2-ARC-001

The software shall separate configuration loading, configuration validation, infrastructure construction, and application-service construction.

##### L2-ARC-002

The software shall construct application components through explicit typed mappings rather than runtime constructor reflection.

##### L2-ARC-003

The software shall support injection of filesystem, clock, delay, repository, and integrity implementations for testing.

##### L2-ARC-004

The software shall not provide a reduced-validation fallback mode.

##### L2-ARC-005

The software shall not use Python assertions to enforce operational or data-safety requirements.

##### L2-ARC-006

The application factory shall construct only components required by the selected CLI command or service mode.

#### L2 Configuration Error Requirements
##### L2-CFG-008

The software shall report all detectable configuration validation issues in a single validation result where practical.

##### L2-CFG-009

Each configuration issue shall identify the section, option, invalid value when safe to display, and reason for rejection.

##### L2-CFG-010

The software shall provide contextual information describing valid options and accepted value ranges.

##### L2-CFG-011

The software shall use the same configuration-option definitions for validation and generated operator documentation where practical.

#### L2 Filesystem Identity Requirements
##### L2-FS-001

The software shall record the device identifier and inode of each source file before claiming it.

##### L2-FS-002

The software shall verify that a claimed file refers to the same device and inode as the pre-claim source file.

##### L2-FS-003

The software shall reject a claim operation when the source and claim destination are not located on the same filesystem.

##### L2-FS-004

The software shall not follow symbolic links during source inventory or claiming unless explicitly enabled by an approved future requirement.

##### L2-FS-005

The software shall validate that submitted source and destination paths remain beneath configured approved roots.

## Testing Ideas From This File
The configuration and factory tests should cover:

```
valid configuration produces the expected immutable objects
unknown section is rejected
unknown option is rejected
missing required option is rejected
invalid integer includes section and option in the error
multiple independent errors are reported together
invalid enum lists accepted choices
factory maps every config field explicitly
factory does not rely on inspect.signature
test filesystem can be injected
test clock can be injected
test sleeper prevents real retry delays
production filesystem is used by default
assert statements are not used for runtime validation
source and claim paths on different st_dev values are rejected
inode identity is preserved after claim
symlink source paths are rejected
resolved paths cannot escape approved roots
```
The biggest lesson from this file is not the multi-backend directory factory itself. It is the disciplined pipeline of **load, validate, explain, then construct**. We should retain that pattern while replacing dynamic reflection and permissive fallbacks with explicit standard-library code appropriate for a data-durability system.

## My Prompt:
file_handler/local.py

## Chat Reply:
This file is useful for defining the filesystem boundary, but it does **not** contain the performance-critical copy implementation. The actual buffered copy loop, concurrency, retry behavior, stability gating, and move workflow appear to live in `Directory` from `_directory.py`. Therefore, we cannot yet validate the claim that `file-handler` has been maximized for copy performance.

We can still extract several good practices and identify important changes for `Background File Mover`.

## Overall Direction
Because S3 support is expected later, we should retain a storage abstraction—but not a broad Directory abstraction that tries to make POSIX filesystems and object storage appear identical.

A better separation is:
```
Transfer workflow
    │
    ├── SourceStorage
    ├── DestinationStorage
    ├── IntegrityVerifier
    ├── JobRepository
    └── TransferCoordinator
```
Initial implementations:
```
PosixStorage
    Supports local filesystems and mounted NFS

Future:
S3Storage
    Supports object storage through an optional adapter
```
The durable workflow remains the same conceptually:
```
claim source
create manifest
copy to temporary destination
verify
publish
delete or release source
```
But the implementation of operations differs:
| Operation             | POSIX/NFS                          | Future S3                                             |
| --------------------- | ---------------------------------- | ----------------------------------------------------- |
| Claim                 | Atomic rename on source filesystem | Object tag, metadata state, or copy to claimed prefix |
| Temporary destination | Hidden temporary filename          | Temporary object key                                  |
| Publish               | Atomic rename                      | Server-side copy or final-key upload                  |
| Durability flush      | `flush()` and `fsync()`            | Complete upload and validate response                 |
| Identity              | Device and inode                   | Bucket, key, version ID, ETag                         |
| Delete                | `unlink()`                         | Object deletion, preferably version-aware             |
Trying to hide all of these differences behind generic methods such as `mkdir()` and `open_file()` would eventually produce leaky abstractions.

## Good Ideas in `LocalDirectory`
#### 1. Standard filesystem exceptions are retained

The implementation maps operations to familiar Python exceptions:

```python
FileNotFoundError
PermissionError
IsADirectoryError
OSError
```
This is better than converting every failure into one generic custom exception.

For the new application, the filesystem layer should generally preserve the original exception as the cause:

```python
raise SourceOpenError(
    path=path,
    operation="open-read",
    errno_value=error.errno,
) from error
```
The original `errno` must remain available because it helps classify NFS and local filesystem failures.

#### 2. Path operations use `pathlib.Path`
This is appropriate and should continue for POSIX/NFS paths.

Our public models should use `Path`, not arbitrary strings:
```python
@dataclass(frozen=True)
class TransferPath:
    """Describe source and destination paths for one transfer file."""

    relative_path: Path
    claimed_source_path: Path
    temporary_destination_path: Path
    final_destination_path: Path
```
We should validate that `relative_path` is genuinely relative and contains no traversal components.

#### 3. Race conditions during directory traversal are anticipated
This handling is sensible:
```python
except FileNotFoundError:
    continue
```
Files can disappear between enumeration and metadata inspection.

However, the appropriate reaction depends on the phase:

* During an optional discovery scan, disappearing files may be skipped and reported.
* During job claiming, a disappearing file must cause the submission to be rejected or marked incomplete.
* After a file has been claimed, disappearance is a serious data-integrity event.

The new application must not apply the same permissive behavior in every phase.

#### 4. Missing-file deletion is idempotent
This is a useful concept:
```python
filepath.unlink(missing_ok=True)
```
Recovery logic must tolerate operations that may already have completed before a crash.

For example:
```
source already deleted
destination verified and published
database still says SOURCE_CLEANUP_PENDING
```
Recovery should interpret that as a potentially completed cleanup, verify destination state, and safely advance the record.

Idempotency is essential.

#### 5. UTC timestamps are used
This is correct:
```python
datetime.fromtimestamp(..., tz=timezone.utc)
```
All persisted application timestamps should use UTC.

For filesystem comparisons, however, we should use integer nanosecond values:
```python
stat_result.st_mtime_ns
```
rather than `datetime` or floating-point seconds. Nanosecond integer metadata is safer for equality comparisons.

## Important Problems for the New Mover
#### 1. `_resolve_root()` creates missing directories automatically
This behavior is unsafe for source directories:

```python
if not root.exists():
    root.mkdir(parents=True, exist_ok=True)
```
A mistyped source path could silently create an empty directory, making the submission appear valid while the expected recordings remain elsewhere.

We need different policies.

##### Source root
```
Must already exist.
Must be a directory.
Must be under an approved source root.
Must not be created automatically.
```

##### Destination root
The destination may be created only when:

* Its parent exists beneath an approved destination root.
* Creation is allowed by configuration.
* The application creates it intentionally.
* The resolved path cannot escape the approved root.

##### State and runtime directories

These may be created by startup or packaging with controlled permissions.

One generic “resolve or create root” method is therefore inappropriate.

#### 2. `Path.resolve()` follows symbolic links
This appears in multiple places:
```python
Path(root_specifier).expanduser().resolve()
```
and:
```python
resolved_item = Path(path).resolve()
```
That conflicts with a strict no-symlink policy.

A submitted path such as:
```
/recordings/run-001/data.bin
```
could pass lexically beneath the source root but resolve to another filesystem through a symbolic link.

For this application, we should:

* Reject symlink path components.
* Use lstat() where appropriate.
* Avoid blindly calling resolve() before validating components.
* Confirm path containment after safe inspection.
* Open files in ways that reduce symlink races.

On Linux, we should consider using `os.open()` with flags such as:

```python
os.O_RDONLY
os.O_NOFOLLOW
os.O_CLOEXEC
```
where supported.

For destination creation:
```python
os.O_WRONLY
os.O_CREAT
os.O_EXCL
os.O_NOFOLLOW
os.O_CLOEXEC
```
This provides stronger behavior than ordinary `Path.open()`.

#### 3. Symlink skipping is too permissive by default
The existing default is:
```python
skip_symlinks: bool = False
```
For `Background File Mover`, the default should be strict rejection:
```
reject symbolic links = true
```
“Skip” may also be undesirable. If a submitted recording set contains a symbolic link, silently skipping it could produce an incomplete dataset.

Recommended behavior:

```
Explicit file list contains symlink:
    Reject submission.

Directory submission encounters symlink:
    Reject submission unless policy explicitly allows exclusions.
```
Data completeness is more important than making the scan continue.

#### 4. `rglob("*")` is convenient but not ideal for a durability-critical inventory
This traversal:

```python
for item in self.root.rglob("*"):
```
is easy to use, but gives limited control over:

* Symlink traversal
* Error handling per directory
* Filesystem boundaries
* Ordering
* Metadata collection
* Directory descriptor safety
* Exclusion of the claim directory
* Concurrent directory changes

A more controlled implementation could use `os.scandir()` recursively.

Benefits:

* `DirEntry` can provide metadata efficiently.
* Symlink following can be disabled explicitly.
* We can avoid traversing the `.moving` claim directory.
* We can record file identity during inventory.
* We can handle errors at directory boundaries.
* Fewer metadata calls may improve large-directory scanning performance.

A deterministic order should be used:

```
sort by relative path
```
This produces repeatable manifests and tests.

#### 5. Scan errors are emitted and processing continues
This code catches an `OSError`, emits an event, and keeps scanning:
```python
except OSError as err:
    self.on_operation_progress.emit(...)
```
That may be suitable for a general-purpose scanning tool, but not necessarily for transfer submission.

Suppose one subdirectory cannot be read. Continuing could yield a partial inventory and move only part of the scenario.

For the new system:

> A source inventory shall be all-or-nothing unless the submission explicitly names an approved subset of files.

Any unreadable source path should reject claiming before destructive renames begin.

#### 6. `open_file()` accepts arbitrary modes
This API:
```python
def open_file(self, path: Path, mode: str) -> IO[bytes]:
```
allows unsafe or unexpected modes:
```
w
a
r+
wb+
```
The new filesystem interface should expose intent-specific methods:
```python
open_source_reader(path)
create_destination_exclusive(path)
open_destination_reader(path)
```
That prevents core transfer code from accidentally opening a source file for writing or overwriting a destination.

#### 7. `IOError` loses useful specificity
The code often does:
```python
raise IOError(...)
```
In Python 3, `IOError` is an alias for `OSError`, but creating a new generic error can lose the original `errno` unless it remains accessible through `__cause__`.

NFS classification often depends on values such as:
```
ESTALE
EIO
ETIMEDOUT
ENOSPC
EDQUOT
EROFS
EACCES
EXDEV
```
The error classifier should inspect the original exception chain and preserve:

* `errno`
* filename
* destination filename
* operation
* source and destination paths

#### 8. Directory removal treats non-empty as success
This code intentionally treats `ENOTEMPTY` as success:

```python
if err.errno == errno.ENOTEMPTY:
    status, error = "success", None
```
That is reasonable if the requirement is “remove the directory only when empty.”

But it should not be reported simply as successful deletion. It is more accurately:
```
SKIPPED_NOT_EMPTY
```
For our project, job cleanup should distinguish:

* Directory removed
* Directory already absent
* Directory retained because it contains excluded/unexpected files
* Directory removal failed

Unexpected remaining content may indicate that the simulation wrote new files into the directory or that the claim process missed data. That should not disappear into a generic success state.

#### 9. Deletion occurs by pathname without identity revalidation
Before deleting a source file, the mover must confirm that the path still refers to the file that was originally claimed.

Otherwise, a path could have been replaced between verification and deletion.

Before source deletion, compare:
```
device ID
inode
size
possibly mtime
```
against the claimed file record.

The sequence should be:
```
destination verified
        ↓
lstat claimed source
        ↓
verify device and inode
        ↓
unlink claimed path
```
If identity differs, do not delete it. Transition the job to manual intervention.

#### 10. File-size and modification methods perform separate path-based calls
These methods:
```python
os.path.getsize(path)
os.path.getmtime(path)
```
perform separate metadata lookups.

For stability and identity checks, use one call:
```python
metadata = path.stat(follow_symlinks=False)
```
Then collect:
```python
metadata.st_dev
metadata.st_ino
metadata.st_mode
metadata.st_size
metadata.st_mtime_ns
metadata.st_ctime_ns
metadata.st_nlink
```
This is both more coherent and often more efficient.

## Performance Conclusions From the Provided Code
We have not seen enough code to determine whether `file-handler` is optimized for copy performance.

The performance-critical questions remain unanswered:

1. What function performs the actual copy?
2. What buffer size is used?
3. Is `shutil.copyfileobj()` used?
4. Is `os.sendfile()` used?
5. Is `copy_file_range()` used?
6. Is copying performed concurrently?
7. Is concurrency bounded globally or per operation?
8. Are source and destination hashes calculated in the same read pass?
9. Is the destination re-read for verification?
10. Are metadata and permissions copied unnecessarily?
11. Are files opened with buffering?
12. Is progress reporting performed per chunk, and does it create lock contention?
13. Are retries file-level or chunk-level?
14. Is partial-file resume supported?
15. Does the implementation call `fsync()`?
16. Does it account for NFS mount behavior?

Since `_directory.py` was not provided, we should not claim that any specific optimization from this project can be reused.

## Initial copy implementation recommendation
For the first version, use a clearly testable buffered copy loop rather than relying blindly on one high-level function:

```python
while True:
    chunk = source.read(buffer_size)
    if not chunk:
        break

    destination.write(chunk)
    hasher.update(chunk)
```
This supports:

* Bounded memory
* Progress tracking
* Cancellation checkpoints
* Streaming source hash
* Fault injection
* Accurate byte counts
* Controlled retry behavior

However, when pre-copy source hashing is required, the source hash is already computed in a separate pass. During the copy pass, hashing again may not be necessary unless we want to ensure the source did not change between hashing and copying.

A stronger workflow is:

```
pre-copy source stat
source hash pass
post-hash source stat and identity check
persist hash
copy while calculating copy-stream hash
post-copy source stat and identity check
verify copy-stream hash equals pre-copy source hash
hash destination
verify destination hash
publish
delete source
```
This costs additional CPU and destination reads but provides strong detection of source mutation.

The exact integrity modes should let operations choose the trade-off.

## Proposed Storage Interfaces
To support S3 later without distorting the initial implementation, I recommend two levels.

#### Workflow-level interface
```python
class TransferSource(Protocol):
    """Provide source operations required by the transfer workflow."""

    def inventory(self, request: SourceRequest) -> FileInventory:
        """Create a complete source inventory."""

    def claim(self, inventory: FileInventory, job_id: str) -> ClaimedInventory:
        """Claim source items for exclusive transfer processing."""

    def open_reader(self, item: ClaimedItem) -> BinaryIO:
        """Open a claimed source item for binary reading."""

    def stat_claimed(self, item: ClaimedItem) -> ObjectMetadata:
        """Read metadata for a claimed source item."""

    def delete_claimed(self, item: ClaimedItem) -> None:
        """Delete a verified claimed source item."""
```
```python
class TransferDestination(Protocol):
    """Provide destination operations required by the transfer workflow."""

    def create_temporary_writer(
        self,
        item: DestinationItem,
    ) -> BinaryIO:
        """Create an exclusive temporary destination object."""

    def open_temporary_reader(
        self,
        item: DestinationItem,
    ) -> BinaryIO:
        """Open the temporary destination for verification."""

    def publish(self, item: DestinationItem) -> PublishedObject:
        """Publish a verified temporary object."""

    def inspect_published(
        self,
        item: DestinationItem,
    ) -> ObjectMetadata | None:
        """Inspect an existing published destination."""

    def remove_temporary(self, item: DestinationItem) -> None:
        """Remove an invalid or abandoned temporary object."""
```
#### POSIX-specific lower-level interface
```python
class PosixFileSystem(Protocol):
    """Define POSIX filesystem operations used by storage adapters."""

    def lstat(self, path: Path) -> os.stat_result:
        ...

    def scandir(self, path: Path) -> ContextManager[Iterator[os.DirEntry[str]]]:
        ...

    def replace(self, source: Path, destination: Path) -> None:
        ...

    def unlink(self, path: Path, *, missing_ok: bool = False) -> None:
        ...

    def fsync_file(self, file_descriptor: int) -> None:
        ...

    def fsync_directory(self, path: Path) -> None:
        ...
```
This gives us future extensibility without making S3 pretend it is a filesystem.

## Future S3 Design Considerations
S3 support should be added as an optional package or plugin because the base application has a no-external-runtime-dependencies requirement.

Potential future structure:
```
background-file-mover/
├── src/file_mover/
│   └── standard-library core
└── optional/
    └── file_mover_s3/
        └── boto3-based adapter
```
Or separate distributions:
```
file-mover-core
file-mover-s3
```
The core project should not contain conditional imports that silently degrade when `boto3` is unavailable.

S3-specific concerns will include:

* Multipart uploads
* Multipart threshold and part size
* Upload restart/reconciliation
* Object metadata
* Checksums
* Version IDs
* SSE configuration
* Final-key collision policies
* Server-side copy behavior
* Eventual consistency assumptions, although modern S3 has strong read-after-write consistency
* Compatible object stores that may behave differently
* Credential providers
* Endpoint configuration
* TLS trust
* Object-lock and retention policies

These are exactly why S3 should implement workflow capabilities rather than subclass a generic filesystem directory.

## Updated Component Model
The architecture should now include:
```
TransferCoordinator
│
├── JobRepository
├── ManifestRepository
├── TransferSource
│   └── PosixTransferSource
├── TransferDestination
│   └── PosixTransferDestination
├── FileCopyEngine
├── IntegrityVerifier
├── RetryPolicy
├── ErrorClassifier
└── TransferEventPublisher
```
Future:
```
TransferSource
├── PosixTransferSource
└── S3TransferSource

TransferDestination
├── PosixTransferDestination
└── S3TransferDestination
```
This is more precise than:
```
Directory
├── LocalDirectory
├── SMBDirectory
└── S3Directory
```

## Requirements Derived From `LocalDirectory`
#### L2 POSIX Source Requirements
##### L2-POSIX-001

The software shall require submitted source roots to exist before job submission and shall not create missing source directories.

##### L2-POSIX-002

The software shall reject symbolic links encountered within a submitted source inventory.

##### L2-POSIX-003

The software shall reject a source inventory when any requested path cannot be inspected or read.

##### L2-POSIX-004

The software shall produce source inventories in deterministic relative-path order.

##### L2-POSIX-005

The software shall exclude internal claim directories from source discovery.

##### L2-POSIX-006

The software shall collect device ID, inode, file type, size, modification time in nanoseconds, and link count from a single metadata observation where supported.

##### L2-POSIX-007

The software shall validate source-file identity before claiming and again before deleting the claimed source.

#### L2 POSIX Destination Requirements
##### L2-POSIX-008

The software shall create temporary destination files using exclusive creation semantics.

##### L2-POSIX-009

The software shall refuse to follow symbolic links when creating or opening temporary destination files.

##### L2-POSIX-010

The software shall flush and synchronize completed temporary destination files before verification or publication.

##### L2-POSIX-011

The software shall publish temporary destination files using atomic replacement or rename semantics only within the destination filesystem.

##### L2-POSIX-012

The software shall synchronize the destination directory after publication where supported and configured.

#### L2 Cleanup Requirements
##### L2-CLN-001

Source cleanup shall be idempotent.

##### L2-CLN-002

A missing source during recovery shall be treated as potentially completed cleanup only after the published destination has been verified.

##### L2-CLN-003

A non-empty claim directory shall not be reported as successfully removed.

##### L2-CLN-004

Unexpected files remaining in a completed job’s claim directory shall place the job into manual-intervention state.

##### L2-CLN-005

The software shall not delete a claimed source path when its current device and inode differ from the recorded identity.

#### L2 Storage Extensibility Requirements
##### L2-STO-001

The transfer workflow shall depend on source and destination capability interfaces rather than directly on POSIX path operations.

##### L2-STO-002

The initial release shall provide POSIX source and destination implementations suitable for local and mounted NFS filesystems.

##### L2-STO-003

The source and destination interfaces shall permit a future S3 implementation without changing the durable job-state workflow.

##### L2-STO-004

Storage-specific identity information shall be represented through typed metadata capable of supporting POSIX device/inode identity and future S3 bucket/key/version identity.

##### L2-STO-005

Optional storage adapters requiring external dependencies shall not weaken or alter the no-external-dependency core application.

## Final Assessment of the Existing `file-handler`

The provided application contains several mature and useful concepts:

* Lifecycle reporting
* Retry visibility
* Strict configuration intent
* Helpful validation messages
* Factory-based construction
* Backend separation
* Filesystem exception handling
* Idempotent cleanup behavior
* Stability checks
* Operational statistics

The primary weaknesses for this project are:

* Synchronous operation model
* In-memory authoritative state
* Generic directory abstraction across unlike storage systems
* Loose event and result typing
* Symlink-permissive defaults
* Automatic source-directory creation
* Configuration mutation by the CLI
* Dynamic constructor reflection
* Inconsistent statistics and operation naming
* Insufficiently explicit claim, verify, publish, and deletion states

Most importantly, the code provided does not include the actual base `Directory` copy implementation, so none of its copy-performance techniques can yet be identified or validated. For the new project, we should treat `file-handler` as an experienced source of design lessons—not as code to port—and build the transfer core around explicit durability guarantees.

## My Prompt:
I did not realize I did not provide _directory.py, lets add it to the analysis now.
file_handler/directories/_directory.py

## Chat Reply:
This file finally exposes the copy path, and it changes the assessment materially.

The existing `file-handler` does contain several valuable implementation ideas:

* Bounded chunked copying
* Multithreaded file-level concurrency
* Retry handling with exponential backoff
* Pre-copy stability checks
* Post-copy size verification
* “Delete only confirmed copied files” move safety
* Best-effort directory cleanup
* Avoidance of deleting files that appeared after the initial scan

Those are all worth carrying into the new design conceptually.

However, the current implementation is not sufficiently durable for `Background File Mover`, and several behaviors would be unsafe for recorded simulation data.

## What the Current Copy Engine Actually Does
The core copy loop is:

```python
with (
    self.open_file(src_path, "rb") as src_f,
    dest_dir.open_file(dest_path, "wb") as dst,
):
    for chunk in iter(lambda: src_f.read(1024 * 1024), b""):
        dst.write(chunk)
```
This means:

* Copy buffer size is fixed at 1 MiB.
* One thread is used per file task.
* `ThreadPoolExecutor()` uses Python’s default worker count.
* Files are copied concurrently.
* Destination files are opened directly at the final name.
* Existing destination files are deleted before copy.
* There is no destination temporary filename.
* There is no `flush()` or `fsync()`.
* Integrity verification is file-size only.
* Retry restarts the whole file from byte zero.
* The source is deleted after successful copy if `move()` is called.

This is a reasonable general-purpose file mover, but not yet a durable transactional mover.

## Performance Assessment
#### Good performance choices
##### File-level concurrency

This is likely the largest performance benefit:
```python
with ThreadPoolExecutor() as pool:
```
Filesystem copy operations release the GIL while blocked in kernel I/O, so threads can improve throughput when:

* Multiple files exist
* Source and destination storage tolerate parallel streams
* Network latency is meaningful
* Storage controllers benefit from queue depth

This is worth retaining.

But concurrency must be explicit and configurable. The default executor worker count is based on CPU count, not storage characteristics. On a large host, it could generate far too many simultaneous NFS streams.

We should use:
```python
ThreadPoolExecutor(
    max_workers=config.max_concurrent_files,
    thread_name_prefix="swit-copy",
)
```
#### Bounded memory

The 1 MiB read buffer prevents entire files from being loaded into memory.

That is correct.

For the new mover, the buffer size should be configurable. A likely starting point is between 1 MiB and 8 MiB, tested against the actual NFS environment.

Larger is not always better. We should benchmark:
```
1 MiB
4 MiB
8 MiB
16 MiB
```
with concurrency values such as:
```
1
2
4
```
The relevant metric is total end-to-end transfer throughput while preserving simulation-host responsiveness.

#### Copying independent files in parallel
The implementation schedules one future per file:
```python
pool.submit(
    self._copy_single_file_with_retries,
    src,
    dest_dir,
    rel,
)
```
That is suitable when the dataset contains multiple substantial recordings.

It is less helpful when there is one very large file. The new project should not split individual files into multiple parallel regions in the first release because that complicates retry, hashing, and destination publication.

#### Performance limitations
##### No use of kernel-assisted copy operations

The implementation does not use:

* `os.copy_file_range()`
* `os.sendfile()`
* `shutil.copyfile()`, which may use platform fast-copy syscalls internally

A manual Python loop can still perform well because the actual I/O occurs in C and the kernel, but it may involve more user-space copies and Python loop overhead.

For this project, a manual loop remains attractive because we need:

* Progress tracking
* Fault injection
* Optional hashing
* Controlled cancellation
* Byte accounting

We should not automatically replace it with `shutil.copyfile()`.

A good architecture is to support copy strategies behind an interface:

```
BufferedCopyStrategy
KernelCopyStrategy
HashingCopyStrategy
```
The initial implementation should probably use `BufferedCopyStrategy`, then benchmark whether `copy_file_range()` materially improves NFS-to-NFS performance.

Important: kernel copy optimizations may behave differently across NFS mounts and kernels. They must be benchmarked in the real environment rather than assumed superior.

#### Retry restarts whole-file copies

Tenacity retries `_copy_single_file()` as a whole.

If a 40 GB file fails at 39 GB, the next attempt:

1. Deletes the destination again.
2. Reopens the source.
3. Copies the entire file from zero.

This is simple and safe, but expensive.

For the first release, whole-file retry is acceptable if:

* Files are not individually enormous
* Failures are rare
* Durability is more important than optimization

Resume support should be considered later as a separate requirement.

#### Fixed retry policy

The existing policy is:
```python
wait_exponential(multiplier=1, min=2, max=30)
stop_after_attempt(3)
```
That is too short for a 100 GB operational transfer system.

A transient NFS problem could last longer than three attempts.

The new mover needs:

* Configurable retry count
* Configurable maximum retry duration
* Persisted retry state
* Retry continuation after service restart
* Error classification by errno
* Manual retry support

Retries should be job-aware and durable, not just function-call retries.

## Strong Ideas We Should Carry Forward
#### 1. Delete only files confirmed copied

This is one of the best parts:
```python
self._last_copy_success_src
```
and:
```python
for src_file in self._last_copy_success_src:
    self.remove_file_with_retries(src_file)
```
The comment is particularly important:

> Never do “delete everything except failures” — that can delete new files that appeared during the copy window.

That should become a formal requirement.

The new mover should never rescan a directory after copying and infer which files to delete. It should delete only the exact claimed file records whose destinations were verified.

#### 2. Stability recheck immediately before copy

This is useful:
```python
if not self._is_stable_for_copy(src_path):
    ...
    raise UnstableFileError(...)
```
A pre-copy recheck reduces the chance of copying a still-changing file.

For the new architecture, this should become stronger:
```
inventory observation
claim
pre-hash observation
post-hash observation
pre-copy observation
post-copy observation
pre-delete identity check
```
Each observation should include:

* Device ID
* Inode
* Size
* Modification time in nanoseconds
* File type
* Link count

#### 3. Size verification before source deletion

This is a minimum-integrity safeguard:
```python
if src_size != dst_size:
    raise IOError(...)
```
We should retain size verification in every integrity mode, including when hashing is disabled.

Hashing disabled should mean:
```
verify identity and size
```
not: 
```
perform no verification
```

#### 4. Preserve failed source files

The move implementation deletes only successful copies and leaves failed ones behind.

That is the correct safety direction.

The new mover strengthens this by claiming files first and retaining them in a job-specific staging area until the job reaches a verified terminal state.

#### 5. Deepest-first empty-directory cleanup

This is correct:
```python
sorted(parent_rels, key=lambda p: len(p.parts), reverse=True)
```
The new mover can use the same concept after all claimed files from a job have been deleted.

However, unexpected remaining files must be surfaced rather than silently ignored.

## Critical Problems for the New Project
#### 1. Existing destination files are deliberately deleted

This is the most dangerous behavior:
```python
dest_dir.remove_file_with_retries(dest_path)
```
followed by:
```python
dest_dir.open_file(dest_path, "wb")
```
This implements overwrite semantics by deleting the current destination.

For SWIT recordings, that should not be allowed by default.

A destination collision must be handled as:
```
destination absent
    → create temporary file

destination exists and matches expected content
    → idempotently reuse

destination exists and differs
    → fail retained / manual intervention
```
Never silently delete an existing final recording.

#### 2. Copy writes directly to the final destination name

This means downstream processing can see a partial file.

If the copy fails midway, the final path may contain incomplete data.

The new mover must write to:
```
.partial-<job-id>-<file-id>
```
and publish only after verification.

#### 3. No explicit buffer flush or `fsync()`

Leaving the `with` block closes the file, which flushes Python buffers, but that does not guarantee durable storage.

For destination publication:
```python
destination.flush()
os.fsync(destination.fileno())
```
should occur before verification and rename where supported.

For NFS, `fsync()` semantics depend on mount and server behavior, but it is still the correct client request for durable write completion.

We should also consider directory synchronization after atomic rename.

#### 4. Size verification is not enough

Equal file size does not prove equal content.

Configurable integrity modes should be:
```
metadata
source-hash
source-and-destination-hash
```
The strongest mode should:

1. Compute the source hash.
2. Persist the source hash manifest.
3. Copy to a temporary destination.
4. Compute destination hash.
5. Compare.
6. Publish.
7. Delete source.

#### 5. Broad retry on every `OSError`

The current transient set is:
```python
(
    ConnectionError,
    TimeoutError,
    OSError,
)
```
This retries permanent failures such as:

* `EACCES`
* `EPERM`
* `EROFS`
* `EINVAL`
* `ENAMETOOLONG`
* `EISDIR`
* `EXDEV`

Retrying those three times only delays the inevitable.

The new error classifier should distinguish:

##### Usually retryable
```
ESTALE
EIO
ETIMEDOUT
ECONNRESET
ECONNREFUSED
EHOSTUNREACH
ENETUNREACH
EBUSY
EAGAIN
```
##### Operator-remediable, retained
```
ENOSPC
EDQUOT
EROFS
EACCES
EPERM
```
##### Request/configuration failure
```
ENOENT before claim
ENOTDIR
EINVAL
EXDEV during expected same-filesystem claim
```
Some errors need environment-specific treatment.

#### 6. Retry callback appears to inspect the wrong object

This code is suspicious:
```python
"exception_type": type(retry_state.outcome).__name__,
```
`retry_state.outcome` is usually a Future-like result wrapper, not the underlying exception.

The actual exception is normally obtained from:
```python
retry_state.outcome.exception()
```
Similarly, the emitted `error` currently uses:
```python
error=retry_state.outcome
```
rather than the actual exception.

This could cause misleading retry logs and statistics.

#### 7. `UnstableFileError` may be retried unintentionally or reported repeatedly

`UnstableFileError` is not in the configured retry tuple, so it will not retry, which is good.

However, `_copy_single_file()` emits:
```
skipped_unstable
```
and then raises.

The outer future handling records it as a failure. That may be acceptable, but the event model can produce multiple events for one condition.

In the new system, instability should have a dedicated state:
```
SOURCE_UNSTABLE
```
and a defined disposition:
```
reject submission
or
retain and retry after delay
```
For recordings explicitly declared complete, instability may indicate orchestration submitted too early.

#### 8. Stability checks only compare size

The full check is:
```python
mtime gate
size polling
```
A file can be modified without changing size.

The new stability comparison should include:
```
size
mtime_ns
inode
device
```
Optionally `ctime_ns`.

#### 9. Default stability polling is silently normalized

This line:
```python
self.stability_polls = max(1, stability_polls)
```
turns invalid values into valid ones.

A configuration value of `-5` should be rejected, not silently converted to `1`.

Production configuration should fail closed.

#### 10. Path overlap checks use string prefix comparison

This is fragile:
```python
dst_root_norm.startswith(src_root_norm)
```
It attempts to normalize slashes, but string comparisons are not reliable filesystem containment checks.

Potential issues include:

* Case behavior
* Symlinks
* Mount bind paths
* Lexical traversal
* Equivalent paths with different spellings

The new project must use validated path components and filesystem metadata.

#### 11. Same-root comparison is also string-based
```python
str(self.root) == str(dest_dir.root)
```
Two paths may refer to the same filesystem object through different names.

Use metadata where relevant:
```
st_dev
st_ino
```
for directories.

#### 12. The rollback behavior is not transactionally safe

When `stop_on_fail=True`, copied destinations are deleted:
```python
dest_dir.remove_file_with_retries(dest_abs)
```
This assumes the copied destination is safe to remove.

But because final destination names are used directly, another process could have modified or replaced a file before rollback.

The new mover should never use “rollback by deleting published final files” as the core safety mechanism.

Instead:
```
all files remain temporary
verify complete job
publish each file according to policy
```
Whether publication is per-file or job-level should be explicit. A truly atomic publication of an entire multi-file dataset is not generally possible across ordinary filesystems, but a final manifest or completion marker can define when downstream processing may begin.

#### 13. Success tracking uses string matching

This logic is fragile and inefficient:
```python
for src_obj, _rel in files_to_copy:
    if str(src_obj) == src_path_str:
        self._last_copy_success_src.append(src_obj)
        break
```
A future should map directly to a typed file record, not a string.

For example:
```python
future_to_file: dict[Future[FileCopyResult], FileRecord]
```

#### 14. Shared mutable operation state is not safe for concurrent jobs

These are instance fields:
```python
self._last_copy_selected_src
self._last_copy_success_src
```
If the same `Directory` instance were used concurrently, operations could overwrite one another’s state.

The new service must keep state per job and per file, never in reusable storage adapter fields.

#### 15. `ThreadPoolExecutor()` queues every file immediately

For a directory with hundreds of thousands of files, this creates a future for every file.

That can consume substantial memory.

The dataset may contain only a manageable number of large files, but the design should avoid assuming that.

We can:

* Submit work incrementally
* Maintain a bounded in-flight future set
* Or use a queue feeding a fixed worker pool

Since job files will already be recorded in SQLite, workers can claim queued file records in batches.

#### 16. `stop_on_fail` does not actually stop immediately

All file futures are submitted before results are processed.

If one file fails, other copies continue running. Rollback happens only after all futures finish.

So the phrase “stop on fail” is inaccurate.

This is another reason to use explicit job-state semantics rather than a Boolean flag.

## How We Should Adapt the Good Parts
The new `FileCopyEngine` should retain the bounded copy loop:

```python
class BufferedFileCopyEngine:
    """Copy file content using a bounded binary buffer."""

    def copy(
        self,
        source: BinaryIO,
        destination: BinaryIO,
        *,
        buffer_size_bytes: int,
        progress_callback: CopyProgressCallback | None = None,
    ) -> CopyResult:
        """Copy all source bytes to the destination stream."""
```
Internally:
```python
bytes_copied = 0

while True:
    chunk = source.read(buffer_size_bytes)
    if not chunk:
        break

    destination.write(chunk)
    bytes_copied += len(chunk)

    if progress_callback is not None:
        progress_callback(bytes_copied)
```
But progress events should be throttled. Emitting an event for every 1 MiB chunk across 100 GB would generate roughly 102,400 events.

Progress updates should occur by:
```
time interval, such as every 5 seconds
or
byte threshold, such as every 256 MiB
```

## Recommended Durable Per-File Workflow
For each claimed file:
```
1. Load durable file record.
2. Verify claimed source identity.
3. Compute source hash if configured.
4. Persist source hash and fsync manifest.
5. Create temporary destination exclusively.
6. Copy with bounded buffer.
7. Flush and fsync destination.
8. Verify byte count and destination size.
9. Hash destination if configured.
10. Compare integrity values.
11. Atomically publish destination.
12. Record published destination state.
13. Revalidate claimed source identity.
14. Delete claimed source.
15. Record move complete.
```
On any failure:
```
retain claimed source
retain or quarantine temporary destination
record exact failure
schedule retry or manual intervention
```

## Recommended Concurrency Model

The good part of the current implementation is parallel file transfer. We should retain that with explicit limits.
```
BackgroundMoverService
    └── one bounded ThreadPoolExecutor

max_concurrent_jobs = 1
max_concurrent_files = 2
```
Workers should obtain file work from the repository:
```
QUEUED_FOR_HASH
QUEUED_FOR_COPY
QUEUED_FOR_VERIFY
QUEUED_FOR_CLEANUP
```
A job-level coordinator decides when the overall job is complete.

This is more recoverable than submitting all work from an in-memory list.

## Updated Requirements From `_directory.py`
#### L2 Copy Engine Requirements
##### L2-COPY-001

The software shall copy file content using bounded memory independent of file size.

##### L2-COPY-002

The copy buffer size shall be configurable and validated.

##### L2-COPY-003

The software shall support configurable bounded file-level concurrency.

##### L2-COPY-004

The software shall not derive copy concurrency from CPU count without an explicit configured upper bound.

##### L2-COPY-005

The software shall write copied content to a temporary destination name rather than the final published name.

##### L2-COPY-006

The software shall create temporary destination files using exclusive creation and shall not overwrite existing destination files.

##### L2-COPY-007

The software shall record the exact byte count written during each copy attempt.

##### L2-COPY-008

The software shall flush and synchronize temporary destination files before verification.

##### L2-COPY-009

A retry shall never cause deletion of the claimed source file.

##### L2-COPY-010

The initial release may restart a failed file copy from byte zero, provided the temporary destination is safely replaced or recreated.

#### L2 Retry Requirements
##### L2-RTY-001

The software shall classify failures before deciding whether to retry.

##### L2-RTY-002

The software shall not retry permanent filesystem errors solely because they derive from OSError.

##### L2-RTY-003

Retry attempt number, next retry time, and last failure shall be stored durably.

##### L2-RTY-004

Retry policy shall survive process and host restart.

##### L2-RTY-005

Retry delay and maximum attempts shall be configurable.

##### L2-RTY-006

The software shall support manual retry of retained jobs.

#### L2 Destination Safety Requirements
##### L2-DST-001

The software shall not delete an existing published destination file as part of normal transfer preparation.

##### L2-DST-002

An existing destination shall be either verified as identical and reused or treated as a collision.

##### L2-DST-003

A destination collision with differing content shall prevent source deletion.

##### L2-DST-004

Downstream consumers shall not treat temporary destination files as complete data.

##### L2-DST-005

The software shall provide a completion manifest or marker indicating that the job’s published files are ready for processing.

#### L2 Source Deletion Requirements
##### L2-DEL-001

The software shall delete only source files represented by durable claimed file records.

##### L2-DEL-002

The software shall never delete files discovered through a post-copy directory rescan merely because they were not reported as failed.

##### L2-DEL-003

The software shall revalidate source-file identity immediately before deletion.

##### L2-DEL-004

The software shall not delete a source file when destination verification is incomplete

## Final Assessment

The existing implementation is more mature than the earlier files alone suggested. Its strongest transferable ideas are:

* Concurrent per-file copying
* Bounded chunk reads
* Retry with backoff
* Stability checks immediately before copy
* Size validation
* Deleting only explicitly confirmed source files
* Avoiding broad post-copy source deletion
* Deepest-first empty-directory cleanup

Its main gaps relative to the new project are:

* No durable job state
* No restart recovery
* Direct writes to final destination names
* Destructive destination overwrite
* No `fsync()`
* No cryptographic integrity verification
* Broad and imprecise retry classification
* Unbounded default concurrency relative to storage capacity
* Shared mutable in-memory operation state
* No persistent retry state
* No temporary publication workflow
* No exact source identity check before deletion

So the correct approach is not to copy this class. We should preserve the **copy-loop, concurrency, retry, and selective-deletion lessons**, while rebuilding them inside a durable state-machine architecture.

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
