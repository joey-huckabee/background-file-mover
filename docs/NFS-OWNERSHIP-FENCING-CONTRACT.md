# First-release single-host NFS ownership contract

Revised in [increment 41](RUST-INCREMENT-41.md), 2026-10-16, after the deployment
clarifications below. [Increment 42](RUST-INCREMENT-42.md) implements the local
guard and worker handoff with selected local tests. [Increment 43](RUST-INCREMENT-43.md)
adds the configurable wait and bounded controller with selected local cases;
remaining NFS/lifecycle qualification is pending. Supersedes
the blanket external-fencing prerequisites in increment 40 for this restricted
first-release profile. It does not declare a local lock equivalent to NAS fencing.
Production NFS and source deletion remain disabled. Registration, cross-host
failover, re-enrollment and offline repair stay deferred.

## Confirmed deployment and remaining unknowns

| Item | Confirmed first-release constraint |
|---|---|
| Mover ownership | Exactly one mover, always restarted on the same host; another host will not use these scopes |
| Account and administration | Runs under the user's account, without host sudo or NAS administration; an administrator can set up systemd |
| Startup paths | Manual and systemd starts use the same configuration file and fixed local state directory |
| Persistence | SQLite database, WAL/shared-memory sidecars, state files and ownership guard live on persistent local disk, not NFS or a home directory merely assumed local |
| Payload storage | Source and destination are mounted NFS shares, normally separate but possibly the same share; NetApp and Dell Isilon are in use |
| Private working areas | Other applications and cleanup jobs leave mover-private claim/staging areas untouched; normal recorder input paths remain reusable after 202 |
| Stop behavior | Wait for the old mover and every worker before replacement; configurable shutdown wait, default 60 seconds, then report incomplete/blocked instead of waiting silently forever |

NFS version, mount/security options and exact paths are unknown; the user cannot
check them yet. Discover them later with read-only host information. Existing
fixture evidence is hard NFSv4.1 on a shared modern kernel; it does not qualify
NFSv3, every v4 minor version, actual NAS options or hardware. Do not assume a
NAS management API, credential revocation, host power fence, Kerberos or a new
storage service is available. The host kernel supplies NFS, not this application.

This profile trusts administrator-managed mounts and cooperating local launchers.
Keep approved root bindings/markers, strict observations, safe traversal and
original source/state pairing. An unexpected local fallback, changed root/pin or
foreign receipt refuses effects; matching marker text is not cryptographic proof
of NAS identity. Qualification must record the actual mount/security boundary
and its limitations. Do not change/downgrade installed mount security to make a
test pass. No cryptographic endpoint authentication or malicious-NAS/admin
protection is newly claimed; stronger profiles need separate design/qualification.

## Shared host-local ownership guard

Use a protected persistent regular guard file under the fixed local state
directory, separate from SQLite and NFS coordinator.lock files. The implemented
location is `<state-directory>/instance.lock`, where the state directory is the
configured database parent. It must already exist, belong to the service account
and have no group/other permission bits; use mode 0700 for normal operation.
The guard is created once, empty and mode 0600; reuse does not rewrite it.
Current local filesystem admission permits ext-family, tmpfs and overlay magic
values; tmpfs/overlay support container tests and do not establish persistent
production storage. [Increment 44](RUST-INCREMENT-44.md) validates actual SQLite
file/recovery names and rejects individually mounted state/guard/control names;
supported state files must actually reside locally. Other
filesystem types, including NFS even in qualification
builds, refuse. Persistent local production storage still needs deployment
qualification. Validate local filesystem, private parent,
regular-file type, owner, mode 0600, single link and held/named identity. Reject
symlinks, unsafe parents, replaced/foreign files and unsupported storage. Never
truncate, unlink, recreate or replace an existing guard to bypass a holder.

Every effect-capable launch path must acquire the same nonblocking exclusive
local flock before opening SQLite or performing NFS bootstrap/claim/delivery.
Contention reports an existing instance/worker promptly and performs no effects.
Initialization and single-file/maintenance effect paths must use this guard too;
an alternate command is not an ownership bypass. Read-only/platform tools require
an explicit no-effects boundary. Do not infer ownership from a PID file or
`kill -0`; PIDs can be reused.

Pass the same locked open description explicitly to every potentially relevant
child, including bootstrap, claiming, capacity sampling, recording/delivery and
publication workers. Validate inheritance/descriptor identity; do not depend on
accidental exec descriptor leakage. All holders close their own copies only;
none explicitly unlocks the shared description. Keep the guard through active
work, draining, uncertainty, reconciliation and confirmed shutdown. If the parent
dies, surviving workers retain their copies and block a new manual/systemd start.
If a worker loses the descriptor or cannot establish ownership, refuse its effects.
No unconfirmed replacement is started because a worker timed out.

The implementation sends one SCM_RIGHTS descriptor and a bounded, strict
version-1 identity prefix over each existing private worker Unix stream. The child
checks named/held parent and file identities, descriptor access and exclusive-lock
ownership before acknowledging or reading its assignment. Missing, extra,
unlocked, read-only or wrong-scope descriptors refuse. Bootstrap, enrollment,
claim, payload, delivery and source-space worker modes all use the prefix. It is
an internal same-executable protocol, not an API or mixed-version compatibility
promise. SQLite schema and existing assignment/receipt formats are unchanged.
Service startup, source initialization and single-file transfer acquire the guard
before SQLite/source bootstrap; platform checking remains read-only. The normal
TCP listener may bind before guard acquisition, so an occupied port can refuse
first. Acquisition is nonblocking; the shutdown wait does not apply to it.

This is cooperative same-host instance exclusion, not a server-enforced fence.
It requires all supported invocations to use the same approved state directory.
A deliberate alternate configuration/state copy, another user/host bypassing the
protocol or a privileged actor replacing files is outside this profile. Shared
UIDs are not isolation from a hostile process. Document trusted account access;
never advertise the guard as a distributed lock or prevention of arbitrary NAS
writes. Keep source/destination locks and receipts as additional checks.

## Configurable shutdown wait

The implemented controller requires usable local configuration/state/proc
filesystems and a shared PID namespace with its daemon. Keep the config file on
local disk as a deployment requirement for bounded control; the confirmed same-
config constraint alone does not establish its storage locality. NFS-hosted
configuration and other namespace/sandbox profiles require separate qualification.

Implemented startup option (omission uses 60):

```json
{
  "shutdown_wait_seconds": 60
}
```

Omission means 60 seconds. Validation accepts an integer 1 through 3600
seconds; reject zero, negative, fractional, string/null and out-of-range values.
There is no unlimited/disabled wait. This is a lifecycle setting, independent of
job retry windows, source-space probe timeouts and persisted delivery deadlines.
It authorizes neither deletion nor early guard release. No hot reload is implied.

Start a monotonic deadline when shutdown begins. Stop admission/new assignments,
request cooperative child stop/termination and drain while preserving original
intents, receipts and uncertain results. Complete only after the coordinator and
all owned workers are confirmed exited and the normal safe-shutdown conditions
hold. The first request sets the deadline; repeated requests/signals do not reset
it. Changing the next startup configuration cannot extend a stop already underway.

At the deadline, the operator-facing stop controller must return an unsuccessful
result with the clear message **shutdown incomplete; restart blocked**, plus
bounded local progress/remaining-worker information where available. Implemented
`--stop CONFIG.json` returns JSON/exit 2 with `ShutdownIncomplete`; independent
`--status CONFIG.json` reports local lifecycle and observed child PIDs. The
controller returns control
to the operator; the daemon and blocked children may still exist and must retain
ownership. A later status/stop request may observe completion. No detach/drop of
a live worker, forced guard deletion, alternate state path or success exit is
permitted merely to meet the time limit.

The application cannot promise a blocked NFS syscall or process exits in 60
seconds. A foreground daemon's shell cannot be promised control just by logging
a timeout. Increment 43 implements a separate bounded local stop/status path
using the same executable, without releasing the live daemon's guard. Existing
SIGTERM handling alone does not implement that user-facing guarantee. A stop-timeout
result is not evidence that restarting is safe.

## Manual/systemd coordination

Both paths must use the exact same local guard, user, configuration and state.
The administrator provisions the service/unit and path permissions; ordinary
operation must not assume sudo. How the account requests start/stop of that unit
(user unit or administrator-authorized system service control) must be qualified
before publishing commands. Do not assume authorization merely from User=.

Systemd stop timers, process-group handling and restart policy must be coordinated
with the application/controller's deadline, not copied into a unit blindly.
A systemd job finishing, failed stop, SIGKILL or service status is not proof of
worker exit or settled remote I/O. Any attempted restart still acquires the local
guard first and refuses while a surviving holder remains. Bound restart attempts
and retain diagnostic access; avoid a retry loop while shutdown is incomplete.
Qualify against the actual SLES systemd version in a container lifecycle tier;
latest documentation is not proof of old-version support. The local CLI controller
is in increment 43. Increment 57 adds only a disposable fixture unit and modern
manager/SLES-service-root evidence; no production Rust unit or native SLES
manager/account-control qualification follows. See [its scope](RUST-INCREMENT-57.md).

## Local exclusion and NFS recovery are separate gates

Keep the original local database and recorded claims/allocations, file identities,
size/hash receipts, pinned destinations and manifests. Local lock acquisition or
confirmed process exit alone does not establish that queued/retried/server-accepted
NFS operations or client writeback have settled. Do not mark an uncertain effect
not-applied because a child was killed, nor start an unsafe conflicting attempt.

After the old processes exit and a new instance acquires the guard, readiness
for the relevant effects still requires matching state/root custody and qualified
original-state reconciliation. Start with only safe local observation and bounded
reconciliation; authorizing payload/namespace effects needs evidence appropriate
to each recorded applied/not-applied/uncertain operation. If late effects cannot
be excluded or their outcome safely reconciled in the supported host/NFS profile,
keep that work blocked for review. Restore storage and inspect original evidence;
no force, new generation, fixed wait or delivery resume overrides custody.

Delayed-RPC, server recovery, lock reclaim, reboot/remount and durability behavior
remain mandatory qualification gaps. We do not presume a NAS-side barrier API as
the implementation answer for this single-host profile, and we do not waive the
underlying safety obligation. If qualification finds local exclusion plus owned
reconciliation insufficient, retain the production block and revisit the profile
or require stronger controls explicitly. A remount changing strict pins can still
refuse; no automatic rebind is introduced. Actual server/transport identity limits
must be documented, not hidden by matching marker IDs.

Destination-only outages may still allow bounded source claiming and 202 when
source/state authority and admission limits remain valid. Source uncertainty
withholds new unproven acknowledgements. Prior valid 202 still permits producer
path reuse; recovery uses private claims, never a newer recording at the old path.
Committed manifests remain consumer-visible. Same-share and separate-share layouts
must both pass the agreed copy/hash/destination-reread/no-clobber recovery protocol;
being on one share does not authorize a different integrity shortcut.

## Single-host acceptance matrix (selected local and controlled NFS evidence)

SH IDs remain obligations, not reused NF IDs. L1-SEC-009 retains its existing ID.
Increment 42 covers selected SH-01/02/03/04/13 local cases: private guard
validation, eight-way acquisition race, all three effect entry points, all six
worker modes, coordinator death with a paused claim worker, and 12 actual
mounted-NFS state-parent refusals across both build modes/profiles. This does not
close the full cases: actual systemd races, every death phase, delayed RPCs and
deployment storage remain unqualified. Selected file owner/alias/mount admission
is extended by increment 44 below. Increment 43 implements SH-05 config validation and selected
SH-06/07/08 local controller cases: clean stop, two-second/default-60 delayed
drain, retained exclusion, repeated stop plus signal/config edits, silent/absent
IPC and malformed/foreign-instance requests. The timed pause is local, not an
uncancellable NFS syscall; actual systemd (SH-09), broader drain boundaries and
full NFS-deadline qualification remain pending.

[Increment 44](RUST-INCREMENT-44.md) extends selected SH-01/13 admission to
actual database/WAL/shared-memory/rollback-journal names, preserving original
state on unsafe type/mode/owner/alias refusal. Kernel mount inventory rejects
individual mounts before candidate metadata calls, including guard/control names.
Valid WAL recovery and legacy private-directory file modes remain supported.
Actual systemd/account policy, hostile concurrent same-UID/root mutation,
deployment persistence and remaining SH boundaries are not qualified by this.

[Increment 45](RUST-INCREMENT-45.md) extends selected SH-06/07/08 to real
hard-NFS claim/copy/verification shutdown. Copy workers are observed kernel-blocked
beyond short/default deadlines with retained ownership and bounded unsuccessful
control; prompt claim/read exit is reported separately. Repeated requests/signals
and a changed next-start budget cannot reset the live deadline. Original-state
recovery follows server restoration and confirmed old exit. Other operation/death
boundaries, actual systemd/account policy and delayed-effect settlement remain
open; local stop success never certifies NAS settlement.

[Increment 46](RUST-INCREMENT-46.md) adds selected SH-04/08 evidence after actual
coordinator SIGKILL with claim/copy/verification workers blocked or terminating.
Selected surviving children retain local exclusion and report OwnerUnavailable.
However, both debug/release terminating verification cases expose a release-blocking
gap: the local guard is released while the worker remains in D across repeated
bracketed observations, so current control
can incorrectly report NoActiveOwner for the required worker-exclusion contract.
This prevents SH-04/FR-03/05 closure; require a qualified exclusion-lifetime fix.
A terminating child that exits with its coordinator before the kill point is
recorded as prompt exit.
Bootstrap/source-read/publication/manifest death phases, systemd group control
and delayed remote settlement remain open. No force/adoption path is introduced.

[Increment 47](RUST-INCREMENT-47.md) adds independent local lifetime evidence:
`workers.json` is synchronized before worker spawn and pins the coordinator group,
boot, PID namespace, start ticks and guard. All workers inherit/validate that group.
A physically free flock no longer establishes logical ownership freedom while a
recorded process/thread is live. Effect starts refuse before SQLite/source access;
unserved control remains OwnerUnavailable/exit 2. Bound local proc observations;
unknown observations retain exclusion and malformed evidence refuses. Protect both
workers.json and workers.next with the original state; no delete-file remedy or
cross-namespace adoption is provided. No package/helper executable is added.
Original-state reconciliation still follows confirmed exit, and remote settlement
is separate. Keep the increment 46 counterexample and all remaining SH obligations.

| Case | Evidence required before support |
|---|---|
| SH-01 | Default/fixed config and actual local database/WAL/state/guard path; refuse NFS state, unsafe parents, foreign/replaced/symlink/multilink guard and alternate unsupported startup scope without NFS/SQLite effects. |
| SH-02 | Race manual/manual, manual/systemd and systemd/systemd starts on same host: exactly one shared local guard winner, prompt loser refusal before SQLite/source bootstrap. |
| SH-03 | All effect-capable commands and every worker class explicitly inherit/validate the same locked description. No missing/CLOEXEC/early-close/unlock bypass or accidental descriptor holder prolonging ownership. |
| SH-04 | Kill parent during bootstrap, claim, copy, verification and publication; actual surviving worker blocks another start until confirmed exit. Preserve original state/claims and no replacement overlap. |
| SH-05 | Shutdown option omission=60; valid bounds 1/3600 and invalid types/ranges; current unrelated probe/retry/cleanup policies unchanged. |
| SH-06 | Clean drain finishes before configured deadline; controller success only after confirmed old process/worker completion. The next same-state start uses normal binding/reconciliation. |
| SH-07 | Block a worker on NFS beyond a short configured test deadline and exercise the default 60-second path: controller returns incomplete/nonzero within a measured tolerance, holder remains and concurrent/new starts refuse. Do not equate timeout/SIGKILL to cancellation. |
| SH-08 | Repeated stop requests/signals and next-start config changes do not reset the first monotonic deadline. Safe local status stays bounded; later completion can be observed without forcing a replacement. |
| SH-09 | Admin-provisioned actual-version systemd lifecycle under the unprivileged account: authorized start/stop, process-group/timeout/restart behavior, guarded manual conflict and no restart storm. No NAS-admin operations required. |
| SH-10 | Same and separate NFS shares: original state, private working directories, producer-reused paths, destination no-clobber and 3N integrity/manifest behavior survive outage/restart. No current NFS-version guess becomes a support claim. |
| SH-11 | Delayed client/server RPC/writeback at claim/link/unlink/copy/sync/publication/manifest boundaries after parent/child exit: qualified owned reconciliation or explicit review, no conflicting redispatch or false 202/commitment. A userspace pre-call pause is insufficient. |
| SH-12 | Actual supported mount/version/security profile, missing/replaced mount/root, server recovery/grace/reclaim, longer outages, changed strict pins and storage durability: measured safe continuation or preserved refusal, not automatic rebind. |
| SH-13 | Wrong/stale/cloned state, foreign allocations and scope aliases refuse the supported workflow; no force/delete-lock/delete-state remedy. Document deliberate same-UID/other-host bypass as outside this cooperative profile, not detected by IDs. |
| SH-14 | Production/qualification GNU/glibc-2.22 SLES gates for every changed Rust build/test, exact artifact/ELF and required lifecycle/NFS fixture cases; DOC-04/05 distinguish controller completion from process/storage settlement. Production NFS and deletion remain off pending gates. |

## Earlier NF obligations and extended profiles

Original NF-01–18 were defined in [increment 40](RUST-INCREMENT-40.md); their
original definitions remain in that commit's contract history. They are not
renumbered, marked passed or silently redefined as SH tests. This mapping separates
carry-forward safety work from requirements outside the confirmed deployment.

| Original ID | Revised scope/disposition |
|---|---|
| NF-01 | Default-off gates and supported-profile refusal carry into SH-01/14; external provider presence is not a blanket first-release prerequisite. |
| NF-02 | Original-state enrollment/restart evidence carries into SH-06/13 and existing binding gates. |
| NF-03 | Same-host cooperative races are SH-02/03. Independent cross-host exclusion is deferred with cross-host operation. |
| NF-04 | Root/pin/fallback/alias refusal carries into SH-01/12/13. Cryptographic NAS identity/hostile-server enforcement is a separate extended profile, not proven by mounts. |
| NF-05 | Parent death and surviving workers carry into SH-04/11; neither worker exit nor local guard alone proves remote settlement. |
| NF-06 | Actual server/client lock recovery remains SH-12. Cross-client authority transfer/enforcement remains deferred. |
| NF-07 | Delayed/in-flight effect safety remains mandatory in SH-11; no NAS barrier API is assumed. |
| NF-08 | All pinned endpoints still need safe owned recovery (SH-10/11/13). Multi-endpoint external fence observations remain deferred. |
| NF-09 | External fencer crash/regrant controls remain deferred; no provider exists in this design. |
| NF-10 | Server recovery/changed pins remain SH-12, with preserved refusal where continuity cannot be established. |
| NF-11 | Bounded wait, load and unconfirmed children carry into SH-07/08/14 and FR-05 queue qualification. |
| NF-12 | Source/destination outage handoff invariants carry into SH-10/11 and existing admission limits. |
| NF-13 | Original-state owned recovery/review remains SH-06/11/13; no repair authority added. |
| NF-14 | Clones/foreign state remain unsupported/refused by supported workflow (SH-13); distributed credential/host fencing is deferred. |
| NF-15 | Declared storage failure/durability evidence remains SH-12 and other release gates; no power-loss guarantee from container death. |
| NF-16 | Source deletion remains off (SH-14); later FR-04 still requires independent receipt/policy-qualified cleanup. |
| NF-17 | SLES compatibility remains SH-14. Any future provider's dependencies require separate qualification. |
| NF-18 | Single-host operational guides remain SH-09/14. External-provider/takeover runbooks stay deferred. |

For future cross-host operation, takeover, cloned-state restoration or populated
re-enrollment, preserve the stronger independently enforced old-writer exclusion
and settled-operation obligations in [fenced enrollment](FENCED-ENROLLMENT-DESIGN.md)
and increment 40. They cannot be satisfied by this local guard or the 60-second
timer. Those profiles require explicit new scope, controls and qualification.

## Bootstrap/source-read qualification scope

[Increment 48](RUST-INCREMENT-48.md) extends selected SH-04/08 evidence to fresh,
unenrolled bootstrap and accepted source-read workers in debug/release. Surviving
orphans require retained logical ownership and competing-start refusal; prompt
stop is a distinct outcome. Bootstrap must remain unready without SQLite, with
explicit first enrollment only after restoration/confirmed exit. Source-read
recovery preserves original custody, old staging and producer-reused paths.
Consult the increment and its raw evidence for actual results. No ownership,
shutdown, retry/review or production policy changes accompany this expansion.
See increment 49 for the selected enrolled/populated-state extension. Publication/
manifest death, other bootstrap boundaries, systemd/group control and delayed NAS
effects remain open; FR-03/05 are not closed.

## Existing-state bootstrap qualification

[Increment 49](RUST-INCREMENT-49.md) extends selected SH-04/08 evidence to an
active enrolled-empty pair and populated state with an accepted job, retained WAL
and partial copy. Require unchanged local database/sidecar/staging evidence and
remote enrollment/source evidence before recovery, with no SQLite inspection by
the fixture, replacement state or re-enrollment. Surviving orphans must exclude
all competing effect starts until actual exit; prompt stop is distinct. Read the
increment for actual results, corrected seed preparation and limits.

Selected NFS-source/local-destination cases do not close FR-03/05. See increment
50 for selected publication/manifest cases. Other bootstrap/shutdown boundaries,
both-NFS crashes, actual systemd/group policy and delayed NAS effects remain open. Production NFS and source
deletion remain disabled; no runtime policy or dependency change accompanies this
qualification expansion.

## Publication and manifest qualification

[Increment 50](RUST-INCREMENT-50.md) extends selected SH-04/08 evidence to
pre-publication, durable file-link and durable manifest-link boundaries using
local source/NFS destination. Actual D observations follow release into an
outage; surviving orphans must retain exclusion until confirmed exit and
competitors must refuse. Prompt exit remains a distinct outcome. Recovery must
preserve the verified payload inode/attempt and any existing manifest inode/hash,
then reconcile through the original database without a second allocation.
A visible file or manifest does not prove SQLite commitment, confirmed worker
exit or settled remote effects. Read the result report for actual case outcomes.
FR-03/05 remain open for other boundaries, both-NFS crashes, mount/deployment and
systemd policy, and delayed remote effects. Production NFS/deletion stay disabled.

## References and next increment

Linux [flock(2)](https://man7.org/linux/man-pages/man2/flock.2.html) describes
open-description lock inheritance and advisory scope; it does not certify NAS
settlement. SQLite [WAL guidance](https://www.sqlite.org/wal.html) supports keeping
this project's WAL database/state on local storage. The official systemd
[v228 service manual source](https://raw.githubusercontent.com/systemd/systemd/v228/man/systemd.service.xml)
illustrates timeout/process-group controls; this is not identification or
qualification of the deployed host's systemd version.

Next qualify remaining local guard/death-phase and shutdown boundaries,
actual NFS workers beyond deadlines and systemd/account-control behavior.
Extend selected evidence to remaining SH-01–04/06–14 cases and actual NFS
recovery/mount profiles, maintaining scenarios throughout.
No NAS/host-admin fencing facility or package experiment is a prerequisite for
independent local guard work. Production NFS and source deletion remain disabled.

[Increment 57](RUST-INCREMENT-57.md) exercises selected SH-02/08/09 lifecycle
cases with systemd 252 and glibc-2.22 service userspace, local payload/state and
controlled pauses. Native SLES manager/cgroup support, actual account policy,
persistent deployment and hard-NFS/systemd remain open. A second-port probe
uses identical state/storage bindings to reach the guard because same-port
service conflicts can fail at listener binding first. No guard or deadline
semantics change; production NFS/deletion remain disabled.
