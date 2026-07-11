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
/var/lib/swit-file-mover/
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
/run/swit-file-mover/control.sock
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
├── .swit-moving/
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
host01.dat.swit-moving.8f6e4ad6
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
  "source_root": "/recordings/current-run/.swit-moving/8f6e4ad6",
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
  /processing/scenario-001/.swit-partial-8f6e4ad6-host01.dat
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

The remote processing system should consume only finalized names, never `.swit-partial-*` files.

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
├── swit_file_mover/
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
    --scenario-id SWIT-2026-0710-001 \
    --source /recordings/scenario-001 \
    --destination /processing/scenario-001

# Submit an explicit list
file-mover submit \
    --scenario-id SWIT-2026-0710-001 \
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
            "/usr/bin/swit-file-mover",
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
state_directory = /var/lib/swit-file-mover
runtime_directory = /run/swit-file-mover
log_directory = /var/log/swit-file-mover
poll_interval_seconds = 2
shutdown_timeout_seconds = 60

[paths]
allowed_source_roots = /recordings
allowed_destination_roots = /processing
claim_directory_name = .swit-moving
partial_file_prefix = .swit-partial-

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
manifest_filename = swit-transfer-manifest.json

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