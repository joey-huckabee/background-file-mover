# Increment 167: consumer guide (DOC-02)

2026-11-21, continuing release gate P10-11 while the user is unavailable.
Documentation only; no behavior change.

## Change

- New [consumer guide](CONSUMER-GUIDE.md):
  - the destination layout (UUID folder, payload paths, `.staging/`, legacy
    numeric folders and v1 manifests);
  - `COMMITTED.json` as the only completion signal;
  - what the mover never changes after commit;
  - a step-by-step manifest check;
  - rules for taking recordings away, including move mode;
  - the no-clobber behavior for existing UUID folders.
- Links from the [user guide index](USER-GUIDE.md), the DOC-02 row in
  [scenarios](RUST-SCENARIOS.md), the producer quickstart and the roadmap.

## How it was checked

- **Layout and permissions:** a committed demo recording (files `0400`,
  folders `0700`, a `.staging/` that stays) and its exact `COMMITTED.json`.
- **Folder name:** `Submission::destination_component` (UUID, or the job
  number for legacy jobs). Producer jobs are not grouped by generator
  (`group_by_generator: false`).
- **Completion:**
  - the manifest is prepared only when every file's transfer is `Published`
    (`mover-fs/src/manifest.rs`);
  - `COMMITTED.json` is linked from a fully written and verified
    `.staging/COMMITTED.part`.
- **Unchanged after commit:** destination deletion refuses when
  `COMMITTED.json` exists. Automatic cleanup removes only superseded attempts,
  never final names, the manifest or folders (increment 160).
- **Move mode:** a failed delivered-set check keeps the source copy and
  retries, with the job under Needs attention (operator guide, increment 162).

## Not covered

- How consumer accounts get read access is a deployment decision (DOC-05).
- DOC-04, DOC-05 and L1/L2/L3 traceability remain open.
