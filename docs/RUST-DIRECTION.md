# Rust direction and next-session handoff

Recorded 2026-10-13 on `feature/rust-transfer-coordinator`. The user supplied
[CONVERSATION.md](../CONVERSATION.md) as the new direction. This supersedes the
earlier same-filesystem-only release scope and component-for-component port.
Preserve the conversation as design input; its claims about existing defects
are review leads, not verified findings merely because they appear there.

## Intended architecture

Design a durable transfer coordinator using Rust ownership, explicit effects,
bounded resources and established libraries. Preserve useful requirements and
crash/fault evidence without copying C++ internal architecture or temporary scope
restrictions. Use one executable, configuration file and systemd service.

The proposed architecture has an asynchronous coordinator, one scheduler state
owner, a dedicated local SQLite owner thread, bounded command/result channels,
and supervised filesystem workers as child processes of the same executable in
an internal worker mode. Reserve claim/reconciliation capacity. Coalesce progress
without starving durable acknowledgements. Process isolation cannot make stuck
NFS calls reliably cancellable: bound replacement workers and reconcile/fence
uncertain assignments before redispatch.

Four proposed crates have meaningful boundaries: `mover-core` for pure decisions,
`mover-store` for SQLite, `mover-fs` for filesystem effects, and `file-mover` for
API/coordination/operations. Use narrow fault-injection interfaces, not a generic
backend framework. A future object-storage protocol would have different semantics.

## Proposed protocol for review

[TRANSFER-PROTOCOL.md](TRANSFER-PROTOCOL.md) defines claim custody, copied-file
evidence, manifest commitment, cleanup authorization and crash reconciliation.
[REST-API-DRAFT.md](REST-API-DRAFT.md) proposes the producer submission/status
contract. Review the API and producer/consumer handoff before freezing the design.

The additive generator form identifies the generator and supplies a mover-visible
source directory/file names without selecting a destination. Startup configuration
routes the job to a default or per-generator destination, pinned at acceptance.
Retain the earlier explicit-root form for permitted advanced use. Mounted shares
use the filesystem protocol; S3 remains a separately qualified future adapter with
the same producer-facing milestones. See the additive Rust section of
[L1-REQ.md](L1-REQ.md#additive-rust-generator-and-delivery-requirements).

Generator file names may be relative subfolder paths; list files explicitly.
Preserve those relative paths inside each destination recording container,
including future S3 object-key prefixes. Only required folders are created;
empty/unlisted source directories are not transferred.
Producer sizes are optional assertions. The service measures and persists actual
sizes during claim before copying; this adds no payload read. Recording metadata
and per-file keys are optional in the generator body, with service-assigned IDs.

- Separate internal durable `Accepted` from confirmed `Claimed`; submission returns
  202 only after both. The recorder waits for 202, reuses paths, and need not poll
  or monitor delivery. Claimed-job replay returns 202 for the same key/job.
  Require completed files, closed writers,
  explicit handoff and idempotent submission; pathname changes do not stop writers.
- Record intent before effects, claim into a private source-filesystem namespace,
  copy into exclusively owned destination staging, verify, publish without clobber,
  commit the recording set, then authorize source cleanup.
- Publish an immutable completion manifest carrying file identities, sizes and
  integrity evidence. Consumers must honor it. Per-file publication is not an atomic
  transaction spanning a recording set, SQLite and multiple filesystems.
- Model applied, not-applied and uncertain/partially applied outcomes. Recovery
  requires operation ownership and content evidence, not merely an existing name.
  Cleanup requires a validated publication receipt.
- Keep local SQLite ownership, short WAL/FULL/foreign-key transactions, durable
  operation records and tested migrations. Assign disjoint source ownership across
  instances; local databases are not a distributed queue or fencing mechanism.
- Enforce approved roots/relative paths, descriptor-relative traversal, regular
  files, private namespaces, mount identity and qualified no-clobber capabilities.
  Do not require openat2 or newer-kernel-only facilities.

**Agreed integrity plan:** calculate the source hash during copying, then reread
destination staging and compare its hash/size before publication and cleanup.
The normal path is 3N logical data I/O: source read + destination write + destination
reread. A 100 GB file copies 100 GB of payload and accounts for roughly 300 GB of
logical I/O, not 300 GB necessarily crossing the network. There is no separate
source prehash pass. Persist the completed digest after copying and retain the
claimed source for interruption recovery. See [INTEGRITY-DESIGN.md](INTEGRITY-DESIGN.md)
for sequencing, source immutability, recovery and the future S3 checksum distinction.
Two workers and 4 MiB buffers are benchmark suggestions, not production decisions.
Resumable chunks and optimized copy paths follow a correct retained-source baseline.

## Packages and deployment

E1–E5 qualify exact configurations of bundled rusqlite/SQLite, rustix, Serde/JSON,
httparse and Tokio. Tokio retains signal-hook-registry transitively. The broader
conversation proposes Axum/Tower/Tower HTTP, sha2, thiserror, tracing/subscriber,
clap, uuid, sd-notify and rust-ini. These and proposed development tools are
candidates, not qualified dependencies. Review features, graphs and licenses.
Axum would replace the application-maintained HTTP surface; preserve E4 framing
evidence and strict JSON/API tests when framework extractors are introduced.
Use [DASHBOARD-DESIGN-NOTES.md](DASHBOARD-DESIGN-NOTES.md) for the offline/security
requirements and status-query/polling findings when designing the operator UI.

Retain x86_64 GNU/glibc 2.22, baseline CPU settings, no musl, modern controlled
builds and pinned SLES-equivalent container validation. The user's builder remains
unqualified; cargo-zigbuild is the reference. The conversation's actual-host test
suggestion does not override the user's explicit container-only preference.
Preserve the [NFS fixture note](NFS-TEST-FIXTURE.md). Old kernel/CPU and storage
durability coverage remain limited. Disconnected builds need toolchain/targets,
native prerequisites and notices as well as vendored Cargo sources.
Use [INTEGRATION-DESIGN-NOTES.md](INTEGRATION-DESIGN-NOTES.md) for deployment
checks, confinement gaps and fail-closed harness requirements.

## Resume here

Every Rust build/test now requires [RUST-SLES-GATE.md](RUST-SLES-GATE.md): reference
cargo-zigbuild GNU/glibc 2.22 compilation, ELF audit and exact debug/release test
execution in pinned SLES userspace. Run `python scripts/check-rust-sles.py`;
host-only tests do not satisfy validation, even for early pure-core increments.

The generator contacts a remote mover. Review
[GENERATOR-REGISTRATION-DRAFT.md](GENERATOR-REGISTRATION-DRAFT.md) for proposed
registered tokens, scoped REST enrollment and explicitly restricted tokenless
profiles, including optional local clients. The user confirmed the remote mover
has access to the source NFS mount; claim directly on that shared filesystem.
Confirm mount-path mapping and qualify custody/durability on the export.
Enrollment uses the selected one-time setup key. Registration/token work is
explicitly deferred so core/storage/transfer testing can proceed incrementally.
Tokenless trust and detailed issuance recovery remain later design work.

Grouping recording containers by generator is startup-configurable via
`group_by_generator`. False keeps the earlier flat-container layout; true adds
the validated generator component above each recording. Snapshot layout at
acceptance and preserve submitted subfolders under either setting.

Destination consumers can and must wait for a valid `COMMITTED.json`, published
only after every required file is verified and published. The user confirmed this
set-visibility contract; finalize the versioned manifest schema before code.

Confirmed missing files retry for a configurable period, then block for operator
review. Persist deadlines across replays/restarts; retain partial claims and
reservations, never skip files, and withhold 202. The agreed default is five
minutes (`missing_file_retry_window_seconds = 300`), configured at startup and
recorded per job. The recorder retries temporary failures/timeouts with the same
ID, but stops/logs correction or review-required errors. Without 202 it must
keep source paths untouched; stopping client retries does not cancel accepted work.

The recorder can retain and reuse a unique submission ID across retries. Use
`submission_id` in generator JSON, scoped to generator identity; replay identical
details and return the original job/202 after claiming. New recordings get new IDs.

The user confirmed automatic source deletion after verified whole-recording
commitment, configurable at startup. Production move profiles enable
`delete_source_after_commit`; initial development profiles disable it. Require
both recorded job policy and current service authorization for deletion. Retain
sources/accounting when disabled; do not reopen or restore producer paths.

Destination outages do not stop the agreed 202-after-claim producer handoff
while safe source/local persistence and configured retention capacity remain.
Queue delivery to the pinned destination, retain sources and expose the outage
to operators. Finalize backlog limits, source-space margins and retry timing.

Experiments are stopped at the user's request. E6/thiserror is **unrun** and must
not automatically be next. The dependency-free first Rust core slice is now in
`rust/crates/mover-core`; [RUST-INCREMENT-01.md](RUST-INCREMENT-01.md) records its
ten passing WSL tests and limits. `mover-store` now adds local SQLite acceptance/
replay; [RUST-INCREMENT-02.md](RUST-INCREMENT-02.md) records its evidence.
`mover-fs` adds protected local source claims and interrupted-effect reconciliation;
[RUST-INCREMENT-03.md](RUST-INCREMENT-03.md) records the setup and limits. Only
all-file durable receipts yield Ready202 and release reservations. The local
`file-mover` executable now implements JSON submission/202-after-claim and health;
see [RUST-INCREMENT-04.md](RUST-INCREMENT-04.md) for configuration, bounds and
missing-deadline evidence. The single-file local `--transfer-one` command now
copies/hashes, independently verifies, publishes without clobber and recovers
interrupted effects; see [RUST-INCREMENT-05.md](RUST-INCREMENT-05.md).
Automatic local multi-file delivery and durable completion manifests are now
implemented; see [RUST-INCREMENT-06.md](RUST-INCREMENT-06.md) for budgets,
recovery and scope. Read-only operator job status is implemented in
[RUST-INCREMENT-07.md](RUST-INCREMENT-07.md). Audited delivery resume is implemented
in [RUST-INCREMENT-08.md](RUST-INCREMENT-08.md). Audited missing-file deadline reset
is implemented in [RUST-INCREMENT-09.md](RUST-INCREMENT-09.md). Read-only retention
accounting is implemented in [RUST-INCREMENT-10.md](RUST-INCREMENT-10.md).
The user approved deferring offline inspection and repair at the completed
increment-10 boundary. Prioritize worker isolation and controlled NFS testing;
use that evidence to decide which additional operator tools are necessary.
[Increment 11](RUST-INCREMENT-11.md) isolates background copying and verification
in supervised children without giving those children database access.
[Increment 12](RUST-INCREMENT-12.md) adds source observation/allocation/claiming
and file/completion-manifest publication children.
[Increment 13](RUST-INCREMENT-13.md) isolates runtime destination opening/locks,
staging allocation/restarts, manifest steps and custody checks in recording
sessions. Source replay scope checks also run in children.
[Increment 14](RUST-INCREMENT-14.md) measures hard-mount startup blocking,
inherited lock lifetime and metadata interruption/recovery.
[Increment 15](RUST-INCREMENT-15.md) isolates source singleton bootstrap, transfers
the locked descriptor and qualifies startup shutdown before NFS restoration.
The user requested retaining the opt-in NFS qualification capability permanently;
see [NFS-QUALIFICATION.md](NFS-QUALIFICATION.md) and
[increment 16](RUST-INCREMENT-16.md). Diagnose the controlled baseline's handoff
and publication refusals, then qualify outages and stable root/export ownership
before enabling production NFS. Preserve
[RETENTION-REPAIR-DESIGN.md](RETENTION-REPAIR-DESIGN.md) for future repair
prerequisites, leaving registration deferred and deletion disabled.
Production namespace/mount
qualification remain future work; do not deploy the local claim prototype on NFS.
The fifteen milestones retain useful release obligations.

[Increment 17](RUST-INCREMENT-17.md) adds owned no-clobber link/unlink recovery
and bounded worker diagnostics after measuring the fixture rename refusals.
The normal-operation NFS baseline now passes in both profiles. Next qualify
Rust runtime interruption, coordinator death and stable root/export ownership;
production NFS and source cleanup remain disabled.

[Increment 18](RUST-INCREMENT-18.md) adds retained qualification-only pause controls
and real Rust worker outage/interruption cases, including actual child custody
after coordinator death. Next expand source-read/verification and longer outage
qualification, stable export authorization and cross-client ownership. Production
NFS and source cleanup remain disabled.

[Increment 19](RUST-INCREMENT-19.md) qualifies source-read and verification-read
interruption in both profiles and adds [the scenario catalog](RUST-SCENARIOS.md),
with retrospective user explanations and six documentation deliverables.
Next qualify interrupted claim/file link intermediates, longer outages and stable
root/export authorization/cross-client ownership. Production NFS and deletion
remain disabled; update the catalog with each increment.

Next session: read this handoff, the protocol/API drafts, CONVERSATION.md,
[Increment 20](RUST-INCREMENT-20.md),
and [the scenario catalog](RUST-SCENARIOS.md). Maintain its stable user-situation
IDs, evidence boundaries and user-guide backlog with every increment. It includes
retrospective explanations for the already implemented local/API/recovery cases.
Also read
experiment results and the branch [review](BRANCH-REVIEW.md). Work through the
producer-facing Accepted/Claimed contract, reconcile requirements and refine
the proposed protocol using the agreed streaming-hash/destination-reread plan.
Revise the roadmap around four increments:

1. Core protocol, durable evidence and local persistence.
2. One recoverable cross-filesystem transfer with deletion disabled initially.
3. Gated cleanup, manifests, admission, worker isolation and operational diagnostics.
4. Measured optimization, then optional resumption/copy fast paths/dashboard work.

Start on the feature branch. Do not automatically resume experiments or start a
line-for-line port. Preserve branch work as reference before any cleanup. During
cutover, old and new daemons must not manipulate the same source namespace.

Increment 20 passes durable two-name NFS claim/file link interruption in both
profiles, preserving aliases until confirmed worker exit and recovering the same
inode/attempt. SC-049/050 record the user-visible results. In-flight link/unlink
RPCs, other synchronization boundaries, longer outages and stable root/export
authorization/cross-client ownership remain future qualification. Production NFS
and deletion remain disabled. Ubuntu's post-reboot user startup was unavailable;
the unchanged mandatory gates passed through the healthy Podman WSL2 engine using
the documented Windows `CONTAINER_CONNECTION` selection.
