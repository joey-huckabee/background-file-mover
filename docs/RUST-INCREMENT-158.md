# Increment 158: dashboard robustness pass

User request 2026-11-15: the robustness items of the roadmap's "UI review and
refinement" checklist: long paths, unknown sizes, large paginated histories,
empty/error/stale states, keyboard/focus, contrast and narrow layouts.
Dashboard assets only.

## Method

On the WSL demo with 304 jobs, including a job with four 50+ character folder
levels and a 150-character file name, a 40-file job, a job with an unmeasured
file and two jobs stopped for review; then with zero jobs. Headless Edge
screenshots at 1440, 1024, 800 and 390 px; an in-page WCAG contrast audit of
every visible text node against its actual background (overview, history,
attention, storage, settings); a keyboard audit with real key events
(40 Tab steps on Job history, dialog open/Escape); the service stopped while a
page was open.

## Findings and changes

| # | Finding | Change |
| --- | --- | --- |
| F5/F11 | An expanded job detail was as wide as the horizontally scrolling table: at 1440 px the third panel and the file list's Status/Size columns were cut off (also at 800 px) | The detail sticks to the left edge and is sized to the visible card (the table scroller is a CSS size container; `100cqw`) |
| F7 | A search with no results showed one small line | A centred "No jobs match these filters." with **Show all jobs** (clears search and filter, returns focus to the search box); footer reads "0 jobs" |
| F9 | At narrow widths the live status text ran into the breadcrumb | Below 800 px the top bar shows the status dot only (wording still announced), hides "Private admin interface" |
| F10 | At 390 px the history table showed only the Job column and the filter tabs overflowed | Below 600 px every table becomes stacked cards, each value labelled with its column (labels taken from the table header); tabs wrap |
| F12 | With the service stopped the top bar said "Reconnecting…" but the sidebar still said "Connected" | The sidebar status and dot follow the live connection: Connected / Reconnecting… / Not connected |
| Contrast | 26 text groups below WCAG AA, e.g. the "Live" label (1.43:1), inactive steps (2.59:1), most captions and table headers (3-4.4:1) | Darker text tones: muted `#5a665f`, Live `#2f6b45`, amber notices `#7a5414`, active nav count `#3c5a44`, sidebar label `#9fb5a6`; each at least 4.5:1 on its backgrounds. Remaining: decorative "›" and "/" (now `aria-hidden`) and the disabled pagination arrow (exempt) |
| Keyboard | Logical order and a visible focus indicator on all 40 steps; no way to skip the sidebar; the confirmation dialog focused itself while Back was still disabled | **Skip to content** button (first Tab stop; the hash is the view, so it moves focus to the main region); focus moves to Back once enabled; Escape still closes and returns focus to the opener |
| Empty | Zero jobs: clear empty states throughout; "select all" was still enabled | "Select all" disabled when the page has no rows |

Confirmed without change: long paths and file names wrap in the file list;
unknown sizes read "4.00 KiB + 1 unmeasured"; 304 jobs load in two list
batches and page at 50 per page ("page 1 of 7"); stat cards stack on a phone.

Known, not changed:
- Search matches job number, request ID and top-level folders, not nested
  folders or file names.
- At 1440 px the history table is still wider than its card (horizontal
  scroll for the destination column); the detail no longer depends on it.
- The 40-page loading bound (10,240 jobs) was not exercised here (unit tested
  in increment 145).
- Quick repeated sign-ins can briefly exhaust the live-stream slots: freed
  slots are noticed at the next 15 s keepalive, and the page retries after
  30 s, showing "Live updates unavailable" meanwhile.

## Tests

- Admin UI node tests; file-mover admin unit tests; all 12 admin TLS tests
  (document, CSP hashes, sessions, live stream, actions).
- Contrast audit after the changes: no failing text except the exempt
  decorative separators and disabled control.
- Keyboard audit: Tab order and focus indicators; dialog opens with Enter,
  focus inside, Escape closes, focus returns.
- Screenshots after the changes at 1440, 800 and 390 px, with the service
  stopped, and with zero jobs.
