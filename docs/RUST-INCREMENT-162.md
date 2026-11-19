# Increment 162: move mode (source cleanup after verified delivery, schema 18)

User request 2026-11-18: "Source files will be deleted during a move and not
during a copy". Decision the same day: move or copy is a **service setting**
(`delete_source_after_commit`, default off), not chosen by the sender.
Implements the reviewed [design](MOVE-MODE-DESIGN.md) and roadmap item P08.

**Off by default.** No installation is switched to move mode. Enabling it on a
production host is a separate authorization (AGENTS.md).

## Change

- **Configuration:** top-level `delete_source_after_commit` (default `false`),
  recorded in each job's policy at acceptance (previously always false).
  Cleanup needs both the job's policy and the loaded setting. The Settings
  page shows Transfer mode Move or Copy.
- **Store (schema 18):** a new `source_cleanups` table: one row per file, with
  state `Intent`, `Removed` or `Failed`, a **monotonic** `authorized` flag,
  attempts, `next_attempt_at` and a diagnostic. It is added by the guarded
  additive migration 17 -> 18 (chain 11 -> 18). Snapshot verification
  compares it, and history clear forgets it.
  - **Rounds:** `next_source_cleanup` finds a committed move job without an
    active deletion pass that has eligible files: Published, claim complete,
    and no row, `Intent`, or `Failed` past its backoff. It returns the round
    together with every published attempt and the manifest.
    `source_cleanup_eligible` rechecks that round after the job is marked busy.
  - **Intent:** `authorize_source_cleanup` records `Intent` with
    `authorized = 1` before a removal is sent.
  - **Results:** `finish_source_cleanup` records them in one transaction.
    Removed is accepted only from authorized `Intent`. A failure gets backoff
    (30 s, doubling, capped at 1 h) and keeps `authorized` unchanged.
  - Loading a job rebuilds file phase `SourceRemoved` from Removed rows.
  - **Replay:** a held copy counts as released once a confirmed deletion
    targeted it, or once `authorized = 1`. A failure before authorization
    (set verification) therefore still requires custody on replay.
  - **Accounting and manual deletion:** source reserved bytes exclude removed
    copies, and the manual source-deletion preview no longer offers them.
- **mover-fs:**
  - `verify_committed_manifest`: `COMMITTED.json`, opened `O_NOFOLLOW` in the
    identity-checked job folder, must be the recorded object (device, inode,
    uid, size, mtime, single link). Its bytes must equal the persisted
    manifest, whose SHA-256 matches the stored digest, and it must parse
    strictly.
  - `verify_published_exact`: each listed file, reached through the
    authenticated parent walk, must be exactly its recorded published object
    (regular, owned, no group/other write, a single link, size, mtime). No hash
    pass.
- **Worker protocol:** `verify_manifest`, `verify_final` (one bounded message
  per file, in order) and `remove_source`, which the child accepts only after
  the complete set was verified in the same session. It then removes the held
  copy with the existing `discard_retained_source`, revalidating custody
  before and after.
- **Execution** (delivery thread, after deletions; only with move mode on):
  1. find a round;
  2. mark the job busy and recheck;
  3. take the job's destination custody lane;
  4. in **one** delivery-worker session (`clean_sources`), verify the set,
     then for each file record intent and remove;
  5. reap the child, then save the results while still holding the marker and
     the lane.

  If the set verification fails, nothing is sent and every file of the round
  is Failed with `authorized = 0`.
- **Status:**
  - A committed move job with held copies left is condition `CleanupPending`;
    once all are removed it is `Committed`.
  - Job detail: `source_cleanup_enabled` follows the job's policy, and
    `source_cleanup` gives the setting plus removed, pending, failed, next
    attempt and last error.
  - List rows: `source_cleanup_failed`.
- **Dashboard:**
  - The final step reads **Moved**, **Copied · removing source…** or
    **Copied · source cleanup retrying**, with a badge.
  - Activity shows "Source files: N of M removed" with paused or retrying
    detail, only for a delivered move job. A cancelled move job says its
    copies are not removed automatically; an undelivered one says removal
    happens after verified delivery.
  - **Needs attention** includes move jobs whose cleanup has failed.
  - **Delete source files…** keeps today's rules (cancelled move jobs, move
    mode off).
- **Contract:** the `CleanupPending` condition, `SourceCleanupStatus`, and the
  `source_cleanup_failed` list field. The checker passes.
- **Docs:** operator guide "Move mode", the HTTPS setup note, the migration
  guide (schema 18), architecture, roadmap (move mode and P08 done), and the
  design status.

## Tests

- **Store** (four new tests):
  - committed move jobs only (not copy, not uncommitted);
  - Removed refused without intent; intent releases the copy for replay;
    Removed sets `SourceRemoved` and releases accounting;
  - the manual preview no longer offers removed copies;
  - backoff values; failure before authorization keeps custody, and failure
    after it keeps the copy released (monotonic);
  - an active deletion pass blocks cleanup;
  - clear-first recheck fails; while the job is busy, clear is refused;
  - migration 17 -> 18 with fault rollback, MigrationRequired and snapshot
    verification.

  All downgrade and compatibility tests were updated for schema 18.
- **mover-fs:** on a real delivered three-file job, set verification detects:
  - a replaced manifest (same bytes, other inode), and a manifest rewritten in
    place;
  - a truncated delivered file, a file rewritten to the same size, and an
    extra link;
  - **another** file missing.

  An intact set passes, and verification changes nothing.
- **Worker session** (`source_removal_requires_the_full_set_verified_in_the_same_session`),
  on a two-file recording: the required set comes from the verified
  manifest's own list, never the caller's count.
  - Refused, held copy kept: removal alone; after the manifest only; after a
    file only; after the manifest and file 0 with a claimed count of 1 or 2;
    files out of order.
  - Succeeds after the manifest and both files are verified; the delivered
    files are untouched.
- **Real service** (`move_mode_removes_held_copies_only_after_verified_delivery`):
  - **Move job:** delivered, then its held copy is removed automatically. The
    file reads `SourceRemoved`, the job `Committed`, and source reserved bytes
    reach 0. The sender's reused path is untouched, the delivered file and
    `COMMITTED.json` remain, and replay returns 202.
  - **Copy job:** restarted with move mode on, it keeps its copy.
  - **Move mode off:** a delivered move job waits as `CleanupPending` with
    `enabled: false`. For a seeded recovery state (authorization recorded
    directly in the store and the held copy removed, as an interruption
    between unlink and result persistence would leave it), an exact replay
    still returns 202.
  - **Move mode back on:** the paused job completes, and the seeded one is
    recorded Removed after the sync.
  - **Changed delivery:** a job whose delivered file was rewritten in place
    fails verification, keeps its good source copy, shows the failure with a
    retry time, and still replays 202.
- **Admin HTTPS:** 13 tests, with the list row extended by
  `source_cleanup_failed`. Dashboard node tests cover the progress labels,
  badges, Needs attention and activity text.
- fmt and workspace clippy; contract checker.

## Not covered

- No test interrupts a live cleanup worker between unlink and persistence.
  The real-service test seeds the state such an interruption leaves
  (authorized intent, copy gone), and the store tests cover each persisted
  transition.

- Production enablement and source cleanup on NFS sources (unqualified).
- The retry itself is covered at store level (backoff, rediscovery after the
  time); the real-service test does not wait out the 30 s backoff.
