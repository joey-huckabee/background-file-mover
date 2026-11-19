# Move mode: source cleanup after verified delivery (design proposal)

Status: proposal for review before implementation. Roadmap items "Move mode"
(user request 2026-11-18) and P08 (independently recoverable postcommit source
cleanup). Implements the cleanup policy already agreed in
[REST-API-DRAFT](REST-API-DRAFT.md) ("Completion and errors") and
[TRANSFER-PROTOCOL](TRANSFER-PROTOCOL.md) step 8.

**Authorization boundary.** This adds the capability, **off by default**. No
real installation is switched to move mode by this work. Enabling it on a
production host is a separate user authorization (AGENTS.md: no source deletion
without it). Tests and the demo use disposable data.

## User decisions

- 2026-11-18: in a **move**, source files are deleted after delivery; in a
  **copy** they are kept.
- 2026-11-18: move or copy is a **service setting**
  (`delete_source_after_commit`), not chosen by the sender, as in the agreed
  contract. No producer API change.

## What "source files" means here

At acceptance the mover takes over each file: the sender's original name is
moved into the mover's private area on the source disk
(`<source root>/.file-mover/<area>/data`). After 202 the sender's path is
released and may be reused. "Deleting the source" therefore means removing the
mover's **held copy** in that private area, exactly what **Delete source
files…** does by hand today (increments 143/144). The sender's original path is
never opened or touched.

## Configuration and recorded policy

- New top-level setting `delete_source_after_commit` (boolean, default
  `false`). The Settings page shows it, and Help explains it.
- Each job records the setting at acceptance (`DeliveryPolicy`, today always
  false). A job accepted as a copy never becomes a move, and a move job keeps
  its recorded policy.
- **Both must allow it:** a file is cleaned up only when its job's recorded
  policy is move **and** the currently loaded setting is true. Restarting with
  `false` stops all new cleanup (including pending retries; see Recovery).
  Re-enabling resumes move jobs only. It never restores deleted copies.

## Eligibility (per file)

All of these must hold:
- the job committed: manifest phase 4 and the job's committed fact;
- the file's phase is Published (not yet SourceRemoved), and its claim is
  complete with a recorded retained-copy identity;
- the job has no active confirmed deletion pass;
- no other worker holds the job (the delivery thread's busy marker).

## Execution

The delivery thread, between jobs, takes up to 16 cleanup steps per tick, like
confirmed and automatic deletions:
1. **Discover** the next eligible file, or a pending retry whose time has
   come.
2. **Mark the job busy**, then **recheck** eligibility in the store. History
   clear may have won, or a pass started; if the recheck fails, nothing is
   touched. The marker is held through worker reaping and result persistence.
3. **Record intent** durably: a `source_cleanups` row with state `Intent`,
   before any effect. From then on, replay validation treats the held copy as
   released (as for confirmed deletion), so a replay mid-cleanup keeps its 202.
4. **Revalidate the delivered side** (protocol step 8) in a supervised
   delivery-worker session under destination custody. `COMMITTED.json` must
   exist and be the recorded manifest object (device, inode, uid), and this
   file's published final must be the recorded object (`published_identity`,
   increment 160). On failure, nothing on the source is touched and the result
   is a failure (retried).
5. **Remove the held copy** in the supervised claim worker under source custody,
   with the existing `discard_retained_source`. It checks root, area and
   object identity, unlinks, requires `nlink == 0`, syncs the area, and removes
   the emptied area. An already-absent copy counts only after the containing
   folder is synced.
6. **Record the result** in one transaction:
   - **Removed:** the file phase becomes `SourceRemoved`, the row `Removed`,
     and the job's source reservation for that file is released.
   - **Failure:** the row becomes `Failed` with a bounded diagnostic,
     `attempts + 1`, and `next_attempt_at` set by backoff (30 s, doubling,
     capped at 1 h).

   A stop or crash before persistence leaves `Intent`, which is rerun on the
   next tick; removal is idempotent.

Cleanup failures never restart delivery or touch the destination. The recording
stays committed and visible to consumers throughout.

## Recovery and retries

- **Retries:** failures are retried indefinitely with capped backoff, as agreed
  ("cleanup failure is retried independently of delivery"). Each attempt
  revalidates from scratch.
- **Interrupted runs:** an `Intent` row after a restart is rerun at once
  (idempotent: Removed or AlreadyAbsent).
- **Setting turned off:** `Intent` and `Failed` rows stay as they are and
  nothing runs. The job shows "Source cleanup paused (move mode is off)". The
  held copies stay reserved.
- **Earlier manual deletion:** if a confirmed deletion pass removed the copy,
  cleanup finds it absent and records `Removed` after the sync.

## State (schema 18)

A new table `source_cleanups`:
- key `(job_id, file_index)`;
- `state` (`Intent`, `Removed`, `Failed`);
- `attempts`, `next_attempt_at`, `diagnostic`, `updated_at`.

It is added by the guarded additive migration 17 -> 18 (chain 11 -> 18).
Snapshot verification compares it, and history clear forgets its rows.

## Status and API

- **Job detail:** `source_cleanup`, which is `null` for copy jobs. For move
  jobs it is `{"enabled": <setting now>, "removed": n, "pending": n,
  "failed": n, "next_attempt_at": t|null, "last_error": text|null}`.
- **Conditions:**
  - `Committed` stays for a delivered copy job and for a move job with every
    source removed.
  - New `CleanupPending` for a committed move job with copies still held. It
    is an extension of the `JobCondition` enum; contract artifacts are
    updated.
- **File phase:** `SourceRemoved` (already in the contract).
- **Retention:** source reserved bytes exclude `SourceRemoved` copies, and the
  Storage page shows released space.
- **List:** `transfer_mode` reads `Move` from the recorded policy (the
  increment 134 field).

## Dashboard

- **Progress:** the final step reads **Copied** for copy jobs. For move jobs
  it reads **Moved** once every held copy is removed; until then it reads
  **Copied · removing source…**, or **Copied · source cleanup retrying** after
  a failure.
- **Activity:** "Source files: 2 of 3 removed; retrying in 60 s (last error:
  …)", or "paused: move mode is off".
- **Needs attention:** includes move jobs whose cleanup has failed at least
  once.
- **Delete source files…:** stays for copy jobs. It is hidden for move jobs,
  where cleanup removes those copies; a failing cleanup is fixed by fixing its
  cause, not by a second deletion path.
- **Settings page:** shows "Move mode: on/off".
- **Help:** a short paragraph on copy vs move.

## Interactions

- **History clear:** refused while a cleanup of the job is running (busy
  marker). Otherwise allowed as today; the dialog already says held copies stay
  untracked.
- **Confirmed deletion passes:** cleanup skips a job with an active pass, and
  manual source deletion is not offered for move jobs.
- **Automatic destination cleanup** (increment 160) is independent: it runs on
  the destination side only.
- **NFS sources:** the same custody rules apply. Production NFS remains
  disabled and unqualified for this effect.

## Proof

- **mover-store:**
  - eligibility (copy job, setting off, uncommitted, active pass, busy recheck
    after clear);
  - Intent before effect;
  - Removed transition with accounting released;
  - Failed with backoff, and retry timing;
  - setting off pauses, and re-enabling resumes;
  - migration 17 -> 18 with fault rollback and snapshot verification.
- **mover-fs:** the existing discard tests, plus revalidation that refuses
  when `COMMITTED.json` or a published final was replaced.
- **Real service (`api.rs`):**
  - **Move job:** delivered, then every held copy is removed automatically.
    Files read `SourceRemoved`, the job `Committed`, and source reserved bytes
    reach 0.
  - **Untouched on a move job:** the destination files and `COMMITTED.json`
    keep their bytes and inodes, the sender's reused original path is never
    touched, and exact replay returns 202.
  - **Copy job:** keeps its held copies.
  - **Setting changes:** a job accepted as a copy and later restarted with
    move on keeps its copies. A move job restarted with move off pauses with
    `CleanupPending`, and resumes when turned back on.
  - **Failure:** a held copy swapped for another object is refused, kept,
    retried with backoff, and shown in Needs attention.
  - **Clear race:** cleanup holding the job refuses a clear; clear first
    leaves nothing touched.
- **Admin HTTPS:** detail `source_cleanup`, the `CleanupPending` condition,
  and Delete source files hidden for move jobs.
- **Dashboard node tests:** progress labels, activity wording, and Needs
  attention.
