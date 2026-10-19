# Buffered payload COMMIT reply-loss lab

This extends the retained [I/O lab](NFS-BUFFERED-IO-LAB.md), not production
support. Keep production NFS and source deletion disabled. Preserve assignment,
shutdown, retry and review policy. The finite increment is six native controls
and eight service cases, on NMP-41B same-share and separate-share layouts.

1. Inspect both Podman engines and rootful volumes/networks. Use the existing
   approved WSL2 Podman VM, pinned builder and SLES 12 SP5 userspace image, and
   cached fixture NFSD image. Do not disturb another lab or remove unrelated
   resources. The [fixture guide](NFS-TEST-FIXTURE.md) describes provisioning.
2. Run both mandatory compatibility gates and retain their output directories:

   ```powershell
   python scripts/check-rust-sles.py
   python scripts/check-rust-sles.py --qualification
   ```

   Each uses locked cargo-zigbuild GNU/glibc 2.22, debug/release ELF auditing and
   exact target tests in pinned SLES userspace. Source-identical prior passing
   gates may supply live artifacts while fresh gates run; the independent final
   audit must compare current/live/fresh Rust inputs and all forty artifact bytes.
3. Run the mutually exclusive qualification matrix:

   ```powershell
   python scripts/check-nfs-mount-profile.py --buffered-commit --production-gate rust/validation/<production-run> --qualification-gate rust/validation/<qualification-run>
   ```

   The runner repeats 43 inventory/model controls and retains exact driver
   snapshots before acquisition. It creates one privileged kernel NFSD server,
   two root-squashed, synchronous 64 MiB tmpfs exports, a pinned SLES client and
   two unprivileged relays on an owned internal network. Both endpoints use hard
   NFSv4.1/TCP/sec=sys buffered `ac,async` mounts. Same-share roots are disjoint;
   separate shares are two logical exports on this same server. State, SQLite,
   configuration, rendezvous and instance guard remain local.
4. Before service fault cases on each layout, compile the disposable native C
   probe with pinned Zig GNU/glibc 2.22 and audit its ELF. Its new `chmod` mode
   writes two 1 MiB zero buffers and a 17-byte tail, then calls `fchmod(0400)`,
   `fsync`, and close. Existing 4 KiB modes remain separate. This native fixture
   executable is never linked into or shipped with the Rust service.
5. Run discovery with the external networkless I/O tracer. Before releasing the
   native local ready/go rendezvous, record actual client/observer/active-relay
   time namespaces. Capture both transports; a separate destination mount may
   use an established source-relay connection. Require successful COMMIT paired
   request/reply records within the actual target descriptor's successful
   `fchmod` interval. A clean `fsync` or a guessed transport cannot satisfy this.
6. Run native release and drop controls. Arm both active relays for COMMIT (5),
   then write/flush. Require a fully decoded request and its matching status-zero
   COMMIT reply held before forwarding. While held, require the actual process
   in D state inside x86_64 syscall 91, mode 0400, on the target descriptor.
   Read only local proc for that process. Independently read the server-local
   target inode/size/hash and confirm two live NFSD threads. Release the matched
   reply, or discard it and interrupt its connection. Require native completion,
   unchanged server object and decoded actual replay/resend evidence for drop.
   If capability fails, retain failure and stop before service qualification;
   do not substitute FILE_SYNC WRITE controls or invent a COMMIT.
7. Run debug/release service `live-release` and `death-drop` on each layout:

   | Case | Injection and required outcome |
   | --- | --- |
   | live-release | Accept job 1/202; reuse producer path. At existing `copy_chunk` pause, arm COMMIT controls and release worker. Require actual payload staging fchmod blocked with matched server-success reply withheld, unchanged local Intent receipt, responsive health and same-ID 202. Release reply; commit attempt 1 normally. |
   | death-drop | Reach the same proven boundary. Kill the coordinator first, prove the actual orphan still holds the original local `instance.lock`, then kill the worker. Drop reply and interrupt connection; require actual worker exit before original-state restart. Preserve the uncertain first partial and commit with a new attempt. |

   Service and worker processes use UID/GID 1000, no active capabilities and
   NoNewPrivs=1. Fixture setup/observers have narrowly scoped extra capabilities;
   they do not establish production account control. Do not edit state, reset
   deadlines, re-enroll or delete the uncertain partial to make recovery pass.
8. Require original claimed source inode/hash, local database inode/enrollment,
   original job ID, newer producer bytes, verified destination and manifest,
   source retention and no job 2. Stop the recovered service normally. Preserve
   raw relay records, before/after snapshots and worker/security observations.
9. Release all armed relays before cleanup waits. Confirm actual process exit,
   unmount normally, unexport and remove only this run's containers/export
   volume/network. Never use lazy/forced unmount. Uncertain cleanup is FAILED
   with retained resource identities. Preserve caches and older unrelated volumes.
10. After fresh gates and lab finish, capture `post-run-inventory.json` in the
    live directory using the [sync lab command](NFS-BUFFERED-SYNC-LAB.md#independent-audit-retained-evidence-and-cleanup).
    Require no containers in either engine and only the two original rootful
    cache volumes/default network. Run the independent verifier:

    ```powershell
    python scripts/verify-nfs-buffered-commit.py rust/validation/<live-run> --production-gate rust/validation/<fresh-production-run> --qualification-gate rust/validation/<fresh-qualification-run>
    ```

    It checks exact snapshots, raw record hashes/decoding, matched success held
    before forwarding, pending FD/inode, recovery invariants, meaningful rejected
    proof mutations and current/live/fresh source/artifact equality before
    retaining compressed raw evidence and input/verifier snapshots in `docs/`.
    Retain any failed full acquisition separately, with its original exact sources.

These observations use pinned SLES userspace on a modern shared WSL2 kernel,
one client and one volatile controlled server. They do not establish original
SLES-kernel behavior, physical disk/power durability, NAS failover, NetApp/Isilon
interoperability, all delayed-effect settlement, longer outages or independent
endpoint failure domains. Drop includes connection interruption. UNSTABLE WRITE
reply-loss qualification remains separate. See [testing limits](TESTING-LIMITATIONS.md)
and the actual [increment results](RUST-INCREMENT-78.md).
