# Increment 140: job cancellation storage and safe stop (state schema 15)

First half of admin cancel, authorized by the user on 2026-11-13 ("go ahead with
cancel"). The user chose that cancel leaves files in place: files already taken
over and any partial destination output stay where they are (Storage page) until
the later "delete retained data" action. This matches the frozen contract
(CancellationStatus: "File disposition stays unchanged"). The confirmation proof,
`POST /api/v2/admin/jobs/cancel` and the dashboard button follow in increment141.
No real installation is migrated by this work.

## Change

- **Schema 15** adds `cancellations`: one row per job with state `Pending` or
  `Cancelled`, the requesting account principal, `requested_at` and
  `stopped_at` (null exactly while Pending, enforced by a CHECK).
- **`Store::admin_cancel`** decides one occurrence in one immediate
  transaction, per the approved group-53 default: missing, completed and already
  cancelled jobs skip; a still-pending duplicate fails; otherwise the request is
  recorded as Pending (accepted). It never undoes a cancellation.
- **Work stops at once:** no new claim (`begin_claim` refuses), no delivery
  pickup (`delivery_candidates` excludes the job), and an in-progress delivery
  stops before its next step (start, each file, before the manifest) without
  counting a failure or recording a problem. Retry occurrences on the job fail;
  operator resume and reset-missing return 409 `recording_cancelled`.
- **Safe stop:** the delivery thread settles cancellations between jobs, so no
  delivery is in progress. Settlement reads the claim thread's "processing a
  submission" flag inside its own store transaction. Store transactions are
  serialized with every claim's own cancellation check, so either settlement
  sees the claim and waits, or the claim sees the cancellation and stops. Only
  then is the job marked Cancelled with `stopped_at`. If the delivery committed
  first, the request is dropped: the job is Delivered, never shown as cancelled.
- **Producer replay:** an exact unfinished request for a cancelled job returns
  409 `recording_cancelled` (retryable false) before any other check, as the
  producer contract requires; a request whose whole handoff completed keeps its
  original 202 meaning.
- **Status:** job condition `CancellationPending` or `Cancelled`; job detail
  includes `cancellation` (omitted when none was requested); list rows report the
  real CancellationStatus instead of the constant NotRequested. The dashboard
  shows "Cancelling" and "Cancelled" badges and activity text.
- History clear removes the job's cancellation row; backups compare it.
- **Migration:** `--migrate-state` converts 14 -> 15 with the shared guarded
  additive step and chains 11 -> ... -> 15. Normal startup reports
  MigrationRequired for 11-14.

## Tests

- Store: accepted, pending-duplicate failed, missing skipped, completed
  skipped, cancelled skipped; delivery pickup excluded; resume and reset-missing
  refused; retry fails; settlement deferred while a claim is active, then
  Cancelled with stopped_at; survives restart; a new claim refused while an
  already claimed file stays claimed; committed-first race drops the request;
  history clear; 14 -> 15 upgrade with all checkpoints and a pre-commit fault;
  snapshot verification refuses an altered cancellation row; all compatibility
  and fixture tests updated for schema 15.
- Real service (`cancelled_jobs_stop_claims_and_delivery_and_keep_their_files`):
  a waiting job and a handed-off job are cancelled; both settle to Cancelled;
  resubmitting the waiting request returns 409 `recording_cancelled` even after
  the missing file arrives, and nothing more is taken over; the completed handoff
  replays 202; the handed-off job is never delivered although the destination
  became ready; taken-over files stay in place; operator resume is refused.
- Local native runs (gate SQLite flags, private WSL namespace): fmt and workspace
  clippy clean; all mover-store tests (the known load-sensitive UUID race test
  passes alone); full API suite with only the environment failures also seen on
  main (a load-sensitive one passes alone); mover-fs backup tests; all 27
  real-service TLS/admin tests. The SLES gates run in PR CI.

## CI result

PR48 CI run
[43466244306](https://github.com/joey-huckabee/background-file-mover/actions/runs/43466244306)
at `bb49f72` passes both full modes: production **405 tests per debug/release
profile** and nfs-qualification **409/profile** (increment139's 400/404 plus four
store cancellation tests and the real-service cancellation test). Independent
review had no findings (settlement ordering, committed-first race and in-flight
delivery confirmed). Merged to main as `afcb61f`.
