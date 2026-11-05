# Offline state inspection and backup

These commands prepare for a later explicit migration. They do not convert or
restore a database. Use a production build; qualification builds are lab-only.

1. Schedule downtime. Stop the mover service with your installed systemd unit:
   `sudo systemctl stop YOUR-MOVER-UNIT.service`. Run maintenance as the original
   mover account, using the original configuration and local state directory.
2. Check `file-mover --status /etc/file-mover/config.json`. A live daemon or
   surviving worker prevents either command below. If it reports OwnerUnavailable
   or maintenance refuses surviving workers, follow the
   [restart/orphan guide](RUST-OPERATOR-GUIDE.md); restore unavailable storage and
   wait for the original processes to exit. Do not remove locks/workers.json,
   replace state or start a second owner to bypass refusal.
3. Inspect:

   ```sh
   file-mover --check-state /etc/file-mover/config.json
   ```

   Success reports schema, instance, job count and stored pairing state. Schema
   11 and legacy-only schema 12 are supported here. Missing/empty/foreign/older/
   newer/changed/corrupt state and UUID-bearing state refuse. `RecordedActive`
   describes stored enrollment evidence, not a filesystem health check. `Prepared`,
   `OwnershipMissing` or `Unenrolled` are not repaired by inspection/backup.
4. Prepare an existing private backup parent on protected local storage, owned
   by the mover account, with enough free space for a complete database snapshot.
   For example create `/var/lib/file-mover-backups` with mode 0700 through your
   normal host provisioning. Keep it outside state, source and destination trees,
   including older jobs' recorded roots. Do not use NFS, symlinks, a mounted file
   or a bind-mount alias of those scopes. Do not reuse an existing output directory.
5. Create the snapshot with a unique new absolute directory:

   ```sh
   file-mover --backup-state /etc/file-mover/config.json /var/lib/file-mover-backups/before-upgrade-20261105
   ```

   Require exit status 0 and `verified:true`. The directory contains private
   `state.sqlite` and `VERIFIED.json`. The snapshot includes committed WAL data;
   do not substitute a raw copy of the live main database. The receipt records
   the verified snapshot hash, original identity and executable hash. Protect
   this directory as sensitive historical state.
6. On any failure, keep original state and the incomplete output. Fix the cause
   (permissions, local capacity, unsupported state or surviving processes) and
   retry using a different new directory. No automatic cleanup, resume or overwrite
   occurs. Even if VERIFIED.json exists after a sync error, the failed command
   did not establish successful durable publication. There is no apply command.
7. Restart only with software compatible with the unchanged original schema.
   This foundation build still refuses normal schema-11 service startup; keep
   its original compatible binary until a qualified migration is available.

Source/destination roots may be unavailable: these commands do not inspect files,
move data, enroll roots or settle remote filesystem effects. Stop/refusal rules
still apply. They write normal local lifetime metadata and may update SQLite
shared-memory coordination, but do not change live job rows or schema.

Never restore this snapshot over active or newer custody. A stale database can
lose ownership/replay evidence. There is no automatic restore/downgrade/takeover.
Clearing history does not erase previously exported backups: retire them separately
under your retention policy; the mover retains no live linkage to cleared files.

See [increment 112](RUST-INCREMENT-112.md) for actual validation and limitations.
