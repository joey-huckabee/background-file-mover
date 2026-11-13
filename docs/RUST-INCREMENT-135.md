# Increment 135: several concurrent admin browser connections

The user asked on 2026-11-12 to allow multiple independent browser connections
("go ahead with 1"); see the [UI review](dashboard/UI-REVIEW-2026-11-12.md) and
[roadmap](ROADMAP.md). Prerequisite for event-pushed live updates.

## Change

- Admin listener admits **4** concurrent connections (was 1).
- New explicit **operator reservation**: producer and admin TCP connections
  together may hold at most 7 of the 8 global connection slots, so the private
  operator socket always has one, whatever the network load. Previously this held
  only implicitly (6 producer + 1 admin).
- Producer limits are unchanged (6). Producer and admin TLS still share the fixed
  6-slot TLS executor, so a full producer load can still refuse admin connections;
  no admin throughput is promised then (design section 2).
- Each connection holds its audience permit, the network permit and the global
  permit until its TLS job actually ends, as before.
- After a connection flood stops, connections already queued may each hold an
  admin slot until the existing 5-second handshake deadline; admin recovers then.

## Tests

- Real service: three held admin sessions plus a fourth served request; with four
  held, a fifth connection is closed without a reply while the operator socket
  answers; released sessions free their slots.
- The flood test now asserts recovery within the handshake deadline instead of an
  immediate request (one admin slot made that immediate request almost always pass).
- All 24 TLS listener tests pass locally with the new
  [dev scripts](AGENT-WORKFLOW.md#practical-environment-notes) (native build with
  the gate's SQLite flags inside a private mount namespace). Not gate evidence.

## Validation status

Pending PR CI for both full SLES modes and independent review.
