# Controlled NFS recovery at initial payload LINK

Increment 92 reuses the [retained two-filesystem infrastructure](NFS-DISTINCT-RECOVERY-LAB.md)
and [bounded I/O observation](NFS-VERIFICATION-RECOVERY-LAB.md) from prior increments.
Keep production NFS and post-delivery source deletion disabled. No Rust code,
dependency, producer API, retry/review policy or shutdown deadline changes.

## Selected boundary and acceptance

Repeat four native retained-FD controls, then four actual mover cases:
debug/release with NFSD restart or NFSD quiescence followed by same-container
SIGKILL/confirmed exit/start. The source and destination are distinct buffered
NMP-41B NFS client filesystems on two bounded tmpfs volumes held by a separate
storage keeper. State and ownership remain local on a third filesystem.

Select the existing qualification-only file_link_rpc rendezvous, immediately
before the link/unlink fallback's initial linkat call. Payload copying/reread
verification and the original-file sync already succeeded. Durable status is
Claimed/PublishIntent. The complete 2,097,169-byte staging inode has one link and
the expected SHA-256; final payload and COMMITTED.json are absent.

Stop the selected facility, release the pause and require actual D-state linkat,
flags zero, from staging-directory FD/name 1.part to nested-directory FD/name
data.bin. Record both descriptors' paths, mount IDs and inode metadata through
local proc state. Independently observe unchanged source/staging and absent
publication on read-only backing filesystems while stopped. Preserve the original
coordinator/worker/epoch, responsive API and ownership-specific contender refusal.

Restore the same facility and require the original pending call to return zero,
a successful raw NFS LINK named data.bin within its interval, final-file and
new-parent sync before old staging removal, then later manifest publication and
attempt-1 commitment. Preserve the original staging inode/hash as the one-link
final payload, absent staging, original state/enrollment/source and recorder's
newer reused-path bytes. Require actual worker exit and clean committed replay.
The recorder and consumer contracts remain unchanged.

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
   python scripts/check-nfs-server-recovery.py --mover --distinct-filesystems --payload-link-recovery --production-gate rust/validation/PRODUCTION_RUN --qualification-gate rust/validation/QUALIFICATION_RUN
   ```

   The payload-link flag requires mover/distinct-filesystems and excludes
   verify-recovery, publication-recovery and manifest-recovery. The runner prints payload-link-server-recovery-RUN and captures
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
6. Provision source/destination private roots and local state once per case.
   Submit to the exact qualification executable until confirmed 202/job 1; reuse
   the producer path with newer bytes. At file_link_rpc require PublishIntent,
   complete verified one-link staging and absent payload/manifest. Independently
   capture staging identity/hash and private source through read-only backing
   mounts; confirm distinct client filesystems and separate local state.
7. Attach the bounded external I/O observer before releasing the pause. Retain
   fresh relay checkpoint, common Linux clock namespaces and backend/keeper
   identity. Stop NFSD and confirm zero threads; container cases additionally
   require SIGKILL, wait exit 137/Status exited/PID 0 before same-container start.
8. Snapshot unchanged backing source/staging and absent final payload/manifest
   while stopped. Release the pause; require actual D-state syscall 265, flags
   zero, old/new directory FD paths and fdinfo. Completed trace must identify
   1.part and data.bin. Require health, unchanged status/state/epoch and guard
   contention; an ephemeral-listener contender must refuse on ownership. Avoid
   NFS client pathname inspection while the backend is down.
9. Timestamp restoration in the common Linux clock domain. Restore original
   server/IP/exports/volumes without remount or worker replacement. Require the
   same linkat entry to exit zero after restoration. Decode exact raw records:
   successful LINK named data.bin must lie inside that pending interval; retain
   both PUTFH hashes and raw request/reply hashes. This single-worker correlation
   does not establish discarded replies, server completion while stopped, full
   filehandle authority or exact cached-session/lease/reclaim semantics.
10. Require final-file/new-parent sync before staging unlink, old-parent sync
    before later manifest publication and all remaining syncs successful. Verify
    original staging inode/hash becomes final with one link and no staging name,
    original-worker attempt 1 commits, and worker actually exits. Validate complete
    manifest, private source, enrollment and local database inode/configuration.
    Stop cleanly, restart original state, replay identical JSON and require the
    same committed job/manifest with recorder's newer bytes untouched.
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
    python scripts/verify-nfs-payload-link-recovery.py rust/validation/LIVE_RUN --production-gate rust/validation/FRESH_PRODUCTION_RUN --qualification-gate rust/validation/FRESH_QUALIFICATION_RUN
    ```

    Require no containers/owned resources, unchanged baseline volume metadata and
    network names, exact source/archives/binaries, forty ELF checks, positive
    LINK syscall/staging/RPC/state proof and rejection of all corrupted-proof controls.

## Recorded result

See [increment 92](RUST-INCREMENT-92.md) and retained raw/input evidence for
four native and four actual mover passes, both SLES gates, 143 rejected proof
corruptions, forty audited ELF artifacts and final normal cleanup. Each original
pending linkat contains a successful raw LINK. Final-file/new-parent sync precede
staging removal; all sixty-eight remaining worker syncs succeed. The original
staging inode/hash becomes one-link final, with later manifest, attempt-1
commitment and clean original-state replay preserving producer reuse.

The actual debug container case changes backend network namespace; other actual
cases and all native controls retain theirs. Keeper/storage and VM boot identity
stay stable. This does not qualify general namespace/reclaim or NAS/power outcomes.

## Limits

This selects one live initial payload LINK continuation, not worker/coordinator
death, replacement or crash reconciliation. Original-file sync and earlier
copy/verification precede observation. Other payload/manifest sync and initial
manifest LINK boundaries remain separate; clean committed replay is a distinct
check. Actual successful namespace and sync calls do not prove physical durability.

The separate keeper and VM retain two bounded tmpfs filesystems. NFSD quiescence
precedes container termination. This is not abrupt live-server death, independent
NAS, disk/power loss, outstanding UNSTABLE-data loss, full lease/reclaim/session
qualification or old SLES kernel/client evidence. Preserve measured namespace
behavior without generalizing it. Unknown RPC compounds retain raw bytes. Pinned
SLES userspace shares the modern WSL2 kernel; workload/concurrency/endurance and
shipping account/deployment/access obligations remain open.

Staging removal is not private-source cleanup. Production NFS and source deletion
stay disabled; all eight release gates remain open. Registration, S3, offline
repair and DOC-06 remain deferred.
