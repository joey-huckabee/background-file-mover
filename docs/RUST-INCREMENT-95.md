# Rust increment 95: coordinator death during pending payload LINK

## Scope and changes

Repeat four native retained-FD prerequisites, then four actual debug/release x
NFSD/quiesced-container recoveries with both source and destination on separate
retained NFS filesystems and local SQLite/ownership state on a third filesystem.
Kill only the coordinator during actual D-state payload linkat, preserve orphan
exclusion through actual worker exit, independently inspect retained remote
namespace/custody, then recover the original state. Production NFS and private-
source deletion remain disabled. No shipping Rust/dependency, API/retry/review
policy or shutdown deadline changes.

The fixture retains --payload-link-death-recovery as a mutually exclusive mode
of check-nfs-server-recovery.py. Existing live-coordinator modes keep their path.
The bounded external I/O tracer adds an explicit coordinator-death exit mode:
it retains the actual syscall outcome and permits fatal signal or normal error
exit without requiring syncs that a killed worker never executed. A worker that
finishes the pending operation is required to retain its actual sync results.
Existing zero/supervised-delivery modes retain their previous sync/exit requirements. This is observer interpretation,
not syscall substitution or new service cancellation behavior.

## Measured results

Run `payload-link-death-recovery-20261021T235453Z-9a8b079a` passes four native prerequisites and all four actual mover
cases. Raw acquisition freezes 17 exact source files. Every
case proves linkat(265), expected old/new directory FDs, exact 1.part/data.bin names
and actual D-state before death. Health responds in 1.719–1.906
seconds while the worker is blocked. The sampled worker is UID/GID 1000 with no
capabilities and no-new-privileges.

After the coordinator exits, each case has three actual-D-state ownership
samples reporting OwnerUnavailable/exit 2, plus specifically refused service,
source-initialization and transfer contenders using identical state and an
ephemeral API port. Epoch and private source/staging/absent-publication observations
remain unchanged. Across twelve samples, 0 physical flock probes are free;
logical ownership remains held in every sample. These are separate observations.

In all four cases the original orphan completes LINK and six successful syncs
after restoration, removes staging and retains the complete one-link final file.
It then exits code 1 after losing the coordinator channel; the external trace
records a closed-socket EPIPE write. Replacement reconciles the original
PublishIntent from the retained inode and completes the job without recopying it.
These cases retain the physical flock while blocked; they do not reproduce the
early lock-closure cases qualified separately in [increment 47](RUST-INCREMENT-47.md).

| Profile | Restart | Old link result | Old return observed | Final present after old exit | Free physical-lock samples | Worker exit |
|---|---|---|---|---|---|---|
| debug | nfsd | 0 | True | True | 0 | code 1 |
| debug | container | 0 | True | True | 0 | code 1 |
| release | nfsd | 0 | True | True | 0 | code 1 |
| release | container | 0 | True | True | 0 | code 1 |

Restore the same backend before draining users, confirm
actual old-worker exit, record independent read-only backing namespace/content,
then start replacement using the original database/configuration/enrollment.
Successful post-restoration raw LINK records and final original-inode custody
are audited separately from attribution to the original pending call. A completed
original call also requires a successful raw LINK inside its exact syscall
interval; staging removal requires original file/new-parent sync before unlink
and staging-directory sync afterward. Preserve these measured outcomes; no local ownership observation proves remote settlement.

All four original-state recoveries reach Committed on attempt 1, retaining the
original staging inode as the one-link final payload, complete source bytes and
original private-source inode. Completion manifests validate, staging is absent,
and clean stop/restart plus identical-ID replay returns 202/job 1 without changing
the producer's 'next recording' bytes or the completed manifest. Replacement
epochs use new coordinator groups with unchanged boot/namespace/guard identity.

The service captures 13024 bounded raw RPC records, including 1556 records
outside the strict decoder's understood subset. The verifier validates every
payload hash/XID, redecodes understood records and successful post-restoration
payload LINK responses, retaining errors/unknowns rather than ignoring them.
Native session/write-verifier changes remain independently audited. The separate
keeper retains both bounded 64 MiB/4096-inode tmpfs backings across same-server
restart. Backing devices are 0:137/0:138, client devices 0:208/0:213 and local
state stat device 172. Keeper PID 2630619 and its mounts remain unchanged in
25 server observations plus cleanup; the backing reader remains read-only.

## Compatibility, audit and cleanup

Fresh production `20261021T234105Z-26f8c073` passes 211 exact-target tests per profile; qualification
`20261021T234105Z-c04cf59a-nfs-qualification` passes 212 per profile. Both use locked cargo-zigbuild GNU/glibc 2.22 and
pinned SLES 12 SP5 userspace, 42 locked packages, six ELF negative controls and
forty audited Rust artifacts total. All 62 Rust project inputs and shipping
executable bytes match the earlier passing gates used by the live fixture.
The independent verifier rejects 139 corrupted mover/storage proofs and
runs seven RPC decoder regressions. Two invalid mode-combination CLI controls
also refuse before provisioning. No host-only Rust test is substituted.

Inventory at 2026-10-22T00:14:09.605339+00:00 confirms both engines
have zero containers and unchanged baseline full volume metadata/network names.
Both NFS mounts normally unmount before owned user/backend removal; keeper is
removed last, then bounded role volumes, parent volume and private network.
No force/lazy unmount, VM reset, global host/cgroup or NAS policy change is used.
The initial acquisition `payload-link-death-recovery-20261021T234223Z-d472a3a7`
remains failed in the [retained initial evidence](RUST-NFS-PAYLOAD-LINK-DEATH-RECOVERY-INITIAL-EVIDENCE.json),
with all 31 files, frozen sources, raw RPCs and external trace. Its first actual
orphan retained ownership, completed LINK and six syncs after restoration, then
exited code 1. The observer had wrongly required signal exit. Preserve that
rejection; the corrected explicit observer mode permits normal error exit and
independent custody checks also permit final-only publication. No production
safety policy was weakened and no shipping code changed. Earlier failed
retained-storage setup evidence remains preserved separately.

Read [raw acquisition](RUST-NFS-PAYLOAD-LINK-DEATH-RECOVERY-EVIDENCE.json),
[input/audit evidence](RUST-NFS-PAYLOAD-LINK-DEATH-RECOVERY-INPUT-EVIDENCE.json),
[production gate](RUST-SLES-EVIDENCE.json),
[qualification gate](RUST-SLES-QUALIFICATION-EVIDENCE.json) and the
[step-by-step lab](NFS-PAYLOAD-LINK-DEATH-RECOVERY-LAB.md).

## Limits and next work

These are finite same-kernel controlled recovery observations, with NFSD quiesced
before container SIGKILL, storage memory deliberately retained and no independent
server/NAS/persistent disk reboot. Worker exit and an observed absent final name
do not prove globally settled delayed effects or authorize arbitrary redispatch.
Do not infer SLES kernel/NFS client, exact maintenance systemd, NetApp/Isilon,
power-loss durability, larger loads/outages, other phases or terminating-worker
coverage. A successful raw LINK after restoration alone is not proof that the old worker
returned from its original call; require the independently audited exact interval
and actual return. Old workers may complete an assigned effect before detecting
coordinator loss on the next channel operation.

Next qualify the equivalent manifest-LINK coordinator-death/original-state
recovery cases. Keep actual RPC-bearing sync discovery, bootstrap/claim and other
worker/deadline/deployment boundaries open. Maintain SC-129/DOC-01–05, defer DOC-06,
registration/S3/offline repair and keep all eight release gates open.
