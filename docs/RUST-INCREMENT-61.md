# Rust increment 61: restart after incomplete managed stop

Scope recorded 2026-10-18 before execution on `feature/rust-transfer-coordinator`.
Keep production NFS and source deletion disabled. No Rust, dependency, ownership,
retry/review, shutdown deadline or shipping-unit policy change is intended.

## Results

`systemd-20261018T144555Z-aa983032` passes both declared records with no cleanup errors. See
[raw evidence](RUST-SYSTEMD-RESTART-EVIDENCE.json). All six explicit systemd start
requests are retained separately from their subsequent manager/job/journal results.
There are 24 direct competing effect-command refusals across both profiles: four
before stop, four after incomplete stop and four after repeated start requests
per profile. Every sampled blocked observation retains the old epoch and a real
D-state old thread, with unsuccessful bounded local control and no authorized
replacement. The three managed contenders per profile fail at listener binding with
AddrInUse, before reaching the local ownership guard. All six no-block start
requests return 0 and each launches a process, then settles to failed/timeout;
none becomes ready or acquires ownership. The unit journal records four starts
per profile (initial owner plus three explicit contenders), three bind failures,
zero application guard refusals and zero scheduled automatic restarts. The managed
starts therefore qualify listener-binding refusal. Managed guard-refusal and
rate-limit saturation remain untested in these two records; separate alternate-port
service and manual initialize/transfer probes exercise the ownership guard.
The no-block start acknowledgement and a transient Started message are not
successful mover startup.

| Profile | Outage after incomplete stop | Quiet window | Unit-journal application guard refusals | Automatic replacement after restore | Result |
|---|---|---|---|---|---|
| debug | 91.953 s | 25.547 s | 0 | No | PASS |
| release | 92.062 s | 25.328 s | 0 | No | PASS |

| Profile | Application stop controller | Manager stop | Three start sequences settled |
|---|---|---|---|
| debug | exit 2, 2.891 s | exit 0, 17.359 s, failed/timeout | 18.859 / 18.438 / 18.625 s |
| release | exit 2, 2.875 s | exit 0, 17.360 s, failed/timeout | 19.047 / 18.516 / 18.641 s |

These fixture measurements include Podman overhead. Manager MainPID is zero
while the old coordinator/worker threads remain live; status preserves the
original ShutdownIncomplete instance/epoch. Repeated starts run into the still
held listener and repeat the manager's two-stage SIGTERM timeout against the
unit group. A new short-lived contender is distinct from an authorized owner.
No activation/refusal growth occurs during the final quiet windows.

Both cases restore storage and confirm all known old threads exited before the
post-restoration observation or explicit recovery. The report records whether
replacement actually occurs during that finite window. No automatic replacement
occurs in either case: all four post-restoration snapshots per profile are
NoActiveOwner over 12.344 / 12.672 seconds. Explicit reset-failed/start of the
original unit then succeeds. This is the measured operator recovery path, not
an indefinite promise that automatic activity can never occur. Original-state
attempt-2 recovery preserves source/database inodes, enrollment, old partial allocation and
valid bytes, producer-reused paths, stable roots and verified manifest/hashes.
Source remains retained, cleanup is false and final status is NoActiveOwner.
The approved fixture is restored and normally unmounted before all owned
containers/volume/network/hierarchy are removed; independent hierarchy absence
is checked. Cached images and the existing build caches are retained.

The manager is the cached Leap 42.3 systemd-228-71.1 equivalent; services and
controllers execute in pinned SLES 12 SP5/glibc-2.22 userspace. Both NFS exports
share one controlled server and modern WSL2 kernel. The finite quiet/restoration
windows do not prove indefinite no-storm behavior, every brief scheduling
interleaving, delayed RPC settlement or remaining release/deployment obligations.
Production NFS and source deletion remain disabled; all eight release gates stay
open. See [the lab procedure](SYSTEMD-LIFECYCLE-LAB.md) section 13 and
[testing limits](TESTING-LIMITATIONS.md).

## Finite cases and pass conditions

Two qualification-only cases, debug and release, using the approved equivalent
systemd 228 manager and exact fresh GNU/glibc-2.22 SLES-gated artifacts. Retain the
existing disposable unit's Restart=on-failure, RestartSec=1, StartLimitInterval=10,
StartLimitBurst=2, application wait 2 and manager stop timeout 8. These shortened
fixture settings do not change the default configurable 60-second application wait.
Both source and destination are separate hard NFSv4.1 exports on one controlled
server; state/SQLite stays local. Reuse increment 60's infrastructure and teardown.

1. Accept a nested recording, reuse the producer path, capture original source,
   database, enrollment and partial-copy evidence, then release the mid-copy pause
   into an actual server outage. Require a real D-state worker, not SIGSTOP.
2. Stop the managed unit and independently invoke the bounded application stop
   controller. Require ShutdownIncomplete with surviving old threads and unchanged
   ownership. Record manager completion separately from application exit.
3. While storage remains unavailable, make exactly three spaced explicit unit
   start requests. Observe local status, every known old main/worker thread,
   ownership epoch, manager properties and journal. Classify a manager refusal
   separately from a launched contender's application guard refusal. No authorized
   replacement is allowed before old exit. Probe direct competing effect commands.
4. Hold the outage for at least 90 seconds after incomplete stop, with at least
   20 seconds of quiet observation after the last settled explicit request. Each
   request must settle within a finite 30-second observation window. At most six
   application guard refusals may result from the three requested start sequences;
   at most seven unit starts (including the initial owner) and six scheduled
   restarts may be observed across those sequences.
   Capture actual manager activation/refusal evidence and fail on continued
   activation/refusal growth during the quiet window. This is finite evidence,
   not an indefinite no-storm guarantee or proof of every brief interleaving.
5. Restore storage, require confirmed exit of all known old threads, then observe
   local/manager state before any explicit recovery request. Record whether any
   automatic replacement occurs. If none occurs, explicitly reset failed state
   and start the original unit. Require original-state attempt-2 recovery, preserved
   source/database/enrollment/old partial, producer-reused path, valid manifest and
   hashes, cleanup false, changed authorized epoch only after old exit and final
   NoActiveOwner. Never delete/rebind state or kill/adopt an unknown orphan.
6. Restore storage before cleanup; normal unmount precedes removal of the owned
   client/server/network/volume and nonce-owned hierarchy. Fail and retain resources
   on unconfirmed safe teardown. Run fresh production and qualification SLES gates,
   verify source/artifact/driver provenance and maintain SC-034/092/093/095 and
   DOC-03/04/05, the lab procedure, operator instructions and testing limits.

Remaining operation phases, independent endpoints/NAS, in-flight RPC settlement,
power durability, actual account/persistent deployment, exact SLES maintenance
patches and native old-kernel/CPU behavior remain outside this finite increment.
All eight release gates remain open pending their full closure evidence.

## Compatibility and provenance

Fresh production `20261018T142203Z-f3516f7e` and qualification
`20261018T142214Z-790fc1f9-nfs-qualification` pass 204 and 205 tests per profile respectively.
Each gate completes GNU/glibc-2.22 cargo-zigbuild, twenty ELF audits, six negative
controls, locked dependency/features, formatting/Clippy and exact SLES execution.
The graph remains 42 external packages; maximum imported GLIBC_2.18 and loader
`/lib64/ld-linux-x86-64.so.2` remain unchanged. Both 61-file Rust inventories,
source archives and artifacts match current bytes; all four service binaries are
byte-identical to increment 60. No Rust input or fixture unit template changes.

Seventeen executed driver hashes and four actual installed helper hashes match
source; staged bytes are checked after LF normalization. Evidence JSON, local
links, Python syntax, whitespace, traceability and stable 95 SC/six DOC IDs are
checked separately. Previous stop/death and local lifecycle evidence is retained.
