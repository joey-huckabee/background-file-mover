# Rust increment 99: source-claim synchronization discovery before HTTP 202

## Scope and changes

Retain --claim-sync-discovery with --mover --distinct-filesystems, excluding other
selected phases. Eight debug/release x private-file/private-parent fsync x healthy/
stopped-NFSD cases follow four native retained-FD recovery prerequisites. Source
and destination use separate retained NFS filesystems; SQLite/ownership stay local.
Production NFS and postcommit private-source cleanup remain disabled. No shipping
Rust/dependency, API/retry/review policy or shutdown deadline changes.

The fixture-only nfs_claim_sync_discovery.py starts at existing claim_link_rpc.
After successful LINK, external nfs_io_trace.py gates the exact first fsync on
source .file-mover/1-0/data or its parent .file-mover/1-0. The observer now admits
these fixture source paths as well as its existing destination paths. It uses
bounded local entry/exit rendezvous, no network and no syscall substitution.
Ptrace t/T is an artificial stop. Reset syscall entry time after entry release;
record actual exit before the exit hold. Both artificial holds are excluded from
actual syscall/RPC attribution. Original-file sync before LINK is outside this
attachment; other calls are observed but not independently fault-selected.

## Measured results

Run `claim-sync-discovery-20261022T040936Z-6ea91cfe` passes four native controls and all eight mover cases,
freezing 18 acquisition files. At entry, original
current/nested/data.bin and private data alias the same complete original inode/
hash, each with two links. The API remains Accepted, destination recording data
is absent, local ownership is held, and there is one assigned claim worker.
No HTTP 202 permits producer reuse while the selected sync is held. Same-worker/
epoch status, UID/GID 1000, zero capabilities and NoNewPrivs are retained.

| Profile | Target | Backend | Actual outcome | Selected raw records | Pairs spanning entry |
|---|---|---|---|---|---|
| debug | file | healthy | healthy_completion | 0 | 0 |
| debug | file | nfsd-stopped | completed_while_nfsd_stopped | 0 | 0 |
| debug | directory | healthy | healthy_completion | 0 | 0 |
| debug | directory | nfsd-stopped | completed_while_nfsd_stopped | 0 | 0 |
| release | file | healthy | healthy_completion | 0 | 0 |
| release | file | nfsd-stopped | completed_while_nfsd_stopped | 0 | 0 |
| release | directory | healthy | healthy_completion | 0 | 0 |
| release | directory | nfsd-stopped | completed_while_nfsd_stopped | 0 | 0 |

Across the eight selected intervals: 0 raw RPC records, 0 captured
request/reply pairs spanning entry, 0 decoded temporal WRITE/COMMIT
candidates and 0 actual blocked syncs. Inspect per-case evidence rather
than interpreting artificial holds as NFS blockage. A temporal candidate is not
proof of target causality or reply-withholding capability. If stopped NFSD permits
successful local completion, that observation does not qualify blocked-sync
recovery, power-loss durability or every other workload/cache.

The eight original apply workers complete 56 observed fsync calls in total,
seven per case: private data, private parent, original parent after unlink,
private data, private parent, original parent and source .file-mover namespace.
All 56 observed syncs returned zero, with no raw interval records or captured
pairs spanning entry. Each of the eight traced original LINK calls contains one
successful raw LINK pair, establishing the positive capture control. LINK precedes
the selected hold; original-name unlink occurs only after exit release. The file inode is bound
to independent backing custody; the directory inode is bound to the actual LINK
parent descriptor. Backing and client device numbers stay in their own views.

After restoration if needed, complete selected fsync and recheck both aliases
before exit release. Preserve original HTTP response/transport outcome and retry
identical JSON/ID until confirmed 202/job 1 with source_paths_released. Only then
confirm source-name absence and write 'next recording'. The same coordinator
commits attempt 1 with original private inode/hash, complete destination/valid
manifest, stable DB inode/configuration/enrollment and intact newer producer bytes.
Normal stop/restart replay returns 202 for the same committed job and manifest.
No recorder post-202 polling or consumer API-polling duty is added. Source-name
unlink during claiming remains separate from disabled private-source cleanup.

Fixture-observed health takes 1.750–2.203 seconds including
Podman/tool overhead. Independently decode 22954 bounded service RPC records;
retain 2341 outside the strict decoder subset with exact payload hashes/XIDs.
Account all observed sync intervals and captured pairs spanning entry separately;
unknown or broader activity does not become positive sync attribution.

Keeper PID 2949638 retains source backing 0:136 and destination backing 0:137
across 33 server observations plus cleanup. Client devices 0:182/0:187 and local
state stay distinct. Two 64 MiB/4096-inode role tmpfs backings and a
read-only backing reader preserve custody across the controlled native restarts.

## Compatibility, independent audit and cleanup

Production `20261022T034051Z-a7d5fba9` passes 211 exact-target tests per profile; qualification
`20261022T034052Z-297b65c8-nfs-qualification` passes 212 per profile. Both use locked cargo-zigbuild GNU/glibc 2.22,
pinned SLES 12 SP5 userspace, six negative ELF controls per gate and 42 locked
packages. Verify all forty Rust ELF artifacts and all 62 unchanged Rust project
inputs. The final rerun uses these same fresh gates for its live executables;
complete archives and shipping bytes match the recorded artifacts. No host-only
cargo testing is substituted for these required checks.

The independent verifier rejects 277 corrupted mover/storage proofs, runs
seven RPC decoder regressions and two CLI refusal controls before provisioning.
It checks raw RPC redecoding/intervals, actual descriptors and namespace ordering,
custody, no premature 202/reuse, worker exit/replay, exact Rust inputs/ELFs and
final inventory. Historical failed storage/audit attempts from increments 88/94
remain independently retained as provenance.

The [initial acquisition](RUST-NFS-CLAIM-SYNC-DISCOVERY-INITIAL-EVIDENCE.json)
completed all four native controls and eight mover cases, but the shared harness
still expected four cases for this new mode and failed its final assertion. Normal
cleanup succeeded. Retain exact failed report, eighteen acquisition sources and
zero-container post-run inventory. Correct only that shared count expression to
admit eight cases for --claim-sync-discovery, then repeat the complete native/mover
matrix using the fresh passing SLES artifacts. The independent auditor verifies
the exact count-only source delta and both cleanup inventories. No runtime Rust,
NFS behavior, shutdown deadline or raw acquisition was changed to hide the failure.

Final inventory at 2026-10-22T04:34:28.320541+00:00 confirms zero
containers on both engines and unchanged baseline full volume metadata/network
names. Restore before draining users; normally unmount both NFS mounts, remove
owned users/backend, keeper last, then owned volumes/network. No forced/lazy
NFS unmount, VM reset or global host/cgroup/NAS policy change is used.

Read [raw acquisition](RUST-NFS-CLAIM-SYNC-DISCOVERY-EVIDENCE.json),
[input/audit evidence](RUST-NFS-CLAIM-SYNC-DISCOVERY-INPUT-EVIDENCE.json),
[production gate](RUST-SLES-EVIDENCE.json),
[qualification gate](RUST-SLES-QUALIFICATION-EVIDENCE.json) and the
[step-by-step infrastructure lab](NFS-CLAIM-SYNC-DISCOVERY-LAB.md).

## Limits and next work

This is exact sync discovery, not coordinator-death, reply-withholding or abrupt
server recovery. Native dirty-write controls do not qualify these actual service
sync boundaries. Memory-backed storage and a modern shared kernel cannot qualify
NAS/VM reboot, independent servers, persistent disk/power loss, outstanding
UNSTABLE-data loss, old SLES kernel/client or maintenance systemd, NetApp/Isilon,
100 GB throughput or concurrency/endurance. Other source syncs and fault-selected
cache/workload/size/outage profiles remain open. Local ownership/exit is not
remote-settlement proof and cannot authorize arbitrary uncertain-effect redispatch.

Next measure original-file sync before LINK and remaining workload/cache RPC
boundaries before selecting further synchronization recovery cases. Maintain
SC-133/DOC-01–05, defer DOC-06/registration/S3/offline repair, leave all eight release
gates open, and keep production NFS/postcommit private-source cleanup disabled.
