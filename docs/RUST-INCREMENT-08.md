# Rust audited delivery resume

The trusted loopback operator API now implements
`POST /api/v2/jobs/{job_id}/resume` for fully claimed recordings whose delivery
has reached its persistent three-failure review threshold. This requests normal
worker reconciliation of the same job and pinned destination. It does not
authorize overwriting a collision or bypass custody/verification checks.

## Request and receipt

First inspect `GET /api/v2/jobs/{job_id}` and its `details.review_epoch`:

```json
{
  "command_id": "operator-command-001",
  "expected_review_epoch": 0,
  "reason": "Inspected protected staging and corrected destination permissions"
}
```

Send `Content-Type: application/json`. `command_id` is a stable retry identity,
bounded to 128 UTF-8 bytes. The reason is required, bounded to 512 bytes. Empty,
whitespace-only or control-containing strings are rejected; unknown/duplicate
JSON fields and negative/fractional epochs are rejected. An optional
`Idempotency-Key` header must equal `command_id`. The actor is recorded as
`trusted-loopback-operator`; this labels the deployment boundary, not an
authenticated human identity. Registration/operator authentication remains deferred.

HTTP 200 acknowledges a durable scheduling decision, not completed delivery:

```json
{
  "job_id": "1",
  "source_paths_released": true,
  "retryable": false,
  "details": {
    "action": "DeliveryResumeScheduled",
    "command_id": "operator-command-001",
    "review_epoch": 1,
    "replay": false
  }
}
```

The release flag reports the existing all-file claim receipts. Only the recorder's
submission 202 is its handoff acknowledgement; this operator command changes
neither producer obligations nor claim facts.

Repeating the exact command returns its original receipt with `replay:true`,
even after another failure/review or completed delivery. It never resets that
later review. A changed reason/actor/expected epoch under the same command ID
returns `409 command_conflict`. A new command must use the current review epoch;
stale epochs, incomplete claims, committed jobs and jobs not stopped at the
review threshold return `409 review_conflict`. Missing jobs return 404. Invalid
commands return 400; wrong method/media type return 405/415. Queue saturation
or storage timeout/failure returns retryable 503: retain the same command ID,
because a lost response does not prove the transaction failed.

## Persistence and effects

Schema 6 adds `operator_resumes`, keyed by job/command ID with one successful
command per review epoch. Writable opens migrate schemas 1–5 transactionally;
schema 5 retains the existing instance identifier, claims and review state.
Read-only opens refuse unmigrated state. No dependency/features change is needed.

The SQLite owner checks the claimed/uncommitted job, current review epoch and
three-failure condition in one immediate transaction. It inserts the immutable
reason, actor, timestamp and prior retry code/deadline, then removes the delivery
retry/review row. Both commit together. The bounded delivery scan can then
discover the same job; transfer/manifest evidence and retained data are unchanged.
Normal worker checks reconcile its latest owned attempt, including publication
that may already have happened. An unsafe condition can stop delivery again.

Status exposes `review_epoch` and `latest_resume` with the audit fields.
`latest_resume.review_epoch` is the epoch consumed by that command; the status
epoch and successful receipt report the next epoch. The
epoch counts successful resume commands; audit records are retained in SQLite
and never automatically pruned. At 64 successful commands per job, new actions
return `409 operator_audit_capacity`; exact command replays still work. This is
an explicit prototype retention limit, not an operator retry recommendation.

Operator commands share the eight-slot status queue/thread and have the same
two-second API wait. They use short database transactions and perform no
filesystem effects on the request path. No active worker can be selected from
the persistent three-failure stopped state in the current single-delivery-thread
profile. Distributed takeover and supervised-worker fencing remain unqualified.

Missing-file review/deadline resets, manual pauses, orphan adoption/deletion,
retention reclamation and source cleanup are not implemented by this command.
Source deletion remains disabled. Orphan repair needs a separate ownership and
effect-intent contract; repeatedly resuming an orphan cannot safely adopt it.

## Evidence and requirements

Storage tests cover schema-5 migration, durable replay after restart, a new
review surviving old command replay, stale/conflicting commands, invalid input,
the audit cap and a SQL failure between audit insert and retry reset. API tests
exercise the actual audited service binary: lost response/restart replay,
rejection of unclaimed/committed jobs, strict request validation and a foreign
destination collision remaining untouched. After removing only that test's
collision fixture, reconciliation uses the same already verified attempt and
commits the manifest without recopying or opening a reused producer path.

The Rust derivation is controlled recovery of a retained job (`L1-SYS-005`'s
recovery intent) and review visibility (`L1-API-002`). Architectural obligations
are authoritative serialized command handling and separation of operator intent
from filesystem evidence. Implementation obligations are epoch comparison,
idempotent command receipts, atomic audit/reset, preserved transfer evidence and
bounded retention. Tests provide partial Rust evidence; historical C++ scopes
and automatic trace coverage are unchanged. Formal Rust L2/L3 IDs remain roadmap
work. Current platform results are in [RUST-SLES-EVIDENCE.json](RUST-SLES-EVIDENCE.json).

The final source passed 77 tests per profile through the native WSL gate,
using zigbuild for GNU/glibc 2.22 and exact artifact execution in pinned SLES
userspace. All 20 emitted executables passed loader/library/symbol audits and
require at most GLIBC_2.18. The 42-package Linux graph and selected features are
unchanged. A Windows validation attempt hit an intermittent Podman SSH handshake
failure during release qualification; it removed its containers. The final WSL
run passed both profiles and completed container cleanup. Container qualification
does not prove old-kernel/CPU behavior, NFS durability or power-loss recovery.
