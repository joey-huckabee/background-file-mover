# Buffered UNSTABLE WRITE reply-loss lab

This retains the [payload COMMIT infrastructure](NFS-BUFFERED-COMMIT-LAB.md)
and adds a separate operation-38 matrix. Production NFS and source deletion stay
disabled. Rust behavior, retry/review policy and existing deadlines stay unchanged.
The host kernel performs NFS I/O; the relays only inject controlled test faults.
Read [increment 79](RUST-INCREMENT-79.md) for actual outcomes and limitations.

1. Inspect both Podman engines for unrelated containers and rootful volumes/
   networks. Use the approved WSL2 Podman VM and pinned builder/SLES images,
   not an actual SLES installation. Preserve caches and unrelated old volumes.
2. Run and retain both required compatibility gates:

   ```powershell
   python scripts/check-rust-sles.py
   python scripts/check-rust-sles.py --qualification
   ```

   Require locked cargo-zigbuild GNU/glibc 2.22, debug/release exact target tests
   in pinned SLES userspace, ELF and relocation checks. Prior passing source-
   identical gates may supply live artifacts while fresh gates run; final audit
   must compare all current/live/fresh Rust inputs and forty artifact bytes.
3. Run the mutually exclusive fixture mode:

   ```powershell
   python scripts/check-nfs-mount-profile.py --buffered-unstable --production-gate rust/validation/<production-run> --qualification-gate rust/validation/<qualification-run>
   ```

   The runner repeats 43 inventory/model controls and captures 26 exact driver/
   test sources. One owned privileged NFSD server exports two root-squashed,
   synchronous 64 MiB tmpfs filesystems on a private internal network. The pinned
   SLES client mounts hard NFSv4.1/TCP/sec=sys buffered `ac,async` through two
   unprivileged relays. Same-share roots are disjoint; separate-share roots use
   two logical exports on this same server. SQLite/state/guard/config stay local.
   These are not independent NAS failure domains.
4. Before service injection on each layout, run native discovery, release and
   connection-interrupted reply-drop controls. Reuse the audited disposable
   Zig GNU/glibc 2.22 C probe: two 1 MiB zero writes plus a 17-byte tail, then
   fchmod(0400), fsync and close. This is a fixture executable, not a shipping
   Rust target or new production dependency. Keep the old 4 KiB modes separate.
5. Discovery uses the external networkless I/O tracer and actual live client/
   observer/relay time namespaces. Capture both active transports; a destination
   mount address does not establish which connection carries its RPCs. Require
   actual WRITE requests/replies marked UNSTABLE in the target fchmod interval.
   Preserve unknown traffic; ptrace alters scheduling and supplies no benchmark.
6. Arm both relays for WRITE (38). Decode each request and matching status-zero
   reply before forwarding. Require request stable=0, response committed=0 and
   full returned count. A FILE_SYNC reply cannot satisfy this capability. While
   replies remain held, observe actual native syscall 91/0400/target FD and
   D state through local proc, and server-local original inode/size/hash with
   live NFSD threads. Require the complete three-range payload, not only a visible
   filename. The pending FD inode must match the controlled server object.
7. Release held successes, or discard them and interrupt their connection.
   Require native fchmod/fsync completion and unchanged server object. For drop,
   decode actual replay of **every** lost handle/range/hash. Distinguish exact
   session replay from RETRY_UNCACHED_REP followed by a new WRITE. Record actual
   requested and returned stability; do not label a stronger resend UNSTABLE.
   Any successful resend still marked UNSTABLE needs a later matching successful
   same-handle/range/verifier COMMIT. Missing ranges, wrong bytes/handles, weaker
   replies, wrong verifier or an earlier/unrelated COMMIT must fail.
8. Only after capability passes on its layout, run eight service cases:

   | Cases | Injection and acceptance |
   | --- | --- |
   | Debug/release, both layouts, live-release | Accept job 1/202 and reuse producer path. At copy_chunk, arm WRITE controls and release worker. Require actual pending payload fchmod, all three successful UNSTABLE ranges held, full server-object hash, responsive health, unchanged local Intent and same-ID 202. Release replies and commit attempt 1. |
   | Debug/release, both layouts, death-drop | Reach the same proven boundary. Kill/reap the coordinator first, independently prove its actual D-state orphan retains the same local instance guard, then kill that worker and drop replies/connection. Confirm actual exit before original-state restart. Preserve the first uncertain partial; complete a new attempt without manual repair. |

   Services/workers/relays use UID/GID 1000, zero active capabilities and
   NoNewPrivs=1. Extra mount/ptrace capabilities belong to fixture setup and
   observers. Do not edit SQLite, reset deadlines, re-enroll, delete partials or
   change production policy to make recovery pass. Require original private
   source inode/hash, database inode/enrollment, newer producer bytes, validated
   destination/manifest, job 1 replay and no job 2. Stop recovered services normally.
9. Release every armed relay before waiting in cleanup. Confirm actual exit,
   unmount normally, unexport and remove only owned containers/export volume/
   network. Never force/lazy unmount. Uncertain cleanup remains FAILED with
   retained resource identities. Preserve full failed runs and exact sources.
10. After both gates and the runner **exit**, capture `post-run-inventory.json`
    using the [sync lab command](NFS-BUFFERED-SYNC-LAB.md#independent-audit-retained-evidence-and-cleanup).
    Require no containers in either engine and only the original two rootful
    cache volumes/default network. Run the retained independent verifier:

    ```powershell
    python scripts/verify-nfs-buffered-commit.py --unstable rust/validation/<live-run> --production-gate rust/validation/<fresh-production-run> --qualification-gate rust/validation/<fresh-qualification-run>
    ```

    It verifies raw payload hashes/decoding, UNSTABLE versus FILE_SYNC, full range
    coverage, actual pending descriptor/server evidence, retransmission/COMMIT
    ordering, recovery invariants and exact source/artifact provenance. Retain
    compressed raw observations, input/verifier snapshots and regression outputs.

This finite scope does not qualify live WRITE loss without coordinator death,
server reboot/changed verifier, all sizes/cache/load/phases, original SLES kernel
or maintenance packages, independent NAS failures, NetApp/Isilon interoperability
or physical power durability. Server UNSTABLE success explicitly is not durable
storage proof; later COMMIT success on volatile tmpfs is not power-loss proof.
Local worker exit/guard availability is not remote settlement. Keep all remaining
[first-release gates](RUST-FIRST-RELEASE.md) and [testing limits](TESTING-LIMITATIONS.md)
explicit; producer/consumer contracts remain unchanged.
