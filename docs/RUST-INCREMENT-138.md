# Increment 138: admin delivery retry route and dashboard button

Second half of reviewed admin delivery retry, authorized by the user on
2026-11-13 ("go ahead with retry delivery"; per-job button approved). Builds on
the schema-13 receipt storage of [increment 137](RUST-INCREMENT-137.md). No real
installation is migrated or changed by this work.

## Change

- **`Mover-Retry-Context` codec** (`file-mover/src/retry_context.rs`) mirrors
  `docs/api/check_retry_context_candidate.py`: one header occurrence, 6144-byte
  value, `v1.` + canonical unpadded base64url, 4096-byte decoded payload, strict
  fixed-key JSON (no unknown or duplicate fields, no fractions), canonical
  re-encode, `{"job_ids":[...]}` body (1-256 exact positive i64), selection
  SHA-256 over `BFM-RETRY-SELECTION\0v1\0` + count + IDs, epoch count, repeated-ID
  epoch consistency, then instance. All 4 known answers and 52 decoding cases of
  `docs/api/retry-context.candidate.vectors.json` pass from an embedded copy; CI
  `cmp`s the copy against the contract file.
- **`POST /api/v2/admin/jobs/retry`** on the admin listener. Precedence:
  405, session 401, exact Origin / Sec-Fetch-Site / CSRF 403, media type 415,
  then whole-request validation before any occurrence: sizes 431
  `request_headers_too_large`, bad body 400 `invalid_selection`, other context
  errors 400 `invalid_retry_context`, wrong instance 409 `review_conflict`, and a
  non-null epoch for a never-allocated job ID 400 `invalid_retry_context`.
  Each occurrence then rechecks the session (revocation wins, 401) and runs
  `Store::admin_retry` on the observation thread. Receipt capacity or a full
  queue returns 503 `service_busy`, storage failure 503 `storage_unavailable`;
  earlier occurrences stay committed and an unchanged resend replays them.
  Success is 202 `{accepted_count, failed_count, skipped_count}`.
- **Receipt key:** SHA-256 of `BFM-RETRY-RECEIPT\0v1\0` + account principal +
  `\0` + canonical payload bytes. The principal is the server-held account ID
  (`Authorized::principal`), never client input; it is also the audit actor.
- **Dashboard:** the job detail Activity panel shows a **Retry delivery** form
  when the job needs review after 3 failed attempts and its list row has a
  non-null review epoch. The explanation is required (plain single-line text,
  at most 512 bytes). The context is frozen at the first click using the row's
  instance, exact job ID string and epoch (browser SHA-256, canonical JSON with
  only `"` and `\` escaped). A lost reply or 503 offers "Send retry again", which
  resends the identical request so the service replays the stored outcome. Live
  updates pause while the explanation is being typed, then resume.

## Review fixes

- Each occurrence's store decision runs under the session lock
  (`Sessions::while_authorized`), so a logout either finishes first (the
  occurrence is refused with 401, nothing disclosed) or waits for it.
- Inactivity renews only when the batch newly admitted work (accepted, not a
  replay); rejected requests, replays and all-skipped/failed batches do not.
- The dashboard compares the parsed BigInt failure count correctly, and a frozen
  retry stays visible and resendable across live refreshes until a readable
  final reply reconciles it, even if the job has left review; an unreadable 202
  keeps it uncertain.

## Tests

- Unit: all reference vectors; maximum-width payload equals the published
  bounds; receipt key depends on principal and exact context.
- Session: gated work blocks a concurrent logout until done, runs nothing
  after revocation and never renews.
- Admin UI (node): eligibility and outcome text from real parsed (BigInt)
  service JSON; the browser encoder reproduces the single-job known answer
  byte for byte; escaping equals JSON escaping for valid reasons; invalid
  reasons (empty, controls, lone surrogates, over 512 bytes) are refused.
- Real service (`admin_retry_delivers_a_reviewed_job_and_replays_its_receipt`):
  a destination collision makes delivery fail; the job reaches review; every
  refusal above (405/401/403/415/400/409/431) leaves it in review; the retry is
  accepted, an exact resend replays it, the recording commits, the original
  outcome still replays after commit, a new or null context skips, the audit
  records the account principal and exact reason, and after sign-out the
  request is 401.
- Local native runs (gate SQLite flags, private WSL namespace): fmt and clippy
  clean, file-mover unit tests pass except the reload tests that need the gate's
  TLS fixture variable, all 27 real-service TLS/admin tests pass. The SLES gates
  run in PR CI.
