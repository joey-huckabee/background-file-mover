# Increment 145: dashboard on the original control-room design

User request 2026-11-13: "revisit the original UI design which was way better
than what we have now". The original is the control-room concept in
[docs/dashboard/mockup.html](dashboard/mockup.html) (2026-11-10). This increment
moves the live dashboard onto that design. It keeps the earlier review decisions
recorded in [UI-REVIEW-2026-11-12](dashboard/UI-REVIEW-2026-11-12.md): no Generator
column, Received › Acquired › Copied/Moved steps, source and destination folders,
inline expanding job detail, and the plain-language Activity panel.

No new API: every view uses existing routes.

## Change

- **Layout and style:** the mockup's visual system (forest-green sidebar, ivory
  canvas, cards, stat tiles, line icons) is now the dashboard stylesheet. It is
  `mockup.css` minus the design-study banner, followed by the existing component
  rules and a small integration block. The page stays self-contained, and the
  hash-pinned style and script CSP is unchanged in form.
- **Sidebar navigation:** Overview, Job history (count), Needs attention (amber
  count when non-zero), Storage and Settings; account and sign-out at the
  bottom; live-update state and "Private admin interface" in the top bar.
  Views have bookmarkable URLs (`#overview`, `#history`, …).
- **Overview (new):**
  - stat tiles for active (delivering / waiting for files), delivered, needs
    attention and retained jobs;
  - a "From source to destination" stage strip;
  - storage reservation meters from `/api/v2/retention`;
  - a "jobs need a closer look" banner linking to Needs attention;
  - the five most recent jobs.
- **Needs attention (new):** every job waiting for a review; opening one jumps
  to its detail in Job history.
- **Job history:** filter tabs (All, Active, Needs attention, Delivered,
  Cancelled) and search by job number, recording ID or folder, with sort, client
  paging (50 per page) and the existing inline detail and actions.
- **Data:** the page loads every kept job through the existing list route, 256
  per page and at most 40 pages, so totals, filters and search cover all jobs.
  Live updates reload it.
- **Storage and Settings:** unchanged content, restyled.

Bulk selection (checkboxes with bulk cancel and clear) is a separate later step.

## Review fixes

- **No silent truncation:** jobs load newest first, so recent jobs, attention
  alerts and search always cover the newest work. When more jobs exist beyond
  the 40-page bound, a page-wide notice on Overview, Job history and Needs
  attention says that only the newest jobs are loaded and that totals, alerts and
  search exclude older ones. Needs attention never claims "nothing needs your
  attention" outright in that case. **Load older jobs** continues loading.
- **Bookmarks:** after the session is restored the selected view initializes,
  so `#settings` and `#storage` load directly; live updates also refresh
  Settings.
- **Accurate stages:** a pending cancellation is still active work (shown as
  "cancelling"), not cancelled, and jobs stopped for review are no longer counted
  as delivering. The stage footer lists review, cancelling and cancelled counts.
- **Accessibility:** filter buttons expose `aria-pressed`, kept in sync on every
  change, including when opening a job from another view.

## Tests

- Admin UI node tests unchanged and passing.
- All 12 real-service admin TLS tests pass against the new page (document, CSP
  hashes, sessions, live stream, actions).
- Visual check on the WSL demo with headless Edge (signed in through the real
  login form): Overview, Job history with an expanded job detail, Needs
  attention, Storage and Settings.

## CI result

PR56 CI run
[43612140574](https://github.com/joey-huckabee/background-file-mover/actions/runs/43612140574)
at `e8ad760` passes both full modes (no Rust test count change; dashboard assets
only). An earlier run failed the document test because the inline SVG carried an
`xmlns` URL (removed). Independent review raised five findings across two rounds
(truncation, bookmarked views, stage accuracy, filter accessibility, page-wide
incomplete notice), all fixed; final re-review had no findings.
