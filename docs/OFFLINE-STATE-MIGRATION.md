# Offline schema-11 to schema-12 migration

This command converts validated legacy state without opening payload roots. It
preserves job IDs, file indices, claims, transfer attempts, audits, enrollment,
manifest-v1 bytes and the job-ID high-water mark. UUID admission and manifest v2
remain disabled. No automatic migration or reverse conversion is provided.
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
   metadata may be written. Schema 11 reports conversion_required:true. Valid
   legacy-only schema 12 reports false. Preview does not prove free capacity,
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
