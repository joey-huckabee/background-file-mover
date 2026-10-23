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

Current next work follows the [release-closure review](RUST-RELEASE-CLOSURE.md): P01 freezes the versioned API/manifest and release behavior inventory.
Use RC-01-24 and P01-12 to bound remaining work; do not automatically select
another NFS experiment. All eight gates remain open. Keep production NFS and
source deletion disabled; default-off cleanup remains a release deliverable.
Earlier increment summaries below are evidence, not the current work order.

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

[Increment 54](RUST-INCREMENT-54.md) adds selected independent endpoint outages:
source claim/read and destination copy/verification/publication, two controlled
server network namespaces/IPs on one kernel, local state and bounded healthy-peer
fresh I/O. Read its 28-case outcomes and exact SLES provenance. Keep remaining
failure directions/phases, bootstrap, real NAS/disk durability, mount/security,
in-flight RPC/remote settlement and systemd/account work open. Production NFS
and source deletion stay disabled.

[Increment 55](RUST-INCREMENT-55.md) adds four selected source-only NFS failures
after the first copied chunk, with the destination independently usable. The
qualification-only source_copy rendezvous advises source cache eviction before
the next read; actual blocked read-syscall/unchanged-prefix evidence is required.
Read actual outcomes and provenance before assuming termination/recovery behavior.
Other endpoint directions/phases, bootstrap, delayed RPC/remote settlement,
mount/security, NAS/disk durability and systemd/account work stay open.
Production NFS and source deletion remain disabled.

[Increment 56](RUST-INCREMENT-56.md) adds eight selected enrolled-empty/populated
startup death/stop cases with both private roots on distinct controlled NFS
endpoints, local state, source-only outage and a usable destination. Read actual
outcomes and provenance. Preserve separate local/remote snapshots, original
database/source/binding/enrollment and populated WAL/partial evidence. Fresh/
destination-side/later startup, other endpoint phases, delayed RPC/settlement,
mount/security, NAS/disk durability and systemd/account work remain open.
Production NFS and source deletion remain disabled.

[Increment 57](RUST-INCREMENT-57.md) adds a retained controlled systemd/manual
lifecycle fixture. It uses a real systemd 252 manager and pinned SLES/glibc-2.22
service root, local payload/state, explicit account checks and bounded restart
policy. Keep native SLES manager/cgroup compatibility, actual account authority,
persistent deployment and combined hard-NFS/systemd qualification open. No Rust
inputs/dependencies or production NFS/deletion enablement change.

[Increment 58](RUST-INCREMENT-58.md) records a blocked systemd-228
equivalent-container preflight. Public official SLES images omit the manager;
Leap 42.3 provides 228, while exact SLES-maintained RPM qualification remains
pending. The private cgroup-v2 manager/parser cannot initialize; all ten lifecycle
records are NOT_RUN. Compiled directive introspection supports the candidate
legacy key names only. Keep an approved suitable isolated engine/package source
as prerequisites; no real SLES installation is required. No production behavior
or NFS/deletion enablement changes.

[Increment 59](RUST-INCREMENT-59.md) follows explicit user approval for the
broader Podman-VM bootstrap. Retain the separate approved image/helpers and
`--manager 228 --allow-host-cgroup-bootstrap` entry point; refuse an unknown
existing hierarchy and require complete owned/kernel-hierarchy cleanup. Read
its actual lifecycle results and retained failures rather than treating the
blocked 58 preflight as changed. The [lab guide](SYSTEMD-LIFECYCLE-LAB.md) gives
every setup/test step; [testing limitations](TESTING-LIMITATIONS.md) separates
ABI/userspace, manager, kernel, NFS, durability, workload and deployment evidence.
Ten local lifecycle records, eight armed races and 32 explicit competitor
refusals pass with verified cleanup. The legacy unit uses unit-owned SIGTERM,
with the bounded controller checked independently: a global ExecStop after
guard refusal stopped a legitimate foreign owner in the retained failed run.
Production NFS and source deletion remain disabled.

[Increment 60](RUST-INCREMENT-60.md) adds four selected actual hard-NFS/systemd
managed stop/death records with separate exports and local state. Read actual
outcomes, old-thread/epoch and original-state recovery evidence. Keep remaining
operation/shutdown/death phases, remote settlement, actual NAS/mount/security,
account/persistence, exact vendor/kernel and workload qualification open.
Production NFS/source deletion remain disabled.

[Increment 61](RUST-INCREMENT-61.md) adds selected restart-after-incomplete-stop
qualification through `--nfs --nfs-suite restart`, preserving the older matrices.
Read actual manager refusal, retained ownership, quiet/restoration observations
and recovery actions. Update the maintained lab/operator/scenario/limits documents;
keep remaining shipping/operation/deployment qualification open and production
NFS/source deletion disabled.

[Increment 62](RUST-INCREMENT-62.md) adds
`--coordinator-death --death-scope destination-startup` to the retained NFS fixture.
Source startup can finish during a destination outage; qualify the real early
delivery worker and custody/replay behavior, not a fabricated destination-blocked
source-bootstrap child. Read actual eight-case outcomes and the
[dedicated lab](NFS-DESTINATION-STARTUP-LAB.md). Preserve original state/old partials,
96 stable SC/six DOC IDs, and production NFS/source deletion disabled.

[Increment 63](RUST-INCREMENT-63.md) adds twelve selected file/manifest
publication interruption records: four observed blocked client unlinkat syscalls
and eight crashes after namespace effects before sync. Original-state recovery
preserves inode/content and attempt one. Follow [the lab](NFS-PUBLICATION-SYNC-LAB.md)
for infrastructure, exact gates, interruptions and cleanup. Client syscall entry
does not prove RPC delivery/settlement, and pre-sync process crashes do not prove
power-loss durability. In-flight link/sync RPCs and full SH-11/12 remain open;
production NFS and source deletion stay disabled.

[Increment 64](RUST-INCREMENT-64.md) first proves server REMOVE completion
with its successful reply withheld and an actual pending client, then qualifies
four file/manifest worker cases. Loss includes explicit connection closure and
observed NFSv4.1 replay; the initial healthy-stream discard timeout stays failed.
The [lab](NFS-LOST-REPLY-LAB.md) records independent capability, exact SLES artifacts,
recovery and normal-unmount cleanup. No Rust inputs/dependencies changed. Remaining
claim/LINK/sync RPC, server-recovery/durability and full SH gates stay open;
production NFS and source deletion remain disabled.

Increment 65 adds server-completed publication LINK reply-loss qualification; see [results](RUST-INCREMENT-65.md). Keep production NFS/deletion disabled and maintain SC-099, the step-by-step lab and remaining reply-loss/durability limits.

Increment 66 adds source-claim LINK/REMOVE success-reply-loss qualification; see [results](RUST-INCREMENT-66.md). Keep production NFS/source deletion disabled, preserve SC-100 and the simple same-ID JSON-until-202 producer workflow, and maintain the step-by-step source lab and testing limits.

Increment 67 records synchronization RPC capability and actual worker observations; see [results](RUST-INCREMENT-67.md) and [lab](NFS-SYNC-LAB.md). No COMMIT/mover sync-loss support follows from buffered OS controls. Preserve SC-101/102, GNU/glibc-2.22 checks and production NFS/source deletion disabled.

[Increment 68](RUST-INCREMENT-68.md) defines the [mount-profile contract](NFS-MOUNT-PROFILE.md)
and [step-by-step lab](NFS-MOUNT-PROFILE-LAB.md). Buffered NMP-41B is the bounded
first-release qualification candidate; noac NMP-41N retains its earlier diagnostic
scope. Read-only model decisions were validated there; increment 69 below adds Rust
startup/effect enforcement and selected real worker evidence. Remaining buffered
fault qualification stays pending. Matching proc pins
cannot prove continuity or NAS availability. Production NFS/deletion remain off.

[Increment 69](RUST-INCREMENT-69.md) implements supervised NFS mount-profile
checks using strict per-binding declarations, root-descriptor mount ID correlation
and fingerprints in existing enrollment/worker observations. Local encodings stay
unchanged; legacy NFS bindings without profiles refuse without automatic migration.
The [extended lab](NFS-MOUNT-PROFILE-LAB.md#supervised-rust-authorization-extension)
records selected real B/B/N/N refusal/recovery/replay scope alongside the model.
Increment 70 below adds selected same-share workers. Next qualify remaining
buffered interruption/synchronization boundaries. Production NFS and source deletion remain disabled.

[Increment 70](RUST-INCREMENT-70.md) qualifies selected buffered NMP-41B same-share
baselines and durable claim/file LINK process-crash recovery in debug/release.
Maintain SC-104, the [step-by-step lab](NFS-SAME-SHARE-LAB.md), original local
state/enrollment and the producer JSON-until-202 contract. Remaining buffered
bootstrap/copy/verify/manifest, outage and synchronization/RPC boundaries stay
open. Production NFS/source deletion remain disabled.

[Increment 71](RUST-INCREMENT-71.md) adds the retained --buffered-reads matrix
and [lab](NFS-BUFFERED-READS-LAB.md) for actual source-copy/destination-verification
read blockage, coordinator death and original-state recovery on buffered same/
separate shares. Maintain SC-106 and DOC-01/03/04/05. The syscall observer alone
gets SYS_PTRACE/DAC_READ_SEARCH inside its isolated client; ordinary workers keep zero active
capabilities. Copy recovery preserves old partials/uses attempt 2; verification
retains attempt 1. Production NFS and source deletion stay disabled, and remaining
buffered RPC, bootstrap/publication/manifest and deployment gates stay open.

[Increment 72](RUST-INCREMENT-72.md) adds --buffered-publication and the
[lab](NFS-BUFFERED-PUBLICATION-LAB.md) for buffered same/separate-share
file/manifest returned-LINK/pre-sync and pending-unlink process interruption,
coordinator death, surviving-worker exclusion, original-inode attempt-1 recovery
and committed replay. Maintain SC-107 and DOC-01/02/03/04/05. Joint-outage POST
replay includes source revalidation; this matrix tests replay before outage and
after recovery. Preserve unchanged retry/review/deadlines, remaining actual
RPC/sync/remote-settlement qualification and production NFS/source deletion off.

[Increment 73](RUST-INCREMENT-73.md) extends the retained publication helper and
verifier with --buffered-post-unlink/--post-unlink. Eight buffered same/separate-
share debug/release cases pause after file/manifest staging unlink returns and
before directory sync. Require absent staging, original one-link final allocation,
old-thread exit before original-state attempt-1 recovery and stable replay. See
[the lab](NFS-BUFFERED-POST-UNLINK-LAB.md); maintain SC-108 and DOC-01/02/03/04/05.
This pause-only mode adds no syscall-observer capabilities. Keep production
NFS/deletion disabled and actual pending-sync/RPC/durability gates open.

[Increment 74](RUST-INCREMENT-74.md) adds --buffered-claims with a dedicated
helper/verifier: eight pre-202 buffered source custody LINK/producer-name REMOVE
cases across both share layouts and profiles. Keep original source paths/parents
unchanged until confirmed 202, actual blocked syscall/descriptor/flag evidence,
surviving-worker exclusion and original-state/inode recovery. See
[the lab](NFS-BUFFERED-CLAIM-LAB.md); maintain SC-109 and DOC-01–05. No Rust,
retry/review or deadline changes; production NFS/source deletion remain off.

[Increment 75](RUST-INCREMENT-75.md) adds --buffered-bootstrap with a retained
helper/verifier: eight buffered enrolled-empty/populated startup death/recovery
cases on both layouts/profiles. Require aged attributes, actual kernel-blocked
bootstrap, Starting/no false-ready reply, surviving-worker exclusion and original
state/inode/partial recovery. See [the lab](NFS-BUFFERED-BOOTSTRAP-LAB.md);
maintain SC-110 and DOC-01–05. Existing Rust, retry/review and all deadlines remain
unchanged; production NFS and source deletion stay disabled.

[Increment 76](RUST-INCREMENT-76.md) retains --buffered-sync with a dedicated
helper/verifier and [lab procedure](NFS-BUFFERED-SYNC-LAB.md). Observe eight
healthy claim/delivery workers, actual clock identity and complete mount-ID sync
intervals before selecting service fault cases. Conditional native controls are
OS capability evidence only. Maintain SC-111 and DOC-01–05, no new recorder duty,
unchanged Rust/retry/review/deadlines and production NFS/deletion off.

Increment-76 observations find no captured calls/replies inside 112 successful
service syncs; broader windows contain WRITE/COMMIT and both native discoveries
observe WRITE. No service-matching operation means zero new withholding cases.
Next locate actual worker I/O/RPC boundaries with both relays and descriptor/
filehandle attribution before defining service fault cases. Preserve initial
rejected-scope native transport evidence separately.

[Increment 77](RUST-INCREMENT-77.md) retains --buffered-io and a dedicated
external observer/analysis/verifier, preserving the earlier synchronization mode.
Use actual descriptor flags/offsets/inodes, bounded write bytes, both relays and
GETATTR fsid/fileid evidence before selecting reply-loss cases. SAVEFH/RESTOREFH
must update current/saved handle state; preserve initial failed evidence. Consult
[the lab](NFS-BUFFERED-IO-LAB.md) and actual attribution limits. Maintain SC-111 and
DOC-01–05; no Rust, retry/review, deadline or production NFS/deletion change.

Actual increment-77 result: four delivery traces associate 16 WRITE and four
COMMIT requests with payload/manifest fchmod before fsync; twelve WRITE ranges
match earlier captured buffers. Claim-window requests stay unattributed. Next
prove server completion/reply withholding for the payload fchmod COMMIT path
before selected service loss/death/recovery cases. Keep production NFS/deletion off.

[Increment 78](RUST-INCREMENT-78.md) proves payload-fchmod COMMIT success held
before forwarding: six native controls, then eight service live-release or
coordinator-death/worker-kill/drop recoveries, both NMP-41B layouts/profiles.
Read [the lab](NFS-BUFFERED-COMMIT-LAB.md) and actual scope: release commits on
attempt 1; death/drop preserves the first partial and original state, then commits
attempt 2. Both shares can use the source relay. Maintain SC-112/DOC-01–05.
Next qualify actual UNSTABLE-WRITE withholding; keep live COMMIT loss without
death and unobserved source sync open. No Rust/retry/review/deadline or production
NFS/source-deletion change.

[Increment 79](RUST-INCREMENT-79.md) passes six native and eight selected
UNSTABLE WRITE release/death-drop cases on both buffered layouts/profiles. The
[complete lab](NFS-BUFFERED-UNSTABLE-LAB.md) preserves initial failed validation,
corrected highest-slot-hint comparison and every-range/new-WRITE/later-COMMIT
proof. Four live releases commit attempt 1; four death/drop cases preserve first
partial/original state and commit attempt 2. Maintain SC-113/DOC-01–05. Next
qualify live-coordinator WRITE/COMMIT loss without death. No Rust, dependency,
retry/review/deadline or production NFS/source-deletion change.

[Increment 80](RUST-INCREMENT-80.md)/SC-114 adds twelve native controls and
eight live-coordinator payload reply-loss cases: COMMIT/UNSTABLE WRITE across
both buffered share layouts and debug/release profiles. The same coordinator
remains responsive, same-ID replay stays 202, and each case commits attempt 1
without replacement, restart, review or manual state changes. The
[step-by-step procedure](NFS-BUFFERED-LIVE-LOSS-LAB.md) accounts separately for
payload retransmissions and later other-handle traffic, retaining all raw bytes.
This supplies selected FR-03/05 evidence; all eight release gates remain open.
Production NFS/source deletion, retry/review policy and deadlines stay unchanged.
Longer losses, other phases, reboot/verifier changes and deployment/NAS/kernel/
physical-durability qualification remain open.

[Increment 81](RUST-INCREMENT-81.md)/SC-115 establishes actual manifest-side
successful-reply withholding: four healthy worker traces, then four hold/release
controls across both buffered layouts/profiles. The
[step-by-step lab](NFS-MANIFEST-CAPABILITY-LAB.md) separates actual manifest
WRITE stability and pending permission change from earlier payload COMMIT/
UNSTABLE evidence. Complete private bytes do not imply public commitment.
All cases preserve original source/state/enrollment and commit attempt 1 after
release. Selected reply loss, replay and coordinator-death recovery are covered
separately by increment 82; all eight release gates and production NFS/deletion remain
unchanged. Maintain DOC-01–05; DOC-06 stays deferred.


[Increment 82](RUST-INCREMENT-82.md)/SC-116 qualifies eight finite manifest WRITE
reply-loss recoveries after eight repeated discovery/release controls, across both
buffered NMP-41B layouts and debug/release profiles. Live-coordinator replay and
post-death application recovery from immutable SQLite intent are checked
separately. The latter confirms coordinator exit, orphan guard retention, actual
old-worker exit before restart, original staging inode/bytes before republication
and phase-1 to phase-4 durable intent preservation. All cases commit with payload
attempt 1 and preserve source/state/enrollment and producer-path reuse.
Read [the complete loss/recovery procedure](NFS-MANIFEST-LOSS-LAB.md) and retained
raw/audit evidence. This supplies selected FR-03/05 evidence; all eight release
gates stay open. Production NFS/source deletion, Rust inputs/dependencies,
retry/review and deadlines stay unchanged. Other workload/phases, server/verifier
recovery, delayed-effect settlement, NAS/kernel/power and deployment qualification
remain open. Maintain DOC-01–05; DOC-06 stays deferred.


[Increment 83](RUST-INCREMENT-83.md)/SC-117 adds buffered actual source-claim LINK
and REMOVE successful-reply hold/release controls, with the
[step-by-step procedure](NFS-CLAIM-CAPABILITY-LAB.md). Server-side namespace
completion does not authorize recorder path reuse before confirmed 202. Keep
selected capability/release evidence separate from increment 84's selected
reply-discard/replay/death evidence. Production NFS/source deletion stay off;
Rust behavior/dependencies and retry/review/deadline policy remain unchanged.
All eight release gates and DOC-01/02/04/05 completion remain open; maintain
DOC-03 and defer DOC-06.


[Increment 84](RUST-INCREMENT-84.md)/SC-118 qualifies sixteen finite buffered
source-claim LINK/REMOVE reply-loss recoveries after eight repeated release
controls across both share layouts and build profiles. Live cases prove successful
cached namespace session replay with full raw request-byte checks and the same
coordinator. Death cases prove orphan exclusion, actual exit and unchanged server
aliases before original-state restart. Every case commits attempt 1 while
preserving source/state/enrollment and newer producer bytes. The
[step-by-step lab](NFS-CLAIM-LOSS-LAB.md) documents infrastructure, proof, cleanup
and limits. Rust/dependencies, retry/review/deadlines and production NFS/deletion
stay unchanged. All eight release gates remain open; maintain DOC-01–05 and
defer DOC-06. Server recovery, delayed effects, pending source synchronization,
other workloads and NAS/kernel/power/deployment qualification remain future work.


[Increment 85](RUST-INCREMENT-85.md)/SC-119 isolates source synchronization:
four actual buffered claim workers pass 32 source fsync calls, with no captured
request/reply inside those intervals or captured pair spanning entry. Separate
source-export native probes prove FILE_SYNC WRITE success withholding, release
and drop/reconnect recovery on both share layouts. The actual-service/native
operation intersection is empty, so zero mover source-sync reply-loss/death
cases are qualified. Read the [step-by-step lab](NFS-SOURCE-SYNC-LAB.md) and raw
scope/limitations; broader-window traffic is not source-sync attribution.
Server recovery/delayed settlement and other workloads remain open. Production
NFS/source deletion, Rust behavior/dependencies, retry/review and deadlines stay
unchanged. Maintain DOC-01–05 and defer DOC-06; all eight release gates stay open.


[Increment 86](RUST-INCREMENT-86.md)/SC-120 establishes native server-recovery
fixture capability after two retained failed acquisitions. Four original-FD
probes pass NFSD stop/start and confirmed same-container SIGKILL/exit/start on
source/destination exports, preserving opaque handles/backing inodes while
observing BADSESSION, new sessions and changed write verifiers. Network namespace
and VM kernel boot ID remain unchanged; this is not VM/NAS reboot or Rust mover
recovery qualification. The [step-by-step lab](NFS-SERVER-RECOVERY-LAB.md)
records pinned private IP, actual exit, live trace checkpoints, WSL clocks,
raw proof, rescue/normal cleanup and limits. Both SLES gates and independent
36-control proof audit pass. Production NFS/source deletion and runtime policy
remain unchanged; maintain DOC-01–05, defer DOC-06 and keep all eight gates open.


[Increment 87](RUST-INCREMENT-87.md)/SC-121 qualifies four actual live-coordinator
source-copy recoveries after four native controls: debug/release with NFSD restart
or NFSD quiescence followed by same-container SIGKILL/confirmed exit/start.
Each retains the original worker/attempt 1, custody/local state, staging inode,
payload/manifest integrity and clean-restart committed replay. Two mounts/export
paths share one client NFS filesystem and backing volume; distinct client
filesystems/independent shares remain unqualified. Repeated abrupt termination
controls failed and are retained with rescue evidence; the final controlled
sequence does not qualify abrupt failure, other phases, NAS or power loss.
Read the [complete lab](NFS-SERVER-MOVER-LAB.md), raw/input evidence and rejected
audit assumption. Both SLES gates, 50 proof controls and final inventory pass.
Rust/dependencies, retry/review/deadlines, production NFS/source deletion and
all eight release gates remain unchanged. Maintain DOC-01–05; defer DOC-06.


[Increment 88](RUST-INCREMENT-88.md)/SC-122 extends the controlled source-copy
recovery matrix to two genuinely distinct client NFS filesystems, backed by two
bounded tmpfs superblocks held by a separate storage container. Four native
controls precede four debug/release actual mover cases. Original-worker attempt-1
completion, staging inode, private source, local state/enrollment and committed
replay are preserved. The [step-by-step lab](NFS-DISTINCT-RECOVERY-LAB.md) documents
volume bounds, keeper/backend/reader/client identity checks, initial OCI setup
failure, normal cleanup and independent audit. This adds selected cross-filesystem
copy evidence; it does not qualify independent NAS, persistent disks, abrupt live
server termination, power loss, other phases or worker replacement. Both SLES
gates remain mandatory; production NFS/source deletion and all eight release
gates stay unchanged. Maintain DOC-01-05 and defer DOC-06.


[Increment 89](RUST-INCREMENT-89.md)/SC-123 extends the retained two-filesystem
fixture to live destination-staging verification across controlled NFS server
restart. Four native prerequisites precede four debug/release mover cases using
NFSD restart or NFSD-quiesced same-container termination/start. The
[complete lab](NFS-VERIFICATION-RECOVERY-LAB.md) distinguishes durable Copied
status and a full staging file from completed verification: require actual
D-state staging read/FD/offset proof, unchanged staging/source/state and no final
payload or manifest during the outage, then original-worker attempt-1 commitment
and original-state replay. I/O tracing checks full reread through EOF and later
publication; it starts after earlier copy synchronization. READ RPC compounds
remain unknown in the retained decoder, so this is not READ session-replay proof.
Keep retained-memory/modern-kernel, independent NAS/power and other-phase limits
explicit. Maintain DOC-01-05 and defer DOC-06; runtime policy, production NFS/source
deletion and all eight release gates remain unchanged.

The release container-restart case in increment 89 continues across an observed
backend network-namespace change while keeper/storage and VM boot identity remain
stable. This selected actual continuation does not close broader namespace,
lease/reclaim, VM/NAS reboot or physical-durability qualification.


[Increment 90](RUST-INCREMENT-90.md)/SC-124 tests controlled server recovery at
payload publication's two-name staging-removal boundary. Four native controls
precede four debug/release live-worker cases on the retained two-filesystem
fixture. The [complete lab](NFS-PUBLICATION-RECOVERY-LAB.md) requires complete
same-inode staging/final aliases with two links, PublishIntent and no manifest,
actual pending unlinkat on the staging directory, unchanged custody/state/ownership,
then original-call removal, one-link original final inode, later manifest and
attempt-1 committed replay. Staging removal is not postcommit source cleanup.
The initial final LINK/file/new-parent sync precede tracing; initial LINK and other
sync/manifest/death boundaries remain separate. Retained memory, controlled NFSD
quiescence and modern-kernel evidence do not establish NAS/power durability or a
full lease/reclaim matrix. Maintain DOC-01-05, defer DOC-06 and keep runtime policy,
production NFS/source deletion and all eight release gates unchanged.


[Increment 91](RUST-INCREMENT-91.md)/SC-125 extends the same finite controlled
server-recovery matrix to manifest staging-name removal. The
[step-by-step lab](NFS-MANIFEST-RECOVERY-LAB.md) requires an already Published
one-link verified payload with no payload staging, manifest_phase 3, and complete
same-inode manifest aliases with two links. Actual D-state unlinkat named
COMMITTED.part, unchanged source/payload/manifest/state/ownership and correlated
successful raw REMOVE precede original-worker attempt-1 commitment. The original
manifest inode/hash survives with one link after the remaining syncs. Clean
original-state replay preserves recorder reuse. A valid COMMITTED.json remains
the consumer signal; this boundary precedes the local Committed receipt and adds
no consumer API-polling or recorder monitoring duty. Initial manifest LINK/file/
new-parent sync precede tracing. Other sync/death/reconciliation boundaries,
retained-memory versus physical durability, controlled quiescence, independent
NAS/power and modern-kernel limits remain explicit. Maintain DOC-01-05 and defer
DOC-06; production NFS/source deletion and all eight release gates stay unchanged.


[Increment 92](RUST-INCREMENT-92.md)/SC-126 extends controlled server-recovery
qualification to the initial payload LINK at file_link_rpc. The
[step-by-step lab](NFS-PAYLOAD-LINK-RECOVERY-LAB.md) starts with verified one-link
staging, PublishIntent and absent final payload/manifest. Require actual D-state
linkat with both directory FD/path/mount/inode observations, successful raw LINK
inside its original pending interval, final-file/new-parent sync before staging
removal and later manifest publication. The original staging inode/hash becomes
the one-link final payload; original-worker attempt-1 commitment and clean
original-state replay preserve recorder reuse and private source/state/enrollment.
The recorder and valid-manifest consumer contracts stay unchanged. Earlier
copy/verification/original-file sync precede tracing; remaining initial manifest
LINK, other sync/death/reconciliation, NAS/power, full session/reclaim and modern-
kernel limits remain explicit. Maintain DOC-01-05 and defer DOC-06; production
NFS/source deletion and all eight release gates stay unchanged.


[Increment 93](RUST-INCREMENT-93.md)/SC-127 extends controlled server-recovery
qualification to initial manifest LINK at manifest_link_rpc. The
[step-by-step lab](NFS-MANIFEST-LINK-RECOVERY-LAB.md) starts with payload
Published, manifest_phase 3, complete one-link manifest staging, absent final
manifest and unchanged one-link verified payload with no payload staging.
Require actual D-state linkat with both directory FD/path/mount/inode observations,
successful raw LINK named COMMITTED.json inside its original pending interval,
manifest-file/new-parent sync before staging removal and remaining successful
syncs before the local receipt. Original manifest inode/hash, payload, source,
state/epoch and attempt-1 committed replay preserve recorder reuse. Producer and
valid-manifest consumer duties stay unchanged. Earlier payload effects/manifest
write/original-file sync precede tracing; remaining sync/death/reconciliation,
retained-memory versus physical NAS/power durability, full session/reclaim and
modern-kernel limits remain explicit. Maintain DOC-01-05 and defer DOC-06;
production NFS/source deletion and all eight release gates stay unchanged.


[Increment 94](RUST-INCREMENT-94.md)/SC-128 establishes exact publication file-
fsync capability before selecting more sync recovery. The
[step-by-step lab](NFS-PUBLICATION-SYNC-DISCOVERY-LAB.md) repeats native controls
and eight actual debug/release payload/manifest healthy/stopped-NFSD observations.
An external exact-path observer holds at entry/exit without changing shipping
Rust or substituting syscalls; artificial ptrace stops are excluded from syscall/
RPC timing and are not D-state. Require complete aliases/source/payload, original
state/epoch/guard, actual outcome before/after restoration, attempt-1 commitment
and clean committed replay. Independently decode raw interval traffic and captured
pairs spanning entry, keeping broader/unknown activity separate. Successful local
completion while NFSD is stopped supplies no blocked-sync recovery qualification;
native dirty-write recovery cannot substitute for actual service evidence.
Producer/consumer duties, runtime policy and deadlines remain unchanged. Maintain
DOC-01-05, defer DOC-06, keep production NFS/private-source deletion disabled and
all eight release gates open. Other sync/directory/workload/cache, death/recovery,
physical NAS/power and old-kernel profiles remain separate.

[Increment 95](RUST-INCREMENT-95.md)/SC-129 adds four selected debug/release
payload-LINK coordinator-death recoveries across NFSD/quiesced-container restart,
after four native prerequisites. Actual pending linkat and old-worker D-state
are distinguished from artificial pauses and successful syscall returns. Logical
ownership refuses all three contenders through actual old-worker exit; physical
flock closure is recorded separately. After restoration, independent read-only
namespace/custody observations precede original-state attempt-1 commitment and
replay preserving producer reuse. No arbitrary uncertain-effect redispatch or
remote-settlement proof follows from local exit. See the
[step-by-step lab](NFS-PAYLOAD-LINK-DEATH-RECOVERY-LAB.md) and exact raw/audit
results. Both SLES gates and normal cleanup pass. Other phases, actual blocked
syncs, NAS/persistent-storage/power and old-kernel behavior remain unqualified;
production NFS/private-source deletion stay off and all eight release gates open.

[Increment 96](RUST-INCREMENT-96.md)/SC-130 adds four selected manifest-LINK
coordinator-death recoveries across NFSD/quiesced-container restart after four
native prerequisites. Require actual D-state linkat, old-group exclusion and all
three contender modes refused until actual worker exit. Independent read-only
backing observations retain original manifest/payload/source custody; exact raw
SQLite/WAL copies prove phase 3 remains pending after old-worker exit, separately
from a visible valid completion manifest. Original-state attempt-1 commitment and
replay preserve producer reuse. Recorder/consumer duties remain unchanged. See
the [step-by-step lab](NFS-MANIFEST-LINK-DEATH-RECOVERY-LAB.md), raw/audit evidence
and both SLES gates. Normal cleanup passes. Local ownership/exit is not global
remote-settlement proof; unselected phases/syncs, NAS/power and old-kernel behavior
remain unqualified. Production NFS/private-source deletion stay off; eight release
gates remain open.

[Increment 97](RUST-INCREMENT-97.md)/SC-131 qualifies four selected source-claim
LINK coordinator-death recoveries before HTTP 202 across NFSD/quiesced-container
restart, after four native prerequisites. Require actual D-state linkat, logical
old-worker exclusion/three contender refusals through actual exit, preserved
original/private source custody and copied SQLite/WAL proof of pending done=0
with no transfer/manifest before replacement. The original request must have no
202/path release; only confirmed identical-ID retry 202 permits producer reuse.
Original-state attempt-1 delivery and replay preserve newer producer bytes. See
the [step-by-step lab](NFS-CLAIM-LINK-DEATH-RECOVERY-LAB.md) and exact raw/audit
results. Both SLES gates and normal cleanup pass. Claim source-name removal is
separate from disabled private-source cleanup; local exit is not global remote
settlement. Unselected REMOVE/sync/termination, NAS/power and old-kernel behavior
remain open; eight release gates stay open and production NFS/deletion stay off.

[Increment 98](RUST-INCREMENT-98.md)/SC-132 qualifies four selected source-claim
REMOVE coordinator-death recoveries before HTTP 202 across NFSD/quiesced-container
restart after four native prerequisites. Require same-inode two-name custody at
entry, actual D-state unlinkat, independently decoded preceding LINK/resumed REMOVE,
logical exclusion/three contender refusals through actual exit and copied local
SQLite/WAL claim done=0/no transfer or manifest before replacement. Confirmed
identical-ID retry 202 precedes producer reuse; original-state attempt-1 commitment
and replay preserve newer bytes. See the [step-by-step lab](NFS-CLAIM-REMOVE-DEATH-RECOVERY-LAB.md),
raw/audit evidence and preserved initial pre-mount Podman connection failure.
Both SLES gates and normal cleanup pass. Observer attachment at REMOVE excludes
earlier file/new-parent syncs; this is not actual blocked-sync or NAS/power-loss
qualification. Local exit is not global remote settlement. Other sync/termination,
old-kernel/deployment and broader workloads remain open; all eight release gates
stay open and production NFS/postcommit private-source cleanup stay off.

[Increment 99](RUST-INCREMENT-99.md)/SC-133 adds eight selected source-claim
private-file/private-parent synchronization observations before HTTP 202, across
debug/release and healthy/stopped NFSD after four native prerequisites. External
actual syscall entry/exit controls exclude artificial holds; independently audit
raw interval traffic and captured pairs spanning entry, seven observed syncs per
worker, complete two-name custody/Accepted state and no producer reuse until
confirmed same-ID 202. Original-state attempt-1 delivery/replay preserves newer
bytes. See the [step-by-step lab](NFS-CLAIM-SYNC-DISCOVERY-LAB.md) and measured
raw/audit evidence. Successful local stopped-NFSD completion is discovery, not
blocked-sync, reply-withholding or physical-durability qualification. Original-file
sync before LINK and other workloads/caches/termination remain separate. Both
SLES gates and normal cleanup pass after correcting and retaining an initial
shared case-count assertion failure and rerunning the full matrix. Keep all eight release gates open and
production NFS/postcommit private-source cleanup disabled.

[Increment 100](RUST-INCREMENT-100.md)/SC-134 adds four debug/release x healthy/
stopped-NFSD original-file fsync observations before claim LINK after four native
prerequisites. Exact actual entry/exit excludes artificial holds; require complete
one-link original, private data absent, Accepted state and no premature 202.
Both stopped-NFSD calls return locally: no selected raw RPC or captured pair
spanning entry is observed. All eight syncs per worker return zero; successful
following LINK pairs calibrate capture. Same-ID 202 before reuse, attempt-1
commitment, original-state replay, both SLES gates and normal cleanup pass.
See the [step-by-step lab](NFS-ORIGINAL-CLAIM-SYNC-DISCOVERY-LAB.md), retained setup
connection failure and raw/input evidence. This does not qualify blocked-sync,
reply-loss, physical durability or broader cache/workloads. Prioritize joint-outage
replay/revalidation/admission next; require positive RPC evidence before further
sync recovery. All eight release gates stay open; production NFS/private-source
cleanup stay disabled.

[Increment 101](RUST-INCREMENT-101.md)/SC-135 adds four debug/release x source-space
admission off/on joint-outage cases after four native prerequisites. Actual
D-state destination verification and source revalidation preserve acknowledged
custody, original state and producer replacement bytes. The initial replay plus
six-request burst returns bounded retryable non-release 503s with queue refusal;
timed-out HTTP waiters do not cancel queued commands. Enabled policy permits at most one
probe; probes may already have exited. The two blocked data workers stay stable. One-job retention prevents
new durable acceptance, while original attempt-1 delivery and clean restart/replay
recover after restoration. Both SLES gates, exact-artifact/raw/corruption audits
and normal cleanup pass. See [step-by-step infrastructure](NFS-JOINT-OUTAGE-LAB.md).
This finite shared-backend test does not qualify independent outages, pre-202/
partial claims, source substitution, throughput/endurance or physical durability.
Keep all eight release gates open and production NFS/private-source cleanup off.

[Increment 102](RUST-INCREMENT-102.md)/SC-136 adds four debug/release x pending
source LINK/REMOVE replay cases before HTTP 202 after four native prerequisites.
One-file Accepted/non-release state, complete one-/two-name original custody,
zero confirmed claims/destination attempts and the same D-state worker/epoch
survive a six-request burst. Initial request and burst return retryable non-release
503s with queue refusal; HTTP timeout is not cancellation. Confirmed same-ID 202
precedes producer reuse; original private inode/attempt-1 delivery, complete
manifest and original-state restart/replay preserve newer bytes. Both SLES gates,
exact raw/ELF/corrupted-proof audits and normal cleanup pass. See the
[step-by-step lab](NFS-PRE202-REPLAY-LAB.md) and retained pre-provisioning/gate SSH
failures with unchanged-source retries. Multi-file partial handoffs, source changes,
independent outages, death, physical durability and load/endurance remain open.
Keep all eight gates open and production NFS/private-source cleanup disabled.

[Increment 103](RUST-INCREMENT-103.md)/SC-137 qualifies selected two-file partial
handoffs: first privately claimed, second LINK/REMOVE pending, Accepted/non-release,
one confirmed claim and no delivery. Four native controls precede four debug/release
cases. Same D-state worker/epoch and complete custody survive finite retry/queue
refusals. Only confirmed whole-set 202 permits producer reuse; attempt-1 delivery,
exact two-file manifest and original-state restart preserve originals/private and
newer producer bytes. A qualification-only claim-index selector enables the fixture;
production API/retry/review/deadlines stay unchanged. Both SLES gates, raw/ELF/
corrupted-proof audits and normal cleanup pass. See the [step-by-step lab](NFS-PARTIAL-HANDOFF-LAB.md).
Source changes, other multi-file boundaries, independent outages, death and load/
physical durability remain open. Production NFS/private-source cleanup stay off;
eight gates remain open; registration/S3/repair/DOC-06 stay deferred.

[Increment 104](RUST-INCREMENT-104.md)/SC-138 qualifies selected second-file
pre-effect inode replacement and size-change refusal after the first claim completes.
Four native controls precede four debug/release cases on healthy NMP-41B NFS.
Existing non-retryable 409 recording_blocked persists across two unpaused restarts,
with original intent, first/private custody, changed/saved files, Accepted/AwaitingClaims,
one confirmed claim and zero delivery/review-epoch changes. Sixteen copied SQLite/
WAL snapshots, raw RPC/corruption/forty-ELF audits and both SLES gates pass; normal
cleanup restores baseline. See the [step-by-step lab](NFS-SOURCE-CHANGE-LAB.md).
No Rust/dependency/API/retry/review/deadline changes or automatic repair. These are
intentional producer contract violations, not permission to modify before 202.
Other source/parent/timing changes, hostile tampering, outages/death and physical
NAS/durability/load remain open. Eight release gates stay open, production NFS/
private-source cleanup stay off; registration/S3/repair/DOC-06 stay deferred.
