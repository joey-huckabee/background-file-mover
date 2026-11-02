# Admin replay and retained-data outcomes - candidate

This design review resolves mechanisms, not new product approvals. The compact
body remains {"job_ids":[...]}; no new public job or operation ID is proposed.
The reviewed request context outside that body is an outstanding user choice.
[Groups 35/38/41-45](../REST-ERROR-SCENARIOS.md) remain authoritative.

## Why retry needs immutable context

At review epoch 0, an operator retries job 42 and the response is lost. The
scheduled work later fails into review epoch 1. A transport replay of the old
request must return the old result; it must not authorize another retry.
A deliberate retry after inspecting epoch 1 must be distinguishable from that
old request. Account, route and job_ids alone cannot express the distinction.
A mutable session variable, current-state lookup or ordinary CSRF token cannot
prove which review the operator intended; another tab or polling can change
current state while an old HTTP request remains in flight.

**Recommended mechanism, pending approval:** carry the existing per-job review
epochs and required audit context in an immutable request header. Keep the JSON
body unchanged. Bind that context to the authenticated account, retry action
and exact ordered list, including duplicate occurrences. Freeze it at the
operator's deliberate Retry action; resend it unchanged for transport retries.
Polling, reauthentication and session renewal must not update an old request's
context. A new deliberate action after later review uses the later epoch.
No extra confirmation dialog is added and no generic audit reason substitutes
for the existing reviewed explanation of operator action.

Exact header spelling/encoding and its aggregate byte budget are not selected
here. The complete request must fit the existing 8 KiB header bound. An encoding
or smaller per-request context limit must be specified and negatively tested;
do not silently raise HTTP limits to accommodate a batch. Request context is
not another job-identifier scheme, and it does not replace CSRF protection.

## Transactional behavior to preserve

- Authenticate every request, including replay, before receipt disclosure.
  Logout/password revocation prevents subsequent authorization; old receipts
  do not override it.
- Recognize an exact persisted receipt before comparing the current review
  epoch. Return its original outcome without changing later state.
- For a new occurrence, validate its frozen epoch, original custody and current
  eligibility; record the audit, scheduling decision and occurrence result in
  the same SQLite transaction. Writing a batch result after the existing
  resume command commits leaves a crash gap and is insufficient.
- Internally derive bounded command keys from the immutable account/action/
  ordered selection/context and occurrence position. This reuses the existing
  command facility internally; it is not a new public identifier. Persist enough
  exact context to reject changed parameters rather than trust a digest alone.
- Every repeated list occurrence gets its own per-job decision. Reusing one
  command key for both entries of [42,42] would wrongly replay one accepted
  command as two accepted attempts. The exact second-retry classification is
  still a proposal; do not infer it from the approved duplicate-cancel rule.
- A crash between jobs may leave a partial batch. Replay processes only missing
  occurrences with their original preconditions; it cannot refresh epochs or
  fabricate counts for uncommitted results. Parallel batches serialize per job.
- Preserve existing audit caps. Bounded new batch receipts need an explicit
  retention/refusal policy. History clear must not secretly retain detailed
  history indefinitely merely to promise an old batch receipt forever.

This requires an implementation design for new receipt storage and transaction
integration. The current resume endpoint alone is not a working bulk adapter.
Current safeguards are in [operators.rs](../../rust/crates/mover-store/src/operators.rs),
[operators.sql](../../rust/crates/mover-store/src/operators.sql), and the
[later-review replay tests](../../rust/crates/mover-store/src/tests.rs).

## Deletion results after history clear

**Proposed:** keep operational ownership and deletion status under the original
job_id when history clears. Retention lookup must consult that retained-owner
record even without the detailed job row. Never resolve through forgotten UUID
recognition or redirect an old job ID to newly submitted work.

Permit one active confirmed deletion sweep per job. Persist actual deleted/failed
counts and an explicit pending/unknown/completed condition for the latest sweep.
A 202 reports only facts known at acceptance; pending counts are not final zeros.
Later status exposes actual progress and final counts under that same job_id.
Failed files remain and no automatic retry is scheduled. A later explicitly
confirmed sweep may replace the latest summary; overlapping and historical
request results are not separately addressable under this recommendation.

Confirm only the displayed owned file set, revalidate its protected identities
at admission and safe stop, and reject changes rather than widen deletion.
Keep committed-output protection and uncertain-worker exclusion. No file effects
are authorized by receipt counts. Exact stale-confirmation responses, repeated
whole-request semantics and summary replacement policy remain to approve.

## Finite acceptance obligations

Freeze tests for: lost epoch-0 response followed by epoch-1 failure; two tabs at
one epoch; refreshed session/polling with an old request; duplicate occurrences;
crash before/after scheduling commit; partial batch replay; audit capacity;
revoked-session replay; history clear versus receipt retention; old job lookup
after UUID reuse; deletion with partial failure and stale confirmation. These
are planned obligations, not new passing tests or permission for physical delete.
