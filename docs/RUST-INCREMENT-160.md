# Increment 160: delete partial destination files; automatic leftover cleanup (schema 17)

User request 2026-11-17: "do deleting partly delivered destination files".
Decisions 2026-11-18: two separate dashboard buttons, and a delivered job's
leftover partial attempts are removed automatically after a successful
delivery ("move" mode, deleting source files after delivery, is a separate
roadmap item). Implements the reviewed
[design](dashboard/DESTINATION-DELETION-DESIGN.md). No real installation is
migrated and no production deletion is enabled.

## Scope

- **Delete source files…** (`delete-data`): retained source copies, unchanged
  from increments 143/144.
- **Delete partial destination files…** (`delete-destination-data`, new):
  cancelled jobs (stop confirmed) whose manifest never reached publication
  intent:
  - every recorded attempt: `.part` files (`UnfinishedDestinationStaging`) and
    files already moved into place (`UnfinishedDestinationPayload`);
  - the manifest staging (`UnfinishedManifestStaging`).

  A `COMMITTED.json` present in the job folder refuses everything.
- Both actions are behind `admin_ingress.allow_data_deletion` (default off),
  one job per request. Their proofs and fingerprints are scoped, so neither
  action's proof works for the other. They share the job's single pass.
- **Automatic cleanup** (not gated by the setting): a delivered job's
  superseded attempts, those below the published attempt (always phase 0).
  It never touches the published attempt, final names, `COMMITTED.json`, their
  folders or the job folder.

## Change

- **Schema 17:** new table `destination_deletion_targets`, keyed
  (`job_id`, `kind`, `file_index`, `attempt`). It is a separate table rather than
  a new key on `deletion_targets`, because the guarded migration step only adds
  empty tables. `--migrate-state` adds it 16 -> 17 and chains 11 -> ... -> 17.
  Snapshot verification compares it, and history clear forgets its rows.
- **Store (`deletions.rs`):**
  - `DeletionScope` (Source, Destination) for previews and passes. Each
    fingerprint is domain-separated by scope.
  - `DeleteTarget` gains `kind` and `attempt`; `file_index` and `size_bytes`
    become optional.
  - `next_destination_deletion` / `finish_destination_deletion` drive
    confirmed passes. A pass is Done once neither table has pending rows, and
    its counts span both tables.
  - Automatic cleanup: `next_automatic_cleanup` finds work,
    `automatic_cleanup_eligible` rechecks it after the job is marked busy, and
    `finish_automatic_cleanup` records a row with no pass. A failure is not
    retried. Automatic rows never appear in `DeletionStatus`.
- **Accounting:** destination reserved bytes and attempts-by-phase no longer
  count an attempt whose staging or payload target is Deleted.
- **mover-fs `discard_unfinished_destination`** never follows symlinks, and
  matches device, inode and uid before every unlink:
  - **Single names:** open, match, unlink, require `nlink == 0`, sync the
    folder.
  - **Payload:** both names (final, staging alias) must match before either is
    unlinked. Absent names are allowed, so a rerun completes from any partial
    state.
  - **Delivered jobs:** before unlinking, every published final name is opened
    and verified (`published_identity`), and the target must be none of them.
    The worker gets one bounded `verify_published` message per file in the
    same session, in order, before the `discard`, so job size never exceeds a
    frame limit (`destination_cleanup_messages_fit_their_frame_at_maximum_sizes`
    uses maximum-length paths).
  - **Payload folder syncs:** both names' folders are synced whichever name
    was still present, so a rerun makes an interrupted earlier unlink durable.
  - **Already absent:** acknowledged only after syncing the folder it is
    absent from.
  - **Folders:** emptied folders are removed bottom-up. On cancelled jobs the
    final name's parents are authenticated by walking the recorded path from
    the private job folder to the recorded parent, then the job folder goes.
    Delivered jobs only lose emptied `.staging` folders.
- **Execution:** the delivery thread takes confirmed destination targets, then
  automatic cleanups, after retained-source targets, up to 16 per tick, under
  the job's destination custody lane, the same as a delivery. Before an
  automatic cleanup starts, the job is marked busy and the attempt rechecked
  (history clear may have won). The marker is held until the worker child is
  reaped and the result is saved, so a clear meanwhile is refused as busy. A supervised delivery worker performs
  each one (new `discard` operation), with source and destination locks
  checked before and after. A stop leaves the target pending. Failures are
  recorded with the worker's bounded diagnostic and retried only by a fresh
  confirmation.
- **Contract:** schema confirm action, OpenAPI `confirm_action` enum and the
  new POST route, checker route inventory, and a destination preview fixture;
  the contract checker passes.
- **Routes:** `confirm_action=delete-destination-data` and
  `POST /api/v2/admin/jobs/delete-destination-data`. Each target in a preview
  now reports its `kind` and `attempt` (contract `DeleteTarget`).
- **Dashboard:**
  - A second button, **Delete partial destination files…**, on cancelled jobs.
  - Its confirmation lists each item with its attempt, the known total size,
    and "+ N partial file(s) of unknown size". It says consumers never saw
    them and that the source copies are untouched.
  - The source dialog never fails on a missing size.
  - The activity line reads "Files: N deleted".
- **Docs:** `ADMIN-HTTPS-SETUP` (deleting files), `ARCHITECTURE` (routes), the
  offline migration and operator guides (schema 17), the roadmap (including
  move mode) and the contract status.

## Tests

- **mover-fs**, with a real store and real transfers:
  - **Cancelled two-file job:** a published file and two attempts of the
    other. The partial-destination selection is exact, all three are removed,
    the job folder and its `sub/` folder go, the source action still offers
    the three retained copies, destination reserved bytes reach 0, and a rerun
    is AlreadyAbsent.
  - **Payload recovery:** final only, alias only, both, and neither all
    complete. A foreign alias or a foreign final is refused, and both names
    stay.
  - **Refusals:** a `COMMITTED.json` planted in the folder, a substituted
    final, and a symlinked job folder are all refused and nothing is removed.
  - **Delivered job, automatic cleanup:** only the superseded `.part` goes.
    The final and `COMMITTED.json` keep their bytes and inodes, the folders
    stay, and reserved bytes drop by exactly that attempt. There is no
    deletion status and no manual destination targets. A `.part` replaced by a
    link to the published file is refused, and so is a delivered job missing
    its manifest. Each refusal is recorded once and not retried.
  - **Manifest phases:** at phase 2 (written) the payload and manifest staging
    are removed. At phase 3 (publication intent) nothing at the destination is
    offered.
- **Store:**
  - **Scopes:** a delivered job's destination preview is empty, and each
    scope's fingerprint is stale for the other.
  - **Automatic cleanup:** the work record carries the published attempts.
    Finishing twice is refused, exactly that attempt's reservation is
    released, and no pass is recorded.
  - **Clear races:** if clear wins, the recheck refuses. While the job is
    busy, clear is refused until the result is saved. A failure is not
    retried.
  - **Migration 16 -> 17:** pre-commit fault rollback, and snapshot
    verification detecting a changed row.
  - Every downgrade and compatibility test was updated for schema 17.
- **Real service**
  (`partial_destination_files_are_deleted_on_confirmation_and_leftovers_after_delivery`):
  - **Setup:** two jobs handed off while the destination was unprovisioned.
    Offline, under destination custody and with the pin recorded, job 1 got a
    published file and an allocated attempt, and job 2 a lost-receipt attempt.
  - **Job 1:** cancelled, with its partial destination files confirmed. The
    running service removes both targets and the job folder, keeps the
    retained source copies, and destination reserved bytes reach 0.
  - **Job 2:** delivered by the service from a later attempt, which then
    removes every superseded attempt by itself. Only the published attempt
    stays reserved, there is no deletion status, and no manual targets remain.
  - Both handoffs replay 202.
- **Admin HTTPS** (`admin_delete_data_…`): the new action is off with the
  setting (no preview, 404). A delivered job's partial-destination preview is
  empty. Neither action's proof works on the other route.
- **Dashboard node tests:** the new action's route, button, item list with
  attempts, unknown sizes, wording and outcomes, and the source dialog with a
  null size.
- fmt and workspace clippy; mover-store, the mover-fs transfer tests, the
  real-service deletion tests, admin TLS and the node tests. Full-suite runs
  and the SLES gates are reported in the PR.

## Not covered

- The real-service test builds partial destination state offline with the
  real transfer functions, not by interrupting a live delivery. The
  qualification pause between a payload's two unlinks
  (`destination_discard_between_names`) exists, but no test drives it; the
  two-name states it would produce are covered directly.
- No screenshot of the new button and dialog in a running demo yet; the
  wording is covered by the node tests.
