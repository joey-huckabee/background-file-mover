# Buffered source-claim reply-withholding lab

Read [increment 83](RUST-INCREMENT-83.md), [fixture infrastructure](NFS-TEST-FIXTURE.md),
[mount profiles](NFS-MOUNT-PROFILE.md) and [testing limits](TESTING-LIMITATIONS.md).
This is a finite capability/release lab. It changes no Rust behavior or production
authorization and discards no replies. Production NFS/source deletion remain off.

1. Use feature/rust-transfer-coordinator. Inventory both engines before starting:

   ```powershell
   podman ps -a
   podman volume ls
   podman --connection podman-machine-default-root ps -a
   podman --connection podman-machine-default-root volume ls
   podman --connection podman-machine-default-root network ls
   podman --connection podman-machine-default-root image inspect localhost/background-file-mover-e2-nfs
   ```

   Preserve unrelated containers, cache volumes and historical anonymous volumes.
   The fixture uses the approved rootful Podman VM; Rust gates use the default
   engine. Never run these commands against a production NAS or source tree.
2. Run both required compatibility gates and retain their output directories:

   ```powershell
   python scripts/check-rust-sles.py
   python scripts/check-rust-sles.py --qualification
   ```

   Require locked zigbuild GNU/glibc 2.22, debug/release ELF audits and exact
   target tests in pinned SLES 12 SP5 userspace. Source-identical prior passing
   gates can supply live binaries while fresh gates run; the final audit checks
   all 62 Rust entries and forty artifact hashes/bytes against those used live.
3. Freeze acquisition/helpers/tests before launching the mutually exclusive mode:

   ```powershell
   python scripts/check-nfs-mount-profile.py --claim-capability --production-gate rust/validation/<production-run> --qualification-gate rust/validation/<qualification-run>
   ```

   Missing either gate or combining matrices fails before fixture creation.
   The runner snapshots 28 sources and repeats 43 mount inventory/model controls.
   It creates an internal network, privileged NFSD server, pinned SLES client,
   two unprivileged relays and one owned export volume. Two root-squashed,
   synchronous 64 MiB tmpfs exports provide same-share disjoint roots and
   separate-share logical roots on one server. Mount hard NFSv4.1/TCP/sec=sys,
   ac,async,timeo=10,retrans=1 (NMP-41B). SQLite/state/guard remain local.
   Client setup uses SYS_ADMIN plus SYS_PTRACE/DAC_READ_SEARCH for proc sampling;
   actual mover/claim workers and relays use UID/GID 1000, zero active
   capabilities and NoNewPrivs=1. No host ptrace/NAS policy is modified.
4. Run eight actual claim workers: two operations × two layouts × debug/release.
   Each recording contains nested/data.bin, 2 MiB+17 bytes. Save the server-local
   original inode/device/size/hash and one-link/absent-custody observations.
   Submit asynchronously and pause at claim_link_rpc or claim_unlink_rpc.
   No successful 202 has yet authorized producer-path reuse.
5. Observe and arm the target LINK (11, name data) or REMOVE (28, name data.bin)
   on both active transport relays before releasing the worker pause. Same-share
   uses one relay; separate shares use two. Kernel session sharing means mount
   address alone cannot identify the carrier; record the actual matching role.
   Require a whole matched, status-zero request/reply, exact raw hashes/XID,
   one withheld success, no selected forwarded success and no decoder errors.
   Preserve complete compounds; never search arbitrary bytes for opcodes.
6. While withheld, sample the real worker's D state and current x86_64 syscall:
   linkat 265 with both directory descriptors and zero flags, or unlinkat 263
   with producer-parent descriptor and zero flags. Match descriptor paths,
   mount IDs and parent inodes to independent server directories. Keep NFSD
   running with two threads. Independent server observations must show LINK's
   two aliases to the original inode, or REMOVE's absent producer alias and
   surviving one-link original custody inode. All original size/hash values
   must match. This is syscall sampling plus relay tracing, not a full ptrace
   syscall-entry/exit or production-scale benchmark.
7. Require health/job status within five seconds; status remains Accepted and
   source_paths_released=false. Initial submission and same-ID retries return
   retryable 503 handoff_pending/service_busy within existing fixture limits.
   Destination job 1 must remain absent, with the original coordinator and one
   claim worker. The recorder leaves its paths untouched even when server-side
   REMOVE is already complete. Recheck withheld success and unchanged server
   aliases; then release the exact saved reply. Do not drop it, kill the
   coordinator, edit SQLite, re-enroll or reset a deadline.
8. Confirm same-ID job 1/202 with released paths before writing newer producer
   bytes. Require ordinary attempt-1 commitment, original one-link private
   source/hash, verified destination payload and manifest, original database
   inode/enrollment and unchanged root identities. Preserve newer producer
   bytes, retain claimed source, and require job 2 absent. Stop normally through
   the bounded controller and confirm coordinator exit.
9. Release relays before cleanup; require normal unmount, unexport and removal
   of only owned containers/volume/network. Never use lazy/forced unmount to
   claim success. Retain complete failed reports and exact source snapshots
   before fixing/reacquiring any failed control. Wait for the actual runner and
   both gate processes to exit before final inventory, not just a PASS line.
10. Capture post-run-inventory.json with the
    [retained inventory procedure](NFS-BUFFERED-SYNC-LAB.md#independent-audit-retained-evidence-and-cleanup).
    Both engines must have zero containers; rootful retains only its two original
    cache volumes and default network. Preserve unrelated volume identities.
    Then run:

    ```powershell
    python scripts/verify-nfs-claim-capability.py rust/validation/<live-run> --production-gate rust/validation/<fresh-production-run> --qualification-gate rust/validation/<fresh-qualification-run>
    ```

    It checks full raw wire hashes/decodes/bounds, matched successful withholding,
    descriptor/server aliases, custody/API/source/state/final-manifest invariants,
    actual-proof rejection controls, Python proof tests, all 28 source snapshots,
    both fresh/live source archives, forty artifact comparisons and inventories.
    Retain compressed lossless report bytes/SHA, audit/source snapshots, fresh
    Rust archives and regression output in the two CLAIM-CAPABILITY evidence files.
    Update SC-117 and DOC-01–05 with observed results; DOC-06 remains deferred.

This lab does not qualify reply loss, native replay, coordinator death, server
restart/verifier changes, delayed remote effects or producer modifications before
202. Producer-name removal during claiming is distinct from postcommit source
cleanup, which remains disabled. One shared modern WSL2 kernel and volatile
exports cannot prove original SLES kernel/maintenance-RPM compatibility, NetApp/
Isilon interoperability, independent NAS failure domains or physical power
durability. Other sizes/file counts/cache states/load and endurance remain open.
Discrete API samples are not continuous-availability or latency guarantees.

Selected buffered live/death reply-loss recovery is covered separately by the
[claim loss lab](NFS-CLAIM-LOSS-LAB.md) and [increment 84](RUST-INCREMENT-84.md).
Keep its replay/reconciliation proof distinct from the capability controls here.
