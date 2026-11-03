# Admin replay and retained-data outcomes - candidate

Group 49 approves reviewed-state context in a request header on 2026-11-02.
The compact body remains {"job_ids":[...]}; no new public job or operation ID or
confirmation dialog is added. Exact wire/storage details below remain proposals.
[Groups 35/38/41-45](../REST-ERROR-SCENARIOS.md) remain authoritative, with
[group 50](../REST-ERROR-SCENARIOS.md#history-clear-forgets-all-file-linkage-group-50)
now removing all file management/linkage after successful clear.

## Short closeout table

2026-11-03: group 51 approves the specified retry/deletion defaults below.
Groups 1-51 are approved, with group 50 overriding post-clear tracking. Rows
still marked proposed remain proposals; this is not approval of all candidate
transport, schema or implementation details.
Routine names, serialization and transaction mechanics are engineering work.

| Situation | Rule / remaining recommendation | Approval / remaining choice |
|---|---|---|
| A valid cancel batch finishes with no jobs newly accepted | Keep 202 and report the real zero accepted/failed/skipped counts. Do not imply any job stopped. | Group 44 already covers processed all-skipped selections. No new approval needed. |
| A valid retry batch finishes with no jobs newly accepted | Use the same 202 count summary; show zero accepted and actual failed/skipped attempts. Whole-request validation/storage errors remain errors. | Approved group 51/API-E133; no successful-transfer claim. |
| [42,42] retries eligible job 42 | First occurrence may schedule it; the second independently checks that same frozen review and counts as failed once work is scheduled. Whole-request replay preserves both original outcomes. | Approved group 51/API-E134; exact-command replay and frozen review remain required. |
| A cancellation response is lost | Dispatch a repeated request against the same stored job. Pending duplicate cancel fails; completed/safely-cancelled/missing entries skip. Never undo the first cancellation or cancel a replacement job. | Existing groups 33/41-44, with proposed transport application. No new target ID. |
| A history-clear response is lost | Repeating clear reports only jobs actually cleared this time; previously cleared IDs silently skip. Files remain untouched; all cleared-job ownership/accounting and action linkage is forgotten. | Group 50 overrides earlier post-clear tracking; groups 19/31/39/42 preserve other rules. No hidden UUID-recognition tombstone. |
| History is explicitly cleared after a retry was accepted | Clear that job's detailed command results too. Late retry of the cleared job skips; other uncleared jobs retain their own exact replay results. Original aggregate counts are not promised after clear. | Approved group 51/API-E135, consistent with group 50. No hidden history or redirection to a reused UUID. |
| A confirmed deletion is already running | Allow one active sweep per job. Repeat requests observe that same sweep; no second removal attempt or double-counted files. Keep showing actual pending/deleted/failed results. | Approved group 51/API-E136, within existing best effort/safe-stop scope. |
| Deletion finishes with failures and the admin tries again | Require a fresh deliberate confirmation for the remaining safe files. No automatic retry. Show the latest sweep's results under the original job ID, while the job is still tracked. Clear forgets the results and all file linkage; do not promise every older sweep remains separately available. | Fresh explicit request remains approved in group 40. Latest-result-only presentation is approved in group 51/API-E137. |
| The owned file selection changes after confirmation | Reject the stale confirmation and require a fresh confirmation; never broaden the deletion. An older replay must not start a later sweep. | Approved group 51/API-E138; exact stale-error wire remains to specify. |
| Storage fails partway through a batch | Return an error without fabricated final counts; earlier committed decisions remain valid. Retry uses the original frozen context, and status shows actual progress. | Preserve group 38 and exact replay. No batch-wide rollback claim or false success. |

Group 50 settles the post-clear choice: **nothing remains linked to the files**.
Group 51 also approves latest manual-deletion results **before clear**, retry
no-work/duplicate outcomes, receipt removal for the cleared job and one active
deletion pass with stale-selection refusal. Cancellation transport application
and exact field/storage details remain separate; do not infer their approval.

Receipts for uncleared jobs must not expire automatically or disappear when
receipt capacity fills. Refuse additional unauditable commands instead. Design
bounded failed/skipped batch receipt storage without an automatic history purge.
Clearing one job must not erase the audit/replay protection of other jobs in the
same selection. A future SQL migration must make those boundaries testable.

Only the latest deletion result is approved (group 51); this does not permit an old
confirmation to be reused as new intent. Bind it to a monotonic per-job stored
state version and exact owned-file scope, revalidate before effects, and return
an existing result or stale refusal rather than start another sweep. This is a
precondition on the existing job's state, not a new public operation identifier.
The exact transport and receipt layout are engineering design still to complete.

No new schema fixtures or simulated lifecycle tests are needed to count this
review as progress. These rows require real storage/action tests when implemented;
none is new passing evidence. Other P01 engineering work remains: complete read
schemas, state-preserving UUID migration, legacy/v2 manifest handling and protected
session/ingress design. They are not six separate user product-approval requests.

## Why retry needs immutable context

At review epoch 0, an operator retries job 42 and the response is lost. The
scheduled work later fails into review epoch 1. A transport replay of the old
request must return the old result; it must not authorize another retry.
A deliberate retry after inspecting epoch 1 must be distinguishable from that
old request. Account, route and job_ids alone cannot express the distinction.
A mutable session variable, current-state lookup or ordinary CSRF token cannot
prove which review the operator intended; another tab or polling can change
current state while an old HTTP request remains in flight.

**Approved header mechanism (group 49), candidate wire now specified:** carry
the existing per-job review
epochs and required audit context in an immutable request header. Keep the JSON
body unchanged. Bind that context to the authenticated account, retry action
and exact ordered list, including duplicate occurrences. Freeze it at the
operator's deliberate Retry action; resend it unchanged for transport retries.
Polling, reauthentication and session renewal must not update an old request's
context. A new deliberate action after later review uses the later epoch.
No extra confirmation dialog is added and no generic audit reason substitutes
for the existing reviewed explanation of operator action.

The [wire candidate](RETRY-HEADER.candidate.md) now specifies
Mover-Retry-Context, canonical base64url/JSON, exact selection binding and byte
limits with executable artifact fixtures. It additionally proposes the existing
instance identity as a precondition against wrong-installation replay. These
precise fields remain candidates, not new approvals. The aggregate 8 KiB head
bound is unchanged. Context is neither a new job identifier nor CSRF protection.

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
  command as two accepted attempts. Group 51 fixes the second occurrence as failed after the first schedules work;
  do not count one accepted command twice.
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

## Clear ends file management (group 50)

Successful clear leaves all source/destination files in place and forgets their
mover linkage, ownership, accounting, inventory and operation results. There is
no retained-owner row or post-clear management endpoint. If the mover should
delete eligible retained data, finish that confirmed action before clear.
Afterward, cleanup is outside this service. Do not reconstruct linkage from old
paths, directory scans or immutable manifest contents, and do not rewrite those
files to implement clear. Removing tracked byte totals does not free disk space.

Clear requires safely completed/cancelled work with every associated worker and
file effect stopped/settled, including manual deletion/cleanup. Serialize new
actions against clear so no worker continues after the job is forgotten. Old
job IDs silently skip in bulk actions and keep existing 404 lookup behavior.
Never resolve through the forgotten UUID or reuse an old internal job ID.

**Approved by group 51 before clear:** one active confirmed deletion sweep per tracked
job, latest-sweep progress/actual deleted/failed counts under that job_id, and
fresh confirmation for another deliberate attempt. No automatic retry or double
counting. A stale confirmation must not broaden scope or start a later sweep.
Clear removes its result; no post-clear summary is retained. Preserve committed
output/original protection and best effort for safely owned remaining files.

## Finite acceptance obligations

Freeze tests for: lost epoch-0 response followed by epoch-1 failure; two tabs at
one epoch; refreshed session/polling with an old request; duplicate occurrences;
crash before/after scheduling commit; partial batch replay; audit capacity;
revoked-session replay; history clear removes only its own receipts/linkage; no post-clear old job
management or reconstruction after UUID reuse; deletion with partial failure and stale confirmation. These
are planned obligations, not new passing tests or permission for physical delete.
