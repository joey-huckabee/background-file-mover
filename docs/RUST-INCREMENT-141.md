# Increment 141: cancel confirmation, route and dashboard button

Second half of admin cancel, authorized by the user on 2026-11-13 ("go ahead with
cancel"; files stay in place). Builds on the schema-15 storage and safe stop of
[increment 140](RUST-INCREMENT-140.md).

## Change

- **Confirmation proof** (`file-mover/src/confirmation.rs`): HMAC-SHA256 over a
  framed scope: state instance, account principal, session revocation
  generation, action, exact ordered job IDs, the job-ID high-water mark at
  issuance and expiry. Wire form `c1.<expires_at>.<high_water>.<64 hex>`
  (contract `ConfirmationToken`). Valid for 300 s.
  The key is random per process and never stored, so a restart, a logout or an
  account activation voids every proof. Verification is constant-time and any
  mismatch (scope, order, duplicates, expiry, encoding) is the same refusal.
- **Confirmation mode** on `GET /api/v2/admin/jobs?confirm_action=cancel&job_ids=…`:
  same session rules as other reads (401 first). The query must contain exactly
  those two keys, each once. It takes 1–256 canonical positive IDs, keeping order
  and duplicates. Anything else is 400 `invalid_selection`. Only `cancel` is
  implemented; clear-history and delete-data follow in their own increments.
  The response is the contract `JobList` with
  `confirmation: {action, job_ids, token, expires_at, deletion_targets: [],
  complete: true}`. Cancel targets no files, so the preview is complete without
  deletion targets.
- **`POST /api/v2/admin/jobs/cancel`**:
  - Uses the same action authorization as retry, now one shared helper: session
    401, exact Origin / Sec-Fetch-Site and CSRF 403, media type 415.
  - The job-IDs-only body is checked first (400 `invalid_selection`).
  - The `Mover-Confirmation` proof must match that exact selection for this
    account and session generation, else 400 `invalid_confirmation`. Nothing is
    dispatched before that.
  - Each occurrence then runs `Store::admin_cancel` under the session admission
    guard, the same guard retry uses, so logout ordering holds.
  - Inactivity renews right after each newly accepted cancel.
  - The response is 202 `AttemptCounts`. A storage or queue failure returns 503
    without fabricated counts.
  - A resend of the same request is the approved lost-response behavior: a
    still-pending cancel counts failed, an already cancelled one skips.
- **Dashboard:** job detail Activity shows **Cancel job…** for any job that is not
  delivered and has no cancellation.
  - Clicking it fetches a proof and shows an inline confirmation: "Cancel job
    #N? The mover stops working on it and will not deliver it. Files it already
    took over, and any partly delivered files, stay where they are (see
    Storage). This cannot be undone.", with **Cancel job** and **Keep job**.
  - After a lost reply or 503 the same request can be resent until the proof
    expires.
  - Activity then shows "Cancellation requested …" or "Cancelled …".

## Review fixes

- A proof could have cancelled a job created after it was issued (preview
  `[2]` while only job 1 existed; job 2 created later; resend). The proof now
  authenticates the job-ID high-water mark at issuance, and the cancel route
  permanently skips any ID above it without dispatching. Missing IDs at or below
  it still skip silently. The admin TLS test covers both: before and after
  job 2 exists, the old proof skips it.
- CI failed once on formatting of the test file (fixed).

## Tests

- Unit: HMAC matches RFC 4231 cases 1 and 2; proofs bind instance, principal,
  generation, action, ordered IDs (including duplicates) and expiry, and refuse
  another process's key and malformed tokens.
- Admin UI (node): cancel outcome wording from real parsed counts.
- Real service (`admin_cancel_needs_a_matching_confirmation_and_stops_the_job`):
  - strict confirmation queries;
  - preview shape;
  - 405, 401, 403 and 415;
  - missing, mismatched and tampered proofs refused with no effect;
  - accepted cancel, and a resend that cannot cancel twice;
  - the job settles to Cancelled in detail and list;
  - a third send skips;
  - the sender's resubmission gets 409 `recording_cancelled` and its file stays;
  - after sign-out, the old proof is refused for a new session.
- Updated the admin list test: confirmation mode now answers for cancel.
- Local native runs (gate SQLite flags, private WSL namespace): fmt and workspace
  clippy clean, all 28 real-service TLS/admin tests. The SLES gates run in PR CI.

## CI result

PR49 CI run
[43468903580](https://github.com/joey-huckabee/background-file-mover/actions/runs/43468903580)
at `2f00db1` passes both full modes: production **408 tests per debug/release
profile** and nfs-qualification **412/profile** (increment140's 405/409 plus two
proof unit tests and the real-service cancel route test). An earlier run failed
on test-file formatting only. Independent review found one issue (a proof could
reach a job allocated after issuance), fixed by binding the issuance high-water
mark; re-review had no findings. Merged to main as `e28f0e9`.
