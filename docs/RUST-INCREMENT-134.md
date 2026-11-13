# Increment 134: dashboard UI refinement from the live review

Applies the user's decisions from the [2026-11-12 UI review](dashboard/UI-REVIEW-2026-11-12.md)
to the read-only dashboard, with two contract extensions the user approved. The
user asked to review the result live rather than answer more questions first
("Just go with it and we will review after it is being hosted by the server").
No action, dependency or real state.

## Page changes

- **Sign-in:** brand panel and tagline kept; the three helper lines removed.
- **Job history:**
  - Columns: Job (number + Request ID), Progress, Files delivered, Size, Source
    folder, Destination folder. Every header has hover text.
  - Progress: **Received › Acquired › Copied|Moved** steps plus a badge only for
    Waiting for files, Ready to deliver, Retrying delivery or Needs review.
  - Job column toggles **oldest/newest first** (server-side order).
  - Session-timeout and read-only notes removed.
- After live review: Progress steps are pill badges colored per stage (Received
  blue, Acquired teal, Copied/Moved solid green; unreached steps outlined grey),
  and "Sign out everywhere" is labelled **Sign out** (hover: signs out every
  session; transfers keep running).
- **Job detail** opens **inline** under the selected row (one open at a time) in
  a three-panel layout (Job, Activity, Storage reserved) above the files table.
  All facts in plain wording; hover shows the technical field and value. Files:
  File | Status (Waiting/Acquired/Verified/Delivered) | Size | Attempts. The
  job's reservations load inline after the detail (sequentially, because the
  admin listener still admits one connection at a time).
- **Storage** (was Retention): Reserved at source/destination, Jobs kept, Files
  with unknown size; details list including Files acquired; one-line footnote.
- **Settings** (new, read-only): provenance line, then Transfers, Storage limits,
  Producer connection (approved sender fingerprints), Dashboard, Certificates and
  keys (subject, expiry date, warning under 30 days or expired) and Internal.
- If login succeeds but the browser keeps no session cookie, the sign-in form
  now says so instead of silently returning.

## Contract extensions (approved 2026-11-12)

- `JobSummary` gains `files_total`, `files_delivered`, `measured_bytes` (decimal
  string), `unmeasured_files`, `source_folder`, `destination_folder` (relative to
  the roots recorded with each job; `source_folder` is empty for a job submitted
  from the source root itself, shown as "(source root)") and `transfer_mode` (`Copy` unless source cleanup after
  delivery is actually enabled; it is not today).
- `GET /api/v2/admin/jobs` gains `order=asc|desc` (default asc). Cursors are now
  `c1.<instance>.<a|d>.<last>` and continue only their own order (400
  `invalid_cursor` otherwise). Store `status_page` reads either direction in one
  transaction.
- New `GET /api/v2/admin/settings`: startup snapshot of configuration with paths
  and certificate subject/expiry; never key material, verifiers or file contents.
  Same read authorization as other admin GETs.
- Certificate subject and expiry come from a small dependency-free DER reader
  (`cert_info.rs`) over certificates already loaded and verified at startup;
  malformed input yields no value, never an error.

Recorded in `docs/api/openapi.candidate.json` and `contract.candidate.schema.json`.

## Tests

- Unit: DER reader (UTCTime/GeneralizedTime, long-form lengths, every truncation
  of a valid certificate), cursor/order parsing, cursor encoding, descending store
  pages.
- Real service: new row fields for a committed job, descending pages and
  order-bound cursors, settings fields including the approved client fingerprint
  and a DER-read expiry, no key bytes or verifier in settings, 401/405 on settings.
- Fixed a race in increment129's `real_verification_issues_only_for_exact_credentials`:
  consecutive logins now wait for the verifier thread to exit (the slot is held
  until actual exit, which can trail the reply under load).
- Browser: parser and byte-format tests unchanged and still passing.

Independent review found two P2 issues in the first revision: the schema forbade
the legitimate empty source folder, and the page implied folders are relative to
the currently configured roots. Both fixed: the schema allows and documents the
empty value, and hover text says folders are relative to each job's recorded
roots, which can differ from Settings for older jobs.

## Validation status

Pending PR CI for both full SLES modes, independent review and the user's live review.
