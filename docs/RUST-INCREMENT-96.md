# Rust increment 96: coordinator death during pending manifest LINK

## Scope and changes

Four native retained-FD prerequisites precede four actual mover cases:
debug/release x NFSD restart/NFSD-quiesced same-container restart. Both source and
destination use distinct retained NFS filesystems; SQLite and ownership state use
a third, local filesystem. Kill only the coordinator while COMMITTED.part to
COMMITTED.json linkat is actually D, retain old-worker exclusion through actual
exit, inspect original remote custody and local phase evidence, then recover from
the original state. Production NFS/private-source deletion remain disabled. No
shipping Rust, dependency, API/retry/review or shutdown deadline changes.

The retained fixture adds mutually exclusive --manifest-link-death-recovery to
check-nfs-server-recovery.py and extends the existing death path with manifest
custody, unchanged published payload and independent local SQLite snapshots.
The existing coordinator-death tracer mode from increment 95 handles actual
normal-error or signal exit without inventing an unfinished call's success.
Python SQLite is fixture/auditor instrumentation only, with no service dependency.

## Measured results

Run `manifest-link-death-recovery-20261022T014422Z-4ecc4f2c` passes four native controls and all four actual mover
cases, freezing 17 exact acquisition files. Before outage,
the payload is already Published, complete one-link final without staging;
COMMITTED.part contains complete original bytes with one link, no final manifest,
and SQLite manifest_phase is 3. Actual pending linkat(265), both directory FD
paths/mount/inode IDs and exact COMMITTED.part/COMMITTED.json names are observed.
Fixture-observed health requests take 1.718–1.906 seconds
while blocked, including Podman/tool overhead; the
sampled worker is UID/GID 1000 with zero capabilities and no-new-privileges.

After coordinator exit, twelve actual-D-state local ownership samples report
OwnerUnavailable/exit 2. Service, initialization and transfer contenders using
the same protected state and an ephemeral API port all refuse specifically for
ownership. The old epoch, private source, published payload and complete manifest
staging remain unchanged. Physical flock probes are free in 0 samples;
record this separately from logical ownership and prior early-closure coverage.

| Profile | Restart | Old LINK result | Old sync count | Final manifest after old exit | Worker exit |
|---|---|---|---|---|---|
| debug | nfsd | 0 | 6 | True | code 1 |
| debug | container | 0 | 6 | True | code 1 |
| release | nfsd | 0 | 6 | True | code 1 |
| release | container | 0 | 6 | True | code 1 |

In all four cases the original worker completes the manifest LINK and six syncs
after restoration, removes staging and leaves the original one-link valid final
manifest. It then exits code 1 after coordinator-channel loss; a closed-socket
EPIPE write is retained in the external trace. SQLite still has manifest phase 3.

Restore the same backend before draining users. Confirm actual old-worker exit
before replacement; independently observe full manifest bytes/hash/inode and
unchanged payload/private source through the read-only backing reader. Successful
original-call attribution requires actual return plus successful raw LINK inside
that exact interval, not merely a later successful operation. Original file/new-
parent sync precedes staging removal; staging-directory sync follows. No successful
post-restoration WRITE is observed; complete payload/manifest bytes are retained. A killed
call without a return would remain explicitly unfinished, never fabricated.

Read-only snapshots copy only local jobs.sqlite and existing WAL after coordinator
exit, then repeat after old-worker exit. Original file hashes are checked before
and after each copy. Only copied files are opened, read-only/query-only, with no
original SQLite or unavailable NFS access by this observer. Exact compressed raw
files are retained and independently reconstructed by the verifier. In all four
cases both snapshots remain byte-identical, with exact original manifest bytes/
hash at phase 3 and payload attempt 1/Published (phase 4). A visible valid final
manifest does not fabricate a received phase-4 SQLite receipt. Consumers keep the
valid-manifest contract; no API-polling duty is added. The recorder still retries
unchanged JSON until 202 and has no post-202 delivery-monitoring duty.

Original-state recovery reaches Committed on attempt 1 with the original manifest
inode as one-link final, absent manifest staging, unchanged published payload
inode/hash and retained private source. Clean stop/restart plus same-ID replay
returns 202/job 1, preserving the producer's 'next recording' bytes and completed
manifest. New coordinator epochs retain original boot/namespace/guard identity.

The independent audit redecodes 14326 bounded service RPC records, retaining
1598 records outside the strict decoder's understood subset, protocol errors
and exact payload hashes/XIDs. Native protocol session/write-verifier changes
remain separately audited. Two 64 MiB/4096-inode tmpfs role backings are retained
by keeper PID 2687006. Source/destination backing devices are 0:189/0:190,
client devices are 0:234/0:239 and local-state stat device is 206.
Keeper identity/mounts remain stable in 25 server
observations plus cleanup, with a read-only backing reader.

## Compatibility, audit and cleanup

Production `20261022T014158Z-d251952e` passes 211 exact-target tests per profile; qualification
`20261022T014158Z-d16b39b5-nfs-qualification` passes 212 per profile. Both use locked cargo-zigbuild GNU/glibc 2.22
and pinned SLES 12 SP5 userspace. Forty Rust ELF artifacts, six negative ELF
controls per gate, 42 locked packages and all 62 unchanged Rust project inputs
are verified. Earlier passing gates used for live executables match the fresh
archives' contents and shipping executable bytes exactly.

The independent verifier rejects 167 corrupted mover/storage proofs,
including SQLite raw-file/hash/phase and visible-manifest corruption, and runs
seven RPC decoder regressions. Two invalid CLI mode combinations refuse before
provisioning. Earlier rejected fixture/observer evidence from increments 88/95
remains separately preserved and hash-verified as provenance.

The first independent audit failed because the Windows sandbox denied writes to
its default temporary directory. Its [exact code, diagnostic and unchanged raw
acquisition](RUST-NFS-MANIFEST-LINK-DEATH-RECOVERY-AUDIT-INITIAL-EVIDENCE.json)
remain preserved. Reconstruction now uses a fresh workspace scratch directory
that inherits the workspace ACL; its resolved parent is checked before access
and removal, and SQLite is closed before cleanup. The passed acquisition is
byte-identical to that initial audit input. No service behavior, proof condition,
shutdown deadline or global permission setting changed.

Final inventory at 2026-10-22T02:06:29.699272+00:00 confirms zero
containers on both engines, unchanged baseline full volume metadata/network names
and no owned fixture resources. Restore before draining, normally unmount both
NFS mounts, remove owned users/backend, keeper last, then owned role/parent volumes
and private network. No force/lazy NFS unmount, VM reset or global NAS/host/cgroup
policy change is used.

Read [raw acquisition](RUST-NFS-MANIFEST-LINK-DEATH-RECOVERY-EVIDENCE.json),
[input/audit evidence](RUST-NFS-MANIFEST-LINK-DEATH-RECOVERY-INPUT-EVIDENCE.json),
[production gate](RUST-SLES-EVIDENCE.json),
[qualification gate](RUST-SLES-QUALIFICATION-EVIDENCE.json) and the
[step-by-step lab](NFS-MANIFEST-LINK-DEATH-RECOVERY-LAB.md).

## Limits and next work

These selected same-kernel controlled restarts retain tmpfs memory. NFSD is
quiesced before container termination; this does not establish abrupt live-server,
independent NAS/VM reboot, outstanding UNSTABLE-data loss or persistent-disk/power
safety. Modern WSL2/Podman kernel and pinned SLES userspace do not qualify old
SLES kernel/NFS client, exact maintenance systemd, NetApp/Isilon, larger loads,
longer outages or other phases. Local lock release/exit never proves all delayed
remote effects settled or authorizes arbitrary redispatch/takeover. Normal file-
sync completion here does not establish blocked-sync or directory-sync recovery.

Next qualify source-claim LINK coordinator-death/original-state recovery before
HTTP 202, retaining recorder handoff rules. Keep remaining bootstrap/claim,
actual RPC-bearing synchronization, termination/deadline, remote access and
shipping deployment work open. Maintain SC-130/DOC-01–05; keep DOC-06,
registration/S3/offline repair deferred and all eight release gates open.
