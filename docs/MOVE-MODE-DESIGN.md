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

The delivery thread, between jobs, takes up to 16 cleanup files per tick, like
confirmed and automatic deletions. One job is cleaned per session:
1. **Discover** a job with eligible files, or with a pending retry whose time
   has come.
2. **Mark the job busy**, then **recheck** eligibility in the store. History
   clear may have won, or a pass started; if the recheck fails, nothing is
   touched.
3. **Take custody for the whole session.** The cleanup uses the job's
   destination custody lane, exactly like a delivery: the shared destination
   lock held by the coordinator, or the serialized lane where the child
   acquires it. It opens **one supervised delivery-worker session**, whose
   child holds both source custody (its inherited source lock and source
   authorization) and destination custody. That custody is held, unbroken,
   through the verification, every source unlink and sync, and the child's
   exit. A verification reply followed by releasing a lock is never enough.
4. **Verify the intact delivered set** in that child, before any source effect:
   - `COMMITTED.json` is opened `O_NOFOLLOW` in the identity-checked job folder.
     Its device, inode, uid, size and mtime must equal the recorded manifest
     object, and its bytes must equal the persisted manifest bytes, whose
     SHA-256 matches the stored digest.
   - **Every** file listed in the manifest is opened at its final name through
     the authenticated parent walk. Its full recorded published identity must
     match: regular file, uid, no group/other write, a single link, and the
     size and mtime recorded at publication. This is the same check the
     manifest step applies before commitment.
   - No hash pass on the uninterrupted path: permissions and retention keep
     verified objects unchanged, and size, mtime and links detect truncation
     or rewriting through the same inode. Any mismatch or missing final fails
     the whole job's cleanup this round; nothing on the source is touched.

   The checks are sent as bounded messages: one for the manifest (which
   carries at most 128 KiB of manifest bytes) and one per file, in order. The
   child accepts a source removal only after the complete set was verified in
   the same session.
5. **For each eligible file,** in order:
   - **record intent** durably before the removal message is sent: the
     `source_cleanups` row gets state `Intent` and `authorized = 1`. The
     `authorized` flag is monotonic; once set it is never cleared. From then
     on, replay validation treats the held copy as released (as for confirmed
     deletion), so a replay keeps its 202 whether or not the unlink has
     happened;
   - the child **removes the held copy** with the existing
     `discard_retained_source`. It checks root, area and object identity,
     unlinks, requires `nlink == 0`, syncs the area and removes the emptied
     area. An already-absent copy counts only after the containing folder is
     synced.
6. **After the child has exited and been reaped,** and still holding the busy
   marker (and in shared mode, the lane), **record the results** in one
   transaction:
   - **Removed:** the file phase becomes `SourceRemoved`, the row `Removed`,
     and the file's source reservation is released.
   - **Failure:** the rows become `Failed` with a bounded diagnostic,
     `attempts + 1`, and `next_attempt_at` set by backoff (30 s, doubling,
     capped at 1 h). `authorized` keeps its value, so two cases stay distinct:
     - **before authorization** (set verification failed; no intent was
       recorded for the file): `authorized = 0`. No source effect could have
       happened, so replay validation still requires the held copy, exactly as
       before cleanup;
     - **after authorization** (the removal was sent, then failed or was
       uncertain): `authorized = 1`. The copy may already be gone, so replay
       treats it as released and keeps its 202.

   A stop or crash before persistence leaves `Intent`, which is rerun on the
   next round (verification, then an idempotent removal, Removed or
   AlreadyAbsent).

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
- **Setting off with an `Intent` row:** nothing runs and replay still treats
  the copy as released, so it returns 202 whether or not the unlink happened.
  The row is completed when move mode is turned back on.

## State (schema 18)

A new table `source_cleanups`:
- key `(job_id, file_index)`;
- `state` (`Intent`, `Removed`, `Failed`);
- `authorized` (0 or 1, monotonic: once set, never cleared). A CHECK requires
  `authorized = 1` for `Intent` and `Removed`;
- `attempts`, `next_attempt_at`, `diagnostic`, `updated_at`.

Replay validation's "released" test (`retained_copy_released`) becomes: a
confirmed deletion has targeted the file, or a `source_cleanups` row has
`authorized = 1`.

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
- **Delete source files…** keeps today's rules for every job, move jobs
  included. That covers cancelled move jobs, which never commit and so are
  never cleaned up automatically, and move jobs while move mode is off. While
  a confirmed pass is active, automatic cleanup skips the job; the busy marker
  serializes the two otherwise. Both removals are identity-checked and
  idempotent.
- **Settings page:** shows "Move mode: on/off".
- **Help:** a short paragraph on copy vs move.

## Interactions

- **History clear:** refused while a cleanup of the job is running (busy
  marker). Otherwise allowed as today; the dialog already says held copies stay
  untracked.
- **Confirmed deletion passes:** cleanup skips a job with an active pass; a
  copy removed by a pass is later recorded `Removed` after the sync.
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
- **mover-fs (set verification):**
  - refuses a `COMMITTED.json` that was replaced, or rewritten in place with
    the same inode and different bytes;
  - refuses a published final truncated or rewritten through the same inode
    (size or mtime);
  - refuses a final that gained an extra link, and **another** file's final
    that is missing;
  - passes an intact set.
- **file-mover worker:** a source removal is refused unless the full set was
  verified in the same session (out of order, partial, or a new session).
  Custody locks are revalidated after the unlink.
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
  - **Interruption after unlink, before persistence:** the copy is gone and
    the row is `Intent`.
    - With move mode on, restart records `Removed` after the sync.
    - With move mode off, restart runs nothing, the job shows paused, and an
      exact replay still returns 202.
  - **Cancelled move job:** never cleaned up automatically, and **Delete
    source files…** still removes its held copies.
  - **Failure before authorization:** set verification fails because a final
    was replaced. The rows are `Failed` with `authorized = 0`, and the held
    copies stay. A replay still validates custody, so it is refused (409)
    once the held copy has also been swapped, as today. The next round retries
    after backoff.
  - **Failure after authorization:** the removal is sent, then the result
    is recorded as failed (or the copy disappears). The row is `Failed` with
    `authorized = 1`; an exact replay returns 202 although the copy is gone,
    and the next round records `Removed` after the sync.
- **Admin HTTPS:** detail `source_cleanup`, the `CleanupPending` condition,
  and **Delete source files…** still offered for a move job (cancelled, or with
  move mode off).
- **Dashboard node tests:** progress labels, activity wording, and Needs
  attention.
