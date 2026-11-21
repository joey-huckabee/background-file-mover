# L2 to Rust evidence

Each row maps one [L2 requirement](L2-REQ.md) to Rust evidence. This is the
P10/RC-23 traceability work, done one family per increment
([plan](TRACE-MATRIX.md#plan)). `scripts/check_trace.py` checks this file: every
ID exists in L2-REQ.md, every cited test function exists in the cited file, and
every disposition is allowed.

**Dispositions:**
- **Tested:** the named tests show the requirement.
- **Partly tested:** tests show part of it; the rest is cited by inspection.
- **Inspection:** code only; no test isolates it.
- **Deviation (needs approval):** Rust meets the intent by a different
  mechanism. It stays open until the user accepts the deviation or the
  requirement is reworded.
- **Not applicable (needs approval):** proposed only; never final without the
  user.
- **Open:** no evidence found yet.

Evidence is written `path::test_name` for tests and `path` for inspected code,
relative to `rust/crates/`. A test listed here shows behavior in the build and
storage it runs on; it does not qualify NFS, systemd or physical faults (see
the [deployment matrix](SUPPORTED-DEPLOYMENT.md)).

## DPR — Data preservation (parent L1-SYS-003)

| L2 | Disposition | Evidence | Notes |
|---|---|---|---|
| L2-DPR-001 | Tested | mover-fs/tests/transfer.rs::abrupt_exit_at_each_durable_copy_and_publication_boundary; mover-fs/tests/transfer.rs::corrupted_staging_with_restored_metadata_fails_independent_hash | Each attempt copies into `<recording>/.staging/<attempt>.part`. The final name does not exist until publication. |
| L2-DPR-002 | Partly tested | mover-fs/tests/transfer.rs::abrupt_exit_at_each_durable_copy_and_publication_boundary; mover-fs/src/transfer.rs | The test shows the Copied, Verified and PublishIntent phases are reached and recovered before the final name exists. The syncs (`sync_file` after the copy; the publication file, staging and parent syncs) are by inspection. NFS durability is covered only by the lab records. |
| L2-DPR-003 | Partly tested | mover-fs/tests/transfer.rs::lost_custody_and_source_changes_block_transfer; mover-fs/src/transfer.rs | The test shows a source whose size changed is refused before publication. The staging-size and verification-size checks (`staging size mismatch`, `verification size/identity changed`) are by inspection. |
| L2-DPR-004 | Tested | mover-fs/tests/transfer.rs::corrupted_staging_with_restored_metadata_fails_independent_hash; mover-fs/tests/transfer.rs::cross_filesystem_copy_large_file_retains_source_and_preserves_names | SHA-256 is always computed, with no option to turn it off. Staged bytes are re-hashed independently: a mismatch stays Copied and never publishes. The recorded digest equals `sha256sum` of the source. |
| L2-DPR-005 | Tested | mover-fs/tests/transfer.rs::abrupt_exit_at_each_durable_copy_and_publication_boundary; mover-fs/tests/transfer.rs::foreign_equal_content_final_is_never_overwritten; mover-fs/src/relocate.rs::collision_at_the_link_transition_never_clobbers_or_removes_original | Publication is an atomic same-filesystem `renameat2(RENAME_NOREPLACE)` from staging to the final name, so an existing name is never replaced. Only where the filesystem reports that flag unsupported (`ENOSYS`, `EOPNOTSUPP`, `EINVAL`) does it fall back to a no-clobber hard link, then remove the staging name (`mover-fs/src/relocate.rs`). Both paths are tested; the fallback is a different mechanism from the literal "rename" and is listed for review. |
| L2-DPR-006 | Tested | file-mover/tests/api.rs::move_mode_removes_held_copies_only_after_verified_delivery; file-mover/tests/api.rs::source_removal_requires_the_full_set_verified_in_the_same_session; mover-core/tests/protocol.rs::cleanup_requires_job_policy_current_permission_and_set_commit | Source copies are removed only in move mode, only after commit and only after the whole delivered set is checked again. A tampered delivery keeps the source copy. In copy mode (the default) the mover never removes them. |
| L2-DPR-007 | Tested | mover-fs/tests/transfer.rs::corrupted_staging_with_restored_metadata_fails_independent_hash; mover-fs/tests/transfer.rs::lost_custody_and_source_changes_block_transfer; mover-fs/tests/transfer.rs::abrupt_exit_at_each_durable_copy_and_publication_boundary; mover-store/src/tests.rs::move_mode_failures_keep_authorization_distinct_and_back_off | A failed verification, a changed source, an interruption at any copy or publication boundary, or a failed cleanup check keeps the claimed source copy. |
