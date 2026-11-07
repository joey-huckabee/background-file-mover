# Rust increment 97: source-claim LINK coordinator death before HTTP 202

## Scope and changes

Repeat four native retained-FD controls, then four actual debug/release x NFSD/
NFSD-quiesced same-container source-claim LINK cases. Source and destination have
distinct retained NFS filesystems; SQLite/ownership state is local on a third.
Keep production NFS and postcommit private-source cleanup disabled. No shipping
Rust/dependency, API/retry/review policy or shutdown deadline changes.

The retained --claim-link-death-recovery mode dispatches to the fixture-only
nfs_claim_death_recovery.py module using existing claim_link_rpc and external I/O
observer controls. Capture the original request's non-202/connection-loss outcome,
original source/private namespace, local pending claim and actual worker lifetime.
Only after replacement's confirmed identical-ID 202 may the test recorder recreate
the source path. Offline Python SQLite inspects copied fixture evidence only;
it introduces no service dependency.

## Measured results

Run `claim-link-death-recovery-20261022T021745Z-83f504a6` passes four native prerequisites and all four mover cases,
freezing 18 exact acquisition files. Before the selected LINK,
the original current/nested/data.bin is complete, one-link and unchanged; protected
.file-mover/1-0/data is absent. The internal job is Accepted, with one planned claim
done=0 and no transfer or manifest. That local intake state does not authorize
recorder reuse; the generator still needs a confirmed HTTP 202.

After stopping the backend, release the qualification pause into actual D-state
linkat(265), record both source directory FD paths/mount/inode IDs and exact
data.bin/data names. Sampled workers use UID/GID 1000, zero capabilities and
no-new-privileges. Fixture-observed health requests take 1.735–2.000
seconds including Podman/tool overhead; Accepted job/local-state observations
remain unchanged while the source operation blocks.

Kill only the coordinator PID. Twelve actual-D-state local ownership samples
report OwnerUnavailable/exit 2, with 0 free physical flock probes recorded
separately from logical ownership. Service, initialization and transfer contenders
using the same protected state and an ephemeral API port all refuse specifically
for ownership. Source names/bytes, epoch and absence of a destination recording
directory remain unchanged while the orphan is blocked. These cases did not
reproduce early physical-lock release; that separate condition remains covered
by [increment 47](RUST-INCREMENT-47.md).

| Profile | Restart | Old LINK result | Old sync count | Private-only after old exit | Worker exit | Original HTTP status |
|---|---|---|---|---|---|---|
| debug | nfsd | 0 | 7 | True | code 1 | 503 |
| debug | container | 0 | 7 | True | code 1 | 503 |
| release | nfsd | 0 | 7 | True | code 1 | 503 |
| release | container | 0 | 7 | True | code 1 | 503 |

All four original requests returned HTTP 503 with handoff_pending, retryable=true
and source_paths_released=false. Response logs were empty before the outage.
Connection loss is an allowed fixture outcome but was not observed in these four
cases. The fixture makes no producer modification before a confirmed retry 202.
A killed worker without a syscall return remains unfinished; original-call
success requires an actual return plus a successful raw LINK inside its exact
interval. Where original-name removal completes, verify private file/new-parent
sync before unlink, original-parent sync afterward and remaining claim syncs.

After restoration, all four old workers completed LINK and seven successful
synchronizations, removed the original source name and retained the complete
original inode privately. Each exited with code 1 after its coordinator channel
closed; the trace records EPIPE. The read-only backing reader independently
confirmed private-only custody before replacement. Destination recording data
remained absent; no transfer/manifest was inferred from a pending claim receipt.

Exact local jobs.sqlite/WAL copies after coordinator death and after actual old-
worker exit remain byte-identical. The independent auditor reconstructs both raw
files and requires the one original job/claim, exact relative names/source identity,
claim done=0 and zero transfer/manifest rows. A completed filesystem claim is
separate from a received local done=1 receipt and an HTTP acknowledgement.

Restart the original state after those observations. In all four cases, the first
identical-ID/body retry returned 202/job 1 with source_paths_released=true. No
intermediate replacement-owner 503 was observed. The original source name was
absent at 202; only then did the recorder recreate it with 'next recording'.
Attempt-1 delivery commits with the original
private-source inode/hash, verified complete destination/manifest, original DB/
config/enrollment identities and preserved newer producer bytes. Clean stop/
restart and same-ID replay return 202/job 1 without recopying or re-claiming the
producer's replacement. Recorder post-202 monitoring and consumer rules stay unchanged.

The auditor validates 11986 bounded service RPC records, retaining 1260
records outside its strict decoder subset, payload hashes/XIDs and protocol
errors. Native session/write-verifier changes remain independently audited.
Keeper PID 2755486 retains two 64 MiB/4096-inode role tmpfs
backings: source device 0:189 and destination device 0:190, across 25 server
observations plus cleanup. Client NFS devices 0:234/0:239 and local-state stat
device 206 remain distinct, with a read-only backing reader.

## Compatibility, audit and cleanup

Fresh production `20261022T021442Z-e33c1bbd` passes 211 exact-target tests per profile; qualification
`20261022T021443Z-4a54ee5d-nfs-qualification` passes 212 per profile. Both use locked cargo-zigbuild GNU/glibc 2.22,
pinned SLES 12 SP5 userspace, forty Rust ELF artifacts total, six negative ELF
controls per gate and 42 locked packages. All 62 Rust project inputs and shipping
bytes match the earlier passing gates supplying the live executables.

The independent verifier rejects 159 corrupted mover/storage proofs and
runs seven RPC decoder regressions. Two invalid CLI combinations refuse before
provisioning. Historical failed fixture/observer/auditor attempts from increments
88/95/96 remain preserved as provenance; workspace-contained raw-DB reconstruction
inherits the workspace ACL, validates resolved paths and closes SQLite before
owned scratch removal.

Inventory at 2026-10-22T02:39:44.560849+00:00 confirms zero containers
on both engines and unchanged baseline full volume metadata/network names.
Restore before draining, normally unmount both NFS mounts, remove owned users/
backend, keeper last, then owned volumes/network. No force/lazy NFS unmount,
VM reset or global NAS/host/cgroup policy change is used.

Read [raw acquisition](RUST-NFS-CLAIM-LINK-DEATH-RECOVERY-EVIDENCE.json),
[input/audit evidence](RUST-NFS-CLAIM-LINK-DEATH-RECOVERY-INPUT-EVIDENCE.json),
[production gate](RUST-SLES-EVIDENCE.json),
[qualification gate](RUST-SLES-QUALIFICATION-EVIDENCE.json) and the
[step-by-step lab](NFS-CLAIM-LINK-DEATH-RECOVERY-LAB.md).

## Limits and next work

Source-name removal during protected claiming is separate from postcommit private-
source deletion, which remains off. A durable submitted job, completed remote
claim, local process exit or free physical lock does not permit premature producer
reuse or prove globally settled delayed effects. Do not authorize arbitrary
redispatch/takeover from these finite observations.

This same-kernel controlled restart retains tmpfs memory and quiesces NFSD before
container termination. It does not qualify abrupt live-server/NAS/VM reboot,
independent servers, persistent disk/power loss, outstanding UNSTABLE-data loss,
old SLES kernel/NFS client or exact maintenance systemd, NetApp/Isilon, larger/
concurrent/endurance workloads, longer outages, pending claim REMOVE or other
synchronization/termination phases. Native synchronization is not an unobserved
service blocked-sync recovery. All eight release gates remain open.

Next qualify source-claim REMOVE coordinator-death/original-state recovery before
HTTP 202. Preserve the handoff contract, actual-exit exclusion and private custody.
Maintain SC-131/DOC-01–05; keep DOC-06, registration/S3/offline repair deferred and
production NFS/private-source cleanup disabled.
