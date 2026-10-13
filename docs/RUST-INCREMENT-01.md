# Rust core protocol increment

The first Rust slice introduces `rust/crates/mover-core` without external
dependencies, on `feature/rust-transfer-coordinator`. It makes the agreed
protocol guards executable while storage/API details continue incrementally.

## Validation

Ten integration tests passed on 2026-10-13 using Rust/Cargo 1.99.0 in Ubuntu WSL.
Sources were staged on the native filesystem in a temporary directory; the
historical WSL checkout on integration-lab was not modified. Formatting and
Clippy with warnings denied passed. Cargo tests/checks were offline/locked.

| Guard | Test |
|---|---|
| Acceptance and partial claims cannot release paths | `acceptance_and_partial_claims_never_release_paths` |
| Optional expected size/empty-file handling | `expected_size_mismatch_does_not_confirm_claim` |
| Stable replay identity and pinned route | `replay_preserves_handoff_and_pinned_policy` |
| Verification/publication precede set commitment | `publication_and_commit_require_all_prior_evidence` |
| Both cleanup policy switches and whole-set commitment | `cleanup_requires_job_policy_current_permission_and_set_commit` |
| Claim replay cannot change observed size | `repeated_claim_cannot_change_recorded_size` |
| Relative traversal/reserved names rejected | `path_traversal_and_reserved_names_are_rejected` |
| Duplicate/prefix conflicts, including intervening sorted names | `duplicate_and_prefix_conflicts_are_order_independent` |
| Empty requests/unknown files cannot advance | `empty_requests_and_unknown_files_do_not_advance` |
| Aggregate overflow is not a wrapped small size | `aggregate_overflow_is_not_reported_as_small_recording` |

Source: [protocol.rs](../rust/crates/mover-core/tests/protocol.rs).
Run [test-rust-wsl.sh](../scripts/test-rust-wsl.sh) or the native commands in
[rust/README.md](../rust/README.md).

## Evidence limits

This is partial pure-decision evidence for L1-API-008/009 and
L1-SYS-025/028/029/032, not completed production verification. The historical
generated matrix does not discover Rust tests; integrate Rust L2/L3/test discovery
deliberately instead of marking these requirements implemented from guard tests.

No SQLite persistence, actual claim, HTTP response, hashing, NFS execution,
manifest publication, worker supervision or source unlink is implemented. The
model trusts its caller's receipts. Future effect adapters must commit intent,
perform/reconcile effects and durably record results before confirming transitions.
Host tests do not qualify a SLES artifact. No package experiment was resumed.
