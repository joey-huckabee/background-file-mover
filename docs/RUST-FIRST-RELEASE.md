# First Rust release checklist

Release scope recorded 2026-10-16 on `feature/rust-transfer-coordinator`.
This is the release finish line within the broader [roadmap](ROADMAP.md), not a
production-support declaration or a replacement for requirements. No release
version or delivery date is assigned. All gates below remain open; implemented
parts and their evidence stay in the [scenario catalog](RUST-SCENARIOS.md) and
increment reports. Do not count increments or passing tests as a completion
percentage.

Use [testing limitations](TESTING-LIMITATIONS.md) to distinguish tested behavior,
environment assumptions and remaining evidence. The [lifecycle lab procedure](SYSTEMD-LIFECYCLE-LAB.md)
documents the controlled infrastructure, individual test steps and cleanup;
it is not a production installation guide.

## Intended first release

One executable/configuration/systemd service coordinates explicit recording sets
from an approved source filesystem, including a specifically qualified NFS
profile, into a configured filesystem destination. The recorder supplies its
identity, source directory and explicit relative file names, with optional size
assertions; it does not choose the destination. Preserve subfolders. The recorder
keeps closed, completed files unchanged until 202, retries the identical ID/body
if it does not receive 202, and has no delivery-monitoring duty afterward.

202 means durable acceptance and confirmed custody of every submitted file, so
the recorder can immediately reuse its original paths. Delivery hashes during
copy and rereads destination staging (3N normal logical I/O), verifies content,
publishes without clobbering and exposes the agreed completion manifest for
consumers. Recovery preserves original state, claimed source and uncertain effects.
The release includes configurable postcommit source deletion, disabled by default,
with job policy plus current startup authorization and verified receipts.
Source-space admission remains configurable and off by default.

The production use case includes a recorder contacting a remote mover that can
access the source NFS mount. The current loopback prototype does not meet that
requirement. Gate FR-01 must resolve and qualify the remote access boundary;
deferring registration does not authorize exposing the existing endpoint.

## Release gates

A gate closes only with linked passing evidence for its declared supported
configuration and user instructions. Before each qualification increment, list
its finite cases and pass conditions; record unsupported configurations rather
than silently expanding the matrix. New features beyond this scope require an
explicit scope decision. Newly discovered data-safety defects still block release.

| Gate | Remaining deliverable | Closure evidence |
|---|---|---|
| FR-01 | Freeze producer, consumer and access contracts | Versioned OpenAPI and manifest rules; exact retry/error/ID-retention behavior, path/encoding and metadata rules; approved remote listener/caller binding/security profile tested end to end. Preserve the simple recorder workflow. Registration stays deferred until separately scheduled; resolve the remote access prerequisite before enabling it. |
| FR-02 | Qualify source admission and capacity recovery | Actual bounded source-fill/restoration without policy changes; same-ID refusal/retry, no new job or false path release, preserved partial/claimed replay, finite concurrent load and blocked-statistics/root-change cases. Classify inode/quota/external-writer limits and destination-shortage recovery for the declared storage profile. A sample is not a physical reservation. |
| FR-03 | Establish production NFS authority and failure safety | Implement/qualify the [single-host contract](NFS-OWNERSHIP-FENCING-CONTRACT.md), SH-01–14: same configuration/local state, inherited local ownership guard, surviving-worker exclusion, actual NFS mount/root scope and safe delayed-effect reconciliation/refusal. Cover same/separate shares, in-flight namespace/sync effects, server recovery and declared durability limits. Local lock release is not remote-settlement proof. External fencing/cryptographic NAS identity belong to separately qualified extended profiles; no takeover/rebind/stale-state adoption. |
| FR-04 | Implement conservative configurable source cleanup | After FR-03 and relevant worker/filesystem failure gates, pin job cleanup policy, require current authorization and validated destination receipts, delete only owned claimed source, persist progress and retry cleanup independently. Prove off behavior, interruptions, restart, changed destination/custody refusal and retention accounting. Preserve producer-reused paths and other jobs' data. |
| FR-05 | Close scheduling, recovery and lifecycle gaps | Qualify remaining boundaries of the implemented shutdown_wait_seconds setting (default 60, range 1–3600) and bounded stop/status controller; timeout returns incomplete/restart-blocked without releasing live ownership. Complete hard-NFS deadline and manual/systemd coordination evidence. Enumerate remaining durable effect boundaries, allocation/orphan refusal and migrations; test crashes/restart with original state, bounded queues/workers and concurrent load, missing-file timers/backoff, readiness and shutdown with blocked children. Uncertain old effects must prevent unsafe redispatch; timeout alone never proves cancellation. Unsupported repair remains an explicit stop/review outcome. |
| FR-06 | Package the supported deployment | Reproducible locked/offline build and notices, systemd install/service-account permissions and sandbox tests, supported config/provisioning/enrollment, upgrade and rollback rehearsal preserving ownership. Choose the supported SLES-container/deployment matrix and document shared-kernel limits. Keep cargo-zigbuild as the qualified reference until a replacement builder passes equivalent checks. |
| FR-07 | Complete Rust requirements and release evidence | Reconcile active/deferred requirements, derive L2/L3 and discover Rust tests separately from historical evidence; review meaningful failure-path coverage, complete the declared crash/fault matrix and audit the exact shipping ELF/interpreter/libraries. All Rust builds/tests use the GNU/glibc-2.22 SLES gate; qualify production and retained qualification configurations. |
| FR-08 | Deliver user guides and rehearse cutover | Finish DOC-01/02/04/05, update DOC-03 and current architecture/config/CLI/deployment references; execute producer retry/lost-response, consumer validation, capacity recovery and original-state restart walkthroughs on the release candidate. Demonstrate old/new services cannot share source custody. Publish supported profiles, known limits and review/escalation instructions. |

## Execution order and next increment

Selected FR-02 source-capacity cases have evidence in
[increment 38](RUST-INCREMENT-38.md); the eight release gates remain open.
Do not repeat that bounded tmpfs case as unfinished implementation work.

Next qualify remaining buffered NMP-41B fresh/warm-cache and later bootstrap,
untested claim boundaries and actual
pending synchronization/RPC operations, plus untested copy/verification failure directions,
under the [mount-profile contract](NFS-MOUNT-PROFILE.md), MP-01-12. Preserve supervised authorization, descriptor/enrollment authority and
original-state recovery. Selected basic B/B cases do not close the full worker or
synchronization reply-loss matrix. Keep production NFS and source deletion off.

Next qualify remaining server-recovery phases and worker death/replacement,
independent servers/shares and broader filesystem profiles, outstanding UNSTABLE
data and delayed settlement. Establish repeatable bounded abrupt live-server termination
before selecting its mover cases. Preserve original state and actual-exit
exclusion, and cover joint-outage replay/backpressure under the declared profile.
[Increment 87](RUST-INCREMENT-87.md)/SC-121 qualifies only selected live source-copy
continuation with NFSD restart or NFSD-quiesced container restart, on two mounts
sharing one client filesystem. [Increment 88](RUST-INCREMENT-88.md)/SC-122
adds the same finite source-copy cases on two distinct client NFS filesystems
backed by retained bounded tmpfs volumes. [Increment 89](RUST-INCREMENT-89.md)/SC-123
adds selected destination-staging verification recovery on that fixture, with full
reread/EOF before payload and manifest publication.
[Increment 90](RUST-INCREMENT-90.md)/SC-124 adds the selected two-name payload
staging-removal boundary, preserving PublishIntent and the original inode/attempt
through controlled recovery. Next qualify controlled recovery during manifest
commitment; retain remaining initial payload LINK/other sync, bootstrap/claim
and worker-death cases. These increments do not close FR-03/05 or qualify
abrupt recovery, independent NAS, persistent disk or power loss. Additional source
synchronization reply-loss cases require a positively observed actual service RPC in the selected workload. Selected
claim, payload and manifest reply-loss evidence does not qualify every operation,
outage duration, workload or deployment profile.

1. Qualify remaining NFS operation/synchronization and shutdown boundaries,
   remaining endpoint-failure directions/phases beyond selected source-copy
   interruptions, remaining fresh/later source bootstrap and destination recovery
   phases, native SLES systemd/cgroups, actual account/persistence and combined hard-NFS
   lifecycle (SH-01-04/06-14).
   Maintain the [lifetime-ownership fix](RUST-INCREMENT-47.md) and its regression
   matrix; retain the failed increment 46 evidence without calling it support.
   Discover actual mounts/version/security later and qualify NFS recovery
   (SH-10–14) before production enablement. Select/qualify the remote proxy profile
   and RA-01–16 alongside remaining producer/consumer contracts; registration stays deferred.
2. Complete remaining FR-02 capacity cases and corresponding FR-03/05 failure
   cases before implementing FR-04 cleanup. Develop independent contract,
   documentation and packaging work as useful, without treating it as storage
   qualification.
3. Finish FR-06/07/08 and run the declared release-candidate matrix. Enable only
   the production profiles whose gates have closed.

[Increment 39](RUST-INCREMENT-39.md) defines the remote producer access boundary;
implementation and all RA cases remain pending, and FR-01 stays open.
[Increment 40](RUST-INCREMENT-40.md) records the earlier broader fencing design.
[Increment 41](RUST-INCREMENT-41.md) revises the first release to the confirmed
single-host/user-account/local-state profile, with private NFS working folders
and a configurable 60-second shutdown wait. [Increment 42](RUST-INCREMENT-42.md)
implements the shared local guard and explicit worker handoff with selected local
evidence. [Increment 43](RUST-INCREMENT-43.md) implements the configurable wait
and bounded local controller with selected config/clean/timeout/repeated-request
cases. Remaining SH qualification stays pending; FR-03/05 stay open. Prior NF obligations are explicitly
mapped to carry-forward safety or deferred extended profiles. No NAS/host-admin
facility is a prerequisite for independent guard work. Production NFS, remote
REST, takeover and source deletion remain disabled/deferred as applicable.

[Increment 44](RUST-INCREMENT-44.md) adds selected SQLite file/sidecar admission
and mount/owner refusal evidence. These checks do not close FR-03 or FR-06:
deployment persistence, systemd/account policy, remaining shutdown/NFS failure
cases and production enablement remain open.

[Increment 45](RUST-INCREMENT-45.md) adds selected real hard-NFS worker stop,
retained-copy deadline and original-state recovery evidence. FR-03/05 remain open:
other operation/death boundaries, systemd/account coordination and delayed NFS
effects are still prerequisites. No production NFS/deletion enablement follows.

[Increment 46](RUST-INCREMENT-46.md) extends selected coordinator-death cases to
actual blocked/terminating NFS workers and original-state recovery. This is
a failed SH-04 qualification with an observed terminating-worker ownership gap,
not release approval. That counterexample blocks release until addressed; other
operation/death phases, systemd/account behavior and delayed remote effects also
remain prerequisites. Production gates stay off.

[Increment 47](RUST-INCREMENT-47.md) adds independent process-group lifetime
exclusion to address that counterexample. It does not close FR-03/05 or qualify
systemd/group control, other worker death phases, old kernels or NAS settlement.
Production NFS and source deletion remain disabled pending the release gates.

[Increment 48](RUST-INCREMENT-48.md) extends selected death-phase qualification
to fresh, unenrolled bootstrap and accepted source-read workers, including blocked
orphans and separately recorded prompt/incomplete stop outcomes. Read its report
for actual evidence. No Rust/runtime policy change or FR-03/05 closure follows;
at increment 48, enrolled/populated bootstrap, publication/manifest, systemd and
delayed NFS effects remained open. See increment 49 for the selected enrolled/
populated extension. Production NFS and source deletion stay disabled.

[Increment 49](RUST-INCREMENT-49.md) extends the bootstrap fixture to original
enrolled-empty/populated state with retained WAL and a partial copy. Its result
report distinguishes actual surviving orphans, prompt stop and normal same-pair
recovery without re-enrollment. Read the failed seed evidence and correction as
fixture history, not a changed retry/review policy. FR-03/05 remain open for
other operation/shutdown boundaries, both-NFS crashes, systemd and delayed
remote effects. See increment 50 for selected publication/manifest cases.
Production NFS/deletion remain disabled.

[Increment 50](RUST-INCREMENT-50.md) extends destination-NFS death checks to
pre-publication, durable file-link and durable manifest-link boundaries. Read its
results for actual surviving/prompt outcomes, original-inode/attempt/manifest
recovery and exact SLES evidence, including the failed initial qualification run.
FR-03/05 remain open; these finite phase cases do not qualify every RPC/deadline,
both-NFS crash layout, NAS settlement/power durability or actual systemd/account
policy. Production NFS and source deletion remain disabled.

[Increment 51](RUST-INCREMENT-51.md) stabilizes the post-stop status timing test
while preserving the original runtime deadline and existing test bound. Three
qualification rounds per profile retain identity, budget, countdown and ownership
checks; read its fresh SLES results. This test-only change adds no NFS/systemd/
NAS coverage and closes no production release gate. Keep increment 50's failure
history and production NFS/source deletion disabled.

## Selected both-NFS death evidence

[Increment 52](RUST-INCREMENT-52.md) passes 24 selected claim/copy/verification/
publication/manifest death cases with both private roots on one controlled
NFSv4.1 export and local state. Original-state recovery, custody/publication
identity and surviving-worker exclusion are checked. FR-03/05 remain open for
separate exports/independent endpoint failures, remaining both-NFS bootstrap/read,
exact in-flight RPCs, remote settlement/power durability and actual systemd/account
policy. This evidence closes no first-release gate. Production NFS/deletion stay off.


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

## Deferred beyond the first release

S3/object storage, registration/token enrollment, dashboard/UI, offline repair,
populated-state re-enrollment and automated takeover, resumable chunks, advanced
scheduling and performance optimization remain outside this checklist. Optional
generator grouping and per-job policy customization are also deferred. Safe
manual stop/review can remain a supported outcome; unsupported repair is not a
reason to add implicit adoption or deletion.

Registration's selected one-time setup key is retained as a future decision.
Remote access still needs the FR-01 approved boundary; takeover being deferred
does not remove FR-03 same-host exclusion and safe NFS reconciliation requirements.
Until the relevant release gates pass, production NFS and source deletion stay
disabled. No actual SLES host is required: retain pinned SLES 12 SP5 userspace
container qualification and explicitly report untested old-kernel/CPU behavior.

[Increment 57](RUST-INCREMENT-57.md) adds selected real-manager manual/systemd
coordination evidence using systemd 252 and a pinned SLES service root. It leaves
native SLES systemd/cgroups, actual account policy, persistent deployment and
combined hard-NFS/systemd open. All eight release gates remain open; no
production NFS or source deletion is enabled.

[Increment 58](RUST-INCREMENT-58.md) records a blocked private-container 228
preflight, not completion of the older-manager lifecycle work. Ten planned
records remain NOT_RUN; even unit verification cannot initialize on the selected
private cgroup-v2 engine. Compiled directive-name checks do not close FR-05/06.
A suitable approved isolated engine and verified SLES manager-package source
remain prerequisites, with container-only testing and no real SLES installation
requirement. All eight gates remain open; production NFS/deletion stay disabled.

[Increment 59](RUST-INCREMENT-59.md) adds the separately approved Podman-VM
bootstrap for the equivalent-228 lifecycle matrix, preserving earlier failed/
blocked evidence. Use its actual outcomes for the finite local lifecycle scope;
exact vendor patches, old kernels, account/persistence and combined hard-NFS
behavior remain distinct. The lab and limitations guides advance DOC-04/05;
they do not close FR-05/06/08 or any other release gate. Production NFS and
source deletion remain disabled.
All ten selected equivalent-228 local lifecycle records pass, including the
corrected unit-owned shutdown and independent controller checks. This is finite
SH-02/08/09 evidence, not closure of the full deployment/NFS release gates.

[Increment 60](RUST-INCREMENT-60.md) passes four selected combined hard-NFS/
equivalent-228 managed stop/death cases at mid-copy with distinct exports/local
state. It advances finite FR-03/05 evidence; all eight gates remain open.
Remaining operation/endpoint/deadline boundaries, NAS settlement/durability,
actual package/kernel/account/persistence and workload evidence are not waived.
Production NFS and source deletion remain disabled.

[Increment 61](RUST-INCREMENT-61.md) advances finite FR-03/05 evidence for
restart after incomplete stop: two debug/release records with three spaced
explicit starts each, quiet-outage observations, confirmed old-thread exit and
original-state recovery. Read actual automatic/manual intervention outcomes.
Other phases, shipping restart/account/persistence policy, remote settlement and
full SH qualification remain open; all eight release gates and production
NFS/deletion restrictions remain unchanged.

[Increment 62](RUST-INCREMENT-62.md) advances selected FR-03/05 evidence for
destination-only outage before empty/populated startup. Source startup/control
readiness and confirmed custody/202 can succeed while a supervised delivery
worker blocks; see actual death/stop and original-state recovery outcomes.
SC-096 and [the dedicated lab](NFS-DESTINATION-STARTUP-LAB.md) explain that distinction.
Remaining phases, remote effects, supported mount/security/deployment and all eight
release gates stay open. Production NFS and source deletion remain disabled.

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

[Increment 65](RUST-INCREMENT-65.md) qualifies four selected debug/release file/manifest LINK success-reply-loss cases after independent and repeated server-completion/withheld-success/pending-client controls. Recovery preserves original inode/content and attempt one. The loss model explicitly includes connection interruption; it does not qualify source-claim LINK, COMMIT/fsync reply loss, persistent-media/power/server recovery or old kernels. Production NFS and source deletion remain disabled.

[Increment 66](RUST-INCREMENT-66.md) qualifies four selected debug/release source-claim LINK/REMOVE success-reply-loss cases after independent and repeated source-server completion/withheld-success/pending-client controls. Initial/same-ID submissions remain retryable 503 with paths unreleased until original-state custody recovery confirms 202; only then does the producer reuse paths. Original claim inode/content, job ID, database/enrollment and attempt one survive delivery. Loss explicitly includes connection interruption; COMMIT/fsync, remaining claim/mount/security boundaries, server/media/power durability and old kernels remain unqualified. Production NFS and source deletion remain disabled.

[Increment 67](RUST-INCREMENT-67.md) correlates four actual debug/release claim/delivery synchronization traces with raw NFS traffic. Selected noac sync intervals have no observed outgoing RPC; separate buffered OS controls prove stable WRITE reply withholding/recovery, not COMMIT or mover sync-loss support. See [the reproducible sync lab](NFS-SYNC-LAB.md). No Rust/service/dependency policy changes; production NFS and source deletion remain disabled, and FR-03/05 remain open.

[Increment 68](RUST-INCREMENT-68.md) selects the buffered NMP-41B qualification
candidate and retains NMP-41N as a distinct noac diagnostic. The
[mount contract](NFS-MOUNT-PROFILE.md) and [lab](NFS-MOUNT-PROFILE-LAB.md) validate
read-only model decisions for selected SH-10/12/13 inventory cases. That increment did not include Rust
startup/effect enforcement; increments 69-70 below add supervised checks and
selected worker cases. Remaining buffered fault coverage stays open. Reused mount IDs show that matching pins do
not prove continuity. FR-03/05 remain open; production NFS/deletion stay disabled.

[Increment 69](RUST-INCREMENT-69.md) integrates explicit nfs_mount declarations and
proc-to-root-descriptor/profile fingerprints into supervised bootstrap and worker
authorization. Selected live mismatch/refusal/restoration/replay cases and both
SLES gates complement the independent model; they do not close FR-03/05. Legacy
NFS profile-less bindings refuse without automatic migration. Production NFS and
source deletion remain disabled; increment 70 below adds selected same-share
worker cases. Remaining B/B interruption and synchronization/recovery work stays open.

[Increment 70](RUST-INCREMENT-70.md) adds selected actual same-share buffered
worker evidence: debug/release baselines and durable claim/file LINK crash
recovery, original-state replay and unchanged producer-reused bytes. See the
[same-share lab](NFS-SAME-SHARE-LAB.md). SH-10 gains finite same-mount coverage;
remaining buffered outage, RPC/sync and bootstrap/copy/verify/manifest boundaries
stay open. FR-03/05 and all eight release gates remain open; production NFS and
source deletion remain disabled.

[Increment 71](RUST-INCREMENT-71.md) addresses selected buffered NMP-41B
copy/verification interruption/death recovery on same/separate shares. The
[lab](NFS-BUFFERED-READS-LAB.md) requires actual blocked read descriptors and
surviving-worker exclusion before original-state recovery. Joint outage of one
server is distinct from independent endpoints or mutating-RPC settlement.
FR-03/05 and all eight release gates remain open. Keep production NFS and source
deletion disabled; remaining buffered bootstrap/publication/manifest, failure
directions, synchronization, workload and deployment cases stay open.

[Increment 72](RUST-INCREMENT-72.md) addresses selected buffered file/manifest
publication interruption and original-state recovery on both layouts; see the
[lab](NFS-BUFFERED-PUBLICATION-LAB.md). Returned-LINK/pre-sync process crashes
and actual pending staging unlinkat are distinct from withheld-success RPCs or
in-flight fsync/COMMIT. Normal recovery must retain original payload/manifest
allocations and producer-reused bytes. Remaining boundaries, remote settlement,
workload and deployment gates stay open. Production NFS/source deletion remain
disabled; all eight release gates stay open.

[Increment 73](RUST-INCREMENT-73.md) passes eight selected buffered
after-staging-unlink/before-directory-sync process-crash cases across both share
layouts and build profiles. See [the lab](NFS-BUFFERED-POST-UNLINK-LAB.md) for
absent staging, original one-link final allocation, original-state attempt-1
recovery, replay and measured limits. Earlier failed aggregate-timer evidence
remains failed; corrected requests have separate timing checks. Actual pending
sync/RPC, remote settlement, workload and deployment qualification remain open.
All eight release gates stay open; production NFS and source deletion remain off.

## Buffered pre-202 source-claim evidence

[Increment 74](RUST-INCREMENT-74.md)/SC-109 adds eight buffered source-claim
LINK/REMOVE interruption/recovery cases across both layouts and profiles; see
[the step-by-step lab](NFS-BUFFERED-CLAIM-LAB.md). Keep actual client syscall
proof separate from server completion/reply-loss proof. Preserve immutable
producer files/parents until confirmed custody/202 and original-state/inode
recovery after actual old-worker exit. No full release gate is closed by this
finite matrix; production NFS and source deletion remain disabled.

## Buffered enrolled/populated bootstrap evidence

[Increment 75](RUST-INCREMENT-75.md)/SC-110 adds eight buffered startup
interruption/recovery cases, enrolled-empty/populated across both layouts and
profiles. See [the step-by-step lab](NFS-BUFFERED-BOOTSTRAP-LAB.md) for cache aging,
actual blocked bootstrap, Starting/no false-ready response, surviving-worker
exclusion and original-state/WAL/partial/inode recovery. Preserve remaining fresh/
warm-cache/later startup, synchronization, workload and deployment qualification.
All eight release gates stay open; production NFS and source deletion stay off.

[Increment 76](RUST-INCREMENT-76.md)/SC-111 adds eight healthy buffered
claim/delivery synchronization observations and conditional native capability
discovery. Read the actual observed operations and unknown traffic before
defining a service fault matrix; neither successful fsync nor OS controls close
FR-03/05 or physical durability. The [lab](NFS-BUFFERED-SYNC-LAB.md) documents
clock/process privileges, exact wire evidence and limits. All eight gates remain
open, with production NFS/deletion disabled.

[Increment 77](RUST-INCREMENT-77.md) extends SC-111 with actual buffered worker
file-operation observations and descriptor/filehandle/payload attribution.
Its [lab](NFS-BUFFERED-IO-LAB.md) distinguishes supported identity matches,
plain timing, unmatched/unknown operations and the initially refused fixture
analysis. This selects future finite RPC fault cases; it adds none itself and
closes no full FR-03/05 gate. Production NFS/deletion remain disabled.

[Increment 78](RUST-INCREMENT-78.md)/SC-112 qualifies six native COMMIT
controls and eight finite payload-fchmod service release/death-drop cases on
both buffered layouts/profiles. Its [lab](NFS-BUFFERED-COMMIT-LAB.md) documents
matched completion-withheld proof, original-state/partial recovery and cleanup.
This supplies selected FR-03/05 evidence, not full gate closure. UNSTABLE WRITE
loss, live COMMIT loss without death, unobserved sync phases, workload/NAS/kernel
and remaining deployment qualification stay open. Keep all eight gates open and
production NFS/source deletion disabled.

[Increment 79](RUST-INCREMENT-79.md)/SC-113 qualifies six native UNSTABLE
WRITE controls and eight finite service release/death-drop cases, preserving
original state/source/partial and producer reuse after 202. Its
[complete lab](NFS-BUFFERED-UNSTABLE-LAB.md) includes initial validator failure,
corrected slot-hint identity checks, actual all-range retransmission/COMMIT proof,
cleanup and testing limits. This adds selected FR-03/05 evidence; all eight gates
stay open. Live-coordinator reply loss without death and broader kernel/NAS/
workload/durability/deployment obligations remain future work. Production NFS and
source deletion stay disabled.

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
