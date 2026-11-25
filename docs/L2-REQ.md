# L2 — Architectural Derivations

Level 2 requirements derive software behavior from the L1 system requirements. Each L2
has exactly one L1 **Parent** and a declared verification method. L2 requirements
use new Rust L3 IDs only where a test plan needs them; the earlier Python
`docs/L3-REQ.md` is retired history and its IDs are never reused. Live status is
tracked in `docs/TRACE-MATRIX.md`.

Every requirement statement is a normative **SHALL** obligation, including
imperative rewordings: “Publish…” means “The software shall publish…”.

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

Publish verified staging with same-filesystem no-clobber rename, or exclusive link/unlink when the rename flag is unsupported; preserve recoverable intermediate custody.

**Reworded 2026-11-22** (D02; previous wording in git history).

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-DPR-006

Automatic source removal requires move mode and a freshly verified committed set; separate confirmed deletion may remove held copies of delivered copy-mode or settled cancelled jobs, never producer originals.

**Reworded 2026-11-22** (D01; previous wording in git history).

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-DPR-007

The software shall retain the claimed source file if any copy, flush, synchronization,
verification, or publication operation fails.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

## CFG — Configuration

#### L2-CFG-001

The software shall load runtime configuration using the approved Rust dependency
graph and qualified platform interfaces.

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

Validate typed configuration at entry points and share runtime snapshots by immutable references; no distinct immutable validated Config type is promised.

**Reworded 2026-11-22** (D06; previous wording in git history).

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

Report the first configuration error rather than aggregate independent issues.

**Reworded 2026-11-22** (D07; previous wording in git history).

**Parent**: L1-SYS-010

**Verification Method**: Test (T)

#### L2-CFG-009

Return secret-safe textual configuration errors without promising uniform section/option/value/reason records or echoing offending values.

**Reworded 2026-11-22** (D07; previous wording in git history).

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

#### L2-CFG-010

Include selected option/range guidance where implemented, without promising complete valid-value context for every diagnostic.

**Reworded 2026-11-22** (D07; previous wording in git history).

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

#### L2-CFG-011

The software shall share a single option definition source between validation and
generated documentation.

**Parent**: L1-SYS-008

**Verification Method**: Inspection (I)

## EVT — Operational events

#### L2-EVT-001

Use advisory watch versions and progress snapshots rather than a general immutable operational-event bus.

**Reworded 2026-11-22** (D08; previous wording in git history).

**Parent**: L1-SYS-007

**Verification Method**: Test (T)

#### L2-EVT-002

Use one trusted SQLite-thread version callback without panic isolation and independent bounded SSE streams; general subscriber-failure isolation is not promised.

**Reworded 2026-11-22** (D08; previous wording in git history).

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

Identify jobs in aggregated progress snapshots and expose a representative per-job file index; version invalidations need not identify every transfer event.

**Reworded 2026-11-22** (D08; previous wording in git history).

**Parent**: L1-SYS-007

**Verification Method**: Test (T)

## CLI — Command-line interface

#### L2-CLI-001

Use the existing mode flags and standard Rust argv parser without a general short/long alias or log-level option contract.

**Reworded 2026-11-22** (D07; previous wording in git history).

**Parent**: L1-SYS-008

**Verification Method**: Test (T), Inspection (I)

#### L2-CLI-002

Use local mode flags for lifecycle/offline operations and approved HTTP APIs for producer submission and job operations.

**Reworded 2026-11-22** (D07; previous wording in git history).

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

The software shall preserve exact legacy stdout/stderr behavior with logging
OFF, without logging threads or filesystem effects. Command results and readiness
remain on stdout; foreground diagnostics/prompts remain on stderr and explicit
automation shall not require a terminal.

When explicitly enabled in configuration with a file path and non-off level,
the daemon shall send bounded, secret-safe leveled events to stderr/journal and
a private application-managed rotating file. Levels shall be error, warn, info
and debug; restart applies changes. Default file-family capacity shall be
approximately 1 GiB with oldest managed files rotated out. Logging shall neither
block transfer loops on sink I/O nor turn logging failures into transfer failures.
Info-mode transfer slowdown shall be at most 2% versus OFF under the reviewed
measurement method. Logging shutdown shall wait at most 250 ms total.

**Reworded 2026-11-23** (superseding D07 no-log-files clause after #108 revision;
settings settled 2026-11-25; previous wording in git history).

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

See [LOGGING-DESIGN.md](LOGGING-DESIGN.md) for custody, lossy queues, rotation,
shared-storage limits and performance acceptance. The original 2026-11-22 D07
ballot is historical; the no-managed-log-files clause was explicitly rejected.

#### L2-CLI-007

CLI overrides shall apply only to the current command or job and shall never modify the
configuration file.

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

#### L2-CLI-008

Submit recordings through producer HTTP; the local transfer-one command operates on an already accepted job.

**Reworded 2026-11-22** (D07; previous wording in git history).

**Parent**: L1-SYS-002

**Verification Method**: Test (T)

#### L2-CLI-009

Separate producer HTTP acceptance from asynchronous service delivery; do not promise a nonblocking submit CLI.

**Reworded 2026-11-22** (D07; previous wording in git history).

**Parent**: L1-SYS-002

**Verification Method**: Test (T)

#### L2-CLI-010

Print readable Display-based errors and return failure for top-level command errors; do not promise a traceback or top-level panic catcher.

**Reworded 2026-11-22** (D07; previous wording in git history).

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

Use pure core transitions and explicitly supplied concrete store/guard dependencies, without universal injectable filesystem/clock/delay/hash interfaces.

**Reworded 2026-11-22** (D06; previous wording in git history).

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

Use the pinned Rust fmt/Clippy and cargo-libc/glibc/ELF/native audit gates rather than a C++11/GCC compilation contract.

**Reworded 2026-11-22** (D06; previous wording in git history).

**Parent**: L1-SYS-009

**Verification Method**: Test (T), Inspection (I)

#### L2-ARC-008

Concurrent code shall pass under ThreadSanitizer, enforced in CI as a tier
separate from the AddressSanitizer build.

TSan and ASan cannot be combined in one binary, so this is a distinct job
rather than an additional flag. Data races are the failure class least likely
to be caught by a passing test suite: a race can be present for years and
observable only under a scheduler the test machine never produces.

**Parent**: L1-SYS-009

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

Validate each producer-listed path using descriptor-relative no-follow traversal; do not require a recursive discovery inventory.

**Reworded 2026-11-22** (D02; previous wording in git history).

**Parent**: L1-SYS-004

**Verification Method**: Test (T)

#### L2-POSIX-003

Keep earlier durable claims and reservations when a later listed file cannot be claimed; withhold whole-set handoff instead of rolling back custody.

**Reworded 2026-11-22** (D02; previous wording in git history).

**Parent**: L1-SYS-004

**Verification Method**: Test (T)

#### L2-POSIX-004

Preserve the first durable path/index order and accept order-independent replay; identity sorting does not reorder custody.

**Reworded 2026-11-22** (D02; previous wording in git history).

**Parent**: L1-SYS-007

**Verification Method**: Test (T)

#### L2-POSIX-005

Reject reserved components in explicit producer paths at any depth, rather than exclude them during discovery.

**Reworded 2026-11-22** (D02; previous wording in git history).

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

Authorize automatic cleanup only after set verification; separate confirmed deletion of eligible delivered or settled cancelled jobs may count an already absent held copy as deleted.

**Reworded 2026-11-22** (D01; previous wording in git history).

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

Run direct rustix/POSIX storage effects in supervised children rather than a general storage capability interface.

**Reworded 2026-11-22** (D06; previous wording in git history).

**Parent**: L1-SYS-001

**Verification Method**: Inspection (I)

#### L2-STO-002

The initial release shall ship POSIX source and destination adapters for local and NFS
filesystems.

**Parent**: L1-SYS-001

**Verification Method**: Test (T)

#### L2-STO-003

Support the concrete POSIX workflow; an object-storage adapter is not part of the current interface contract.

**Reworded 2026-11-22** (D06; previous wording in git history).

**Parent**: L1-SYS-001

**Verification Method**: Inspection (I)

#### L2-STO-004

Identify stored objects with POSIX device/inode/owner/size/time/link facts; do not promise object-storage identities.

**Reworded 2026-11-22** (D06; previous wording in git history).

**Parent**: L1-SYS-007

**Verification Method**: Inspection (I)

#### L2-STO-005

Optional storage adapters shall use the approved pinned Rust dependency graph
and qualified platform interfaces; new dependencies require explicit approval.

**Parent**: L1-SYS-009

**Verification Method**: Inspection (I)

## COPY — Copy engine

> **Parenting note (2026-08-05).** `L2-COPY-001`, `002`, `003`, and `011` were
> reparented from `L1-SYS-001` to `L1-SYS-003`. They describe a copy engine, and
> `L1-SEC-007` forbids building one at v1.0.0 — but `L1-SYS-001` is Active, so
> the trace matrix counted them in v1.0.0 scope and reported four requirements
> as owed that could not be satisfied without violating another requirement.
> This is the same class of contradiction caught earlier with `L1-SYS-015`.
>
> `L1-SYS-003` is Deferred and already parents `L2-COPY-005/006/008/009`, so the
> four now sit with the rest of the copy family. The v1.0.0 denominator falls
> from 226 to 222.
>
> `L2-COPY-004` deliberately stays under `L1-SYS-001`. Despite its COPY prefix it
> constrains concurrency generally — "shall not derive concurrency from CPU count
> without an explicit cap" — and that applies to the C4 worker pool, which is
> built and shipping. It is a live v1.0.0 obligation, not a deferred one.

#### L2-COPY-001

The software shall copy files using a bounded-memory read/write loop.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-COPY-002

The software shall use a configurable and validated copy buffer size.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-COPY-003

The software shall use configurable, bounded per-file concurrency.

**Parent**: L1-SYS-003

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

**Out of scope for the first release (approved 2026-11-22, D04).**

The software may use a kernel-assisted file copy when configured and available, and shall
fall back to the bounded buffered copy without failing the transfer when it is not.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

## BWL — Bandwidth limiting

#### L2-BWL-001

**Out of scope for the first release (approved 2026-11-22, D04).**

The software shall support a configurable maximum aggregate copy throughput, expressed in
bytes per second, that bounds how fast source data is transferred. Because a
kernel-assisted copy cannot be paced from userspace, a non-zero limit shall force the
buffered copy strategy.

The second sentence was carried up from the retired `L3-PY-011` when the Python
requirements were deleted. It is a constraint on the feature rather than on how the
feature was written, and without it an implementation can honour the limit for buffered
copies and silently ignore it whenever the kernel path is taken.

**Parent**: L1-SYS-001

**Verification Method**: Test (T)

#### L2-BWL-002

**Out of scope for the first release (approved 2026-11-22, D04).**

The maximum copy throughput shall be adjustable at runtime, through the control interface,
without restarting the service, and the new limit shall apply to transfers already in
progress.

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

#### L2-BWL-003

**Out of scope for the first release (approved 2026-11-22, D04).**

The throughput limit shall be enforced across all concurrent file copies in aggregate, not
independently per file.

**Parent**: L1-SYS-001

**Verification Method**: Test (T)

#### L2-BWL-004

**Out of scope for the first release (approved 2026-11-22, D04).**

A configured throughput limit of zero shall mean unlimited, imposing no throttling.

**Parent**: L1-SYS-001

**Verification Method**: Test (T)

## LIF — Job lifecycle control

#### L2-LIF-001

Cancellation preserves held source and incomplete destination data; deletion is a separate confirmed action.

**Reworded 2026-11-22** (D01; previous wording in git history).

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-LIF-002

Cancel cooperatively between delivery steps and settle only after active work exits; do not promise buffer-level interruption or pause.

**Reworded 2026-11-22** (D01; previous wording in git history).

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

#### L2-LIF-003

A cancelled job shall reach the terminal ``CANCELLED_RETAINED`` state with its source
retained.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

#### L2-LIF-004

**Out of scope for the first release (approved 2026-11-22, D04).**

The software shall provide pause and resume commands; a paused job shall perform no
further work until resumed, and resume shall return it to the runnable queue.

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

#### L2-LIF-005

Reject invalid core transitions without state change, never panicking or corrupting durable state; bulk cancellation skips unknown or finished jobs and reports its outcomes.

**Reworded 2026-11-22** (D01; previous wording in git history).

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

## RSM — Partial-file byte-offset resume

#### L2-RSM-001

**Out of scope for the first release (approved 2026-11-22, D04).**

The software shall be able to resume an interrupted file copy from the byte offset of its
fsynced partial destination rather than re-copying the file from byte zero. Where a
resume path truncates the partial destination, it shall truncate to the resume offset and
never to zero, so an already-copied prefix is preserved.

The second sentence was carried up from the retired `L3-PY-012`. Truncating to zero on
resume is the specific mistake that turns a resume feature into a slower version of
starting over, and it is not excluded by the sentence above it.

**Parent**: L1-SYS-005

**Verification Method**: Test (T)

#### L2-RSM-002

**Out of scope for the first release (approved 2026-11-22, D04).**

An interrupted partial destination — whether left by a crash (reconciled at startup) or by
an operator pause — shall be preserved for resume when resume is enabled, and removed when it
is disabled so the file restarts from byte zero instead of colliding with the exclusive
create.

**Parent**: L1-SYS-005

**Verification Method**: Test (T)

#### L2-RSM-003

**Out of scope for the first release (approved 2026-11-22, D04).**

A resumed partial that fails size or hash verification shall be discarded so the next
attempt restarts the file from zero; unverified bytes shall never be published.

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

## ENV — Environment capability diagnostics

#### L2-ENV-001

Check mandatory capabilities at startup and refuse unsafe or unsupported operation, rather than emit a complete optional-capability diagnostic report.

**Reworded 2026-11-22** (D07; previous wording in git history).

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

#### L2-ENV-002

Treat no-follow access as mandatory and omit an optional kernel-copy capability report because that backend is not used.

**Reworded 2026-11-22** (D07; previous wording in git history).

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

#### L2-ENV-003

Return startup capability refusals through ordinary error handling without requiring a separate capability-probe command.

**Reworded 2026-11-22** (D07; previous wording in git history).

**Parent**: L1-ROB-001

**Verification Method**: Test (T)

## RTY — Retry and error classification

#### L2-RTY-001

The software shall classify an operational error before deciding to retry.

**Parent**: L1-SYS-010

**Verification Method**: Test (T)

#### L2-RTY-002

Send binding refusals straight to review and bound other unclassified delivery failures to three persisted failures before review; retries grant no new effect authority.

**Reworded 2026-11-22** (D05; previous wording in git history).

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

Use a fixed three-failure review limit with capacity delays of 30/60 seconds before subsequent attempts and five seconds for other failures.

**Reworded 2026-11-22** (D05; previous wording in git history).

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

Require verified committed delivery for automatic removal; exempt separately confirmed deletion of eligible delivered or settled cancelled held copies.

**Reworded 2026-11-22** (D01; previous wording in git history).

**Parent**: L1-SYS-003

**Verification Method**: Test (T)

## CTL — Control plane

#### L2-CTL-001

Require explicit binding and audience-separated transports: loopback plaintext, native HTTPS or protected Unix producer ingress, with private local control.

**Reworded 2026-11-22** (D09; previous wording in git history).

**Parent**: L1-API-001

**Verification Method**: Test (T)

#### L2-CTL-002

Use length/close framing for ordinary JSON exchanges; allow approved admin documents/assets and open SSE streams their respective content/framing.

**Reworded 2026-11-22** (D09; previous wording in git history).

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

Use ordinary API route/method/schema errors where applicable, with producer-audience forbidden-route precedence to prevent disclosure.

**Reworded 2026-11-22** (D09; previous wording in git history).

**Parent**: L1-API-001

**Verification Method**: Test (T)

#### L2-CTL-006

Isolate bounded asynchronous HTTP, fixed TLS executors, local lifecycle IPC and supervised transfer work instead of requiring one control-server thread pool.

**Reworded 2026-11-22** (D06; previous wording in git history).

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

#### L2-CTL-017

Receive TERM/interrupt through Tokio signal tasks and request lifecycle stop in task context, not through an application C signal-flag protocol. Only async-signal-safe code shall run in OS signal handlers, including handlers installed by dependencies.

**Reworded 2026-11-22** (D06; previous wording in git history).

**Parent**: L1-SYS-008

**Verification Method**: Test (T), Inspection (I)

#### L2-CTL-018

The service shall ignore `SIGPIPE` process-wide.

The default disposition terminates the process. A REST control plane writes to
sockets that clients may close at any moment, so the default turns a
disconnecting client into a killed daemon — remotely, without authentication,
and while a transfer is in flight. Writes must fail with `EPIPE` and be handled
where they occur.

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

#### L2-CTL-019

The service shall provide a configuration-validation mode that loads and
validates the configuration, reports any faults with the loader's
`file:line: message` diagnostic, and exits without starting the service,
without opening the durable store, and without binding a socket.

This is what lets a deployment gate on configuration before the service is
allowed to touch anything: run it as systemd `ExecStartPre` and an invalid
config fails the unit outright instead of half-starting a daemon that then
dies with its state directory already created. The capability diagnostics
requirements (`L2-ENV-001..003`) share the same parent.

**Parent**: L1-SYS-008

**Verification Method**: Test (T), Demonstration (D)

#### L2-CTL-020

Startup shall bring subsystems up in dependency order and shall stop everything
already started if any later step fails; shutdown shall tear down in the
reverse order, ending with the durable store synced and closed.

A failure partway through startup that leaves a worker pool running or a socket
bound produces a process that is neither serving nor exited — the state an
operator cannot diagnose and systemd will not restart correctly.

**Parent**: L1-SYS-008

**Verification Method**: Test (T)

#### L2-CTL-010

Expose audience-separated job, retention, health and lifecycle reads instead of a universal api/status aggregate.

**Reworded 2026-11-22** (D09; previous wording in git history).

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

Expose the approved versioned producer/operator/admin routes and admin documents without unversioned aliases or audience merging.

**Reworded 2026-11-22** (D09; previous wording in git history).

**Parent**: L1-API-002

**Verification Method**: Test (T)

#### L2-CTL-014

Separate typed dispatch, validation and concrete effects; handlers may perform stream, store and session operations and need not be pure functions.

**Reworded 2026-11-22** (D06; previous wording in git history).

**Parent**: L1-API-001

**Verification Method**: Test (T), Inspection (I)

#### L2-CTL-015

The software shall survive hostile HTTP input — oversized headers, invalid methods,
truncated requests, and non-HTTP bytes — by responding with an error status or closing
the connection, never by terminating.

**Parent**: L1-ROB-001

**Verification Method**: Test (T)

#### L2-CTL-016

Terminate producer HTTPS in Rust with mTLS authorization; keep explicit loopback HTTP separate and never fall back to it after a TLS error.

**Reworded 2026-11-22** (D09; previous wording in git history).

**Parent**: L1-API-005

**Verification Method**: Inspection (I)

## JOB — Durable job state

#### L2-JOB-001

Persist accepted jobs and per-file custody transactionally before returning admission; preserve them on same-state recovery, without the historical per-file-record deferral.

**Reworded 2026-11-22** (D03; previous wording in git history).

**Parent**: L1-SYS-007

**Verification Method**: Test (T)

#### L2-JOB-002

The software shall enable foreign keys, WAL journaling, and synchronous=FULL on the
state database.

**Parent**: L1-SYS-007

**Verification Method**: Test (T)

#### L2-JOB-003

Serialize repository commands through one SQLite-owner thread and its connection, rather than per-caller connections.

**Reworded 2026-11-22** (D03; previous wording in git history).

**Parent**: L1-SYS-007

**Verification Method**: Test (T)

#### L2-JOB-004

Refuse incompatible or migration-required state at ordinary startup; upgrades use the explicit guarded offline command.

**Reworded 2026-11-22** (D03; previous wording in git history).

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

Share recording identity, file paths and measured integrity facts between stored jobs and completion manifests; use fixed SHA-256 without shared creation-time or integrity-mode fields.

**Reworded 2026-11-22** (D03; previous wording in git history).

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

#### L2-JOB-010

Keep bounded latest per-job problems and compose status from phases, cancellation and retry/review; problems are not an iff-FAILED field.

**Reworded 2026-11-22** (D03; previous wording in git history).

**Parent**: L1-SYS-023

**Verification Method**: Test (T)

#### L2-JOB-011

Require explicit fresh-source enrollment and guarded state preparation; never silently replace an enrolled source’s missing database.

**Reworded 2026-11-22** (D03; previous wording in git history).

**Parent**: L1-SYS-016

**Verification Method**: Test (T)

#### L2-JOB-012

The software shall fail to start, with a diagnosable error identifying the damage, when
the state store is present but corrupt. Corruption shall never be silently skipped or
partially recovered.

A crash leaving work incomplete is expected and is handled by `L1-SYS-016`. A store that
cannot be read is a different condition: continuing past it would silently discard the
record of jobs whose source files may still exist.

**Parent**: L1-SYS-007

**Verification Method**: Test (T)

#### L2-JOB-013

Persist claim intent before payload relocation; read-only observation and empty private-area allocation may precede intent. If intent cannot be recorded, the software shall perform no payload relocation.

**Reworded 2026-11-22** (D02; previous wording in git history).

**Parent**: L1-SEC-003

**Verification Method**: Test (T)

#### L2-JOB-014

Roll back failed admission transactions, but retain admitted jobs and uncertain post-effect facts for phase-aware reconciliation; do not require successful review writes on failed storage. Never delete the source or continue silently after an unrecorded effect.

**Reworded 2026-11-22** (D02; previous wording in git history).

**Parent**: L1-SEC-002

**Verification Method**: Test (T)

#### L2-JOB-015

The job sequence shall be durable and monotonic across restarts.

Job identifiers and the `{seq}` rename-template field both derive from it. A
counter held only in memory repeats after every restart, so identifiers
collide and `{seq}` templates silently fall into collision handling rather than
producing distinct names.

**Parent**: L1-SEC-003

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

Persist the accepted inventory and claim identities in SQLite; write COMMITTED.json on completed delivery, not submission.

**Reworded 2026-11-22** (D03; previous wording in git history).

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

Restart interrupted copies in fresh owned attempts; preserve stale partials until safe post-delivery cleanup or separate confirmed deletion.

**Reworded 2026-11-22** (D01; previous wording in git history).

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

Keep pure recording transitions in the core and cancellation, retry/review and cleanup transitions in the store, with explicit effect boundaries.

**Reworded 2026-11-22** (D03; previous wording in git history).

**Parent**: L1-SYS-022

**Verification Method**: Test (T)

#### L2-CORE-002

Split durable job facts between core recording and SQLite records, with live progress outside the core.

**Reworded 2026-11-22** (D03; previous wording in git history).

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

Use pinned serde_json with strict project duplicate-key, UTF-8/BOM, trailing-data and field-shape rules for producer decoding.

**Reworded 2026-11-22** (D06; previous wording in git history).

**Parent**: L1-SYS-009

**Verification Method**: Inspection (I)

#### L2-JSON-002

The codec shall reject malformed input with a diagnosable error and shall never
terminate the process.

**Parent**: L1-ROB-001

**Verification Method**: Test (T)

#### L2-JSON-003

The parser shall accept only the route-specific schema and approved strictness rules in the REST contract bundle and shall reject
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

**Out of scope for the first release (approved 2026-11-22, D04).**

The rename engine shall expand a configured template, supporting timestamp, sequence,
and original-name fields, into the target filename.

**Parent**: L1-SYS-013

**Verification Method**: Test (T)

#### L2-REN-002

**Out of scope for the first release (approved 2026-11-22, D04).**

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

Use a configured bounded delivery-worker set and active-job exclusion rather than a condition-variable queue.

**Reworded 2026-11-22** (D06; previous wording in git history).

**Parent**: L1-SYS-017

**Verification Method**: Test (T)

#### L2-MGR-002

Route recording transitions through the core and cancellation, retry and cleanup transitions through the store.

**Reworded 2026-11-22** (D03; previous wording in git history).

**Parent**: L1-SYS-022

**Verification Method**: Test (T), Inspection (I)

#### L2-MGR-003

The manager shall support clean shutdown: stop intake, drain or fail in-flight jobs,
and join all workers.

**Parent**: L1-SYS-018

**Verification Method**: Test (T)

## XFR — Transfer strategies

#### L2-XFR-001

The transfer operation shall expose a common interface accepting source, destination,
and an optional progress callback.

The interface is retained even though v1.0.0 offers a single strategy: the
cross-filesystem copy returns at v1.1, and an interface introduced then would be a
change to every caller rather than an addition behind one.

**Parent**: L1-SYS-015

**Verification Method**: Test (T), Inspection (I)

#### L2-XFR-002

Copy into staging, sync and verify before no-clobber rename or exclusive link/unlink publication.

**Reworded 2026-11-22** (D02; previous wording in git history).

**Parent**: L1-SYS-014

**Verification Method**: Test (T)

**Note:** cross-filesystem copying exists in the current Rust mover. Delivery
copies to destination-side staging, verifies it and publishes without clobber;
this requirement is active, not conditional on future copy support. The
publication-mechanism rewording also applies to L2-NFS-007, while actual
cross-client visibility and server durability remain separately qualified
obligations. Historical deferral wording is preserved in git history.

> **L2-XFR-003 was removed and its identifier is retired.** It required an
> external-command transfer strategy launched via `fork`/`execvp`. The transfer protocol requires this boundary: a
> free-text command in configuration makes the configuration file executable, and
> delegating the move voids the commit-point guarantees of `L1-SEC-001` and
> `L1-SEC-002`.
>
> The identifier is not reused, so a reference to `L2-XFR-003` in older material
> resolves to this note rather than to an unrelated requirement. It is deliberately
> not a heading, so the trace matrix does not count a removed obligation as a live one.
>
> The subprocess discipline it specified — argv array, substitution into elements,
> never a shell — is retained unconditionally as `L2-SEC-008`, governing any
> subprocess this project ever spawns.

#### L2-XFR-004

Report bounded operation, numeric errno and safe-action diagnostics without native error text; use dashboard labels for known errno values.

**Reworded 2026-11-22** (D07; previous wording in git history).

**Parent**: L1-SYS-023

**Verification Method**: Test (T)

## DASH — Operator dashboard

#### L2-DASH-001

Serve an embedded authenticated dashboard using admin reads and advisory SSE updates instead of api/status polling.

**Reworded 2026-11-22** (D08; previous wording in git history).

**Parent**: L1-OBS-001

**Verification Method**: Demonstration (D)

#### L2-DASH-002

The dashboard shall function without external network resources.

**Parent**: L1-OBS-001

**Verification Method**: Test (T), Inspection (I)

#### L2-DASH-003

The dashboard shall insert every dynamic value into the DOM through
`textContent` or `createTextNode` only, and shall never assign to `innerHTML`.

Filesystem paths and error strings reach the page from the API, and a path is
attacker-influenced in exactly the way the `L1-SEC-*` invariants already
assume: whoever can create a file can choose its name. A name containing
markup becomes script execution in an operator's browser the moment it is
assigned to `innerHTML`, and the operator holds the one account with authority
over this service. Text-node insertion removes the injection path rather than
escaping it, so there is no escaping function left to get wrong.

**Parent**: L1-OBS-001

**Verification Method**: Test (T), Inspection (I)

## SEC — Filesystem security discipline

Derived from `docs/CYBERSECURITY.md`. These are the controls that make the
`L1-SEC-*` invariants hold against an adversary who can win races and a
privileged agent that can stall or delete files.

#### L2-SEC-001

All filesystem operations on managed trees shall be file-descriptor relative —
`openat`, `renameat2`, `fstatat`, `unlinkat`, `mkdirat`, `fchmod` — against
directory descriptors opened at operation start and held for its duration.
Path-based operations on managed trees are prohibited.

**Parent**: L1-SEC-002

**Verification Method**: Inspection (I), Test (T)

#### L2-SEC-002

After every `openat`, the software shall `fstat` the descriptor and verify
device, inode, and file type against the preceding `fstatat`, aborting the
entry on mismatch.

`O_NOFOLLOW` stops a symlink; it does not stop a different regular file being
swapped in between the classify and the open. This check closes that residual
window.

**Parent**: L1-SEC-002

**Verification Method**: Test (T)

#### L2-SEC-003

Directory opens shall use `O_RDONLY | O_DIRECTORY | O_NOFOLLOW`, and file opens
within managed trees shall use `O_NOFOLLOW`. Symbolic links shall be rejected
by default and never followed.

**Parent**: L1-SEC-005

**Verification Method**: Inspection (I), Test (T)

#### L2-SEC-004

The software shall classify every entry by type before acting on it and shall
act only on regular files. Directories, symlinks, FIFOs, sockets, and device
nodes shall be rejected and logged.

A device node smuggled into a watched directory is a classic escalation trick
against a privileged mover.

**Parent**: L1-SEC-005

**Verification Method**: Test (T)

#### L2-SEC-005

Before starting a move, the software shall verify on an open descriptor that
the source is a regular file owned by a configured trusted UID, and that its
parent directory is not world-writable without the sticky bit. A violation
shall abort the move with a logged, actionable error.

**Parent**: L1-SEC-005

**Verification Method**: Test (T)

#### L2-SEC-006

Externally supplied path names shall be validated before use in any system
call: absolute after canonicalization, no `..` components, no control
characters, no embedded newlines.

**Parent**: L1-ROB-001

**Verification Method**: Test (T)

#### L2-SEC-007

Same-filesystem moves shall use `renameat2` with `RENAME_NOREPLACE`, invoked
through `syscall(2)` where the libc wrapper is absent. Where the flag is
unsupported by the kernel or filesystem, the software shall fall back to
`linkat` followed by `unlinkat`, which fails `EEXIST` on an existing target.

**Parent**: L1-SEC-006

**Verification Method**: Test (T)

#### L2-SEC-008

Never invoke system(3) or a shell; launch external processes with Rust Command and an explicit argument vector rather than a prescribed fork/execvp implementation.

**Reworded 2026-11-22** (D06; previous wording in git history).

**Parent**: L1-SEC-005

**Verification Method**: Inspection (I), Test (T)

#### L2-SEC-009

Every potentially blocking system call on a managed file shall be subject to a
configurable timeout. Expiry shall fail only the affected entry, logged as
suspected external interference with the measured duration and file size.

Latency correlating with file size is the on-access-scan fingerprint. There is
no errno for "a scanner is holding this open" — timing is the only signal
available.

**Parent**: L1-SEC-004

**Verification Method**: Test (T)

#### L2-SEC-010

A stalled or failed entry shall not block forward progress of other queued
moves or of durable-state processing.

**Parent**: L1-SEC-004

**Verification Method**: Test (T)

#### L2-SEC-011

When recovery finds neither the source nor the destination present, the
software shall mark the entry failed-external, log at high severity, and shall
not retry automatically.

The naive invariant says exactly one path exists. Quarantine by endpoint
security produces the state that invariant calls impossible, so it is a third
modeled outcome rather than an assertion failure.

**Parent**: L1-SEC-004

**Verification Method**: Test (T)

#### L2-SEC-012

The durable state store shall reside in a directory writable only by the
service account, be opened `O_NOFOLLOW`, and every recorded path shall be
validated before recovery acts on it.

**Parent**: L1-SEC-003

**Verification Method**: Inspection (I), Test (T)

#### L2-SEC-013

On SELinux platforms, delivered objects shall carry the destination tree's
default context, applied before the commit rename so that no wrongly labeled
object is ever observable at the final path. Source contexts shall not be
preserved. On AppArmor platforms, the software shall run under a profile
enumerating exactly the paths it may access.

**Parent**: L1-SEC-005

**Verification Method**: Test (T), Demonstration (D)

#### L2-SEC-014

The software shall ship a hardened systemd unit: `ProtectSystem=strict`,
`ReadWritePaths=` limited to managed trees and the state directory,
`NoNewPrivileges=yes`, `PrivateTmp=yes`, `ProtectHome=yes`, a trimmed
`CapabilityBoundingSet=`, a dedicated service account, and `UMask=0077`.

**Parent**: L1-SYS-012

**Verification Method**: Inspection (I)

#### L2-SEC-015

Any cryptographic hashing used for file verification shall use SHA-256 or
stronger. Non-cryptographic checksums are permitted for torn-write framing
only, never for file verification.

**Parent**: L1-SEC-005

**Verification Method**: Inspection (I)

#### L2-SEC-016

At startup the software shall query local endpoint-security on-access
configuration where available, and log whether managed trees are covered by
scanning exclusions.

This verifies that a requested ePO exclusion actually landed on this host,
rather than being assumed from the policy request.

**Parent**: L1-SEC-004

**Verification Method**: Demonstration (D)

## NFS — network filesystem behavior

The recordings arrive on a shared NFS mount by design, so NFS is a primary
target rather than an edge case. Generic guidance defers this to "a design
review of its own"; section 4 of `docs/CYBERSECURITY.md` is that review, and
these are its outcomes.

#### L2-NFS-001

Support for `RENAME_NOREPLACE` shall be detected at runtime, per managed
filesystem, by attempting the operation and observing `EINVAL`, `ENOSYS`, or
`EOPNOTSUPP`. Capability shall never be inferred from kernel version alone, and
the selected strategy shall be logged per tree.

**Parent**: L1-SEC-006

**Verification Method**: Test (T)

#### L2-NFS-002

The `linkat` plus `unlinkat` fallback shall be treated as a primary tested
path, not an exceptional one.

NFS supports no `RENAME_NOREPLACE`, so on the mount where the recordings live
this fallback is what production runs on every move.

**Parent**: L1-SEC-001

**Verification Method**: Test (T)

#### L2-NFS-003

Recovery shall disambiguate an existing destination by comparing recorded
source identity against the object present, distinguishing an interrupted
`linkat`/`unlinkat` pair from a genuine collision.

The pair is not atomic together: a crash between them leaves both names
pointing at one inode. Treating that as a collision — the obvious reading —
would fail a move that had in fact all but completed.

**Parent**: L1-SEC-003

**Verification Method**: Test (T)

#### L2-NFS-004

`ESTALE` shall be classified as an expected retryable condition rather than a
fault.

**Parent**: L1-SEC-004

**Verification Method**: Test (T)

#### L2-NFS-005

The software shall tolerate NFS silly-rename artifacts (`.nfsXXXX`) appearing
in managed directories and shall not treat them as unexpected entries.

Unlinking a file another client holds open does not remove it; the server
renames it in place.

**Parent**: L1-SEC-004

**Verification Method**: Test (T)

#### L2-NFS-006

The identity verification of `L2-SEC-002` shall be documented as weakened over
NFS, where the compared attributes are served from the client attribute cache,
and the qualification checklist shall record the mount options in effect.

**Parent**: L1-SEC-002

**Verification Method**: Inspection (I)

#### L2-NFS-007

Use same-filesystem staging, sync/verification, no-clobber rename or exclusive link/unlink and set-manifest commitment; qualify cross-client visibility separately instead of prescribing two-hop rename.

**Reworded 2026-11-22** (D02; previous wording in git history).

**Parent**: L1-SYS-014

**Verification Method**: Test (T)

#### L2-NFS-008

Durability claims shall be treated as server-side, and shall be qualified on a
real export rather than on a local temporary directory.

`fsync` on NFS commits to the server, but close-to-open consistency means other
clients observe data only after close, and directory `fsync` is weakly defined.

**Parent**: L1-SEC-002

**Verification Method**: Demonstration (D)
