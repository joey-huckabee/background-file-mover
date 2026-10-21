# Controlled NFS recovery during payload publication

Increment 90 reuses the [retained two-filesystem infrastructure](NFS-DISTINCT-RECOVERY-LAB.md)
and [bounded I/O observation](NFS-VERIFICATION-RECOVERY-LAB.md) from prior increments.
Keep production NFS and post-delivery source deletion disabled. No Rust code,
dependency, producer API, retry/review policy or shutdown deadline changes.

## Selected boundary and acceptance

Repeat four native retained-FD controls, then four actual mover cases:
debug/release with NFSD restart or NFSD quiescence followed by same-container
SIGKILL/confirmed exit/start. The source and destination are distinct buffered
NMP-41B NFS client filesystems on two bounded tmpfs volumes held by a separate
storage keeper. State and ownership remain local on a third filesystem.

Select the existing qualification-only file_unlink rendezvous. The final payload
link already exists, its file and new parent have been synchronized, and the
staging alias is about to be removed. Both names must refer to the same complete
2,097,169-byte inode with link count two and the expected SHA-256. The durable
phase remains PublishIntent and COMMITTED.json is absent. A final payload name
alone is not the consumer completion signal.

Stop the selected facility before releasing the rendezvous. Require an actual
D-state unlinkat(2) on the destination staging directory FD, name 1.part, flags
zero. Preserve both aliases and private source through independent observation.
Keep the original coordinator/worker/epoch, responsive local API and contended
ownership; a contender must refuse specifically on ownership.

After restoration require the original unlink syscall to return zero, a matching
successful decoded REMOVE within its pending interval, old staging name absent,
original final inode/hash with link count one, later manifest publication,
attempt-1 commitment, actual worker exit and original-state committed replay.
The recorder's newer bytes and original source/state/enrollment remain untouched.

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
   python scripts/check-nfs-server-recovery.py --mover --distinct-filesystems --publication-recovery --production-gate rust/validation/PRODUCTION_RUN --qualification-gate rust/validation/QUALIFICATION_RUN
   ```

   The publication flag requires mover/distinct-filesystems and excludes
   verify-recovery. The runner prints publication-server-recovery-RUN and captures
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
6. For each actual case, provision source/destination private roots and local state
   once. Start the exact qualification executable and submit JSON until confirmed
   202/job 1, then reuse the producer path with newer bytes. At file_unlink require
   PublishIntent, complete staging and the original worker. Through the independent
   read-only backing mount, capture both aliases' device/inode/link count/size and
   full hash in one bounded command; require the same inode, two links and absent
   completion manifest. Do not use final-name visibility as delivery completion.
7. Attach the bounded external I/O observer before releasing the pause. It reads
   local proc/memory, recording actual syscall/FD/path/mount/inode/results. Retain
   a fresh relay checkpoint, common Linux clock namespaces and backend/keeper
   identity. Stop NFSD and confirm zero threads; container cases also require
   SIGKILL, wait exit 137/Status exited/PID 0 before eventual same-container start.
8. Independently snapshot both payload aliases and private source while stopped;
   require unchanged identities, bytes and absent manifest. Release the local
   rendezvous. Require D-state syscall 263, original staging-directory FD and
   flags zero; the completed I/O trace must identify pathname 1.part. Require
   responsive health, unchanged PublishIntent/state/epoch and local guard contention.
   Use an ephemeral listener for the contender so port collision cannot fake
   ownership exclusion. Avoid NFS client path inspection while the backend is down.
9. Timestamp restoration in the common Linux clock domain and restore the original
   server/IP/exports/volumes without remount or worker replacement. Require the same
   unlink entry to exit zero after restoration. Re-decode raw request/reply pairs:
   a successful REMOVE named 1.part must lie inside that pending syscall interval,
   with its PUTFH and raw hashes retained. Do not infer discarded replies, server
   completion before restoration, or exact cached-session replay from this case.
10. Require original-worker attempt-1 commitment and actual worker exit. The final
    payload keeps the original inode/hash with one link; staging is absent. All
    traced syncs succeed and manifest publication follows staging removal. Verify
    private source, enrollment, original local database inode/configuration and
    complete manifest. Stop cleanly, restart original state, replay identical JSON
    and require the same committed job/manifest and newer producer bytes untouched.
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
    python scripts/verify-nfs-publication-recovery.py rust/validation/LIVE_RUN --production-gate rust/validation/FRESH_PRODUCTION_RUN --qualification-gate rust/validation/FRESH_QUALIFICATION_RUN
    ```

    Require no containers/owned resources, unchanged baseline volume metadata and
    network names, exact source/archives/binaries, forty ELF checks, positive
    syscall/alias/RPC/state proof and rejection of all corrupted-proof controls.

## Recorded result

[Increment 90](RUST-INCREMENT-90.md) records four native and four actual mover
passes, both fresh SLES gates, 115 rejected proof corruptions, forty audited ELF
artifacts and final normal cleanup. All original staging-removal calls have a
successful decoded REMOVE within their pending interval. Sixty later worker sync
calls return zero; the original final inode/hash survives with one link, the
manifest follows and attempt-1 committed replay preserves newer producer bytes.

The debug container-restart mover case changes backend network namespace; other
mover cases and all native controls retain theirs. VM boot identity remains
unchanged. Keeper PID/start/mount namespace/full inventory and its two bounded
filesystems remain stable across twenty-five server-state observations and final
cleanup. This measured selected continuation is not a general namespace, lease/
reclaim, VM/NAS reboot or physical-durability guarantee.

## Limits

This tests one live-worker continuation at removal of an already synchronized
staging alias. It does not qualify initial LINK/rename effects, other publication
sync boundaries, manifest interruption, coordinator/worker death during this
recovery, uncertain-effect redispatch or application reconciliation after a crash.
A subsequent clean committed replay is a separate check.

The initial final LINK/file/new-parent sync precede observer attachment. Trace
only the actual remaining unlink, later sync and manifest effects; do not invent
pre-attachment syscall evidence. Correlated REMOVE success in the selected
single-worker window does not establish a full NFS lease/reclaim/replay matrix.
Unsupported compounds remain unknown with raw bytes preserved.

Two tmpfs filesystems retain data because their separate keeper and VM survive.
NFSD is explicitly quiesced before container termination. This is not abrupt
live-server death, persistent disk/NAS power loss, independent NAS failures,
outstanding UNSTABLE-data loss or old SLES kernel/client qualification. Record
actual network namespace behavior without assuming retention/replacement. Pinned
SLES userspace/ELF evidence shares the modern WSL2 kernel. Larger/concurrent or
longer-outage workloads and deployment/account/remote API behavior remain separate.
Staging-name removal is not postcommit private-source cleanup; the latter stays
disabled along with production NFS. All eight release gates remain open;
registration, S3, offline repair and DOC-06 remain deferred.
