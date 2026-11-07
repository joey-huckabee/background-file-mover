# Buffered NFS enrolled and populated startup recovery lab

This eight-case extension retains the [mount-profile infrastructure](NFS-MOUNT-PROFILE-LAB.md)
and [NFS fixture](NFS-TEST-FIXTURE.md). See [increment 75](RUST-INCREMENT-75.md)
for actual results. Production NFS and source deletion remain disabled.

## Infrastructure and commands

1. Use the existing approved Podman WSL2 VM/rootful connection. Inspect the
   branch, containers and cached server image before running:

   ```powershell
   git status --short --branch
   podman --connection podman-machine-default-root ps -a
   podman --connection podman-machine-default-root image inspect localhost/background-file-mover-e2-nfs
   ```

   Use `feature/rust-transfer-coordinator`. Stop for conflicting unrelated labs;
   remove no resources owned by another run. Missing modules/images require the
   existing [fixture setup](NFS-TEST-FIXTURE.md), not silent bootstrap or new pins.
2. Run both mandatory SLES compatibility gates and retain printed directories:

   ```powershell
   python scripts/check-rust-sles.py
   python scripts/check-rust-sles.py --qualification
   ```

   Locked cargo-zigbuild targets GNU x86_64/glibc 2.22. Require ELF loader/library/
   symbol audits, negative controls and exact debug/release tests in pinned SLES
   userspace. Host-only Cargo tests cannot replace the gates.
3. Start the matrix using both passing gates:

   ```powershell
   python scripts/check-nfs-mount-profile.py --production-gate rust/validation/<production-run> --qualification-gate rust/validation/<qualification-run> --buffered-bootstrap
   ```

   Select one worker matrix only; this option is mutually exclusive with other
   mount-profile worker options. The runner repeats 43 independent model/inventory
   controls, verifies current Rust entries against gate archives and hashes all
   transferred executables. Source-identical prior passing gates may supply live
   binaries while fresh gates run; record the distinction and compare all fresh
   artifacts afterwards. Retain exact SHA-256/Base64 driver snapshots.
4. Each run owns an internal network, named export volume, privileged kernel-NFS
   server and pinned SLES client. Root-squashed synchronous child exports use
   fsids 68/69 and 64 MiB tmpfs devices. The buffered mounts use NFSv4.1/TCP/sec=sys,
   hard, `ac,async,acregmax=60,acdirmax=60`. Same-share uses disjoint private roots
   on `/tmp/profile-source`; separate-share additionally mounts
   `/tmp/profile-destination`. Record selected mount records/devices and full
   mountstats. Both shares have one server/outage domain. Local state is under a
   private UID-1000 parent on a different filesystem. No host NAS/mount is touched.
5. Isolated root setup uses SYS_ADMIN and the syscall/kernel-wait observer adds
   SYS_PTRACE and DAC_READ_SEARCH. Ordinary service, worker, controller and HTTP
   processes retain UID/GID 1000, no active capabilities, NoNewPrivs=1. Capture
   actual worker security; change no host ptrace policy, kernel, systemd or NAS
   privilege. Do not confuse observer permissions with deployment requirements.

## Eight cases and acceptance

Run each state in debug/release on both layouts. Cases are serial because they
interrupt the same controlled NFSD.

| State | Seed before startup interruption | Expected normal recovery |
|---|---|---|
| `bootstrap_enrolled` | Initialized original database/receipt; no job | First job claims after recovery/202, then attempt 1 |
| `bootstrap_populated` | Job 1 already acknowledged; claimed source, WAL and exactly one 1 MiB copy partial | Same job/202, attempt 2; old partial retained unchanged |

1. Provision fresh protected role markers and initialize source enrollment once.
   Create nested 2 MiB plus 17 byte input; capture source inode/size/hash. Hashes
   are fixture comparison evidence, not a production prehash; normal delivery
   keeps the 3N source-hash-during-copy/destination-reread design.
2. For populated state, start the qualification service at `copy_chunk`, require
   custody/job 1/202, then write `next recording` at the producer path. Require a
   real delivery child at its 1 MiB checkpoint, job Claimed/Intent/attempt 1 and a
   zero-filled 1 MiB partial. Kill the seed coordinator before the seed worker
   so a live coordinator cannot allocate a second attempt. Confirm exit and
   NoActiveOwner, exactly `1.part` in staging and a nonempty retained WAL.
3. Snapshot closed database/WAL/SHM/journal and configuration, source receipt/
   binding/lock and producer/custody, destination binding/partials/final/manifest.
   Include inode, size, metadata and hashes; do not open SQLite for observation.
   Record source payload and database identity separately. These snapshots exclude
   atime and ownership epoch/control sidecars, which legitimately change.
4. Stop only owned NFSD (`rpc.nfsd 0`), confirm zero threads and wait at least
   65 seconds with no NFS path access before launching the service. Explicit
   mount maxima/mountstats establish the cache-aging setup. Use no global cache
   flush, remount or noac substitution. This wait is distinct from the service's
   configurable default 60-second shutdown setting; no deadline is changed.
5. Launch without a bootstrap pause hook. Through the bounded local controller,
   observe Starting and one assigned bootstrap worker. Require actual child
   command/UID/capabilities, D state, a pending syscall and NFS/RPC kernel stack
   or wait-channel evidence. Send asynchronous `/healthz`; prove its socket
   connected and request was sent, but no ready reply arrived. Closed local
   database/configuration evidence must still equal the pre-start snapshot.
   Use only local state and `/proc` while storage is unavailable.
6. Kill only the coordinator PID. Twice require a D orphan and OwnerUnavailable/
   exit 2; record raw flock independently. Preserve the old epoch. With the same
   state and alternate listener, service startup, initialization and direct
   transfer must promptly refuse with the surviving-worker ownership diagnostic.
   An occupied listener is not exclusion proof. The existing bootstrap budget
   may request termination before coordinator death; record actual logs, and do
   not change that budget to force the test.
7. After contender probes, SIGKILL the old worker. Restore NFSD using
   `rpc.nfsd -G 10 -L 10 -V 4 -p 2049 2`, wait eleven seconds and confirm two
   threads. Confirm actual old worker/thread exit, free guard and NoActiveOwner
   before restart. The interrupted health request must finish without 200 OK.
   A zombie proves exit/files closed, not PID-1 reaping or NAS-effect settlement.
8. With storage restored, compare local, source and destination evidence exactly
   before recovery begins. Preserve database/WAL/sidecars, original receipt,
   binding, source and partial bytes/inodes. Do not re-enroll, erase an epoch,
   recreate state, reset review or change retry policy.
9. Restart using original state and identical JSON/IDs. Require job 1/202 with
   paths released. For enrolled-empty, only now write the next producer bytes;
   populated state already reused its path after seed 202. Recover normally to
   Committed, attempt 1 or 2 as above, validated manifest and retained original
   source inode/content. Database inode, enrollment and destination binding must
   survive; populated `1.part` must retain its inode/size/hash. Require job 2 absent
   and a replacement coordinator epoch with the original guard/scope identity.
10. Stop cleanly with the bounded controller and confirm exit. Restart/replay
    again; require the same committed job, publication/manifest identities/hashes,
    original receipt/database and old partial, plus unchanged newer producer
    bytes. Stop cleanly and retain all service logs and per-case observations.

## Independent audit and cleanup

After the live matrix and both fresh gates pass:

```powershell
python scripts/verify-nfs-buffered-bootstrap.py rust/validation/<live-run> --production-gate rust/validation/<fresh-production-run> --qualification-gate rust/validation/<fresh-qualification-run>
```

The verifier checks complete tuple coverage, cache aging, real pending bootstrap,
readiness, worker security/exclusion/exit, namespace/state preservation, expected
attempts and replay. It compares current Rust entries to live/fresh archives and
all forty fresh artifact hashes/bytes to live inputs. Gzip metadata may differ;
Rust entries and executable/test bytes must match. Only after all assertions pass
are separate bootstrap evidence/input evidence and canonical SLES reports saved.
Input evidence retains source archives and the exact verifier source. Preserve
all earlier reports; a failed attempt must not become passing evidence.

Restore NFSD before failure termination/wait. After users exit, unmount normally,
unexport and remove only owned containers/export volume/network. Keep cached
images/toolchain volumes. Mark FAILED and retain uncertain resources; use no
forced/lazy NFS unmount or host/NAS changes. Independently inspect both engines
with `podman ps -a` and its rootful equivalent; compare volumes/networks with the
pre-run baseline.

## Testing limits

This matrix covers enrolled-state source bootstrap with aged buffered attributes,
one client/server, joint outage, volatile tmpfs and a shared modern WSL2 kernel.
Cache-only startup can differ; control readiness does not certify destination
health or durable storage. These finite cases do not qualify every warm-cache,
fresh-enrollment or later destination startup phase; explicit stop/deadline/
terminating-orphan branches; server-completed RPC/reply loss, pending sync/COMMIT,
server reboot/failover/reclaim, independent NAS/cache, physical-media/power,
old SLES kernel, workload/endurance or universal latency. Closed snapshot checks
are not live backups. Contender probes precede worker SIGKILL; afterwards the
harness waits for actual exit. Read [testing limitations](TESTING-LIMITATIONS.md).
All first-release gates remain open; production NFS/source deletion stay off.
