# File-name search: design

Status: revision 2 reviewed and approved 2026-11-21; implemented in
[increment 165](../RUST-INCREMENT-165.md). User request 2026-11-21 ("go with
1": the dashboard leftovers). User decision the same day: **server search**
for file names and nested folders.

## Problem

Job history search matches the job number, request ID and the job's top-level
source and destination folders (`admin.js` `matches`). It does not match file
names or nested folders, because the job list does not carry them.

A job holds up to 256 files, and the dashboard loads up to 10,240 jobs per
round. Sending every name with the list could reach gigabytes, so the server
matches names and returns only job IDs.

## Route

`GET /api/v2/admin/jobs/search?q=<text>[&until=<job>][&cursor=<token>]`

### Access

- Same admin listener and session as `GET /api/v2/admin/jobs`, through
  `authorize_read`. Read-only; no body.
- A **background** read carries no activity header and needs no CSRF token.
- A read marked as interaction (`Mover-Admin-Activity: interaction`) needs
  the session-bound CSRF token and passes the existing browser-header checks,
  exactly as marked list reads do today.
- The page marks only the **first** request of a search the user typed.
  Cursor continuations and restarts caused by history reloads are background
  reads.

### Parameters

- **Parsing:**
  - The query string is split on `&`. Each part is `name=value`.
  - Allowed names: `q` (required), `until` and `cursor` (optional).
  - Each name may appear at most once. An unknown, duplicate or missing
    parameter is `400 invalid_query`.
  - Percent-decoding accepts only `%` followed by two hex digits. Anything
    else after `%` is `400 invalid_query`.
  - `+` is a literal plus sign, not a space. The page encodes with
    `encodeURIComponent`, so a space arrives as `%20`.
- **`q`:**
  - The decoded bytes must be valid UTF-8 with no control characters
    (Unicode `Cc`).
  - **Normalized query:** trim Unicode white space at both ends (Rust
    `str::trim`), then fold with Unicode lowercase (`to_lowercase`).
  - The trimmed text must be 1–256 Unicode scalar values (counted before
    folding).
  - Any violation is `400 invalid_query`.
  - The normalized query is used both for matching and for cursor binding.
- **`until`:** a canonical positive decimal job ID. Only jobs with
  `job_id >= until` are scanned. The page passes its oldest loaded job, so the
  search never goes past what the page shows.
- **`cursor`:** see below.

### Match and reply

- **Match:** the normalized query is a substring of the Unicode-lowercased
  **relative path** of any of the job's files. Paths include nested folders,
  so `2026/run-7/a.wav` matches `run-7`.
- **Order:** newest job first.
- **Reply `200`:**
  ```json
  {"job_ids": ["10540", "10537"], "next_cursor": "c1.…", "scanned_jobs": 412}
  ```
  - `job_ids`: decimal strings, descending, distinct; matches in this reply
    only.
  - `scanned_jobs`: jobs whole-scanned by this reply (for progress text).
  - `next_cursor`: `null` when every job down to `until` (or job 1) has been
    scanned. Otherwise an opaque token continues the scan.

### Cursor

- **Form:** `c1.<instance>.s.<query digest>.<until>.<last scanned job>`.
  - The query digest is the hex SHA-256 of the normalized query's UTF-8
    bytes.
  - `until` is `0` when absent.
- **Checks:** a cursor whose instance, digest or `until` does not match the
  request is `400 invalid_cursor`. So is one in another form, for example a
  list cursor.
- **Meaning:** the next reply scans jobs older than the last scanned job.

## Bounded cost

Each request does **one** bounded store call and returns. The page, not the
service, follows the cursor. So:
- the single observation thread is free between chunks for other admin reads;
- the single store connection is free for claims and delivery;
- a browser abort stops further chunks, because none is ever requested.

Inside the one store call:
- Rows are read newest job first, `(job_id DESC, file_index)`.
- For each row, the path's byte length is read before its text.
- A job is always scanned whole; once one of its files matches, its remaining
  files are skipped.
- The call stops at the next job boundary once it has read **8,192 file
  rows** or **1 MiB** of path text. A job has at most 256 paths of at most
  4 KiB each, so one call reads at most 8,448 rows and 2 MiB of path text.
- Each path is lowercased on its own. No other per-row allocation is kept,
  except a matching job's ID.
- No index or schema change.

Typical histories (tens of files per job, short names) need one or a few
requests per search. A worst-case history (10,240 jobs × 256 × 4 KiB paths)
needs about 10,000 (one 1 MiB job per call). Each request stays bounded, and the page shows progress.

## Dashboard

- Typing keeps today's instant local match. After the input has been still for
  300 ms, the page starts a server search for the normalized query, with
  `until` = its oldest loaded job.
- **Generations:** a search generation counter increases on a query change, a
  history reload that changes the newest or oldest loaded job (including "Load
  older jobs"), and sign-out.
  - A reply from an older generation is dropped.
  - Its continuation is never requested, and the browser request is aborted
    (request kind `search`).
  - A history reload that changes the loaded range restarts the active search
    over the new range, as a background read.
- Results are the union of local matches and server matches, in the current
  sort.
- **Status line:**
  - while running: "Searching file names… N jobs checked";
  - on failure, local matches stay and the line reads "File names could not
    be searched. Try again.";
  - an empty query clears the server matches.

## Contract

The candidate schema gains the route, its parameters, the reply object and the
`invalid_query` and `invalid_cursor` errors.

## Tests

- **Real service** (admin listener):
  - a nested folder and a file name each find their job;
  - case is ignored;
  - a non-matching query returns nothing;
  - the query parsing errors are refused: control characters, empty or 257
    scalar values, bad `%` escapes, duplicate or unknown parameters;
  - `+` and `%2B` both search for a literal plus;
  - a cursor is refused with another query, another `until`, or as a list
    cursor;
  - `until` stops the scan;
  - with more than 8,192 file rows, the cursor continues and finds an old
    match;
  - marked reads require CSRF; background reads don't.
- **Node** (`scripts/admin-ui`):
  - debounce, and an abort on a newer query;
  - the union with local matches;
  - cursor following to `null`;
  - dropping stale-generation replies, and a restart on "Load older jobs";
  - the activity header only on the first request;
  - the failure message.

## Not covered

- No search over jobs the page has not loaded; "Load older jobs" stays the
  way to include them.
- Unicode case folding differs from JavaScript's in rare cases (for example a
  final sigma), so a match may differ from what the page alone would find.
