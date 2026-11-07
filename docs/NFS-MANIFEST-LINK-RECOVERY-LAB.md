# Controlled NFS recovery at initial manifest LINK

Increment 93 reuses the [retained two-filesystem infrastructure](NFS-DISTINCT-RECOVERY-LAB.md)
and [bounded I/O observation](NFS-VERIFICATION-RECOVERY-LAB.md) from prior increments.
Keep production NFS and post-delivery source deletion disabled. No Rust code,
dependency, producer API, retry/review policy or shutdown deadline changes.

## Selected boundary and acceptance

Repeat four native retained-FD controls, then four actual mover cases:
debug/release with NFSD restart or NFSD quiescence followed by same-container
SIGKILL/confirmed exit/start. The source and destination are distinct buffered
NMP-41B NFS client filesystems on two bounded tmpfs volumes held by a separate
storage keeper. State and ownership remain local on a third filesystem.

Select the existing qualification-only manifest_link_rpc rendezvous, immediately
before the manifest link/unlink fallback's initial linkat. Payload is already
verified and Published with one link, expected SHA-256 and no payload staging.
Manifest staging contains complete bytes with one link; COMMITTED.json is absent.
Durable job status remains Claimed, payload Published, manifest_phase 3.

Stop the facility, release the pause and require actual D-state linkat, flags
zero, from staging-directory FD/name COMMITTED.part to recording-directory
FD/name COMMITTED.json. Capture both FD paths, mount IDs and directory inode
metadata through local proc state. Independent read-only backing observations
must preserve private source, manifest staging and published payload while stopped.
Keep original coordinator/worker/epoch, responsive API and ownership-specific
contender refusal.

Restore the same facility without remount or worker replacement. Require original
linkat success and a raw successful LINK named COMMITTED.json inside its interval.
Require manifest-file/new-parent sync before staging removal, remaining syncs
before local commitment, original manifest inode/hash as one-link final, unchanged
payload/source/state, attempt 1, actual worker exit and clean committed replay.
The recorder and valid-manifest consumer contracts remain unchanged.

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
   python scripts/check-nfs-server-recovery.py --mover --distinct-filesystems --manifest-link-recovery --production-gate rust/validation/PRODUCTION_RUN --qualification-gate rust/validation/QUALIFICATION_RUN
   ```

   The manifest-link flag requires mover/distinct-filesystems and excludes
   verify-recovery, publication-recovery, manifest-recovery and payload-link-recovery. The runner prints manifest-link-server-recovery-RUN and captures
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
   Submit to the exact qualification executable until confirmed 202/job 1, then
   reuse the producer path with newer bytes. At manifest_link_rpc require payload
   Published, manifest_phase 3, one-link complete manifest staging, absent final
   manifest and unchanged one-link verified payload with no payload staging.
   Capture manifest bytes/identity/hash in one read-only backing command. In this
   shared report, staging_before records the already final payload identity;
   manifest_staging_before records the actual manifest staging object.
7. Attach the bounded external I/O observer before releasing the pause. Retain
   fresh relay checkpoint, common Linux clock namespaces and backend/keeper
   identity. Stop NFSD and confirm zero threads; container cases additionally
   require SIGKILL, wait exit 137/Status exited/PID 0 before same-container start.
8. Snapshot unchanged source, manifest staging and payload while stopped, with
   final manifest still absent. Release the pause and require actual D-state
   syscall 265, flags zero, old/new directory FD paths and fdinfo. The completed
   trace must identify COMMITTED.part and COMMITTED.json. Require responsive
   health, unchanged status/state/epoch and guard contention; an ephemeral-listener
   contender must refuse specifically on ownership. Avoid NFS client pathname
   inspection while the backend is down.
9. Timestamp restoration in the common Linux clock domain. Restore original
   server/IP/exports/volumes without remount or replacement. Require original
   linkat to exit zero after restoration. Decode exact raw records: successful
   LINK named COMMITTED.json must lie inside that interval. Retain both PUTFH
   hashes and raw request/reply hashes. This single-worker correlation does not
   establish discarded replies, server completion while stopped, full opaque-
   handle authority or exact cached-session/lease/reclaim semantics. Manifest
   bytes were already complete, so no post-restoration WRITE is required.
10. Require final-manifest/new-parent sync before staging unlink and all remaining
    syncs successful before local commitment. Verify the original manifest inode/
    hash becomes one-link final with no staging name, unchanged published payload,
    original-worker attempt 1, actual worker exit, complete manifest, private
    source/enrollment and local database inode/configuration. Stop cleanly,
    restart original state and replay identical JSON; require the same committed
    job/manifest and recorder's newer reused-path bytes untouched.
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
    python scripts/verify-nfs-manifest-link-recovery.py rust/validation/LIVE_RUN --production-gate rust/validation/FRESH_PRODUCTION_RUN --qualification-gate rust/validation/FRESH_QUALIFICATION_RUN
    ```

    Require no containers/owned resources, unchanged baseline volume metadata and
    network names, exact source/archives/binaries, forty ELF checks, positive
    LINK syscall/staging/RPC/state proof and rejection of all corrupted-proof controls.

## Recorded result

See [increment 93](RUST-INCREMENT-93.md) and retained raw/input evidence for
four native and four actual mover passes, both SLES gates, 151 rejected proof
corruptions, forty verified ELF artifacts and final normal cleanup. Each original
pending linkat contains successful raw LINK. Manifest-file/new-parent sync
precedes staging removal; all twenty-four remaining worker syncs succeed. Original
manifest inode/hash becomes one-link final, payload stays unchanged, and clean
attempt-1 committed replay preserves producer reuse.

The actual debug container case changes backend network namespace; other actual
cases and native controls retain theirs. Keeper/storage and VM boot identity
stay stable. This does not establish general namespace/reclaim or NAS/power
qualification.

## Limits

This selects one live initial manifest LINK continuation, not worker/coordinator
death, replacement or crash reconciliation. Earlier payload copy/verification/
publication, manifest writing and original-file sync precede observation.
Remaining sync boundaries and clean committed replay are separate obligations.
A visible valid manifest and a later local receipt are different observations;
no consumer API-polling or recorder monitoring duty is added. Namespace/sync
success in retained memory does not establish physical NAS/power durability.

The separate keeper and VM retain two bounded tmpfs filesystems. NFSD quiescence
precedes container termination. This is not abrupt live-server death, independent
NAS, persistent disk/power or outstanding UNSTABLE-data loss, full lease/reclaim/
session qualification or old SLES kernel/client evidence. Preserve measured
namespace behavior without generalizing it. Unknown RPC compounds retain raw
bytes. Pinned SLES userspace shares the modern WSL2 kernel; workload/concurrency/
endurance and shipping account/deployment/access obligations remain open.

Staging removal is not private-source cleanup. Production NFS and source deletion
stay disabled; all eight release gates remain open. Registration, S3, offline
repair and DOC-06 remain deferred.
