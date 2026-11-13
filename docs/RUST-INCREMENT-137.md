# Increment 137: retry receipts storage (state schema 13)

First half of reviewed admin delivery retry, authorized by the user on
2026-11-13 ("go ahead with retry delivery"; schema 13 approved explicitly). This
increment is storage only; the request codec, route and dashboard button follow
in increment138. No real installation is migrated by this work.

## Change

- **Schema 13** adds `retry_contexts` (one row per job and canonical request
  context: principal, instance, frozen epoch, reason) and `retry_outcomes`
  (one row per occurrence position: accepted, failed or skipped). Receipts store
  only the owning job's projection, never other selected jobs (increment-120
  closeout, "Retry receipts").
- **`Store::admin_retry`** decides one occurrence in one immediate transaction:
  exact receipt first (projection must match, else conflict); null epoch and
  missing job skip without a row; then context capacity (64 per job, refuse
  with `ReceiptCapacity`, no eviction), then classification: committed skips;
  released, uncommitted, in delivery review with 3 failures, frozen epoch equal
  to the current one and audit capacity left is accepted, recorded in the
  existing `operator_resumes` audit and scheduled exactly like the trusted-local
  resume; anything else fails. The outcome row commits with the decision.
  `[42,42]`: the second occurrence fails once the first scheduled work.
- **`Store::job_id_high_water`** for the "never-allocated future ID" rule.
- **History clear** removes the cleared job's receipts (other jobs keep theirs).
- **Migration:** `--migrate-state` converts 12 -> 13 (`upgrade_retry_receipts`:
  validates schema, identities, sequence and contents before and after, creates
  only the two tables, integrity check, version stamp) and chains 11 -> 12 -> 13.
  Normal startup reports MigrationRequired for 11 and 12. The new step's
  checkpoints use distinct `receipts_*` names, so 11 -> 12 fault injection is
  unchanged. Account commands now require schema 13.

## Tests

- Store: accepted retry and exact replay; duplicate occurrence fails; an old
  request after a later review replays its original outcome without scheduling;
  stale epoch fails; projection mismatch conflicts; null epoch and missing job
  skip with no rows; foreign instance refused; 64-context cap refuses without
  eviction and existing receipts still replay; committed job skips; clear removes
  only that job's receipts; 12 -> 13 upgrade succeeds with all checkpoints and a
  pre-commit fault leaves schema 12 intact.
- Review fixes: a later occurrence of an already-accepted context fails even
  if delivery committed or the service restarted in between; backup/snapshot
  verification compares both receipt tables (altered, deleted or missing rows
  are refused).
- Existing migration, inspection, backup, compatibility and service tests were
  updated: 12 now requires migration, 13 is current, a rerun after interruption
  needs a fresh backup directory.
- Local native runs (gate SQLite flags): all mover-store tests pass except the
  pre-existing load-sensitive `uuid_transaction_races…` (passes alone 3/3); the
  changed API and backup tests pass individually. CI is authoritative.

## Validation status

Pending PR CI for both full SLES modes and independent review.

## CI result

PR41 CI run
[43377828546](https://github.com/joey-huckabee/background-file-mover/actions/runs/43377828546)
at `e8f248a` passes both full modes: production **391 tests per debug/release
profile** and nfs-qualification **395/profile** (increment136's 385/389 plus six
receipt storage tests). Independent review found two issues (backup verification
of receipt tables; duplicate-after-acceptance classification across commit), both
fixed with tests; re-review had no findings. Merged to main as `9fefeb6`.
