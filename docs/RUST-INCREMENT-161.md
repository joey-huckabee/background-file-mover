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
    **In place, not delivered**. The heading adds "· N in place, not
    delivered".
  - The attempt counts (job panel and Storage page) label the published phase
    **In place**, because they count attempts at their final names whether or
    not the job committed.
- The cancel action's reply shows only while the job's cancellation is still
  not requested (for example "Nothing to cancel"). Once the service reports
  Pending or Cancelled, the status line says it and the stale reply is
  dropped.

## Tests

- Dashboard node test: `fileStatus` wording for committed and uncommitted
  jobs.
- Admin TLS tests (13/13): the existing list assertion, `files_delivered` = 2
  for a delivered job, is unchanged. fmt and clippy.
- Demo: cancelled job #10 (three files moved into place, never committed)
  shows "0 of 3" in the list, "0 of 3 delivered · 3 in place, not delivered",
  each file "In place, not delivered", and no stale "Cancelling…" line.
