# Rust protected local claim increment

`mover-fs` adds the first real source claim, without payload copying or hashing.
The synchronous coordinator loads accepted work, prepares a private directory,
commits the exact claim intent through `mover-store`, performs a descriptor-relative
`RENAME_NOREPLACE`, synchronizes the claimed file and affected directories, then
commits the receipt. No SQLite transaction spans filesystem I/O. Calls must run
outside an async executor, with one fenced worker per operation.

## Handoff and recovery

Actual logical size comes from the opened regular file. An optional expected
size must match before moving the source. Nested source folders remain in place;
only the explicitly submitted file entry moves. Private custody is
`source-root/.file-mover/<job-id>-<file-index>/data`; the submitted relative name
remains in SQLite for later destination layout. Destination transfer is not added.

Schema 2 persists each intent's root path, source/private names, root/parent/private
directory observations, source identity/size/mtime/link count and receipt status.
A tested transactional migration preserves schema-1 accepted jobs and reservations.
Changed intents, malformed observations and inconsistent ledgers fail closed.
Foreign/future schemas are retained and rejected.

Every partial claim keeps all job reservations and Pending handoff. Committing
the last receipt and releasing reservations share one transaction. Only then
does the recording return Ready202. Same-ID replay restores that fact without
opening the generator's reused source path. A failed receipt transaction withholds
Ready202 even if the filesystem effect has already succeeded.

An unfinished intent is reconciled against the recorded protected namespace and
object identities. If the private file is present and matches, required fsyncs
are repeated before recording completion. Otherwise the still-matching source
can be renamed. A remaining/reappeared producer entry, foreign private file,
changed directory/file identity or uncertain error blocks completion and retains
data. There is no rollback onto producer names or automatic deletion of leftovers.

## Supported setup and limits

This is a local test increment, not a deployable NFS service. An administrator
must provision a service-owned 0700 `.file-mover` directory under an approved
source root. The root and traversed source parents must be service-owned without
group/other write permission. Handed-off files must be service-owned, regular,
closed/immutable, without other hard links or group/other write permission.
The producer must leave files and parent entries untouched until Ready202.
Privileged/same-UID interference is outside this custody contract.

All path components are opened without following symlinks; cross-device traversal
is rejected. This slice admits only local ext, tmpfs and container overlay types.
It does not establish production mount/export identities or defend against
privileged remounts/inode reuse after lost custody. NFS and other filesystems are
blocked. NOREPLACE failure is retained for reconciliation; no overwrite,
cross-filesystem copy/delete or link fallback is attempted.

Private per-file directory allocation is exclusive and synchronized before the
claim intent commits. A crash/database failure in that allocation gap can leave
an empty orphan; subsequent allocation blocks rather than adopting it. Production
namespace allocation needs its own persisted creation intent, instance ownership
and explicit orphan reconciliation. Empty directories are never recursively
cleaned by this worker. No actual HTTP 202, worker process supervision, source
cleanup, missing-file retry scheduler or destination publication exists yet.

## Verification

The mandatory gate builds with cargo-zigbuild for GNU/glibc 2.22 and executes the
exact debug/release test binaries in pinned SLES 12 SP5 userspace as UID 1000,
without capabilities or network and with eager binding. It also audits every
artifact, checks hashes, formatting/Clippy and six negative ELF controls.
See [RUST-SLES-EVIDENCE.json](RUST-SLES-EVIDENCE.json) for the passing run.
There are **38 passing tests per profile** (10 core, 19 store, 9 filesystem),
plus ignored child helpers explicitly invoked by parent tests. All ten emitted
test executables import at most GLIBC_2.18 and use the standard loader; no shared
SQLite or additional shared library requirement is introduced by rustix.

Tests cover actual/omitted/zero/mismatched sizes, nested-folder preservation,
partial claims/reservations, same-ID restart replay and producer reuse, missing
files, symlink components/leaves, hard links, FIFOs, writable parents, foreign
equal-content collisions, allocation orphans, replaced private directories,
changed source identity and premature producer reuse. Real read-only SQLite
failure after the effect and an aborted last-receipt reservation release both
withhold handoff. Schema migration and damaged claim observations are tested.

Subprocesses exit without destructors after intent commit, immediately after
rename before directory synchronization, after the synchronized effect and
after receipt commit. Reopen either completes reconciliation or returns the
already committed claim, preserving a reused producer file. This is process-exit
evidence, not server/storage power-loss qualification or an old-kernel test.

Dependencies reuse the exact E2 cumulative versions/checksums: rustix 1.1.5,
defaults off with std/fs/process and the default Linux raw-syscall backend,
linux-raw-sys 0.12.1, plus E1's SQLite configuration. No new experiment starts.
The gate checks the qualified rusqlite/rustix/linux-raw-sys feature sets as well
as dependency versions. No musl, openat2, newer libc renameat2 wrapper,
linux_latest/use-libc feature or additional application package is introduced.

## Requirement evidence boundary

These are Rust evidence links, not promotion of historical C++ release status or
proof of a finished REST service. Detailed Rust L2/L3 derivations and automated
Rust trace discovery remain roadmap work; the current C++ matrix is unchanged.

| Requirement intent | Current evidence | Remaining qualification |
|---|---|---|
| L1-API-008; L2-SUB-002: all-file claim before handoff | `actual_sizes_nested_paths_partial_handoff_and_path_reuse`, `missing_second_file_retains_first_claim_and_all_reservations`, `failed_last_receipt_rolls_back_claim_fact_and_reservation_release` | HTTP response, resource admission, remote endpoint |
| L1-API-009; L2-SUB-001: same-key replay without re-claiming | `actual_sizes_nested_paths_partial_handoff_and_path_reuse`, `abrupt_process_exit_reconciles_intent_effect_and_receipt_boundaries` | API normalization/caller binding and retry timing |
| L1-SYS-028: discovered actual size and optional assertion | `actual_sizes_nested_paths_partial_handoff_and_path_reuse`, `expected_size_mismatch_does_not_move_or_allocate` | Production source/endpoint contract |
| L1-SYS-029; L2-FS-004: explicit nested files without symlink following | `actual_sizes_nested_paths_partial_handoff_and_path_reuse`, `symlinks_aliases_special_files_and_writable_parents_are_rejected` | Mount aliases/remount authorization and destination hierarchy |
| L2-FS-001/002: durable before/after source identity | `identity_changes_and_recovery_with_reappeared_original_block`, `replacement_private_directory_blocks_effect_and_preserves_source` | Instance ownership, lost-custody/remount recovery and NFS |
