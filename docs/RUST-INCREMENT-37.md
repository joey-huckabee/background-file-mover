# Rust increment 37: first-release scope and finish line

Documentation increment on `feature/rust-transfer-coordinator`, 2026-10-16.
Defines [the first-release checklist](RUST-FIRST-RELEASE.md) in response to the
request for a bounded finish line. It assigns no release version, date or
completion percentage and makes no runtime support claims.

The eight open gates cover contracts/remote access, capacity admission, NFS
authority and failures, conservative configurable cleanup, scheduling/recovery,
deployment, Rust traceability and user/cutover evidence. The intended release
preserves 202-after-all-claims, the simple recorder, configured filesystem
routing, relative folders and 3N integrity verification. Source-space admission
and eventual cleanup default off. Production NFS/deletion remain disabled.

S3, registration, dashboard, offline repair, populated re-enrollment/takeover and
optimization stay deferred. Remote recorder access is an explicit release
prerequisite despite deferred registration; no loopback prototype exposure is
authorized. Deferring takeover does not waive normal NFS ownership/fencing.

The next implementation increment qualifies native source-fill/restoration in
bounded disposable storage with unchanged policy, original local SQLite state,
existing/partial replay and same-ID recovery. It does not fill a host disk or
claim to close all remaining capacity/NFS cases. Subsequent work resolves access
and fencing prerequisites before dependent qualification and cleanup.

The future-only roadmap links the finish line while retaining broader backlog.
README, handoff, AGENTS and the scenario catalog link the release priorities.
All 81 stable scenario IDs, six DOC items and existing evidence scopes remain.

## Validation

Documentation-only checks cover local Markdown link targets, unique release-gate
and scenario IDs, DOC items, unchanged Rust source/dependency files, trace-matrix
consistency and whitespace. No Rust build/test or NFS fixture is needed or run
for these documentation changes. Increment 36 remains the runtime evidence;
its pushed implementation CI run 38986905658 completed successfully. The new
checklist does not requalify any binary, filesystem or deployment.
