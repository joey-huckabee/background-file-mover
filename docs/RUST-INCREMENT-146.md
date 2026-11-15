# Increment 146: bulk selection in Job history

Second step of the UI revisit (user, 2026-11-14), after the control-room layout
([145](RUST-INCREMENT-145.md)). Dashboard only: the cancel and clear routes
already accept 1-256 jobs with one confirmation proof.

## Change

- Job history has a checkbox per row and a select-all for the page, with an
  indeterminate state for partial selection. Selection survives paging,
  filtering and search. After a successful batch only the jobs actually sent
  are deselected; jobs beyond the 256 limit and jobs that did not qualify stay
  selected. Sign-out clears it.
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

- While a confirmation is open or being sent, the selection is locked
  (checkboxes and select-all disabled), so the confirmed request and its resend
  after a lost reply cannot be changed or lost.

## Tests

- Admin UI (node): the selection lock holds while confirming, while sending and
  after a lost reply; partial deselection keeps the over-limit and
  non-qualifying jobs selected; eligibility for every job state, confirmation wording
  (including the "and N more" list), outcome wording from real parsed counts.
- Admin unit tests and all 12 real-service admin TLS tests pass.
- Visual check on the demo: three jobs selected, of which two delivered jobs
  qualify for Clear; the job waiting for review is left out with an
  explanation.

## CI result

PR59 CI run
[43654707264](https://github.com/joey-huckabee/background-file-mover/actions/runs/43654707264)
at `dd515d1` passes both full modes (dashboard assets only; no Rust test count
change). Independent review found two issues (selection changes could discard a
frozen request; a batch cleared unsent selections), both fixed; re-review had no
findings.
