# First Rust release checklist

Release scope recorded 2026-10-16 on `feature/rust-transfer-coordinator`.
This is the release finish line within the broader [roadmap](ROADMAP.md), not a
production-support declaration or a replacement for requirements. No release
version or delivery date is assigned. All gates below remain open; implemented
parts and their evidence stay in the [scenario catalog](RUST-SCENARIOS.md) and
increment reports. Do not count increments or passing tests as a completion
percentage.

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

1. Qualify remaining guard/death-phase and shutdown boundaries, actual NFS
   workers beyond deadlines and systemd/account-control (SH-01–04/06–14).
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
