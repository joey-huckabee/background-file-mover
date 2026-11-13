# Offline state migration (schema 11, 12 or 13 to schema 14)

**Update, [increment139](RUST-INCREMENT-139.md):** the current schema is 14. The
same `--migrate-state` command converts 13 -> 14 (it adds the empty per-job
problem table in one transaction; existing rows are untouched) and chains
11 -> 12 -> 13 -> 14. Preview reports `target_schema: 14` and
`conversion_required: true` for schemas 11, 12 and 13; it is a no-op for 14.
Checkpoint names for the new step are `problems_*`.

**Update, [increment137](RUST-INCREMENT-137.md):** the current schema is 13. The same
`--migrate-state` command now converts schema 12 to 13 (it adds the empty admin
retry receipt tables in one transaction; existing rows are untouched) and chains
11 -> 12 -> 13 for legacy state. Preview reports `target_schema: 13` and
`conversion_required: true` for schemas 11 and 12; it is a no-op for 13. Each run
needs a new backup directory, including a rerun after an interrupted migration.
The procedure below is otherwise unchanged.

Current runtime checkpoint: [increment 118](RUST-INCREMENT-118.md) records UUID/v2
integration and exact gate status. Validated mixed schema-12 state can be inspected
and backed up; schema-11 conversion still preserves only original legacy state.
Finish partial legacy handoff with a compatible predecessor before starting the
new runtime. Older legacy-only/activation-disabled statements below describe the
original increment's qualification, not authority to deploy or convert live state.


This command converts validated legacy state without opening payload roots. It
preserves job IDs, file indices, claims, transfer attempts, audits, enrollment,
manifest-v1 bytes and the job-ID high-water mark. This command never assigns
UUIDs or rewrites v1 data; current runtime support is described in increment 118.
No automatic migration or reverse conversion is provided.
See [increment 115](RUST-INCREMENT-115.md) for actual qualification and limits.

1. Schedule downtime. Stop your installed mover service:
   `sudo systemctl stop YOUR-MOVER-UNIT.service`. Use the original mover account,
   host, configuration, PID namespace and local state directory. Keep original
   state, source custody and destination files together.
2. If a daemon or surviving worker prevents maintenance, follow the
   [restart guide](RUST-OPERATOR-GUIDE.md). Restore unavailable storage and wait
   for the old processes to exit. Never remove instance.lock or workers.json,
   replace state, adopt workers or bypass exclusion. A free flock alone is not
   sufficient. The command retains lifetime exclusion through SQLite closure.
3. Provision a private local backup parent, owned by the mover account, mode
   0700, outside all current/stored source, destination and live state trees.
   Reserve space for a full snapshot plus replacement table and WAL growth.
   Capacity estimates do not guarantee successful writes. Do not use NFS,
   symlinks or bind-mount aliases of protected scopes.
4. Preview with a new absolute output directory:

   ```sh
   file-mover --migrate-state /etc/file-mover/config.json --backup-dir /var/lib/file-mover-backups/upgrade-20261107
   ```

   No backup directory or job-data changes are made. Local guard/lifetime
   metadata may be written. Schemas 11 and 12 report conversion_required:true;
   current schema 14 reports false (schema 13 reports true since increment139). Preview does not prove free capacity,
   output-parent permissions or successful writes; apply checks these again.
5. Apply explicitly, using that same unused directory:

   ```sh
   file-mover --migrate-state /etc/file-mover/config.json --backup-dir /var/lib/file-mover-backups/upgrade-20261107 --confirm
   ```

   Under continuous exclusion, the command creates a WAL-aware snapshot,
   compares every typed row and sequence, publishes/syncs VERIFIED.json, then
   converts in one SQLite transaction. It compares all original columns and
   dependent/shared rows against the snapshot before commit. Only exit status
   zero with converted:true establishes reported conversion success. The backup
   receipt describes the backup step; migration_apply_enabled:false in that
   receipt means the backup operation itself performed no conversion.
6. On any failure, preserve original state, all sidecars, backup and diagnostics.
   Run `file-mover --check-state /etc/file-mover/config.json` after old processes
   exit. Errors or loss of the response may occur after commit: never infer
   rollback merely from a failed command. Valid 11 remains eligible for retry
   with a DIFFERENT new backup directory; valid legacy-only 12 is a validated
   no-op, even if the requested backup directory already exists. A no-op creates
   no backup. Unknown/corrupt state requires investigation, not manual editing.
7. Restart with the schema-12-capable production binary and original config/state:
   `sudo systemctl start YOUR-MOVER-UNIT.service`. Inspect readiness and jobs as
   described in the operator guide. Existing work keeps its original legacy
   identity, paths and v1 manifests; no enrollment or replay identity is reset.
   An unfinished enrollment/review remains unfinished; migration does not repair it.

Only known schema 11 and supported legacy-only 12 are accepted. Missing, empty,
foreign, modified, corrupt, older/newer databases and UUID-bearing state refuse.
Normal startup still refuses schema 11 with MigrationRequired. Unsupported state
is not initialized or repaired. Source/destination availability is unnecessary
for the database-only command; restart still enforces normal storage admission.

Never restore the backup over live/progressed custody or downgrade schema 12.
The backup is sensitive historical recovery evidence, not current authority and
not an authorization for a later apply. Protect and retire it separately. History
clear forgets live file linkage; it does not erase separately held backups or old
physical pages. The command does not qualify deployment, NFS settlement, hardware
power-loss durability, automatic takeover or hostile same-UID/root mutation.
