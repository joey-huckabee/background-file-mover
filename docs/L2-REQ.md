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

The software shall load runtime configuration using only C++11 standard-library and
POSIX functionality.

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

**Verification Method**: Inspection (I)

#### L2-ARC-007

All production code shall compile under `-std=c++11 -Wall -Wextra -Werror` on GCC 4.8.5
without warnings, and shall carry no per-object warning exemption.

**Parent**: L1-SYS-009

**Verification Method**: Test (T), Inspection (I)

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

Optional storage adapters shall not introduce dependencies beyond the C++11 standard
library, POSIX, and the vendored set recorded in `cpp/VENDORED.md`.

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

An interrupted partial destination — whether left by a crash (reconciled at startup) or by
an operator pause — shall be preserved for resume when resume is enabled, and removed when it
is disabled so the file restarts from byte zero instead of colliding with the exclusive
create.

**Parent**: L1-SYS-005

**Verification Method**: Test (T)

#### L2-RSM-003

A resumed partial that fails size or hash verification shall be discarded so the next
attempt restarts the file from zero; unverified bytes shall never be published.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

## ENV — Environment capability diagnostics

#### L2-ENV-001

The software shall verify that the required interpreter and platform capabilities are
present — an `AF_UNIX` socket, `fcntl` locking, SQLite WAL journaling, the configured hash
algorithm, Python 3.10 or later, and POSIX termination signals — and report a missing
required capability as a failure.

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

#### L2-ENV-002

The software shall report the availability of optional capabilities (kernel-assisted copy,
`O_NOFOLLOW`) as advisories, without failing the diagnostic when they are absent.

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

#### L2-ENV-003

A capability probe shall never crash the diagnostic; a probe that raises shall be reported
as an unavailable capability with its error detail.

**Parent**: L1-ROB-001

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

Clients and the service shall communicate over an HTTP/1.1 REST interface bound to the
configured address and port, defaulting to loopback.

**Parent**: L1-API-001

**Verification Method**: Test (T)

#### L2-CTL-002

Request and response bodies shall be UTF-8 JSON delimited by `Content-Length`; the
service shall not accept chunked request bodies and shall close the connection after
each response.

**Parent**: L1-API-003

**Verification Method**: Test (T)

#### L2-CTL-003

The software shall reject an over-large request body with HTTP 413 before allocating
its body.

**Parent**: L1-API-004

**Verification Method**: Test (T)

#### L2-CTL-004

A malformed control message shall never crash the service.

**Parent**: L1-SYS-010

**Verification Method**: Test (T)

#### L2-CTL-005

The software shall reject unknown routes with HTTP 404, unsupported methods on a known
route with HTTP 405, and malformed JSON with HTTP 400, each carrying a JSON error body.

**Parent**: L1-API-001

**Verification Method**: Test (T)

#### L2-CTL-006

The control server shall run on a thread pool separate from the transfer workers.

**Parent**: L1-SYS-008

**Verification Method**: Inspection (I)

#### L2-CTL-007

The software shall fail to start with a diagnosable error, rather than binding
silently or partially, when the configured address and port are already in use.

**Parent**: L1-API-006

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

The software shall expose service status and aggregate job statistics at
`GET /api/status`.

**Parent**: L1-OBS-002

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

#### L2-CTL-013

The REST interface shall expose `POST /api/jobs`, `GET /api/jobs`,
`GET /api/jobs/{id}`, `GET /api/status`, and `GET /`.

**Parent**: L1-API-002

**Verification Method**: Test (T)

#### L2-CTL-014

Route handlers shall be pure functions of request and job-manager view, unit-testable
without opening a socket.

**Parent**: L1-API-001

**Verification Method**: Test (T), Inspection (I)

#### L2-CTL-015

The software shall survive hostile HTTP input — oversized headers, invalid methods,
truncated requests, and non-HTTP bytes — by responding with an error status or closing
the connection, never by terminating.

**Parent**: L1-ROB-001

**Verification Method**: Test (T)

#### L2-CTL-016

The software shall not implement TLS in-process, and shall document the reverse-proxy
termination path for deployments requiring encrypted transport.

**Parent**: L1-API-005

**Verification Method**: Inspection (I)

## JOB — Durable job state

#### L2-JOB-001

The software shall persist every job durably in SQLite. Per-file records are deferred
to v1.1 with `L1-SYS-003` and `L1-SYS-006`.

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

**Parent**: L1-OBS-002

**Verification Method**: Test (T)

#### L2-JOB-007

The durable job record and the job manifest shall record consistent job metadata — the
same creation time and the same integrity policy (mode and hash algorithm) — for every
accepted job. Deferred to v1.1 with `L1-SYS-006`; there is no manifest at v1.0.0.

**Parent**: L1-SYS-007

**Verification Method**: Test (T)

#### L2-JOB-008

The state database shall reside on a local filesystem. The software shall reject a
configured state path that resolves onto a network filesystem, because SQLite's locking
depends on POSIX advisory locks that NFS implements unreliably.

**Parent**: L1-SYS-007

**Verification Method**: Test (T)

#### L2-JOB-009

SQL and the vendored `sqlite3.h` shall be confined behind a repository interface; no
other translation unit shall include the database header or embed SQL.

**Parent**: L1-SYS-009

**Verification Method**: Inspection (I)

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

## CORE — Job model and state machine

#### L2-CORE-001

The core shall define the job state set and the legal-transition relation as pure
functions performing no I/O.

**Parent**: L1-SYS-022

**Verification Method**: Test (T)

#### L2-CORE-002

The core shall represent a job with identity, source path, destination path, state,
creation, update and finish timestamps, byte counters, and an error field.

**Parent**: L1-SYS-021

**Verification Method**: Test (T)

#### L2-CORE-003

The core shall apply state transitions atomically: an invalid request shall leave the
job unmodified.

**Parent**: L1-SYS-022

**Verification Method**: Test (T)

#### L2-CORE-004

The core shall accept timestamps from the caller and shall not read the system clock.

**Parent**: L1-OBS-003

**Verification Method**: Test (T), Inspection (I)

## JSON — Request and response codec

#### L2-JSON-001

The JSON codec shall be implemented by the project and shall not delegate parsing to a
third-party library.

**Parent**: L1-SYS-009

**Verification Method**: Inspection (I)

#### L2-JSON-002

The codec shall reject malformed input with a diagnosable error and shall never
terminate the process.

**Parent**: L1-ROB-001

**Verification Method**: Test (T)

#### L2-JSON-003

The parser shall accept only the strict subset defined in ADR-0009 and shall reject
every construct outside it, including trailing bytes after the top-level value,
duplicate member names, floating-point values, and embedded NUL characters.

**Parent**: L1-ROB-001

**Verification Method**: Test (T)

#### L2-JSON-004

The parser shall enforce bounded nesting depth, string length, member count, and total
input size, such that no input can exhaust the stack or address space.

**Parent**: L1-ROB-002

**Verification Method**: Test (T)

#### L2-JSON-005

The codec shall be verified against a third-party JSON conformance corpus and by
coverage-guided fuzzing, with every fuzzer finding retained as a regression case.

**Parent**: L1-ROB-002

**Verification Method**: Test (T)

## REN — Rename engine

#### L2-REN-001

The rename engine shall expand a configured template, supporting timestamp, sequence,
and original-name fields, into the target filename.

**Parent**: L1-SYS-013

**Verification Method**: Test (T)

#### L2-REN-002

The rename engine shall apply a configured collision policy when the target name
already exists.

**Parent**: L1-SYS-013

**Verification Method**: Test (T)

#### L2-REN-003

The rename engine shall operate only within a single filesystem and shall reject
cross-device renames.

**Parent**: L1-SYS-013

**Verification Method**: Test (T)

## MGR — Job manager and worker pool

#### L2-MGR-001

The manager shall dispatch queued jobs to a configured number of worker threads through
a mutex- and condition-variable-protected queue.

**Parent**: L1-SYS-017

**Verification Method**: Test (T)

#### L2-MGR-002

The manager shall drive every job state change exclusively through the CORE transition
function.

**Parent**: L1-SYS-022

**Verification Method**: Test (T), Inspection (I)

#### L2-MGR-003

The manager shall support clean shutdown: stop intake, drain or fail in-flight jobs,
and join all workers.

**Parent**: L1-SYS-018

**Verification Method**: Test (T)

## XFR — Transfer strategies

#### L2-XFR-001

Transfer strategies shall implement a common interface accepting source, destination,
and a progress callback.

**Parent**: L1-SYS-015

**Verification Method**: Test (T), Inspection (I)

#### L2-XFR-002

The copy strategy shall write to a temporary name, fsync, then rename to the final
name, so the destination never appears under its final name partially written.

**Parent**: L1-SYS-014

**Verification Method**: Test (T)

#### L2-XFR-003

The exec strategy shall launch the configured external command via `fork`/`execvp` with
an argv array, never through a shell, reap the child, and map exit codes to job errors.

**Parent**: L1-SYS-015

**Verification Method**: Test (T), Inspection (I)

#### L2-XFR-004

Every strategy failure shall produce a human-readable error string including `errno`
text where applicable.

**Parent**: L1-SYS-023

**Verification Method**: Test (T)

## DASH — Operator dashboard

#### L2-DASH-001

The dashboard shall be a single embedded HTML and JavaScript page polling
`GET /api/status` at a fixed interval.

**Parent**: L1-OBS-001

**Verification Method**: Demonstration (D)

#### L2-DASH-002

The dashboard shall function without external network resources.

**Parent**: L1-OBS-001

**Verification Method**: Test (T), Inspection (I)
