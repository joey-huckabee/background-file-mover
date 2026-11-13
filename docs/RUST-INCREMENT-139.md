# Increment 139: failure causes in the dashboard (state schema 14)

Authorized by the user on 2026-11-13: "We also need better Error capture in the
Activity card when something goes wrong. It would be good if the user knew what
the issue was so they could go fix the problem like permission denied etc."
First part of that request together with cancel (increment 140). No real
installation is migrated by this work.

## Problem

The worker processes already report a bounded, path-free diagnostic for every
failed step (for example `staging_directory_create errno=17; inspect storage`).
The service only wrote it to the log; the database and dashboard kept a generic
code (`delivery_requires_review`), so the operator could not tell what to fix.

## Change

- **Schema 14** adds `job_problems`: one row per job with the stage (`claim` or
  `delivery`), the worker diagnostic (1-240 printable ASCII bytes, enforced by a
  CHECK and in code), the file index being processed and the time. A newer
  problem replaces the older one. It is informational only: never an effect
  receipt, retry authorization or custody fact. History clear removes it;
  backup verification compares it.
- **Capture:** the delivery session keeps the last validated child diagnostic
  and the current file; on any delivery failure except service shutdown the
  service records it before scheduling the retry or review. Errors without a
  child diagnostic record a fixed code (`destination_binding_refused`,
  `blocked_or_uncertain`, ...), never arbitrary error text. Per-file claim
  failures record the same way when they are filesystem failures (a worker
  diagnostic or I/O error). Refusals returned to the sender (missing file, size
  mismatch, scope or custody refusals) leave job state unchanged, so a refused
  resubmission never alters the job.
- **Job detail** gains `last_problem` (`stage`, `operation`, `errno`, `file_id`,
  `diagnostic`, `recorded_at`), omitted when there is none, so existing shapes
  are unchanged.
- **Dashboard:** the Activity panel shows the problem in plain language: what
  went wrong ("Permission denied", "No space left", "Something is already
  there", "Read-only storage", "Stale network file handle", ...), during which
  step and on which file, which side (source or destination folder, named from
  the job) and what to do. The raw diagnostic is shown small for support. After
  the job is delivered it is shown as "Earlier problem (resolved)".
- **Migration:** `--migrate-state` converts 13 -> 14 with the same guarded
  additive step used for 12 -> 13 (now one shared implementation), and chains
  11 -> 12 -> 13 -> 14. Normal startup reports MigrationRequired for 11-13.

## Review fixes

- The published contract now defines `last_problem` (`JobProblem` in
  `docs/api/contract.candidate.schema.json`: bounded, printable, optional and
  never null), with fixtures for presence, a job-level problem, null (invalid)
  and unsafe text (invalid). Omission stays covered by the existing status
  fixtures. `check_contract_candidate.py` passes again: its route inventory now
  includes the settings and live-events routes added in increments 133/136, and
  it accepts the documented `text/event-stream` body.
- Collision advice (errno 17/39) no longer says "move or rename it": a collision
  does not prove the item is foreign. The dashboard tells the operator to find
  out what it is first, leave the mover's own data in place, and move only an
  item known not to be the mover's.

## Tests

- Store: latest problem recorded and replaced; invalid text refused in code and
  by the table CHECK; unknown jobs ignored; history clear removes it; 13 -> 14
  upgrade with all checkpoints, a pre-commit fault leaves 13 intact; snapshot
  verification refuses altered problem rows; all compatibility, migration and
  fixture tests updated for schema 14.
- Admin UI (node): plain-language descriptions for permission, space, existing
  item, source vs destination side, special codes and unknown errors.
- Real service: the destination-collision test now also checks that the job's
  `last_problem` is `staging_directory_create` errno 17 at delivery, and that it
  remains after the retried delivery succeeds.
- Local native runs (gate SQLite flags, private WSL namespace): workspace clippy
  clean; all mover-store tests; mover-fs backup tests; API migration,
  compatibility and offline-state tests; all 27 real-service TLS/admin tests.
  The SLES gates run in PR CI.
