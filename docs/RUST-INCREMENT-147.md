# Increment 147: dashboard review round 1

User review of the live dashboard, 2026-11-14. Dashboard assets only; no API
or behavior change on the service side.

## Change

- **Overview heading:** "The big picture" is now the page title (h1 size). The
  former title "Every file. Accounted for." and the small eyebrow line above it
  are gone on Overview. Other views keep their eyebrow.
- **Stage footer:** no longer repeats the "N stopped for review" count (the
  Needs attention tile and banner already show it). Cancelling and cancelled
  counts stay.
- **"Total jobs":** replaces "Retained jobs" (Overview tile) and "Jobs kept"
  (Storage tile); Settings shows "Maximum total jobs". It counts every job in
  the history: active, delivered, needing review or cancelled.
- **Sidebar:** the "Your files. Your network." text block is removed; the
  shield icon sits just above the account separator (hover text keeps the
  self-contained note).
- **Delete source files:** the per-job "Delete held copies…" action, its
  outcome messages and the Settings line are renamed. Same confirmation,
  same behavior.
- **Clear history button (Job history):** next to Refresh. It clears every
  loaded delivered or cancelled job, oldest first, at most 256 per confirmed
  request (the existing clear-history route and proof). Files are never
  deleted; there is no delete option in this flow. Jobs that are active or
  need review stay.
- **Modal confirmation:** bulk confirmations (Clear history button and the
  selection bar's Cancel jobs / Clear from history) now open a modal dialog
  instead of an inline notice. Escape or Back closes it, except while a request
  is in flight; a lost reply keeps the dialog open so Confirm resends the same
  request.
- **Refresh:** verified on the demo: it reloads the jobs list and storage
  reservations, disables itself while loading and re-enables afterwards.

## Tests

- Admin UI node tests: new `clearAllPlan` cases (eligibility, ordering, the
  256 bound and the "click again" note); delete outcome wording updated.
- file-mover admin unit tests and all 12 real-service admin TLS tests pass
  locally (the 5 known local-only reload tests need CI fixtures).
- Visual check on the WSL demo with headless Edge: Overview, Job history,
  the Clear history dialog (opened and closed with Back), Storage.
