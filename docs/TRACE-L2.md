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
relative to `rust/crates/`. A `scripts/...` path is a repository CI test in
another language (for example dashboard JavaScript). A test listed here shows behavior in the build and
storage it runs on; it does not qualify NFS, systemd or physical faults (see
the [deployment matrix](SUPPORTED-DEPLOYMENT.md)).

## DPR — Data preservation (parent L1-SYS-003)

| L2 | Disposition | Evidence | Notes |
|---|---|---|---|
| L2-DPR-001 | Tested | mover-fs/tests/transfer.rs::abrupt_exit_at_each_durable_copy_and_publication_boundary; mover-fs/tests/transfer.rs::corrupted_staging_with_restored_metadata_fails_independent_hash | Each attempt copies into `<recording>/.staging/<attempt>.part`. The final name does not exist until publication. |
| L2-DPR-002 | Partly tested | mover-fs/tests/transfer.rs::abrupt_exit_at_each_durable_copy_and_publication_boundary; mover-fs/src/transfer.rs | The test shows the Copied, Verified and PublishIntent phases are reached and recovered before the final name exists. The syncs (`sync_file` after the copy; the publication file, staging and parent syncs) are by inspection. NFS durability is covered only by the lab records. |
| L2-DPR-003 | Partly tested | mover-fs/tests/transfer.rs::lost_custody_and_source_changes_block_transfer; mover-fs/src/transfer.rs | The test shows a source whose size changed is refused before publication. The staging-size and verification-size checks (`staging size mismatch`, `verification size/identity changed`) are by inspection. |
| L2-DPR-004 | Tested | mover-fs/tests/transfer.rs::corrupted_staging_with_restored_metadata_fails_independent_hash; mover-fs/tests/transfer.rs::cross_filesystem_copy_large_file_retains_source_and_preserves_names | SHA-256 is always computed, with no option to turn it off. Staged bytes are re-hashed independently: a mismatch stays Copied and never publishes. The recorded digest equals `sha256sum` of the source. |
| L2-DPR-005 | Deviation (needs approval) | mover-fs/tests/transfer.rs::abrupt_exit_at_each_durable_copy_and_publication_boundary; mover-fs/tests/transfer.rs::foreign_equal_content_final_is_never_overwritten; mover-fs/src/relocate.rs::collision_at_the_link_transition_never_clobbers_or_removes_original | Publication is an atomic same-filesystem `renameat2(RENAME_NOREPLACE)` from staging to the final name; an existing name is never replaced. Where the filesystem reports that flag unsupported (`ENOSYS`, `EOPNOTSUPP`, `EINVAL`), it falls back to a no-clobber hard link, then removes the staging name (`mover-fs/src/relocate.rs`). That fallback is not the required rename. **Decision:** accept the fallback, or reword the requirement to "atomic, no-clobber publication". Both paths are tested. |
| L2-DPR-006 | Deviation (needs approval) | file-mover/tests/api.rs::move_mode_removes_held_copies_only_after_verified_delivery; file-mover/tests/api.rs::source_removal_requires_the_full_set_verified_in_the_same_session; mover-core/tests/protocol.rs::cleanup_requires_job_policy_current_permission_and_set_commit; file-mover/tests/api.rs::confirmed_deletion_removes_only_retained_copies_and_keeps_replay | **Automatic removal** meets the requirement. It happens only in move mode, after commit, and after the whole delivered set is checked again; a tampered delivery keeps the copy. **Operator-confirmed deletion** (increments 143/144, behind `admin_ingress.allow_data_deletion`, off by default) is approved behavior that removes the mover's held source copies without that condition: for delivered jobs in copy mode, and for cancelled jobs whose files were never published. Deletion touches only the mover's private held copies, never the sender's paths. A job can be cancelled while partly claimed, before any 202, and its held copies then deleted. **Decision:** reword the requirement to exempt explicit, operator-confirmed deletion. |
| L2-DPR-007 | Partly tested | mover-fs/tests/transfer.rs::corrupted_staging_with_restored_metadata_fails_independent_hash; mover-fs/tests/transfer.rs::lost_custody_and_source_changes_block_transfer; mover-fs/tests/transfer.rs::abrupt_exit_at_each_durable_copy_and_publication_boundary; file-mover/tests/api.rs::move_mode_removes_held_copies_only_after_verified_delivery | **Refusal tests:** a failed independent verification and a changed source keep the claimed source copy, and a changed delivery blocks move-mode removal. **Recovery:** a process exit at each copy and publication checkpoint keeps the source copy and resumes (the operations themselves succeeded; this tests interruption, not their failure). **Not isolated:** failure of each flush, sync or publication call is handled by returning an error before any source removal (`mover-fs/src/transfer.rs`, `relocate.rs`), but is not injected by a test. |

## DST — Destination publication (parents L1-SYS-003, L1-SYS-007)

| L2 | Disposition | Evidence | Notes |
|---|---|---|---|
| L2-DST-001 | Tested | mover-fs/tests/transfer.rs::foreign_equal_content_final_is_never_overwritten; mover-fs/tests/transfer.rs::incomplete_set_and_foreign_manifest_never_commit; mover-fs/tests/transfer.rs::committed_or_substituted_destination_data_is_never_deleted; file-mover/tests/api.rs::operator_resume_keeps_collision_safe_and_reconciles_same_verified_attempt | An existing final file (same inode afterwards) and an existing `COMMITTED.json` are left untouched. Destination deletion refuses a committed area, a substituted final file and a symlinked area. |
| L2-DST-002 | Tested | mover-fs/tests/transfer.rs::foreign_equal_content_final_is_never_overwritten; mover-fs/tests/transfer.rs::publication_intent_reconciles_owned_aliases_and_retains_source; file-mover/tests/api.rs::operator_resume_keeps_collision_safe_and_reconciles_same_verified_attempt | The requirement allows reuse **or** collision. The mover always takes the collision branch for a destination it did not create, even one with identical content. It only reconciles its own recorded objects, matched by recorded identity, after an interruption. |
| L2-DST-003 | Tested | file-mover/tests/api.rs::operator_resume_keeps_collision_safe_and_reconciles_same_verified_attempt; mover-core/tests/protocol.rs::cleanup_requires_job_policy_current_permission_and_set_commit; mover-fs/tests/transfer.rs::foreign_equal_content_final_is_never_overwritten | A differing file at the final name (`foreign recording`) fails delivery, is kept, and no `COMMITTED.json` is written. Source removal requires commit, so the source copy stays. |
| L2-DST-004 | Partly tested | mover-fs/tests/transfer.rs::abrupt_exit_at_each_durable_copy_and_publication_boundary; mover-fs/tests/transfer.rs::incomplete_set_and_foreign_manifest_never_commit | **Tested (mover side):** in-progress copies exist only as `.staging/<attempt>.part`, a final name appears only after verification, and `COMMITTED.json` is not written while any file is unpublished. **Documented obligation (consumer side):** consumers must ignore `.staging/` and any folder without a validated manifest ([consumer guide](CONSUMER-GUIDE.md)). No test exercises a consumer. |
| L2-DST-005 | Tested | mover-fs/tests/transfer.rs::multi_file_delivery_commits_exact_manifest_and_retains_every_claim; mover-fs/tests/transfer.rs::incomplete_set_and_foreign_manifest_never_commit | The tests show `COMMITTED.json` is written only when every file is in place. They check each listed path, its measured size and its delivered bytes, and that the published manifest equals the saved record and is not rewritten on a repeat. They do not check the per-file SHA-256 fields. It can be visible before the mover records the commit, so consumers validate it ([consumer guide](CONSUMER-GUIDE.md)). |

## DEL — Source deletion (parent L1-SYS-003)

Source copies are removed in two ways: **automatic** removal in move mode, and
**operator-confirmed** deletion (increments 143/144, off by default). Both remove
only the mover's private held copy (`<source root>/.file-mover/<job>-<index>/data`)
through `mover-fs` `discard_retained_source`, never a sender's path.

| L2 | Disposition | Evidence | Notes |
|---|---|---|---|
| L2-DEL-001 | Tested | mover-fs/tests/claim.rs::discard_removes_only_the_exact_retained_copy; mover-store/src/tests.rs::deletion_passes_target_only_retained_copies_of_stopped_jobs; file-mover/tests/api.rs::confirmed_deletion_removes_only_retained_copies_and_keeps_replay | Targets come only from durable claim records (the claim intent: recorded root, private area and object identity). The sender's reused original path and other jobs' copies are untouched. |
| L2-DEL-002 | Tested | mover-fs/tests/claim.rs::discard_removes_only_the_exact_retained_copy; file-mover/tests/api.rs::move_mode_removes_held_copies_only_after_verified_delivery | There is no rescan: removal works from recorded claims only. A new file written at the original path after the claim (what a rescan would find) is never touched. |
| L2-DEL-003 | Tested | mover-fs/tests/claim.rs::discard_removes_only_the_exact_retained_copy | Just before removal the mover checks the root, the private area and the copy against their recorded identities. After the unlink it checks that the open handle has zero links. A replaced copy or a symlinked area is refused and kept. |
| L2-DEL-004 | Deviation (needs approval) | file-mover/tests/api.rs::move_mode_removes_held_copies_only_after_verified_delivery; file-mover/tests/api.rs::source_removal_requires_the_full_set_verified_in_the_same_session; mover-core/tests/protocol.rs::cleanup_requires_job_policy_current_permission_and_set_commit | Automatic removal meets it: commit plus a fresh check of the whole delivered set, and a tampered delivery keeps the copy. Operator-confirmed deletion can remove held copies of cancelled jobs whose delivery never completed. This is the same approved exception and the same decision as L2-DPR-006. |

## CLN — Cleanup and source retention (parents L1-SYS-003, L1-SYS-005, L1-SYS-010)

| L2 | Disposition | Evidence | Notes |
|---|---|---|---|
| L2-CLN-001 | Tested | mover-fs/tests/claim.rs::discard_removes_only_the_exact_retained_copy; file-mover/tests/api.rs::move_mode_removes_held_copies_only_after_verified_delivery; mover-store/src/tests.rs::move_mode_cleans_committed_move_jobs_with_intent_before_effect | Repeating a removal returns "already absent". The intent is recorded before the effect, and a removal that happened but was not recorded is completed after restart, not repeated. |
| L2-CLN-002 | Deviation (needs approval) | file-mover/tests/api.rs::move_mode_removes_held_copies_only_after_verified_delivery; mover-store/src/tests.rs::move_mode_cleans_committed_move_jobs_with_intent_before_effect | **Automatic cleanup (tested):** a removal can be recorded only after its authorization, and authorization only after the committed delivered set is verified. The move-mode test covers recovery: a removal authorized and applied before an interruption is recorded as done afterwards. **Operator-confirmed deletion (the approved exception):** an absent held copy also counts as deleted, including for cancelled jobs without a verified destination. Same decision as L2-DPR-006 and L2-DEL-004. |
| L2-CLN-003 | Inspection | mover-fs/src/lib.rs | The mover reports removal of the **copy**, not the folder. The private folder is removed only if empty: a non-empty one is kept (`remove_empty_area` ignores `ENOTEMPTY`) and never reported as removed. No test leaves an extra file in the folder. |
| L2-CLN-004 | Partly tested | mover-fs/tests/claim.rs::discard_removes_only_the_exact_retained_copy; file-mover/tests/api.rs::move_mode_removes_held_copies_only_after_verified_delivery | **Tested:** an unexpected object at the copy's name (replaced copy, symlinked folder) is refused, kept and reported as a failure: in move mode the job goes to Needs attention with the error. **Gap:** an extra file beside the copy is kept **silently**, not reported or routed to an operator. **Decision:** whether to report such leftovers. |
| L2-CLN-005 | Tested | mover-fs/tests/claim.rs::discard_removes_only_the_exact_retained_copy | A copy whose identity (device, inode and the rest of the recorded identity) differs from the claim is refused and kept. |

## SUB — Submission and claiming (parents L1-SYS-002, L1-SYS-003, L1-SYS-004, L1-SYS-007)

| L2 | Disposition | Evidence | Notes |
|---|---|---|---|
| L2-SUB-001 | Tested | mover-store/src/tests.rs::replay_rejects_changed_details_and_keeps_original_context; mover-fs/tests/claim.rs::actual_sizes_nested_paths_partial_handoff_and_path_reuse | A repeated request returns the original job (same `job_id`, saved context, replay flag) and does not claim again. A new file the sender wrote at the released path is left alone. A changed request is a conflict, not a new job. |
| L2-SUB-002 | Tested | mover-fs/tests/claim.rs::actual_sizes_nested_paths_partial_handoff_and_path_reuse; mover-fs/tests/claim.rs::missing_second_file_retains_first_claim_and_all_reservations; mover-core/tests/protocol.rs::acceptance_and_partial_claims_never_release_paths | The job is recorded first. Handoff stays Pending while any file is unclaimed, across a store reopen, and becomes Ready (202) only after every file is claimed. |
| L2-SUB-003 | Tested | file-mover/tests/api.rs::malformed_json_scope_and_http_framing_never_claim; mover-core/tests/protocol.rs::empty_requests_and_unknown_files_do_not_advance | Malformed bodies, out-of-scope folders, `..` paths and bad sizes are refused without claiming, and the source file stays. An empty file list is refused by request validation (`mover-core/src/recording.rs`, 1-256 files). |
| L2-SUB-004 | Deviation (needs approval) | mover-store/src/tests.rs::failure_mid_file_list_rolls_back_partial_acceptance; mover-fs/tests/claim.rs::durable_claim_intent_reconciles_its_two_name_link_intermediate | No separate manifest file is written at submission. The claimed set is recorded durably in SQLite: the job and its file list in one transaction, rolled back whole on failure, plus a claim record with the recorded identity before each move. The written manifest is `COMMITTED.json` at delivery. **Decision:** accept the database record as the submission manifest, or reword. |
| L2-SUB-005 | Tested | mover-fs/tests/claim.rs::missing_second_file_retains_first_claim_and_all_reservations; mover-store/src/tests.rs::failure_mid_file_list_rolls_back_partial_acceptance | When a later file is missing, the first claimed file stays in private custody and its reservations stay, across a reopen. A failed acceptance leaves no partial record. |

## FS — Filesystem identity and claiming (parent L1-SYS-004)

| L2 | Disposition | Evidence | Notes |
|---|---|---|---|
| L2-FS-001 | Tested | mover-fs/tests/claim.rs::identity_changes_and_recovery_with_reappeared_original_block; mover-fs/tests/claim.rs::collisions_and_unrecorded_directory_are_never_adopted | The claim intent records the observed source identity (device, inode, owner, size, mtime, links) before any move. A file replaced after the intent is refused. |
| L2-FS-002 | Partly tested | mover-fs/tests/claim.rs::durable_claim_intent_reconciles_its_two_name_link_intermediate; mover-fs/tests/claim.rs::abrupt_process_exit_reconciles_intent_effect_and_receipt_boundaries | Recovery tests show the moved object is matched to its recorded identity before the claim completes. The check right after a normal move (`exact(&fd, expected, 1)` in `mover-fs/src/relocate.rs`) is by inspection. |
| L2-FS-003 | Inspection | mover-fs/src/relocate.rs | The private area is under the source root, and the move refuses unless the file and both folders share the recorded device ("relocation requires one-link same-device intent"). No test puts the private area on another filesystem. |
| L2-FS-004 | Tested | mover-fs/tests/claim.rs::symlinks_aliases_special_files_and_writable_parents_are_rejected; mover-fs/tests/claim.rs::discard_removes_only_the_exact_retained_copy | Symbolic links (file or folder), hard-link aliases, FIFOs and writable parents are refused. A symlinked private area is never followed. There is no option to allow links. |
| L2-FS-005 | Tested | file-mover/tests/api.rs::malformed_json_scope_and_http_framing_never_claim | A source folder outside the configured root, the mover's private names (`.file-mover`, `.control`, `.staging`, `COMMITTED.json`) and `..` paths are refused (`source_outside_scope`, 400) without claiming. |

## REC — Recovery and scheduling (parents L1-SYS-001, L1-SYS-005)

| L2 | Disposition | Evidence | Notes |
|---|---|---|---|
| L2-REC-001 | Tested | file-mover/tests/api.rs::restart_discovers_claimed_delivery_and_keeps_original_destination; file-mover/tests/api.rs::operator_status_observes_partial_claims_outage_and_committed_restart; mover-fs/tests/transfer.rs::abrupt_exit_at_each_durable_copy_and_publication_boundary | After a restart, unfinished jobs are picked up from saved state, checked against the files on disk and completed. A job keeps its original destination even if the configuration changed. |
| L2-REC-002 | Deviation (needs approval) | mover-fs/tests/transfer.rs::abrupt_exit_at_each_durable_copy_and_publication_boundary; mover-fs/tests/transfer.rs::delivered_job_superseded_attempt_is_cleaned_automatically_and_nothing_else | An interrupted copy is re-queued as a new attempt (attempt 2). The stale partial is **kept** at that point, not removed. Superseded attempts are removed automatically only after the job is delivered; for a cancelled job, by operator-confirmed deletion. **Decision:** accept removing stale partials after delivery instead of at re-queue, or reword. |
| L2-REC-003 | Tested | mover-fs/tests/transfer.rs::receipt_failure_after_publication_reconciles_without_recopy; mover-fs/tests/transfer.rs::manifest_receipt_failure_after_publication_recovers_without_recopy; mover-fs/tests/transfer.rs::abrupt_exit_at_each_durable_copy_and_publication_boundary; mover-fs/tests/transfer.rs::cross_filesystem_copy_large_file_retains_source_and_preserves_names | Files already copied, verified or published are reconciled, not copied again (same attempt). A repeat of a finished transfer returns the same result. |
| L2-REC-004 | Partly tested | file-mover/tests/api.rs::parallel_delivery_commits_every_job_exactly_once; file-mover/tests/api.rs::pending_capacity_retry_survives_restart_and_recovers_without_operator_resume; file-mover/tests/api.rs::unsafe_startup_configuration_is_rejected | **Tested:** `delivery_concurrency` is limited to 1-8, `delivery_concurrency` workers start (4 for a setting of 4), and every job commits once on its first attempt. A job waiting to retry is picked up after its saved deadline, including after a restart (the forced capacity failure needs a qualification-build fault point). **Inspection:** that jobs are actually delivered at the same time, up to the limit. Each of the `delivery_concurrency` workers delivers one job at a time, and `ActiveJobs` keeps two workers off the same job (`file-mover/src/lib.rs`). No test observes overlap. |

## RTY — Retry and error classification (parents L1-SYS-005, L1-SYS-007, L1-SYS-008, L1-SYS-010)

Policy: [delivery retry policy](DELIVERY-RETRY-POLICY.md).

| L2 | Disposition | Evidence | Notes |
|---|---|---|---|
| L2-RTY-001 | Tested | file-mover/tests/api.rs::pending_capacity_retry_survives_restart_and_recovers_without_operator_resume; mover-store/src/tests.rs::capacity_backoff_keeps_mixed_failure_budget_binding_review_and_clock_bounds; file-mover/tests/api.rs::parallel_delivery_keeps_outage_deferral_and_foreign_marker_review | Failures are classified before scheduling. In qualification builds, the service test injects a real payload-write fault and checks it is recorded as a destination capacity failure (`destination_capacity_requires_review`). The store test covers the schedule for each class and binding refusal (immediate review). The outage test covers a destination unavailable before allocation (deferred, not counted). |
| L2-RTY-002 | Deviation (needs approval) | mover-store/src/tests.rs::capacity_backoff_keeps_mixed_failure_budget_binding_review_and_clock_bounds; file-mover/tests/api.rs::unavailable_destination_claims_then_foreign_marker_requires_review_without_allocation | A destination binding refusal or a foreign marker goes straight to review. Other failures that are not capacity or outages, including permanent ones such as a digest refusal, get up to three bounded reconciliation attempts (5 s apart) before review. That is not a permanent-error classification. The attempts grant no new permission to repeat an effect. **Decision:** accept the bounded-then-review policy, or reword. |
| L2-RTY-003 | Tested | mover-store/src/tests.rs::capacity_backoff_deadlines_review_and_audited_reset_survive_restart; mover-store/src/tests.rs::status_snapshot_preserves_deadlines_review_and_claims_across_restart | The failure count, next retry time and last failure cause are stored in SQLite and reported in job status. |
| L2-RTY-004 | Tested | mover-store/src/tests.rs::capacity_backoff_deadlines_review_and_audited_reset_survive_restart; file-mover/tests/api.rs::pending_capacity_retry_survives_restart_and_recovers_without_operator_resume | Retry state and deadlines survive a reopen of the store and a service restart. |
| L2-RTY-005 | Deviation (needs approval) | mover-store/src/tests.rs::capacity_backoff_keeps_mixed_failure_budget_binding_review_and_clock_bounds | The backoff is bounded but **not configurable**. The limit is three persisted failures, then review. Delays are 30 s and 60 s for capacity failures and 5 s for others (`mover-core/src/retry.rs`, per the approved policy). **Decision:** accept fixed values, or make them configurable. |
| L2-RTY-006 | Tested | mover-store/src/tests.rs::operator_resume_is_audited_idempotent_and_rejects_stale_review_epochs; file-mover/tests/tls_listener/admin.rs::admin_retry_delivers_a_reviewed_job_and_replays_its_receipt | A failed job in review can be retried by hand: through the host-local operator `resume` (audited) or the dashboard **Retry** (audited, without a confirmation step). The job's files are retained throughout. |

## LIF — Job lifecycle control (parents L1-SYS-003, L1-SYS-008)

| L2 | Disposition | Evidence | Notes |
|---|---|---|---|
| L2-LIF-001 | Deviation (needs approval) | file-mover/tests/tls_listener/admin.rs::admin_cancel_needs_a_matching_confirmation_and_stops_the_job; file-mover/tests/api.rs::cancelled_jobs_stop_claims_and_delivery_and_keep_their_files | Cancel is a confirmed, audited dashboard action. It keeps the claimed source copies. It does **not** discard the incomplete destination: files stay in place, and removing partial destination files is a separate confirmed action (**Delete partial destination files**, increment 160). **Decision:** accept separate deletion, or reword. |
| L2-LIF-002 | Deviation (needs approval) | file-mover/tests/api.rs::cancelled_jobs_stop_claims_and_delivery_and_keep_their_files; mover-store/src/tests.rs::admin_cancel_outcomes_settlement_and_stopped_work | There is no pause. Cancellation is cooperative, with no forced kill, but it stops **between steps**, not inside a copy at a buffer boundary. Delivery checks for cancellation before each step (`stop_if_cancelled` in `file-mover/src/delivery_worker.rs`). Settlement waits until no worker or claim is active on the job. Durable data is kept. **Decision:** accept step-boundary cancellation without pause, or reword. |
| L2-LIF-003 | Tested | file-mover/tests/api.rs::cancelled_jobs_stop_claims_and_delivery_and_keep_their_files; mover-store/src/tests.rs::admin_cancel_outcomes_settlement_and_stopped_work | A cancelled job settles to the terminal condition **Cancelled** (with `stopped_at`), keeps its files, and is never delivered or revived. The state is named `Cancelled`, not `CANCELLED_RETAINED`. |
| L2-LIF-004 | Not applicable (needs approval) |  | Proposed: job pause and resume are not part of the Rust first release and are not implemented. The nearest controls are stop/restart (service-wide) and cancel. If the user keeps it in scope, it becomes Open. |
| L2-LIF-005 | Deviation (needs approval) | mover-store/src/tests.rs::admin_cancel_outcomes_settlement_and_stopped_work; file-mover/tests/tls_listener/admin.rs::admin_cancel_needs_a_matching_confirmation_and_stops_the_job; mover-core/tests/protocol.rs::publication_and_commit_require_all_prior_evidence | Invalid core transitions get a typed error (`InvalidTransition`) with state unchanged. But by approved design, cancelling an **unknown or already-finished job is skipped**, not refused: the outcome is `Skipped`, counted in a successful bulk reply. **Decision:** keep the approved skip behavior and reword the requirement to match. |

## CORE — Job model and state machine (parents L1-SYS-021, L1-SYS-022, L1-OBS-003)

| L2 | Disposition | Evidence | Notes |
|---|---|---|---|
| L2-CORE-001 | Partly tested | mover-core/tests/protocol.rs::publication_and_commit_require_all_prior_evidence; mover-core/tests/protocol.rs::acceptance_and_partial_claims_never_release_paths | **In the core (tested):** the recording's handoff and per-file phases and their legal transitions live in `mover-core`. It has no dependencies and no file, network or clock access, and the tests drive the transitions directly. **Outside the core:** cancellation states and transitions (`mover-store/src/cancellations.rs`), retry and review state, and source cleanup are kept in the store. So the complete job state relation is not defined in the core. This is the same architectural split as the L2-CORE-002 decision. |
| L2-CORE-002 | Deviation (needs approval) | mover-core/tests/protocol.rs::replay_preserves_handoff_and_pinned_policy | The core `Recording` holds identity, the file list, per-file phases, measured sizes and the pinned delivery policy. Timestamps, retry counters and failure causes live in separate SQLite records, combined in job status. There are no byte-progress counters in the core; live progress is reported separately. **Decision:** accept the split model, or reword. |
| L2-CORE-003 | Tested | mover-core/tests/protocol.rs::publication_and_commit_require_all_prior_evidence; mover-core/tests/protocol.rs::repeated_claim_cannot_change_recorded_size; mover-core/tests/protocol.rs::expected_size_mismatch_does_not_confirm_claim; mover-core/tests/protocol.rs::empty_requests_and_unknown_files_do_not_advance | An invalid transition returns an error and leaves the phase, recorded size and authorization unchanged. |
| L2-CORE-004 | Inspection | mover-core/Cargo.toml | `mover-core` reads no clock: it has no dependencies and uses no `std::time`, `std::fs` or `std::net`. Times are supplied by callers (the store and service). No test isolates this. |

## BWL — Bandwidth limiting (parents L1-SYS-001, L1-SYS-008)

The Rust mover has no throughput limit. The copy buffer size
(`copy_buffer_bytes`) and parallelism settings change speed but do not cap it.

| L2 | Disposition | Evidence | Notes |
|---|---|---|---|
| L2-BWL-001 | Not applicable (needs approval) |  | Proposed: no configurable bytes-per-second limit exists in the Rust first release. If kept in scope, Open (a product change). |
| L2-BWL-002 | Not applicable (needs approval) |  | Proposed, with L2-BWL-001: no runtime throughput adjustment. |
| L2-BWL-003 | Not applicable (needs approval) |  | Proposed, with L2-BWL-001: no aggregate limit. |
| L2-BWL-004 | Not applicable (needs approval) |  | Proposed, with L2-BWL-001: no limit setting, so there is no zero-means-unlimited value. Copies are always unthrottled. |

## RSM — Partial-file byte-offset resume (parents L1-SYS-003, L1-SYS-005)

| L2 | Disposition | Evidence | Notes |
|---|---|---|---|
| L2-RSM-001 | Not applicable (needs approval) |  | Proposed: there is no byte-offset resume. An interrupted copy restarts as a new attempt from byte zero, and its partial is kept until delivery ([restart runbook](RUST-RESTART-RUNBOOK.md): "byte-offset resume is not promised"). If kept in scope, Open. |
| L2-RSM-002 | Not applicable (needs approval) |  | Proposed, with L2-RSM-001: no resume setting and no pause. Partials are always kept, and new attempts use new names, so they never collide (see L2-REC-002). |
| L2-RSM-003 | Not applicable (needs approval) | mover-fs/tests/transfer.rs::corrupted_staging_with_restored_metadata_fails_independent_hash | Proposed, with L2-RSM-001, since there are no resumed partials. Its safety clause holds anyway: unverified bytes are never published (L2-DPR-004). |

## REN — Rename engine (parent L1-SYS-013)

| L2 | Disposition | Evidence | Notes |
|---|---|---|---|
| L2-REN-001 | Not applicable (needs approval) |  | Proposed: files keep the producer's relative paths. There is no rename template; the recording folder name is the recording UUID (or the job number for legacy jobs). |
| L2-REN-002 | Not applicable (needs approval) | mover-fs/tests/transfer.rs::foreign_equal_content_final_is_never_overwritten | Proposed, with L2-REN-001: no configurable collision policy. The only policy is no-clobber: an existing name is never replaced (L2-DST-001 and 002). |
| L2-REN-003 | Inspection | mover-fs/src/relocate.rs | The mover's own same-filesystem moves (claiming into the private area, and publication) refuse unless the file and both folders are on the recorded device. This is the same check as L2-FS-003; no cross-device test. |

## XFR — Transfer strategies (parents L1-SYS-014, L1-SYS-015, L1-SYS-023)

| L2 | Disposition | Evidence | Notes |
|---|---|---|---|
| L2-XFR-001 | Partly tested | mover-fs/tests/transfer.rs::cross_filesystem_copy_large_file_retains_source_and_preserves_names; file-mover/src/progress.rs::files_of_one_job_add_up_and_finished_files_drop_out | **Interface:** `copy_effect_observed` and `verify_effect_observed` (`mover-fs/src/transfer.rs`) take the source (the recorded claim), the destination (the recorded transfer), a buffer size and a progress callback. `copy_effect` is the same call with a no-op callback, so the callback is optional. Delivery workers pass a callback that feeds live progress. **Tested:** the copy through this interface, and the progress aggregation. **By inspection:** the callback wiring in `file-mover/src/delivery_worker.rs`; no test drives a callback through a transfer. **Difference from the wording:** source and destination are passed as recorded identities (claim and transfer records), not plain paths. |
| L2-XFR-002 | Deviation (needs approval) | mover-fs/tests/transfer.rs::abrupt_exit_at_each_durable_copy_and_publication_boundary; mover-fs/tests/transfer.rs::foreign_equal_content_final_is_never_overwritten; mover-fs/src/relocate.rs::collision_at_the_link_transition_never_clobbers_or_removes_original | Temporary name, sync, then publication: see L2-DPR-001, 002 and 005. Publication is `RENAME_NOREPLACE`, with the no-clobber link fallback. Same decision as L2-DPR-005. |
| L2-XFR-004 | Deviation (needs approval) | mover-fs/src/payload_io.rs::payload_diagnostics_keep_operation_errno_and_safe_actions_without_error_text | A failure records the operation, the numeric errno and a safe action (at most 240 characters), deliberately **without** OS error text. The dashboard shows plain-language labels for known errno values. **Decision:** accept errno numbers plus labels instead of errno text, or reword. |

## MGR — Job manager and worker pool (parents L1-SYS-017, L1-SYS-018, L1-SYS-022)

| L2 | Disposition | Evidence | Notes |
|---|---|---|---|
| L2-MGR-001 | Deviation (needs approval) | file-mover/tests/api.rs::parallel_delivery_commits_every_job_exactly_once | A configured number of delivery worker threads (`delivery_concurrency`) take runnable jobs from the store. `ActiveJobs` keeps two workers off one job. There is no mutex and condition-variable queue. The behavior is covered by L2-REC-004 (partly tested). **Decision:** accept the mechanism, or reword. |
| L2-MGR-002 | Deviation (needs approval) | mover-core/tests/protocol.rs::publication_and_commit_require_all_prior_evidence | Recording transitions go through `mover-core`. Cancellation, retry and cleanup state change in the store. Same decision as L2-CORE-002. |
| L2-MGR-003 | Partly tested | file-mover/tests/api.rs::default_sixty_second_stop_returns_incomplete_while_delayed_drain_retains_ownership | **Tested:** every service test stops the service normally and checks a clean exit. The qualification-build test pauses shutdown with no job in flight. It shows the 60 s deadline, the `ShutdownIncomplete` report, ownership kept while the drain is held, and a clean exit with the instance freed once released. **Not tested here:** draining or failing an in-flight transfer and joining its workers. That is by inspection of the shutdown path (`file-mover/src/lib.rs`) and the historical blocked-worker evidence in the [restart runbook](RUST-RESTART-RUNBOOK.md) (increments 43, 45, 60 and 61). |

## STO — Storage abstraction (parents L1-SYS-001, L1-SYS-007, L1-SYS-009)

| L2 | Disposition | Evidence | Notes |
|---|---|---|---|
| L2-STO-001 | Deviation (needs approval) | mover-fs/src/transfer.rs | Storage work is done in `mover-fs` through direct POSIX calls (`rustix`), run by supervised worker children. There is no capability-interface layer between the workflow and POSIX. **Decision:** accept the direct POSIX design, or reword. |
| L2-STO-002 | Partly tested | mover-fs/tests/transfer.rs::cross_filesystem_copy_large_file_retains_source_and_preserves_names | Local POSIX source and destination are tested. NFS runs only in NFS-qualification builds and labs, and **production NFS is disabled** ([deployment matrix](SUPPORTED-DEPLOYMENT.md)). |
| L2-STO-003 | Deviation (needs approval) | mover-fs/src/transfer.rs | There is no storage interface for a future object-storage adapter; one would change the workflow. **Decision:** accept, or keep as future product work. |
| L2-STO-004 | Deviation (needs approval) | mover-fs/tests/claim.rs::identity_changes_and_recovery_with_reappeared_original_block | The recorded identity (`ObjectIdentity`: device, inode, owner, size, mtime, links) is POSIX-only. It has no object-storage form. Same decision as L2-STO-003. |
| L2-STO-005 | Inspection | ../Cargo.lock | No optional storage adapters exist. All dependencies are locked and built offline in the SLES gate, which also audits the ELF files ([SLES gate](RUST-SLES-GATE.md)); new dependencies need approval (AGENTS.md). |

## ENV — Environment capability diagnostics (parents L1-SYS-008, L1-ROB-001)

| L2 | Disposition | Evidence | Notes |
|---|---|---|---|
| L2-ENV-001 | Deviation (needs approval) | mover-store/src/tests.rs::qualified_sqlite_options_and_durable_settings; file-mover/tests/api.rs::unsafe_startup_configuration_is_rejected | There is no separate capability diagnostic. The Rust service checks what it needs at startup and refuses if it is missing: SQLite build options and WAL settings, local state filesystem types and permissions, locks, and configuration. The Python items (interpreter version, hash library) do not apply. **Decision:** accept startup refusal in place of a diagnostic report, or reword. |
| L2-ENV-002 | Not applicable (needs approval) |  | Proposed: there are no optional capabilities to report. No kernel-assisted copy is used, and no-follow opening is mandatory, not optional. |
| L2-ENV-003 | Not applicable (needs approval) |  | Proposed, with L2-ENV-001: there is no capability probe. Startup checks return typed refusals rather than crashing. |

## DASH — Operator dashboard (parent L1-OBS-001)

| L2 | Disposition | Evidence | Notes |
|---|---|---|---|
| L2-DASH-001 | Deviation (needs approval) | file-mover/tests/tls_listener/admin.rs::admin_https_login_session_logout_and_boundary_precedence | The dashboard is one embedded HTML, CSS and JavaScript page on a separate signed-in HTTPS listener. It reads `/api/v2/admin/…` routes and receives live updates by server-sent events, not by polling `GET /api/status`. **Decision:** accept, or reword. |
| L2-DASH-002 | Tested | file-mover/src/admin.rs::document_inlines_assets_and_csp_admits_only_them; file-mover/tests/tls_listener/admin.rs::admin_https_login_session_logout_and_boundary_precedence | **Unit test:** the served document inlines the page's style and script, contains no `http://`, `https://`, `src="` or external `href`, and its CSP admits exactly those two inline assets by hash, with nothing `unsafe`. **Service test:** the live page's CSP starts with `default-src 'none'` and contains nothing `unsafe`. **Inspection:** the full CSP has no external sources (`admin.rs`). |
| L2-DASH-003 | Partly tested | scripts/admin-ui/no-html-sinks.test.js; file-mover/src/admin.rs::document_inlines_assets_and_csp_admits_only_them | **Automated (regression checks on spelling):** the CI check fails on common HTML-parsing sinks and dynamic-code calls in `admin.js`, including whitespace variants (`innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval (`, `new Function`, string `setTimeout`/`setInterval`, `setAttribute("on…")`, and others), and on inline handlers in the page. The Rust unit test also refuses `innerHTML` and `insertAdjacentHTML`. These checks are lexical, so aliased or computed access could evade them. **Inspection:** every dynamic value is inserted with `textContent` or text nodes. |

## JSON — Request and response codec (parents L1-SYS-009, L1-ROB-001, L1-ROB-002)

| L2 | Disposition | Evidence | Notes |
|---|---|---|---|
| L2-JSON-001 | Deviation (needs approval) | mover-fs/src/recording_codec/tests.rs::strict_raw_json_and_original_map_rules_before_policy | The producer codec tokenizes with `serde_json`, an approved pinned dependency. It adds project rules on top: duplicate keys rejected at any depth, BOM refused, no trailing data, exact field shapes. The dashboard has its own lossless parser. **Decision:** accept the approved library with project strictness, or reword. |
| L2-JSON-002 | Tested | mover-fs/src/recording_codec/tests.rs::strict_raw_json_and_original_map_rules_before_policy; file-mover/tests/api.rs::malformed_json_scope_and_http_framing_never_claim | Malformed input returns a typed error (`invalid_json` / `invalid_submission`, HTTP 400) and the service keeps running. |
| L2-JSON-003 | Partly tested | mover-fs/src/recording_codec/tests.rs::strict_raw_json_and_original_map_rules_before_policy; mover-fs/src/recording_codec/tests.rs::malformed_manifest_fields_and_duplicate_keys_are_refused | **Tested:** trailing bytes, duplicate members (including escape-equivalent keys), BOM, lone surrogates, invalid UTF-8, NaN, unknown fields and non-string sizes are refused. **Not at the parser:** JSON numbers with fractions are not rejected by the parser itself, but by the schema (every number field is a string or an integer). An embedded NUL in a string is refused by the field rules (control characters), not the parser. |
| L2-JSON-004 | Tested | mover-fs/src/recording_codec/tests.rs::strict_raw_json_and_original_map_rules_before_policy; mover-fs/src/recording_codec/tests.rs::byte_limits_and_maximum_integer_manifest_are_bounded; file-mover/tests/api.rs::malformed_json_scope_and_http_framing_never_claim | The total size is checked before parsing (64 KiB request, 413; 128 KiB manifest). 2,000-deep nesting is refused (the parser's recursion limit). String length and member count are bounded by the total size. |
| L2-JSON-005 | Open |  | No third-party conformance corpus and no fuzzing. Fixtures and contract vectors are tested, but that is not this requirement. |
