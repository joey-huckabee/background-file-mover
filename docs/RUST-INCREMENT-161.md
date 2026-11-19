# Increment 161: cancelled jobs no longer read as delivered

User request 2026-11-18: fix two display issues seen on a cancelled demo job.

## Problems

1. A cancelled job whose files had already been moved into place showed
   "Delivered" for each file, "3 of 3 delivered" in the job list and detail,
   and "Delivered 3" in the destination attempt counts. Those files were never
   committed, so consumers never saw them.
2. After cancelling from the dashboard, the cancel action's own reply
   ("Cancelling: the mover is stopping work on this job.") stayed under the
   status line, even after the job had settled as Cancelled.

## Change

- **Delivered** now means visible to consumers, i.e. the job committed.
  - The list's `files_delivered` counts published files only for committed
    jobs; it is 0 otherwise. The contract field now has a description saying
    so.
  - Job detail file status: a published file of an uncommitted job reads
    **Placed, delivery not confirmed**, with a hover note that it may since
    have been deleted. The record keeps the phase after a deletion, and a
    manifest can be published before its receipt is saved, so "placed" is
    recorded history, not proof the file is still there. The heading adds
    "· N placed, delivery not confirmed".
  - The attempt counts (job panel and Storage page) label the published phase
    **In place**, because they count attempts at their final names whether or
    not the job committed.
- The cancel action's reply is classified. A refusal or no-op (for example
  "Nothing to cancel") stays visible. An acknowledgement (accepted, or already
  in progress) yields to the job's own status line once the service reports
  Pending or Cancelled. If the delivery committed first, the service drops the
  cancellation and the job is Delivered; the dashboard then says "The job was
  delivered before the cancellation took effect." instead of a stale
  "Cancelling…".

## Tests

- Dashboard node tests: `fileStatus` wording for committed and uncommitted
  jobs; `cancelReplyText` for an acknowledgement superseded by Pending or
  Cancelled, the commit-first race, a no-op refusal, and a pending
  confirmation.
- Admin TLS tests (13/13): the existing list assertion, `files_delivered` = 2
  for a delivered job, is unchanged. fmt and clippy.
- Demo: cancelled job #10 (three files moved into place, never committed)
  shows "0 of 3" in the list, and no stale "Cancelling…" line (screenshot
  taken with the first wording, since revised).
