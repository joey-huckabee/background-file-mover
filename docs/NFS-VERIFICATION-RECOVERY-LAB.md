# Controlled NFS server recovery during destination verification

This increment 89 extension uses [the retained-storage infrastructure](NFS-DISTINCT-RECOVERY-LAB.md)
from increment 88. Keep production NFS and post-delivery source deletion disabled.
Registration, S3 and offline repair remain deferred. This is a qualification test
of existing behavior, with no Rust source, dependency, API or retry-policy change.

## Finite acceptance matrix

Repeat four native original-FD controls first: source/destination with NFSD
stop/start or NFSD quiescence followed by same-container SIGKILL/confirmed exit/start.
Then run four actual mover cases: debug/release with each of those two facilities.
Both configured roots use buffered NMP-41B on distinct client NFS filesystems;
local SQLite/ownership uses a third filesystem. The two backing tmpfs volumes
are retained by a separate keeper throughout every controlled restart.

Unlike the source-copy boundary, verification begins with a complete 2 MiB + 17
byte staging file, successful preceding copy synchronization and durable Copied
phase. The qualification-only verify_read rendezvous follows cache advice and
precedes the first destination reread. Accept only an actual D-state read(2) on
that staging FD, requesting 1 MiB at offset zero, with no read-completed marker.
A process stuck in later metadata does not qualify this case.

Require unchanged original coordinator/worker/epoch and Copied status, contended
local ownership and an ownership-specific contender refusal during the outage.
Neither final payload nor completion manifest may exist yet. After restoration,
observe the original FD reading 1 MiB, 1 MiB, 17 bytes and EOF. Require full digest
verification, publication after the reread, original staging inode as final,
attempt-1 commitment, actual worker exit and original-state committed replay.
Producer-reused paths, private source and enrollment/state remain unchanged.

## Step-by-step procedure

1. Use feature/rust-transfer-coordinator and the cached pinned images/prerequisites
   in the parent lab. Inventory both Podman engines, require no unrelated containers
   and preserve their original volumes, caches and networks. No real SLES host is
   required. Setup is restricted to owned containers and volumes in the Podman VM.
2. Run both mandatory Rust build/test paths and retain their printed directories:

   ```powershell
   python scripts/check-rust-sles.py
   python scripts/check-rust-sles.py --qualification
   ```

   They use locked cargo-zigbuild GNU/glibc 2.22, exact target tests in pinned
   SLES 12 SP5 userspace, ELF/loader/library audits and negative controls. Matching
   prior gates may supply live executables while fresh gates run; final audit must
   compare exact Rust archive contents and shipping bytes across both sets.
3. Check that both selected artifact directories contain a PASSED report.json
   and a source.tar.gz matching the current Rust inputs. Freeze acquisition scripts and run the selected matrix:

   ```powershell
   python scripts/check-nfs-server-recovery.py --mover --distinct-filesystems --verify-recovery --production-gate rust/validation/PRODUCTION_RUN --qualification-gate rust/validation/QUALIFICATION_RUN
   ```

   Both earlier flags are required for --verify-recovery. The runner prints
   verify-server-recovery-RUN and captures seventeen exact scripts, including the
   bounded I/O syscall observer. Do not modify those scripts while acquisition runs.
4. Create the parent export volume, two local-driver tmpfs volumes (64 MiB and
   4,096 inodes each), live storage keeper, private fixed-IP NFS backend, read-only
   independent observer, unprivileged relay and pinned SLES client. Publish no
   ports. Verify actual distinct backing/client devices, exact mount profile and
   local state before testing. Preserve keeper PID/start/mount namespace/full
   mountinfo and the reader's read-only flags. Follow the parent's exact settings,
   including NFSD's fixture-only ten-second lease/grace and hard,ac,async NFSv4.1
   TCP/sec=sys mounts with timeo=10,retrans=1. These are controlled lab settings,
   not an inferred NAS or production timeout policy.
5. Repeat all four native retained-FD controls under this frozen fixture. Prove
   actual pending syscalls, original opaque handles/backing inodes, A-to-B bytes,
   successful synchronization/readback and actual process exit. Record successful
   session/write-verifier and namespace/VM-boot observations. All must pass before
   any Rust verification recovery case.
6. For each actual case, provision private source/destination markers and local
   state once, start the exact qualification executable and submit JSON. Require
   confirmed 202/job 1, then create newer data at the reused producer path. At
   verify_read require Copied status and complete staging size 2,097,169. Snapshot
   independent read-only source and staging inode/size/hash and confirm no final
   payload or COMMITTED.json exists. Do not hash/read staging through the NFS
   client after the cache advice; independent backing reads avoid refilling it.
7. Attach the existing bounded external I/O syscall observer to the actual worker.
   It observes local proc/memory and records FD path, mount, inode, offsets,
   syscall entries/results and later publication operations. Record a fresh relay
   checkpoint and common Linux time namespaces. Stop NFSD and confirm zero threads.
   For container cases additionally SIGKILL, wait for exit 137/Status exited/PID 0,
   and later restart that exact container. The keeper retains both filesystems.
8. Independently verify unchanged staging/source while stopped and absent final
   payload/manifest. Release the local rendezvous, require D-state read on the
   destination staging FD at position zero with 1 MiB requested and no completed
   marker. Observe responsive health, unchanged Copied status/state/epoch and
   local guard contention. A contender uses an ephemeral listener and must refuse
   on ownership; address-in-use is not valid exclusion evidence.
9. Timestamp restoration in the common Linux clock domain and restore the original
   server/IP/exports/volumes without remounting or replacing the worker. Require
   that blocked read to complete after restoration, followed by the remaining
   bytes and EOF on the same inode/FD. Publication of payload and manifest must
   follow the complete reread. All observed sync calls must succeed; their trace
   begins after the earlier copy sync, so do not claim to trace that preceding sync.
10. Require original-worker attempt-1 Committed status and actual worker exit.
    Verify source retained, original staging inode as final, exact source/final
    hashes, manifest and unchanged source/enrollment/local state/configuration.
    Cleanly stop, restart original state and retry identical JSON. Require the same
    committed job/manifest and newer producer bytes untouched, then stop cleanly.
11. Wait for runner exit and cleanup_errors=[]. Restore storage service before
    draining blocked users, normally unmount both NFS mounts and remove only owned
    resources. Verify keeper continuity one final time and remove it last so the
    local volume driver can release the retained tmpfs mounts. Remove both role
    volumes, parent and private network. Never force/lazy-unmount NFS or reset VM,
    global cgroup policy or unrelated units. Preserve failures and exact inputs
    before correction; do not promote a failed acquisition to passing support.
12. Wait for actual successful exit of both fresh SLES gates and all lab processes,
    then capture both engines and independently audit the retained evidence:

    ```powershell
    python scripts/capture-nfs-lab-inventory.py rust/validation/LIVE_RUN
    python scripts/verify-nfs-verification-recovery.py rust/validation/LIVE_RUN --production-gate rust/validation/FRESH_PRODUCTION_RUN --qualification-gate rust/validation/FRESH_QUALIFICATION_RUN
    ```

    Require zero remaining containers, unchanged baseline volume metadata/network
    names, exact frozen sources/archives/binaries, forty ELF artifacts, raw RPC
    redecoding, positive actual read/publication proof and rejection of all corrupt
    proof controls. The initial increment 88 proc-bind setup failure stays retained
    as fixture provenance; it is not a failure of this new acquisition.

## Retained initial caller failure

The first acquisition completed all four native controls but ran no Rust case:
the caller combined a gate timestamp and suffix from different runs, producing
a nonexistent report path. It exited FAILED with cleanup_errors=[] after normal
unmount/removal. The [exact command, report, seventeen source snapshots, native
probe, logs and raw wire](RUST-NFS-VERIFY-RECOVERY-INITIAL-EVIDENCE.json) remain
retained. The corrected command selects existing matching-source gate directories
and repeats all controls; no acquisition script, service behavior or deadline was
changed. Do not count those initial native passes as Rust recovery support.

## Recorded result and namespace scope

[Increment 89](RUST-INCREMENT-89.md) records four native and four actual mover
passes, both fresh SLES gates, 111 rejected proof corruptions, forty audited ELF
artifacts and final normal cleanup. All workers reread 2,097,169 bytes through
EOF on the original read-only staging FD before publishing payload and manifest.
Seventy-two traced worker sync calls succeed; earlier copy sync is outside the
attachment window. Native/session recovery and actual service read continuation
are checked separately.

The native container-source and actual release-container cases change backend
network namespace; other controls/cases retain theirs. VM boot ID is unchanged,
and keeper/storage identity remains stable in all twenty-five server-state
observations and final cleanup. Record those measured outcomes without assuming
that restarting the same container always retains or always replaces its namespace.
The selected actual continuation is not comprehensive fresh-namespace/reclaim
qualification or VM/NAS reboot evidence.

## Testing limits

The actual pending and completed read is proven at the Linux syscall/descriptor
boundary, with full destination digest validation by the service. The retained
RPC decoder does not support READ compounds; unknown raw records remain retained.
Do not label them successful READ RPCs or claim specific READ session replay.
Cache advice alone is not proof; actual pending FD/D state and incomplete-loop
checks are mandatory. Setup/backing observation adds fixture I/O outside normal
production 3N logical transfer I/O.

Storage is deliberately retained in memory on one modern WSL2 kernel NFS server.
NFSD is quiesced before container termination. This does not qualify abrupt live
server death, persistent disk/NAS power loss, old SLES kernel/client behavior,
independent endpoint failures, outstanding UNSTABLE-data loss, longer/larger or
concurrent workloads, worker death/replacement or other durable effect phases.
Measure namespace behavior; do not assume a same-container restart always retains
or replaces its namespace. SLES userspace/ELF compatibility is separate from
original-kernel, vendor-maintenance, account/deployment and physical durability.
All eight release gates remain open; production NFS/source deletion stay disabled.
