# Chat Capture
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
`Background File Mover` should be a **long-running background service** managed by `systemd`, not a child process that remains tied to the simulation orchestration script.

The orchestration scripts will submit a transfer request and receive an acknowledgment as soon as the files have been safely claimed. The mover service will then perform the 100 GB transfer independently while the simulation system prepares for the next run.

The basic flow is:

```
Simulation completes
        │
        ▼
Orchestration submits transfer request
        │
        ▼
Mover atomically claims/renames source files
        │
        ▼
Durable job manifest is written
        │
        ▼
Orchestration receives "accepted"
        │
        ▼
Simulation hosts can prepare next scenario
        │
        ▼
Background worker copies files
        │
        ▼
Optional integrity verification
        │
        ▼
Destination files are atomically published
        │
        ▼
Source files are deleted only after verification
```
The critical design principle is:
> A source file is never deleted merely because a copy operation was attempted. It is deleted only after the destination file has been successfully written, finalized, and verified according to the configured integrity policy.

## How the Simulation Script Starts the Transfer

### Long-Running Background Service
The recommended design is a service such as:
```
background-file-mover.service
```
The service runs continuously under `systemd`.
The simulation orchestration script submits a job:
```shell
file-mover submit \
    --source /recordings/scenario-001 \
    --destination /processing/scenario-001 \
    --scenario-id scenario-001
```
The command:

1. Validates the request.
2. Claims the files.
3. Creates a durable job record.
4. Signals the background service.
5. Returns immediately after the job is safely accepted.

The background service then processes the job independently.

This gives us:

* Restart recovery
* Centralized logging
* Controlled concurrency
* Durable job tracking
* Retry handling
* Clean shutdown behavior
* System-level service monitoring
* Protection against duplicate mover processes

## Communication Between the Orchestration Script and Mover
Because the application cannot use external runtime dependencies, there are two strong standard-library choices.
### Option 1: Filesystem Spool Queue
> Not the recommended option
The submit command writes a JSON job manifest into a spool directory:
```
/var/lib/file-mover/
├── queue/
├── processing/
├── completed/
├── failed/
├── manifests/
└── state/
```
A submitted job might initially appear as:
```
queue/8f6e4ad6-64f0-4ccd-bf71-92d96ef6190a.json
```
The service moves it atomically to:
```
processing/8f6e4ad6-64f0-4ccd-bf71-92d96ef6190a.json
```
This is simple, inspectable, and durable.

### Option 2: Unix Domain Socket Plus Durable State
> Recommended option
The submit command connects to the service using a Unix domain socket:
```
/run/file-mover/control.sock
```
The service accepts the request and records it in SQLite or a durable manifest.

This provides faster acknowledgment and clearer request-response behavior, but it adds some implementation complexity.

#### Recommended Combination
Use:

* A **Unix domain socket** for commands and immediate acknowledgments.
* A **SQLite database** for authoritative job state.
* JSON manifests for human-readable transfer inventories and integrity records.

All are available in the Python standard library:
* `socket`
* `sqlite3`
* `json`
* `hashlib`
* `pathlib`
* `shutil`
* `os`
* `logging`
* `threading`
* `concurrent.futures`
* `signal`
The first version could omit the socket and use a spool queue only. However, a socket-based control interface will provide a better operational experience.

## The Most Important Operation: Claiming the Files
You stated that the first step must rename the files so the simulation cannot overwrite them.

That is correct, but the rename behavior needs to be carefully defined.

#### Proposed Source Layout
Before submission:
```
/recordings/current-run/
├── host01.dat
├── host02.dat
├── host03.dat
├── host04.dat
├── host05.dat
└── host06.dat
```
After the mover claims the files:
```
/recordings/current-run/
├── .moving/
│   └── 8f6e4ad6-64f0-4ccd-bf71-92d96ef6190a/
│       ├── host01.dat
│       ├── host02.dat
│       ├── host03.dat
│       ├── host04.dat
│       ├── host05.dat
│       └── host06.dat
```
Alternatively, individual files could be renamed:
```
host01.dat
```
becomes:
```
host01.dat.moving.8f6e4ad6
```
I prefer moving the files into a job-specific staging directory because it:

* Preserves the original filenames.
* Groups all files belonging to one job.
* Makes recovery easier.
* Prevents the simulation from matching the original paths.
* Keeps partially transferred jobs clearly separated.
* Simplifies job inventory and cleanup.

#### Atomic Rename
When the source file and staging directory are on the same filesystem, Python can use:

```python
os.replace(source_path, claimed_path)
```

or:

```python
source_path.rename(claimed_path)
```
A rename within the same filesystem is normally atomic. The file is either visible at the old name or the new name.

However, renaming across two different mounted filesystems is not atomic and generally fails with `EXDEV`. Therefore:

* Claiming must happen entirely within the source filesystem.
* Transferring to the remote NFS filesystem must be implemented as copy, verify, publish, and delete.

The application should never use a blind `shutil.move()` and assume the entire operation is atomic.

## Preventing the Mover From Claiming Files Still Being Written
Renaming a file does not guarantee that another process no longer has it open. On Linux, an application that already has the file open can continue writing to the renamed inode.

Therefore, the mover needs an explicit readiness contract.

#### Best Readiness Contract

The orchestration system should submit the files only after all six recording processes have been stopped or have closed their recording files.

The submit command should receive an explicit statement equivalent to:
```
These files are complete and no further writes are expected.
```
#### Additional Defensive Checks

The mover can optionally verify that:

* File sizes remain unchanged over a configurable stabilization interval.
* Modification timestamps remain unchanged.
* Files are regular files.
* Files are not symbolic links unless explicitly permitted.
* Paths remain beneath approved source roots.
* No duplicate source inode appears twice in the job.
* The destination does not overlap the source.
* The total file inventory can be enumerated successfully.
* The entire six-host recording set is present when required.

A stability check might inspect each file twice:

```
Observation 1: size and mtime
Wait 5 seconds
Observation 2: size and mtime
```
If anything changed, submission fails or remains pending.

This is useful defense-in-depth, but it is not a replacement for the orchestration system's completion signal.

## Durable Job State
A transfer should be treated as a state machine.
```
SUBMITTED
    │
    ▼
VALIDATING
    │
    ▼
CLAIMING
    │
    ▼
CLAIMED
    │
    ▼
HASHING_SOURCE        optional
    │
    ▼
QUEUED
    │
    ▼
COPYING
    │
    ▼
VERIFYING
    │
    ▼
PUBLISHING
    │
    ▼
SOURCE_CLEANUP
    │
    ▼
COMPLETED
```
Failure states can include:
```
RETRY_WAIT
FAILED_RETAINED
CANCELLED_RETAINED
MANUAL_INTERVENTION
```
The word `RETAINED` is important: a failed transfer retains the claimed source data.

#### SQLite State
SQLite is part of Python and gives us transactional job state.

A basic job record could contain:
```
job_id
scenario_id
submission_time
source_root
destination_root
state
attempt_count
next_retry_time
hash_algorithm
verification_mode
file_count
total_bytes
bytes_copied
last_error
created_by
service_instance
```
A file record could contain:
```
job_id
relative_path
claimed_source_path
destination_path
temporary_destination_path
size_bytes
source_mtime_ns
source_hash
destination_hash
bytes_copied
state
attempt_count
last_error
```
This allows the service to restart and determine exactly which files were completed.

#### Why Both SQLite and a Manifest?

SQLite is best for machine-controlled state transitions. A manifest is best for data provenance and human inspection.

A manifest might look like:
```
{
  "schema_version": 1,
  "job_id": "8f6e4ad6-64f0-4ccd-bf71-92d96ef6190a",
  "scenario_id": "scenario-001",
  "created_at": "2026-07-10T15:30:00Z",
  "source_root": "/recordings/current-run/.moving/8f6e4ad6",
  "destination_root": "/processing/scenario-001",
  "integrity": {
    "enabled": true,
    "algorithm": "sha256"
  },
  "files": [
    {
      "relative_path": "host01.dat",
      "size_bytes": 18497327104,
      "sha256": "..."
    }
  ]
}
```
The manifest must be written before transfer starts when source hashing is enabled.

## Hashing and Integrity Modes
Hashing 100 GB of data adds a meaningful amount of source disk I/O. If files are read once to hash and again to copy, the application may read the entire dataset twice.

We should therefore define integrity levels.

#### Mode 1: Metadata Only
```
integrity_mode = metadata
```

Validate:

* File size
* Relative path
* File type
* Destination file size
* Expected number of files

This is fastest but does not detect every possible corruption.

#### Mode 2: Hash Before Copy
```
integrity_mode = source_hash
```
Process:

1. Hash source.
2. Write hash into the durable manifest.
3. Copy source.
4. Hash destination.
5. Compare hashes.
6. Delete source only after a match.

This exactly satisfies the stated requirement that the hash be written into a file before the file is moved.

It is also the most I/O-intensive mode.

#### Mode 3: Hash While Copying
```
integrity_mode = streaming_hash
```
Process:

1. Copy the file in chunks.
2. Update the hash as chunks are copied.
3. Write the completed source-stream hash into the manifest.
4. Re-read and hash the destination.
5. Compare.

This avoids separately reading the source before copying, but it does not write the completed hash before transfer begins. It therefore does not satisfy the strict interpretation of your initial requirement.

#### Mode 4: Source Hash Plus Destination Hash
This should be the highest-assurance mode and likely the production default when integrity verification is enabled:
```
hash source
persist manifest
copy
hash destination
compare
publish
delete source
```
#### Hash Algorithms
Using the standard library, appropriate choices include:

* `sha256`: strong and broadly understood.
* `sha512`: strong but produces larger values without a meaningful operational advantage here.
* `blake2b`: fast, secure, and available in hashlib.

I recommend:
```
Default algorithm: SHA-256
Configurable alternatives: BLAKE2b and SHA-512
```
Avoid MD5 as a primary integrity standard, even though accidental-corruption detection is not the same as cryptographic security.

## Safe Destination Publication
The mover should never copy directly to the final destination filename.

For example:
```
Final destination:
  /processing/scenario-001/host01.dat

Temporary destination:
  /processing/scenario-001/.partial-8f6e4ad6-host01.dat
```
The flow is:

1. Create a temporary destination file.
2. Copy data into it in bounded chunks.
3. Flush Python buffers.
4. Call `os.fsync()` on the file.
5. Verify file size.
6. Optionally calculate the destination hash.
7. Compare integrity information.
8. Atomically rename the temporary file to the final name.
9. Sync the destination directory where practical.
10. Mark the file as published.
11. Delete the claimed source file.
12. Sync the source staging directory where practical.

This prevents downstream processing from seeing a partially copied file.

The remote processing system should consume only finalized names, never `.partial-*` files.

## Copy Versus Move Semantics
Although the product is named Background File Mover, its internal implementation should behave as:
```
claim → copy → verify → publish → delete source
```
It should not behave as:
```
move and hope
```
The source and destination are separate NFS-mounted filesystems, so a true atomic cross-filesystem move does not exist.

The mover creates reliable move semantics through a carefully controlled transaction-like workflow.

## Recovery Behavior
Suppose the service crashes at different points.

#### Crash Before Claiming

Nothing changed. The request may be submitted again.

#### Crash During Claiming

The database and staging directory are inspected at startup. Files already claimed remain available and are reconciled with the job record.

The claim operation should be designed so each file transition is recorded.

#### Crash During Hashing

The source file remains in the claimed directory. Hashing restarts.

#### Crash During Copy

The partial destination remains under a temporary name.

On restart, version one should safely restart that file from byte zero. Resume-at-offset can be added later, but it complicates integrity, destination validation, and NFS behavior.

For 10–30 GB individual files, offset resume may be valuable. It should be a separately defined feature rather than assumed in the initial release.

#### Crash After Copy but Before Destination Publication

The service re-verifies the temporary destination and publishes it if valid.

#### Crash After Publication but Before Source Deletion

The service detects that the final destination exists, verifies it, and then removes the source.

#### Crash After Source Deletion but Before Job State Update

The destination is still authoritative. Recovery determines that the source is gone and the verified destination is present, then completes the state transition.

The software should make all recovery decisions from observable filesystem state plus durable records, not from assumptions about what the previous process probably completed.

## Duplicate and Collision Handling
The destination policy must be explicit.

Recommended default:

> Never overwrite an existing final destination file.

If the destination exists:

1. Compare its expected size.
2. Compare its hash when hashing is enabled.
3. If it exactly matches, mark the transfer idempotently complete.
4. If it differs, place the job into MANUAL_INTERVENTION.
5. Never silently replace the destination.

Useful collision policies may eventually include:
```
fail
verify-and-reuse
version
overwrite
```
For the initial production release, I recommend supporting only:
```
fail
verify-and-reuse
```
Overwriting creates too much risk for recorded simulation data.

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

## Initial L1 Requirements
L1 requirements describe what the system must accomplish.

#### L1-SYS-001 — Background Data Movement

The system shall transfer completed scenario recording files independently of the simulation orchestration process.

#### L1-SYS-002 — Simulation Availability

The system shall allow simulation preparation activities to resume after the recording files have been successfully claimed and the transfer job has been durably accepted.

#### L1-SYS-003 — Data Preservation

The system shall prevent source recording data from being deleted until the corresponding destination data has been successfully published and verified.

#### L1-SYS-004 — Source Protection

The system shall rename or relocate submitted source files within the source filesystem to prevent subsequent simulation runs from overwriting the submitted paths.

#### L1-SYS-005 — Interruption Recovery

The system shall recover incomplete transfer jobs following service termination, host restart, NFS interruption, or process failure.

#### L1-SYS-006 — Transfer Integrity

The system shall provide configurable integrity verification for transferred files.

#### L1-SYS-007 — Traceability

The system shall maintain a durable record of every submitted transfer job and every file included in each job.

#### L1-SYS-008 — Operational Control

The system shall provide interfaces to submit, inspect, retry, and diagnose transfer jobs.

#### L1-SYS-009 — Runtime Independence

The production application shall operate using only Python 3.10 standard-library modules.

#### L1-SYS-010 — Safe Failure

The system shall retain source data and provide actionable error information when a transfer cannot be safely completed.

## Example L2 Decomposition
L2 requirements describe software behavior supporting each L1 requirement.

Under **L1-SYS-003 Data Preservation**:

#### L2-SW-003.1

The software shall copy each claimed source file to a temporary destination filename.

#### L2-SW-003.2

The software shall flush and synchronize the destination file before publication.

#### L2-SW-003.3

The software shall validate the destination file size before publication.

#### L2-SW-003.4

When hashing is enabled, the software shall compare the configured source and destination hash values before source deletion.

#### L2-SW-003.5

The software shall publish a completed destination file using an atomic rename within the destination filesystem.

#### L2-SW-003.6

The software shall delete a claimed source file only after the corresponding destination file has reached the `PUBLISHED_VERIFIED` state.

#### L2-SW-003.7

The software shall retain the claimed source file if any copy, flush, synchronization, verification, or publication operation fails.

## Example L3 Decomposition
L3 requirements describe component-level implementation behavior.

Under **L2-SW-003.4**:

#### L3-INT-003.4.1

The `IntegrityVerifier` shall support SHA-256, SHA-512, and BLAKE2b using `hashlib`.

#### L3-INT-003.4.2

The `IntegrityVerifier` shall read files using a configurable bounded buffer.

#### L3-INT-003.4.3

The ManifestWriter shall persist the completed source hash before the `TransferCoordinator` begins copying that file when pre-copy hashing is configured.

#### L3-INT-003.4.4

The `ManifestWriter` shall write manifests through a temporary file and atomically replace the prior manifest.

#### L3-INT-003.4.5

The `FileTransferWorker` shall calculate the destination hash only after all destination bytes have been flushed.

#### L3-INT-003.4.6

The `IntegrityVerifier` shall compare hash values using `hmac.compare_digest()`.

#### L3-INT-003.4.7

A hash mismatch shall transition the file to INTEGRITY_FAILED, retain both source and temporary destination files, and prevent destination publication.

## Testing Strategy
“Fully Pytested” should include more than line coverage.

#### Unit Tests
Test individual components:

* Configuration validation
* Path validation
* Manifest serialization
* State transitions
* Retry calculations
* Hash calculation
* Collision policies
* Job submission validation
* Source-to-destination mapping
* Error classification

#### Integration Tests
Use temporary directories and actual files:

* Claim file atomically
* Copy and publish file
* Verify destination hash
* Delete source after success
* Preserve source after failure
* Recover a partial transfer
* Reuse an identical existing destination
* Reject a conflicting destination
* Handle nested directories
* Handle empty files
* Handle Unicode filenames
* Handle very long filenames within filesystem limits

#### Fault-Injection Tests
Inject failures at every destructive boundary:
```
After source claim
After job insert
During source hash
After manifest write
During copy
After destination flush
During destination hash
After destination publication
Before source deletion
After source deletion
Before final database update
```
Dependencies such as filesystem operations, clocks, and repository interfaces should be injectable so tests can raise deterministic exceptions.

#### Process Recovery Tests
Start the service, interrupt it, and restart it while jobs are in different states.

#### NFS-Representative Tests
A normal temporary directory cannot reproduce every NFS behavior. The test plan should distinguish:

* Automated local filesystem tests
* Deployment-environment NFS qualification tests

NFS qualification should test:

* Temporary loss of destination mount
* Stale file handles
* Server restart
* Permissions changing during transfer
* Destination capacity exhaustion
* File visibility after rename
* Concurrent client visibility
* Large-file behavior
* Sustained 100 GB transfer
* Multiple simultaneous simulation submissions

#### Quality Gates
Recommended development dependencies:
```
pytest
pytest-cov
ruff
mypy
```
Potential quality criteria:
```
100% requirements mapped to tests
At least 90% branch coverage
No unhandled Ruff violations
No known high-severity static-analysis findings
All public modules, classes, and methods documented
All recovery states exercised
All destructive transitions fault-injection tested
```
The most important metric is not raw coverage. It is whether every state transition and interruption boundary has a test.

## Recommended First Release Boundary
To deliver a dependable initial version rapidly, I would include:

* One systemd-managed background service
* CLI submission
* Directory and explicit-file-list submissions
* SQLite job state
* JSON transfer manifest
* Atomic source claiming
* Copy-to-temporary destination
* Configurable SHA-256 verification
* Atomic destination publication
* Source deletion after verification
* Automatic restart recovery
* Controlled retries
* One active job with configurable file concurrency
* Status, list, retry, and doctor commands
* Complete L1/L2/L3 traceability
* Unit, integration, recovery, and fault-injection tests

I would defer these until a later iteration:

* Partial-file byte-offset resume
* Network API
* Web dashboard
* Multi-host active/active mover services
* Dynamic bandwidth limiting
* Administrative cancellation during copy
* Metrics server
* Advanced scheduling and transfer prioritization
The resulting application is not simply a background file copy utility. It is a **durable transfer coordinator with transaction-like move semantics across two filesystems**. That distinction is what protects the recordings and allows the simulation environment to return to service quickly.

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

