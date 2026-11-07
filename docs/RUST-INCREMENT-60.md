# Rust increment 60: systemd 228 with hard-NFS workers

Scope recorded 2026-10-18 on `feature/rust-transfer-coordinator` before execution.
Keep production NFS and source deletion disabled. No Rust/dependency, retry,
review, ownership or shutdown-deadline change is intended.

## Results

`systemd-20261018T135226Z-2f68b790` passes all four selected combined NFS/systemd records, with
no cleanup errors. See [raw evidence](RUST-SYSTEMD-NFS-EVIDENCE.json).

| Profile | Case | Actual outcome | Result |
|---|---|---|---|
| debug | nfs-stop | incomplete-worker-retained | PASS |
| debug | nfs-death | D-state orphan retained; failed unit; no automatic replacement observed | PASS |
| release | nfs-stop | incomplete-worker-retained | PASS |
| release | nfs-death | D-state orphan retained; failed unit; no automatic replacement observed | PASS |

All cases observe a real D-state worker after the controlled pause is released
into a joint server outage, with NFSD threads confirmed zero. Both endpoints
are NFS on distinct server/client devices and mount IDs; state stays local.
Cross-export hard linking refuses without changing the original file. The
manager/network/export configuration and exact source/driver/image/binary
identities are retained in the report. There are 24 explicit competing
effect-command refusals; ordinary same-port binds remain distinct from guard
refusal. Managed restart observations record actual old process/thread states
and local epochs, not just a new MainPID or a free raw flock.

Sixteen command refusals occur before signals and eight after incomplete managed
stops; no direct post-death competitor is launched in these four cases. Both
death cases retain the old D-state worker and epoch through all five local
observations (OwnerUnavailable/exit 2). The manager reaches failed/timeout with
MainPID 0; its outage journal has no automatic restart/replacement. Recovery
explicitly starts the unit after restoration and confirmed old-thread exit.
This does not qualify eventual automatic recovery after an incomplete stop or
indefinite restart/storm behavior; those remain deployment-policy obligations.

The independent two-second stop controllers return ShutdownIncomplete/exit 2
in 2.875 seconds (debug) and 2.890 seconds (release), including Podman overhead.
Manager stop jobs return exit 0 after 17.375/17.328 seconds, with MainPID 0 and
Result=timeout, while the coordinator and D worker are still live. Application
ownership therefore remains authoritative for exclusion; manager completion is
not worker-exit or NAS-settlement proof. No prompt-exit branch occurred here.

All four cases recover attempt 2 from original state after restoration and
confirmed old-thread exit. Source/database inodes, enrollment, old partial
allocation/content and producer-reused paths are preserved. Manifest/hash,
stable roots, source retention, cleanup false and final NoActiveOwner checks
pass. NFS is restored and normally unmounted before removing the client/server,
owned volume/network and nonce-owned legacy hierarchy. No fixture remains;
the existing Rust caches/default network and cached fixture images are retained.

Actual stop outcomes above distinguish retained-worker deadlines from prompt
kernel-assisted exit. Neither proves arbitrary NFS calls cancellable or NAS
settlement; sampled epoch/exit ordering is not an exhaustive interleaving trace.
One controlled modern server with two tmpfs exports does not qualify independent
NAS failures, persistent storage, reboot/power durability or all operation phases.
Manager is the pinned Leap 42.3 systemd-228 equivalent and glibc 2.22; services
execute in pinned SLES 12 SP5/glibc-2.22 userspace on `6.18.33.2-microsoft-standard-WSL2`.
Exact SLES-maintenance patches, old kernel/CPU behavior and production-scale
workloads remain separate. Production NFS and source deletion stay disabled;
all eight first-release gates remain open.

See [the lab procedure](SYSTEMD-LIFECYCLE-LAB.md) section 12 for each infrastructure,
test and teardown step, and [testing limits](TESTING-LIMITATIONS.md) for remaining
obligations. Historical local-228/preflight evidence is unchanged.

## Finite qualification and pass conditions

Four qualification-only records: debug/release by managed stop/managed
coordinator death at a mid-copy boundary. Source and destination use two
distinct tmpfs-backed NFSv4.1 hard mounts on one controlled server, with SQLite
and ownership state local. Use the approved 228-equivalent manager/bootstrap
and exact gated GNU/glibc-2.22 SLES-root binaries. First observe a real D-state
delivery worker after releasing the local pause into an actual server outage;
SIGSTOP or an unreleased pause cannot substitute for that observation.

For managed stop, use unit-owned SIGTERM and independently call the same-user
bounded controller (loaded wait 2, manager timeout 8). Record prompt kernel-assisted
exit separately from genuine ShutdownIncomplete with a surviving worker. Require
local status/controller bounds, retain exclusion while old workers survive, and
never count prompt exit as qualification of an uncancellable deadline branch.

For coordinator death, kill only the managed main PID, retain bounded restart
attempts and sample local ownership while the mounts remain unavailable. A new
authorized epoch requires confirmed old main/worker exit; a short-lived rejected
contender is distinct from an authorized replacement. Record actual restart,
Starting/readiness and refusal outcomes. No local exit/timer proves NAS settlement.

After restoring the owned server, require confirmed old exit, original-state
attempt-2 recovery, preserved database/source inodes and enrollment, retained old
partial allocation/content, producer-reused paths, verified manifest/hashes,
stable roots, source cleanup false and final NoActiveOwner. Restore NFS before
cleanup; unmount normally before removing the client/server. Preserve resources
and fail if safe teardown cannot be confirmed. Require complete named-hierarchy,
container, volume and network cleanup and fresh production/qualification SLES gates.

Update SC-034/092/093/095, DOC-03/04/05, the step-by-step lab and testing limits.
This does not qualify every operation, independent NAS failures, exact in-flight
RPC settlement, real NetApp/Isilon behavior, persistent storage/power loss,
old kernels, exact SLES-maintenance RPM patches or production-scale workloads.

## Compatibility and provenance

Fresh production `20261018T132844Z-481c0a54` passes 204 tests per profile;
qualification `20261018T132844Z-ee663085-nfs-qualification` passes 205 per profile.
Each gate completes GNU/glibc-2.22 cargo-zigbuild, twenty ELF audits, six negative
controls, formatting/Clippy/locked feature checks and exact SLES userspace tests.
There are still 42 external packages, maximum imported GLIBC_2.18 and interpreter
`/lib64/ld-linux-x86-64.so.2`. Both 61-file Rust inventories match current bytes;
all exact artifacts are checked and the four service binaries are byte-identical
to increment 59. No Rust input/dependency/feature or retry/review change is made.

Seventeen driver hashes and four actual image helper hashes are checked against
executed bytes and staged source after LF normalization. Source archive digests,
machine evidence, stable 95 SC/six DOC IDs, local links, Python/JSON, whitespace
and reference traceability are checked separately. Passing ABI evidence alone
does not qualify NFS semantics or the manager/deployment profile.
