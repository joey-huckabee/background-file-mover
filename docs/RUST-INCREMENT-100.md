# Rust increment 100: original-file claim synchronization discovery

## Scope and changes

SC-134 retains --original-claim-sync-discovery with --mover --distinct-filesystems.
Four native retained-FD recovery prerequisites precede four debug/release x healthy/
stopped-NFSD cases on the original-file fsync before LINK. Separate retained NFS
filesystems hold source and destination; SQLite and ownership stay local. No
shipping Rust, dependency, API/retry/review or shutdown deadline changes.
Production NFS and postcommit private-source cleanup remain disabled.

The fixture-only nfs_original_claim_sync_discovery.py uses existing claim_apply.
Attach the external I/O observer before the worker synchronizes original
current/nested/data.bin. Gate exact syscall 74 entry/exit using existing bounded
local controls, no observer network and no syscall substitution. Ptrace t/T is
artificial; reset actual entry time after entry release and record actual exit
before exit hold. Exclude both artificial holds from syscall/RPC attribution.
Keep LINK from running until the selected sync's exit is independently inspected.

## Measured results

Run `original-claim-sync-discovery-20261022T044424Z-baf067ab` passes all four native prerequisites and four actual
mover cases with eighteen frozen acquisition sources. At entry and selected exit,
the read-only backing reader proves complete original inode/hash, size 2,097,169,
one link, absent private data and absent destination recording directory. Local
ownership remains held, API state is Accepted, and the same single claim worker/
epoch is retained. No 202 permits recorder reuse while held; local health remains
responsive (2.000–2.375 seconds including fixture overhead).
Worker UID/GID 1000, zero capabilities and NoNewPrivs are recorded.

| Profile | Backend | Actual result | Selected raw records | Pairs spanning entry |
|---|---|---|---|---|
| debug | healthy | healthy_completion | 0 | 0 |
| debug | nfsd-stopped | completed_while_nfsd_stopped | 0 | 0 |
| release | healthy | healthy_completion | 0 | 0 |
| release | nfsd-stopped | completed_while_nfsd_stopped | 0 | 0 |

All four selected fsync calls return zero with 0 raw records in their
actual intervals and 0 captured pairs spanning entry. There are 0
temporal WRITE/COMMIT candidates and 0 actual blocked syncs. Both stopped-
NFSD calls complete locally before restoration. This clean original-file workload
does not establish a blocked RPC or reply-withholding boundary. Do not substitute
the native dirty-write controls for actual service synchronization evidence.

Observe all 32 fsync calls (eight per worker): original file, private data, private
parent, original parent after unlink, private data, private parent, original parent,
source .file-mover namespace. Every call returns zero. Require a successful raw
LINK request/reply inside each traced LINK syscall as positive capture calibration;
LINK and original-name unlink occur after selected exit release. Bind original
inode to independent backing custody and descriptor mount to the client view.
Backing and NFS-client device numbers remain separate views.

After restoring NFSD when needed and rechecking custody, release selected exit.
Retain the original HTTP response or transport loss and retry the identical JSON/ID
until confirmed 202/job 1/source_paths_released. Confirm original-name absence
before writing 'next recording'. The same coordinator completes attempt 1 with
original private inode/hash, complete verified destination and valid manifest.
DB inode/configuration/enrollment remain stable, newer producer bytes survive,
and normal stop/restart replay returns the same committed job and manifest.
The recorder has no post-202 polling obligation; consumers wait for the valid
completion manifest. Claim-time original-name unlink remains separate from
disabled postcommit private-source cleanup.

Independently decode 11480 bounded raw service records; retain 1166 records
outside the strict decoder subset with exact hashes/XIDs. Account all sync
intervals and captured pairs spanning entry separately. Broader or temporally
adjacent traffic is not target-specific synchronization causality.

## Compatibility, audit and cleanup

Fresh production `20261022T043950Z-74404df5` passes 211 exact-target tests per profile; fresh
qualification `20261022T043950Z-b945b597-nfs-qualification` passes 212 per profile. Both use locked cargo-zigbuild
GNU/glibc 2.22, pinned SLES 12 SP5 userspace, 42 packages and six negative ELF
controls per gate. Audit forty Rust ELF artifacts and all 62 unchanged Rust
project inputs. The live run uses the prior identical-source passing gate
artifacts; independently compare complete source archives and shipping bytes
against both fresh gates. No host-only cargo checks replace these gates.

The independent verifier rejects 141 corrupted mover/storage proofs, runs
seven decoder regressions and two pre-provisioning CLI refusal controls, and
checks native retained-FD behavior, storage continuity, actual descriptors/timing,
raw RPC decoding/calibration, custody/handoff/order, worker exit and replay.
Retain failed historical storage/audit/count attempts from increments 88/94/99.

The [initial setup failure](RUST-NFS-ORIGINAL-CLAIM-SYNC-DISCOVERY-INITIAL-EVIDENCE.json)
records a Podman SSH handshake closure during initial server inspection, before
native/mover cases or client NFS mounts. Automatic teardown reports no errors;
rootful inventory confirms no remaining containers. Preserve exact failed report
and eighteen sources, then retry unchanged acquisition code. The auditor verifies
byte-for-byte equality with the passing run. No failed report is rewritten.

Final inventory at 2026-10-22T05:05:22.353967+00:00 confirms zero
containers on both engines and unchanged baseline full volume metadata/network
names. Restore backend before draining blocked users, normally unmount NFS, remove
owned users/backend, verify/remove keeper last, then role/parent volumes/network.
No forced/lazy unmount, VM reset or global host/cgroup/NAS change is used.

Read the [step-by-step infrastructure lab](NFS-ORIGINAL-CLAIM-SYNC-DISCOVERY-LAB.md),
[raw acquisition](RUST-NFS-ORIGINAL-CLAIM-SYNC-DISCOVERY-EVIDENCE.json),
[input/audit pack](RUST-NFS-ORIGINAL-CLAIM-SYNC-DISCOVERY-INPUT-EVIDENCE.json),
[production gate](RUST-SLES-EVIDENCE.json) and
[qualification gate](RUST-SLES-QUALIFICATION-EVIDENCE.json).

## Limits and next work

This is exact original-file sync discovery, not coordinator-death, withheld reply,
or abrupt server recovery. Memory-backed storage and a modern shared kernel do
not qualify persistent disk/power loss, independent servers, NAS/VM reboot,
outstanding UNSTABLE-data loss, old SLES kernel/client or maintenance systemd,
NetApp/Isilon, 100 GB performance or concurrency/endurance. Different dirty/cache/
workload/size/outage profiles remain open. Local lock/worker exit is not proof of
remote settlement and does not authorize uncertain-effect redispatch.

Prioritize the remaining same-ID replay/source revalidation and bounded admission
behavior during a joint source/destination outage. Select further sync recovery
only when an actual pending service RPC boundary is positively demonstrated.
Maintain SC-134/DOC-01–05, defer DOC-06/registration/S3/offline repair, leave all
eight release gates open and keep production NFS/private-source cleanup disabled.
