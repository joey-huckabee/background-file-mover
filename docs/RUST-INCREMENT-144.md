# Increment 144: delete retained data: confirmation, route, setting and button

Second half of "delete retained data" (user request 2026-11-13; decisions:
cancelled jobs allowed with a plain warning, off by default behind a setting).
Builds on the engine of [increment 143](RUST-INCREMENT-143.md).

## Change

- **Setting `admin_ingress.allow_data_deletion`** (default false):
  - When off, delete-data confirmation mode is 400 `invalid_selection`, the
    route is 404 `not_found`, and the session reply says
    `data_deletion_enabled: false`, so the dashboard hides the button.
  - The Settings page shows the value.
  - The demo turns it on; nothing else does.
- **Confirmation binding:** proofs now carry an authenticated `binding` field.
  Wire form: `c1.<expires>.<high_water>.<binding>.<mac>`.
  - Cancel and clear use `-`.
  - Delete uses the 64-hex fingerprint of the job's exact deletable selection
    at its current pass version (increment 143), so the token stays far below
    6144 bytes.
- **`GET …/admin/jobs?confirm_action=delete-data&job_ids=<one id>`:**
  - The response contains the contract `deletion_targets` (`job_id`, `file_id`,
    `kind: RetainedSource`, `relative_path`, `attempt: null`, `size_bytes`) and
    a proof bound to them.
  - Delete is **per job** in this increment: the dashboard acts per job, and
    the bound fingerprint keeps replay and staleness exact. Bulk deletion can
    follow if wanted.
  - Missing, unfinished or busy jobs preview no targets.
- **`POST /api/v2/admin/jobs/delete-data`**:
  - Checks in order: setting, action authorization (401, 403, 415), one-job body
    (400 `invalid_selection`), and proof (400 `invalid_confirmation`).
  - IDs above the issuance high-water mark get zero counts.
  - Under the session admission guard, `Store::start_deletion` then:
    1. replays or observes the pass this proof started, or an active pass;
    2. returns 409 `stale_confirmation` if the selection changed (including an
       older proof after a newer pass);
    3. returns zero counts for a no-work or ineligible job;
    4. otherwise starts the pass, and inactivity renews.
  - The response is 202 `DeleteAccepted` (`deleted_count`, `failed_count`,
    `completion_pending`). The delivery thread removes the files afterwards;
    job detail shows the latest pass.
- **Dashboard:**
  - **Delete retained data…** appears on delivered and cancelled jobs when the
    setting is on.
  - The confirmation lists the files and total size. It says delivered files at
    the destination are not touched; for a cancelled job it warns: "this job was
    never delivered. These are the only copies of the recording and will be
    permanently destroyed."
  - Confirm is disabled when nothing is left.
  - Activity shows "Deleting retained copies…" and then the counts. A stale
    proof says that nothing was deleted and to start again.
  - The confirmed-action component (cancel, clear, delete) gained per-action
    previews.

## Tests

- Unit: the proof binding is authenticated (a changed or removed fingerprint is
  refused), alongside the existing RFC 4231, scope and expiry checks.
- Admin UI (node): delete confirmation lists files and size, warns for
  undelivered jobs, blocks confirm with nothing to delete; outcome wording.
- Real service (`admin_delete_data_is_off_by_default_and_removes_only_retained_copies`):
  - off by default (session flag, no preview, 404);
  - enabled: preview lists the two retained files exactly;
  - a two-job selection and a cancel proof are refused;
  - delete removes only `.file-mover` copies while delivered output and
    `COMMITTED.json` stay;
  - the same proof replays the finished pass;
  - a fresh proof with nothing left is zero work;
  - a cancelled job's older proof is 409 stale after a newer pass deleted its
    copy;
  - the job is then cleared.
- Session test updated for the new `data_deletion_enabled` field.
- Local native runs (gate SQLite flags, private WSL namespace): fmt and workspace
  clippy clean, proof unit tests, all 30 real-service TLS/admin tests (the
  load-sensitive live-stream test passed alone). The SLES gates run in PR CI.
