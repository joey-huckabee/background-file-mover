# Increment 107: guarded offline completed-job history clear

2026-11-02 through 2026-11-03 (local coordinator work dates). The user explicitly authorizes implementation
of group 50 after its contract decision. This is a bounded working increment;
it does not freeze all P01 schemas or implement the remaining admin dashboard.

## Behavior

`file-mover --clear-history CONFIG.json JOB_ID...` previews the selected IDs and
explains UUID/submission replay forgetting, unchanged files and loss of mover
tracking. Add `--confirm` to apply. Output is an actual cleared_count. Require
1-256 canonical positive i64 IDs. Process every entry; missing/noncommitted jobs
and repeated IDs after a successful removal skip. There is no batch deduplication
or reported skip reason. No unconfirmed call clears job records. Preview still records its own local
process lifetime; it is not entirely filesystem-read-only.

Acquire the existing local InstanceGuard before SQLite, including independent
worker-group epoch admission. Hold it until the Store owner thread has closed. Register this command itself
in the process-group epoch before either Store open, including preview, so
its local SQLite owner is independently covered after early flock closure.
Preview is read-only for job data; it writes normal local lifetime metadata.
No source/destination bootstrap, payload filesystem access, enrollment, filesystem worker spawning,
HTTP listener or payload deletion is part of this command. It works with payload
roots unavailable. The shared guard excludes other daemon/effect commands.

A dedicated Store maintenance mode opens existing current-schema state only:
no CREATE, fresh initialization or legacy migration. Ordinary service Store handles
cannot invoke clear. The caller must hold offline instance/lifetime admission;
the Store transaction alone is not worker-quiescence proof. Current cancellation
is not persisted/implemented, so only load-validated **committed** jobs qualify.
Daemon stop, errors, published payloads or precommit manifests do not qualify.

One IMMEDIATE transaction removes all ten per-job dependency tables, then the
selected job rows, under foreign-key enforcement. This removes live request/
replay, claim/transfer/manifest, route observations, audit/reset, failure and
accounting linkage. Preserve shared metadata, source enrollment/ownership and
sqlite_sequence. A cleared submission may become fresh work with a strictly
larger job ID. Files/COMMITTED.json and their inodes/bytes are not modified.
Unknown old files are not scanned or adopted after restart; they are unmanaged.

## Meaningful checks

Four Store tests cover:

- Every table's job-linked rows disappear while another completed/unfinished
  job, shared enrollment/instance data and increasing IDs survive. Reopen and
  replay the old prototype body as new unclaimed work.
- Published files and manifest phases 0-3 remain ineligible; malformed batches
  cannot partly apply, including an invalid ID after an eligible selection.
- A late injected SQL DELETE failure on the second selected job rolls back
  both jobs and all dependent rows; reopen preserves the original data.
- Missing, empty and schema-10 state cannot be created, initialized or migrated
  by the maintenance opener; ordinary service handles cannot clear.

Two CLI behavior tests plus one subprocess helper and the existing competing-
entry-point test cover explicit preview/confirm, malformed selections, missing/
foreign state, live daemon refusal before SQLite, and a real surviving child
whose separate coordinator has exited with its guard closed. The helper child
inherits the recorded group but no guard descriptor. Cleanup targets only that
reported PID and waits for guard admission before restarting.

The end-to-end test also asserts the preview process PID matches its persisted
epoch group. This proves wiring, not actual uninterruptible local-disk I/O.

The end-to-end test performs a real local transfer, retains source payload and
producer-reused input, snapshots inode/content identities, clears with both roots
renamed away, then restores them and restarts normally. Old status/claims/
manifest/route/accounting are gone; shared enrollment still works. Repeating
the original producer body claims newly produced data into job 2 without
changing job 1's leftover source, delivered payload or manifest.

These are local SQLite/filesystem and userspace checks, not NFS RPC settlement,
power-failure durability, secure byte erasure or cancelled-job qualification.
The synthetic SQL abort demonstrates transaction rollback, not a hardware crash.

## Validation

Validated source: `426f4be05ef8ceeccaa903b9683b7fd165e55db4`.
The [tracked evidence inventory](HISTORY-CLEAR-EVIDENCE.json) records source,
report and artifact hashes; raw packs remain in the ignored WSL validation tree.

- Production 20261103T060450Z-23c5ba73: **PASSED**, 218 tests in debug and
  218 in release; 20 executable artifacts audited/relocated, normal cleanup.
- Qualification 20261103T063347Z-a9292bff-nfs-qualification: **PASSED**,
  220 tests in debug and 220 in release; 20 executable artifacts audited/relocated,
  normal cleanup. The feature name does not mean these local tests requalify NFS.

Both archives contain the same 63 source inputs, verified against the committed
Git blobs. All 40 retained executable hashes match their reports. Both modes
passed formatting, Clippy, independent ELF audits and all six negative controls.
All containers created by the final gates were removed.
Every Rust build/test uses scripts/check-rust-sles.py, cargo-libc 0.2.4,
GNU/glibc 2.22, independent ELF audits and pinned SLES target execution.

Two preliminary source snapshots were intentionally interrupted during review:
20261103T051435Z-1aa593a0 and 20261103T051755Z-90160623. Keep their reports/logs;
neither is a passing gate. Review strengthened coordinator-exit coverage and
made the helper marker unambiguous under single-threaded libtest before the
final runs. The run timestamps are UTC; the coordinator work date is local.

The first completed debug run, 20261103T052158Z-bf9d1e90, passed the CLI/API
suite but failed three Store fixture setups: their inherited group_by_generator
setting is unsupported by transfer persistence. Correct the fixture to the
existing supported ungrouped mode; keep the refusal/validation unchanged and
retain that failed report. The final-source gates above validate the corrected input.

The 20261103T053634Z-1f51ef6c run passed all debug tests before being
intentionally interrupted in release. A final review then registered the clear
command's own process group before SQLite, closing the local owner-thread
lifetime gap; the preview PID/epoch assertion covers that wiring. Its earlier
results are not final-source qualification. Retain this interrupted report too.

## Scope still pending

No authenticated HTTP/dashboard clear or safely-cancelled state exists yet.
No new dependency, schema version or producer-format migration is added.
SC-181-183 cover the group-50 contract; this implements only its offline committed
subset. Global UUID semantics, safe cancellation, physical/manual/automatic
deletion, remote authentication and the remaining API/release gates remain open.
Old NFS/systemd evidence belongs to older artifacts and is not requalified here.
