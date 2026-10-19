# NFS mount-profile lab: procedure and limits

This lab validates the [candidate mount contract](NFS-MOUNT-PROFILE.md) and its
read-only Python decision model. It executes **no Rust mover**, enables no production
NFS and deletes no claimed source. See [increment 68](RUST-INCREMENT-68.md) for
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
