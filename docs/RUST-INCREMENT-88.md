# Rust increment 88: controlled recovery across distinct NFS filesystems

## Scope and acceptance

Qualify the selected source-copy boundary on genuinely distinct client NFS
filesystems. First prove two independently retained tmpfs superblocks, their
identity continuity through controlled backend restart, read-only independent
observation and two distinct client NFS devices. Local SQLite/ownership remains
on a third filesystem. Run four original-FD native controls before four actual
supervised Rust cases: debug/release with NFSD restart or NFSD quiescence then
confirmed same-container SIGKILL/exit-137/start.

Each mover must block in its actual claimed-source read after copying 1 MiB,
retain the original coordinator, worker, assignment, local epoch and custody,
refuse competing startup, and finish attempt 1 after restoration. Verify source,
staging/final inode, complete manifest, enrollment/local-state continuity and
clean original-state restart/same-ID replay preserving newer producer data.

Retain failed setup evidence, exact acquisition sources and raw wire/syscall
proof, independently audit results and run both required SLES gates. Follow the
[step-by-step infrastructure and test procedure](NFS-DISTINCT-RECOVERY-LAB.md).
Production NFS/source deletion, Rust inputs/dependencies, API handoff,
retry/review behavior and shutdown deadlines stay unchanged.

## Results

Run distinct-server-recovery-20261020T233014Z-9cb6d7f4 exits 0 with status PASSED
and cleanup_errors=[]. Four native controls precede four actual mover cases:

| Build | Facility | Actual blocked operation | Outcome |
|---|---|---|---|
| Debug | NFSD 2 to 0 to 2 | Claimed-source read requesting 1 MiB | Original worker/attempt 1, Committed and replay passed |
| Debug | NFSD zero, then same-container SIGKILL/exit 137/start | Claimed-source read requesting 1 MiB | Original worker/attempt 1, Committed and replay passed |
| Release | NFSD 2 to 0 to 2 | Claimed-source read requesting 1 MiB | Original worker/attempt 1, Committed and replay passed |
| Release | NFSD zero, then same-container SIGKILL/exit 137/start | Claimed-source read requesting 1 MiB | Original worker/attempt 1, Committed and replay passed |

Keeper/backing devices are source 0:141 and destination 0:142; client devices are
0:186 and 0:191. Source/staging st_dev values are 186/191 and local SQLite state
is 158 in every case. This closes the earlier shared-device scope gap for this
selected controlled source-copy boundary. It is actual buffered copying across
different filesystems, not a test asserting a particular EXDEV rename error.

Keeper PID 2008259, StartedAt, mount namespace, complete mountinfo and devices
remain identical across twenty-five server-state observations and final cleanup.
Both kernel mount tables show size=65536k,nr_inodes=4096. The independent reader
sees the same two devices through read-only mounts. All four native probes retain
their original opaque filehandle/backing inode, complete A-to-B 4 KiB writes and
readback with eight successful sync calls and normal exit 0. Successful sessions
and WRITE verifiers change in all four controls. One native container-source
control observes a changed server network namespace; other native controls and
all four actual mover cases do not. The VM boot ID remains unchanged throughout.
Do not turn that single native observation into fresh-namespace mover support.

Every mover is actually D-state in read(2) on its private claimed-source FD after
1,048,576 staged bytes, with no read-completed marker. Health remains responsive
in 1.703-1.890 seconds; competing startup with an ephemeral listener refuses on
local ownership in 0.844-0.922 seconds. Claimed/Intent status, original epoch,
local database inode/configuration, enrollment and private source remain stable.
All eighty observed worker sync calls return zero. Each worker completes its
2,097,169-byte payload on attempt 1 and subsequently exits with traced status 9,
the existing supervised retirement after confirmed commitment. This is not
worker-death-during-copy qualification. The original staging inode becomes final,
source/final hashes and complete manifests match, and original-state restart with
same-ID replay returns the same committed job/manifest while newer producer bytes
remain untouched.

The first acquisition failed before server startup because the OCI runtime
rejected proc/PID/root binds. It ran zero native or Rust recovery cases and made
no NFS client mounts. Its exact inputs/report and normal-unmount cleanup helper
remain [retained](RUST-NFS-DISTINCT-RECOVERY-INITIAL-EVIDENCE.json). The passing
fixture uses Podman local-driver named tmpfs volumes instead.

## Compatibility, independent audit and cleanup

- Production gate 20261020T232331Z-a6d39e23: 211 target tests per debug/release profile.
- Qualification gate 20261020T232331Z-593cf8a0-nfs-qualification: 212 per profile.

Both processes exit 0 without cleanup errors. Formatting/Clippy, locked
cargo-zigbuild GNU/glibc 2.22, exact target tests in pinned SLES 12 SP5,
loader/library/symbol checks and six negative ELF controls per mode pass.
All 62 Rust inputs and the 42-package graph remain unchanged. There is still
one shipping executable; forty audited artifacts include tests and both modes.
The live acquisition used the preceding passing, identical-source gates while
fresh checks ran; the audit compares all source archive contents and exact
shipping bytes to the fresh gates, not compressed archive hashes across runs.

The audit validates sixteen frozen acquisition sources, the native probe/ELF,
original syscall/FD/security/clock/state proofs, raw RPC hashes and redecoding,
keeper/reader/backend/client identities, both gate archives and forty ELF files.
All 58 mover-proof corruptions and five distinct-storage corruptions are rejected;
seven RPC decoder regression tests pass. Native windows retain 172 raw records;
service windows retain 11,882 records including 1,751 unknown records and decoded
10052/2 statuses. Unknown compounds are preserved, not silently discarded or
attributed to synchronization intervals without actual evidence.

After all users and both gates exit, inventory captured at
2026-10-20T23:47:46.358521+00:00 confirms zero containers in both engines, the
original two rootful Rust caches/default network and unchanged baseline volume
metadata/network names on both engines. Client mounts normally unmount before
owned resources are removed; Podman's local driver releases the retained tmpfs
mounts after the keeper is removed last. No force/lazy NFS unmount is used.

Read the [raw acquisition](RUST-NFS-DISTINCT-RECOVERY-EVIDENCE.json),
[input/audit evidence](RUST-NFS-DISTINCT-RECOVERY-INPUT-EVIDENCE.json),
[production gate](RUST-SLES-EVIDENCE.json),
[qualification gate](RUST-SLES-QUALIFICATION-EVIDENCE.json) and
[complete procedure](NFS-DISTINCT-RECOVERY-LAB.md).


## Limits and remaining work

Two different retained tmpfs filesystems on one kernel NFS backend qualify a
specific cross-filesystem copy path. They do not simulate independent NAS systems
or persistent disks. The keeper survives every event and NFSD is explicitly
quiesced before container termination. Abrupt live-server termination, fresh
network namespace, VM/NAS reboot and physical power/disk durability stay
unqualified. Outstanding UNSTABLE-data loss, delayed effects, other service
phases and worker death/replacement remain future work. No forced/lazy NFS
unmount or host/NAS policy change is part of this fixture.

Pinned SLES 12 SP5 userspace shares the modern WSL2 kernel; this does not qualify
the original SLES kernel/NFS client, vendor-maintenance patches, deployment
accounts or 100 GB/endurance performance. Keep all eight release gates open,
registration/repair/DOC-06 deferred and production NFS/source deletion disabled.
The recorder still submits/retries the same JSON until 202 and has no later
monitoring duty; consumers require a validated completion manifest.
