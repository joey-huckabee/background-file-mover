# Increment 170: traceability plan and the first L2 family (DPR)

2026-11-21, continuing release gate P10 (RC-23) while the user is unavailable.
Documentation and a docs checker only; no product behavior change.

## Change

- **[Plan](TRACE-MATRIX.md#plan):**
  - map L2 to Rust evidence one family per increment;
  - collect deviations, "not applicable" proposals and rewording as decisions
    for the user;
  - leave the Python-era L3 replacement to the user;
  - roll up to L1 last.
- **[TRACE-L2.md](TRACE-L2.md):** dispositions and evidence for DPR (data
  preservation, L2-DPR-001 to 007, parent L1-SYS-003).
  - Tested: 001, 004.
  - Partly tested:
    - 002: syncs by inspection;
    - 003: staging and verification size checks by inspection;
    - 007: refusals and checkpoint recovery tested; failures of individual
      sync and publication calls are not injected.
  - Deviation (needs approval):
    - 005: the no-clobber link fallback where `RENAME_NOREPLACE` is
      unsupported;
    - 006: operator-confirmed deletion, an approved exception that needs
      requirement rewording.
- **`scripts/check_trace.py`**, run in the hygiene `admin-ui` CI job. It
  checks that:
  - every row's ID exists in L2-REQ.md;
  - no ID is mapped twice;
  - the disposition is one of the allowed set;
  - cited files exist and each cited name is a function marked `#[test]`;
  - notes are present.
  It prints the mapped count (7 of 199).

## How it was checked

- **Each cited test was read**, not matched by name:
  - staging `.part` and final absence: `abrupt_exit…`, `corrupted_staging…`;
  - independent re-hash refusing a tampered stage: `corrupted_staging…`;
  - a changed source refused before publication: `lost_custody…`;
  - an existing final never replaced: `foreign_equal_content…` and the
    relocate link-collision unit test;
  - source removal only after the verified committed set: move-mode tests.
- **Publication** was read in `mover-fs/src/relocate.rs`. An earlier draft of
  this mapping called it a link-only deviation. It is
  `renameat2(RENAME_NOREPLACE)` with a no-clobber link fallback only when the
  filesystem lacks that flag.
- **Checker:** negative-checked with an unknown ID, a misspelled test name and
  a non-test helper function (all reported, exit 1). It checks references, not
  whether a test proves its row; that is a review question.

## Follow-up: DST (2026-11-21)

L2-DST-001 to 005 mapped in the same file: 001, 002, 003 and 005 Tested; 004
Partly tested (the consumer side is a documented obligation, not tested). For
002 the requirement allows collision, and the mover always treats a foreign
destination as one, even an identical one.

## Decisions for the user (from DPR and DST)

- **L2-DPR-005:** accept the no-clobber link fallback, or reword the
  requirement to "atomic, no-clobber publication".
- **L2-DPR-006:** reword the requirement to exempt explicit, operator-confirmed
  deletion (increments 143/144).

## Not covered

- 192 L2 requirements remain, along with L3 and the L1 roll-up.
- Test evidence does not qualify NFS, systemd or physical faults.
