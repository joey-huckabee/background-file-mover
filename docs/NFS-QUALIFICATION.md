# Retained NFS qualification capability

Increment 25 requires version-2 source/destination bindings and an exclusively
preprovisioned empty service-owned mode-0600 `.file-mover/coordinator.lock` at
each root. Do not reuse version-1 observed state or mix directory-lock and
regular-lock binaries; see [cutover restrictions](RUST-INCREMENT-25.md).
The ownership fixture now requires peer startup exclusion and tests actual
claim/delivery worker lock custody after coordinator death. Empty-scope clean
release and peer file-lock probes do not authorize independent-state takeover.
Qualification results must distinguish cooperative exclusion from the still
unimplemented partition/reclaim/takeover fence.

The user explicitly requested keeping this capability. Preserve its Cargo
feature, build identification, compatibility gates and fixture runner for future
qualification/regression work. Do not remove it when production NFS support is
eventually approved; changing that decision requires a new user direction.

## Build distinction

`file-mover/nfs-qualification` forwards to `mover-fs/nfs-qualification`. Both
features are disabled by default. The qualification build adds NFS filesystem
magic `0x6969` to the source/destination root allowlist. Ownership, permissions,
singleton locks, durable receipts, copying, verification, publication and source
retention use the same implementation as the production build. There is no
alternate transfer engine and no runtime option or environment variable that
enables NFS in a production binary.
From [increment 23](RUST-INCREMENT-23.md), compiled capability also requires an
explicit `source_binding` and preprovisioned source marker. The fixture provisions
them through `scripts/nfs_binding.py`; service startup never creates them. A
declared NFS source cannot fall back to an underlying local directory. Strict
observed identity pins do not authenticate a server/export or provide fencing.

Increment 24 also requires explicit `destination_binding` configuration and a
preprovisioned private destination marker. The same fixture helper provisions
both roles. Destination policy is pinned at acceptance without accessing the
destination; a recording child validates/pins its first observation before
allocation. Missing destinations defer delivery, while foreign bindings require
operator review. Keep full runtime regression evidence after effect-path changes.

Both builds identify themselves with `--check-platform`:

```text
file-mover 0.1.0 local-claim prototype build=production
file-mover 0.1.0 local-claim prototype build=nfs-qualification
```

Qualification service/transfer startup also prints a conspicuous warning.
Internal workers do not print that warning into their private IPC channels.
The label is derived from the filesystem crate's actual compiled capability,
including builds that enabled the leaf feature directly.

Qualification artifacts are for the controlled fixture and must remain outside
deployment packaging. They are retained under a separate validation run and have
`-nfs-qualification` filenames. This repository currently has no Rust deployment
packaging; future packaging must select production artifacts explicitly and
verify their build label. The feature adds no dependencies or package versions.
Production NFS support and source deletion remain disabled.

## Equivalent compatibility gates

Run both from the Windows checkout using native WSL Podman:

```powershell
wsl -d Ubuntu -- bash /mnt/c/Users/Joey/Documents/GIT-GitHub/joey-huckabee/background-file-mover/scripts/test-rust-wsl.sh
wsl -d Ubuntu -- bash /mnt/c/Users/Joey/Documents/GIT-GitHub/joey-huckabee/background-file-mover/scripts/test-rust-wsl.sh --qualification
```

On a Linux runner, the entry points are `python3 scripts/check-rust-sles.py` and
the same command with `--qualification`. Each gate runs formatting/Clippy,
cargo-zigbuild debug/release builds for x86_64 GNU/glibc 2.22, audits every ELF
artifact and executes exact artifacts in pinned SLES 12 SP5 userspace. Reports
record build mode and actual workspace features. Build labels are checked in
both smoke execution and an executable/API test. CI has a matrix for both modes.
No host-only test pass replaces either gate.

## Controlled normal-operation baseline

After both gates pass, reuse their exact artifacts:

```powershell
python scripts/check-nfs-boundaries.py rust/validation/<production-run> --qualification-gate rust/validation/<qualification-run> --isolated-startup
```

The runner verifies both source snapshots, artifact hashes and labels. It also
checks that service, source initialization and single-file transfer refuse an
NFS database/state parent in both profiles and build modes, without creating a
guard/database or opening the deliberately absent source. These local-state
refusals do not qualify cross-host exclusion or delayed RPC settlement. It first
proves both production profiles reject a reachable NFS source without creating
SQLite. `scripts/nfs_baseline.py` then drives the actual qualification service
through REST in pinned SLES userspace, using the saved private hard-mounted
NFSv4.1 fixture. SQLite stays local. It tests NFS as source, as destination and
as both, in debug and release, asserting actual filesystem types.

Each case submits three files: a top-level text file, a nested file larger than
the copy buffer, and an empty file. Successful cases check stable-ID replay,
immediate reuse of original paths after 202, retained private source contents,
destination bytes, independently computed hashes and the exact V1 completion
manifest. Test hashing is outside the service; normal service I/O remains 3N.

Blocked cases retain their response, status, service log and available integrity
evidence. The runner reports a failed baseline rather than claiming unsupported
operations work. It does not silently introduce overwrite or deletion fallbacks.
All cases are attempted, then normal-operation failure prevents advancing to the
outage phase. The owning runner restores NFS and confirms process completion and
unmount before removing only its own resources. See [NFS-TEST-FIXTURE.md](NFS-TEST-FIXTURE.md).

## Qualification boundary

For root/ownership diagnostics, run the same baseline runner with both gate
directories and `--isolated-startup --ownership` (omit `--runtime` unless also
repeating that separate matrix). It creates one additional pinned client,
records distinct network/mount namespaces and server-side NFS client identities,
compares actual coordinator exclusion between clients, and includes a regular-file
remote-lock positive control. It then removes only the peer's mount and tests
startup at the same pathname/configuration on the underlying local filesystem.
No jobs are submitted while coordinators overlap or the mount is absent. The
current missing-mount probe includes a copied matching NFS marker and requires
both builds to refuse the local stand-in without changing an existing database.

See [increment 22](RUST-INCREMENT-22.md) and
[the root/ownership design](ROOT-OWNERSHIP-DESIGN.md). Diagnostic completion is
separate from protection: inspect `ownership.probe_status`, each startup
exclusion/refusal field and `cooperative_exclusion_passed`. Increment 25's eight
ownership cases cover two startup exclusions, four actual worker inheritance/
original-state recovery cases and two missing-mount cases. `protection_complete`
and `production_authorized` remain false because fencing is unqualified, even
when cooperative exclusion passes. PASSED is not production approval.
The two clients intentionally declare the
same coordinator identity, so that probe still measures exclusion of a cloned
identity, not marker mismatch between different IDs. The retained full interruption and
long-outage reports remain separate evidence with different scopes.

For deterministic real-worker interruption, add `--runtime` to the fixture
command above. It requires both passing gate directories and first repeats the
normal baseline. [Increment 18](RUST-INCREMENT-18.md) explains its claim, partial
copy, coordinator-death and manifest-intermediate cases and evidence boundaries.
The qualification-only pause controls are permanent fixture capabilities, have a
60-second pause budget and require a private local rendezvous directory. Production
ignores them. Do not set them for ordinary service execution or deployment.

[Increment 19](RUST-INCREMENT-19.md) adds source-read and destination-verification
interruption. For those selected points only, the worker issues per-file Random
and DontNeed advice before the rendezvous, then enters the payload read loop.
Advice is not proof of cache eviction: a local `read-completed` observation is
created after the loop and before post-read metadata checks. The fixture fails
if that marker appears during the outage or the assigned reader is not observed
in kernel-blocked state `D`, avoiding a cached payload read being
mistaken for a pending read. These observations never authorize durable effects.
Production issues neither advice nor markers. Cache advice adds no normal
payload pass, dependency or production requirement.

See [the scenario catalog](RUST-SCENARIOS.md) for the user-visible situations and
documentation work fed by these qualification results.

[Increment 20](RUST-INCREMENT-20.md) adds explicit `claim_link` and `file_link`
points after the new exclusive link is synchronized and before old-name removal.
These cases hold the local rendezvous while NFS is unavailable, interrupt the
worker, restore connectivity and require both owned aliases before restart.
Recovery must preserve the recorded inode and remove only its old binding.
This is a deterministic process crash at a real NFS link intermediate, not an
in-flight unlink RPC test. The latter remains unqualified.

[Increment 21](RUST-INCREMENT-21.md) adds three-minute outage cases to the same
`--runtime` command for claim application and destination verification in both
profiles. The worker is released immediately into real NFS operations; the pause
budget is not extended. The runner samples health/status and kernel-blocked
assignment identity throughout the outage, makes three sequential same-ID retries,
then restores NFSD and requires live recovery on attempt 1 without restarting
the service. A retry left waiting in the single-slot submission queue can cause
later retries to return retryable 503 `service_busy`; `handoff_pending` is also
valid before custody is complete. No 503 releases source paths.
These checks do not simulate concurrent floods or server reboot.
See the increment results before treating SC-051/052 as qualified.

To rerun just those four runtime cases after an assertion change, append
`--long-outages-only` to `--runtime`. Normal baseline and OS/startup checks still
run; report `runtime_scope` identifies the restricted runtime scope. It is not
a replacement for the full runtime suite after changes to service effects.
Each runtime case also writes a result JSON after its cleanup, so an earlier
failure can be inspected before the entire fixture completes.

If Ubuntu's post-reboot user runtime prevents native rootless Podman startup,
the same gate can use the healthy Podman WSL2 engine from Windows:

```powershell
$env:CONTAINER_CONNECTION = 'podman-machine-default-root'
python scripts/check-rust-sles.py
python scripts/check-rust-sles.py --qualification
```

Use this environment selection for the gate process; no persistent connection
default needs changing. Sources still build under `/work` in the pinned Linux
builder, and every artifact still runs in pinned SLES userspace. Engine-local
toolchain/registry caches are retained. This changes neither the target nor the
compatibility checks. Record the chosen engine in the increment results.

[Increment 17](RUST-INCREMENT-17.md) records the no-clobber rename refusal measured
on the fixture and the owned link/unlink recovery implementation. Worker diagnostics
are observations, never authorization to commit an effect or delete retained data.

Allowing NFS in a test build is not production authorization. The normal baseline
and selected runtime cases provide one-client evidence for their measured
operations. Cross-client fencing, stable export/mount ownership, outages beyond
the selected three-minute cases, concurrent flooding and queue-memory limits,
in-flight link/unlink RPCs, other synchronization boundaries, server reboot and power-loss durability
remain separate qualification before production enablement. Containers
use SLES/glibc userspace on the runner kernel; no actual SLES host testing is
required by this plan.

The current service requires explicit source initialization before fixture
readiness. [Increment 27](RUST-INCREMENT-27.md) records persistent source/state
pairing and selected interrupted enrollment cases. Qualification helpers initialize
only their own newly provisioned scopes; restart uses original state. Fresh-state
refusal after lock release is distinct from exclusion while an old worker holds
the lock. Neither establishes a partition/reclaim or storage takeover fence.

[Increment 28](RUST-INCREMENT-28.md) adds the `enrollment_directory_sync` pause
between file and namespace sync, plus `enrollment_read` for actual receipt reads
during startup shutdown. The read case must observe a kernel-blocked child and
no read-completed marker before requesting shutdown. Record observed child/service
exit relative to server restoration; no prompt-cancellation guarantee is assumed.
Enrollment write/sync fault values simulate selected failures only in qualification
builds. Production ignores those controls; simulated ENOSPC/EIO is not actual NFS
server storage-error qualification. The new `nfs_enrollment.py` helper is retained
with the rest of the owned fixture and its driver hash recorded in reports.

[Increment 29](RUST-INCREMENT-29.md) adds opt-in `--enrollment-storage` with a
separate server tmpfs capped at 4 MiB/128 inodes. It tests actual server ENOSPC
before receipt creation and during receipt writing, without injected errno
controls. Only fixture filler files are removed to restore capacity; receipts,
producer data and original databases are preserved. It requires qualification
artifacts and retains baseline/OS/startup checks. Add `--ownership --runtime`
only when a full rerun is intended; the focused storage report does not claim
those suites ran. Consult the increment for actual results and retry decisions.
Tmpfs exhaustion does not establish physical-disk, EIO or power-loss durability.

[Increment 30](RUST-INCREMENT-30.md) adds `--delivery-storage`: a separate bounded
32 MiB server tmpfs with 1 MiB left available before a 2 MiB recording is submitted.
Real copying must exhaust it, retain source custody, reach review, and recover via
audited resume after capacity restoration, both live and across original-state
restart. The option can run alongside `--enrollment-storage`; neither implies the
full `--runtime`/`--ownership` suite was requested. Consult the increment for
actual results and generic payload-diagnostic limitations. Keep the new helper
and recorded driver hashes with the permanent fixture capability.

[Increment 31](RUST-INCREMENT-31.md) adds operation-specific payload errno logs
and retained qualification-only `FILE_MOVER_QUALIFICATION_PAYLOAD_FAULT` controls
for selected read/write/sync boundaries. Production ignores those controls.
The real `--delivery-storage` cases use no injected fault and now require the
actual copy-write ENOSPC diagnostic once per failed attempt. Retry/review/resume
and effect authorization are unchanged; diagnostic guidance is not a receipt or
storage fence. Simulated EIO is distinct from actual server/hardware failure.

Increment 32 retains qualification-only `FILE_MOVER_QUALIFICATION_EFFECT_FAULT`
for selected staging/manifest operation labels (EIO before the native call).
Production ignores it. This is a synthetic return-error control, separate from
actual server outages/ENOSPC; relocation keeps its existing deterministic
checkpoints. See [increment 32](RUST-INCREMENT-32.md) and SC-073 for results,
unreceipted-allocation refusals and final-manifest ambiguity. Keep all existing
ownership/fencing and production-NFS restrictions.

Increment 33 extends `--delivery-storage` with two pending-restart automatic
capacity recovery cases in addition to the four existing review/resume cases.
The native fixture preserves saved deadlines and old attempts, observes the new
capacity status code and rejects attempts observed before their deadline. It
never injects ENOSPC in these cases. See [the retry policy](DELIVERY-RETRY-POLICY.md)
and [increment 33](RUST-INCREMENT-33.md) for actual results and scope. Schema 11 preserves original retry/enrollment state while widening the retry-code
constraint. The private delivery session uses protocol version 2; persisted receipts and bindings keep
their existing versions. Keep all production NFS/fencing restrictions.

## Source-space probe controls (increment 36)

Qualification-only `FILE_MOVER_QUALIFICATION_SOURCE_SPACE_FAULT=unavailable`
returns a source probe I/O error. Existing pause controls select
`source_space_statistics` immediately before the native descriptor statistics
call. Production ignores both selectors. The default-off guard never dispatches
this worker. Local target API tests exercise native measurements, explicit
unavailability and a paused real child killed at its probe deadline, with replay/
health retained. This does not qualify an in-flight hard NFS statistics call,
source disk/quota exhaustion or remote cancellation. Extend the retained fixture
before claiming those cases. The source-space child has its own version-1 bounded
request/reply; existing delivery wire 2 and persisted receipt/binding formats do
not change. Parent and child remain the same executable.

## Bounded source admission qualification (increment 38)

Opt-in `--source-storage` requires `--qualification-gate` and adds the permanent
`nfs_source_storage.py` helper to the existing driver. It uses only a separate
32 MiB/512-inode server tmpfs source export, with local state and destination.
Consume its owned filler to native ENOSPC, release 1 MiB of metadata headroom,
and test new-key refusal, claimed replay and partial recovery while low. Remove
only the filler and retry the identical refused ID with the same policy and live
coordinator. Check all claimed/final payloads and manifests and preserve reused
producer paths. No synthetic fault/pause selectors are needed.

Example, replacing the run directories with exact passing current-source gates:

```powershell
python scripts/check-nfs-boundaries.py rust/validation/<production-run> --qualification-gate rust/validation/<qualification-run> --source-storage --isolated-startup
```

The driver retains baseline and OS/startup checks. Other optional runtime,
ownership and storage suites run only when selected. Consult
[increment 38](RUST-INCREMENT-38.md) and its report for actual results; the option's
existence is not qualification. Tmpfs block depletion does not establish disk,
quota/inode, blocked statistics RPC, export replacement, power-loss or fencing
behavior. Keep production NFS and deletion disabled.

## First-release single-host ownership obligations

[Increment 41](RUST-INCREMENT-41.md) revises the
[ownership contract](NFS-OWNERSHIP-FENCING-CONTRACT.md) around confirmed single-host,
fixed local state/config and private NFS working areas. SH-01–14 cover shared
local guard/inheritance, manual/systemd conflicts, default-60 configurable stop
controller and actual NFS original-state recovery/refusal. [Increment 42](RUST-INCREMENT-42.md)
implements the local guard/handoff with selected local evidence. [Increment 43](RUST-INCREMENT-43.md)
adds the configurable wait and bounded local controller. Remaining hard-NFS drain,
systemd and storage/lifecycle cases stay pending. The earlier NF-01–18 have an
explicit carry-forward/deferred mapping, not silent passing status.

Qualify both same-share and separate-share layouts. Actual deployment NFS version
and mount/security settings remain unknown; retained fixture evidence is v4.1 only.
Local lock release, killed containers, confirmed child exit and pre-call pauses
cannot alone prove old client/server RPCs or writeback have settled. Preserve
review for unsafe uncertainty. Shared-kernel clients are appropriate for this
same-host guard profile but do not prove other hosts are fenced or power-loss
semantics. No actual SLES host or NAS-admin facility is assumed. Keep container
userspace, ELF and exact-target gates; qualify actual systemd lifecycle separately.
Production NFS and source deletion remain disabled.

Increment 42's [local-instance fixture evidence](RUST-NFS-LOCAL-INSTANCE-EVIDENCE.json)
records all six normal baseline cases, 12 NFS-state-parent refusals in both
profiles/build modes, and retained isolated startup/OS lock checks passing with
the final audited binaries. No runtime death/long-outage, two-client ownership
or capacity-storage suite is selected in that report; earlier reports retain
their original scope. See [increment 42](RUST-INCREMENT-42.md) for local worker
inheritance/death evidence and remaining state-layout/lifecycle limits.

Increment 43's [lifecycle fixture evidence](RUST-NFS-LIFECYCLE-EVIDENCE.json)
records all six normal transfers followed by local Running/clean Stopped for the
same instance, 12 mounted-NFS state-parent refusals, and independent local
Starting status during actual hard-NFS bootstrap (0.859 seconds including Podman
execution overhead). Retained signal/interruption checks also pass. See
[increment 43](RUST-INCREMENT-43.md) for measured local two-second/default-60
controller timeouts and the remaining uncancellable-worker/systemd qualification.
No runtime death/long-outage, ownership or capacity suite is selected here.

[Increment 44](RUST-INCREMENT-44.md) extends the retained fixture with SQLite
file-layout admission: foreign UID files and individual NFS bind mounts of the
database, WAL, shared memory, rollback journal, instance guard and control name.
Mounted-file refusals run with the NFS server stopped and preserve original
bytes/identities/modes. This is admission evidence in a disposable container,
not actual production NFS, systemd, delayed-effect settlement or durability
qualification. The existing normal-transfer/lifecycle and startup/lock checks
remain required regressions.

[State-layout evidence](RUST-NFS-STATE-LAYOUT-EVIDENCE.json) records final fixture
`nfs-20261017T114805Z-60f221d4`: 48 foreign-UID and 72 mounted-file refusals,
maximum 0.953 seconds, unchanged recorded hashes/identities/owners/modes, six
normal transfer/lifecycle regressions, 12 NFS-state-parent refusals and retained
isolated-startup/OS interruption checks. Cleanup completed without errors.
A prior fixture failed during restricted-root setup before the new matrix;
[increment 44](RUST-INCREMENT-44.md) records its correction and limits.

## Retained real-worker shutdown matrix

Use --shutdown with passing production and qualification gates plus
--isolated-startup. It selects 12 real-worker cases: claim, copy and verification,
each with a short two-second budget and omitted/default 60, in debug and release.
The complete normal-transfer, state-layout and startup/OS regressions still run.
For unchanged Rust inputs, existing passing gates are reusable only after the
driver verifies the complete source snapshot/inventory and exact artifact hashes.
Any Rust input change requires new mandatory gates first.

```powershell
python scripts/check-nfs-boundaries.py rust/validation/20261017T111519Z-1ecdab26 --qualification-gate rust/validation/20261017T111519Z-8fa9a462-nfs-qualification --isolated-startup --shutdown
```

Select --shutdown separately from --runtime; --long-outages-only remains a
--runtime selector. Existing runtime, ownership and capacity capabilities remain
available. See [increment 45](RUST-INCREMENT-45.md) for actual outcomes and scope.
The runner stops the server and releases the worker rendezvous, verifies a real
kernel D-state assignment, then exercises independent local status/stop, same-state
competitor refusal, first-deadline behavior and original-state recovery. Report
prompt exit separately from a retained child beyond the deadline; do not use a
userspace pause as proof of uninterruptible NFS. Never restart before restoration
and confirmed old process exit in these cases, even if the local guard is free.


[Recorded shutdown evidence](RUST-NFS-SHUTDOWN-EVIDENCE.json) passes all 12
cases: five deadline-held workers and seven prompt exits, 51 competing starts
refused, all original-state recoveries verified. Normal transfer, 12 NFS-parent
and 120 SQLite-file admission regressions passed; cleanup had no errors.


## Retained coordinator-death matrix

Select `--coordinator-death` with passing production and qualification gates and
`--isolated-startup`, separately from `--runtime` and `--shutdown`. The matrix
uses the same hash-checked SLES binaries and retains the six normal-transfer,
12 NFS-state-parent, 120 SQLite-file and isolated startup/OS regressions.

```powershell
python scripts/check-nfs-boundaries.py rust/validation/20261017T145042Z-b718db7b --qualification-gate rust/validation/20261017T145053Z-11bb8adc-nfs-qualification --isolated-startup --coordinator-death
```

[Increment 46](RUST-INCREMENT-46.md) defines the 12 cases and records outcomes.
Kill only the coordinator PID after actual kernel blocking, or after ordinary
stop leaves a terminating worker alive. Confirm coordinator exit and repeated
orphan D state/local guard contention before competing starts. Require bounded
OwnerUnavailable, no competing writer and original-state recovery after restored
storage and confirmed old-worker exit. Prompt stop before the selected kill point
is a separate outcome, not surviving-terminating-worker evidence. Both profiles
must actually observe a surviving terminating child for the matrix to pass.
Unexpected early guard release fails before starting competitors. Do not use
local lock release or process exit as NAS settlement proof.


The initial increment 46 matrix failed during verification termination after
coordinator death. Its evidence is retained separately. The diagnostic driver
brackets guard/status probes with D-state observations, skips competitors after
unexpected guard loss, and may continue safe recovery/remaining cases. Such a
case remains failed and the complete fixture exits nonzero even if all retained
regressions pass. Compatibility success never overrides failed ownership proof.


[Complete coordinator-death evidence](RUST-NFS-COORDINATOR-DEATH-EVIDENCE.json)
is **FAILED**: ten worker cases passed and both verification-termination cases
lost ownership while D. All 12 safe original-state recoveries and all retained
regressions passed, with clean teardown. The matrix remains a release blocker;
production NFS and deletion remain disabled. See increment 46 for exact scope.


## Lifetime-retention regression

[Increment 47](RUST-INCREMENT-47.md) retains the same `--coordinator-death` matrix
and the failed increment 46 evidence. Run twelve core cases, with at most three
additional terminating-verification repetitions per profile if needed to observe
the original kernel-exit condition (at most eighteen cases total). A prompt exit
is recorded separately and does not satisfy that coverage requirement. The
regression records physical flock closure separately from logical ownership. All orphan D-state cases require
OwnerUnavailable/exit 2 and three actual effect-command refusals, even if the raw
flock is free. To pass, both debug and release must observe a kernel-closed guard
while logical exclusion remains. Restore storage and confirm exit before recovery.
State-file regression coverage additionally mounts NFS on workers.json/workers.next
and requires prompt refusal without touching the blocked remote file.

Use fresh passing production/qualification SLES gates after Rust changes. This is
one-client/shared-kernel evidence, not NAS settlement or full SH-04 closure.


Increment 47 reproduction command (passing gates are required):

```powershell
python scripts/check-nfs-boundaries.py rust/validation/20261017T162146Z-b28d902b --qualification-gate rust/validation/20261017T162159Z-32bce9a2-nfs-qualification --isolated-startup --coordinator-death
```

The expanded state matrix retains 120 prior refusals and adds 64 lifetime-file
owner/mount/control refusals across fourteen preserved fixtures. No production
NFS or source cleanup is enabled by this command.

The saved [increment 47 evidence](RUST-NFS-OWNERSHIP-EXIT-EVIDENCE.json) passes
thirteen cases (twelve core plus one release verification repeat), including
actual raw-lock closure with D-state ownership retained in both profiles, thirty
competing starts refused and all original-state recoveries. Six normal transfers,
twelve NFS state-parent refusals and 184 state-file refusals also pass; all fourteen
state fixtures preserve bytes/identity/permissions and cleanup reports no errors.
See the increment report for timing, exact-source and remaining-scope details.

## Bootstrap/source-read death-phase expansion

[Increment 48](RUST-INCREMENT-48.md) defines eight additional selected cases:
debug/release × bootstrap/source-read × blocked/following local stop. Select
`--coordinator-death --death-scope bootstrap-source-read` with fresh passing
production/qualification gate directories and `--isolated-startup`. The default
`--coordinator-death` still selects the retained claim/copy/verification matrix,
including its raw-lock-closure requirement and bounded verification repetitions.
The new phase matrix observes raw lock state but does not require a particular
new worker mode to reproduce the verification-specific kernel exit path.

These phase cases use an NFS source and local destination; both-NFS crash layouts
remain outside this expansion. Bootstrap launches into unavailable NFS without a
fixture pause; source-read uses the retained pre-read rendezvous. Direct D observations are required. Surviving
orphans must retain ownership and refuse competitors until actual exit; prompt
stop is recorded separately. Bootstrap cannot serve readiness or create SQLite;
source-read must preserve custody, the original partial and producer-reused paths.
The [saved phase evidence](RUST-NFS-STARTUP-READ-DEATH-EVIDENCE.json) passes eight
cases: four surviving blocked orphans retain ownership and refuse twelve competing
effect commands; four following-stop cases exit promptly. All recover with original
state, source and reused paths preserved. Six normal transfers, twelve NFS-state-
parent refusals and all 184 state-file refusals pass, with fourteen fixtures
preserved and clean teardown. See increment 48 for exact gate/artifact provenance,
timings and remaining limitations. These cases do not newly reproduce raw flock
closure; preserve increment 47's separate strict regression evidence.


## Enrolled/populated bootstrap death

[Increment 49](RUST-INCREMENT-49.md) defines eight additional cases selected by
`--coordinator-death --death-scope bootstrap-existing-state`: enrolled-empty and
populated state, debug/release, blocked/following local stop. The populated case
starts with an accepted claimed job, retained WAL and a 1 MiB partial. Snapshots
use metadata/SHA-256 without opening SQLite; require unchanged database/sidecars,
staging, receipt and source evidence through blocked bootstrap and old exit.
Recovery uses the original pair without re-enrollment. Preserve the prior two
scope selectors and increment 47's stricter raw-lock-closure regression.

These cases isolate an NFS source with a local destination. Record actual D state,
connected/sent unanswered readiness, retained ownership and competing-start refusal
for surviving orphans; distinguish prompt stop. No runtime policy, dependency or
production-enable change is introduced. Read the increment for pass conditions,
actual results and limitations. The [corrected existing-state evidence](RUST-NFS-ENROLLED-BOOTSTRAP-EVIDENCE.json)
passes all eight cases: four surviving D orphans retain ownership, twelve competing
starts refuse and four following-stop workers exit promptly. All recover using
the same database inode and receipt, with populated WAL/partial/job replay
preserved. Six normal transfers, twelve state-parent refusals and 184 state-file
refusals pass across fourteen preserved fixtures, with clean teardown. The initial
worker-first seed allowed a retry and correctly hit staging EEXIST/review; preserve
its separate failed report and use the corrected coordinator-first preparation.
No allocation deletion, review reset or application change is part of this test.
