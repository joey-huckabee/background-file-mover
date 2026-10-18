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

Prioritize the [first-release checklist](RUST-FIRST-RELEASE.md), recorded in
[increment 37](RUST-INCREMENT-37.md). It bounds the initial filesystem/NFS release
and keeps optional adapters/repair/UI deferred. [Increment 38](RUST-INCREMENT-38.md)
adds bounded native source-capacity fixture evidence.
[Increment 39](RUST-INCREMENT-39.md) defines the proposed remote access contract
and RA-01–16 without implementing ingress or registration.
[Increment 40](RUST-INCREMENT-40.md) records the earlier broad fencing baseline.
[Increment 41](RUST-INCREMENT-41.md) revises it under confirmed one-host/account,
fixed local config/state and private NFS working-area constraints.
[Increment 42](RUST-INCREMENT-42.md) implements local ownership and descriptor
handoff with selected local denial/race/surviving-worker evidence.
[Increment 43](RUST-INCREMENT-43.md) implements the configurable default-60 local
stop/status controller with selected config/clean/timeout/repeated-request cases.
[Increment 44](RUST-INCREMENT-44.md) adds local SQLite file/recovery-name admission,
individual state/guard/control mount refusal and retained-WAL recovery; existing
state is preserved on refusal and no automatic repair is introduced.
[Increment 45](RUST-INCREMENT-45.md) adds real hard-NFS shutdown qualification:
selected copy workers retain ownership beyond short/default deadlines; prompt
claim/read exit is distinct, and original-state recovery waits for restoration
and confirmed old exit. No Rust behavior or retry/review policy changes.
[Increment 46](RUST-INCREMENT-46.md) tests coordinator death with selected actual
kernel-blocked and terminating NFS children, bounded OwnerUnavailable, inherited
local exclusion and original-state recovery. Prompt exit before parent kill is
recorded separately. No Rust/retry/review change or production enablement follows.
[Increment 47](RUST-INCREMENT-47.md) adds persistent local process-group lifetime
evidence before all worker spawns, checked independently of physical lock closure.
Status and new starts retain exclusion while a recorded process/thread is live;
unknown evidence never authorizes replacement. Preserve the increment 46 failure
as history and qualify remaining death, NFS operation/drain and
systemd/account-control cases (SH-01–04/06–14). Qualify late NFS effects, actual
mounts, same/separate shares and systemd scope (SH-10–14); local exclusion is not remote
settlement. Keep stronger external fencing/cross-host takeover deferred. No NAS
administration is assumed. Production NFS/deletion and remote ingress stay off;
registration stays deferred.

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
[Increment 36](RUST-INCREMENT-36.md), [source-space policy](SOURCE-SPACE-ADMISSION-DESIGN.md),
[operator guide](RUST-OPERATOR-GUIDE.md),
[retry policy](DELIVERY-RETRY-POLICY.md), [enrollment contract](FENCED-ENROLLMENT-DESIGN.md),
[root/ownership design](ROOT-OWNERSHIP-DESIGN.md),
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
RPCs, other synchronization boundaries, outages beyond selected qualification and stable root/export
authorization/cross-client ownership remain future qualification. Production NFS
and deletion remain disabled. Ubuntu's post-reboot user startup was unavailable;
the unchanged mandatory gates passed through the healthy Podman WSL2 engine using
the documented Windows `CONTAINER_CONNECTION` selection.

Increment 21 adds three-minute hard-mounted claim/verification outages in both
profiles, sequential submission backpressure checks and live recovery on attempt 1.
SC-051/052 distinguish custody pending from delivery pending. An HTTP wait timeout
does not cancel the queued submission; retryable `service_busy` can follow
`handoff_pending`. Keep the full interruption evidence and focused long-outage
report separate. Stable root/export authorization and cross-client fencing remain
prerequisites to production NFS; source deletion remains disabled.

Increment 22 adds actual two-client startup and absent-mount diagnostics.
SC-053/054 record gaps: a second NFS client can reach readiness against the
same source, and an owned local stand-in is accepted after the expected mount
is absent. Same-client refusal and a regular-file remote-lock control pass.
These are measured limitations, not enabled production features. Next implement
explicit source root binding/state enrollment, then pinned destination binding
and qualified cross-client exclusion/fencing using ROOT-OWNERSHIP-DESIGN.md.
Keep one statically assigned coordinator per disjoint source and no automatic
takeover. Do not combine these results with earlier outage evidence as though
they proved a distributed fence or stable export authorization.

Increment 23 implements required source binding and preprovisioned marker
validation in supervised bootstrap, durable schema-8 source enrollment and
authorization checks in claim/delivery workers and the single-file CLI. Matching
restarts work; changed pins or populated unbound state refuse startup. Expected
NFS sources refuse underlying local stand-ins even with matching copied markers.
Keep old state/source data intact; no automatic rebind, legacy-job enrollment
override or authenticated export/fencing claim is provided. Strict device/fsid
changes may require future fenced re-enrollment. Next pin destination bindings,
then qualify cross-client exclusion/fencing; production NFS/deletion stay disabled.

Increment 24 pins destination policy per accepted job, observes and persists
validated destination custody before staging, and revalidates in delivery
children and the single-file CLI. Missing destinations do not gate source 202;
foreign or changed bindings require explicit review. Schema 9 preserves legacy
jobs but service startup refuses jobs without a saved destination policy.
Next qualify cross-client exclusion/fencing and explicit legacy enrollment/rebind.
Keep production NFS and deletion disabled.

Increment 25 uses preprovisioned empty private regular lock files at both roots.
Version-2 bindings/observations and bootstrap receipts refuse the old directory
protocol; worker descriptors must match the named writable lock. Two-client
qualification checks actual claim/delivery custody after coordinator death and
recovery through the original state. Cooperative exclusion does not authorize
independent-state takeover or fence lost locks/partitions/reclaim. Preserve old
state and require explicit fenced cutover/enrollment; production NFS/deletion stay
disabled. Next qualify those remaining fences and authenticated export identity.

Increment 26 specifies explicit first enrollment, persistent source/state pairing,
interrupted enrollment and fenced recovery requirements. This is design only;
current empty-state enrollment does not prevent a fresh database using the same
coordinator label after lock release. Next implement unused-scope enrollment and
matching restart, then qualify interrupted setup and fresh-state refusal. Preserve
old state/data; no rebind command, automatic takeover or production NFS/deletion
authorization is provided. Lost-lock/partition diagnostics and an independently
qualified fence remain prerequisites to populated-state recovery.

Increment 27 adds explicit unused-scope initialization and original-state restart.
Schema 10 persists prepared/active ownership and version-3 binding policies exclude
old protocols. The source receipt is validated in inherited workers and pinned to
the original database. Unknown/preexisting namespaces and ambiguous creation stay
blocked without automatic repair; matching text does not establish ownership.
See the increment for current gate/fixture evidence and the catalog for SC-064/065.
Next expand enrollment error/synchronization evidence and lost-lock/partition
diagnostics, then select an independently qualified fence before populated rebind.
Production NFS/deletion, registration and offline repair stay disabled/deferred.

Increment 28 adds narrow qualification-only enrollment write/sync fault controls,
a process-death pause between file and directory sync, and stage-specific bounded
enrollment diagnostics. It qualifies startup shutdown while the actual receipt
read is blocked on hard NFS; consult the increment for observed exit timing and
the fixture's current result before claiming cancellation. Schema 10, binding
version 3 and the persisted receipt remain unchanged. Keep pending/ambiguous
creation blocked and preserve original state/data. Next qualify broader storage
errors and lost-lock/partition/reclaim, then an independently enforced fence before
populated-state rebind or takeover. Production NFS/deletion remain disabled.

Increment 29 adds opt-in real server ENOSPC qualification using a separate bounded
tmpfs export. It distinguishes inode exhaustion before receipt creation from data
space exhaustion after creation; the original database and source evidence remain
required. Consult the increment for actual results before claiming safe retry or
review outcomes. The Rust implementation, schema and dependency graph are unchanged.
Physical-disk/EIO, in-flight synchronization, power loss and independently enforced
fencing remain separate qualification; production NFS/deletion stay disabled.

Increment 30 adds bounded destination-full payload qualification, with selected
live and original-state restart recovery through existing review/audited resume.
Consult the increment for actual results, retained partial/source evidence and
diagnostic limits. The Rust implementation/schema/dependency graph are unchanged.
Continue qualifying broader storage errors, in-flight RPCs and independently
enforced fencing before production NFS; source deletion remains disabled.

Increment 31 adds payload operation/errno diagnostics with fixed safe actions and
qualification-only read/write/sync fault controls. Retry timing, review thresholds,
audited resume and effect authorization stay unchanged. Consult its results for
real ENOSPC logs, synthetic boundary tests and full NFS regression. A publication
sync error can leave a valid final file without a committed recording. Preserve
source/state and keep broader retry policy, storage EIO and fencing as future work.

Increment 32 extends operation/errno diagnostics to staging allocation, relocation
and completion-manifest I/O. It preserves retry/review/resume and native effect
order. Unreceipted exclusive allocations still refuse automatic repair; a valid
final manifest may exist before coordinator commitment if synchronization fails.
Consult the increment and SC-073 for actual validation and qualification scope.
Broader retry policy, EIO/power-loss and independent fencing remain future work.

Increment 33 adds [typed copy-ENOSPC backoff](DELIVERY-RETRY-POLICY.md): 30/60-second
pending retries, still review after three persisted failures. Pending deadlines and
counts survive restart; restoration before review can recover automatically, while
review still requires audited resume. Schema 11 widens the constrained vocabulary
through a preserving transaction. Private delivery-session protocol 2 is distinct
from persisted receipt version 1 and binding version 3. Consult the increment for
actual gates, failed-development findings, selected NFS scope and limits. Preserve
all other retry/reconciliation, ownership and production NFS/deletion restrictions.

Increment 34 delivers DOC-03 in the [operator guide](RUST-OPERATOR-GUIDE.md):
status interpretation, audited resume/missing reset, exact command replay,
retention/capacity triage and preservation/refusal boundaries. Documentation only;
no runtime or qualification changes. Keep the other guides in the catalog backlog.
Existing job/byte reservation limits already apply; the next admission increment
should refine source-space margins and sustained-shortage behavior, not recreate
those limits. Design and qualify that policy before changing admission effects.

Increment 35 defines the configurable/default-off source-space admission policy
and SA-01–18, catalog SC-075–081. Design only: current config/API and schema 11
are unchanged. The guard applies to new keys, preserves existing partial/replay
recovery and ledger limits, and requires bounded fresh authorized observations.
Implement and qualify before promoting these future scenarios to supported.

Increment 36 implements the default-off local source-space guard with strict
configurable byte/percent margins, replay-first serialized new-key admission,
one supervised capacity child and cached global retention visibility. New keys
can await a shared probe through at most two asynchronous HTTP waiters and one
recheck within the existing total ten-second handoff budget; existing keys skip it.
Unknown/late results return retryable unavailable; cold admission does not depend
on fast recorder retries. See its results and SA mapping before expanding storage claims. No
schema/dependency change; keep physical/NFS capacity qualification pending.


[Increment 48](RUST-INCREMENT-48.md) extends the retained coordinator-death fixture
with `--death-scope bootstrap-source-read`: eight selected fresh-bootstrap and
accepted source-read cases, blocked or following local stop, in both profiles.
Read the report for actual outcomes and limitations. No Rust runtime, package,
retry/review or production-gate change is introduced. Preserve original local
state and wait for confirmed old exit before recovery; fresh bootstrap performs
explicit first enrollment afterward. See increment 49 for the selected enrolled/
populated extension and increment 50 for selected publication/manifest cases.
Other operation/systemd/NAS-settlement obligations remain open.


[Increment 49](RUST-INCREMENT-49.md) adds selected enrolled-empty/populated
bootstrap death cases through `--death-scope bootstrap-existing-state`. Preserve
the original database, retained WAL/sidecars, receipt, partial and reused source
path; snapshots must not open SQLite. Normal recovery uses the same enrollment
pair without re-initialization. Read the increment for actual outcomes and scope;
no runtime/dependency/retry/review change accompanies the fixture expansion.
See increment 50 for the selected publication/manifest extension. Other
synchronization, both-NFS crash and actual systemd/NAS settlement obligations
remain open; production NFS/deletion remain disabled.

[Increment 50](RUST-INCREMENT-50.md) adds twelve selected destination-NFS
pre-publication/file-link/manifest-link cases via `--death-scope
publication-manifest`. Require real D after release into outage, original-state
competitor refusal while an orphan survives and restoration/actual exit before
recovery. Keep the verified payload inode/attempt and existing manifest inode/hash;
visible names are distinct from SQLite commitment. Read the actual outcomes and
initial SLES timing-test failure in the increment. No runtime/dependency/policy
changes or production enablement accompany these checks; retain all earlier
selectors and the strict raw-lock-closure regression.


[Increment 51](RUST-INCREMENT-51.md) stabilizes the existing repeated-stop test
with bounded status polling through a valid Draining snapshot to daemon expiry.
The same original four-second test bound, two-second loaded budget, instance
identity, monotonic countdown and ownership/refusal checks remain enforced;
three rounds run per qualification profile. Runtime deadlines/defaults and all
production code stay unchanged. Keep the increment 50 failed evidence and read
the fresh gate results in increment 51. No new NFS qualification or production
NFS/source deletion enablement follows.

[Increment 52](RUST-INCREMENT-52.md) extends selected coordinator-death/recovery
qualification to both private roots on one controlled NFSv4.1 export with local
state. Read its actual 24-case results and exact SLES provenance. Original-state,
source inode/receipt, reused paths and publication evidence are required. Keep
separate-export/independent endpoint, both-NFS bootstrap/read, in-flight RPC,
remote settlement and actual systemd/account work open. Production NFS/source
deletion remain disabled; no runtime policy changed.

[Increment 53](RUST-INCREMENT-53.md) adds selected death/recovery cases across
two distinct NFS exports backed by separate bounded tmpfs filesystems on one
controlled server. The database/lifetime state stays local. Read its actual
24-case results and SLES provenance. Independent endpoint/NAS failures, delayed
RPC settlement, disk/power durability, remaining both-NFS bootstrap/read and
actual systemd/account qualification remain open. Production NFS/deletion stay off.
