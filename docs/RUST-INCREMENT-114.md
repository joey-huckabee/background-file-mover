# Remove retired implementation and coupled tooling

2026-11-07. The user authorizes a branch, complete removal of the retired
implementation and its references, and merge to main. This supersedes the
reference-retention decision from the preceding integration. Baseline main is
`f8443e8cebec9085c8100bf00a883e9210c82227`.

## Scope

Remove the retired application source, vendored/test trees, build/fuzz/analysis
workflows and image, editor launch settings, sample configuration/service unit,
comparison harnesses and their result documents, obsolete parser/build decisions
and coupled traceability/smoke tools. Update current guides, links and instruction
files to describe Rust only. Keep the generic staged-file hook and installation/
mode tools, without obsolete application builds or trace-generator calls.

The application is Rust under rust/. Native C fixtures required by current Rust
NFS/systemd/qualification work remain. Their source, runtime libraries, toolchain
pins and authentic retained Rust evidence are not application-reference code.
No dependency notice, ABI check or licensing obligation is dropped.

## Dependency and requirement preservation

The live SLES gate previously consumed dependency data from a retired comparison
report. Extract its exact dependency records and selected Tokio features into
scripts/rust-qualified-dependencies.json before deleting that report. No version,
feature or license value changes. Keep full target graph equality, integrity
checksums, Cargo.lock, selected features, capability labels, offline behavior and
independent ELF/runtime audits. Include the new pin file in CI path triggers and
record its SHA-256 in each gate report. Extracting values alone is not new
qualification. The regression verifies pin membership/checksums against the lock.

Preserve L1/L2 functional IDs and retained L3 obligations. Retire obsolete
implementation-specific mechanisms/IDs without reuse or coverage claims. Explicitly
retain directory fsync before publication, readiness behavior when unrequested,
flock lifetime and the ban on unlinking lock files. Keep TRANSFER-PROTOCOL.md,
approved API groups, state/custody/refusal rules and qualification limits.
Replace obsolete coverage output with an honest traceability status: Rust
requirement/test discovery remains open under P10/RC-23. Historical percentages
and comparison outputs do not become current Rust qualification.

The delivery plan retains the R0-R14 release-deliverable inventory and current
release/protocol requirements while retiring obsolete implementation-comparison
instructions. The organizational license exclusions remain unchanged in
LICENSE-POLICY.md.

## Runtime and validation boundary

The only application source edit changes an explanatory HTTP-parser comment.
Non-comment Rust statements, Cargo manifests/lock, schemas, tests and C fixtures
remain unchanged. No runtime behavior, producer wire, transfer/retry policy,
state format or payload operation is introduced by cleanup.

Required closeout: exact pin-extraction comparison, repository reference and
local-link audits, generic hook/Python checks, independent removal review and
fresh production/qualification SLES PR checks. Actual acceptance is recorded in
the cleanup PR and its retained run artifacts before merge; no pass is declared
merely by this document. Prior Rust evidence remains tied to its original
inputs/hashes and is not rewritten as qualification of the cleaned source.

All eight release gates stay open. Production NFS/source deletion, migration
apply, UUID/manifest-v2 activation and deployment remain disabled/separately
authorized. No operational database, payload or live service is changed.
