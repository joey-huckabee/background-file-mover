# Controlled NFS recovery during manifest commitment

Increment 91 reuses the [retained two-filesystem infrastructure](NFS-DISTINCT-RECOVERY-LAB.md)
and [bounded I/O observation](NFS-VERIFICATION-RECOVERY-LAB.md) from prior increments.
Keep production NFS and post-delivery source deletion disabled. No Rust code,
dependency, producer API, retry/review policy or shutdown deadline changes.

## Selected boundary and acceptance

Repeat four native retained-FD controls, then four actual mover cases:
debug/release with NFSD restart or NFSD quiescence followed by same-container
SIGKILL/confirmed exit/start. The source and destination are distinct buffered
NMP-41B NFS client filesystems on two bounded tmpfs volumes held by a separate
storage keeper. State and ownership remain local on a third filesystem.

Select the existing qualification-only manifest_unlink rendezvous. The payload
is already verified and Published, with its final inode/hash and one link; payload
staging is absent. COMMITTED.part and COMMITTED.json contain the same complete
manifest inode with two links. Initial manifest LINK/file/new-parent sync precede
the pause. Local status remains Claimed, payload Published, manifest_phase 3.

The existing consumer contract waits for a valid COMMITTED.json after all required
payload files are verified and published. This case does not add a consumer API
polling duty or a recorder monitoring duty. Manifest-name visibility and the later
local Committed receipt are separate observations; retained-memory observation
does not prove physical durability under NAS or power failure.

Stop the selected facility, then release the pause. Require an actual D-state
unlinkat(2), flags zero, staging directory FD and pathname COMMITTED.part.
Independently observe unchanged manifest aliases, published payload and private
source on read-only backing mounts while stopped. Preserve original coordinator,
worker, epoch, responsive API and ownership-specific contender refusal.

Restore the same facility and require the original pending call to succeed, a
successful raw REMOVE within its interval, original manifest inode/hash with one
link and no staging alias. Require the remaining staging/file/directory syncs,
original-worker attempt-1 commitment, actual exit and original-state replay.

## Step-by-step procedure

1. Use feature/rust-transfer-coordinator and the cached pinned images from the
   parent labs. Inventory both Podman engines; require no unrelated containers.
   Preserve baseline anonymous volumes, Rust caches and networks. Use owned
   containers/volumes only; no real SLES installation or NAS-admin access is needed.
2. Run the two mandatory Rust build/test paths and retain their output directories:

   ```powershell
   python scripts/check-rust-sles.py
   python scripts/check-rust-sles.py --qualification
   ```

   These use locked cargo-zigbuild GNU/glibc 2.22, exact target tests in pinned
   SLES 12 SP5 userspace, ELF/interpreter/library audits and negative controls.
   Existing identical-source gates may supply live binaries while fresh gates run;
   the final audit compares exact archives and shipping bytes across both sets.
3. Check selected artifact paths contain PASSED report.json and matching source
   archives before provisioning. Freeze acquisition scripts, then run:

   ```powershell
   python scripts/check-nfs-server-recovery.py --mover --distinct-filesystems --manifest-recovery --production-gate rust/validation/PRODUCTION_RUN --qualification-gate rust/validation/QUALIFICATION_RUN
   ```

   The manifest flag requires mover/distinct-filesystems and excludes
   verify-recovery and publication-recovery. The runner prints manifest-server-recovery-RUN and captures
   seventeen exact acquisition sources. Do not edit them during an active run.
4. Provision the parent's private fixed-IP NFS backend/internal network, parent
   export volume, separate storage keeper, two local-driver tmpfs volumes bounded
   to 64 MiB/4,096 inodes each, read-only independent backing reader, unprivileged
   relay and pinned SLES client. No ports are published. Prove actual distinct
   backing/client devices and local state, reader ro flags and keeper continuity.
   Follow the existing root_squash/sync exports, fsids 68/69, fixture ten-second
   lease/grace and hard,ac,async NFSv4.1 TCP/sec=sys timeo=10,retrans=1 settings.
   These are controlled fixture settings, not an inferred production/NAS policy.
5. Repeat all four native original-FD controls before any mover case. Prove actual
   pending syscalls, original opaque handle/backing inode, A-to-B bytes, successful
   synchronization/readback and normal probe exit. Measure session/write-verifier,
   network namespace and VM-boot observations rather than assuming restart semantics.
6. For each actual case, provision private roots and local state once. Submit
   JSON to the qualification executable and require confirmed 202/job 1. Reuse the
   producer path with newer bytes. At manifest_unlink require Published and
   manifest_phase 3. Capture complete manifest bytes/hash and both aliases'
   device/inode/link count/size in one read-only command. Require two links and
   unchanged one-link final payload; payload staging is absent. The field
   staging_before in this shared report records the final payload identity in
   manifest mode, not a claim that payload staging remains present.
7. Attach the bounded external I/O observer before releasing the pause. Retain
   a fresh relay checkpoint, common Linux clock namespaces and backend/keeper
   identity. Stop NFSD and confirm zero threads; container cases also require
   SIGKILL, wait exit 137/Status exited/PID 0 before same-container start.
8. Independently snapshot manifest aliases, published payload and private source
   while stopped. Release the pause and prove actual D-state syscall 263 on the
   staging-directory FD, flags zero. The completed trace must identify
   COMMITTED.part. Require health, unchanged status/state/epoch and local guard
   contention. Use an ephemeral contender listener to exclude port-collision
   false positives. Avoid NFS client path inspection while the backend is down.
9. Timestamp restoration in the common Linux clock domain. Restore the original
   server/IP/exports/volumes without remount or worker replacement. Require the
   same unlink call to exit zero after restoration. Re-decode raw request/reply
   pairs: a successful REMOVE named COMMITTED.part must lie inside that interval,
   with PUTFH and raw hashes retained. This is not discarded-reply or full cached
   session/reclaim proof. No post-restoration WRITE is required: manifest bytes
   were complete before this boundary.
10. Require the original manifest inode/hash with one link and staging absent,
    unchanged published payload, and remaining successful syncs before original
    attempt-1 commitment. Validate complete manifest, private source, enrollment,
    original local database inode/configuration and actual worker exit. Stop
    cleanly, restart original state, replay identical JSON and require the same
    committed job/manifest and newer producer bytes untouched.
11. Wait for actual runner exit and cleanup_errors=[]. Restore service before
    draining blocked users. Normally unmount both NFS mounts, remove owned users
    and backend, verify keeper identity one final time and remove it last. Let
    Podman's local driver release the retained tmpfs mounts, then remove both role
    volumes, parent volume and private network. No force/lazy NFS unmount, VM reset,
    global host/cgroup policy change or NAS operation. Preserve failed acquisition
    sources and available raw proof before correction; failures never count as support.
12. After all lab processes and both fresh SLES gates exit successfully, capture
    both engines and run the independent audit:

    ```powershell
    python scripts/capture-nfs-lab-inventory.py rust/validation/LIVE_RUN
    python scripts/verify-nfs-manifest-recovery.py rust/validation/LIVE_RUN --production-gate rust/validation/FRESH_PRODUCTION_RUN --qualification-gate rust/validation/FRESH_QUALIFICATION_RUN
    ```

    Require no containers/owned resources, unchanged baseline volume metadata and
    network names, exact source/archives/binaries, forty ELF checks, positive
    manifest syscall/alias/RPC/state proof and rejection of all corrupted-proof controls.

## Recorded result

See [increment 91](RUST-INCREMENT-91.md) and its retained raw/input evidence for
four native and four actual mover passes, both compatibility gates, 127 rejected
proof corruptions, forty verified ELF artifacts and final normal cleanup. Every
original pending unlink has a correlated successful REMOVE. Sixteen remaining
sync calls return zero, the original manifest inode/hash survives with one link,
and original-state attempt-1 committed replay preserves recorder reuse.

The debug container case changes backend network namespace; other actual cases
retain theirs. Keeper storage/identity and VM boot remain stable. No physical
NAS/power or full session/reclaim guarantee follows from these observations.

## Limits

This selects live continuation at manifest staging-name removal. Initial manifest
LINK/file/new-parent sync precede observation; no pre-attachment syscall evidence
is claimed. Other sync boundaries, coordinator/worker death, replacement and crash
reconciliation remain separate. A later clean committed replay is a distinct test.

The separate keeper and VM retain two tmpfs filesystems. NFSD quiescence precedes
container termination. This is not abrupt live-server death, independent NAS,
persistent disk/power loss, outstanding UNSTABLE-data loss, a complete NFS
lease/reclaim matrix or an old SLES kernel/client test. Preserve measured backend
namespace behavior without generalizing it. Unsupported RPC compounds remain
unknown with raw bytes retained. Pinned SLES userspace shares the modern WSL2
kernel. Workload/size/concurrency/endurance and deployment/access limits remain.

Destination staging removal is not private-source cleanup. Production NFS and
source deletion stay disabled. All eight release gates stay open; registration,
S3, offline repair and DOC-06 remain deferred.
