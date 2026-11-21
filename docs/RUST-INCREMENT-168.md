# Increment 168: restart runbook refresh (DOC-04)

2026-11-21, continuing release gate P10-11 while the user is unavailable.
DOC-04 already exists as the [restart runbook](RUST-RESTART-RUNBOOK.md)
(2026-11-08), but parts of it no longer matched the current build. This
increment brings it up to date. Documentation only; no behavior change.

## Change

- **Runbook:**
  - **Header:** source removal (move mode) and data deletion now exist, off by
    default. It no longer says they are disabled.
  - **New rows:**
    - the dashboard after a restart (every session signed out);
    - cancelled jobs (stay cancelled);
    - jobs waiting for missing files (deadline kept; automatic retries resume;
      a saved block stays until `reset-missing`);
    - move-mode cleanup in progress (resumes from records; paused while move
      mode is off);
    - confirmed data deletion in progress (continues from saved targets).
  - **Upgrade row:** the current schema is 18. Startup refuses 11-17 with
    MigrationRequired, and the offline migration chains them to 18.
  - **"Approved future behavior that is not implemented":** split into
    "Formerly pending behavior, now implemented" (SC-157, SC-162/165, SC-140)
    and "Not supplied".
- **Operator guide, "State compatibility before startup":** the same schema
  facts. It no longer says the UUID producer runtime is disabled. An
  unfinished legacy handoff refuses with UnsupportedIdentity.

## How it was checked

- **Schema:** `SCHEMA_VERSION = 18`. Startup refuses
  `(11..=17).contains(&version)` with MigrationRequired
  (`mover-store/src/lib.rs`). The offline migration is titled "schema 11-17 to
  schema 18".
- **UnsupportedIdentity:** observed while seeding an admin test this session
  ("legacy handoff is incomplete").
- **New rows:** each cites its increment's existing tests:
  - sessions: 129/130;
  - cancellation survives restart: 140, store test;
  - missing-file timer from saved state: 163;
  - an applied-but-unrecorded removal is reconciled: 162, job 5 of
    `move_mode_removes_held_copies_only_after_verified_delivery`;
  - a deletion pass continues offline-started: 143/160, API tests.

## Not covered

- No new restart, systemd, NFS or power-loss tests.
- DOC-05 and L1/L2/L3 traceability remain open.
