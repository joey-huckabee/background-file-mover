# Buffered same-share transfer and recovery lab

This is a controlled qualification procedure, not production deployment guidance.
Production NFS and source deletion remain disabled. Use the existing disposable
[mount-profile infrastructure](NFS-MOUNT-PROFILE-LAB.md); do not run mount, signal
or cleanup commands against a NAS or host service. No NAS administrator access is
needed. The approved lab uses a private rootful Podman network, a privileged
kernel-NFS fixture server, and an isolated pinned SLES 12 SP5 client. The client
has only SYS_ADMIN for fixture mount setup; the mover, workers and HTTP client
run as UID/GID 1000 with no effective capabilities and no-new-privileges.

## Step-by-step procedure

1. From the repository root, build/test both configurations through the required
   GNU/glibc 2.22 compatibility gate. Each invocation prints its result directory:

   ```powershell
   python scripts/check-rust-sles.py
   python scripts/check-rust-sles.py --qualification
   ```

2. Run the profile fixture with those exact passing result directories:

   ```powershell
   python scripts/check-nfs-mount-profile.py --production-gate rust/validation/<production-run> --qualification-gate rust/validation/<qualification-run> --same-share
   ```

   Both reports must pass with no cleanup errors, use the current platform
   configuration, and contain a checksum-verified source archive identical to the
   current Rust inputs. The runner verifies artifact hashes before copying and
   again in the SLES client. It records exact fixture sources as SHA-256/Base64.
   No host-only cargo test is a substitute.

3. The outer runner repeats its 43 mount-profile model/inventory decisions,
   parser controls and reversible VFS-flag capability control. These are separate
   from live service evidence. It creates two root-squashed child exports with
   64 MiB tmpfs capacity each. The service matrix uses **only the source export**,
   mounted once at /tmp/profile-source with NMP-41B hard/TCP NFSv4.1/sec=sys,
   buffered ac/async semantics. The other export is only used by the retained
   independent profile controls; it is not the service destination.

4. For each debug/release binary, execute three fresh cases: uninterrupted
   baseline, claim_link, and file_link. Give each case disjoint private source and
   destination directories beneath that same mount and separate role-specific
   binding markers. Keep configuration, SQLite, ownership state and the pause
   rendezvous on local disk beneath a UID-1000 mode-0700 parent. Provision only
   fresh owned fixture markers, then
   explicitly initialize enrollment. Restart never provisions or refreshes pins.
   Record the selected mount records and require identical mount/export/device
   observations for both roles and a different local-state device.

5. Submit one nested file containing 2 MiB plus 17 bytes. In the baseline, require
   202 with released source paths and eventual Committed status. Verify the
   original source inode remains in private custody, destination content/hash,
   nested path and immutable manifest metadata. Reuse the producer path only
   after 202. Same-share placement does not introduce a rename-only delivery
   shortcut: the normal copy/hash/destination-reread protocol still applies.

6. In claim_link, submit asynchronously and observe exactly one actual claim
   worker at the qualification rendezvous after durable LINK, before old-name
   removal. Require the producer and private claim names to reference the same
   inode with exactly two links and the expected hash/size. Status must not
   release paths, and no completion manifest may exist. Leave producer paths
   untouched. This pause is after a returned operation, not a withheld reply.

7. In file_link, require the actual HTTP 202 before reusing the producer path.
   Observe exactly one delivery worker after durable destination LINK, before
   staging-name removal. Require the staging/final names to reference the same
   expected two-link inode. Source custody is already confirmed, but the
   completion manifest must still be absent. Write the next recording only at
   the producer's original path.

8. At either selected pause, STOP that identified worker and verify its stopped
   process state. KILL only the identified coordinator; verify its nonzero exit
   and that the worker remains stopped. KILL that worker and confirm actual exit
   before any replacement starts. An orphan zombie counts as exited/closed files,
   not as reaped by the minimal PID 1. Recheck the exact two owned aliases before
   restart. Preserve an incomplete initial HTTP response; a claim response must
   not be 202. No process-name or process-group killing is used.

9. Restart with the original configuration, database and enrollment. Retry the
   identical request and require job 1/202, then Committed without review bypass.
   Verify original claimed inode/hash, the publication inode in file_link,
   destination hash/size and manifest. Retain sources with cleanup disabled.
   Never infer remote settlement from a free local lock or exited process.
   These cases reconcile operations that already returned in a live server/kernel.

10. Stop through the bounded controller and wait for coordinator exit. Compare
    database inode, configuration and enrollment hashes to the original values.
    Restart again, replay the identical request, require the same committed job,
    unchanged manifest hash, source/publication inodes and untouched newer producer
    bytes. Both retained source and destination must have one link. Stop cleanly.

11. Require six passing live cases, both gate/artifact records, overall PASSED
    and cleanup_errors=[]. Per-case cleanup confirms known worker exit and keeps
    logs. Unmount normally only after services/workers exit, stop/unexport the
    owned server, and remove only the run's containers, volume and network.
    If cleanup fails, preserve the named resources and FAILED result for scoped
    recovery. Never use force/lazy unmount to manufacture a clean result.

## Reading the results and limitations

The six cases distinguish same-share live workers from inventory-only matching,
and buffered NMP-41B from historical noac NMP-41N evidence. They are finite
single-client/single-host, one-file process-crash cases. They do not observe an
NFS outage, server-completed reply withheld, pending RPC settlement, server
restart/grace/reclaim, arbitrary mount replacement, other-client cache coherence,
NAS firmware, persistent disk or power loss. Container userspace is real pinned
SLES/glibc 2.22; the kernel is the modern shared Podman/WSL2 kernel, not an old
SLES kernel. They do not qualify production workload size/endurance or all
bootstrap/copy/verify/manifest interruption boundaries. All eight release gates
remain open. See [testing limitations](TESTING-LIMITATIONS.md) and the
[first-release checklist](RUST-FIRST-RELEASE.md).

Results and exact evidence are recorded in [increment 70](RUST-INCREMENT-70.md).
