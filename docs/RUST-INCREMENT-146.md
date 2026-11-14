# Increment 146: bulk selection in Job history

Second step of the UI revisit (user, 2026-11-14), after the control-room layout
([145](RUST-INCREMENT-145.md)). Dashboard only: the cancel and clear routes
already accept 1-256 jobs with one confirmation proof.

## Change

- Job history has a checkbox per row and a select-all for the page, with an
  indeterminate state for partial selection. Selection survives paging,
  filtering and search, and is cleared after a successful action or sign-out.
- A selection bar shows the count with **Cancel jobs…**, **Clear from history…**
  and **Clear selection**. Each action is enabled only when at least one
  selected job qualifies:
  - Cancel: not delivered and no cancellation yet.
  - Clear: delivered, or cancelled with the stop confirmed.
- Only qualifying jobs are sent, at most 256 per round in job order. The
  confirmation lists them and says how many selected jobs were left out (and
  why).
- Confirmation uses the same proof flow as single-job actions. The proof is
  bound to the exact ordered job list for this account and session, and
  expires in 5 minutes. After a lost reply or 503 the identical request can be
  resent; the service cannot act twice.
- Results are shown as counts: cancel reports cancelling, already cancelling
  and skipped jobs; clear reports the number removed.
- Delete held copies stays per job: its proof binds one job's exact files.

## Tests

- Admin UI (node): eligibility for every job state, confirmation wording
  (including the "and N more" list), outcome wording from real parsed counts.
- Admin unit tests and all 12 real-service admin TLS tests pass.
- Visual check on the demo: three jobs selected, of which two delivered jobs
  qualify for Clear; the job waiting for review is left out with an
  explanation.
