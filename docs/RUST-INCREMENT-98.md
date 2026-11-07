# Rust increment 98: source-claim REMOVE coordinator death before HTTP 202

## Scope and changes

Retain --claim-remove-death-recovery with --mover --distinct-filesystems and
exclude other selected phases. The fixture-only nfs_claim_remove_death_recovery.py
module uses existing claim_unlink_rpc controls. No shipping Rust/dependency,
API/retry/review policy or shutdown deadline changes. Production NFS and
postcommit private-source cleanup remain disabled. Removing the old source name
during claiming is a separate custody operation.

Repeat four native retained-FD prerequisites, then four debug/release x NFSD/
NFSD-quiesced same-container mover cases. Source and destination use distinct
retained NFS filesystems; SQLite/ownership state is local on a third filesystem.
The recorder leaves submitted paths untouched until a confirmed HTTP 202 from
an identical-ID/body retry. Internal Accepted status and completed remote effects
do not independently authorize reuse or add any recorder post-202 monitoring duty.

## Measured results

Run `claim-remove-death-recovery-20261022T030922Z-e2cd734f` passes all four native prerequisites and four mover cases,
freezing 18 acquisition files. At the selected pause,
current/nested/data.bin and .file-mover/1-0/data alias the same complete original
inode/hash, each reporting two links. A successfully decoded raw LINK precedes
the pending REMOVE. The internal job remains Accepted with claim done=0 and no
transfer or manifest. No destination recording directory exists.

Quiesce NFSD, optionally terminate the quiesced container, then release the pause
into actual D-state unlinkat(263), flags zero, data.bin in the recorded original
source-parent FD/mount/inode. Sampled workers use UID/GID 1000, zero capabilities
and no-new-privileges. Health takes 1.735–2.094 seconds including Podman/tool
overhead; the original local DB/configuration identity and Accepted status remain
unchanged while the operation blocks.

Kill only the coordinator. All twelve D-state ownership samples report
OwnerUnavailable/exit 2; all three service/initialize-source/transfer-one contenders
refuse specifically for ownership using the same state and an ephemeral API port.
Record physical flock probes separately: 0 of twelve are free. The same
epoch, two-name original custody and absent delivery remain intact while blocked.
These four cases did not reproduce early physical-lock release; logical ownership
and actual worker lifetime are checked separately.

| Profile | Restart | Old REMOVE result | Observed old syncs | Private-only after old exit | Worker exit | Original HTTP status |
|---|---|---|---|---|---|---|
| debug | nfsd | 0 | 5 | True | code 1 | 503 |
| debug | container | 0 | 5 | True | code 1 | 503 |
| release | nfsd | 0 | 5 | True | code 1 | 503 |
| release | container | 0 | 5 | True | code 1 | 503 |

All four original requests returned 503 handoff_pending, retryable=true and
source_paths_released=false; logs were empty before the outage. All four old
REMOVE calls returned zero after restoration. Each worker completed five observed
syncs, retained the original inode privately with one link and exited with code 1
on its closed coordinator channel. All four first replacement-owner retries
returned 202/job 1 directly, before producer reuse. Connection loss, intermediate
replacement 503 and signal-9 retirement were not observed in these four cases.

Restore the backend before draining and retain actual old-worker exit. Decode
successful raw REMOVE replies after restoration and require a successful pair
inside the original syscall interval when it returns zero. Independently inspect
original/private inode/hash/link-count custody through the read-only backing
reader before replacement. Successful normal code-1 retirement requires the
closed-coordinator-channel EPIPE trace. A missing syscall return remains unfinished.

The external observer attaches at the REMOVE pause. It observes the old-parent
sync after unlink and remaining claim synchronization, not the earlier file/new-
parent syncs preceding the pause. Do not infer actual blocked-sync qualification
or persistent durability from those earlier code paths or successful local fsync.

Exact local jobs.sqlite/WAL snapshots after coordinator death and after old-worker
exit are byte-identical. The auditor reconstructs raw copies, opens them read-only/
query-only, and checks original job/claim identity/names, done=0, and zero transfer/
manifest rows. A completed filesystem claim can coexist with a pending local
receipt and an unacknowledged handoff. Offline Python SQLite is a fixture audit
facility, not a shipping service dependency.

Only after actual exit and independent custody observations restart original
state. Retry identical JSON/ID until confirmed 202/job 1 with source_paths_released;
any intermediate 503 must remain retryable and withhold path release. Confirm the
original source name is absent at 202 before writing 'next recording'. Require
attempt-1 commitment, original private-source inode/hash with one link, full
verified destination and valid manifest, stable DB/configuration/enrollment
identities and intact newer producer bytes. Clean stop/restart and same-ID replay
return 202/job 1 without reclaiming the replacement or changing the manifest.

Audit 11976 bounded raw service RPC records, retaining 1248 outside the
strict decoder subset, exact payload hashes/XIDs and protocol errors. Verify
preceding LINK separately from resumed REMOVE and retain native session/write-
verifier changes, distinct keeper/backing/client/local devices, read-only reader
and storage continuity through cleanup. Keeper PID 2825510 retains source backing
0:190 and destination backing 0:189 across 25 server observations plus cleanup.
Client NFS devices 0:234/0:239 and local-state stat device 206 remain distinct.
Each role backing is a bounded 64 MiB/4096-inode tmpfs with a read-only reader.

## Compatibility, failures, audit and cleanup

Fresh production `20261022T030533Z-8c88590f` passes 211 exact-target tests per profile;
qualification `20261022T030535Z-240bc029-nfs-qualification` passes 212 per profile. Both use locked cargo-zigbuild
GNU/glibc 2.22 and pinned SLES 12 SP5 userspace. Independently audit forty Rust ELF
artifacts, six negative ELF controls per gate, 42 locked packages and 62 unchanged
Rust project inputs. Complete source archives and shipping bytes match the earlier
passing gates used for the live executables.

The independent verifier rejects 171 corrupted mover/storage proofs and
runs seven RPC decoder regressions. Two incompatible CLI controls refuse before
provisioning. Reconstruct copied raw DB/WAL in fresh workspace-contained scratch,
inherit workspace ACLs, verify resolved paths and close SQLite before removing
only the owned directory.

The first attempt stopped during initial server inspection because its Podman SSH
connection was forcibly closed, before NFS mounts, native controls or Rust cases.
Preserve its exact failed report and eighteen acquisition sources in
[initial evidence](RUST-NFS-CLAIM-REMOVE-DEATH-RECOVERY-INITIAL-EVIDENCE.json).
Cleanup reported no errors; rootful inventory confirmed no remaining containers,
only the two original cache volumes and original podman network before unchanged
retry. Do not infer the connection failure's underlying cause.

The first independent audit rejected an incorrect cross-view device comparison:
read-only backing st_dev 190 and NFS-client st_dev 234 are separate namespaces.
Preserve the [rejected auditor, diagnostic and exact passed acquisition](RUST-NFS-CLAIM-REMOVE-DEATH-RECOVERY-AUDIT-INITIAL-EVIDENCE.json).
The corrected auditor validates each device against its own mount/storage view,
then binds this controlled fixture's inode/hash to the local stored intent. This
is not a general rule that arbitrary NAS inode namespaces must match. No raw
acquisition or Rust code changed. Historical failed attempts from increments
88/95/96 remain independently checked as provenance.

Final inventory at 2026-10-22T03:32:05.498579+00:00 confirms zero
containers on both engines and baseline full volume metadata/network names
unchanged. Restore before drain; normally unmount both NFS mounts, remove owned
users/backend, keeper last, then owned volumes/network. No force/lazy NFS unmount,
VM reset or global NAS/host/cgroup policy change is used.

Read [raw acquisition](RUST-NFS-CLAIM-REMOVE-DEATH-RECOVERY-EVIDENCE.json),
[input/audit evidence](RUST-NFS-CLAIM-REMOVE-DEATH-RECOVERY-INPUT-EVIDENCE.json),
[production gate](RUST-SLES-EVIDENCE.json),
[qualification gate](RUST-SLES-QUALIFICATION-EVIDENCE.json) and the
[step-by-step lab](NFS-CLAIM-REMOVE-DEATH-RECOVERY-LAB.md).

## Limits and next work

These finite controlled restarts retain tmpfs memory and the modern shared kernel;
container termination follows NFSD quiescence. They do not qualify abrupt live-
server/NAS/VM reboot, independent servers, persistent storage/power loss, outstanding
UNSTABLE-data loss, old SLES kernel/NFS client or maintenance systemd, NetApp/Isilon,
100 GB throughput, concurrency/endurance, longer outages or other sync/termination
phases. Local lock/exit observations are not globally settled delayed-effect proof
and cannot authorize arbitrary uncertain-effect redispatch or takeover.

Next identify positively observed source-claim synchronization RPC boundaries
before selecting further sync/death/recovery cases. Keep all eight release gates
open, maintain SC-132/DOC-01–05, defer DOC-06/registration/S3/offline repair, and keep
production NFS/postcommit private-source cleanup disabled.
