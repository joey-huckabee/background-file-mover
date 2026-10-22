# Source-claim LINK coordinator-death recovery lab

Increment 97 extends the [retained-storage lab](NFS-DISTINCT-RECOVERY-LAB.md)
and [manifest coordinator-death lab](NFS-MANIFEST-LINK-DEATH-RECOVERY-LAB.md).
Production NFS and postcommit private-source cleanup remain disabled. No shipping
Rust/dependency, API/retry/review policy or shutdown deadline changes are involved.

## Finite matrix and pass conditions

Repeat four native retained-FD controls, then debug/release x NFSD restart/
NFSD-quiesced same-container restart: four actual claim LINK cases. Source and
destination use distinct retained NFS filesystems, with SQLite and ownership state
on a third local filesystem. Keep buffered NMP-41B separate from noac diagnostics.

Pause at claim_link_rpc before linking current/nested/data.bin into protected
.file-mover/1-0/data. The original is complete with one link; private data is
absent. The durable job is internally Accepted with claim done=0 and no transfer
or manifest rows. Accepted internal status is not permission to reuse paths;
only a confirmed HTTP 202 with source_paths_released permits recorder reuse.

Stop the backend, release into actual D-state linkat(265), capture both source
parent directory descriptors and exact data.bin/data names, then kill only the
coordinator. Require logical ownership and all three contender modes refused
through actual old-worker exit. Preserve source bytes/names while unavailable,
and independently observe original/private names after restoration. Never infer
remote settlement from a free physical flock or process exit alone.

The original HTTP request may have timed out with a retryable non-202 before
coordinator death, or lose its connection on death. Retain actual raw outcome and
require no 202/false path release. The test recorder does not change submitted
paths until an identical-ID/body retry receives 202 from the replacement owner.
A durable intake or completed filesystem effect alone does not authorize reuse.

## Step-by-step infrastructure and execution

1. Use feature/rust-transfer-coordinator and cached pinned images. Inventory both
   Podman engines and preserve original volume metadata/network names. The private
   fixture uses the rootful engine; compatibility gates use the default engine.
   Use modern build-host Python with standard sqlite3/zlib only; no Python
   dependency is introduced into the shipping Rust service.
2. Start both required gates and retain their output directories:

   ```powershell
   python scripts/check-rust-sles.py
   python scripts/check-rust-sles.py --qualification
   ```

   They use locked cargo-zigbuild GNU/glibc 2.22, exact target tests in pinned
   SLES 12 SP5 userspace and loader/library/symbol/ELF negative audits. Earlier
   passing identical-source gates may provide live executables while fresh gates
   run; independently compare complete archives and shipping bytes afterward.
3. Validate selected gate paths and freeze eighteen acquisition sources before:

   ```powershell
   python scripts/check-nfs-server-recovery.py --mover --distinct-filesystems --claim-link-death-recovery --production-gate rust/validation/PRODUCTION_RUN --qualification-gate rust/validation/QUALIFICATION_RUN
   ```

   The flag excludes other selected phases. Keep the new claim module and all
   captured sources unchanged during acquisition. Preserve raw failures and exact
   code before correcting a fixture or verifier.
4. Follow the parent lab: private internal network/fixed-IP backend, unprivileged
   reserved-port relay, pinned SLES client and read-only backing reader; publish
   no ports. Retain two separate 64 MiB/4096-inode local-driver tmpfs volumes in a
   network-none keeper. Verify backing/client devices, RO flags and keeper
   continuity. Exports use root_squash/sync, fsids 68/69, fixture lease/grace ten
   seconds. Client mounts use hard,ac,async,vers=4.1,TCP,sec=sys,timeo=10,retrans=1.
   These fixture controls are not production NAS recommendations.
5. Require all four native source/destination x NFSD/container retained-FD controls
   first: actual pending operations, original inode/handle, changed protocol
   session/write verifier, exact bytes/sync/readback and normal exit. Native dirty
   synchronization evidence does not substitute for a service sync boundary.
6. Provision each actual case once. Submit the JSON asynchronously and pause at
   claim_link_rpc. Require internally Accepted, complete original source, absent
   private data and absent destination recording directory. Preserve the raw
   pending/non-202 HTTP outcome. Attach the bounded network-none external I/O
   observer to the actual internal claim worker.
7. Stop NFSD and verify threads=0. For container cases, only then SIGKILL, wait for
   exit 137/exited/PID zero, and later restart the same container/IP. This is
   controlled quiesced recovery, not abrupt live-server or NAS/VM reboot.
8. Release the pause into D-state linkat. Record arguments, old parent
   current/nested and new parent .file-mover/1-0 directory FDs, paths/mount/inode
   IDs, UID/GID 1000, zero capabilities and no-new-privileges. Require responsive
   health/status, Accepted state unchanged and the local physical guard held.
9. Kill only the coordinator PID. Retain the original request's actual response/
   connection loss and reject any 202 or false source_paths_released. Require
   three D-state ownership samples reporting OwnerUnavailable/exit 2 and specific
   ownership refusal by service/initialize-source/transfer-one contenders using
   the same state and an ephemeral API port. Abort safely if exclusion is lost.
   Preserve the epoch, original source binding and absent private data/delivery.
10. After coordinator exit, copy local jobs.sqlite and existing WAL only. Hash
    original files before/after copy, retain compressed exact bytes, and query only
    the copied files read-only/query-only. Require one original job, claim done=0
    with exact source/private names and identity, and zero transfers/manifests.
    Workers do not write SQLite. Repeat after actual old-worker exit and require
    identical snapshots/query results.
11. Restore the backend before draining. Confirm actual old-worker exit and finish
    its external trace. Independently inspect source original/private names through
    the RO backing reader: allow original-only, owned two-name aliases or private-
    only, always complete original inode/hash. Require no destination recording
    directory before replacement. A successful original call needs its actual
    return and a successful raw LINK inside that exact interval. Verify private
    file/new-parent sync before original-name unlink and remaining sync ordering.
12. Only after actual exit and custody observations start the original-state owner.
    Retry identical JSON/ID until 202/job 1 with source_paths_released. Any interim
    503 must remain retryable without path release. Confirm the original name is
    now absent; only then write 'next recording' at the producer's reused path.
    Require attempt-1 commitment, original private-source inode/hash, verified
    destination/manifest, unchanged database/configuration/enrollment identities
    and producer bytes. Delivery may progress independently of receipt of an HTTP
    response; no recorder post-202 monitoring duty is introduced.
13. Stop normally, restart once, replay identical JSON and require 202/job 1,
    Committed, unchanged manifest and producer bytes. Restore backend before
    draining users; normally unmount both NFS mounts; remove owned users/backend,
    keeper last, then owned volumes/network. Never force/lazy-unmount or reset
    the VM. Wait for every fixture process and both compatibility gates to exit.
14. Capture and independently audit final evidence:

    ```powershell
    python scripts/capture-nfs-lab-inventory.py rust/validation/LIVE_RUN
    python scripts/verify-nfs-claim-link-death-recovery.py rust/validation/LIVE_RUN --production-gate rust/validation/FRESH_PRODUCTION_RUN --qualification-gate rust/validation/FRESH_QUALIFICATION_RUN
    ```

    Require zero containers on both engines and unchanged baseline volumes/network
    metadata. Reconstruct retained DB/WAL bytes in fresh workspace scratch with
    inherited ACLs, validate its resolved parent before access/removal, close
    SQLite and remove only that owned directory. The auditor checks raw RPC
    payloads/XIDs/intervals, syscall/ownership/custody/retry proof, native controls,
    corrupted-proof controls, exact Rust inputs and all forty ELF artifacts.

## Interpretation and limitations

The service can finish the pending claim after losing its coordinator, remove the
old source name and retain private custody without a local done=1 receipt or an
HTTP 202. That is not permission for the recorder to recreate the old path yet.
Recovery must preserve the original intent and custody, then confirm 202 before
recorder reuse. Source-name removal during claiming is distinct from postcommit
private-source deletion; private-source cleanup remains off.

A missing syscall return is retained as unfinished. Observed namespace state and
local exit alone do not settle every possible delayed server effect or authorize
arbitrary redispatch/takeover. This finite same-kernel retained-memory lab does
not qualify independent NAS/VM reboot, abrupt live-server death, persistent disk/
power loss, old SLES kernel/NFS client or maintenance systemd, NetApp/Isilon,
other phases including pending claim REMOVE, termination state, longer outages,
100 GB throughput or concurrent/endurance loads. Consumer manifest rules remain
unchanged. All eight release gates stay open; production NFS/private-source
cleanup remain disabled. See [increment 97](RUST-INCREMENT-97.md) and
[testing limitations](TESTING-LIMITATIONS.md) for measured scope and next work.
