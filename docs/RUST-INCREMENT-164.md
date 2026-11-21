# Increment 164: large job history loading test

User request 2026-11-21: the dashboard leftovers from increment 158 ("go with
1"). This increment covers the first: no automated test exercised the
dashboard's 40-page loading bound or "Load older jobs" (increment 158, "Known,
not changed"). File-name search follows separately.

## Change

Test only; the dashboard code is unchanged.

- `scripts/admin-ui/history-loading.test.js` runs the page's own `fetchAll`
  and `renderCompleteness` (sliced from `admin.js`, as the existing
  lossless-JSON test does) against a fake list route. The fake serves jobs
  newest first, 256 per page, with exact cursors, as the service does.
- The hygiene workflow's `admin-ui` job runs it.

## Cases

- **10,540 jobs:**
  - The first round loads exactly 40 pages: the newest 10,240 jobs, held
    oldest first.
  - The cursor stops at the first job not loaded.
  - "Load older jobs" and the notice "Showing the newest 10240 jobs only." are
    shown.
  - Only the first page of a deliberate load is sent as user interaction.
  - "Load older jobs" (budget +40) reaches job 1. The button and notice go.
- **Exactly 10,240 jobs:** complete; no button, no notice.
- **10,241 jobs:** the one oldest job is reported as not loaded.
- **Settings view:** the button stays but the notice is hidden.
- **Errors:**
  - A superseded load (a newer one started) stops without results.
  - A failing page rejects the whole load, with no partial list.
- **Empty history:** one request; no button.

## Not covered

- Real-browser rendering of 10,000+ rows; the history table renders one
  50-job page at a time.
- Server paging is covered by the existing admin listener tests
  (`tls_listener/admin.rs`).
