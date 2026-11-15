# Increment 150: atomic destination capacity reservation (parallel delivery, step 3)

Step 3 of the parallel delivery plan (increment 148). Concurrency stays at one;
no behavior change for a single delivery.

## Problem

The retained-bytes ledger itself could never exceed its limit: saving a new
transfer attempt re-checks the limit inside the same transaction that records
it. The gap was the earlier pre-check (`transfer_capacity`), which runs before
the worker child creates the staging file. Two concurrent deliveries could both
pass the pre-check, both create staging files, and then the second save would
be refused: an unrecorded staging file and a delivery failure instead of a
capacity wait.

## Change

- `Store::transfer_capacity(job, file)` now checks **and reserves** in one store
  step: the file's size is held in an in-memory map of pending destination
  reservations, which every later destination check counts.
- `Store::save_transfer` counts other files' reservations, not its own, and on
  success removes its reservation (the ledger entry replaces it).
- `Store::release_transfer_capacity(job, file)` drops an unsaved reservation;
  the delivery worker holds a `Reserved` guard from the check until the save,
  so failure, cancellation and stop paths release it.
- Reservations are in memory only: they cover work in flight in this process
  and never change durable state or the schema.

## Review fixes

- **Reservation outlives the worker child.** `transfer_capacity` now returns a
  `CapacityHold`; dropping it releases an unsaved reservation. The delivery
  worker keeps every hold in a list declared before its session, so holds drop
  only after the session's child has been killed and reaped (Rust drops locals
  in reverse order), not when the failing step returns.
- **No leaks from in-process callers.** `prepare_transfer_file` and
  `restart_transfer` hold the reservation to the end of the call, so every
  error path releases it.
- **Token-checked release.** Each reservation carries a token; an older hold
  never releases a newer reservation of the same file, and a hold dropped after
  its attempt was saved changes nothing.

## Tests

- Store test: two files of one job compete for room for one; the first
  reservation blocks the second; a repeat check of the same file replaces its
  reservation and the older hold cannot release the newer one; dropping a hold
  frees the room; a save is refused while another file holds the room; saving
  the reserved attempt turns it into the ledger entry.
- mover-fs test: preparing file 1 before file 0 fails after reserving, and the
  reservation is released, so file 0 still fits.
- Local: workspace clippy; store suite 93 of 94 in one run (the known flaky
  UUID race test passes alone); full API suite 107 of 111 in one run (the
  four worker-spawn/restart tests that failed under load pass alone).
