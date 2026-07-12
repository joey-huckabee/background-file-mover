# L2 — Architectural Derivations

Level 2 requirements derive software behavior from the L1 system requirements. Each L2
has exactly one L1 **Parent** and a declared verification method. L2 requirements
decompose further into L3 implementation obligations (`docs/L3-REQ.md`). Live status is
tracked in `docs/TRACE-MATRIX.md`.

Verification method codes: **T** = Test, **I** = Inspection, **A** = Analysis,
**D** = Demonstration.

---

## DPR — Data preservation

#### L2-DPR-001

The software shall copy each claimed source file to a temporary destination filename.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-DPR-002

The software shall flush and synchronize the destination file before publication.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-DPR-003

The software shall validate the destination file size before publication.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-DPR-004

When hashing is enabled, the software shall compare the configured source and
destination hash values before source deletion.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-DPR-005

The software shall publish a completed destination file using an atomic rename within
the destination filesystem.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-DPR-006

The software shall delete a claimed source file only after the corresponding
destination file has reached the published-and-verified state.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-DPR-007

The software shall retain the claimed source file if any copy, flush, synchronization,
verification, or publication operation fails.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

## CFG — Configuration

#### L2-CFG-001

The software shall load runtime configuration using only Python standard-library
functionality.

**Parent**: L1-SYS-009

**Verification Method**: Test (T), Inspection (I)

#### L2-CFG-002

The software shall reject unrecognized configuration sections and options.

**Parent**: L1-SYS-010

**Verification Method**: Test (T)

#### L2-CFG-003

The software shall reject missing required configuration values.

**Parent**: L1-SYS-010

**Verification Method**: Test (T)

#### L2-CFG-004

The software shall validate numeric ranges and cross-field constraints before starting
the service.

**Parent**: L1-SYS-010

**Verification Method**: Test (T)

#### L2-CFG-005

The software shall represent validated runtime configuration using immutable typed
objects.

**Parent**: L1-SYS-009

**Verification Method**: Test (T)

#### L2-CFG-006

The software shall not begin processing transfer jobs when configuration validation
fails.

**Parent**: L1-SYS-010

**Verification Method**: Test (T)

#### L2-CFG-007

The software shall provide a command that validates configuration without starting the
transfer service.

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

#### L2-CFG-008

The software shall report all configuration issues together rather than failing on the
first.

**Parent**: L1-SYS-010

**Verification Method**: Test (T)

#### L2-CFG-009

Each reported configuration issue shall identify the section, option, offending value,
and reason.

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

#### L2-CFG-010

Configuration errors shall provide valid-option and range context to the operator.

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

#### L2-CFG-011

The software shall share a single option definition source between validation and
generated documentation.

**Parent**: L1-SYS-008

**Verification Method**: Inspection (I)

## EVT — Operational events

#### L2-EVT-001

The software shall represent operational events using typed immutable event records.

**Parent**: L1-SYS-007

**Verification Method**: Test (T)

#### L2-EVT-002

The software shall isolate event-subscriber failures so one subscriber cannot prevent
delivery to other subscribers.

**Parent**: L1-SYS-007

**Verification Method**: Test (T)

#### L2-EVT-003

The software shall not rely on event subscribers to perform authoritative job-state
transitions.

**Parent**: L1-SYS-007

**Verification Method**: Test (T)

#### L2-EVT-004

The event publisher shall support concurrent event emission safely.

**Parent**: L1-SYS-007

**Verification Method**: Test (T)

#### L2-EVT-005

Each transfer event shall include a job identifier and, when applicable, a file
identifier.

**Parent**: L1-SYS-007

**Verification Method**: Test (T)

## CLI — Command-line interface

#### L2-CLI-001

The command-line interface shall be built with argparse using only the standard library.

**Parent**: L1-SYS-008

**Verification Method**: Test (T), Inspection (I)

#### L2-CLI-002

The CLI shall provide separate commands for submission, status, listing, retry,
diagnostics, recovery, statistics, and service execution.

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

#### L2-CLI-003

The CLI shall return documented, stable exit codes.

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

#### L2-CLI-004

The CLI shall support human-readable and machine-JSON output.

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

#### L2-CLI-005

The CLI shall write machine output to stdout with no interleaved logging.

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

#### L2-CLI-006

The CLI shall write diagnostics and logs to stderr.

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

#### L2-CLI-007

CLI overrides shall apply only to the current command or job and shall never modify the
configuration file.

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

#### L2-CLI-008

The submit command shall succeed only after the job and its complete claimed file
inventory have been durably recorded.

**Parent**: L1-SYS-002

**Verification Method**: Test (T)

#### L2-CLI-009

The submit command shall not wait for hashing, copying, verification, or source
deletion before returning.

**Parent**: L1-SYS-002

**Verification Method**: Test (T)

#### L2-CLI-010

The CLI shall convert top-level exceptions into a controlled nonzero exit code with a
logged traceback.

**Parent**: L1-SYS-010

**Verification Method**: Test (T)

#### L2-CLI-011

The CLI entry point shall parse the real argument vector and shall not contain
hard-coded commands.

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

## ARC — Architecture and construction

#### L2-ARC-001

The software shall separate configuration loading, validation, infrastructure
construction, and service construction into distinct stages.

**Parent**: L1-SYS-010

**Verification Method**: Inspection (I)

#### L2-ARC-002

The software shall construct components through explicit typed mappings and shall not
use constructor reflection.

**Parent**: L1-SYS-010

**Verification Method**: Inspection (I)

#### L2-ARC-003

The software shall support injection of filesystem, clock, delay, repository, and
integrity dependencies.

**Parent**: L1-SYS-010

**Verification Method**: Test (T)

#### L2-ARC-004

The software shall not fall back to reduced validation on error and shall fail closed.

**Parent**: L1-SYS-010

**Verification Method**: Test (T)

#### L2-ARC-005

The software shall not use assertions for operational or data-safety validation.

**Parent**: L1-SYS-010

**Verification Method**: Inspection (I)

#### L2-ARC-006

The application factory shall construct only the components required by the invoked
command or mode.

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

## FS — Filesystem identity and claiming

#### L2-FS-001

The software shall record the device identifier and inode of each source file before
claiming.

**Parent**: L1-SYS-004

**Verification Method**: Test (T)

#### L2-FS-002

The software shall verify the same device identifier and inode after claiming.

**Parent**: L1-SYS-004

**Verification Method**: Test (T)

#### L2-FS-003

The software shall reject a claim when the source and the claim destination reside on
different filesystems.

**Parent**: L1-SYS-004

**Verification Method**: Test (T)

#### L2-FS-004

The software shall not follow symbolic links during inventory or claiming unless
explicitly approved.

**Parent**: L1-SYS-004

**Verification Method**: Test (T)

#### L2-FS-005

The software shall validate that all inventoried paths remain beneath the approved
source roots.

**Parent**: L1-SYS-004

**Verification Method**: Test (T)

## POSIX — POSIX storage behavior

#### L2-POSIX-001

The software shall require source roots to pre-exist and shall never auto-create them.

**Parent**: L1-SYS-004

**Verification Method**: Test (T)

#### L2-POSIX-002

The software shall reject symbolic links encountered during inventory.

**Parent**: L1-SYS-004

**Verification Method**: Test (T)

#### L2-POSIX-003

The software shall reject the entire inventory if any listed path is unreadable.

**Parent**: L1-SYS-004

**Verification Method**: Test (T)

#### L2-POSIX-004

The software shall enumerate files in a deterministic sorted relative-path order.

**Parent**: L1-SYS-007

**Verification Method**: Test (T)

#### L2-POSIX-005

The software shall exclude claim directories from source discovery.

**Parent**: L1-SYS-004

**Verification Method**: Test (T)

#### L2-POSIX-006

The software shall capture a single metadata observation per file covering device,
inode, type, size, modified-time-ns, and link count.

**Parent**: L1-SYS-004

**Verification Method**: Test (T)

#### L2-POSIX-007

The software shall verify file identity immediately before claiming and immediately
before deletion.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-POSIX-008

The software shall create temporary destination files exclusively, without following
symbolic links.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-POSIX-009

The software shall flush and fsync a temporary destination file before verification and
publication.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-POSIX-010

The software shall publish atomically only within the destination filesystem.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-POSIX-011

The software shall fsync the destination directory after publication where supported.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-POSIX-012

The software shall preserve original errno specificity for NFS error classification.

**Parent**: L1-SYS-005

**Verification Method**: Test (T)

## CLN — Cleanup and source retention

#### L2-CLN-001

The software shall make source cleanup idempotent.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-CLN-002

During recovery, a missing source shall be treated as completed cleanup only after the
published destination is verified.

**Parent**: L1-SYS-005

**Verification Method**: Test (T)

#### L2-CLN-003

The software shall not report a non-empty claim directory as removed.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-CLN-004

The software shall route unexpected remaining files to manual intervention.

**Parent**: L1-SYS-010

**Verification Method**: Test (T)

#### L2-CLN-005

The software shall not delete a claimed path whose device or inode differs from the
recorded identity.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

## STO — Storage abstraction

#### L2-STO-001

The transfer workflow shall depend on capability interfaces rather than raw POSIX
operations.

**Parent**: L1-SYS-001

**Verification Method**: Inspection (I)

#### L2-STO-002

The initial release shall ship POSIX source and destination adapters for local and NFS
filesystems.

**Parent**: L1-SYS-001

**Verification Method**: Test (T)

#### L2-STO-003

The storage interfaces shall permit a future object-storage adapter without changing
the durable workflow.

**Parent**: L1-SYS-001

**Verification Method**: Inspection (I)

#### L2-STO-004

Typed file metadata shall support both POSIX identity and future object identity.

**Parent**: L1-SYS-007

**Verification Method**: Inspection (I)

#### L2-STO-005

Optional storage adapters shall not weaken the standard-library-only core.

**Parent**: L1-SYS-009

**Verification Method**: Inspection (I)

## COPY — Copy engine

#### L2-COPY-001

The software shall copy files using a bounded-memory read/write loop.

**Parent**: L1-SYS-001

**Verification Method**: Test (T)

#### L2-COPY-002

The software shall use a configurable and validated copy buffer size.

**Parent**: L1-SYS-001

**Verification Method**: Test (T)

#### L2-COPY-003

The software shall use configurable, bounded per-file concurrency.

**Parent**: L1-SYS-001

**Verification Method**: Test (T)

#### L2-COPY-004

The software shall not derive concurrency from CPU count without an explicit cap.

**Parent**: L1-SYS-001

**Verification Method**: Inspection (I)

#### L2-COPY-005

The software shall write copied data to a temporary destination name.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-COPY-006

The software shall create the temporary destination exclusively and never overwrite an
existing final destination.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-COPY-007

The software shall record the exact number of bytes copied.

**Parent**: L1-SYS-006

**Verification Method**: Test (T)

#### L2-COPY-008

The software shall flush and synchronize copied data before verification.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-COPY-009

A retry shall never delete the claimed source file.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-COPY-010

The first release may restart a file from byte zero provided the temporary destination
is safely replaced.

**Parent**: L1-SYS-005

**Verification Method**: Test (T)

#### L2-COPY-011

The software may use a kernel-assisted file copy when configured and available, and shall
fall back to the bounded buffered copy without failing the transfer when it is not.

**Parent**: L1-SYS-001

**Verification Method**: Test (T)

## BWL — Bandwidth limiting

#### L2-BWL-001

The software shall support a configurable maximum aggregate copy throughput, expressed in
bytes per second, that bounds how fast source data is transferred.

**Parent**: L1-SYS-001

**Verification Method**: Test (T)

#### L2-BWL-002

The maximum copy throughput shall be adjustable at runtime, through the control interface,
without restarting the service, and the new limit shall apply to transfers already in
progress.

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

#### L2-BWL-003

The throughput limit shall be enforced across all concurrent file copies in aggregate, not
independently per file.

**Parent**: L1-SYS-001

**Verification Method**: Test (T)

#### L2-BWL-004

A configured throughput limit of zero shall mean unlimited, imposing no throttling.

**Parent**: L1-SYS-001

**Verification Method**: Test (T)

## LIF — Job lifecycle control

#### L2-LIF-001

The software shall provide an operator command to cancel a transfer job; cancellation
shall retain the claimed source data and discard only the incomplete temporary
destination.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-LIF-002

The software shall stop an in-flight copy for a pause or cancel request cooperatively, at
a safe buffer boundary, without a forced kill and without losing already-durable data.

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

#### L2-LIF-003

A cancelled job shall reach the terminal ``CANCELLED_RETAINED`` state with its source
retained.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-LIF-004

The software shall provide pause and resume commands; a paused job shall perform no
further work until resumed, and resume shall return it to the runnable queue.

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

#### L2-LIF-005

Lifecycle commands shall reject an unknown job or an invalid state transition with a
typed error, never panicking or corrupting durable state.

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

## RSM — Partial-file byte-offset resume

#### L2-RSM-001

The software shall be able to resume an interrupted file copy from the byte offset of its
fsynced partial destination rather than re-copying the file from byte zero.

**Parent**: L1-SYS-005

**Verification Method**: Test (T)

#### L2-RSM-002

Startup recovery shall preserve interrupted partial destinations for resume when resume is
enabled, and remove them when it is disabled.

**Parent**: L1-SYS-005

**Verification Method**: Test (T)

#### L2-RSM-003

A resumed partial that fails size or hash verification shall be discarded so the next
attempt restarts the file from zero; unverified bytes shall never be published.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

## RTY — Retry and error classification

#### L2-RTY-001

The software shall classify an operational error before deciding to retry.

**Parent**: L1-SYS-010

**Verification Method**: Test (T)

#### L2-RTY-002

The software shall not retry a permanent error merely because it is an OSError.

**Parent**: L1-SYS-010

**Verification Method**: Test (T)

#### L2-RTY-003

The software shall durably persist attempt count, next-retry time, and last failure.

**Parent**: L1-SYS-007

**Verification Method**: Test (T)

#### L2-RTY-004

Retry state shall survive a service restart.

**Parent**: L1-SYS-005

**Verification Method**: Test (T)

#### L2-RTY-005

The software shall use a configurable bounded backoff delay and maximum attempt count.

**Parent**: L1-SYS-010

**Verification Method**: Test (T)

#### L2-RTY-006

The software shall support manual retry of a retained failed job.

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

## DST — Destination publication

#### L2-DST-001

The software shall not delete an existing published destination during transfer
preparation.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-DST-002

An existing destination shall be either verified-identical and reused or treated as a
collision.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-DST-003

A differing destination collision shall prevent source deletion.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-DST-004

Downstream consumers shall never observe a temporary file as a complete recording.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-DST-005

The software shall provide a completion manifest or marker signalling destination
readiness.

**Parent**: L1-SYS-007

**Verification Method**: Test (T)

## DEL — Source deletion

#### L2-DEL-001

The software shall delete only files that have durable claimed records.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-DEL-002

The software shall never delete files discovered via a post-copy rescan.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-DEL-003

The software shall revalidate file identity immediately before deletion.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-DEL-004

The software shall not delete a source when destination verification is incomplete.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

## CTL — Control plane

#### L2-CTL-001

The CLI and service shall communicate over an AF_UNIX stream socket.

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

#### L2-CTL-002

Control messages shall be UTF-8 JSON framed with a 4-byte big-endian length prefix.

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

#### L2-CTL-003

The software shall reject an over-large control message before allocating its body.

**Parent**: L1-SYS-010

**Verification Method**: Test (T)

#### L2-CTL-004

A malformed control message shall never crash the service.

**Parent**: L1-SYS-010

**Verification Method**: Test (T)

#### L2-CTL-005

The software shall reject unknown control commands with a typed error response.

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

#### L2-CTL-006

The control server shall run on a thread pool separate from the transfer workers.

**Parent**: L1-SYS-008

**Verification Method**: Inspection (I)

#### L2-CTL-007

The software shall recover a stale control socket safely: refuse to start if a live
instance is listening, remove only a confirmed-dead socket, and never delete a
non-socket file.

**Parent**: L1-SYS-010

**Verification Method**: Test (T)

#### L2-CTL-008

The software shall permit only one running service instance via a singleton lock.

**Parent**: L1-SYS-010

**Verification Method**: Test (T)

#### L2-CTL-009

The service shall handle SIGTERM and SIGINT and shut down cleanly.

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

#### L2-CTL-010

The software shall provide a health command that reports service status.

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

#### L2-CTL-011

The service shall notify the service manager when it is ready to serve and when it is
stopping.

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

#### L2-CTL-012

The service shall emit a periodic liveness signal so the service manager can detect and
restart a hung service.

**Parent**: L1-SYS-010

**Verification Method**: Test (T)

## JOB — Durable job state

#### L2-JOB-001

The software shall persist every job and its files durably in SQLite.

**Parent**: L1-SYS-007

**Verification Method**: Test (T)

#### L2-JOB-002

The software shall enable foreign keys, WAL journaling, and synchronous=FULL on the
state database.

**Parent**: L1-SYS-007

**Verification Method**: Test (T)

#### L2-JOB-003

The software shall give each thread its own database connection.

**Parent**: L1-SYS-007

**Verification Method**: Test (T)

#### L2-JOB-004

The software shall apply schema migrations idempotently at startup.

**Parent**: L1-SYS-005

**Verification Method**: Test (T)

#### L2-JOB-005

The software shall validate and enforce the allowed job state transitions.

**Parent**: L1-SYS-007

**Verification Method**: Test (T)

#### L2-JOB-006

The software shall query jobs by state and produce aggregate statistics.

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

## SUB — Submission and claiming

#### L2-SUB-001

Submission shall be idempotent by request id: a repeated request shall return the
original job without re-claiming.

**Parent**: L1-SYS-002

**Verification Method**: Test (T)

#### L2-SUB-002

Submission shall claim all source files and durably record the job before returning
accepted.

**Parent**: L1-SYS-002

**Verification Method**: Test (T)

#### L2-SUB-003

Submission shall reject an invalid or empty source inventory without claiming any file.

**Parent**: L1-SYS-004

**Verification Method**: Test (T)

#### L2-SUB-004

Submission shall write a durable manifest for the claimed set.

**Parent**: L1-SYS-007

**Verification Method**: Test (T)

#### L2-SUB-005

A submission failure shall retain any already-claimed source files.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

## REC — Recovery and scheduling

#### L2-REC-001

The software shall reconcile non-terminal jobs against the filesystem at startup.

**Parent**: L1-SYS-005

**Verification Method**: Test (T)

#### L2-REC-002

The software shall re-queue an interrupted in-progress job and remove its stale
temporary destination files.

**Parent**: L1-SYS-005

**Verification Method**: Test (T)

#### L2-REC-003

Reprocessing a recovered job shall skip files that are already fully moved, so recovery
is idempotent.

**Parent**: L1-SYS-005

**Verification Method**: Test (T)

#### L2-REC-004

The transfer scheduler shall process runnable jobs — queued, or retry-waiting whose
retry time has passed — up to the configured job concurrency.

**Parent**: L1-SYS-001

**Verification Method**: Test (T)
