# Live dashboard updates: design

User request 2026-11-12: push status changes to the open dashboard without
polling and without a full-page refresh. The user approved proceeding on the
recommendations below ("Go with your recommendations"). Implemented in
[increment136](../RUST-INCREMENT-136.md); this note is the reviewed design.

## Transport

- **Server-Sent Events** on the admin listener: `GET /api/v2/admin/events`,
  `Content-Type: text/event-stream`, `Cache-Control: no-store`, close-delimited.
  Browsers use the built-in `EventSource`; no library, no WebSocket upgrade.
- Read-only. Authorized like other admin reads by the session cookie, checked
  before anything is sent (401 otherwise). `EventSource` cannot send custom
  headers, so there is no CSRF token or activity marker; a supplied `Origin` must
  match and a supplied `Sec-Fetch-Site` must be `same-origin` (403 otherwise).
- Stream traffic **never renews** the session. Background re-reads it triggers
  are ordinary unmarked reads, which do not renew either.

## Events

- `event: ready` once, then `event: changed` with `data: {"version":N}` when the
  service's state may have changed, plus `: keepalive` comments every 15 s.
  `event: signed-out` is sent before the server closes a stream whose session
  ended. `retry: 5000` sets the browser's reconnect delay.
- The signal comes from the single store worker thread: after any operation that
  changed rows (SQLite change counter moved), it bumps a version. A rolled-back
  write can produce a spurious event; that only causes a re-read, never wrong
  data. Events carry no job data: the page re-reads authoritative state.
- Bursts are coalesced: after a change the stream waits 250 ms and sends one
  event with the latest version.

## Slow or stalled clients

- Every stream write and flush (head, events, keepalives, `signed-out`) is
  bounded by 2 s. A client that stops reading is disconnected at the next write
  instead of holding capacity.
- Revocation and shutdown wake the stream immediately; its final `signed-out`
  write is bounded the same way, then the connection closes.
- After the request-permit handover the stream keeps its stream permit and the
  instance-ownership reference until its executor job is actually destroyed, as
  every TLS job does today.

## Session handling

- The stream re-checks its session on every wake-up and at least every 15 s, so
  inactivity expiry closes it within 15 s.
- Global sign-out, password activation and shutdown close every stream
  immediately (a revocation signal from the session manager).

## Connection budget (unchanged for requests and producers)

- At most **2** concurrent streams across the service.
- A connection starts as an ordinary admin request with its admin, network and
  global permits. When it becomes a stream it takes a stream permit and **gives
  its request permits back**, so open streams never reduce the request budgets,
  the producer cap of 6 or the reserved operator slot.
- The shared TLS executor grows from 6 to 8 job slots (2 threads), so the two
  long-lived stream jobs never take TLS capacity producers previously had.
- A third stream gets `503 service_busy`; the page then shows that live updates
  are unavailable and keeps the manual Refresh button working.

## Page behavior

- One `EventSource` per signed-in page. A small indicator shows Live,
  Reconnecting or Live updates unavailable.
- On `changed`, the page re-reads only what is visible: the current history page
  (same cursor and order), the open job's detail and reservations, Storage when
  shown. Rows and panels are updated in place; scroll position, the open detail
  and paging stay. The previous content stays until the new data arrives, so
  nothing flashes "Loading…".
- On reconnect the page re-reads visible state once, so a missed event cannot
  leave it stale. On `signed-out` the page returns to sign-in.
- `EventSource` does not expose HTTP status codes. When the stream fails
  permanently (`readyState` closed, for example a 401 after a restart or a 503 at
  capacity) the page performs one unmarked session check: 401 returns to sign-in;
  200 shows "Live updates unavailable" and tries one new stream after 30 s.
- One refresh cycle at a time; an event arriving during a refresh schedules a
  single follow-up refresh.

## Out of scope

Per-job event payloads, history of missed events, live updates for Settings
(configuration only changes on restart), and the cached **source free-space
reading** on the Storage page: it changes without a database write, so it is not
pushed; Refresh updates it. Everything else shown comes from the state database.
