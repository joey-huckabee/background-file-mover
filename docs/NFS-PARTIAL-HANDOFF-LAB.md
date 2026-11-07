# Multi-file partial handoff replay: controlled lab

Increment 103/SC-137 extends the [retained-storage lab](NFS-DISTINCT-RECOVERY-LAB.md)
and [single-file replay lab](NFS-PRE202-REPLAY-LAB.md). Production NFS and postcommit
private-source cleanup remain disabled. API, retries, review and shutdown deadlines
are unchanged. Only the opt-in qualification build gains a claim-index pause selector.

## Finite matrix and acceptance conditions

Run four native retained-FD prerequisites, then debug/release x second-file source
LINK/REMOVE: four actual mover cases. Submit two completed files in different
subfolders, in order: earlier/first.bin (23 distinct bytes), nested/data.bin
(2 MiB + 17 bytes). The first finishes private claiming before the second pauses.
At second-file LINK, its original has one link and private data is absent; at
REMOVE, original/private are two aliases of the same inode. The first original
name is absent and its complete original inode is privately retained with one link.

Require Accepted/non-release status, exactly one confirmed claim, no destination
attempts or recording directory, unchanged complete independent custody, one actual
D-state worker and unchanged ownership epoch through a finite request burst.
Neither a completed first claim nor the first original-name disappearance permits
the recorder to reuse any submitted path. Confirmed 202 applies to the entire set.
The producer leaves completed files/parents untouched until that response.

## Step-by-step infrastructure and execution

1. Work on feature/rust-transfer-coordinator. Preserve both Podman engines' baseline
   volume metadata/network names. Use default engine for compatibility gates and
   rootful connection podman-machine-default-root for the private fixture. No real
   SLES installation, NAS credentials or NAS-admin operation is needed.
2. Run both required gates on the final Rust sources:

   ```powershell
   python scripts/check-rust-sles.py
   python scripts/check-rust-sles.py --qualification
   ```

   Both run cargo fmt/clippy, locked cargo-zigbuild for GNU/glibc 2.22, exact target
   tests in pinned SLES 12 SP5 userspace and ELF interpreter/library/symbol/negative
   controls. Host-only cargo testing is insufficient. Retain exact failed reports,
   source archives and diagnostics before corrections; never relabel failures.
3. Start the selected mode with those passing gate directories:

   ```powershell
   python scripts/check-nfs-server-recovery.py --mover --distinct-filesystems --partial-handoff-replay --production-gate rust/validation/PRODUCTION_RUN --qualification-gate rust/validation/QUALIFICATION_RUN
   ```

   This finite flag excludes every other selected phase and requires both --mover
   and --distinct-filesystems. Freeze seventeen acquisition scripts before provisioning;
   do not edit them during acquisition. Record exact Rust source/artifact hashes.
4. Follow the parent lab's internal private network without published ports, owned
   NFSD backend, independent storage keeper, two retained tmpfs role filesystems
   (64 MiB/4,096 inodes each), read-only backing reader, relay and pinned SLES client.
   Source/destination have distinct backing and client devices but share one backend.
   SQLite, ownership and rendezvous stay local. Preserve root_squash/sync exports,
   fsids 68/69 and fixture lease/grace ten seconds. Use NMP-41B hard,ac,async
   NFSv4.1 TCP/sec=sys mounts, timeo=10,retrans=1. These are fixture settings.
5. Repeat native source/destination x NFSD restart/quiesced-container restart.
   Require actual pending retained-FD operations, preserved backing inode/filehandle,
   changed session/write verifier and successful synchronization/readback. These
   prerequisites do not simulate abrupt NAS reboot or power loss.
6. Provision two complete files before submission. Keep source-space admission off
   and set max_retained_jobs=1 for the finite new-ID capacity refusal. Add
   FILE_MOVER_QUALIFICATION_CLAIM_INDEX=1 to the paused service's environment,
   together with claim_link_rpc or claim_unlink_rpc and its local rendezvous.
   The zero-based selector scopes to apply_claim_effect; index 0 runs normally,
   index 1 reaches the existing one-shot pause. Its 60-second budget is unchanged.
   The selector, thread-local scope and test are compiled out of production.
   Invalid/out-of-range selector strings are refused by the qualification hook;
   no selector preserves existing pause behavior. Scope drop restores prior context.
7. Submit identical JSON asynchronously. At the second-file pause capture local
   status/config/DB identity and independent read-only backing custody for both
   files. Run all backing traversal/hash/stat/presence checks as UID/GID 1000.
   Verify directory access positively before asserting absence. Capability-free
   root cannot bypass private-directory permissions and is not a valid shortcut.
8. Stop NFSD and confirm zero threads with server/keeper identity preserved.
   Release the artificial pause within its budget and positively observe second-file
   D-state linkat/unlinkat, flags zero, source-parent descriptor and LINK destination
   descriptor for private 1-1. Inspect only owned worker local /proc data; do not
   traverse stopped NFS from the controller. Capture UID/GID 1000, zero capabilities,
   NoNewPrivs, worker PID and ownership epoch. Artificial pause alone is not blockage.
9. Send six asynchronous requests alternating new-ID and exact original JSON/ID.
   Retain initial plus burst raw HTTP/exit codes: seven retryable non-release 503s,
   including service_busy. HTTP waiter timeout does not cancel queued commands.
   Require same blocked worker/epoch, responsive local health/status, held guard,
   one retained job, one confirmed claim, no destination attempts and unchanged
   first/second custody. New IDs use a missing relative name; this is not proof
   of acceptance of valid new recordings during outage or general load capacity.
10. Restore two NFSD threads before draining. Retry original JSON/ID until confirmed
    202/job 1/source_paths_released. Require second original-name absence, record
    confirmation time, then reuse both original paths with distinct newer bytes.
    Require actual old worker exit, same coordinator, attempt-1 verified delivery
    of both original payloads, subfolders intact, complete two-file manifest and
    original private inode/hash retention. New ID must receive retention_capacity;
    job 2 must not exist. No post-202 recorder polling duty is introduced.
11. Stop normally; restart original config/state without pauses. Replay identical
    JSON/ID, require committed job 1/202, unchanged full manifest hash, original
    private contents and both newer producer files intact. Consumers still wait
    for the valid completion manifest rather than treating acceptance as delivery.
12. Restore backend before draining on every failure. Normally unmount NFS, remove
    owned users/backend, verify/remove keeper last, then role/parent volumes and
    network. Never force/lazy-unmount, reset the VM or change global host policy.
    Wait for gates and fixture to exit, then collect inventory and independently audit:

    ```powershell
    python scripts/capture-nfs-lab-inventory.py rust/validation/LIVE_RUN
    python scripts/verify-nfs-partial-handoff-replay.py rust/validation/LIVE_RUN --production-gate rust/validation/PRODUCTION_RUN --qualification-gate rust/validation/QUALIFICATION_RUN
    ```

    Audit exact raw RPC hashes/XIDs/decoded pairs, first-file REMOVE before outage,
    distinct early source LINK filehandle signatures, selected second namespace
    effects around restoration, actual descriptors/custody, no premature release,
    request refusals and restart. Unsupported compounds remain retained, not positive
    evidence. Run corrupted-proof/storage controls, re-audit forty ELF artifacts,
    all Rust inputs, native controls and unchanged full baseline inventory.

## Evidence and limitations

The [second acquisition](RUST-NFS-PARTIAL-HANDOFF-SECOND-EVIDENCE.json) records a
premature parallel launch: all four native prerequisites passed before the
qualification release gate had written report.json. Artifact loading refused;
no Rust NFS case ran. Preserve the exact failed report and all seventeen sources,
wait for both passing gates, verify baseline cleanup and rerun the complete matrix
without acquisition-source changes. Native success alone is not mover qualification.


Read [increment 103](RUST-INCREMENT-103.md),
[raw acquisition](RUST-NFS-PARTIAL-HANDOFF-EVIDENCE.json) and
[independent audit](RUST-NFS-PARTIAL-HANDOFF-INPUT-EVIDENCE.json) for results.
[Initial gate failures](RUST-NFS-PARTIAL-HANDOFF-INITIAL-EVIDENCE.json) retain both
formatting rejections, exact source archives and rustfmt diagnostics before correction.

This qualifies two files and selected namespace boundaries with the coordinator
alive on a shared backend. It does not qualify arbitrary file counts, missing-file
recovery, source substitution, independent server outages, coordinator death or
unrestricted concurrency/endurance. Raw RPC observation is not withheld-reply
proof or an exact syscall entry/exit interval. Local exit is not global remote
settlement. A modern shared WSL2 kernel and bounded retained tmpfs do not qualify
SLES kernel/client/maintenance systemd, NetApp/Isilon, abrupt NAS/VM reboot,
persistent-disk/power-loss durability, 100 GB workloads or throughput.
Source-name unlink during claim is distinct from disabled postcommit cleanup.
All eight release gates stay open; registration/S3/offline repair/DOC-06 stay deferred.
