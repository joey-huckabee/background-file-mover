# Increment 142: dashboard history clear

Authorized by the user on 2026-11-13 ("Go ahead and start the clear history").
Builds on cancel ([140](RUST-INCREMENT-140.md)/[141](RUST-INCREMENT-141.md)) and
the offline clear of [increment 107](RUST-INCREMENT-107.md). No schema change.

## Change

- **Eligibility** (one shared rule for the offline CLI and the dashboard):
  delivered jobs, and jobs whose cancellation completed (state Cancelled with
  the stop confirmed). Pending cancellations and all other unfinished work are
  not eligible; missing IDs skip silently, as the contract requires.
- **What clear does:** in one transaction it forgets the job and every linked
  record: files, claims, reservations, transfers, manifests, destination
  binding, delivery failures, operator and missing-file audits, retry receipts,
  problem record and cancellation. Instance identity and the job-ID high-water
  mark stay, so IDs are never reused. **No file is touched**: delivered files
  stay at the destination; files the mover took over for a cancelled job stay
  where they are and are no longer tracked or counted (contract group 50; delete
  retained data first if that is wanted, in its own later increment).
- **Online, with the service running:** `Store::admin_clear` evaluates "a worker
  may still be on this job" inside its own immediate transaction, the same
  pattern as cancellation settlement. The delivery thread publishes the job it is
  working on for the whole per-job block, including failure recording. The claim
  thread's "processing a submission" flag also counts. Store transactions are
  serialized, so once a job is forgotten no worker continues with it. A busy job
  is retried for about 2 s, then skipped.
- **`POST /api/v2/admin/jobs/clear-history`** with confirmation mode on the list
  route (`confirm_action=clear-history`):
  - Same action authorization, body and proof checks as cancel; the proof is
    bound to `clear-history` and the issuance high-water mark.
  - Each occurrence runs under the session admission guard; inactivity renews
    after each job actually cleared.
  - Returns 200 `{cleared_count}`: the actual number forgotten.
- **Dashboard:** delivered and cancelled jobs show **Clear from history…** in
  the job detail.
  - The confirmation says what is forgotten, and that no files are touched. For
    a cancelled job it adds that taken-over files will no longer be tracked or
    counted.
  - The row disappears after a successful clear.
  - Cancel and clear now share one confirmed-action component in `admin.js`.

## Review fixes

- The confirmation now states the complete group-50 effect: the job's record,
  activity, accounting and recording ID are forgotten (submitting the same
  recording again creates a new recording), and no files are touched but all
  leave mover management. Delivered files stay at the destination and the
  taken-over source files stay where they are, untracked. A node test checks the
  wording for delivered and cancelled jobs.

## Tests

- Store: online clear clears delivered and settled-cancelled jobs, skips
  missing/unfinished/pending-cancel jobs, defers while a worker is on the job
  (nothing changes), repeats skip, later actions on the old ID skip, unrelated
  jobs untouched, every linked table emptied for cleared jobs; the offline clear
  now accepts completed cancellations but not pending ones.
- Admin UI (node): clear outcome wording.
- Real service (`admin_clear_history_forgets_delivered_and_cancelled_jobs_but_keeps_files`):
  - 405, and a cancel proof cannot clear;
  - an unfinished job is not cleared;
  - a delivered job is forgotten (404 on detail and operator status) while its
    delivered files and `COMMITTED.json` stay;
  - a resend removes nothing;
  - a job cancelled through the dashboard is cleared after its stop is
    confirmed, and its taken-over file stays on disk;
  - the history list is then empty.
- Local native runs (gate SQLite flags, private WSL namespace): fmt and workspace
  clippy clean; all 29 real-service TLS/admin tests; mover-store suite (only the
  known load-sensitive UUID race test, which passes alone); full API suite with
  only environment failures also seen on main or passing alone. The SLES gates
  run in PR CI.
