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

## Tests

- New store test: two files of one job compete for room for one; the first
  reservation blocks the second; a repeat check of the same file does not
  double count; release frees the room (repeat release is a no-op); a save is
  refused while another file holds the room; saving the reserved attempt turns
  it into the ledger entry.
- Local: workspace clippy; store suite 93 of 94 in one run (the known flaky
  UUID race test passes alone); full API suite 107 of 111 in one run (the
  four worker-spawn/restart tests that failed under load pass alone).
