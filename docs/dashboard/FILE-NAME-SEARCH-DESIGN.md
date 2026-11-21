# File-name search: design

Status: proposed, for review. User request 2026-11-21 ("go with 1": the
dashboard leftovers). User decision the same day: **server search** for file
names and nested folders.

## Problem

Job history search matches the job number, request ID and the job's top-level
source and destination folders (`admin.js` `matches`). It does not match file
names or nested folders, because the job list does not carry them.

A job holds up to 256 files, and the dashboard loads up to 10,240 jobs per
round. Sending every name with the list could reach gigabytes, so the server
matches names and returns only job IDs.

## Route

`GET /api/v2/admin/jobs/search?q=<text>[&cursor=<token>]`

- **Access:** same admin listener, session and checks as `GET
  /api/v2/admin/jobs` (`authorize_read`). Read-only; no body; no CSRF needed.
  Like other reads, it counts as activity only when the page sends the
  interaction header.
- **`q`:** percent-decoded UTF-8 with no control characters; 1–256
  characters after trimming. Otherwise `400 invalid_query`.
- **Match:** case-insensitive substring of a file's **relative path**, so
  nested folders match too (`2026/run-7/a.wav` matches `run-7`). Both sides
  are folded with Unicode lowercase (Rust `to_lowercase`, matching the page's
  `toLowerCase` for practical purposes).
- **Order and bound:** newest job first. At most **1,024 job IDs** per reply.
- **Reply** `200`:
  ```json
  {"job_ids": ["10540", "10537"], "next_cursor": null}
  ```
  - `job_ids`: decimal strings, descending, distinct.
  - `next_cursor`: when more jobs remain unscanned, an opaque token in the
    history-cursor form bound to the instance and the search
    (`c1.<instance>.s.<last scanned job>`). A token from another instance or
    order is `400 invalid_cursor`.
- **Contract:** the candidate schema gains the route and its reply.

## Bounded cost

- The scan walks jobs newest first in chunks: one store call reads the next
  256 job IDs and their file paths (at most 65,536 rows). The service's single
  store connection serves claims and delivery between chunks.
- A reply ends when it holds 1,024 matches or has scanned **2,048 jobs** (8
  chunks), whichever comes first. It then returns `next_cursor`, so one
  request's work stays bounded however large the history is.
- No index or schema change.

## Dashboard

- Typing in the search box keeps today's instant local match. After the input
  has been still for 300 ms, the page also asks the server (request kind
  `search`, so a newer query aborts the older one in the browser).
- The page follows `next_cursor` until the reply's last scanned job is older
  than the oldest loaded job, or no cursor remains. It never searches beyond
  what is loaded, and the existing "Showing the newest N jobs only" notice
  still applies.
- Results are the union of local matches and server matches, in the current
  sort.
- While the server search runs, the status line reads "Searching file
  names…". If the search fails, local matches stay and the line reads "File
  names could not be searched. Try again."
- An empty query clears the server matches.

## Tests

- **Real service** (admin listener):
  - a nested folder and a file name each find their job;
  - case is ignored;
  - a non-matching query returns nothing;
  - control characters, an empty or over-long query, and a foreign cursor
    are refused;
  - over 2,048 jobs, the cursor continues the scan and finds an old match.
- **Node** (`scripts/admin-ui`): debounce, abort on a newer query, union with
  local matches, cursor following stopping at the oldest loaded job, and the
  failure message.

## Not covered

- No server-side search over jobs the page has not loaded; "Load older jobs"
  stays the way to include them.
- Unicode case folding differs from JavaScript's in rare cases (for example
  a final sigma), so a match may differ from what the page alone would find.
