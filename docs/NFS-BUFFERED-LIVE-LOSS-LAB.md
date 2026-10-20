# Buffered payload reply-loss lab with a live coordinator

This extends the retained [COMMIT](NFS-BUFFERED-COMMIT-LAB.md) and
[UNSTABLE WRITE](NFS-BUFFERED-UNSTABLE-LAB.md) labs. Read those setup details,
[increment 80](RUST-INCREMENT-80.md) and [testing limits](TESTING-LIMITATIONS.md).
Production NFS and source deletion remain disabled. No Rust, dependency,
retry/review or assignment/shutdown deadline change is part of this increment.

1. Inspect both Podman engines. Preserve the two original Rust cache volumes,
   unrelated older rootless volumes and default networks. Use the approved
   rootful WSL2 Podman VM for the fixture and the default engine for Rust gates.
2. Run both required compatibility gates and retain their complete output:

   ```powershell
   python scripts/check-rust-sles.py
   python scripts/check-rust-sles.py --qualification
   ```

   These use locked cargo-zigbuild, GNU/glibc 2.22, exact debug/release target tests
   in pinned SLES 12 SP5 userspace and ELF/relocation audits. Source-identical prior
   passing gates may provide live artifacts while fresh gates run; final audit
   compares all current/live/fresh Rust sources and forty exact artifact bytes.
3. Freeze all acquisition/helper/test files before starting. Run the two matrices
   with distinct owned fixture resources:

   ```powershell
   python scripts/check-nfs-mount-profile.py --buffered-commit --live-loss --production-gate rust/validation/<production-run> --qualification-gate rust/validation/<qualification-run>
   python scripts/check-nfs-mount-profile.py --buffered-unstable --live-loss --production-gate rust/validation/<production-run> --qualification-gate rust/validation/<qualification-run>
   ```

   Sequential runs are easiest to inspect. Independent instances can overlap with
   frozen sources: each owns a unique internal network, NFSD/client namespaces,
   export volume and relays. Increment 80 overlaps the two final runs; their
   shared VM/kernel/CPU remain a limitation. Wait for both cleanups before final
   inventory. Never share or stop another instance's resources.

   Each captures 26 exact sources and repeats 43 inventory/model controls. One
   owned privileged NFSD container exports two root-squashed synchronous 64 MiB
   tmpfs filesystems on a private internal network. The pinned SLES client mounts
   hard NFSv4.1/TCP/sec=sys with NMP-41B buffered ac,async. Both logical exports
   share one server/kernel; they are not independent NAS failure domains.
   Same-share cases use disjoint private roots; state/SQLite/guard stay local.
4. Before each operation/layout's service cases, run native discovery, release
   and reply-drop controls. The audited disposable C probe built by Zig for
   GNU/glibc 2.22 writes two 1 MiB zero ranges plus a 17-byte tail, fchmods 0400,
   fsyncs and closes. It is fixture infrastructure, not a production executable.
   Discovery traces actual syscalls and both active transports with common live
   clock namespaces. Do not select a relay merely from the mount address.
5. Arm operation 5 (COMMIT) or 38 (WRITE) on both active relays. Require matched
   successful server replies held before forwarding, actual pending fchmod
   syscall 91/mode 0400/target FD/D state, complete server-local size/hash/inode
   and live NFSD. The local FD inode must match the controlled server object.
   WRITE capability requires stable=0/committed=0/full count for all three ranges;
   FILE_SYNC cannot substitute. COMMIT requires preceding successful UNSTABLE
   data ranges on the same handle/verifier. Repeat this proof for actual workers.
6. For the four service cases per matrix, accept job 1 with 202, pause the real
   copy worker at copy_chunk, reuse the producer path with different bytes,
   arm relays and release the checkpoint. Confirm health, unchanged local Intent
   and same-ID 202 while replies are held. Drop the successful replies and
   interrupt their transport connection. Keep the coordinator and worker alive;
   do not send a termination signal or restart them to obtain recovery.
7. During reconnection, record health/status latency, same-ID 202/released replay,
   coordinator PID, children and original-worker state. Require the same live
   coordinator, responsive local API, no replacement assignment and committed
   attempt 1 without review or manual changes. Decode actual original COMMIT
   replay or every original WRITE handle/range/hash resend. Record actual
   stability and require a later matching successful COMMIT for UNSTABLE resends.
   Preserve unknown/raw traffic and distinguish cached/session replay from a new
   WRITE following RETRY_UNCACHED_REP. A highest-slot usage hint alone does not
   change session/slot/sequence identity; other identity changes must fail.
8. Verify original claimed-source inode/hash, original database inode/enrollment,
   newer producer bytes, final payload and validated manifest, job 1 replay/no
   job 2 and retained source. Stop normally with the existing bounded controller.
   Never alter SQLite, reset deadlines, delete uncertain partials, re-enroll or
   change production policy to make a case pass.
9. Release armed replies before waiting during cleanup; confirm actual process
   exit, normal unmount, unexport and remove only owned containers/export volume/
   network. Never force/lazy unmount. Preserve full failed runs with exact sources
   and uncertain resource identities rather than treating cleanup as success.
10. After both runners and both gates exit, capture final engine inventories using
    the [retained inventory procedure](NFS-BUFFERED-SYNC-LAB.md#independent-audit-retained-evidence-and-cleanup).
    Require no containers in either engine and only the original rootful caches/
    default network. Save post-run-inventory.json in each live directory.
11. Run independent audits against fresh passing gates:

    ```powershell
    python scripts/verify-nfs-buffered-commit.py --live-loss rust/validation/<commit-live-run> --production-gate rust/validation/<fresh-production-run> --qualification-gate rust/validation/<fresh-qualification-run>
    python scripts/verify-nfs-buffered-commit.py --unstable --live-loss rust/validation/<write-live-run> --production-gate rust/validation/<fresh-production-run> --qualification-gate rust/validation/<fresh-qualification-run>
    ```

    Retain compressed exact raw reports, SHA-256, source/artifact/probe provenance,
    verifier snapshots, regression outputs and negative proof controls. Audit
    original RPC bytes and temporal/range/verifier relationships, not only the
    runner's passed flag. Record actual outcomes in increment 80 and SC-114.

These are finite short connection-interrupted losses at one payload-fchmod
boundary on a modern shared WSL2 kernel. They do not qualify all ranges/sizes,
longer delays, worker replacement, reboot/changed verifier, earlier source sync,
other NFS phases, independent physical NAS failures, old SLES kernel/packages,
NetApp/Isilon interoperability or physical power durability. Ptrace changes
scheduling; server success, returned fsync, local worker exit and a free guard
are not remote-settlement or power-loss proof. All eight release gates stay open.

Increment 80's actual post-drop status is already Committed in the first sample
for all eight cases. Health/status also pass at the proven held-reply/D-worker
boundary. These are discrete responsiveness observations, not continuous API
availability measurements across reconnection or exact recovery-time bounds.
