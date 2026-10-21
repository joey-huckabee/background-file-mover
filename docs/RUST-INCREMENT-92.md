# Rust increment 92: controlled recovery at initial payload LINK

## Scope and acceptance

Repeat four native retained-FD prerequisites, then four actual debug/release
mover cases with NFSD restart or NFSD-quiesced same-container confirmed
termination/start. Use two retained bounded tmpfs/client NFS filesystems and a
third local state filesystem. Select existing file_link_rpc immediately before
the payload link/unlink fallback's initial linkat call.

Require Claimed/PublishIntent, complete verified one-link 2,097,169-byte staging,
expected hash and absent final payload/manifest. Stop the facility, release the
pause, prove actual D-state linkat with original old/new directory FDs, names
1.part/data.bin and flags zero. Preserve backing source/staging, original state,
epoch/ownership and responsive health; a contender refuses specifically on ownership.

Restore without replacement and require the original call's success plus a raw
successful LINK inside its interval. Require final-file/new-parent sync before
staging removal, old-parent sync before later manifest publication, original
staging inode/hash as the one-link final payload, attempt-1 commitment, actual
worker exit and original-state committed replay preserving recorder reuse.

Follow the [step-by-step lab](NFS-PAYLOAD-LINK-RECOVERY-LAB.md). Both mandatory
SLES gates and independent source/raw/build/cleanup audit are required. Keep Rust
inputs/dependencies, API/retry/review/deadlines, production NFS and source deletion
unchanged.

## Live results

Run payload-link-server-recovery-20261021T014222Z-0d700c9e exits 0, status
PASSED, cleanup_errors=[]. Four native retained-FD prerequisites pass before
four actual mover cases. No acquisition failure occurred in this increment.

| Build | Facility | Actual pending operation | Result |
|---|---|---|---|
| Debug | NFSD 2 to 0 to 2 | linkat from 1.part to data.bin | Original worker/attempt 1; commitment and replay pass |
| Debug | NFSD zero, same-container SIGKILL/confirmed exit 137/start | linkat from 1.part to data.bin | Original worker/attempt 1; commitment and replay pass |
| Release | NFSD 2 to 0 to 2 | linkat from 1.part to data.bin | Original worker/attempt 1; commitment and replay pass |
| Release | NFSD zero, same-container SIGKILL/confirmed exit 137/start | linkat from 1.part to data.bin | Original worker/attempt 1; commitment and replay pass |

At the pause, every case has PublishIntent and complete verified 2,097,169-byte
staging with the expected SHA-256 and one link. Final payload/COMMITTED.json
are absent. Independent read-only backing observations prove source/staging
identity/hash and absent publication unchanged while stopped. Actual workers
block in D-state syscall 265, old staging-directory FD 8 and new nested-directory
FD 10, flags zero. Both FD paths, mount IDs and directory inode metadata match
the externally traced original call. Health responds in 1.797-2.219 seconds;
ephemeral-listener contenders refuse specifically on ownership in 0.922-0.969
seconds. Original coordinator/worker/epoch, status, local database inode/config
and source enrollment remain intact.

After restoration, each original linkat returns zero and its pending interval
contains a successful decoded NFS LINK named data.bin, with both PUTFH hashes
and raw request/reply hashes retained. Final-file and new-parent sync both return
zero before staging unlink; old-parent sync precedes later manifest publication.
All seventeen traced syncs per worker succeed, sixty-eight total. The original
staging inode/hash becomes the one-link final payload and staging is absent.
Post-restoration decoded WRITEs are small manifests, 336/341/338/343 bytes in
matrix order; they are not payload-copy evidence. Earlier copy/verification/
original-file sync precede trace attachment.

All original workers complete attempt 1 and subsequently exit with traced
status 9, existing supervised retirement after a confirmed Committed receipt.
This is not worker death during the operation. Complete manifest/payload
validation and clean original-state same-ID replay preserve the committed job,
manifest, private source, enrollment and recorder's newer reused-path bytes.

Backing tmpfs devices are source 0:141/destination 0:142; client st_dev is
186/191, with local state 158. Both backing mounts retain observed 64 MiB/
4,096-inode bounds. Keeper PID 2253434, start/mount namespace/full mountinfo and
devices stay identical across twenty-five server observations and final cleanup.
Independent role reader mounts remain read-only. The actual debug container case
changes backend network namespace; the other actual cases and all native controls
retain theirs. VM boot identity stays unchanged. This selected observation does
not establish a general network-namespace/reclaim guarantee.

## Compatibility and independent evidence

- Production gate 20261021T014052Z-4515af42: 211 target tests per debug/release profile.
- Qualification gate 20261021T014106Z-2e610510-nfs-qualification: 212 per profile.

Both processes exit 0 without cleanup errors. Locked cargo-zigbuild GNU/glibc
2.22, formatting/Clippy, exact target execution in pinned SLES 12 SP5 userspace,
loader/library/symbol audit and six negative ELF controls per mode pass. All 62
Rust inputs and 42 locked packages remain unchanged; one executable ships.

Live binaries come from the preceding passing identical-source gates while fresh
checks run. The audit checks exact source archive contents and shipping executable
bytes across live/fresh gates; compressed archive hashes may differ by timestamp.
Seventeen frozen acquisition sources, the native probe/ELF, all forty fresh Rust
artifacts/ELF reports and all source archives are independently verified.

All 138 mover-proof corruptions and five storage-proof corruptions are rejected,
143 total. They cover custody/bytes/inode/link count, early payload/manifest,
wrong source/target directory FD/path/mount/name, syscall/clock/result, missing
raw LINK correlation, missing sync, unlink/publication order, worker/state/guard
and shared-device errors. Seven RPC decoder regressions pass. Invalid standalone
and conflicting recovery-flag combinations also refuse before provisioning.
Native windows retain 172 raw records and service windows 11,678, including 1,640
unknown service records and decoded 10052/2 statuses. Unknown compounds remain
preserved. Raw success is correlated inside the original pending linkat interval;
this is not full filehandle authority or cached-session/lease/reclaim proof.

After every fixture/gate process exits, inventory captured at 2026-10-21T02:04:46.683956+00:00 confirms
zero containers in both engines, unchanged baseline volume metadata/network names,
original Rust caches and no owned fixture resources. Both NFS mounts normally
unmount before removing owned users/backend. Keeper removal occurs last, followed
by local-driver release/removal of the bounded role volumes, parent volume and
network. No force/lazy NFS unmount, VM reset, host/cgroup policy change or NAS
operation is used. The earlier increment 88 fixture setup failure remains
retained as provenance; no acquisition or proof correction was needed here.

Read [raw acquisition](RUST-NFS-PAYLOAD-LINK-RECOVERY-EVIDENCE.json),
[input/audit evidence](RUST-NFS-PAYLOAD-LINK-RECOVERY-INPUT-EVIDENCE.json),
[production gate](RUST-SLES-EVIDENCE.json),
[qualification gate](RUST-SLES-QUALIFICATION-EVIDENCE.json) and the
[complete lab](NFS-PAYLOAD-LINK-RECOVERY-LAB.md).

## Limits

This is selected live continuation at initial payload LINK. Initial manifest
LINK, other sync boundaries, coordinator/worker death/replacement, crash
reconciliation and delayed-effect settlement remain separate. Clean committed
replay is a distinct check. The recorder has no post-202 monitoring duty and
consumers still wait for the valid completion manifest. A successful LINK alone
is not completed delivery or proof of physical durability.

The separate keeper and VM retain tmpfs memory; NFSD quiescence precedes container
termination. Abrupt live-server death, independent NAS, outstanding UNSTABLE-data
loss, persistent disk/power, full lease/reclaim/cached-session matrices and old
SLES kernel/client behavior remain unqualified. Single-worker syscall/RPC
correlation is not full opaque-handle authority or discarded-reply proof. Unknown
RPC compounds retain raw bytes. Pinned SLES userspace shares a modern WSL2 kernel.
Larger/concurrent/endurance workloads and shipping account/deployment/access
remain open. Staging removal is not private-source cleanup. Keep production
NFS/source deletion off, all eight release gates open, and registration/S3/
repair/DOC-06 deferred.
