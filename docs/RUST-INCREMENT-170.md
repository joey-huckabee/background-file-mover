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

## Follow-up: DEL and CLN (2026-11-21)

L2-DEL-001 to 004 and L2-CLN-001 to 005, in the same file:
- **Tested:** DEL-001, 002 and 003; CLN-001 and 005.
- **Deviation (needs approval):** DEL-004 and CLN-002 (same exception as DPR-006).
  Automatic cleanup meets them; operator-confirmed deletion does not.
- **Inspection:** CLN-003. A non-empty private folder is kept and not reported
  as removed; no test.
- **Partly tested:** CLN-004. An unexpected object at the copy's name is
  refused and reported. An extra file beside the copy is kept silently.

For **automatic** cleanup, the removal sequence was read in
`file-mover/src/delivery_worker.rs`: the manifest and every final file are
verified before any removal is authorized
(`authorize_source_cleanup`). Then `discard_retained_source` in
`mover-fs/src/lib.rs` re-checks identities and confirms a zero link count.

## Follow-up: SUB and FS (2026-11-21)

L2-SUB-001 to 005 and L2-FS-001 to 005, in the same file:
- **Tested:** SUB-001, 002, 003 and 005; FS-001, 004 and 005.
- **Partly tested:** FS-002. Recovery matches the recorded identity; the
  check right after a normal move is by inspection.
- **Inspection:** FS-003 (the same-device refusal in `relocate.rs`; no
  cross-filesystem test).
- **Deviation (needs approval):** SUB-004. There is no submission manifest
  file; the claimed set is recorded in SQLite.

## Follow-up: REC and RTY (2026-11-21)

L2-REC-001 to 004 and L2-RTY-001 to 006, in the same file:
- **Tested:** REC-001, 003 and 004; RTY-001, 003, 004 and 006.
- **Deviation (needs approval):**
  - REC-002: stale partials are removed after delivery, not at re-queue;
  - RTY-002: permanent failures, other than a binding refusal or a foreign
    marker, get bounded attempts before review;
  - RTY-005: fixed, not configurable, backoff and attempt limit.

## Decisions for the user (from DPR, DST, DEL, CLN, SUB, FS, REC and RTY)

- **L2-DPR-005:** accept the no-clobber link fallback, or reword the
  requirement to "atomic, no-clobber publication".
- **L2-DPR-006:** reword the requirement to exempt explicit, operator-confirmed
  deletion (increments 143/144). The same decision covers L2-DEL-004 and L2-CLN-002.
- **L2-CLN-004:** whether the mover should report (route to an operator) an
  unexpected extra file left in a private folder after removing its copy.
  Today it is kept silently.
- **L2-SUB-004:** accept the durable SQLite job, file list and claim records as
  the submission manifest (the written manifest is `COMMITTED.json` at
  delivery), or reword the requirement.
- **L2-REC-002:** accept removing stale partial copies after delivery (or by
  confirmed deletion) instead of at re-queue, or reword.
- **L2-RTY-002:** accept "bounded attempts, then review" for failures that are
  not explicitly classified, or reword.
- **L2-RTY-005:** accept the fixed retry limit and delays (three failures; 30
  and 60 s for capacity, 5 s otherwise), or make them configurable (a product
  change).

## Not covered

- 192 L2 requirements remain, along with L3 and the L1 roll-up.
- Test evidence does not qualify NFS, systemd or physical faults.
