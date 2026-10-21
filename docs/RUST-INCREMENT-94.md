# Rust increment 94: exact publication file-sync capability discovery

## Scope and acceptance

First establish actual publication synchronization behavior instead of assuming
that a checkpoint name proves a blocked fsync. Repeat four native retained-FD
server-recovery controls, then eight actual mover observations: debug/release,
payload/manifest first final-file fsync, healthy/stopped NFSD. Use retained bounded
source/destination tmpfs/NFS filesystems and local state on a third filesystem.
Production NFS and post-delivery private-source deletion remain disabled.

Use existing file_link_rpc/manifest_link_rpc qualification pauses to attach the
external observer. Complete LINK with a healthy backend, then intercept exactly
the first fsync on the final payload or manifest descriptor. Hold at syscall entry
and exit using bounded local observer rendezvous. These ptrace stops are artificial
and must never be called kernel NFS D-state. Reset the entry timestamp immediately
before execution so the artificial hold is excluded from RPC attribution.

Require complete two-name same-inode custody at entry, expected hash, original
source/state/epoch, uncommitted local status and guard exclusion. For stopped-NFSD
controls prove zero threads before allowing the syscall. Record either actual
D-state syscall 74/expected FD with completion after restoration, or successful
return before restoration with the worker held at exit. The latter supplies no
blocked-sync recovery qualification. Restore before releasing the exit gate.

Require successful remaining calls, original-worker attempt-1 commitment, actual
exit, original inode/hash as one-link final with staging absent, validated manifest
and clean original-state committed replay preserving producer reuse. Decode all
raw bytes; separately count calls/replies inside each sync and pairs spanning its
entry. Keep unknown compounds and broader-window activity visible. Native positive
controls never substitute for actual service-sync evidence.

Run both mandatory SLES gates, exact input/ELF/raw/proof audit and normal cleanup.
See the [step-by-step lab](NFS-PUBLICATION-SYNC-DISCOVERY-LAB.md). Rust inputs,
dependencies, API contracts, retry/review behavior and deadlines stay unchanged.
Directory-sync and other workload/cache/recovery boundaries remain separate.

## Results

Run publication-sync-discovery-20261021T122751Z-949e73c6 exits 0, status
PASSED, cleanup_errors=[]. All four native retained-FD prerequisites and eight
actual mover observations pass. The native controls retain their original
handles/backing bytes and demonstrate selected server recovery; none substitutes
for service-sync capability.

| Profile | Selected file | Healthy control | NFSD-stopped control | Selected RPC records / pairs spanning entry |
|---|---|---|---|---|
| Debug | Payload | fsync returns 0 | Returns 0 before restoration | 0 / 0 in both |
| Debug | Manifest | fsync returns 0 | Returns 0 before restoration | 0 / 0 in both |
| Release | Payload | fsync returns 0 | Returns 0 before restoration | 0 / 0 in both |
| Release | Manifest | fsync returns 0 | Returns 0 before restoration | 0 / 0 in both |

All eight selections are actual syscall 74 on the expected final-file descriptor:
payload FD 6 and manifest FD 9. Entry/exit controls are external ptrace t/T stops,
not D-state. The observer resets enter_ns after entry release and timestamps
return before the exit hold; the artificial holds are excluded from attribution.
Externally measured execution windows are 0.354-1.252 ms, including observer
scheduling overhead, not a performance benchmark. In stopped controls the original
call exits 7.896-8.828 seconds before restoration while NFSD remains zero. The
worker cannot advance to another filesystem operation until the exit gate opens.
No selected call is proved NFS-blocked, and **zero blocked publication file-sync
recovery cases are qualified**. Do not manufacture a COMMIT test or dirty the
production path merely to force such an outcome.

The wider I/O traces include 17 successful syncs per payload case and six per
manifest case: 92 calls total, all returning zero. No captured request or reply
lies inside any of these intervals. Two captured pairs span later staging-directory
sync entries: successful [53,22,9] SEQUENCE/PUTFH/GETATTR compounds in debug manifest
and release payload stopped-NFSD cases. Both requests precede the sync entry and
both replies arrive after its exit. These overlaps remain retained; they do not
establish that those directory syncs caused RPCs. None spans the eight selected
file-sync entries. Directory calls are observed, not independently fault-selected.

Service windows retain 21,782 raw records: 10,891 outgoing calls and 2,232 unknown
records across both directions. Wider decoded traffic includes 40 WRITEs and eight
COMMITs; those operations are not inside the observed sync intervals. Decoded
reply statuses include 0/2/10052/10022/10034/10013. Preserve unknown compounds and
these broader observations rather than treating them as service fsync proof.
Native windows retain 176 raw records separately. Capture-local absence is not a
claim about uncaptured traffic or every workload/cache condition.

At each entry and exit hold, independent read-only observations prove complete
same-inode staging/final aliases with two links, expected hashes and unchanged
private source. Payload cases remain PublishIntent with no manifest; manifest
cases remain Published/manifest_phase 3, with complete manifest aliases and
unchanged one-link payload/no payload staging. The inode observations cover these
holds; later source/payload retention is validated through content and root checks.
Local API status stays unchanged until the gate opens. Health responds in
1.797-2.109 seconds; local flock contention returns 73. Worker UID/GID 1000,
NoNewPrivs and no active capabilities, original coordinator/worker epoch, database
inode/configuration and enrollment remain intact.

After restoration and exit release, original workers complete attempt 1, the
selected original inode/hash becomes one-link final and staging is absent. All
workers subsequently exit with traced status 9, existing supervised retirement
after a confirmed Committed receipt, not death during fsync. Full manifest/hash
validation and clean original-state same-ID committed replay retain private-source
bytes, original root identities/enrollment and the recorder's newer source-path
bytes. The recorder has no new post-202 duty and the valid-manifest consumer
contract is unchanged. Normal shipping transfer remains 3N logical payload I/O.

Backing tmpfs devices are source 0:189/destination 0:190, with client devices
0:234/0:239 and local stat device 206. Both retain observed 64 MiB/4,096-inode
bounds. Keeper PID 2453525, start/mount namespace/full mountinfo and devices stay
identical across 33 server observations and final cleanup; reader role mounts stay
read-only. Server process/container/IP/namespace and VM boot identity remain stable
in all actual controls. Native restart controls also retain their observed network
namespace; this is not a general reboot/reclaim guarantee.

## Compatibility, proof controls and cleanup

- Production gate 20261021T122341Z-1808cc95: 211 target tests per debug/release profile.
- Qualification gate 20261021T122353Z-2234b939-nfs-qualification: 212 per profile.

Both processes exit 0 without cleanup errors. Locked cargo-zigbuild GNU/glibc
2.22, formatting/Clippy, pinned SLES 12 SP5 exact target execution, loader/library/
symbol checks and six negative ELF controls per mode pass. All 62 Rust inputs and
42 locked packages stay unchanged; one executable ships. Live binaries use the
preceding passing identical-source gates while fresh checks run; the audit checks
exact source contents and shipping bytes across both sets, allowing timestamp
variation in compressed archives. Eighteen frozen acquisition sources, native
probe/ELF and all forty fresh Rust artifacts/ELF reports are verified.

All 176 mover-proof corruptions and five storage-proof corruptions are rejected,
181 total. They cover false syscall/FD/worker/phase/exit/outcome, inclusion of
artificial holds, wrong restoration order, manifest/source/custody changes, missing
raw checkpoint, corrupted RPC bytes, shared devices and false backend state.
Seven RPC decoder regressions pass. Invalid standalone/conflicting discovery
flags refuse before provisioning.

The first audit failed because the new verifier expected filesystem_devices,
which Case records only for separate_exports. This retained-storage runner instead
captures actual client mountinfo plus a local stat device sample. Before correction,
the exact failed verifier/diagnostic and full original acquisition were retained in
[initial audit evidence](RUST-NFS-PUBLICATION-SYNC-DISCOVERY-INITIAL-EVIDENCE.json).
The corrected verifier derives the two actual NFS devices from captured mountinfo,
compares local-state stat device, and checks mount ID plus backing/keeper continuity.
The acquisition is byte-for-byte unchanged; no missing field is fabricated and
no failed audit is counted as passing evidence. There is no acquisition failure
or production behavior/deadline change. The earlier increment 88 fixture setup
failure remains separately retained as provenance.

Inventory captured at 2026-10-21T12:56:32.206115+00:00 after every process exits confirms zero
containers in both engines, unchanged baseline volume metadata/network names,
original Rust caches and no owned fixture resources. Both NFS mounts normally
unmount before owned-user/backend removal; keeper is removed last before the local
driver releases/removes bounded role volumes, parent volume and private network.
No force/lazy NFS unmount, VM reset, global host/cgroup or NAS policy change is used.

Read [raw acquisition](RUST-NFS-PUBLICATION-SYNC-DISCOVERY-EVIDENCE.json),
[input/audit evidence](RUST-NFS-PUBLICATION-SYNC-DISCOVERY-INPUT-EVIDENCE.json),
[production gate](RUST-SLES-EVIDENCE.json),
[qualification gate](RUST-SLES-QUALIFICATION-EVIDENCE.json) and the
[complete lab](NFS-PUBLICATION-SYNC-DISCOVERY-LAB.md).

## Limits and next work

This tests selected clean first final-file fsync behavior on one buffered NMP-41B
fixture/workload. It establishes no blocked file-sync recovery, service COMMIT
capability at these points, directory-sync outage matrix, arbitrary cache/load/
size behavior or physical durability. Further sync-failure cases require an actual
RPC-bearing candidate in a different condition, not a pause name or native probe.
Next qualify coordinator-death/original-state recovery while payload LINK is
pending across controlled server recovery; retain uncertain effects and actual-exit
exclusion. Other sync/directory, bootstrap/claim and worker-death boundaries remain.

The modern WSL2 kernel and separate keeper retain tmpfs memory. Native container
restart first quiesces NFSD; actual sync controls only stop/start NFSD. Abrupt
live-server death, independent NAS, outstanding UNSTABLE-data loss, persistent
disk/power, full session/reclaim and old SLES kernel/client guarantees remain
unqualified. Shipping account/deployment/access and larger/concurrent/endurance
workloads stay open. Destination staging removal is not private-source cleanup.
Keep all eight release gates open, production NFS/source deletion off, and
registration/S3/offline repair/DOC-06 deferred.
