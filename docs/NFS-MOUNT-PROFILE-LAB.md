# NFS mount-profile lab: procedure and limits

Without gate arguments this lab validates the [candidate mount contract](NFS-MOUNT-PROFILE.md)
and its read-only Python decision model, executing no Rust. The optional supervised
Rust extension is described below. Neither mode enables production NFS or deletes
claimed source. See [increment 68](RUST-INCREMENT-68.md) for
actual run IDs, failed assumptions and fresh SLES compatibility results.

## Infrastructure

Use the existing approved Podman WSL2 VM and rootful connection
`podman-machine-default-root`. The script creates one private internal network,
one named export volume, one privileged kernel-NFS server and one pinned SLES
12 SP5 client. No host ports are published and no host NAS/mount is touched.
The NFS/NFSD modules must already be available in the VM. No new bootstrap,
package installation, kernel change or systemd unit is required for this lab.

The cached server image is `localhost/background-file-mover-e2-nfs`; its source
is [Nfs.Containerfile](../experiments/e2-rustix/Nfs.Containerfile) and
[nfs-server.sh](../experiments/e2-rustix/nfs-server.sh). Image ID and actual
nfs-common/nfs-kernel-server/rpcbind package versions are retained per run.
The client and builder image digests/toolchain are pinned in
[rust-platform.json](../scripts/rust-platform.json). Keep those digests; a rebuilt
server resolving different packages requires newly recorded evidence.

The server entrypoint provisions `/exports` as the NFSv4 pseudo-root. The runner
adds `/exports/profile-source` and `/exports/profile-destination`, separate
16 MiB tmpfs devices exported rw/sync/root_squash with fsids 68/69. These child
exports demonstrate ordinary UID/GID 1000 read/write with root squashing. The
pseudo-root entrypoint remains the historical permissive fixture, confined to the
private network; no host/NAS export policy is inferred from it.

The client drops all capabilities except SYS_ADMIN for mount setup and has
NoNewPrivs. The runner's root shell mounts/unmounts only its private paths.
Read/write controls run as UID/GID 1000, mode 0600 under umask 077. No Rust
executable, Python runtime or extra package is installed into the SLES image.
Python on the Windows host evaluates text returned by `cat /proc/self/mountinfo`.

## Reproduce step by step

1. From the repository root on Windows, verify the active branch is
   `feature/rust-transfer-coordinator` and inspect the engine inventory:

   ```powershell
   git status --short --branch
   podman --connection podman-machine-default-root ps -a
   podman --connection podman-machine-default-root image inspect localhost/background-file-mover-e2-nfs
   ```

   Stop if unrelated running fixtures would conflict with the lab. Do not remove
   another run's resources. If modules/images are missing, follow the existing
   [fixture setup](NFS-TEST-FIXTURE.md); do not silently bootstrap or replace pins.

2. Run the required Rust compatibility gates (the profile lab is not a substitute):

   ```powershell
   python scripts/check-rust-sles.py
   python scripts/check-rust-sles.py --qualification
   ```

   Both reports must pass and have no cleanup error. These use cargo-zigbuild,
   the x86_64 GNU/glibc 2.22 target, ELF/interpreter/library audits and actual
   debug/release target tests inside pinned SLES userspace. They do not run on an
   old SLES kernel. No host-only cargo command is acceptable as replacement.

3. Run the mount lab:

   ```powershell
   python scripts/check-nfs-mount-profile.py
   ```

   Record the printed `rust/validation/mount-profile-<timestamp>-<id>` path.
   Setup waits for NFS_READY and records the image, packages, export policy,
   shared kernel, namespace, client security and actual glibc 2.22.

4. Inspect the raw report, not just the process exit code:

   ```powershell
   Get-Content rust/validation/<printed-run>/report.json -Raw
   ```

   Require PASSED, no cleanup errors and passed entries in `checks`. Every entry
   identifies **live inventory**, **synthetic inventory mutation**, or **declaration
   negative control**, and includes its exact inventory/declaration/result.
   `sources` contains SHA-256 and Base64 exact driver/model bytes for replay.
   Inspect the individual cases as well as the totals; a model match is explicitly
   `PROFILE_MATCH_ONLY`, production_authorized=false, deletion_authorized=false.

5. Verify the following bounded cases:

   - N/N, B/B and both mixed endpoint combinations; stable same-namespace pins;
     mode/UID/size/hash controls; separate export devices and disjoint roots on
     one share. Mixed matches are observation capability, not shipping support.
   - Actual soft, read-only and nocto mounts on each endpoint; actual absent
     mounts, nested source/destination/state mounts, subtree bind alias and NFS
     state. Refusals are decisions of the model, not current mover HTTP responses.
   - Remount observations and a deliberate change of effective source timeo
     from 10 to 20; the changed pin must refuse. An identical pin after a
     same-options remount is allowed and explicitly proves no continuity claim.
   - Synthetic v3/v4.2/UDP/security/locking/cache/unknown/duplicate/connection
     controls and malformed/oversized/escaped/prefix-collision inventories.
     These do not claim actual mounts of those unsupported variants succeeded.
   - Server NFSD threads set to zero while local mount inventory remains readable
     and matching in under five seconds. There is **no NFS path operation while
     the server is stopped**. Restart NFSD, wait through fixture grace, verify
     original probe hashes before teardown. This is not a server-recovery test
     for the mover or pending operations.

6. Cleanup must normally unmount every recorded client mount in reverse order
   before stopping NFSD/exportfs and removing containers, volume and network.
   The runner records cleanup errors and leaves resource identities for recovery
   if normal unmount fails. It never uses lazy/forced unmount. Do not delete a
   volume or network to disguise a failed cleanup; restore the owned server first.

   ```powershell
   podman --connection podman-machine-default-root ps -a
   podman --connection podman-machine-default-root volume ls
   podman --connection podman-machine-default-root network ls
   ```

   The preexisting toolchain cache volumes/default network are not lab residue.

## Evidence interpretation

The initial run is preserved as
[failed remount assumption](RUST-NFS-MOUNT-PROFILE-INITIAL-EVIDENCE.json): the
kernel reused IDs and all selected observations matched after remount. Cleanup
succeeded. The corrected runner retains matching-remount observations and tests
refusal only when an actual selected option changes. Do not relabel the initial
failure as passing or claim the model detects every replacement mount.

The lab establishes only the declared model decisions for recorded snapshots.
It does not close snapshot-to-use races, validate symlinks/real root descriptors,
prove mount continuity, authenticate servers, test old kernels or real NAS
firmware, qualify mover buffered delivery/lost-sync recovery, test persistence
of overlay/tmpfs state, or prove physical-media/power durability. Server export
sync is known only because this disposable server is controlled. Real client
mountinfo cannot attest a NAS's export/backing-storage policy.

Service integration and the buffered worker fault matrix remain open under
FR-03/05 and MP-09–12. Earlier noac workers and buffered OS-only WRITE controls
retain their original scope. Keep production NFS and source deletion disabled;
see [testing limitations](TESTING-LIMITATIONS.md).

## Supervised Rust authorization extension

Increment 69 adds real service checks after the independent model checks and
server restoration. Build/test both final source configurations first:

```powershell
python scripts/check-rust-sles.py
python scripts/check-rust-sles.py --qualification
python scripts/check-nfs-mount-profile.py --production-gate rust/validation/<passing-production-run> --qualification-gate rust/validation/<passing-qualification-run>
```

The extension rejects stale/failed gates, waits at most 180 seconds for a supplied
active gate's final report, and executes no Rust before both reports pass. It verifies
every current archived Rust input, then checks the exact service ELF hashes before copying them into the
same pinned SLES client. It installs no Python/package in that image. The driver
runs the service and HTTP probe shell as UID/GID 1000; only its private mount setup
uses client SYS_ADMIN. Database/config/rendezvous files remain on client-local
storage under a private /tmp/mount-auth directory. Source and destination private
roots remain under their separate root-squashed child exports.

For each debug/release build and B/B or N/N layout:

1. Mount the explicit profile and provision fresh protected endpoint markers and
   the coordinator lock with the same nfs_mount declaration used in configuration.
   No prior enrollment is upgraded. Record actual inventory and source identity.
2. Require initialization refusal before SQLite creation for wrong source address,
   absent declaration, incompatible cache profile, absent declared mountpoint and
   the production build with an otherwise valid NFS declaration. Record errors
   and exits. These are real program decisions, distinct from synthetic inventories.
3. Initialize with the qualification build, then start the service and wait for
   successful health. Add unrelated nested tmpfs mounts inside each private root.
   For these fixed fixture-only control paths, the UID-1000 setup helper temporarily
   changes the label/approved-root ancestors from mode 0700 to 0701 so root-squashed
   setup can look up the empty mountpoint. It restores 0700 in a finally block
   before any service request; no file listing/write permission is granted and
   the private .file-mover and payload folders remain 0700. Unmount uses the same
   reversible traversal gate. No client capability is added.
   Submit the recording: require recording_blocked/409, paths not released and
   original source inode/hash intact. Remove only the owned source nested mount.
4. Retry the same submission ID: require job 1/202 and confirmed source custody.
   Only now reuse the original producer filename. Keep the destination nested
   mount until the worker reports destination_binding_requires_review; no manifest
   may exist. The source and original state remain retained.
5. Remove the owned destination nested mount, obtain the current review epoch and
   invoke the existing audited resume endpoint. Require committed manifest,
   destination hash, original claimed source inode/hash and attempt one. This does
   not introduce an automatic review bypass or change retry classification.
6. Stop through the existing bounded controller and wait for actual service exit.
   Restart with original configuration/database/enrollment, replay the original
   submission, require the same job/202/commitment and untouched newer producer
   bytes. Stop again; compare the database inode and enrollment hash.
7. With the service stopped, use a fixture-only remount/Bind flag operation to
   add nosuid to the existing source mount, keeping root/namespace/receipt
   device/inode/UID/mode unchanged. Require original-state startup refusal with
   SourceRootChanged. Restore the exact original VFS flags, verify the selected
   mount record matches, then require same-job restart/replay/commitment without
   re-enrollment. This checks persisted mount fingerprints rather than a newly
   substituted inode. The [mount(2) semantics](https://man7.org/linux/man-pages/man2/mount.2.html)
   describe per-mount MS_REMOUNT plus MS_BIND flags; this is a lab action only.
8. Only after all services and their children exit, normally unmount and proceed
   to the next layout. Final runner cleanup follows the same restore/unmount-first
   procedure above. A cleanup failure makes the run failed; preserve named resources
   for recovery rather than force-unmounting them.

Require report.rust_executed=true and authorization.passed=true, four passing
service cases and twenty failed-before-SQLite initialization controls. The report
captures exact model/driver sources, both gate IDs and binary hashes, configs,
actual responses, source/manifest/state evidence and final cleanup status. Logs
remain in its validation directory. Permanent result evidence is linked from
[increment 69](RUST-INCREMENT-69.md).

The retained broad boundary runner also uses explicit declarations for newly
provisioned fixture bindings:

```powershell
python scripts/check-nfs-boundaries.py rust/validation/<passing-production-run> --qualification-gate rust/validation/<passing-qualification-run> --isolated-startup
```

It preserves earlier noac baseline/state/OS checks; it does not convert those
records into buffered service synchronization qualification. The shared fixture
provisioner caches only the declarations of newly created disposable markers and
never refreshes them at restart. It must not be reused as a production migration
or automatic profile-discovery tool.

This extension gives finite live worker refusal/restoration/replay evidence. It
still does not qualify arbitrary mount replacement races, every interrupted
bootstrap/copy/verify/publication/manifest boundary, pending sync/COMMIT reply loss,
server grace/reclaim, other-client caches, NAS firmware, disk/power durability or
old-kernel behavior. The new fdinfo mount-ID cross-check is an old-interface design
used on a modern kernel here; missing/invalid fields refuse. Maintain the original
state and the single-host/cooperative/private-root assumptions.

### Startup regression scope after the new production refusal

Production now refuses a declared NFS source before remote metadata, including
when NFSD is stopped. The older outage test incorrectly expected it to block.
Use the qualification binary for actual blocked-bootstrap/shutdown observations.
`--isolated-startup` therefore requires `--qualification-gate`. For a focused
repeat of only inherited lock, OS metadata outage and isolated startup:

```powershell
python scripts/check-nfs-boundaries.py rust/validation/<passing-production-run> --qualification-gate rust/validation/<passing-qualification-run> --isolated-startup --startup-only
```

This mode marks transfer/local-state/state-file scopes NOT_RUN; it does not imply
the full matrix ran. Increment 69 retains the broad run's individually passed
6/12/184 subcases and overall failure separately, then records the corrected
focused startup pass. Its initial cleanup EBUSY and later successful normal
unmount have a separate recovery record. No forced/lazy unmount was used. See
[increment 69](RUST-INCREMENT-69.md) for all failed/pass IDs and exact source bytes.

The live-lab setup failures are also preserved: missing CHOWN capability was
resolved by creating files as UID 1000; root-squashed traversal was resolved by
reversible execute-only gates on the owned fixture ancestors. Private modes are
restored before every service request. On an unexpected failure with a nested
private mount still present, preserve the named resources and stop all known
services through their bounded controller first. Restore the owned server and
use the same scoped traversal gate for a normal unmount; never bypass custody or
force/lazy-unmount to report clean cleanup.

## Buffered same-share service extension

Use --same-share with both passing gates to select the six-case service matrix
instead of the four separate-export mount-authorization cases. Independent model
controls still run. Follow [the complete same-share procedure](NFS-SAME-SHARE-LAB.md)
for private layout, 64 MiB export capacity, actual durable-link pauses, worker and
coordinator exit, original-state recovery, replay and normal cleanup. See
[increment 70](RUST-INCREMENT-70.md) for results; remaining buffered outage and
synchronization reply-loss boundaries are separate work.

## Buffered read interruption extension

Use --buffered-reads with both passing gates to select same/separate-share copy
and verification read interruption/death/recovery cases. The read and publication matrices add
SYS_PTRACE and DAC_READ_SEARCH to the isolated root observer for local /proc syscall inspection;
UID-1000 service/workers retain no active capabilities. No host ptrace policy is
changed. Follow [the complete buffered-read procedure](NFS-BUFFERED-READS-LAB.md)
for cache ordering, actual read/descriptor proof, joint NFSD outage, orphan
exclusion, original-state recovery and cleanup. Results and limitations are in
[increment 71](RUST-INCREMENT-71.md).

## Buffered publication interruption extension

Use `--buffered-publication` with both passing gates to select sixteen
same/separate-share debug/release file/manifest cases. It uses the isolated
SYS_PTRACE/DAC_READ_SEARCH observer and zero-capability UID-1000 workers, as above.
Follow [the full procedure](NFS-BUFFERED-PUBLICATION-LAB.md) for returned-LINK
before-sync versus actual blocked unlinkat, joint outage, coordinator death,
surviving-worker/old-thread exclusion, original-inode recovery and committed replay.
See [increment 72](RUST-INCREMENT-72.md) for measured results and failed initial
expectation. This does not qualify pending fsync/COMMIT, successful RPC replies
withheld, foreign-target conflicts, power loss or production NFS/source deletion.

## Buffered after-unlink/before-directory-sync extension

Use `--buffered-post-unlink` with both passing gates for the eight
file_unlink_sync/manifest_unlink_sync cases across same/separate shares and
debug/release. It reuses the publication helper with a distinct matrix selection
and separate evidence. It needs only mount-setup SYS_ADMIN on the root client;
no syscall-observer capabilities are added. Ordinary workers retain zero active
capabilities. Follow the [step-by-step lab](NFS-BUFFERED-POST-UNLINK-LAB.md) and
[increment 73](RUST-INCREMENT-73.md) for absent-staging/original-allocation
evidence, ownership, actual old-thread exit, recovery/replay, cleanup and limits.
This is a returned-effect process crash, not pending sync/RPC or physical durability.

## Buffered pre-202 source claims

Select --buffered-claims with both passing gates for eight source claim
interruption/recovery cases on NMP-41B, debug/release and same/separate shares.
It is mutually exclusive with the other worker matrices. Actual linkat/unlinkat
observation requires both isolated root observer capabilities SYS_PTRACE and
DAC_READ_SEARCH; mover privileges stay unchanged. Follow
[the dedicated lab](NFS-BUFFERED-CLAIM-LAB.md) and
[increment 74](RUST-INCREMENT-74.md) for finite acceptance/results, immutable
producer paths before confirmed 202, actual-exit ownership, original-inode
custody recovery and separate evidence auditing. No new production authorization
or post-delivery source deletion is enabled.
