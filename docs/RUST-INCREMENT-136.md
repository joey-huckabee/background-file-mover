# Increment 136: live dashboard updates

Implements the reviewed [live updates design](dashboard/LIVE-UPDATES-DESIGN.md):
the open dashboard updates itself when service state changes, with no polling
and no full-page refresh. The user approved the recommended approach ("Go with
your recommendations").

## Change

- **Signal:** the store worker bumps a "state may have changed" version after
  any operation that changed rows (`Store::set_change_listener`). No job data.
- **Route:** `GET /api/v2/admin/events` (Server-Sent Events). Session-cookie
  read authorization (401 before anything is sent); a supplied Origin must match
  and a supplied `Sec-Fetch-Site` must be same-origin (403). Never renews the
  session. Events: `ready`, `changed {"version":N}` (bursts coalesced over
  250 ms), `signed-out`, and 15 s keepalives; `retry: 5000`.
- **Budget:** at most 2 streams. A connection that becomes a stream takes a
  stream permit and returns its admin, network and global request permits, so
  request budgets, the producer cap and the operator reservation are unchanged.
  The shared TLS executor grows from 6 to 8 job slots (6 request + 2 stream) so
  streams never take producer TLS capacity. A third stream gets 503 `service_busy`.
- **Closing:** sign-out, password activation and shutdown wake every stream
  immediately (session revocation signal); expiry closes it within 15 s. Every
  write and flush is bounded by 2 s, so a client that stops reading is dropped.
  The stream permit and instance ownership are held until the job ends.
- **Page:** a Live / Reconnecting / Live updates unavailable indicator next to
  Sign out. On `changed` it re-reads only what is visible (history page with the
  same cursor and order, the open job's detail and reservations, Storage) and
  updates in place, keeping the previous content until new data arrives. One
  refresh at a time with a single queued follow-up. On reconnect it re-reads once.
  When the stream closes for good, one unmarked session check decides between
  sign-in (401) and "Live updates unavailable" with a retry after 30 s.
- **Not pushed:** the cached source free-space reading on Storage (no database
  write) and Settings (changes only on restart).

## Tests

- Store: the change listener fires for writes and not for reads.
- Real service: 401 without a session, 403 for a foreign Origin, stream head and
  `ready`, a second stream accepted and a third refused with 503 while four
  ordinary admin requests and the operator still succeed, a real producer
  submission delivers `changed`, global sign-out delivers `signed-out` to both
  streams, and a new session can open a stream again.
- All 26 TLS listener tests pass locally (dev scripts). In one full local
  mover-store run under heavy parallel load, the existing
  `uuid_transaction_races_keep_winning_mapping_and_global_assertions` failed once;
  it passed 5/5 alone on both main and this branch (timing sensitivity, not this
  change). CI is authoritative.

Implementation review found three P2 issues, all fixed: the stream now subscribes
to revocations before checking the session and rechecks before committing (a
sign-out during setup can no longer leave a stream open); the page re-reads
visible state on every `ready`, including the first; and a live refresh awaits
the whole page → detail → reservations chain before the next one starts.

## Validation status

Pending PR CI for both full SLES modes and independent review.
