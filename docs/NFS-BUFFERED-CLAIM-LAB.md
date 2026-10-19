# Buffered NFS source-claim interruption and recovery lab

This eight-case extension retains the [mount-profile infrastructure](NFS-MOUNT-PROFILE-LAB.md)
and [fixture](NFS-TEST-FIXTURE.md). See [increment 74](RUST-INCREMENT-74.md) for
actual results. Production NFS and post-delivery source deletion remain disabled.

## Infrastructure and commands

1. Use the approved Podman WSL2 VM and rootful connection
   `podman-machine-default-root`. Inspect existing resources and the cached
   `localhost/background-file-mover-e2-nfs` image. Each run owns an internal
   network, export volume, privileged kernel-NFS server and pinned SLES 12 SP5
   client; no host/NAS setup, kernel change or systemd bootstrap is introduced.

   ```powershell
   podman --connection podman-machine-default-root ps -a
   podman --connection podman-machine-default-root image inspect localhost/background-file-mover-e2-nfs
   ```

2. Run both mandatory SLES compatibility gates and retain printed directories:

   ```powershell
   python scripts/check-rust-sles.py
   python scripts/check-rust-sles.py --qualification
   ```

   Locked cargo-zigbuild targets GNU x86_64/glibc 2.22. Require ELF loader/library/
   symbol audits, negative controls and exact debug/release target tests in
   pinned SLES userspace. Host-only Cargo tests cannot replace these gates.

3. Start the matrix with passing gate directories:

   ```powershell
   python scripts/check-nfs-mount-profile.py --production-gate rust/validation/<production-run> --qualification-gate rust/validation/<qualification-run> --buffered-claims
   ```

   Select one worker matrix only. This option is mutually exclusive with
   `--same-share`, `--buffered-reads`, `--buffered-publication` and
   `--buffered-post-unlink`. The runner first repeats 43 independent model/
   inventory controls, compares current Rust entries to both gate archives and
   hashes transferred shipping binaries. Passing source-identical prior gates
   may supply live binaries while fresh gates run; record that distinction and
   independently compare all fresh artifacts afterwards. Exact driver bytes
   are retained as SHA-256/Base64 snapshots.

4. The root-squashed synchronous child exports use distinct fsids 68/69 and
   64 MiB tmpfs capacity each. Mount buffered NMP-41B NFSv4.1/TCP/sec=sys, hard,
   `ac,async`. Same-share uses disjoint private source/destination roots under
   `/tmp/profile-source`; separate-share mounts `/tmp/profile-destination` too.
   Record actual mount records/devices. Both exports share one server/outage.
   Database, configuration, epochs and rendezvous are local under a private
   UID-1000 parent on a different filesystem.

5. Root client setup has SYS_ADMIN; only this isolated syscall observer adds
   SYS_PTRACE and DAC_READ_SEARCH. Both are needed for owner-only UID-1000
   `/proc/PID/syscall` on this fixture. Ordinary service/workers/controllers/HTTP
   run UID/GID 1000, no active capabilities and NoNewPrivs=1. Capture actual
   security records; no host ptrace policy or mover privilege is changed.

## Eight cases and acceptance

Run the following two points in both profiles on both layouts. Cases are serial
because each interrupts the shared server.

| Point | Namespace at unreleased checkpoint | Actual required pending syscall |
|---|---|---|
| `claim_link_rpc` | Original producer file has one link; custody data absent | x86_64 `linkat` 265, old parent `source/current/nested`, new parent `source/.file-mover/1-0`, flags zero |
| `claim_unlink_rpc` | Producer and custody data are the same original inode with two links | x86_64 `unlinkat` 263, old parent `source/current/nested`, flags zero |

1. Provision protected source/destination markers and initialize source once.
   Create nested 2 MiB plus 17 byte input. Capture source inode/size/SHA-256,
   database inode and configuration/enrollment hashes. Start the audited service
   at the selected qualification checkpoint. POST asynchronously; require one
   actual claim child and matching ready checkpoint. The initial hash is fixture
   comparison evidence, not an added production prehash; normal transfer remains
   source hashing during copy plus destination reread (3N logical I/O). The producer leaves all
   files and parents unchanged throughout unconfirmed handoff.
2. Check the namespace above and Accepted/unreleased job status with source
   cleanup false. Destination recording directory must be absent. Record local
   worker epoch/security. Stop only the owned NFSD (`rpc.nfsd 0`), confirm zero
   threads and release the checkpoint. Require actual D state, syscall number,
   flags and directory descriptor targets. Never inspect NFS paths during the
   outage: local state and `/proc` provide the observations.
3. Require health 200 and unchanged job status, each independently below five
   seconds including its host copy/Podman overhead. Keep combined cost diagnostic.
   The original POST must finish with retryable 503 `handoff_pending` or
   `service_busy`, paths unreleased; no early 202 is acceptable. Require Running
   local controller status, one unchanged worker and contended guard.
4. Kill only the coordinator. In two samples require the orphan remains D,
   OwnerUnavailable/exit 2 and unchanged epoch; record raw flock independently.
   With the same state and an alternate listener, attempt service startup,
   explicit initialization and direct transfer. All must promptly refuse with
   the surviving-worker ownership diagnostic. An occupied listener is not proof.
5. Only after contender probes, SIGKILL the worker. Restore owned NFSD using
   `rpc.nfsd -G 10 -L 10 -V 4 -p 2049 2`, wait eleven seconds and confirm two
   threads. Confirm actual worker exit and absence of live old coordinator/
   worker threads, then free guard and NoActiveOwner before restarting. A zombie
   proves exit/files closed, not PID-1 reaping or NAS-effect settlement.
6. Reinspect after restoration/exit. At least one source alias must retain the
   original inode/size/hash; any two aliases must refer to that same inode with
   correct link count. No destination recording may exist yet. Do not assume
   whether an interrupted syscall completed remotely. Preserve database inode,
   configuration and enrollment receipt; database contents legitimately change
   as progress is recorded.
7. Restart using original state and submit identical JSON/IDs. Require job 1/202
   with paths released. Only now write `next recording` at the producer path.
   Normal recovery must reach Committed on attempt 1, validate manifest/content,
   retain the original private custody inode and preserve new producer bytes.
   Require job 2 absent, no review/reset/re-enrollment or policy bypass.
8. Clean stop via bounded controller, confirm exit, restart and replay again.
   Require the same committed job, publication/manifest identities and hashes,
   original local state/configuration/enrollment and newer producer bytes. Stop
   cleanly and retain service logs and case evidence.

## Independent audit and cleanup

After the eight cases and both fresh gates pass:

```powershell
python scripts/verify-nfs-buffered-claims.py rust/validation/<live-run> --production-gate rust/validation/<fresh-production-run> --qualification-gate rust/validation/<fresh-qualification-run>
```

The verifier checks complete tuple coverage, syscall/namespace/pre-202 response,
security, exclusion, actual exit, original-inode recovery/replay, exact current
Rust and driver input bytes and all forty fresh ELF artifact hashes. Live/fresh
Rust entries and artifact bytes must match; archive gzip metadata may differ.
Only after assertions pass does it retain separate claim evidence/input evidence
and refresh canonical SLES reports. Input evidence includes source archives and
the exact verifier source. Earlier experiment/increment reports are preserved.

Failure cleanup restores NFSD before final termination/wait. After users exit,
unmount normally, unexport and remove only owned containers/export volume/network.
Keep cached images/toolchain volumes. Retain uncertain resources and mark FAILED;
use no forced/lazy NFS unmount or host/NAS changes. Independently inspect both
Podman engines after cleanup (`podman ps -a` and the rootful equivalent); compare
remaining volumes/networks against the pre-run baseline.

## What this does and does not qualify

This tests actual blocked client source namespace syscalls, joint server outage,
coordinator death and original-state recovery before 202. Claim removal of the
producer name establishes custody; post-delivery source cleanup is still off.
It proves no server-completed RPC with its reply withheld, pending fsync/COMMIT,
server reboot/failover/reclaim, disk/power durability, independent NAS/cache,
other-client coherence, old SLES kernel behavior or production-scale/endurance.
Contender probes precede worker SIGKILL; after it the harness waits for actual
exit, without adding a terminating/free-raw-guard contender branch. Finite timing
observations do not promise universal cancellation/latency bounds. See
[testing limitations](TESTING-LIMITATIONS.md). All eight release gates stay open.
