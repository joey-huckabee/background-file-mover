# Incomplete claim replay before HTTP 202: controlled lab

Increment 102/SC-136 extends the [retained-storage lab](NFS-DISTINCT-RECOVERY-LAB.md).
Production NFS and postcommit private-source cleanup stay disabled. No shipping
Rust, dependency, retry/review policy or shutdown deadline changes are required.

## Finite matrix and pass conditions

Repeat four native retained-FD recovery prerequisites, then four actual mover
cases: debug/release x source claim LINK/REMOVE. Each case submits one file and
uses existing claim_link_rpc or claim_unlink_rpc. Source and destination occupy
distinct retained NFS filesystems on one backend. SQLite and ownership stay local.
Source-space admission stays off by default; set only max_retained_jobs=1 for the
finite new-ID refusal case. Multi-file partial handoffs remain separate work.

At LINK, the complete original has one link and private data is absent. At REMOVE,
original and private data are complete aliases of one inode with two links. Both
states remain Accepted with source_paths_released=false, zero confirmed claims,
no destination attempts and no destination recording directory. Stop NFSD and
release into the actual kernel operation: require D-state linkat/unlinkat with
source-parent descriptors. An artificial qualification pause is not NFS blockage.

Keep producer paths untouched. Require a non-release response to the initial
request, then six asynchronous retries/new-ID requests returning retryable
non-release 503s, including service_busy, while the same claim worker remains
assigned and blocked. The initial request may time out during the artificial
pause; it is not used as proof of kernel NFS blockage. An HTTP timeout does
not cancel a queued command. Restore the backend, retry identical JSON/ID until
confirmed 202/job 1, and only then reuse the original path. Require original-inode
private custody, attempt-1 delivery/valid manifest, newer producer bytes intact,
new-ID capacity refusal and original-state restart/replay.

## Step-by-step procedure and infrastructure

1. Use feature/rust-transfer-coordinator. Inventory both Podman engines and preserve
   baseline full volume metadata/network names. Use the default engine for SLES
   gates and the rootful engine for the private lab. No real SLES installation,
   NAS credentials or NAS-admin operation is required.
2. Run both required compatibility gates:

   ```powershell
   python scripts/check-rust-sles.py
   python scripts/check-rust-sles.py --qualification
   ```

   These use locked cargo-zigbuild GNU/glibc 2.22, pinned SLES 12 SP5 userspace,
   exact-target tests and ELF interpreter/library/symbol/negative audits. If live
   cases use prior passing identical-source artifacts while fresh gates run, audit
   complete source archives and shipping binary hashes across both sets afterward.
3. Freeze acquisition sources and start the selected mode:

   ```powershell
   python scripts/check-nfs-server-recovery.py --mover --distinct-filesystems --pre202-replay --production-gate rust/validation/PRODUCTION_RUN --qualification-gate rust/validation/QUALIFICATION_RUN
   ```

   The selected flag excludes other phases and freezes seventeen acquisition files.
   Do not edit them during a run. Keep the independent auditor in the input pack.
4. Follow the parent lab's private internal network/fixed-IP backend, independent
   storage keeper, two local-driver tmpfs volumes bounded to 64 MiB/4,096 inodes
   per role, read-only backing reader, unprivileged relay and pinned SLES client.
   Run backing-file presence/absence/stat/hash checks as UID/GID 1000, matching
   the mover. Root with all capabilities dropped cannot bypass private-directory
   permissions; absence without directory access is not valid evidence.
   Publish no ports. Keep root_squash/sync exports, fsids 68/69, fixture lease/grace
   ten seconds and buffered NMP-41B hard,ac,async NFSv4.1 TCP/sec=sys mounts with
   timeo=10,retrans=1. These fixture settings do not define a NAS production policy.
5. Repeat native NFSD/source, NFSD/destination, quiesced-container/source and
   quiesced-container/destination controls. Require actual pending retained-FD
   operations, original backing inode/filehandle and successful sync/readback.
   This does not qualify abrupt server recovery or power loss.
6. Provision each case and start at existing claim_link_rpc or claim_unlink_rpc.
   Submit original JSON asynchronously. Require Accepted/non-release status, local
   state/config identity and complete independent source custody appropriate to
   that phase; require destination recording directory absence. The producer does
   not modify any submitted file or parent before confirmed 202.
7. Stop NFSD and confirm zero threads without changing server/keeper identities.
   Release the existing qualification pause within its unchanged 60-second budget.
   Require actual D-state syscall 265/linkat or 263/unlinkat, flags zero, the source
   parent descriptor and, for LINK, the private directory descriptor. Inspect only
   owned-child local proc information; do not traverse unavailable NFS paths from
   the controller. Capture worker UID/GID 1000, zero capabilities, NoNewPrivs,
   assigned child PID and ownership epoch.
8. Launch a finite six-request burst alternating new and original IDs. Retain raw
   HTTP logs/process exit codes for these plus the initial request. Require seven
   retryable non-release 503s and at least one service_busy. New IDs use a missing
   relative file under the configured source; the one-job limit prevents their
   durable admission after restoration. This does not qualify valid new-file
   acceptance under outage or unrestricted concurrent load.
9. Require the same single blocked worker and unchanged epoch, responsive local
   health/status, held guard, one retained job and zero confirmed claims/destination
   attempts. Independently recheck complete original/private custody and absent
   destination data through the read-only backing reader. Retain local DB inode/
   config hashes and confirm NFSD remains stopped.
10. Restore two NFSD threads before draining. Retry exact JSON/ID until confirmed
    202/job 1/source_paths_released. Record confirmation time, require original-name
    absence, then write 'next recording' and record reuse time. Require actual
    original worker exit, same-coordinator attempt-1 verified delivery, complete
    valid manifest, original private inode/hash and preserved newer producer bytes.
    New ID must receive retention_capacity; job 2 must not exist.
11. Stop normally, restart original config/state, replay the identical submission
    and require 202 for committed job 1, the same complete manifest hash and intact
    producer replacement. No recorder post-202 polling duty is introduced; consumers
    continue to wait for the valid completion manifest.
12. Wait for runner and gate exits. Restore before draining blocked users, normally
    unmount NFS, remove owned users/backend, verify/remove keeper last, then owned
    role/parent volumes and network. Never force/lazy-unmount NFS, reset the VM or
    change global NAS/cgroup/host policy. Capture final inventory and audit:

    ```powershell
    python scripts/capture-nfs-lab-inventory.py rust/validation/LIVE_RUN
    python scripts/verify-nfs-pre202-replay.py rust/validation/LIVE_RUN --production-gate rust/validation/FRESH_PRODUCTION_RUN --qualification-gate rust/validation/FRESH_QUALIFICATION_RUN
    ```

    Independently verify raw RPC hashes/decoding, successful source LINK/REMOVE
    operation pairs and timing around restoration, exact descriptors, custody,
    worker/epoch exclusion, HTTP responses, no early reuse, original-state recovery,
    corrupted-proof controls, native controls and exact live/fresh artifacts.
    Audit forty Rust ELF artifacts and unchanged baseline two-engine inventory.

## Retained infrastructure failure and unchanged retries

The [initial evidence](RUST-NFS-PRE202-REPLAY-INITIAL-EVIDENCE.json) preserves two
Podman SSH handshake failures: production stopped during an artifact copy, and
fixture inventory failed before provisioning or any native/mover case. Preserve
exact failed reports, the gate source archive and seventeen acquisition files.
Check cleanup and retry unchanged code; the independent audit verifies source
identity. Do not relabel a failed attempt as passing evidence.

The [second acquisition](RUST-NFS-PRE202-REPLAY-SECOND-EVIDENCE.json) passed
native controls and self-reported debug LINK success, but REMOVE failed before
outage. Root with all capabilities dropped could not traverse the UID-1000 private
folder, so the presence test falsely reported absence. Retain exact report, sources
and empty rootful inventory. Run backing presence/absence checks as UID 1000,
include a positive destination-parent directory check, and rerun all native/mover
cases. Independently verify the exact two-check source correction. The earlier
self-reported LINK result does not replace corrected custody evidence.

## Results and limits

Read [increment 102](RUST-INCREMENT-102.md) and raw/input evidence for actual results.
One-file pending namespace effects on one shared backend do not qualify multi-file
partial handoffs, missing-file recovery, source substitution, independent server
outages, coordinator death or larger concurrent queues. Bounded retained tmpfs and
a modern shared WSL2 kernel do not qualify NAS/VM reboot, disk/power loss, old SLES
kernel/client or maintenance systemd, NetApp/Isilon, 100 GB throughput or endurance.
Local exit is not proof of global delayed-effect settlement. Source-name unlink
while claiming is distinct from disabled postcommit private-source cleanup.

All eight release gates remain open. Keep production NFS/private-source cleanup
disabled and registration/S3/offline repair/DOC-06 deferred.
