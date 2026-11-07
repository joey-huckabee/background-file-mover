# Exact source-claim file/directory-sync discovery lab

This increment 99 procedure extends the [retained-storage recovery lab](NFS-DISTINCT-RECOVERY-LAB.md).
It tests actual mover file/directory fsync behavior before selecting more server-recovery
cases. Production NFS and private-source deletion stay disabled; no shipping Rust,
dependency, API/retry/review or shutdown deadline changes.

## Finite matrix and evidence rules

Repeat four native retained-FD recovery prerequisites. Then run eight actual
mover cases: debug/release x first private-file/private-parent fsync after LINK x
healthy/stopped NFSD. The source and destination use distinct retained filesystems;
SQLite and ownership are local. Other calls in the same worker trace are observed
but are not independently fault-selected. Original-file sync before LINK is outside
this observer attachment, as are different workloads/caches and termination cases.

Start from claim_link_rpc. Submit JSON asynchronously and keep producer paths
untouched. After healthy LINK completion, intercept syscall 74 on the exact private
file .file-mover/1-0/data or its parent .file-mover/1-0. Record path, mount, inode,
arguments and entry/exit. Original current/nested/data.bin and private data must
alias the same complete inode/hash with two links. Job state is Accepted and the
destination recording directory is absent. No HTTP 202 may authorize reuse while
the selected sync is held. Consumers still wait for the valid completion manifest.

The observer runs with bounded local entry/exit rendezvous, no network, no service
package changes and no syscall substitution. Ptrace states t/T are artificial
stops, not NFS D-state. The syscall enter timestamp is reset after entry release;
its exit timestamp precedes the exit hold. Neither artificial hold belongs to the
actual syscall/RPC interval. A stopped-NFSD fsync may return successfully without
waiting for the server; record that measured outcome rather than inventing a
blocked sync. Actual D-state syscall 74/expected FD, raw target-specific RPC evidence and
post-restoration completion are prerequisites for selecting a blocked-sync
recovery case; this discovery increment does not perform coordinator-death or
reply-withholding tests. Timing alone does not establish causal attribution.

## Step-by-step procedure

1. Use feature/rust-transfer-coordinator and cached pinned images. Inventory both
   Podman engines and preserve baseline volumes/networks. The rootful engine owns
   the private fixture; the default engine runs the mandatory SLES gates. No real
   SLES installation, NAS credentials or NAS-admin operation is required.
2. Start and retain both compatibility gates:

   ```powershell
   python scripts/check-rust-sles.py
   python scripts/check-rust-sles.py --qualification
   ```

   They use locked cargo-zigbuild GNU/glibc 2.22, exact target tests in pinned SLES
   12 SP5 userspace and ELF/loader/library/symbol/negative audits. Passing identical-
   source earlier gates may supply live executables while fresh gates run; audit
   exact archive contents and shipping bytes across both sets afterward.
3. Validate the selected gate paths/report status before provisioning. Freeze
   acquisition scripts and run:

   ```powershell
   python scripts/check-nfs-server-recovery.py --mover --distinct-filesystems --claim-sync-discovery --production-gate rust/validation/PRODUCTION_RUN --qualification-gate rust/validation/QUALIFICATION_RUN
   ```

   This flag excludes the other recovery phases and captures eighteen exact
   acquisition sources. Do not edit them during the run. The separate input pack
   retains the independent verifier and its transitive auditors.
4. Follow the parent lab's private fixed-IP backend/internal network, separate
   storage keeper, two local-driver tmpfs volumes bounded to 64 MiB/4,096 inodes,
   read-only backing reader, unprivileged relay and pinned SLES client. Publish no
   ports. Verify distinct backing/client devices and local state, RO flags and
   keeper continuity. Keep root_squash/sync exports, fsids 68/69, fixture lease/
   grace ten seconds, and buffered NMP-41B hard,ac,async NFSv4.1 TCP/sec=sys mounts
   with timeo=10,retrans=1. These fixture settings are not a NAS production policy.
5. Repeat native NFSD/source, NFSD/destination, quiesced-container/source and
   quiesced-container/destination controls. Require actual pending original-FD
   operations, retained backing inode/handle, expected A-to-B bytes, successful
   sync/readback and normal exit. These remain distinct from mover-sync evidence.
6. Provision private roots and original local state once for each case. Post the
   original JSON asynchronously. At claim_link_rpc attach the external I/O observer
   with the exact source target path and expected normal claim-worker exit. Release
   the Rust pause with NFSD healthy so LINK completes before the selected fsync.
7. Wait for /tmp/sync-gate/entry.json. Require syscall 74, exact private-file/parent
   FD and worker t/T. Inspect both complete aliases through the independent read-
   only backing reader. Capture Accepted API state, absent destination recording,
   epoch, guard contention, UID/GID 1000, zero capabilities, NoNewPrivs and a common
   Linux time namespace. Do not equate backing and NFS-client device numbers.
8. For stopped controls, set NFSD threads to zero and confirm the same server/
   storage identity. Recheck custody. Save a relay checkpoint, timestamp entry
   release and touch observer-local entry-go. Exclude the artificial entry hold
   from the actual syscall/RPC interval.
9. Observe actual exit.json or D-state with syscall 74/expected FD. Keep the worker
   held at exit so a later NFS operation cannot be mistaken for the selected sync.
   If sync returns while NFSD is stopped, retain its zero result and exact interval
   before restoration. Check local health, unchanged Accepted state/epoch and one
   assigned claim worker. An artificial ptrace stop is not blocked NFS execution.
10. Timestamp restoration and restore two NFSD threads if stopped. Wait for actual
    selected exit if necessary, then independently recheck both aliases and absent
    delivery. Preserve the original HTTP log before exit release: a parsed response
    must be non-202 with source_paths_released=false. Release exit-go only afterward.
11. Retain the original request's final response or transport loss. Retry identical
    JSON/ID until confirmed 202/job 1 with source_paths_released. Any intermediate
    503 remains retryable without path release. Confirm the original source name
    is absent, then write 'next recording'. Require same-coordinator attempt-1
    commitment, actual original claim-worker exit, seven correctly ordered traced
    syncs, private original inode/hash with one link, complete verified destination
    and valid manifest. Keep DB inode/configuration/enrollment identities stable.
    Stop cleanly, restart original state and replay; require the same committed
    job/manifest and unchanged producer replacement. No post-202 recorder polling
    or consumer API-polling duty is added.
12. Wait for the actual runner exit and cleanup_errors=[]. Restore before draining
    blocked users; normally unmount both NFS mounts, remove owned users/backend,
    verify keeper identity and remove it last. Release/remove role/parent volumes
    and the private network. Never force/lazy-unmount NFS, reset the VM or change
    global host/cgroup/NAS policy. Preserve failed acquisitions and exact observer
    sources before any correction.
13. After all lab and gate processes exit, capture final inventory and audit:

    ```powershell
    python scripts/capture-nfs-lab-inventory.py rust/validation/LIVE_RUN
    python scripts/verify-nfs-claim-sync-discovery.py rust/validation/LIVE_RUN --production-gate rust/validation/FRESH_PRODUCTION_RUN --qualification-gate rust/validation/FRESH_QUALIFICATION_RUN
    ```

    Require a successful raw LINK pair inside each traced original LINK interval
    as a positive capture control. Verify raw RPC hashes/decoding, all sync
    intervals and captured pairs spanning
    entry, entry/exit gate ordering, classification before/after restoration,
    custody/phase/security/replay, proof corruptions, exact live/fresh artifacts,
    forty ELF reports and unchanged two-engine baseline metadata/networks.

## Retained harness failure and full rerun

The [initial acquisition](RUST-NFS-CLAIM-SYNC-DISCOVERY-INITIAL-EVIDENCE.json)
completed all four native and eight mover cases but failed a shared final assertion
that still expected four mover cases for the new mode. Automatic normal teardown
completed without errors; both engines were empty with baseline volumes/networks
unchanged. Exact report, eighteen sources and post-run inventory are retained.
Correct only the shared count to admit eight --claim-sync-discovery cases, then
repeat all native and mover cases using fresh passing gate artifacts. The final
independent audit checks the exact source delta and both cleanup inventories;
no raw failed acquisition is rewritten as passing evidence.

## Results and limits

Read [increment 99](RUST-INCREMENT-99.md) and its raw/input evidence packs for
measured results. Inspect raw interval records and pairs spanning entry separately.
A decoded WRITE/COMMIT in the temporal window is only a candidate until target/
causality is established. Retain unknown compounds rather than treating them as
proof of absence. Successful clean-file or directory fsync while NFSD is stopped
is not a blocked-RPC recovery or physical-persistence guarantee. Native dirty-write
controls cannot establish actual service clean-file sync or reply-withholding
capability. Do not select further death/loss tests at a boundary without positive
actual syscall/RPC evidence. Broader background activity remains separate.

The keeper and modern WSL2 kernel retain bounded tmpfs memory. NFSD quiescence
precedes native container termination; actual selected discovery cases only stop/
restore NFSD. No abrupt live-server or NAS/VM reboot, independent servers, persistent
disk/power loss, outstanding UNSTABLE-data loss, full lease/reclaim/session or old
SLES kernel/client guarantee follows. Original-file sync before observer attachment,
other fault-selected syncs, termination, workload/cache/size/concurrency/endurance
and shipping deployment/access remain open. Artificial holds are test controls,
not shutdown deadlines. All eight release gates remain open; production NFS and
postcommit private-source cleanup stay disabled. Defer registration/S3/repair and
DOC-06. Source-name unlink during claiming is distinct from private-source cleanup.
