# Rust increment 28: enrollment I/O failures and blocked receipt shutdown

Increment on `feature/rust-transfer-coordinator`, 2026-10-15. Extends
[increment 27](RUST-INCREMENT-27.md) without changing the REST contract,
configuration/binding versions, receipt format or schema 10. No dependency,
deployed executable, repair command or takeover behavior is added. Linux still
handles the mounted NFS filesystem; these are application failure decisions.
Production NFS and source deletion remain disabled.

## Write and synchronization behavior

The production path continues to use standard `write_all`, file `fsync`, then
directory `fsync`, before durable SQLite activation. Narrow enrollment controls
are compiled into the retained qualification feature only. The controls write to
real fixture files but inject selected return values; they are not proof of actual
server disk exhaustion, hardware I/O errors or power-loss durability.

`FILE_MOVER_QUALIFICATION_ENROLLMENT_FAULT` supports these fixture cases:

| Value | Qualification behavior and required outcome |
|---|---|
| `short_write` | Limit each write to seven bytes; standard write-all handling completes the exact receipt and activation. |
| `interrupted_write` | Return Interrupted once, then allow normal writes; initialization completes. |
| `write_zero` | Write a seven-byte prefix, then return zero; initialization fails and preserves the partial receipt and prepared state. |
| `write_enospc` | Write a prefix, then report ENOSPC; no activation, preserved receipt/state for review. |
| `write_eio` | Write a prefix, then report EIO; no activation, preserved receipt/state for review. |
| `file_sync` | Report EIO before receipt file sync; preserve the complete but unactivated receipt. |
| `directory_sync` | Complete file sync, then report EIO before namespace sync; preserve the receipt and do not activate. |

The production executable ignores every value. Tests check exact success bytes,
partial prefixes, prepared/active state, zero accepted jobs and unchanged producer
input. Ordinary startup refuses pending initialization; explicit retry must not
overwrite/adopt a created receipt. The existing no-receipt retry and active-pair
restart behavior remains intact.

The new `enrollment_directory_sync` qualification pause lies between successful
file synchronization and the parent directory synchronization. Killing the real
child there must leave local enrollment pending and the receipt preserved for
review. This fills the process-death gap between the two existing sync calls;
it does not simulate a power failure or an in-flight sync RPC.

## Diagnostics and supervision

Enrollment children return a strict bounded private reply containing either
authorization or a sanitized diagnostic. The parent rejects inconsistent replies;
a diagnostic cannot authorize activation. The same executable launches its own
internal worker, so this private reply change needs no public configuration or
database migration. Known failures identify `create_receipt`, `verify_receipt` or
custody validation, with the write/file-sync/directory-sync operation and errno
when available. Unknown worker termination reports enrollment uncertainty rather
than a generic payload failure. Messages instruct operators to preserve original
state/source for review and do not echo receipt contents or arbitrary error paths.

Active receipt checks gain the existing qualification-only read rendezvous/cache
advice. The normal service must remain unready while its supervised enrollment
child reads the receipt. The NFS fixture pauses that actual child after opening
and validating the receipt metadata, evicts its clean file cache as advice, stops
the controlled server and releases the child into the read. Kernel-blocked state
and absence of the local read-completed marker are required evidence that the
read, rather than a later metadata check, is incomplete.

The fixture requests SIGTERM and observes whether child/service exit occurs
before server restoration within the selected five-second window. No replacement
worker or premature HTTP readiness is permitted. If exit remains pending, restore
NFS before cleanup and record the shutdown limitation; do not claim a signal
cancelled the operation. After restoration require confirmed exit, unchanged
receipt/database/producer input, released cooperative custody and matching restart
with the original database. A read cancellation observation is not a storage
fence or a general hard-mount cancellation guarantee.

## Validation

Production gate `20261015T210811Z-015a69bd` PASSED 152 tests per debug/release
profile. Qualification gate `20261015T210822Z-d4eacbc6-nfs-qualification` PASSED
153 per profile. Both passed formatting/Clippy, 20 executable audits across the
two profiles, six negative ELF controls and exact target execution in pinned
SLES userspace. The highest required GLIBC remains 2.18 and the external graph
remains 42 packages. See [production evidence](RUST-SLES-EVIDENCE.json) and
[qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json).

Full NFS run `nfs-20261015T211759Z-87d109b2` PASSED with exit status 0 and
`cleanup_errors: []`. Its six directional delivery baselines, 24 ownership/
enrollment cases and 22 runtime cases all passed. Enrollment now covers seven
process-death boundaries per profile, including the interval after file sync and
before directory sync. All four three-minute runtime outages retained one blocked
worker with responsive health/status and recovered after restoration. Inherited
OS lock, interrupted metadata, isolated startup shutdown and production refusal
controls also passed. See [full NFS evidence](RUST-NFS-ENROLLMENT-IO-EVIDENCE.json).

In both debug and release, the actual enrollment reader reached kernel state D
(`folio_wait_bit_common`) while the read-completed marker remained absent. After
SIGTERM, both service and child exited before restoration within the five-second
observation window. No readiness was served. The receipt, local database and
producer input remained unchanged; after restoration, the peer could acquire the
cooperative lock and the original database restarted successfully. This selected
read-interruption result does not generalize to every hard-mount operation.

Verified all five retained ownership driver hashes, each gate source archive hash,
and complete source inventories/content against the current Rust tree. The
fixture removed its containers, network and data volume; only the default Podman
network and the existing toolchain/registry cache volumes remain. Images and NFS
modules are retained. Validation used the Windows checkout and healthy root
Podman WSL2 engine; builds ran natively in container `/work`, not `/mnt/c`.

Every Rust build/test uses the mandatory GNU/glibc 2.22 zigbuild gate, ELF audit
and exact debug/release artifact execution in pinned SLES 12 SP5 userspace.
The full fixture must retain all directional delivery, original ownership,
enrollment crash, runtime interruption/three-minute outage and startup/lock cases.
The hard NFSv4.1 clients use `local_lock=none` and share kernel
`6.18.33.2-microsoft-standard-WSL2`; this does not qualify the old SLES kernel,
independent-host fencing, lost-lock/reclaim, server reboot or power-loss durability.

Maintain SC-065/068/069 and DOC-03–05 in [the scenario catalog](RUST-SCENARIOS.md).
Keep the permanent qualification feature and owned fixture capability. Registration,
offline repair, populated-state rebind and automatic takeover remain deferred.
Payload integrity remains the agreed 3N path; enrollment adds metadata operations.
