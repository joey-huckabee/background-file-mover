# Increment 131: read-only admin job history and detail

The user authorized "the read-only job history" on 2026-11-11 after
[increment130](RUST-INCREMENT-130.md). This slice adds bounded history and job
detail reads to the admin HTTPS listener and the dashboard page. It adds no
action, dependency, filesystem probe or real state.

## Implemented boundary

- **`GET /api/v2/admin/jobs`** with optional `limit` (1–256, default 50) and
  opaque `cursor`. Ascending original job ID; `next_cursor` is null on the last
  page; `confirmation` is always null. Only `limit` and `cursor` are accepted,
  each at most once (400 `invalid_http` otherwise). `confirm_action`/`job_ids`
  return 400 `invalid_selection` ("Confirmation mode is not available") because
  actions are not implemented. A malformed cursor or one from another instance
  is 400 `invalid_cursor`.
- **Cursor** `c1.<instance_id>.<last_job_id>`, bound to the state instance.
  Clients must treat it as opaque. No snapshot across pages; cleared jobs vanish.
- **Summary rows** follow the frozen `JobSummary` shape: job ID, generator,
  `recording_id` or legacy `submission_id`, state, condition, source custody,
  `retry_review` (instance, job, current stored review epoch), `cancellation`
  `NotRequested` with null times and `deletion` null. The last two report the
  truth: those features do not exist yet.
- **`GET /api/v2/jobs/{id}`** on the admin listener returns exactly the operator
  `JobStatus` envelope for that job. Non-canonical IDs are 400 `invalid_job_id`;
  unknown or cleared jobs are 404 `not_found`. Job retention, global retention,
  resume and reset-missing stay unavailable to the admin audience (404).
- **One derivation.** Operator status, admin detail and list rows share one
  state/condition/details function, so they cannot disagree.
- **Store.** `status_page(after, limit)` reads one bounded page in a single
  transaction through the same per-job loader as `status`.
- **Reads** go through the existing bounded status thread (8-slot queue, 2 s
  reply deadline). Busy or unavailable storage is 503, never an empty success.
- **Authorization** for every admin GET: session cookie first (401), then for
  `Mover-Admin-Activity: interaction` the session CSRF token, matching Origin if
  sent and `Sec-Fetch-Site: same-origin` if sent (403). Only marked reads renew.
- **Page.** Job history table (job, identity, generator, state, condition,
  source custody) with Previous/Next by cursor stack, Refresh and a detail panel:
  facts, per-file phase, size, transfer phase and attempt, published count, exact
  measured total (or known bytes plus unmeasured count), missing files, delivery
  retry and latest audits. No background polling; Refresh, paging and opening a
  job are deliberate reads. Superseded replies are ignored. A 401 returns to sign-in.
- **Lossless JSON.** The page parses responses with a strict built-in parser that
  turns integers into BigInt, so u64 sizes and i64 values are never rounded.
  All service text is inserted with `textContent`.

## Not in this slice

Retention screen, overview cards, page-local search/filters, retry, cancel, clear,
delete and their confirmation previews. UI trim and refinement remain on the roadmap.

## Tests

- Store: `status_page` bounds, ascending order, `more` flag and equality with
  single-job status (SLES gate; native WSL SQLite cannot run store tests).
- Admin unit: strict query and cursor parsing.
- Real service over HTTPS: two committed jobs; full page fields; `limit=1` plus
  cursor pagination; foreign and malformed cursors; invalid/duplicate/unknown
  query keys; confirmation mode refused; 405 on POST; detail equals operator
  status; 404/400 detail errors; admin retention/action paths 404; marked read
  needs CSRF; global logout makes every read 401.
- Browser parser: `scripts/admin-ui/lossless-json.test.js` (u64/i64 extremes,
  escapes, malformed input), run in the hygiene workflow.

## Validation status

Pending PR CI for both full SLES modes and independent review.
