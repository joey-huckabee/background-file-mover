# Buffered NFS file publication and manifest recovery lab

This controlled qualification uses the [mount-profile fixture](NFS-MOUNT-PROFILE-LAB.md)
and the existing publication checkpoints. Production NFS and source deletion
remain disabled. The production executable, retry/review policy, schemas,
dependencies and shutdown deadlines do not change. Use the
[result report](RUST-INCREMENT-72.md) for actual outcomes; the steps below define
the required observations, not an automatic passing declaration.

## Infrastructure and commands

1. Use the existing rootful Podman VM connection
   `podman-machine-default-root`, its retained kernel-NFS fixture image and the
   pinned SLES 12 SP5 runtime from `scripts/rust-platform.json`. The runner
   creates a unique internal network, one privileged kernel-NFS server, two
   root-squashed synchronous tmpfs child exports and one isolated SLES client.
   Each export has 64 MiB capacity and a distinct fsid, 68/69. No host/NAS mounts,
   credentials, production data or host ptrace policy are changed.
2. Run both mandatory compatibility gates from the repository root:

   ```powershell
   python scripts/check-rust-sles.py
   python scripts/check-rust-sles.py --qualification
   ```

   Retain both result directories. These build locked GNU x86_64/glibc 2.22
   executables with cargo-zigbuild, audit every ELF/interpreter/imported library
   and symbol version, and execute the exact debug/release target tests in pinned
   SLES userspace. Host-only Cargo tests do not replace these gates.
3. Run this worker matrix with both passing source-identical gates:

   ```powershell
   python scripts/check-nfs-mount-profile.py --production-gate rust/validation/<production-run> --qualification-gate rust/validation/<qualification-run> --buffered-publication
   ```

   Select only one of `--buffered-publication`, `--buffered-reads` and
   `--same-share`. Gate archives must match all current Rust inputs and platform
   configuration; executable hashes must match both before and after copying
   into the client. Previously passing source-identical gates may supply live
   artifacts while fresh gates run; record that distinction and independently
   compare all artifacts afterwards.
4. The client has SYS_ADMIN for mount setup and SYS_PTRACE/DAC_READ_SEARCH for
   root-only `/proc` syscall observation inside its own PID namespace. The
   [observer preflight and permission explanation](NFS-BUFFERED-READS-LAB.md)
   are retained. Services, workers, controllers and HTTP run as UID/GID 1000,
   with zero effective/permitted/inheritable capabilities and NoNewPrivs=1.
   Capture each actual paused worker's security status. Do not infer worker
   privileges from the setup observer.
5. The outer runner repeats its independent model/inventory controls. Then mount
   NMP-41B NFSv4.1/TCP/sec=sys, hard, buffered `ac,async`, at
   `/tmp/profile-source`. For same-share cases, use disjoint private role roots
   on that mount. For separate-share cases, mount the second export at
   `/tmp/profile-destination`. Record actual mount inventories/devices and
   explicit binding declarations. Local state/configuration/epochs/rendezvous
   remain under a UID-1000 mode-0700 `/tmp/local` on a different filesystem.
   Separate shares here share one server and outage domain.

## Sixteen actual worker cases

Run four points in debug/release on each layout:

| Point | Exact interruption boundary | Initial owned namespace |
|---|---|---|
| `file_link_sync` | Payload LINK returned; following file/new-parent sync has not been called | `.staging/1.part` and `nested/data.bin` are the same two-link inode; no manifest |
| `file_unlink` | Actual payload `unlinkat` is pending during outage | Same two aliases before release; new binding already passed its sync sequence |
| `manifest_link_sync` | Manifest LINK returned; following file/new-parent sync has not been called | Fully published payload and matching `.staging/COMMITTED.part`/`COMMITTED.json` aliases |
| `manifest_unlink` | Actual manifest `unlinkat` is pending during outage | Same manifest aliases before release; new binding already passed its sync sequence |

1. Provision fresh protected role markers and initialize source enrollment once.
   Create the nested 2 MiB plus 17 byte recording; capture source inode/size/hash,
   database inode and configuration/enrollment hashes. Start the qualification
   service with the selected local rendezvous. Submit JSON and require job 1/202
   with source paths released before writing `next recording` at the old path.
2. Require exactly one actual delivery child at the intended checkpoint. Capture
   worker identity, expected aliases/inode/link counts/sizes/hashes and durable
   job phase, and same-ID 202 replay while storage is healthy. Payload
   interruption is PublishIntent with no manifest. Manifest
   interruption is Published payload with an already valid visible manifest,
   while coordinator state remains Claimed. Validate manifest contents and full
   payload hash before outage: filesystem manifest visibility can precede the
   coordinator recording Committed, and is not an invalid premature manifest.
3. Stop only this owned server's NFSD with `rpc.nfsd 0`; verify zero threads in
   `/proc/fs/nfsd/threads`. For `*_unlink`, release the local rendezvous, wait
   three seconds, require D state and x86_64 syscall 263 (`unlinkat`), flags zero,
   and its directory descriptor resolving to this job's destination `.staging`.
   The checkpoint identifies the selected fixed old name; `/proc` identifies
   the pending syscall and parent, not the pointed-to string or a server RPC.
   For `*_link_sync`, leave the local pause unreleased and SIGSTOP the worker;
   require T state. Label these as returned-effect/pre-sync crashes, never
   pending sync syscalls.
4. With no replacement child, require bounded health 200, unchanged job status
   and local Running status. POST replay revalidates source custody and is not
   required to return 202 during this joint source/destination outage; it is
   tested before outage and after recovery. Kill only the coordinator PID.
   Across two samples require the old worker remains D or T, retained epoch,
   and bounded OwnerUnavailable/exit 2; record raw flock contention separately.
   Attempt service start on an alternate listener, explicit source initialization
   and direct transfer with the same state. All must promptly refuse with the
   surviving-worker diagnostic. An occupied listener is not guard evidence.
5. Only after exclusion observations, SIGKILL the old worker. Record its actual
   state, restore NFSD with `rpc.nfsd -G 10 -L 10 -V 4 -p 2049 2`, wait eleven
   seconds and verify two threads. Confirm actual old-worker exit and
   NoActiveOwner and no live old coordinator/worker threads before restart. A zombie proves exited/closed files, not PID-1
   reaping or remote settlement. No free-flock shortcut authorizes redispatch.
6. Inspect owned effects only after restoration/exit. The final name must still
   identify the original allocation; every remaining alias must match that
   inode/size/hash and the observed link count. A pending unlink may have taken
   effect before death; accept one or two owned names. A payload worker cannot
   create a later manifest without a coordinator assignment.
7. Restart with original database/configuration/enrollment and replay the same
   request. Require job 1/202, eventual Committed on attempt 1 without policy
   resets/re-enrollment/review bypass, original payload inode/hash, and original
   manifest inode/hash in manifest cases. Staging aliases disappear and final
   payload/manifest each have one link. Retained source keeps its original inode
   and content. Source cleanup stays false.
8. Stop through the bounded controller, confirm exit, restart and replay again.
   Require the same committed job, payload/manifest identities and hashes,
   the same database inode/configuration/enrollment and untouched newer producer
   bytes. SQLite content legitimately changes as recovery/commitment progresses;
   this is not a frozen-database-byte assertion. Stop cleanly.
   Record actual outcomes, source snapshots and service logs in `report.json`.

After the live matrix and fresh gates finish, verify and publish retained evidence:

```powershell
python scripts/verify-nfs-buffered-publication.py rust/validation/<live-run> --production-gate rust/validation/<fresh-production-run> --qualification-gate rust/validation/<fresh-qualification-run>
```

The verifier independently checks the complete sixteen-case tuple matrix,
syscall/descriptor observations, ownership/refusal/exit, original allocation and
replay invariants, driver hashes/current bytes and all forty fresh ELF artifact
hashes. It compares live and fresh gate archives by their actual Rust entries
(gzip timestamps may differ), requires byte-identical live/fresh executable and
test artifacts, and only then updates the retained JSON and canonical SLES reports.

## Cleanup and interpretation

Failure cleanup restores NFSD before its final termination/wait for hard-mount
users. The controlled death sequence deliberately requests SIGKILL during outage,
then restores storage before waiting for actual exit and authorizing restart.
Normally unmount each layout only after workers/services exit. The outer runner
then stops/unexports the owned server, removes only its containers/volume/internal
network and records cleanup errors. No lazy/forced NFS unmount is used; retain
resources and mark FAILED if cleanup is uncertain. Verify both Podman engines
afterwards; existing toolchain caches/images are not experiment data to delete.

These cases establish selected client-syscall/process-death and owned allocation
reconciliation on a live tmpfs server. They do not prove successful RPC completion
with its reply withheld, in-flight fsync/COMMIT, stable-media persistence, server
reboot/failover/reclaim, independent NAS failure, delayed mutating settlement,
old SLES kernel behavior, all cache/workload/outage-duration combinations or
universal cancellation bounds. Returned LINK before sync remains only a
process-crash test with retained server/cache state. Existing no-clobber negative
tests remain separate; these cases exercise recovery of the original owned inode,
not a concurrent foreign-target conflict. Contender probes occur while the
coordinator is dead and its old worker is still stopped/blocked, before worker
SIGKILL. After SIGKILL this matrix waits for actual old-thread exit before any
start; it adds no contender probes in the terminating/free-raw-guard interval.
Keep the earlier lifetime-ownership regression evidence separate. See
[testing limitations](TESTING-LIMITATIONS.md); FR-03/05 and all release gates stay
open. Production NFS and source deletion remain disabled.
