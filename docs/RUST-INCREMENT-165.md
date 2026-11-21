# Increment 165: file-name search

User request 2026-11-21: the dashboard leftovers ("go with 1"). User decision
the same day: **server search** for file names and nested folders. Implements
the reviewed [design](dashboard/FILE-NAME-SEARCH-DESIGN.md) (revision 2).

## Change

- **Route** `GET /api/v2/admin/jobs/search?q=&until=&cursor=` (`admin.rs`):
  - Same session, listener and `authorize_read` as the job list. A read
    marked as interaction needs the CSRF token and browser-header checks.
  - **Strict parsing:**
    - only `q`, `until` and `cursor`, each at most once;
    - `%` must be followed by two hex digits; `+` is a literal plus;
    - valid UTF-8 without control characters;
    - trimmed, 1–256 Unicode scalar values, then Unicode lowercase.
    - Errors are `400 invalid_query`.
  - **Cursor** `c1.<instance>.s.<sha256 of the normalized query>.<until>.<last
    scanned job>`. Any mismatch, or another cursor form, is `400
    invalid_cursor`.
  - **Reply:** `{"job_ids", "next_cursor", "scanned_jobs"}`.
- **One bounded chunk per request** (`mover-store` `search_file_paths`,
  observation `Search`):
  - one store call that scans `files` newest job first, in reverse
    primary-key order (no sort);
  - the path byte length is read before the text; a matched job skips its
    remaining paths;
  - stops at the next job boundary after 8,192 rows or 1 MiB of path text.
  - The page follows the cursor, so the observation thread and the store
    connection are free between chunks.
- **Dashboard** (`admin.js`, one delimited block):
  - The local match is still instant. After a 300 ms pause, the page searches
    file paths of the loaded jobs (`until` = oldest loaded job).
  - The union of both is shown. The footer reads "Searching file names… N jobs
    checked", or "File names could not be searched. Try again." on failure.
  - **Generations:** a newer query, a change of the loaded range (including
    "Load older jobs"), "Show all jobs" and sign-out abort the request and
    drop old replies. A range change, or a refresh after a failure, restarts
    the search as a background read.
  - Only the first request of a typed search is marked as interaction.
  - New matches redraw the list, keeping an open detail; otherwise only the
    note changes.
  - Placeholder: "Find a job, file, recording ID or folder".
- **Contract:** OpenAPI route `searchAdminJobFiles`, `$defs/JobFileSearch`,
  `invalid_query` in `AdminError`; route inventory in the checker.

## Tests

- **Store** (`file_name_search_matches_nested_paths_newest_first_in_bounded_chunks`):
  - nested folder and file name, case, newest first, distinct;
  - `before` and `until`;
  - the row and byte budgets stop at job boundaries, and continuation works;
  - invalid ranges are refused;
  - the query plan uses the primary-key index with no temporary B-tree.
- **Unit** (`search_query_is_strict_and_binds_cursors_to_the_query`):
  - normalization;
  - `+` and `%2B`;
  - 256 against 257 scalar values;
  - 21 invalid queries;
  - 8 cursor mismatches.
- **Real service** (`admin_file_name_search_matches_nested_paths_in_bounded_chunks`):
  - Setup: one producer job plus 33 jobs seeded offline with the service's
    context (8,196 file rows).
  - The first chunk ends at the job boundary after 8,192 rows; the cursor
    finds the oldest match.
  - Case and trimming; `until`.
  - A cursor reused with another query or `until`, a list cursor, or a
    foreign instance is refused, along with 7 invalid queries and POST.
  - A marked read needs the CSRF token.
- **Node** (`scripts/admin-ui/file-search.test.js`, CI `admin-ui`):
  - debounce, the marked first request and unmarked continuations;
  - cursor following, redraws only on new matches, progress;
  - abort and dropped replies for a newer query;
  - restarts on a range change and on "Load older jobs", none for an
    unchanged range;
  - failure and retry;
  - no request for empty, over-long or control-character queries;
  - cancel.
- Contract checker; fmt and workspace clippy.

## Not covered

- Jobs the page has not loaded are not searched; "Load older jobs" includes
  them.
- Rare Unicode case-folding differences from JavaScript (for example a final
  sigma).
