# Rust increment 89: server recovery during destination verification

## Scope and acceptance

Qualify four debug/release live-coordinator destination-staging reread cases with
NFSD restart or NFSD quiescence then same-container SIGKILL/confirmed exit/start.
Repeat four native controls before any mover case. Reuse the two bounded tmpfs
filesystems retained by a separate keeper, positively verify distinct client NFS
devices and keep SQLite/ownership local. Keep production NFS/source deletion off.

Require Copied status with a complete staging file, actual D-state staging read
at offset zero, unchanged ownership/state/source/staging and no publication while
blocked. After recovery require original FD/inode full reread through EOF,
publication afterward, original-worker attempt-1 commitment, complete payload and
manifest validation and clean original-state replay preserving producer reuse.
Run both mandatory SLES gates and independently audit exact raw/source/build proof.
Follow the [complete step-by-step lab](NFS-VERIFICATION-RECOVERY-LAB.md).

## Results

Run verify-server-recovery-20261021T000724Z-389c6597 exits 0 with status PASSED
and cleanup_errors=[]. All four repeated native controls pass before any mover:
source/destination with NFSD restart and NFSD-quiesced container termination/start.
They retain original descriptors, opaque handles, backing inodes and A-to-B bytes;
eight sync calls return zero and all probes exit normally. All four observe
changed successful sessions and WRITE verifiers. The native container-source
case changes network namespace; other native cases retain theirs.

| Build | Facility | Pending operation | Completion |
|---|---|---|---|
| Debug | NFSD threads 2 to 0 to 2 | Actual staging read, offset 0, 1 MiB requested | Original worker/attempt 1; commitment and replay pass |
| Debug | NFSD zero, same-container SIGKILL/exit 137/start | Actual staging read, offset 0, 1 MiB requested | Original worker/attempt 1; commitment and replay pass |
| Release | NFSD threads 2 to 0 to 2 | Actual staging read, offset 0, 1 MiB requested | Original worker/attempt 1; commitment and replay pass |
| Release | NFSD zero, same-container SIGKILL/exit 137/start | Actual staging read, offset 0, 1 MiB requested | Original worker/attempt 1; commitment and replay pass |

Every case has a complete 2,097,169-byte staging file and durable Copied status
at the verification rendezvous. Independent read-only backing observation proves
unchanged source/staging inode, size and digest while stopped, with no final
payload or COMMITTED.json. The actual worker is D-state in read(2) on its staging
FD at offset zero, requesting 1 MiB; the read-completed marker is absent. Local
health responds in 1.766-2.547 seconds; a contender with an ephemeral listener
refuses specifically on local ownership in 0.953-1.157 seconds. The original
coordinator/worker epoch, Copied status and local state/configuration remain intact.

After restoration each original read-only staging FD returns 1,048,576 bytes,
1,048,576 bytes, 17 bytes and EOF, at offsets 0, 1,048,576, 2,097,152 and 2,097,169.
The first pending read exits after the recorded restoration start. Actual successful
payload and manifest publication syscalls in this job's destination directories
follow EOF. All 72 traced worker synchronization calls return zero. Copy sync
occurred before attachment and is not among those calls. All four workers later
exit with traced status 9, existing supervised retirement after a confirmed
Committed receipt; no worker-death-during-verification case is claimed.

Every case preserves private source, enrollment, original local database inode
and configuration. The original staging inode becomes final, full payload hashes
and complete manifests match, and clean original-state restart/same-ID replay
returns the same committed job/manifest without changing newer producer-path data.
Source and staging client st_dev are 91/160, with local state 191. Backing tmpfs
devices are 0:141/0:142, each observed at size=65536k,nr_inodes=4096. Keeper PID
2081622, start/mount namespace/full inventory and devices remain identical across
25 server-state observations and final cleanup; independent role mounts stay ro.

The release container-restart mover case observes a changed backend network
namespace; the other three mover cases retain theirs. The VM boot ID remains
unchanged throughout all controls and cases. This is positive evidence for that
selected verification continuation across namespace change, not a repeatability,
full lease/reclaim, VM/NAS reboot or power-loss guarantee.

## Retained initial acquisition

Run verify-server-recovery-20261020T235918Z-be604a20 is FAILED, retained separately.
All four native controls passed, but an incorrect caller artifact-directory path
prevented any Rust case from starting. Cleanup completed normally without errors.
The [exact command, report, sources, native probe/logs and raw wire](RUST-NFS-VERIFY-RECOVERY-INITIAL-EVIDENCE.json)
remain preserved. The corrected run uses existing identical-source gate paths
and repeats every control. Its seventeen acquisition source snapshots exactly
match the failed run; only the command paths changed. Increment 88's initial
proc-bind setup failure remains separately retained as fixture provenance.

## Compatibility, independent audit and cleanup

- Production gate 20261020T235746Z-958b37dc: 211 target tests per debug/release profile.
- Qualification gate 20261020T235746Z-ab768da5-nfs-qualification: 212 per profile.

Both processes exit 0 without cleanup errors. Locked cargo-zigbuild GNU/glibc 2.22,
formatting/Clippy, exact target execution in pinned SLES 12 SP5, loader/library/
symbol checks and six negative ELF controls per mode pass. All 62 Rust inputs
and 42 locked packages remain unchanged; there is one shipping executable.
Live executables come from prior passing identical-source gates while fresh
checks run. The audit compares all source archive contents and exact shipping
bytes across live/fresh gates; compressed archive hashes need not match across runs.

Independent audit verifies seventeen frozen acquisition inputs, native probe/ELF,
actual FD/mount/inode/offset/read-result and publication-order evidence, sync/event
consistency, original custody/state/manifest, keeper/reader/backing/client identity,
raw RPC hashes/redecoding, all source archives and forty fresh ELF artifacts.
All 106 mover-proof corruptions and five storage-proof corruptions are rejected;
seven RPC decoder regression tests pass. Native windows retain 182 records and
service windows 11,786, including 1,689 unknown service records and decoded
10052/2 statuses. Successful post-restoration WRITEs in the decoded evidence are
small manifest writes; no payload-write or READ replay inference follows from them.

After every fixture/gate process exits, inventory captured at
2026-10-21T00:25:58.849168+00:00 confirms zero containers in both engines, original
Rust cache volumes, unchanged baseline volume metadata/network names and no owned
fixture resources remaining. Both client mounts normally unmount before removal;
the keeper is removed last, allowing Podman's local driver to release the tmpfs
mounts. No force/lazy NFS unmount, VM restart, host policy or NAS change is used.

Read [the raw acquisition](RUST-NFS-VERIFY-RECOVERY-EVIDENCE.json),
[input/audit evidence](RUST-NFS-VERIFY-RECOVERY-INPUT-EVIDENCE.json),
[production gate](RUST-SLES-EVIDENCE.json),
[qualification gate](RUST-SLES-QUALIFICATION-EVIDENCE.json) and
[step-by-step infrastructure/testing procedure](NFS-VERIFICATION-RECOVERY-LAB.md).


## Limits

Controlled retained-memory restart is not persistent disk/NAS/power qualification
or abrupt live-NFSD termination. Broader fresh-namespace/reclaim matrices, VM/NAS reboot, independent
endpoint failures, outstanding UNSTABLE data, delayed settlement, worker death and
other service phases remain separate obligations. The existing decoder retains
unknown READ compounds without attributing success/replay. Actual staging read
continuation is proven with syscall/FD/offset/count/EOF evidence and service digest
validation; earlier copy synchronization precedes attachment and is not traced.
Pinned SLES userspace shares a modern WSL2 kernel, so original-kernel/client,
vendor-maintenance, deployment/account and endurance limits remain. Rust inputs,
dependencies, API/retry/review and deadlines stay unchanged. Keep all eight gates
open, registration/repair/DOC-06 deferred and production NFS/source deletion off.
