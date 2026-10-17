# Rust operator status and recovery guide

This guide describes the implemented Rust prototype through increment 51. It
delivers DOC-03 from the [scenario catalog](RUST-SCENARIOS.md). Use it with an
already provisioned, initialized service on trusted loopback and protected local
filesystems. It is not an installation, takeover or filesystem repair procedure.
Production NFS and source deletion remain disabled. Controlled NFS observations
below apply only to the retained qualification build and fixture.

[Increment 46](RUST-INCREMENT-46.md) found that a terminating worker can outlive
its flock after coordinator death. [Increment 47](RUST-INCREMENT-47.md) adds a
persistent local process-group lifetime check: a free flock alone no longer
means NoActiveOwner. Keep the lifetime record with the original local state.

The [ownership contract](NFS-OWNERSHIP-FENCING-CONTRACT.md) now has an
implemented shared local guard, worker handoff and bounded local lifecycle
controller. `shutdown_wait_seconds` now defaults to 60 and accepts integer values
1–3600. It bounds the separate stop command; it does not promise that the daemon,
blocked workers or NFS operations exit by that deadline.

## Local ownership and refused starts

All supported manual/service starts must use the same configuration and fixed
local database directory under the same account. That directory must already
exist, be owned by the account, have no group/other permission bits (use mode
0700), and use admitted local storage.
SQLite, its sidecars and state stay on persistent local disk using actual local
files. Before source/SQLite access, starts validate the database and its -wal,
-shm and -journal names: owned regular files, one link, owner read/write, no
special bits or group/other write permission. Existing 0644 files remain accepted
inside the private directory; new databases use 0600. Symlinks, unsafe files,
recovery files without their database, and individual mounted state files refuse.
The local mount inventory must be readable. Guard/control names also refuse
individual mounts. See [increment 44](RUST-INCREMENT-44.md).

A refusal preserves existing state; do not delete sidecars, blindly change
ownership/permissions, replace state or bypass the guard as a recovery shortcut. Keep the original database and
recovery files together and verify provisioning while the service is stopped.
Valid retained WAL after a process crash is recovered by SQLite on normal restart.
The local status/stop commands do not inspect SQLite and are not repair tools.

A refused start can leave the normal permanent empty instance guard. The service creates
an empty mode-0600 `instance.lock` beside the database and retains it permanently.
It never truncates or deletes it on shutdown. Existing unsafe files, symlinks,
multiple links or replaced identities refuse. NFS state is rejected in both
production and qualification builds. Current admitted filesystem types are
ext-family, tmpfs and overlay; container admission does not establish persistence
for deployment.

A competing effect-capable command reports **local instance or surviving worker
already owns state** and exits without opening SQLite or source bootstrap. A
normal start can also fail first if its listener port is already occupied.
The same exclusion applies to source initialization and single-file transfer.
Each child retains the same locked open description: killing only the coordinator
can leave a worker holding ownership. Wait for the existing mover and workers;
keep the original configuration, database and private working areas. Do not
delete/replace the guard, copy state elsewhere or retry with an alternate state
path to bypass refusal. There is no force-unlock command.

This is cooperative exclusion on one host. A hostile same-UID process, a
deliberately different state path or another host can bypass that profile.
Process exit or a released local lock does not establish settlement of old NFS
requests. Production NFS remains blocked pending recovery/lifecycle qualification;
uncertain effects retain their existing review behavior.

## Local service status and bounded stop

Use the same executable, account, configuration and fixed local state as startup:

```sh
file-mover --status /path/to/config.json
file-mover --stop /path/to/config.json
```

The local mode-0600 `control.sock` is created under the private state directory
before source bootstrap. Its path must fit the system Unix socket pathname limit.
It runs independently of the transfer executor. These commands do not query
SQLite or traverse source/destination mounts; they need a readable local config,
usable approved local state/proc filesystems and the same PID namespace as the
daemon. Keep configuration on local disk too; NFS-hosted configuration I/O is
outside this bounded-control profile.
There is no remote lifecycle route or token.

| Result | Meaning and action |
|---|---|
| `Starting` | Guard is held; bootstrap/enrollment/readiness is pending. Local status does not claim the transfer filesystems are available. |
| `Running` | Coordinator is serving; job completion/custody still use their own API/manifest evidence. |
| `Draining` | First stop has fixed a monotonic deadline. New admission is stopping; original work and ownership remain until confirmed completion. |
| `ShutdownIncomplete` | The stop client's bounded wait or the daemon deadline expired; stop exits 2 with shutdown incomplete; restart blocked. Daemon/workers may remain live. Restore the underlying problem and inspect again; do not force a replacement or remove state/locks. |
| `OwnerUnavailable` | Guard is held but no controller responds (for example, orphan workers, a one-shot initialization/transfer or an IPC problem). Status/stop exit 2, preserving exclusion. No worker is signaled by PID. |
| `Stopped` | This stop command observed its original coordinator exit and the guard become free. It does not prove old NFS RPCs/writeback settled or authorize conflicting storage work. |
| `NoActiveOwner` | No current local guard holder is observed. There may be no daemon or it may already have exited. The observation includes the persisted worker-group epoch, so a live recorded process/thread still counts as an owner after its physical flock closes (increment 47). This is not readiness, confirmed worker exit, storage settlement or permission to bypass original-state recovery. |

Successful status and clean/no-active-owner stop exit 0. Status on an expired
drain exits 2; unsafe configuration/state/IPC errors exit 1 and preserve evidence.
Snapshots include the original coordinator identity, live configured budget,
optional remaining milliseconds and up to 64 observed child PIDs. PIDs are local
observations, not ownership authority or a complete worker inventory.

For example, this startup option accepts an integer 1–3600; omission uses 60:

```json
{"shutdown_wait_seconds": 60}
```

There is no unlimited/disabled value or hot reload. Changing the file while the
service runs does not replace its budget, and another stop/SIGTERM/SIGINT cannot
reset the first deadline. Stop polls are pinned to the original controller
instance. A lost IPC reply is not cancellation or completion; another request can
observe the existing drain. The client uses bounded local I/O and the daemon's
remaining deadline, conservatively allowing for request time. A stop command can
therefore report ShutdownIncomplete just before a status query still briefly
reports Draining. The same original deadline remains in force; preserve ownership
and inspect again. Neither observation proves exit or authorizes replacement.
[Increment 51](RUST-INCREMENT-51.md) makes the integration test observe that
transition within its existing bound without changing runtime timing.

The separate stop command returns control at expiry while the foreground daemon
can still be waiting. Existing signal handling requests shutdown but cannot give
that foreground shell a finite exit guarantee. Source initialization and
single-file transfer still hold the shared guard; they are not managed daemon
instances. Systemd unit/account-control/timeout/restart guidance remains pending
actual-version qualification; do not invent unit settings from this local CLI.

Never delete `instance.lock` or an unexpected control file to bypass a refusal.
A normal stop removes its own matching socket; a later guarded start can replace
an owned stale socket only after all old guard holders are gone. Preserve original
state, sources, receipts and uncertain effects. No process-exit/timeout result
authorizes source deletion, takeover or NFS effect replay.

## Inspect a job

Run these shell examples on the mover machine. They assume the example listener
at `127.0.0.1:8080`, `curl`, and a known job ID from the submission response or
recorder log. Replace `1` with the actual canonical positive decimal job ID.
There is no job-list endpoint yet. The generator identity is a configured label;
operator requests use the trusted-loopback boundary, not a registered user token.

```sh
base=http://127.0.0.1:8080
job_id=1
curl -sS -i "$base/healthz"
curl -sS -i "$base/api/v2/jobs/$job_id"
curl -sS -i "$base/api/v2/jobs/$job_id/retention"
curl -sS -i "$base/api/v2/retention"
```

Keep HTTP status and JSON together. A successful health request does not establish
source/destination availability, current custody or completion. Job status reads
local durable state without accessing the transfer filesystems. It reports a
snapshot, not live worker progress. A slow or missing reply is not cancellation.
Avoid tight polling: operator commands share a bounded queue and local SQLite
owner. Retention scans grow with the ledger; the two-second API wait does not
cancel an admitted database query.

| Field | Meaning and operator action |
|---|---|
| `state: Accepted` | Submission is durable; all-file claiming is incomplete. Keep pending producer files and parents untouched. Already claimed files remain private; do not recreate them. |
| `state: Claimed`, `source_paths_released: true` | Durable claim receipts cover every file. Only the recorder's submission HTTP 202 acknowledges its handoff. The recorder can then reuse original paths and has no delivery polling/resume duty. |
| `state: Committed` | The coordinator recorded the validated completion manifest. Consumers still follow the manifest contract. Sources and earlier attempts remain retained. |
| `details.condition: AwaitingClaims` | Reconcile through the recorder's identical submission retry. Inspect `missing` for pending file/deadline details. |
| `details.condition: Ready` | Claimed work has no recorded retry row; this is not proof of an idle worker or healthy destination. |
| `details.condition: Retrying` | Delivery has a saved retry/deferral row. Read its code, count and deadline; do not send resume while it is below review. |
| `details.condition: ReviewRequired` | A missing-file deadline/block or delivery failure threshold needs review. Select the matching action below; the two commands are not interchangeable. |
| `details.condition: Committed` | Takes precedence over old retry rows. A retained failure code/deadline does not schedule another delivery of a committed job. |

Timestamps are absolute Unix seconds. A retry deadline is an eligibility time,
not a promised start/completion time; worker capacity and normal safety checks
still apply. A past timestamp never overrides `ReviewRequired`. Clock-jump
handling remains future work. Reading status never resets a deadline or review.

Files show stable string `file_id` values, measured `size_bytes` (null before
claim measurement), claim `phase`, latest `transfer_phase` and `attempt`. The
latest attempt is not an inventory of old partials. Manifest phases are null
before intent, then 0=intent, 1=allocation, 2=written, 3=publication authorized,
4=committed receipt. An intermediate phase is not proof that a filesystem
effect did or did not happen. Private custody paths are intentionally omitted.

## Destination shortage: wait or resume?

These are illustrative **partial status projections**, not complete HTTP
responses or instructions to alter state. For example, failure 2 of a confirmed
payload copy-write ENOSPC waits 60 seconds:

```json
{
  "state": "Claimed",
  "source_paths_released": true,
  "details": {
    "condition": "Retrying",
    "delivery_retry": {
      "failures": 2,
      "retry_after": 1792150060,
      "code": "destination_capacity_requires_review"
    }
  }
}
```

Restore capacity on the approved destination without removing mover-owned
partials or final objects. After failure 1 the delay is 30 seconds; after failure
2 it is 60 seconds. Original-state restart preserves the pending deadline/count.
Restoring capacity before review allows automatic recovery at eligibility without
resume; it does not bring the saved deadline forward. The next copy preserves
uncertain old partials and can require another full-file reservation.

If another persisted failure reaches the threshold, the projection becomes:

```json
{
  "state": "Claimed",
  "details": {
    "condition": "ReviewRequired",
    "review_epoch": 0,
    "delivery_retry": {
      "failures": 3,
      "retry_after": 1792150180,
      "code": "destination_capacity_requires_review"
    }
  }
}
```

The third capacity failure saves a 120-second deadline, but no automatic fourth
attempt follows it. Capacity restoration and restart do not clear review. After
reviewing the cause, use audited delivery resume below. This budget counts all
persisted delivery failures together: a generic failure followed by a capacity
failure is failure 2, not a fresh first capacity failure. A crash before saving
a failure result can lose that count; three persisted failures is not a bound
on all physical attempts across crashes.

| Retry code / situation | Current response |
|---|---|
| `destination_capacity_requires_review` | Only confirmed native payload copy-write ENOSPC gets 30/60-second waits, then review. The code name alone does not mean review has already begun. |
| `destination_unavailable` | Confirmed unavailable destination before allocation defers five seconds without charging another failure. Restore the approved storage; do not redirect the accepted job. |
| `destination_binding_requires_review` | Immediate delivery review. Inspect approved mount/root/marker/lock provisioning. Restore the original authorized storage and observations; there is no automatic rebind. |
| `delivery_requires_review` | Other failed/uncertain reconciliation uses the existing five-second schedule and three-failure review threshold. Resume cannot waive custody, integrity or no-clobber checks. |
| No result from a blocked filesystem worker | No new failure classification or permission to replace it. Restore connectivity and establish exit/reconciliation; elapsed time or a signal is not a fence. |

Unavailable-destination deferrals can retain the previous failure count/cause
and set a five-second deferral after the prior deadline has expired. Therefore
the retained code is not a universal selector for every current interval.
See the [retry policy](DELIVERY-RETRY-POLICY.md) for the precise persistence rules.

## Resume reviewed delivery

First save current job status. Confirm all files are claimed, the job is
uncommitted and delivery has reached review. Review storage/logs and correct
only a cause you can safely correct, such as restoring approved destination
capacity. Do not delete collisions, allocations or receipts to force progress.
A binding replacement, unknown allocation or lost custody may have no supported
recovery action yet.

For a job whose **current** `details.review_epoch` is 0, create this request file.
Choose a new command ID for this reviewed action and an accurate reason. For
another epoch, edit the expected epoch before the first send. Once sent, retain
the exact file for uncertain-response retries.

```sh
cat > resume-job-1.json <<'JSON'
{
  "command_id": "capacity-review-job-1-001",
  "expected_review_epoch": 0,
  "reason": "Restored approved destination capacity and reviewed retained attempts"
}
JSON
curl -sS -i -X POST "$base/api/v2/jobs/$job_id/resume" \
  -H 'Content-Type: application/json' --data-binary @resume-job-1.json
```

Successful HTTP 200 has these details:

```json
{
  "action": "DeliveryResumeScheduled",
  "command_id": "capacity-review-job-1-001",
  "review_epoch": 1,
  "replay": false
}
```

This records the audit and resets the delivery failure budget atomically. It
schedules normal reconciliation of the same job and pinned destination, not
completion, overwriting or repair. Fetch status again to observe the outcome.
An unsafe condition can require review again. Existing claims, transfers,
manifests and old partials remain intact; resume does not open a reused producer
leaf as the old source.

If the response is lost, times out or returns 503, resend the **exact same file**
to the same job/action. A transaction may already have committed. An exact replay
returns the original receipt with `replay:true`, even after later failure or
completion. It does not clear a later review. `latest_resume.review_epoch` is
the epoch consumed; current status and the receipt show the next epoch.

## Reset a reviewed missing-file deadline

Use this only when status identifies a still-pending file with an elapsed missing
deadline or persisted block. Confirm the recorder has not reused/modified pending
paths, review the exact missing entry and ensure the intended closed file can
be supplied safely. Already claimed files remain private and must not be recreated.
Delivery resume does not reset missing-file deadlines.

For current `details.missing_review_epoch: 0` and pending `file_id: "1"`, this
example requests a fresh 300-second window. Replace both from actual status:

```sh
cat > reset-missing-job-1.json <<'JSON'
{
  "command_id": "missing-review-job-1-001",
  "expected_missing_review_epoch": 0,
  "file_id": "1",
  "retry_window_seconds": 300,
  "reason": "Confirmed pending paths untouched and the intended file is now available"
}
JSON
curl -sS -i -X POST "$base/api/v2/jobs/$job_id/reset-missing" \
  -H 'Content-Type: application/json' --data-binary @reset-missing-job-1.json
```

HTTP 200 reports `details.action: MissingDeadlineReset`, next
`missing_review_epoch`, `new_deadline` and `replay`; `source_paths_released`
remains false. This changes only that file's deadline/block. It does not claim
the file, repair a size/ownership problem or grant handoff. The recorder must
retry its original submission ID/body and obtain submission 202; there is no
timer-driven missing-file claiming. Other missing files can still block the job.

The window must be 1–86400 seconds. Resend the exact command file after an uncertain
response. Replay preserves the original deadline even if it has since expired;
it never extends the window again. Further reviewed resets need a new command ID
and the current missing-review epoch, which is separate from delivery review.

## Operator command errors

Command IDs allow 128 UTF-8 bytes and reasons 512; both must be nonblank and
contain no control characters. JSON accepts only the defined fields, with no
duplicates. The optional `Idempotency-Key` header must equal `command_id`; these
examples omit it. IDs are scoped to job and operation. Audit actor
`trusted-loopback-operator` records the deployment boundary, not an authenticated
human. Preserve the real operator identity separately in operational records.

| Result | Action |
|---|---|
| `200`, `replay:false` | Durable scheduling/deadline change accepted. Inspect subsequent status; delivery/handoff is not promised by this response. |
| `200`, `replay:true` | Original command receipt returned. Fetch current status to distinguish it from any later review cycle. |
| `409 review_conflict` | Reinspect status: stale epoch, wrong phase or ineligible review. Do not blindly increment epochs or loop new command IDs. |
| `409 command_conflict` | Same command ID has different parameters. Recover the original request/receipt before deciding on any new action. |
| `409 operator_audit_capacity` | The job reached 64 successful commands of this operation. Exact replays remain available; there is no supported audit pruning/bypass. Delivery and missing-reset caps are separate. |
| `503 service_busy` / `storage_unavailable`, timeout or lost reply | Back off and retry the identical command. Do not assume it failed to commit. |
| `400`, `404`, `405`, `415` | Check strict body, known job ID, POST method and JSON media type. Preserve uncertain original requests; a new submission is not a recovery command. |

## Capacity and retained data

Inspect global and per-job retention with the GET commands above. Byte totals
are exact decimal strings; counts are JSON integers. Global headroom includes
`new_job_slots`, separate source/destination byte allowances and `over_limit`.
Per-job `global_headroom` is null. Limits describe current startup configuration;
they are not physical quotas or durable storage capacity measurements.

Source reservations include measured claim intents even before receipts.
Destination reservations charge a full source size for every recorded attempt,
including interrupted and published attempts. Committed jobs and retained sources
still count. An `Intent` attempt can already contain bytes. Unmeasured files,
directory/database/manifest overhead and allocations without receipts prevent
these totals from being an exact disk-usage inventory. Responses explicitly say
`filesystem_inspected:false`, `unreceipted_allocations_accounted:false` and
`automatic_reclamation_enabled:false`.

Check actual capacity through approved storage administration. Client/server
free-space and size views can differ; the bounded NFS fixture observed a real
server-side 1 MiB partial while client views alone were insufficient evidence.
Neither logical reservations nor a client size view authorizes reclamation.
New submissions can be refused with `retention_capacity`; exact submission
replays remain possible. Raising configured limits does not add physical space,
remove retained attempts or qualify sustained shortage admission. Preserve state
and data if safe capacity cannot be provided; offline repair/cleanup is deferred.

## Configure source-space admission

[Increment 36](RUST-INCREMENT-36.md) adds the optional local source-space guard.
Omit `source_space_admission` or set `{"source_space_admission":{"enabled":false}}`
to turn it off. Existing reservation limits and custody checks still apply.
To enable it, add this **fragment** to the otherwise complete startup configuration:

```json
{
  "source_space_admission": {
    "enabled": true,
    "min_available_bytes": 10737418240,
    "min_available_percent": 5,
    "max_sample_age_seconds": 5,
    "probe_timeout_seconds": 2
  }
}
```

10 GiB and 5% are examples, not deployment sizing advice. Both margins must pass;
zero disables one component, but enabled zero/zero is invalid. See the
[policy](SOURCE-SPACE-ADMISSION-DESIGN.md) for strict ranges/defaults. Apply changes
by a normal same-state restart after old process/worker exit; there is no hot
reload. Startup logs the effective policy. No sample survives restart.

A new submission triggers a background probe when needed. At most two HTTP
requests may await it asynchronously and recheck once within the existing total
ten-second handoff budget; other paths stay available. A fresh sufficient result
permits ordinary claiming, including on a cold request. Missing/error/late samples
or unavailable waiter slots return retryable 503 `source_space_unavailable`.
The recorder keeps its ID/body/files untouched and retries. A low observation
returns 503 `source_space_low`. Neither refusal creates a job or releases paths.
Existing accepted/partial submissions bypass this guard but still obey normal
claim, missing-review, custody and ledger checks. No new recorder duty follows 202.

Inspect the existing global GET `/api/v2/retention` command for
`details.source_space_admission`: `policy`, `state` (`Disabled`, `Unknown`,
`Sufficient`, `Low`), `observed_available_bytes`, `required_available_bytes`,
`sample_age_ms` and `reason`. Observed/required bytes are decimal strings or null;
`policy` uses the same field types as startup configuration. Scope is
`SourceRoot`, observation source `supervised_child`. GET never refreshes a sample;
`not_sampled`, `probe_pending`, `probe_timeout`, `sample_expired`,
`probe_unavailable` or `custody_refused` explain Unknown. Only a new-key submission
requests refresh. A Low/failed result can remain cached until its age limit.
Per-job status and reservation `global_headroom` are unchanged.

Restore approved source capacity or review thresholds if they were configured
incorrectly. Turning the guard off does not add capacity or clear existing review.
A good sample reserves no space against external writers or quotas. Source data
is still retained after commitment; this feature cannot reclaim it. Local tests
exercise these commands/status through the SLES gate; hard NFS statistics stalls,
physical-disk source-fill, inode/quota and power-loss cases remain unqualified.

[Increment 38](RUST-INCREMENT-38.md) qualifies a bounded source-capacity example:
a 32 MiB server tmpfs is filled, then left with 1 MiB available against an unchanged
4 MiB admission floor. The service returns `source_space_low` without creating a
new job or releasing paths. Existing claimed replay still returns 202, and an
accepted partial job can finish claiming after its missing file arrives. Removing
only the fixture filler and waiting for a fresh sample lets the identical refused
ID/body reach 202 with the same live coordinator and configuration. No resume is
needed for a request that was never accepted. This is a controlled fixture result,
not permission to delete service-owned files or a guarantee about quotas/disks.
Inspect actual storage use and preserve claimed data and original state.

## Diagnostics and situations that must stay blocked

Known native errors provide fixed operation/errno labels in service logs, for
example `payload_copy_write errno=28` or `manifest_write errno=28`. Payload
labels distinguish source read, copy write/sync, verification read and publication
sync. Staging/manifest allocation and I/O plus `relocate.*` identify selected
namespace boundaries. On Linux, errno 28 is ENOSPC, 5 EIO, 13 EACCES and 17 EEXIST.
Inspect storage for I/O errors and approved permissions for access failures;
preserve evidence for collisions. Only typed copy-write ENOSPC changes scheduling;
similar text or ENOSPC from another operation does not get capacity backoff.

Logs omit arbitrary underlying paths/error text. Logical custody/digest refusals
and some root/traversal failures can still report a generic `blocked_or_uncertain`
or bounded refusal. A missing errno is not proof of a transient error. Keep the
job ID, original request/configuration, before/after status, exact command files
and replies, relevant build/startup/worker logs and storage incident timeline for
review. Preserve the original database/state directory and filesystem objects;
do not edit SQLite or copy/restore live database files as a recovery step.

| Situation | Safe response / current limit |
|---|---|
| Error after allocation creation, before its receipt | Preserve the object and original state. Exclusive creation can later return EEXIST. Resume is not guaranteed to fix it; allocation adoption/repair is deferred. |
| Publication sync fails after final file or `COMMITTED.json` appears | Preserve final names and source. Valid visible bytes alone do not prove coordinator commitment or synchronization. Normal reconciliation must validate exact owned identity/content. Consumers continue to validate the manifest; no log grants deletion. |
| Missing/changed mount, root, marker or lock | Restore the original authorized storage only. Never generate a marker, replace an active lock or edit saved pins to bypass refusal. Changed observations may remain blocked without a supported rebind procedure. |
| Startup says enrollment pending | No API readiness is promised. Explicit `--initialize-source CONFIG` retry is allowed only for the existing prepared setup when no receipt was created; an already active matching pair validates normally. A created but unactivated receipt stays preserved for review, even when its text matches. Use the [enrollment contract](FENCED-ENROLLMENT-DESIGN.md), not repeated blind setup. |
| Enrollment runs out of space | Restoring capacity can permit explicit same-state retry when no receipt was created. Created/partial receipts remain ambiguous and cannot be removed/adopted. Logs and lack of activation matter; do not infer absence from a generic error or inaccessible mount. |
| Coordinator died but a filesystem worker survives | Its inherited custody can still exclude startup and its effect can finish later. Establish confirmed exit and reconcile original state. A kill request or elapsed timeout is insufficient; hard-mounted shutdown can await storage restoration. |
| Fresh, cloned, older or populated legacy database | Preserve the original database and private data. Empty state cannot replace enrollment. IDs do not detect clones/stale snapshots; backup restoration, populated re-enrollment and takeover need a separate independently fenced procedure that is not implemented. Older binaries refuse schema 11. |

Do not use `--transfer-one` as an operator repair bypass. No current action
authorizes source deletion, orphan adoption, receipt replacement, rerouting old
jobs or independently fenced takeover.

## Evidence and documentation boundaries

DOC-03 covers SC-008–010, SC-023–027 and the operator response portions of
SC-058–074, with supporting interruption/capacity explanations from SC-018–020,
SC-028–033 and SC-049–057. Future situations remain explicitly blocked here.
This guide does not promote fixture observations into production support.

Implemented API/request semantics are covered by [07](RUST-INCREMENT-07.md),
[08](RUST-INCREMENT-08.md), [09](RUST-INCREMENT-09.md),
[10](RUST-INCREMENT-10.md) and current source. Diagnostics, shortages and pending
restart recovery have evidence in [28](RUST-INCREMENT-28.md),
[29](RUST-INCREMENT-29.md), [30](RUST-INCREMENT-30.md),
[31](RUST-INCREMENT-31.md), [32](RUST-INCREMENT-32.md) and
[33](RUST-INCREMENT-33.md). The latter passed both GNU/glibc-2.22 zigbuild/ELF/
pinned SLES userspace gates and selected NFS capacity/long-outage checks.
Those containers share a modern runner kernel/CPU; hard NFSv4.1 fixture evidence
does not qualify old kernels, NFSv3, physical disk exhaustion, power loss,
independent-host fencing or production NFS.

These examples were checked against source and existing evidence for
[documentation increment 34](RUST-INCREMENT-34.md); they are not a newly executed
deployment walkthrough. Producer quickstart (DOC-01), consumer manifest validator
(DOC-02), full restart/shutdown troubleshooting (DOC-04), deployment/support matrix
(DOC-05) and future repair/adapter guides (DOC-06) remain separate deliverables.

## Controlled hard-NFS shutdown observations

[Increment 45](RUST-INCREMENT-45.md) tests the existing controller after actual
claim, copy and verification workers enter kernel D state with the NFS server
unavailable. In the selected fixture, a blocked copy can remain alive beyond the
short two-second or default 60-second stop budget. Stop returns exit 2 and
ShutdownIncomplete; the guard and worker remain, and competing starts refuse.
Repeated stop/signals or editing a next-start wait setting do not extend that
instance's first deadline. Preserve original state and working files, restore
approved storage, and observe confirmed process exit before attempting recovery.

Other selected workers can exit promptly when the kernel handles termination.
A local Stopped/NoActiveOwner result describes process/guard ownership; it is not
proof that every NAS operation or client writeback has settled. The fixture always
restores NFS before original-state restart. A brief OwnerUnavailable during final
teardown remains an unsuccessful observation, not permission to bypass the guard.
Original-state recovery checks same-ID replay, retained source/partials and final
manifest integrity without changing retry/review behavior or deleting sources.

These are opt-in qualification-build observations on the stated modern kernel,
not deployment support for arbitrary NFS calls, NAS versions or systemd units.
Production NFS and source deletion remain disabled.


## Historical coordinator-death counterexample and its fix

The increment 46 fixture found a release-blocking exception: during termination,
a verification worker remained kernel-blocked after its local guard closed.
After coordinator death, that version returned NoActiveOwner/exit 0 while the
worker was still D. Increment 47 addresses this with independent group lifetime
evidence; the old failed report remains historical. No conflicting replacement
was started in the failing fixture. Production NFS remains disabled pending the
broader release gates; local ownership never certifies remote settlement.

[Increment 46](RUST-INCREMENT-46.md) exercises selected real kernel-blocked
claim/copy/verification workers after coordinator death, including a terminating
copy worker after an incomplete local stop. A surviving worker can retain the
shared local guard even though the REST listener and local controller are gone.
Local --status then returns OwnerUnavailable/exit 2; competing service,
initialization and single-transfer starts refuse. Repeating --stop cannot make
an absent coordinator supervise an orphan or authorize a replacement.

Preserve the original state, claimed source, partials and working folders. Restore
approved storage and establish old-process completion through the qualified
operating procedure before restarting with the original configuration/state.
The fixture confirms process exit before recovery; it does not supply production
orphan inspection/killing tools or a force/delete-lock remedy. Local guard release
still does not certify that remote RPCs/writeback settled. Unexpected custody or
identity evidence must preserve refusal/review under the existing protocol.

A worker that exits promptly during stop, before the planned coordinator kill,
is recorded separately from a surviving terminating orphan. These controlled
observations do not qualify actual systemd process-group/timeout/restart policy
or every NFS death boundary. Production NFS and source deletion remain disabled.


## Local lifetime record and worker termination

Increment 47 adds `workers.json` beside instance.lock and SQLite, with a private
`workers.next` temporary during atomic replacement. These names are reserved and
cannot be SQLite database names. Keep them on protected
persistent local disk under the same account/configuration and PID namespace.
Do not delete, edit, move or restore them independently to make a start succeed.
Published malformed/scope-mismatched evidence refuses; valid-looking cloned or
hostile modified state is outside this cooperative profile. Stop all previous
binary versions and their workers before an upgrade; mixed workers are unsupported.

Before spawning, the coordinator records its own process group, boot/namespace,
start ticks and guard identity. Children remain in that group. Local stop/status
checks and effect starts consult that evidence when the raw lock is free.
A live recorded process/thread keeps the instance owned: unavailable control
reports OwnerUnavailable/exit 2, and starts refuse before SQLite/source bootstrap.
Unreadable or over-budget process observations do not certify exit. PID-namespace
changes refuse; reused group IDs may conservatively block. The normal same-state
start replaces an inactive epoch after confirmed old exit. No force/adopt command
or automatic orphan killer has been added.

Existing supervision still requests termination and waits for actual child exit;
workers detect bad assignments and lost channels. A worker stuck in the kernel
cannot execute its own deadline code, and SIGKILL may remain pending. Restore the
underlying storage problem, preserve original state and confirm old completion
before recovery. Timeout, lock release and local epoch clearance still do not
prove NAS RPC/writeback settlement. Production NFS/deletion remain disabled.


## Bootstrap and source-read coordinator loss

[Increment 48](RUST-INCREMENT-48.md) exercises selected fresh bootstrap and
accepted source-read workers on the disposable hard-NFS fixture. Read its report
for actual outcomes. During bootstrap, Starting status is local; a bound listener
and sent health request do not imply readiness or database access. If its
coordinator dies while the child remains blocked, preserve the same state and
lifetime files and observe OwnerUnavailable; do not start another mover or
initialize the source until the old worker has exited and storage is restored.
The fresh fixture performs explicit first enrollment afterward; this is not a
repair or re-enrollment procedure for existing jobs.

After accepted source-read interruption, preserve private claimed source, all
staging attempts and the producer-reused original path. Normal same-state recovery
can retain an interrupted partial and allocate the next copy attempt. Do not
clear attempts or resubmit under another ID to bypass custody. A prompt worker
exit following stop is a distinct measured outcome; it does not promise every
hard-NFS call can be cancelled. Existing shutdown, retry/review and termination
policies are unchanged. Production NFS and source deletion remain disabled.


## Restarting an enrolled or populated scope after bootstrap loss

[Increment 49](RUST-INCREMENT-49.md) records selected enrolled/populated bootstrap
death tests. Use its actual evidence and scope. Existing enrollment differs from
first setup: keep the original database, WAL/shared-memory/journal sidecars,
receipt and private working files together. Do not initialize again, replace state
or discard a WAL to make startup proceed. Local Starting status does not imply
HTTP readiness or access to jobs while source bootstrap is blocked.

If the coordinator disappears while its bootstrap child remains alive, preserve
all state and wait for confirmed old exit and restored approved storage before
normal same-configuration startup. A populated scope can contain accepted jobs,
producer-reused paths and partial copies; replay existing IDs and preserve all
attempts. Unreceipted staging allocations or unresolved EEXIST refusals follow existing
retry/review rules; they do not authorize deleting allocations or resetting review. The increment's failed seed setup demonstrates that refusal,
and its corrected test setup is not an operator repair procedure.

No shutdown, retry/review or termination policy changes accompany these tests.
Production NFS and source deletion remain disabled. Both-NFS crash layouts,
actual systemd and delayed NAS effects remain outside increment 49. See the
next section for selected publication/manifest evidence.


## Coordinator loss around file publication and commitment

[Increment 50](RUST-INCREMENT-50.md) exercises selected destination-NFS file and
manifest publication deaths. The manifest can be visible while the last API
snapshot still says Claimed/manifest phase 3: its name alone does not prove that
SQLite recorded Committed, or that all synchronization and worker exit finished.
Consumers continue to validate the immutable manifest under the consumer
contract. Neither a visible final name nor its checksum authorizes source cleanup.

If local status reports OwnerUnavailable/exit 2, keep the original configuration,
local database/recovery files, instance.lock, workers.json and private working
folders. Do not delete an alias, create fresh state, clear review or bypass the
guard to restart. A blocked worker may finish a previously authorized publication
after NFS returns even though its coordinator has died. Wait for confirmed old
exit; normal startup with the original state must reconcile owned effects and
manifest commitment. No orphan-kill/adoption command is supplied by unserved
local control. A bounded stop result is separate from exit and NAS settlement.

The fixture checks original payload inode/attempt and manifest inode/hash across
recovery; it is not a production deployment walkthrough. Both-NFS crashes,
remaining synchronization/delayed RPC boundaries, real systemd/account policy and
NAS reboot/power durability remain outside this increment. Production NFS and
source deletion remain disabled; preserve the earlier failed evidence.
