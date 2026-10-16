# Rust increment 32: allocation, namespace and manifest diagnostics

Increment on `feature/rust-transfer-coordinator`, 2026-10-15. Extends
[increment 31](RUST-INCREMENT-31.md) to surrounding filesystem operations.
Retry timing, three-failure review, audited resume, ownership checks and effect
order remain unchanged. No dependencies, public API, schema 10, binding version 3
or persisted receipt changes. Production NFS and deletion remain disabled.

## What operators can see

Fixed internal operation labels identify staging allocation/directory creation and
sync, completion-manifest allocation/open/read/truncate/seek/write/permissions and
sync, and relocation original/final opens, original/final file sync and old/new
parent sync. Existing no-clobber rename, exclusive link and old-name unlink labels
remain. Numeric errno is preserved; arbitrary OS/custom error text, paths and
payload bytes are not printed. Diagnostics use the existing bounded private
worker path and are separate from receipts and authorization.

| Labels | Existing operation |
|---|---|
| `staging_directory_create`, `staging_parent_create`, `staging_directory_sync` | Recording/staging/nested destination namespace creation and sync |
| `staging_allocate`, `staging_allocation_sync`, `staging_allocation_directory_sync` | Exclusive attempt file creation, file sync and staging-parent sync |
| `manifest_allocate`, `manifest_allocation_sync`, `manifest_open` | Exclusive manifest allocation, its sync and manifest-related descriptor opens (including published-payload custody checks) |
| `manifest_read`, `manifest_truncate`, `manifest_seek`, `manifest_write` | Bounded manifest reread and owned manifest rewrite |
| `manifest_writable`, `manifest_readonly` | Owned manifest permissions before/after rewrite |
| `manifest_file_sync`, `manifest_staging_sync`, `manifest_directory_sync` | Manifest file, staging parent and final recording parent sync |
| `relocate.open_original`, `relocate.open_final` | Old/new regular-file opens |
| `relocate.original_file_sync`, `relocate.final_file_sync`, `relocate.new_parent_sync`, `relocate.old_parent_sync` | Relocation file and parent syncs, including reconciliation |
| `relocate.rename_noreplace`, `relocate.link_exclusive`, `relocate.unlink_original` | Existing no-clobber rename/link/unlink labels, now with fixed safe actions |

Examples:

```text
manifest_write errno=28; storage full; restore approved capacity; preserve source/state; resume only if review required
relocate.rename_noreplace errno=5; storage I/O error; inspect storage; preserve source/state; existing review rules apply
```

For ENOSPC restore approved capacity; for EIO inspect the storage. Preserve original
state, source, partials and final objects. Follow existing review/resume rules.
A failed operation does not prove the effect did not occur. Do not manually remove
an allocation, final name or enrollment receipt to bypass review.

Allocation can fail after creating directories or an exclusive file but before
its receipt is saved. Subsequent exclusive creation can then refuse with EEXIST;
this increment does not add repair or promise that resume fixes such a refusal.
A manifest parent-sync error can occur after COMMITTED.json was published:
coordinator commitment can still be pending/review-required despite valid bytes
at the final name. Consumers continue to use the existing manifest contract;
logs never grant deletion or durable completion. Recovery still validates the
exact owned object/content before advancing.

The same native calls execute in the same order; no retries, extra payload passes,
overwriting fallbacks or new recovery decisions are introduced. Normal integrity
remains 3N. Logical identity/digest refusals and some root/traversal/metadata
errors retain existing diagnostics. This is not a universal error taxonomy.

## Qualification and tests

Retained qualification-only `FILE_MOVER_QUALIFICATION_EFFECT_FAULT` selects a fixed
wrapped staging/manifest operation label and returns EIO before that native call.
It does not select `staging_parent_create` or relocation calls. Shared labels fail
at the first reached occurrence: the `manifest_staging_sync` API case exercises
allocation sync, not every later staging sync.
Production never reads this variable. Existing payload fault controls are unchanged.
Relocation wrapping preserves typed errno/fallback matching and has no new env
fault control. These are simulated errors, not real server EIO or in-flight RPCs.

The API matrix selects 14 boundaries: staging allocation and its file/directory
syncs; manifest allocation, allocation sync, staging sync, truncate, seek, write,
writable/readonly permissions, file sync, read and final directory sync. Tests
require 202 and source/path-reuse preservation, exactly three failures, safe
operation/errno logs and review surviving fault-free restart. Nine recoverable
cases commit only after audited resume/replay. Five allocation cases retain review
and original source/path-reuse evidence without attempted repair. Production ignores all selectors and
commits normally. The final directory-sync case retains a readable final manifest
while service state remains uncommitted.

A relocation test performs the rename then reports EIO: the error retains its
operation/errno, the original name is gone, final bytes remain and exact owned
recovery succeeds. Existing link-collision, two-name interruption, foreign-alias
and unsupported-rename tests remain. Sanitization covers errno 5/28/13/17,
arbitrary custom error strings and safe Debug output.

## Validation

Production gate `20261016T030357Z-fc759659` PASSED 157 tests per debug/release
profile. Qualification gate `20261016T030357Z-9dd76f22-nfs-qualification` PASSED
158 per profile. Both passed formatting/Clippy, 20 executable ELF audits per mode,
six negative controls and exact pinned SLES target execution. All 65 API tests
passed in each mode/profile. Both archived 54-file source inventories/content and
source/artifact hashes match the current tree/results. The dependency graph stays
at 42 external packages; maximum required GLIBC stays 2.18. See
[production evidence](RUST-SLES-EVIDENCE.json) and
[qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json).

Full NFS regression `nfs-20261016T032042Z-ded65186` PASSED with exit status 0
and `cleanup_errors: []`: six directional delivery baselines, 24 ownership/enrollment
cases, 22 runtime interruption cases, four enrollment storage cases and four
destination-full delivery cases. All four three-minute claim/verification outages
retained one blocked worker with responsive health/status and recovered. Inherited
OS locks, interrupted metadata, isolated bootstrap shutdown and production NFS
refusals passed. See [full NFS evidence](RUST-NFS-NAMESPACE-DIAGNOSTICS-EVIDENCE.json).

The actual destination-full cases retained exactly three safe copy-write ENOSPC
logs, original source, reused producer paths and old partials. Review survived
capacity restoration/restart; audited resume/replay committed the original job.
Maximum sampled combined health/status time was 3.89 seconds including host engine
and transport overhead, below the selected 15-second fixture window; this is not a
production SLO. These native ENOSPC checks do not establish real manifest/storage
EIO behavior; the new local error boundaries remain synthetic.

Verified driver hashes, both source archives and executable hashes. Cleanup left
no containers and only the default Podman network plus existing Rust toolchain and
registry cache volumes. Images/NFS modules were retained. Validation used the
Windows checkout, healthy root Podman WSL2 engine and native container `/work`
builds. Hard NFSv4.1 clients with `local_lock=none` shared kernel
`6.18.33.2-microsoft-standard-WSL2`. Container userspace qualification does not prove
old-kernel/hardware, power-loss, lost-lock/reclaim or independent-host fencing.
`protection_complete` and `production_authorized` remain false. Production
NFS/deletion stay disabled. No gate or fixture run failed in this increment.

Rerun after both mandatory gates pass:

```text
python scripts/check-nfs-boundaries.py rust/validation/<production-run> --qualification-gate rust/validation/<qualification-run> --isolated-startup --ownership --runtime --enrollment-storage --delivery-storage
```

Maintain SC-073 and DOC-02–05 in [the scenario catalog](RUST-SCENARIOS.md).
Retry classification/backoff, storage/quota margins and admission policy are
separate future work.
