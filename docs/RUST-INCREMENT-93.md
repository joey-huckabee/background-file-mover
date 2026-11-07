# Rust increment 93: controlled recovery at initial manifest LINK

## Scope and acceptance

Repeat four native retained-FD prerequisites, then four actual debug/release mover
cases with NFSD restart or NFSD-quiesced same-container confirmed termination/
start. Use two retained bounded tmpfs/client NFS filesystems and local state on a
third filesystem. Select existing manifest_link_rpc before initial manifest LINK.

Require Claimed, payload Published, manifest_phase 3, complete one-link manifest
staging, absent final manifest and unchanged one-link verified payload with no
payload staging. Stop the facility, release the pause and prove actual D-state
linkat with both directory FD/path/mount/inode observations, names COMMITTED.part/
COMMITTED.json and flags zero. Preserve source/staging/payload/state/epoch and
ownership, responsive health and ownership-specific contender refusal.

Restore without replacement. Require original-call success and raw successful
LINK inside its interval, final-manifest/new-parent sync before staging removal,
remaining successful syncs before local commitment, original manifest inode/hash
as one-link final, unchanged payload, attempt 1, actual exit and clean committed
replay preserving producer reuse. Keep recorder/consumer duties unchanged.

Follow the [step-by-step lab](NFS-MANIFEST-LINK-RECOVERY-LAB.md). Run both
mandatory SLES gates and independent source/raw/build/cleanup audit. Keep Rust
inputs/dependencies, API/retry/review/deadlines, production NFS and source deletion
unchanged.

## Live results

Run manifest-link-server-recovery-20261021T115541Z-4464ca9d exits 0, status
PASSED, cleanup_errors=[]. Four native retained-FD prerequisites pass before
four actual mover cases. No acquisition failure occurred in this increment.

| Build | Facility | Actual pending operation | Result |
|---|---|---|---|
| Debug | NFSD 2 to 0 to 2 | COMMITTED.part to COMMITTED.json linkat | Original worker/attempt 1; commitment and replay pass |
| Debug | NFSD zero, same-container SIGKILL/confirmed exit 137/start | COMMITTED.part to COMMITTED.json linkat | Original worker/attempt 1; commitment and replay pass |
| Release | NFSD 2 to 0 to 2 | COMMITTED.part to COMMITTED.json linkat | Original worker/attempt 1; commitment and replay pass |
| Release | NFSD zero, same-container SIGKILL/confirmed exit 137/start | COMMITTED.part to COMMITTED.json linkat | Original worker/attempt 1; commitment and replay pass |

Every case reaches payload Published, manifest_phase 3, complete one-link
manifest staging and absent COMMITTED.json. Manifest sizes are 340/345/342/347
bytes in matrix order; recording/submission names explain the variation. The
original verified 2,097,169-byte payload inode/hash stays final with one link and
no payload staging. Independent read-only backing observations prove source,
manifest staging and payload unchanged while stopped, with final manifest absent.

Actual workers block in D-state syscall 265, original staging-directory FD 8,
recording-directory FD 6 and flags zero. Both directory paths/mount IDs/inode
metadata match the external trace. Health responds in 1.797-1.953 seconds;
ephemeral-listener contenders refuse specifically on ownership in 0.953-1.188
seconds. Original coordinator/worker/epoch, phase-3 status, database inode/config
and enrollment remain intact. No timeout or free lock is used as remote-settlement
or redispatch authority.

After restoration, each original linkat returns zero and its pending interval
contains successful decoded NFS LINK named COMMITTED.json, with both PUTFH and
raw request/reply hashes retained. Manifest-file/new-parent sync precede staging
unlink, then staging-directory, final-manifest, staging-directory and recording-
directory syncs finish before local commitment. Six successful syncs per worker,
twenty-four total, return zero. The original manifest inode/hash becomes one-link
final, staging disappears and the payload stays unchanged. No post-restoration
WRITE occurs: manifest bytes were complete before the selected pause. Earlier
payload effects, manifest writing and original-file sync precede tracing.

All original workers complete attempt 1 and later exit with traced status 9,
existing supervised retirement after a confirmed Committed receipt. This does
not test worker death during the operation. Complete payload/manifest validation
and clean original-state same-ID replay preserve the committed job/manifest,
private source, enrollment and recorder's newer reused-path bytes.

Backing tmpfs devices are source 0:190/destination 0:189; client st_dev is
234/239, with local state 206. Both backing mounts retain observed 64 MiB/
4,096-inode bounds. Keeper PID 2383926, start/mount namespace/full mountinfo and
devices stay identical across twenty-five server observations and final cleanup.
Independent role mounts remain read-only. The actual debug container case changes
backend network namespace; other actual cases and all native controls retain
theirs. VM boot identity stays unchanged. This selected observation does not
establish a general network-namespace/reclaim guarantee.

## Compatibility and independent evidence

- Production gate 20261021T115432Z-15017b8f: 211 target tests per debug/release profile.
- Qualification gate 20261021T115444Z-214b3423-nfs-qualification: 212 per profile.

Both processes exit 0 without cleanup errors. Locked cargo-zigbuild GNU/glibc
2.22, formatting/Clippy, exact target execution in pinned SLES 12 SP5 userspace,
loader/library/symbol checks and six negative ELF controls per mode pass. All 62
Rust inputs and 42 locked packages remain unchanged; one executable ships.

Live binaries come from the preceding passing identical-source gates while fresh
checks run. The audit checks exact source archive contents and shipping bytes
across both sets; compressed archive hashes may differ by timestamp. Seventeen
frozen acquisition sources, native probe/ELF, all forty fresh Rust artifacts/ELF
reports and all source archives are independently verified.

All 146 mover-proof corruptions and five storage-proof corruptions are rejected,
151 total. Controls cover manifest bytes/phase/inode/link count, changed payload,
early final name, wrong directory FD/path/mount/name, syscall/clock/result,
missing raw LINK correlation, missing sync or wrong removal order, changed
worker/state/guard and shared-device errors. Seven RPC decoder regressions pass.
Invalid standalone/conflicting manifest recovery invocations refuse before
provisioning. Native windows retain 174 raw records and service windows 11,124,
including 1,342 unknown service records and decoded 2/10052 statuses. Unknown
compounds retain raw bytes. This is selected single-worker syscall/RPC
correlation, not full filehandle authority or cached-session/lease/reclaim proof.

After all fixture/gate processes exit, inventory captured at 2026-10-21T12:20:05.286776+00:00 confirms
zero containers in both engines, unchanged baseline volume metadata/network names,
original Rust caches and no owned fixture resources. Both NFS mounts normally
unmount before removing owned users/backend; keeper removal occurs last, then
the local driver releases/removes the bounded role volumes, parent volume and
network. No force/lazy NFS unmount, VM reset, host/cgroup policy change or NAS
operation is used. The earlier increment 88 fixture setup failure remains
retained as provenance; no acquisition or proof correction was needed here.

Read [raw acquisition](RUST-NFS-MANIFEST-LINK-RECOVERY-EVIDENCE.json),
[input/audit evidence](RUST-NFS-MANIFEST-LINK-RECOVERY-INPUT-EVIDENCE.json),
[production gate](RUST-SLES-EVIDENCE.json),
[qualification gate](RUST-SLES-QUALIFICATION-EVIDENCE.json) and the
[complete lab](NFS-MANIFEST-LINK-RECOVERY-LAB.md).

## Limits

This selects live continuation at initial manifest LINK. Other synchronization,
bootstrap/claim, coordinator/worker death/replacement, crash reconciliation and
delayed-effect settlement remain separate. Clean committed replay is a distinct
check. The consumer still waits for a valid completion manifest, while the local
receipt follows the remaining syncs. No consumer API-polling or recorder
monitoring duty is added. Namespace/sync success in retained memory is not proof
of physical NAS/power durability.

The separate keeper and VM retain tmpfs memory; NFSD is quiesced before container
termination. Abrupt live-server death, independent NAS, outstanding UNSTABLE-data
loss, persistent disk/power, full lease/reclaim/cached-session matrices and old
SLES kernel/client behavior remain unqualified. Single-worker syscall/RPC
correlation is not full opaque-handle authority or discarded-reply proof. Unknown
RPC compounds retain raw bytes. Pinned SLES userspace shares a modern WSL2 kernel.
Larger/concurrent/endurance workloads and shipping account/deployment/access
remain open. Destination staging removal is not private-source cleanup. Keep
production NFS/source deletion off, all eight release gates open, and registration/
S3/repair/DOC-06 deferred.
