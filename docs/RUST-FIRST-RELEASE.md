# First Rust release checklist

Release scope recorded 2026-10-16; closure review updated 2026-10-22 on `feature/rust-transfer-coordinator`.
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

All eight gates remain open. The [closure review](RUST-RELEASE-CLOSURE.md)
audits existing code/evidence, identifies implementation gaps and records the
24 acceptance families RC-01-24. Use that fixed matrix and its P01-12 order;
do not keep selecting new NFS experiments without a named remaining obligation.
A gate needs passing evidence and user instructions for its declared profile.

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

## Next work and release decisions

The user requests full detailed job history until explicit admin dashboard clear.
Explicit clear forgets the UUID; late reuse is new recording work. Only completed
or safely cancelled jobs may clear; cancel unfinished/errored jobs first.
Cancellation and history clear preserve files; separate ownership/accounting
survives clear without UUID replay recognition. Finalize the separate explicit
retained-data deletion admin wire/access and release placement
before freezing the contract; no automated compaction or
blanket UI deferral should silently substitute for that decision.

The [error review](REST-ERROR-SCENARIOS.md) records approved groups 1-34:
fifty initial outcome mappings, error envelope, configurable recorder retry
timing and current-configuration expected-size policy. Follow API-I01-06 after remaining request/schema/compatibility decisions
are resolved. API-E01-110 are acceptance situations, not new qualification passes;
approved missing-file 409/global-ID behavior is not implemented yet. No Rust
prototype API clients exist, so replace its old producer format directly without
an adapter; stored-job/custody safeguards and separate C++ cutover remain.

Next: P01, freeze versioned OpenAPI, manifest validation and the supported route,
error/retry, path/metadata and ID-retention inventory. Preserve existing behavior
and identify design decisions before changing it. Remote access (P02-03), durable
allocation ordering (P04), remaining bounded qualification (P05-07), configurable
cleanup (P08), packaging (P09), traceability/docs (P10-11) and candidate rehearsal
(P12) follow the dependencies in the closure review.

D01-05 record unresolved mount inventory, proxy selection, shipping lifecycle
profile, unproven storage faults and cutover/rollback policy. They are not waived
by this schedule. Keep container-only SLES compatibility qualification; no real
SLES installation prerequisite. No production NFS or source deletion enablement
is authorized here. Registration, S3, cross-host takeover and offline repair stay
deferred; configurable default-off cleanup remains required for this release.

Selected source-capacity evidence from increment 38 and subsequent NFS/lifecycle
results are credited in the review. Preserve all
[previous checklist notes](RUST-RELEASE-EVIDENCE-HISTORY.md) as historical evidence,
not instructions to continue unbounded qualification. This documentation review
adds no new runtime/test result and does not assign a release date or percentage.
