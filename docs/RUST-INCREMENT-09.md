# Rust audited missing-file deadline reset

The trusted loopback operator API now implements
`POST /api/v2/jobs/{job_id}/reset-missing`. It resets the deadline for one
explicitly reviewed, still-pending file with a recorded missing condition.
It changes no filesystem objects, claim intents/receipts, reservations, route
or delivery policy. Source deletion remains disabled.

## Operator contract

Inspect job status first. `details.missing_review_epoch` is separate from the
delivery resume epoch. File IDs are the stable decimal indices shown in status.

```json
{
  "command_id": "missing-reset-001",
  "expected_missing_review_epoch": 0,
  "file_id": "1",
  "retry_window_seconds": 300,
  "reason": "Confirmed recorder has not reused the pending source paths"
}
```

Send `Content-Type: application/json`. Command IDs and reasons have the same
128/512 UTF-8 byte bounds and control-character rejection as delivery resume.
Unknown and duplicate fields are rejected. File IDs must be canonical unsigned
decimal strings; epochs and windows are unsigned integer JSON values. The window
is explicitly chosen per command and must be 1–86400 seconds. An optional
`Idempotency-Key` header must equal `command_id`. The actor is the existing
`trusted-loopback-operator` boundary label, not an authenticated human identity.

HTTP 200 acknowledges the durable deadline change, with
`source_paths_released:false` and `details` containing
`action:"MissingDeadlineReset"`, command ID, next `missing_review_epoch`,
`new_deadline` (Unix seconds) and `replay`. It never grants the recorder a handoff.
The recorder retries its original submission ID/body and waits for its submission
202. Previously claimed files remain in private custody; retry does not reopen
their original names. No timer-driven claiming is introduced here.

Only a pending file whose missing deadline has elapsed or whose blocked flag
has already persisted is eligible. Missing evidence, an unexpired/unblocked
deadline, already claimed files and stale epochs return `409 review_conflict`.
Other files' missing conditions remain unchanged and can still block the job;
each needs its own explicit reset. This operation cannot repair source-size,
ownership, namespace or mount problems.

Retry an uncertain/lost response with the exact command ID and parameters.
Replay returns the original receipt/deadline without extending it, even if the
new deadline has expired or the file subsequently became claimed. Changed
parameters under the same ID return `409 command_conflict`. Command IDs are
scoped to job and operation; reusing an ID on another operation does not replay
this reset. Invalid input returns 400; unknown jobs return 404; wrong
method/media type return 405/415. Queue/storage failures return retryable 503
and do not prove that the transaction failed.

## Durable evidence and bounds

Schema 7 adds `missing_resets`. Writable opens migrate versions 1–6
transactionally; schema-6 migration preserves existing delivery resume audits,
instance identity and missing deadlines. Read-only opens refuse old schemas.
No dependency, toolchain or feature change is required.

The SQLite owner checks file phase, missing evidence, current epoch and audit
capacity in one immediate transaction. It records actor, reason, selected file,
window, command identity, timestamp, old deadline/blocked flag and new deadline,
then updates only that file's deadline and clears its blocked flag. Both changes
commit together. Checked addition rejects timestamp overflow. Startup's recorded
default missing-file window is unchanged; ordinary recorder replay/restart cannot
extend the explicitly reset deadline.

Status exposes `missing_review_epoch` and `latest_missing_reset`. The audit's
`review_epoch` identifies the consumed epoch; status and receipt expose the next
epoch. Full records remain in SQLite. Retention is capped at 64 successful
missing reset commands per job, independently of the 64 delivery-resume records.
Further new resets return `409 operator_audit_capacity`; exact replays still work.
Audits are never automatically pruned.

The action shares the existing eight-slot operator queue/thread and two-second
API wait. It performs no filesystem work on the request path. A concurrently
finishing claim may remove the missing row through its normal receipt commit;
serialized database transactions and pending-phase checks determine whether a
new reset applies. The audit remains available after successful claiming.

## Tests and requirements evidence

Storage tests cover schema-6 migration, preserved partial claims/reservations,
elapsed deadlines before a blocked flag is persisted, restart/replay without
extension, stale/conflicting commands, audit/reset rollback after a SQL failure,
unexpired/missing evidence rejection, checked timestamp overflow and audit limits.
Actual service API tests cover lost-response recovery, partial handoff completed
with the same recorder ID, renewed expiry requiring a new epoch, strict input,
and rejection of unexpired, claimed and committed files. Retained source data is
checked; this increment grants no cleanup authority.

This provides partial Rust evidence for the explicit audited reset part of
`L1-SYS-033` (missing-file review), with individual review visibility contributing
to `L1-API-002`. Architectural obligations are serialized operator intent and
preserved claim custody; implementation obligations are exact-file selection,
epoch comparison, idempotent receipts, atomic audit/deadline change and bounded
retention. Historical C++ coverage and scopes are unchanged. Formal Rust L2/L3
IDs and automatic discovery remain roadmap work.

Current qualification results are recorded in
[RUST-SLES-EVIDENCE.json](RUST-SLES-EVIDENCE.json). Container qualification covers
the exercised userspace behavior, not old-kernel/CPU behavior, NFS durability or
power-loss recovery. Next: explicit retention/orphan repair, worker supervision
and controlled NFS qualification. Registration/token work remains deferred.

The native WSL gate passed all 84 tests per profile using zigbuild for GNU/glibc
2.22 and exact artifact execution in pinned SLES userspace. All 20 emitted
executables passed ELF/loader/library audits and require at most GLIBC_2.18;
the six audit rejection controls passed. The 42-package Linux graph/features
are unchanged. Container cleanup completed without errors.
