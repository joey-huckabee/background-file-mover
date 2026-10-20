# Source-side NFS synchronization lab

This retained fixture separates actual mover synchronization from independent
source-export transport capability. Read [increment 85](RUST-INCREMENT-85.md)
for measured results and [testing limits](TESTING-LIMITATIONS.md) before using
the evidence. Production NFS and post-delivery source deletion remain disabled.

## Step-by-step infrastructure and execution

1. Use `feature/rust-transfer-coordinator` and the already approved Podman WSL2
   VM. Inspect both engines and retain existing volume/network identities:

   ```powershell
   git status --short --branch
   podman ps -a
   podman volume ls
   podman --connection podman-machine-default-root ps -a
   podman --connection podman-machine-default-root volume ls
   podman --connection podman-machine-default-root network ls
   podman --connection podman-machine-default-root image inspect localhost/background-file-mover-e2-nfs
   ```

   Do not remove another lab's resources, unrelated volumes or the two retained
   Rust caches. Missing infrastructure follows [the fixture setup](NFS-TEST-FIXTURE.md).
   No additional VM boot, host ptrace, NAS administration or real SLES installation
   changes are required by this extension.
2. Run both mandatory compatibility gates and retain their printed directories:

   ```powershell
   python scripts/check-rust-sles.py
   python scripts/check-rust-sles.py --qualification
   ```

   These use pinned cargo-zigbuild GNU x86_64/glibc 2.22 builds, ELF auditing and
   exact debug/release tests in pinned SLES 12 SP5 userspace. Previously passing
   source-identical gates can supply live binaries while fresh gates run; the
   final audit must compare all Rust entries and all forty artifact bytes.
3. Freeze acquisition sources and start the source-focused matrix:

   ```powershell
   python scripts/check-nfs-mount-profile.py --source-sync --production-gate rust/validation/<production-run> --qualification-gate rust/validation/<qualification-run>
   ```

   This selector requires both gates and is mutually exclusive with other
   matrices. The runner repeats 43 mount/inventory controls and snapshots its
   acquisition sources before effects. Do not edit those sources during a run.
   Preserve a failed report and captured inputs before correcting/repeating it.
4. The runner creates only owned containers, an internal network and named
   export volume. A privileged kernel-NFS server provides two root-squashed,
   synchronous 64 MiB tmpfs exports with fsids 68/69 and two NFSD threads. The
   pinned SLES client mounts through unprivileged TCP relays from the beginning.
   Same-share uses disjoint roots on one mount; separate-share uses two mounts
   on the same server. Both active relays are captured because kernel connection
   sharing can carry both exports through one relay. A destination mount address
   does not identify the carrier. This is not two independent NAS appliances.
5. Use buffered NMP-41B NFSv4.1/TCP/sec=sys, hard, ac,async,timeo=10,retrans=1.
   The short retransmission settings are fixture settings, not a deployment
   recommendation. Verify actual mountinfo/device identities and keep local
   SQLite, configuration, enrollment and ownership state on a different device.
   The isolated client observer has SYS_ADMIN, SYS_PTRACE and DAC_READ_SEARCH;
   the external networkless ptrace observer has the latter two. Movers, workers,
   controllers, HTTP and relays run as UID/GID 1000, zero active capabilities,
   NoNewPrivs=1. The native C probe is fixture-only, Zig-built for GNU/glibc 2.22
   and ELF-audited; it is not an additional shipping executable or dependency.

## Actual service discovery before fault selection

Run one actual `claim_apply` worker per layout/profile: four total. Create the
nested 2 MiB plus 17 byte recording and original enrollment, submit asynchronously
and attach the bounded syscall tracer at the existing qualification pause.
Require matching live clock namespaces for client, observer and active relays.
Start raw RPC capture before releasing the pause. Trace fsync/fdatasync entry,
exit, result, FD path, inode, device and mount ID through actual worker exit.
Proc observations do not stat/read target files before synchronization.

Independently decode every retained raw RPC payload and verify its hash and
capture bounds. Correlate requests, replies and captured pairs spanning each
sync entry; count exact mount roots as well as descendants. Keep unknown
compounds explicit. A WRITE elsewhere in the window is not a WRITE caused by
source fsync. Require successful sync returns and normal claim-worker exit.

An observation delay may produce retryable 503. Keep producer paths untouched
until identical-ID replay confirms job 1/202 and released paths. Only then write
new producer bytes. Require Committed/attempt 1, validated payload and manifest,
original private source inode/content, original local database/enrollment,
new producer bytes, no job 2 and normal stop. The generator gains no post-202
monitoring duty. Fixture hashes do not change the service's 3N transfer design.

## Independent source-export withholding proof

On each layout, run a native dirty 4 KiB source-file fsync discovery, observing
all active relays. Select only a decoded WRITE or COMMIT actually inside that
probe's fsync interval. Record the intersection with actual service sync RPCs
separately. Source-export native capability does not require or imply that the
service issued the same RPC.

For the discovered native operation run separate hold/release and drop/reset
controls. Before either action require the matched successful raw server reply
to remain held with no forwarded/released/dropped selected reply; the native
process must be blocked in syscall 74 on the expected source-file FD. Assert
D state, verify NFSD still has two threads and independently read the server's
original inode/device/link-count/4096-byte content hash. Recheck held success
before release/drop. Audit whole operation-vector success and exact raw hashes
against the recorded call/reply transport window.

Release forwards the saved success. Drop discards it and interrupts its TCP
connection; it is not isolated packet loss. Require subsequent successful
fsync, original server identity/content and validated cached replay or uncached
reply followed by semantic FILE_SYNC resend, as actually observed. Never call
these native controls mover live/death recovery tests. If discovery produces
no eligible service operation, do not inject a fictional service COMMIT or
promote namespace LINK/REMOVE loss tests into source-sync loss evidence.

## Audit, cleanup and retained evidence

Wait for fixture and both compatibility processes to exit successfully. Normal
teardown releases relays, stops owned processes, normally unmounts NFS before
unexporting/removing owned resources, and preserves unrelated resources. A
cleanup exception fails the run; do not force/lazy-unmount to conceal it.

Capture `post-run-inventory.json` in the live directory with UTC capture time
and `default`/`rootful` objects. Each contains `containers` (IDs), `volumes`
(names), `networks` (names), and `volume_metadata` objects with Name, CreatedAt,
Anonymous and Labels from `podman volume inspect`. Require no containers on
either engine, only the original two cache volumes/default network rootfully,
and unchanged unrelated default-engine volumes. The retained read-only collector
produces that schema and refuses active containers or unexpected rootful
volumes/networks; the verifier additionally compares unrelated volume metadata
with the prior retained baseline. Run:

```powershell
python scripts/capture-nfs-lab-inventory.py rust/validation/<live-run>
python scripts/verify-nfs-buffered-sync.py rust/validation/<live-run> --source-sync --production-gate rust/validation/<fresh-production-run> --qualification-gate rust/validation/<fresh-qualification-run>
```

The independent verifier checks tuples, source/state/manifest/security/clock
evidence, complete raw wire decoding, native discovery, held server success,
replay, corruption rejection controls, live/fresh Rust archives and artifact
bytes, all fresh ELF audit reports and final inventory. It retains the exact
verifier/gate auditor, source snapshots and probe bytes, raw report/SHA and
canonical fresh SLES reports only after all checks pass.

## What remains unproved

An empty sync interval is finite evidence for the captured workload/cache/kernel,
not proof that source sync never sends RPCs. A native FILE_SYNC WRITE is not a
COMMIT, service recovery or namespace persistence guarantee. Shared modern WSL2
kernel, volatile tmpfs exports, one server/client, small files and sec=sys do not
qualify the original SLES kernel, maintenance RPMs, NAS firmware/cache/power,
server restart/verifier changes, delayed effects, all cache/load/file-size cases
or production deployment. Keep unsupported boundaries open in FR-03/05.


## Retained result and evidence

Increment 85 passes four actual worker observations (32 successful source fsync
calls), two native discoveries and four native hold/release/drop-reset controls.
No captured request/reply occurs inside a source-sync interval or spans entry;
the actual-service/native intersection is empty, so no mover source-sync loss/
death case is qualified. Both native drop controls recover via uncached-reply
then semantic FILE_SYNC resend. Both fresh SLES gates and the independent raw/
build/inventory audit pass, including sixteen actual-proof rejection controls.
See [the full result](RUST-INCREMENT-85.md),
[lossless raw report](RUST-NFS-SOURCE-SYNC-EVIDENCE.json) and
[exact inputs/audit](RUST-NFS-SOURCE-SYNC-INPUT-EVIDENCE.json).
