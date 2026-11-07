# Rust increment 91: controlled recovery during manifest commitment

## Scope and acceptance

Repeat four native retained-FD prerequisites, then debug/release actual mover
cases with NFSD restart or NFSD quiescence followed by same-container confirmed
termination/start. Use two retained bounded tmpfs/client NFS filesystems and local
state on a third filesystem. Select the existing manifest_unlink pause.

Require payload Published, manifest_phase 3, complete same-inode manifest aliases
with two links, and unchanged one-link verified payload with no payload staging.
Stop the facility, release the pause and prove actual D-state unlinkat on the
staging directory FD/name COMMITTED.part, flags zero. Preserve source, manifest,
payload, local state, epoch and ownership; health remains responsive and a
contender refuses specifically on ownership.

Restore without replacing the worker. Require original syscall success and a
successful decoded REMOVE within its pending interval, original manifest inode/
hash with one link, staging absent, remaining successful syncs, attempt-1 local
commitment and actual worker exit. Clean original-state same-ID replay must
preserve the committed manifest and recorder's newer bytes. The consumer still
waits for a valid completion manifest; the recorder has no post-202 monitoring
duty. Manifest visibility precedes the local receipt at this selected boundary.

Follow the [complete lab](NFS-MANIFEST-RECOVERY-LAB.md). Run both mandatory SLES
gates and independent source/raw/build/cleanup audit. Keep all Rust inputs,
dependencies, API/retry/review/deadlines, production NFS and source deletion
unchanged.

## Live results

Run manifest-server-recovery-20261021T011415Z-16aad95b exits 0, status PASSED,
cleanup_errors=[]. Four native retained-FD prerequisites pass before four actual
mover cases: debug/release with NFSD restart and with NFSD-quiesced same-container
SIGKILL/confirmed exit 137/start. No acquisition failure occurred in this increment.

| Build | Facility | Pending operation | Result |
|---|---|---|---|
| Debug | NFSD 2 to 0 to 2 | COMMITTED.part unlinkat | Original worker/attempt 1; commitment and replay pass |
| Debug | NFSD zero, same-container confirmed termination/start | COMMITTED.part unlinkat | Original worker/attempt 1; commitment and replay pass |
| Release | NFSD 2 to 0 to 2 | COMMITTED.part unlinkat | Original worker/attempt 1; commitment and replay pass |
| Release | NFSD zero, same-container confirmed termination/start | COMMITTED.part unlinkat | Original worker/attempt 1; commitment and replay pass |

Every case begins with payload Published, manifest_phase 3 and complete same-inode
manifest staging/final names with two links. Manifest sizes are 338/343/340/345
bytes in matrix order; the distinct recording/submission names explain size
variation. The payload remains the original verified 2,097,169-byte inode/hash
with one link and no payload staging. Read-only independent backing observations
prove private source, complete manifest aliases and payload unchanged while stopped.

Actual workers block in D-state syscall 263 on original staging-directory FD 8,
flags zero. Health responds in 1.657-1.828 seconds. Ephemeral-listener contenders
refuse specifically on local ownership in 0.921-1.016 seconds. Original coordinator,
worker, epoch, database inode/configuration, source enrollment and status stay
unchanged. No timeout or newly free lock is used as remote-settlement authority.

After restoration, each original unlink returns zero and its pending interval
contains a successful decoded REMOVE named COMMITTED.part, with PUTFH and raw
request/reply hashes retained. The original final manifest inode/hash survives
with one link and staging is absent. No post-restoration WRITE occurs in these
windows: bytes were complete before the pause. Each case has four successful
remaining sync calls in order: staging directory, final manifest file, staging
directory, recording directory. Sixteen total return zero before local commitment.
Initial manifest LINK/file/new-parent sync precede observer attachment.

All original workers complete attempt 1 and later exit with traced status 9,
existing supervised retirement after a confirmed Committed receipt. This is not
worker death during the selected operation. Complete payload/manifest validation
and clean original-state same-ID replay preserve the committed job, original
manifest, private source and recorder's newer source-path bytes.

Backing devices are source 0:142 and destination 0:141; client st_dev is 186/191
and local state 158. Each backing tmpfs retains observed 64 MiB/4,096-inode bounds.
Keeper PID 2191398, start/mount namespace/full mountinfo/devices remain identical
across twenty-five server observations and final cleanup. Role reader mounts
remain read-only. The actual debug container case changes backend network
namespace; the other actual cases retain theirs. VM boot identity stays unchanged.
This selected observation does not establish a general namespace/reclaim guarantee.

## Compatibility and independent evidence

- Production gate 20261021T011257Z-2bcc0865: 211 target tests per debug/release profile.
- Qualification gate 20261021T011309Z-205562b7-nfs-qualification: 212 per profile.

Both processes exit 0 without cleanup errors. Locked cargo-zigbuild GNU/glibc
2.22, formatting/Clippy, exact target execution in pinned SLES 12 SP5 userspace,
loader/library/symbol checks and six negative ELF controls per mode pass. All 62
Rust inputs and 42 locked packages remain unchanged; one executable ships.

The live fixture uses the preceding passing identical-source gates while fresh
checks run. The final audit checks exact archive contents and shipping executable
bytes across live/fresh gates; compressed archive hashes may differ by timestamp.
Seventeen frozen acquisition scripts, retained native probe/ELF, all forty fresh
Rust artifacts/ELF reports and source archives are independently verified.

All 122 mover-proof corruptions and five storage-proof corruptions are rejected,
127 total. They cover wrong custody/bytes/inode/link counts, manifest phase/bytes,
payload replacement, wrong worker/state/guard/device, syscall name/FD/clock/result,
missing raw correlation and sync order. Seven RPC decoder regressions pass.
Native windows retain 176 raw records and service windows 11,026, including 1,258
unknown service records and decoded 2/10052 statuses. Unknown compounds remain
preserved. This is selected single-worker syscall/RPC correlation, not a complete
filehandle-authority, cached-session/lease/reclaim or discarded-reply proof.

After every fixture/gate process exits, inventory captured at 2026-10-21T01:37:19.456692+00:00 confirms
zero containers in both engines, unchanged baseline volume metadata/network names,
original Rust caches and no owned fixture resources. Both client mounts normally
unmount before removing owned containers; keeper is removed last, then the local
driver releases both retained tmpfs volumes. No force/lazy NFS unmount, VM reset,
host/cgroup policy change or NAS operation is used. The earlier increment 88
fixture setup failure remains retained as provenance; no acquisition or proof
correction was needed for this matrix.

Read [raw acquisition](RUST-NFS-MANIFEST-RECOVERY-EVIDENCE.json),
[input/audit evidence](RUST-NFS-MANIFEST-RECOVERY-INPUT-EVIDENCE.json),
[production gate](RUST-SLES-EVIDENCE.json),
[qualification gate](RUST-SLES-QUALIFICATION-EVIDENCE.json) and the
[complete lab](NFS-MANIFEST-RECOVERY-LAB.md).

## Limits

This is live continuation at one manifest namespace-removal boundary. Initial
manifest LINK/rename, other sync boundaries, coordinator/worker death/replacement
and crash reconciliation remain separate. A later clean committed replay is a
distinct check. The valid-manifest consumer contract stays unchanged: all required
payloads were already verified and Published when the manifest became visible.
Visibility and the later local receipt are different observations; neither this
retained-memory lab nor sync return values establish physical NAS/power durability.

The separate keeper and VM preserve tmpfs memory, and NFSD is quiesced before
container termination. Abrupt live-server death, independent NAS, outstanding
UNSTABLE-data loss, persistent storage/power, full lease/reclaim/session matrices
and old SLES kernel/client behavior remain unqualified. Pinned SLES userspace
shares a modern WSL2 kernel. Larger/concurrent/endurance workloads and shipping
account/deployment/remote access remain separate. Removing destination manifest
staging is not postcommit source cleanup. Keep production NFS/source deletion off,
all eight release gates open, and registration/S3/repair/DOC-06 deferred.
