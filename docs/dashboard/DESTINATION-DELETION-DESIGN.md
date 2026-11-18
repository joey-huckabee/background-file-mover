# Delete unfinished destination data: design

Status: approved (independent review, 2026-11-17); revised 2026-11-18 after the
user decisions below, for re-review. Implemented in
[increment 160](../RUST-INCREMENT-160.md).

**User decisions 2026-11-18:** two separate dashboard actions, **Delete source
files…** (retained source copies, unchanged) and **Delete partial destination
files…** (this design, cancelled jobs). A delivered job's leftover partial
attempts are removed **automatically** after a successful delivery, not by a
button. Deleting source files after delivery belongs to a future "move" mode
(separate work and authorization; roadmap). Completes the roadmap item
"unfinished-destination deletion kinds" of the confirmed data deletion workflow
(contract group 22/50/51, `DeleteTarget`). It extends the retained-source
deletion of [increment 143](../RUST-INCREMENT-143.md) and
[144](../RUST-INCREMENT-144.md). That increment shipped the schema slots, the
`deletion_targets.kind` values and the contract enum, but not the destination
kinds.

User request 2026-11-17: "do deleting partly delivered destination files".

## What a stopped, undelivered job leaves at the destination

`destination_root/<recording directory>/` (the job's area, created by the mover):

- `.staging/<attempt>.part` (file 0) and `.staging/<index>/<attempt>.part`
  (other files): one staging object per **recorded attempt**. A retry keeps the
  older partial attempt and allocates a new one; nothing retires it today.
- The final name (`relative_name`, possibly in subfolders the mover created):
  the verified staging object moved into place at publication (no-clobber
  rename; where rename is unsupported, link then unlink, so after a crash in
  that window the staging name can still point to the same object).
- `.staging/COMMITTED.part`: manifest staging (manifest phases 1-2).
- `COMMITTED.json`: once present, the set is visible to consumers and is never
  touched.

Each attempt is a `transfers` row (`job_id`, `file_index`, `attempt`) with the
recorded root, area, parent, staging-directory and stage identities
(device, inode, uid) and its phase (0 Intent, 1 Copied, 2 Verified,
3 PublishIntent, 4 Published). The manifest row records its staging object
identity and phase (0 intent, 1 allocated, 2 written, 3 authorized,
4 committed).

## Scope

- **Eligible job:** cancelled with the stop confirmed (`cancellations.state =
  Cancelled`). This already implies no worker is on the job and the delivery
  did not commit first. A job that failed but is not cancelled must be
  cancelled first (approved eligibility rule). Delivered jobs get no manual
  targets; their superseded attempts are cleaned up automatically (see
  "Delivered jobs" below).
- **Committed or possibly committed:** if the manifest row is at phase 3 or
  later, the job gets **no destination targets** (publication may have
  happened). The only exception is the automatic cleanup of a delivered job's
  (manifest phase 4) superseded phase-0 staging attempts. On the
  cancelled-job path the worker refuses every destination target of a job whose
  area contains `COMMITTED.json`, whatever the database says.
- **Target kinds** (contract `DeleteTarget`):

| Kind | One per | Object | `file_id` / `attempt` | `size_bytes` |
| --- | --- | --- | --- | --- |
| `UnfinishedDestinationStaging` | attempt in phase 0-2 | `.staging/[index/]<attempt>.part` | file / attempt | source size if phase >= 1 (complete copy), else `null` (partial, unknown) |
| `UnfinishedDestinationPayload` | attempt in phase 3-4 | the final name, plus the staging alias if still present (same object) | file / attempt | source size |
| `UnfinishedManifestStaging` | job, manifest phase 1-2 | `.staging/COMMITTED.part` | `null` / `null` | `null` |

- `relative_path` in the preview is the file's original relative name for
  file kinds and `COMMITTED.json` for the manifest kind. Private host paths and
  inode numbers never reach the wire.
- **Never deleted:** `COMMITTED.json`; anything in a job whose manifest
  reached phase 3, except the automatic cleanup of a delivered job's superseded
  phase-0 staging attempts; any object whose identity differs from the record; anything
  outside the job's area; symlink targets; other jobs' areas; the destination
  root and its `.file-mover` namespace.
- **Folders:** after a job's targets are all deleted, the worker removes the
  folders the mover created, if empty, bottom-up: `.staging/<index>`,
  `.staging`, the final name's parent folders, then the area. It never removes
  recursively (plain `rmdir`; non-empty means something else is there and it
  stays) and never goes above the area. Authority for each folder:
  - the area, `.staging` and `.staging/<index>`: their recorded identities
    (area, staging directory);
  - the final name's ancestors (for `a/b/file` the record holds only `b`, the
    deepest parent): the worker walks exactly the recorded `relative_name`
    components from the identity-checked area, each opened `O_NOFOLLOW` as a
    directory, owned by the service uid with no group/other write access, and
    requires the walk to end at the recorded parent identity. Only that
    authenticated chain is removed, bottom-up, and only while empty. The area
    is private (owner-only, checked as at creation), so under the existing
    trusted private-namespace assumption only the mover could have created
    entries in it. If the walk fails anywhere, every ancestor stays.
  - The area itself is removed only if empty and its identity matches.

## Two actions per job

The dashboard offers two separate confirmed actions, both per job and both
behind `admin_ingress.allow_data_deletion` (default off):
- **Delete source files…** (`confirm_action=delete-data`): retained source
  copies only (`RetainedSource`), as in increments 143/144. Delivered and
  cancelled jobs.
- **Delete partial destination files…**
  (`confirm_action=delete-destination-data`): the destination targets above.
  Cancelled jobs only.

Each preview lists only its own kinds, and its proof binds the fingerprint of
that selection with a scope tag (source or destination), kind, file, attempt,
recorded identity and pass version. A proof for one action can therefore never
start the other, and a selection that changed since the preview is
`stale_confirmation` with nothing deleted. Both actions share the job's single
pass: while either is active the other is not offered.

## Execution

- The same delivery-thread loop that handles retained-source deletion (up to
  16 targets per tick, between jobs, the job marked busy) takes destination
  targets too. Destination targets run in the **supervised delivery worker**
  under destination custody (the lock it holds, or the shared destination
  custody when concurrency is above 1), never in the coordinator.
- New mover-fs primitive `discard_unfinished_destination(transfer | manifest)`:
  1. open the root by path and require the recorded root identity; open the
     area by name (`O_NOFOLLOW`) and require its identity; if `COMMITTED.json`
     exists, refuse ("committed manifest present; nothing deleted");
  2. open the staging directory (and `<index>` subfolder) with identity checks;
  3. open the target name `O_NOFOLLOW` as a regular file and require the
     recorded device, inode and uid (not size or mtime: a partial attempt
     changed after its identity was recorded at allocation). For a
     single-name target (staging, manifest staging) unlink it; a payload is
     never unlinked here (step 4 validates both names first);
  4. a **payload** has up to two names for one object: the final name (in its
     identity-checked recorded parent) and the staging alias. The worker opens
     each name that exists and requires both to be the recorded object before
     unlinking anything. A name that exists but is another object is
     substituted: nothing is unlinked, the target is Failed and both names stay.
     It unlinks the final name, then the alias. Absent names are allowed, so a
     rerun after an interruption between the two unlinks, or after both but
     before the result was saved, completes from whatever remains: final only,
     alias only, both or neither;
  5. after the last name, `fstat` the still-open handle and require
     `nlink == 0`. As for source discard (increment 143) this is a
     post-operation check under the trusted private-namespace assumption: it
     reports an unexpected extra link as Failed, but it cannot prevent a
     same-uid name swap racing the unlink;
  6. `fsync` every directory a name was removed from; then remove empty
     folders as above and `fsync` their parents.
- An already absent object (both names, for a payload) counts as deleted only
  after every directory where a name is absent has been synced (as in
  increment 143).
- The result is persisted only after step 6. A crash or stop before that
  leaves the target Pending; the next tick reruns it idempotently. A target is
  counted once (one row per kind, file and attempt); accounting releases its
  bytes only when the row becomes Deleted, i.e. after durable removal.
- A stop leaves the target pending; failures are recorded with a bounded
  diagnostic and only retried by a fresh confirmation.

## State (schema 17)

Implemented as a new table rather than a new key on `deletion_targets`
(changed during implementation, increment 160): the guarded migration step
only adds empty tables, and rebuilding `deletion_targets` would have needed a
new kind of migration. `destination_deletion_targets` has the key
`(job_id, kind, file_index, attempt)`; `file_index` is `-1` and `attempt` `0`
for the manifest kind, and CHECK constraints tie these to their kinds. Rows
reference `jobs`; `pass` is the confirmed pass, or NULL for an automatic
cleanup (then only `UnfinishedDestinationStaging`, never Pending). A pass and
its counts span both tables; automatic rows never count. `--migrate-state` adds it 16 -> 17 through the shared guarded
additive step and chains 11 -> ... -> 17; startup reports MigrationRequired for
11-16.

## Accounting and status

- Destination reserved bytes (today: one source size per recorded attempt)
  stop counting an attempt whose staging or payload target is `Deleted`. The
  Storage view and capacity admission see the space returned.
- Job detail keeps the latest pass's `DeletionStatus` counts, now covering all
  kinds; list rows unchanged.
- Producer replay of a cancelled job stays 409 `recording_cancelled`.
- History clear still waits for an active pass and forgets deletion rows.

## Dashboard

- **Delete source files…** keeps its button, wording and warning (only copies
  of an undelivered recording).
- **Delete partial destination files…** appears on cancelled jobs when
  deletion is enabled. Its confirmation lists the items (file name and
  attempt), the known total size and "+ N partial files of unknown size", and
  says: "These are unfinished files the mover left at the destination for this
  cancelled job. Consumers never saw them. The mover's held copies on the source
  disk are not touched." Confirm is disabled when nothing is left.
- Activity shows the latest pass of either action with its counts.

## Delivered jobs: automatic cleanup of leftover partial attempts

When a file needed a retry, the older partial `.part` stays in the delivered
recording's private `.staging` folder (not in the manifest, not consumer data).
The user decided these are removed automatically as part of a successful
delivery:
- **What:** each **superseded** attempt of a job whose manifest is committed
  (phase 4): an attempt below the file's published attempt, always phase 0.
  Never the published attempt's object, the final names, `COMMITTED.json`,
  their folders or the area; only `.staging/<index>` and `.staging` are
  removed, and only if they end up empty.
- **When:** the delivery thread looks for such attempts between jobs, like
  confirmed deletions (a few per tick, the job marked busy, under the job's
  destination custody lane), so a job delivered by this version and leftovers
  of jobs delivered earlier are both cleaned. Not gated by
  `allow_data_deletion`: these are the mover's own incomplete temporary copies,
  and the recording's verified delivered files and its retained source copy
  remain.
- **Admission (no pass protects discovery):** the delivery thread first marks
  the job busy (the same marker history clear and other workers honor), then
  **rechecks** in the store that the job is still tracked and the exact attempt
  is still an eligible superseded attempt with no cleanup record, and only then
  starts the worker. If the recheck fails (for example history clear forgot
  the job in between), nothing is touched. The marker is held through the
  worker child's reaping and the result's persistence, so a clear that arrives
  meanwhile is refused as busy until the cleanup has actually finished.
- **Record:** each result is a `destination_deletion_targets` row with no pass
  (`pass` NULL): `Deleted`, or `Failed` with a bounded diagnostic. A failed
  cleanup is logged and **not retried automatically** (no loop on a damaged
  folder); it stays reserved in the accounting. Automatic rows never count in a
  pass's `DeletionStatus`.
- **Safety:** an explicit exception to the step 1 `COMMITTED.json` refusal:
  - only committed jobs (manifest phase 4) and only attempts below the
    published attempt are selected;
  - the worker opens only names under `.staging` (never the area's other
    entries), and before unlinking a superseded `.part` it opens **every**
    published final name of the job (identity-checked parents) and requires the
    target's device and inode to differ from each of them. If any final name
    cannot be opened or matches, the target is Failed and kept;
  - `COMMITTED.json` is never opened for writing, renamed or removed; its
    presence is required on this path (a delivered job without it is refused).

## Proof

- mover-fs: each kind removes exactly its object and the empty folders;
  substituted object refused and kept; symlinked area or staging never
  followed; `COMMITTED.json` present refuses everything on the cancelled-job
  path; a non-empty folder stays; a repeat finds nothing; already absent
  acknowledged after sync.
- Folders: nested `a/b/file` removes `b` and `a` when empty; an ancestor
  replaced by a symlink, another uid's or a group-writable folder, or a walk
  not ending at the recorded parent leaves every ancestor in place.
- Payload two-name recovery: start states final-only, alias-only, both and
  neither; interruption (qualification pause) between the two unlinks and
  after both but before persistence; each rerun completes, the row is counted
  once and accounting is released only after Deleted. A substituted final or
  alias (other inode) is never unlinked and the target is Failed.
- Delivered leftovers (mover-fs): a superseded attempt is removed; the
  published files, `COMMITTED.json` and their folders are byte- and
  inode-identical afterwards and the area stays; a target whose inode equals a
  published object (planted) is refused; a substituted staging alias (other
  inode at the `.part` name) is refused and kept; a delivered job without
  `COMMITTED.json` is refused.
- Delivered leftovers (store): only attempts below the published attempt are
  selected for automatic cleanup, never the published attempt; manifest phase
  3 gives none; a Failed automatic row is not offered again; manual previews of
  delivered jobs offer no destination targets.
- Clear races: clear first, then cleanup (recheck fails, no file touched);
  cleanup holding the busy marker, then clear (refused as busy until the
  cleanup result is saved).
- Two actions: each preview lists only its scope; a source proof cannot start a
  destination pass and vice versa (stale); while one pass is active neither
  action is offered.
- Store: eligibility (pending cancel and not cancelled give no destination
  targets; manifest phase 3+ gives none except a delivered job's superseded
  phase-0 staging attempts at phase 4); fingerprint covers kinds and attempts; stale, replay,
  no-work and failed-then-fresh-confirmation; accounting drops deleted
  attempts; migration 16 -> 17 with fault injection; snapshot verification.
- Real service: cancel a job mid-delivery (a published file, a partial
  attempt, a retried file with two attempts); preview lists source and
  destination targets; delete removes them and the empty area; the source
  original and other jobs are untouched; destination reserved bytes drop;
  a job with `COMMITTED.json` planted in its area deletes nothing at the
  destination and reports failures; replay stays 409.
- Real service, delivered job with a retried file: the service removes the
  older attempt's `.part` automatically after delivery, with no confirmation; published files and `COMMITTED.json` keep their bytes and inodes;
  the area stays; destination reserved bytes drop by exactly that attempt;
  an exact producer replay still returns 202.
- Dashboard: second button only on cancelled jobs; its confirmation lists
  destination items with unknown sizes counted separately; source dialog
  unchanged (node tests).
