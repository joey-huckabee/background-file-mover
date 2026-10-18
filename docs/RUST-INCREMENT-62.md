# Rust increment 62: destination outage during startup recovery

Scope recorded 2026-10-18 before execution on `feature/rust-transfer-coordinator`.
Keep production NFS and source deletion disabled. No Rust input, dependency,
acceptance/retry/review, ownership or shutdown-deadline change is intended.

## Results

`nfs-20261018T152804Z-44b85521` passes all eight selected cases with no cleanup errors. See
[raw evidence](RUST-NFS-DESTINATION-STARTUP-EVIDENCE.json) and the
[step-by-step lab](NFS-DESTINATION-STARTUP-LAB.md).

| Profile | Original state | Signal phase | Actual outcome | Recovery attempt | Result |
|---|---|---|---|---|---|
| debug | enrolled-empty | blocked | blocked_orphan_retains_ownership | 1 | PASS |
| debug | enrolled-empty | terminating | prompt_exit_before_coordinator_kill | 1 | PASS |
| debug | populated | blocked | blocked_orphan_retains_ownership | 2 | PASS |
| debug | populated | terminating | prompt_exit_before_coordinator_kill | 2 | PASS |
| release | enrolled-empty | blocked | blocked_orphan_retains_ownership | 1 | PASS |
| release | enrolled-empty | terminating | prompt_exit_before_coordinator_kill | 1 | PASS |
| release | populated | blocked | blocked_orphan_retains_ownership | 2 | PASS |
| release | populated | terminating | prompt_exit_before_coordinator_kill | 2 | PASS |

All eight starts serve health 200/Running with only destination NFSD stopped;
source NFSD remains two and fresh healthy-source I/O stays bounded. Empty cases
first serve readiness without a destination worker, then confirm custody/202
for a new recording during the outage. Populated cases replay the original job.
All identical claimed replays return job 1/202; job status remains Claimed,
with no false commitment. Runtime workers are real D-state internal delivery
children, without pause/SIGSTOP. This qualifies early destination delivery after
successful source startup, not a destination-blocked source-bootstrap child.

There are 12 direct alternate-port/initialize/transfer guard refusals across
the surviving-orphan records. Read the actual outcome table: prompt stops do
not qualify a retained terminating-worker deadline. Every surviving D worker
retains the old epoch and OwnerUnavailable/2 across three bracketed local/raw-lock
observations. Restoration and confirmed exit of every known old thread precede
replacement. A free raw lock or local process exit alone is not remote settlement.

The actual split is four blocked orphans and four prompt clean stops, with zero
surviving terminating orphans. Stop controllers return Stopped/0 in 1.047–1.172
seconds under the loaded two-second setting. This does not qualify a retained
uncancellable deadline or the default-60 branch at this destination boundary.
Health requests take 1.641–1.922 seconds and blocked-job status 1.688–2.063 seconds,
including Podman overhead; these small-fixture observations are not production
latency guarantees. State-file refusal checks take at most 1.219 seconds.

Original-state recovery preserves database/source inode, enrollment, destination
binding, producer-reused paths and each populated old 1 MiB partial's exact
inode/size/hash. Empty cases commit attempt 1; populated cases commit attempt 2.
Nested manifests/content hashes, stable roots, source retention, cleanup false
and final NoActiveOwner pass. SQLite is legitimately open and can change its
WAL during this path; file snapshots are diagnostic, not frozen or atomic backups.
No re-enrollment, adoption, source deletion or runtime-policy change occurs.

Six normal transfer baselines, twelve state-parent refusals, all 184 state-file
refusals across fourteen preserved fixtures and the existing OS/inherited-lock/
isolated-source-startup checks pass in the same invocation. Endpoints are restored
and normally unmounted before owned containers/volumes/network are removed;
independent inventory is checked. Existing Rust caches/default network and cached
images are retained. No VM module, boot or cgroup bootstrap change is required.

Both servers and the SLES client share one modern WSL2 kernel. The two controlled
NFSv4.1 endpoints use distinct namespaces/IPs/devices/mounts and bounded tmpfs,
not physical NAS or durable-media isolation. In-flight RPC settlement, later
phases, disk/power loss, actual NAS/mount/security/systemd/account policy,
old kernels/CPUs, scale and full release qualification remain separate.
Production NFS and source deletion stay disabled; all eight gates remain open.

## Actual startup boundary and finite cases

Source bootstrap and enrollment authorize the source/local state. They do not
require an available destination. Worker startup launches delivery on a separate
thread, so an enrolled-empty mover can serve readiness while the destination
is unavailable. A populated mover can also serve readiness while a supervised
delivery session blocks opening/validating the destination. Readiness describes
the control plane, not a delivered recording or destination-health guarantee.
This follows the current code; do not change it to manufacture a source-bootstrap
style Starting/unready result.

Eight qualification-only records: debug/release by enrolled-empty/populated state
by coordinator death while blocked/after a two-second local stop. Source and
destination use separate hard NFSv4.1 mounts, two controlled server containers,
network namespaces/IPs and bounded tmpfs exports on one modern VM kernel. State,
SQLite and ownership stay local. Stop only destination NFSD; require source
NFSD two and fresh bounded source write/read/metadata during the outage.

1. Initialize original enrollment/state on healthy endpoints. Populated cases
   seed a 202/Claimed job, producer-reused path, retained WAL and exactly one
   1 MiB attempt-1 partial; confirm seed coordinator then worker exit. Snapshot
   database identity, local files, source/receipt, destination binding and partial.
2. Stop destination NFSD before starting the mover. Require successful source
   startup, health 200 and bounded Running local status. Empty cases first prove
   idle startup has no destination worker, then submit and obtain 202 with actual
   source custody despite the destination outage. Reuse that producer path.
   Populated cases replay the existing key. Both must keep the original job
   Claimed, never falsely Committed, and return 202 for identical claimed replay.
3. Require exactly one actual D-state internal delivery worker without a runtime
   pause or SIGSTOP; record wait channel, UID/capabilities, every thread of the
   known coordinator/worker and original ownership epoch. Require bounded health,
   job status and local control while destination I/O is blocked. Never inspect
   the unavailable destination through fixture observers.
4. Kill only the coordinator in blocked cases. In following-stop cases, record
   prompt clean exit separately from ShutdownIncomplete/2 with a surviving
   worker. Kill the still-live coordinator only for the latter. Surviving D
   workers must retain unsuccessful OwnerUnavailable status/original epoch
   across three bracketed raw-flock/status observations and refuse service on
   an alternate port, initialize and single-transfer competitors. A free raw
   flock alone never authorizes a replacement. Preserve healthy-source evidence.
5. Restore endpoints and confirm all known old threads exited before replacement.
   Preserve original database inode, receipt, source/claimed inode and producer
   reuse. Opening the store, acceptance and delivery scheduling can legitimately
   change SQLite/WAL bytes; record snapshots but do not require the frozen bytes
   used for a source worker blocked before SQLite open. Before recovery, require
   no final payload/manifest and preserve the populated partial exactly.
6. Recover using original state without re-enrollment: empty cases attempt 1,
   populated cases attempt 2 with the old partial inode/size/hash unchanged.
   Verify hashes, nested manifest, root/binding identity, source retention,
   cleanup false, changed authorized epoch only after old exit and final
   NoActiveOwner. Retain six normal baselines, state-parent/184 state-file
   refusals and existing OS/startup checks. Restore before normal unmount and
   owned resource removal; retain resources and fail on uncertain teardown.
7. Run fresh production and qualification GNU/glibc-2.22 zigbuild/ELF/exact SLES
   gates. Verify current source/artifact/driver hashes, maintain stable scenario
   IDs, add SC-096 for this distinct startup situation, update DOC-03/04/05, and
   document each infrastructure/test/cleanup step and
   the actual measured outcomes/limitations.

This is early delivery recovery after startup, not destination-blocked source
bootstrap. It does not qualify every later phase, exact in-flight RPC/settlement,
physical NAS isolation, persistent disk/power loss, systemd/account deployment,
native old kernels/CPUs or automatic takeover. All eight release gates remain open.

## Compatibility and provenance

Fresh production `20261018T150353Z-150c28c0` passes 204 tests per profile and qualification
`20261018T150406Z-a56f9df3-nfs-qualification` passes 205. Each completes GNU/glibc-2.22 cargo-zigbuild,
twenty ELF audits, six negative controls, formatting/Clippy, locked features and
exact SLES execution. There remain 42 external packages, maximum imported
GLIBC_2.18 and loader `/lib64/ld-linux-x86-64.so.2`. Both 61-file source inventories
and all artifacts match; four service binaries are byte-identical to increment 61.
No Rust/dependency/feature or acceptance/retry/review/deadline change is made.

Ten selected-driver hashes, baseline/state-fixture provenance, staged LF-normalized
bytes and evidence JSON are checked. Local links, Python syntax, whitespace and
reference traceability pass. The scenario catalog keeps existing IDs and adds
SC-096 for destination-unavailable startup: 96 SC and six DOC IDs. Historical
source-bootstrap, systemd and other failure evidence is retained unchanged.
