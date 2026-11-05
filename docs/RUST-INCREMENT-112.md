# Increment 112: guarded inspection and verified offline backup

2026-11-05. The user authorizes the next bounded slice after increment 111:
offline inspection and verified backup. Migration apply, UUID producer admission,
manifest-v2 runtime, deployment and release approval remain disabled/separate.
No operational database, custody or payload is changed during development.

## Implemented behavior

`file-mover --check-state CONFIG.json` inspects an existing supported schema 11
or legacy-only schema 12. `file-mover --backup-state CONFIG.json NEW_DIRECTORY`
creates an explicit operator snapshot. Both exclude active daemons and surviving
worker epochs before SQLite, register their own lifetime, and retain InstanceGuard
until every SQLite/artifact handle closes. Neither starts bootstrap, enrollment,
HTTP or payload workers. Normal Store entry points still refuse schema 11 with
MigrationRequired; there is no migration apply command.

Inspection opens SQLite READ_ONLY/FULL_MUTEX/NOFOLLOW without CREATE or URI mode.
It checks application/version, canonical known DDL (including unknown sqliteX
objects), pinned SQLite options, WAL source mode, integrity, FKs, reconstructable
jobs and sequence/instance consistency. It checks stored source pairing and exact
v1 manifest bytes/hash/identity against stored transfer evidence, without probing
source/destination. Pending/missing enrollment evidence is reported, never repaired
or activated. A passing inspection is not proof that physical files exist or that
the service is ready to run. Read-only means job data: normal guard/epoch and SQLite
shared-memory coordination may be written.

Backup requires an absent directory under an existing private local parent. It
refuses lexical overlap with the live state directory, configured roots and every
stored job/transfer/enrollment root before output path access. Mount inventory is
checked before traversal; symlinks/nonprivate parents and unsupported storage refuse.
The directory/file are created exclusively (0700/0600). Name/descriptor identities,
ownership, modes, links and locality are checked before/after SQLite. Same-UID/root
hostile concurrent mutation and aliasing through separately configured bind mounts
are outside the existing protected fixed-path profile.

`VACUUM main INTO ?1` includes committed WAL contents with synchronous=FULL. The
snapshot is validated read-only, then all typed logical rows in declared-key order
are compared, including shared metadata, receipts and sqlite_sequence. Physical
ROWIDs are not compared. No schema conversion/checkpoint/repair is requested on
the source. Snapshot journal mode may differ from the original WAL-only state.
File hash/sync precedes a private `VERIFIED.json` receipt with schema/application,
instance, job count, pairing status, tool version, actual executable SHA-256 and
snapshot SHA-256. Receipt publication and directory/parent sync must all succeed.

Any error is a failed command: preserve the output, retry with a new directory.
Interruption before publication leaves no completion receipt; a failure after
receipt rename may leave its name without confirmed durable publication. Never
infer command success from filename presence. A receipt alone never authorizes
migration/restore: future apply must revalidate source/snapshot under continuous
exclusion. Backups are external historical recovery artifacts, never a live
ownership inventory and never discovered/restored automatically. Group-50 clear
still forgets live linkage; operators protect/retire separate backups themselves.

## Validation and remaining gates

New disposable tests cover real schema-11/schema-12 committed-WAL snapshots,
typed row/sequence comparison, altered snapshots, no overwrite/initialization,
unsupported/foreign/changed/UUID state, private output/path replacement, daemon
and surviving-child exclusion, recorded process lifetime, unavailable payload
roots, original state/inode/manifest/replay preservation, failure boundaries and
qualification-only kill after copying. Failure hooks are compiled out production;
EIO/ENOSPC hooks simulate boundary errors, not actual exhausted media/power loss.

Required production and qualification cargo-libc/SLES gates: NOT_RUN at this
implementation checkpoint. Independent review: pending. Actual-version systemd,
hard NFS, physical storage failures, migration apply/rollback, deployment and all
eight release gates remain unqualified. This file will record final actual results.

Operator procedure: [offline state backup](OFFLINE-STATE-BACKUP.md).
