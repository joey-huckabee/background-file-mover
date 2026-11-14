# Increment 143: retained-data deletion engine (state schema 16)

First half of "delete retained data", authorized by the user on 2026-11-13 ("go
ahead with delete retained data"). The user decided:
- **Cancelled jobs are allowed**, with a plain warning that the retained copy is
  the only copy of the recording.
- **Off by default:** the dashboard action ships behind a configuration setting,
  off by default (increment 144). The demo turns it on.

This increment adds the storage, the delete primitive and execution. Nothing
can start a pass yet except the store API used by tests; the confirmation,
route, setting and button follow in increment 144. No real installation is
migrated and no production deletion is enabled.

## Scope (contract group 22/50/51, DeleteTarget)

- **Deletable:** the mover's own retained source copy of each completed claim
  (`<source root>/.file-mover/<private area>/data`), for jobs that stopped
  safely: delivered, or cancelled with the stop confirmed.
- **Never deleted:** the producer's original path (even when reused), committed
  destination output and manifests, other jobs' areas, anything whose identity
  does not match.
- **Later increment:** unfinished destination kinds (staging, payload, manifest
  staging) are reserved in the schema but not implemented.

## Change

- **Schema 16:**
  - `deletion_passes`: one row per job with the latest pass number, state
    Active or Done, principal, the confirming proof's digest and the
    requested/finished times.
  - `deletion_targets`: per file and kind, the pass it belongs to, its state
    (Pending, Deleted or Failed) and a bounded diagnostic.
- **`mover_fs::discard_retained_source`** runs in the supervised claim worker
  child (new `Discard` assignment). It deletes only when:
  - the source root and private area match their recorded identities;
  - the file matches the claimed object identity, else it is refused and kept;
  - the still-open handle has zero links after the unlink, proving the removed
    name was that object.

  It then syncs the area and removes the emptied area directory; anything
  unexpected stays. Symlinks are never followed. An already absent copy counts
  as no copy remaining.
- **Store:**
  - `deletion_preview` lists remaining targets and a fingerprint of the exact
    selection: file index plus recorded object identity.
  - `start_deletion` checks, in order:
    1. an active pass, or the pass started by this exact confirmation, is
       observed or replayed and never restarted;
    2. eligibility (delivered or cancelled with the stop confirmed);
    3. the fingerprint, else Stale;
    4. no targets left means NoWork, so no pass is created.

    Only then does it start a new pass on the remaining targets.
  - `next_deletion_target` / `finish_deletion_target` drive execution; the pass
    is Done when nothing is pending.
  - Failed targets are only retried by a fresh confirmation, never
    automatically.
- **Execution:**
  - The delivery thread processes up to 16 targets per tick between jobs.
  - It publishes the job it is working on, so clear and other workers
    serialize as before.
  - A stop leaves the target pending.
  - Failures are logged and recorded with the worker's bounded diagnostic.
- **Effects elsewhere:**
  - Deleted copies no longer count as retained source bytes.
  - Clear waits while a pass is active and forgets deletion records.
  - Replay validation of a delivered job skips files whose copy was
    deliberately deleted, so the original 202 meaning is kept.
  - Job detail and list rows report the latest pass as the contract
    `DeletionStatus` (`completion_pending`, `deleted_count`, `failed_count`).
- **Migration:** `--migrate-state` adds 15 -> 16 (shared guarded additive step)
  and chains 11 -> ... -> 16; startup reports MigrationRequired for 11-15.

## Review fixes

- **Old confirmations:** the selection fingerprint now also binds the job's
  current pass version. A confirmation issued before a later pass is always
  Stale, even if the same objects remain (A, then fresh B, then replay A
  starts nothing).
- **Replay during or after deletion:** a delivered job's replay validation skips
  a file as soon as a confirmed deletion has targeted it, in any state. That
  covers the window between unlink and the recorded result, and a failure
  recorded after an uncertain unlink. A fresh confirmation then completes the
  deletion durably (already absent is acknowledged only after a directory sync).
- **Durable absence:** both already-absent paths sync the directory where the
  name is absent (the source namespace or the private area) before reporting
  success, so accounting is released only after durable absence.
- **Known limit, accepted by design:** the post-unlink link-count check detects a
  substituted object only after the fact. It cannot prevent a concurrent
  same-UID name swap inside the mover's private namespace. Safety relies on the
  existing trusted-private-namespace assumption, as for every other custody
  effect.

## Tests

- mover-fs (`discard_removes_only_the_exact_retained_copy`):
  - the exact copy is removed and its area directory removed;
  - the producer's reused original and the other file are untouched;
  - a repeat finds nothing;
  - a replaced object is refused and kept;
  - a symlinked area is never followed.
- Store:
  - only stopped jobs preview;
  - stale selection refused;
  - an active pass is observed, not restarted, and blocks clear;
  - execution and results;
  - deleted copies drop out of retention;
  - the same confirmation replays;
  - a fresh one with nothing left is no-work;
  - a pending cancellation is not eligible;
  - a failed target is retried only by a fresh confirmation, covering just the
    remaining copy;
  - 15 -> 16 upgrade with fault injection;
  - snapshot verification covers both tables;
  - all compatibility and fixture tests updated for schema 16.
- Real service (`confirmed_deletion_removes_only_retained_copies_and_keeps_replay`):
  - a delivered job's retained copy is deleted by the running service;
  - its delivered output and `COMMITTED.json` stay;
  - the producer's reused original is untouched;
  - source reserved bytes drop to 0;
  - an exact replay still returns 202;
  - a cancelled job's swapped copy is refused, kept and reported as one failure.
- Local native runs (gate SQLite flags, private WSL namespace): fmt and workspace
  clippy clean; all mover-store tests; mover-fs claim and backup tests; all 29
  real-service TLS/admin tests; full API suite with only environment failures
  also seen on main or passing alone. The SLES gates run in PR CI.
