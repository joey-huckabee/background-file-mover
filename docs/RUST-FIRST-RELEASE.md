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

Next qualify remaining buffered NMP-41B bootstrap/claim, post-unlink/pre-sync
and actual pending synchronization/RPC boundaries, plus untested copy/verification failure directions,
under the [mount-profile contract](NFS-MOUNT-PROFILE.md), MP-01-12. Preserve supervised authorization, descriptor/enrollment authority and
original-state recovery. Selected basic B/B cases do not close the full worker or
synchronization reply-loss matrix. Keep production NFS and source deletion off.

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
