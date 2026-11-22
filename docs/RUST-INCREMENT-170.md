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
- **Tested:** REC-001 and 003; RTY-001, 003, 004 and 006.
- **Partly tested:** REC-004. Worker count, limits and eventual commits are
  tested; overlapping delivery is by inspection.
- **Deviation (needs approval):**
  - REC-002: stale partials are removed after delivery, not at re-queue;
  - RTY-002: permanent failures, other than a binding refusal or a foreign
    marker, get bounded attempts before review;
  - RTY-005: fixed, not configurable, backoff and attempt limit.

## Follow-up: LIF and CORE (2026-11-21)

L2-LIF-001 to 005 and L2-CORE-001 to 004, in the same file:
- **Tested:** LIF-003; CORE-003.
- **Partly tested:** CORE-001. The recording transitions are in the core;
  cancellation, retry and cleanup state are in the store.
- **Inspection:** CORE-004 (`mover-core` has no clock, file or network
  access).
- **Deviation (needs approval):**
  - LIF-001: cancel keeps partial destination files; deleting them is
    separate;
  - LIF-002: cancellation stops between steps, and there is no pause;
  - CORE-002: the job data is split between the core and SQLite;
  - LIF-005: cancelling an unknown or finished job is skipped (approved), not
    refused with a typed error.
- **Not applicable (needs approval), proposed:** LIF-004 (pause and resume).

## Follow-up: BWL, RSM, REN, XFR and MGR (2026-11-21)

These families describe features of the earlier design.
- **Not applicable (needs approval), proposed:**
  - BWL-001 to 004: no throughput limit;
  - RSM-001 to 003: no byte-offset resume (RSM-003's safety clause holds);
  - REN-001 and 002: no rename templates or collision policies (no-clobber
    only).
- **Inspection:** REN-003 (same-filesystem moves).
- **Deviation (needs approval):**
  - XFR-002: the same publication decision as DPR-005;
  - XFR-004: errno numbers and labels, not errno text;
  - MGR-001: worker threads without a condition-variable queue;
  - MGR-002: the same split as CORE-002.
- **Partly tested:**
  - XFR-001: a copy interface with an optional progress callback; the callback
    wiring is by inspection;
  - MGR-003: deadline, ownership and exit are tested; draining an in-flight
    transfer is by inspection and historical evidence.

## Follow-up: STO, ENV, DASH and JSON (2026-11-21)

- **Tested:** DASH-002 (the inlined-assets unit test and the live CSP),
  JSON-002 and JSON-004.
- **Partly tested:** DASH-003. A new CI check,
  `scripts/admin-ui/no-html-sinks.test.js`, is a lexical regression check
  covering whitespace variants; it tests its own pattern set. Text-only
  rendering is by inspection.
- **Also partly tested:** STO-002 (NFS only in qualification builds), JSON-003
  (fractions and NUL are refused by the schema and field rules, not the
  parser).
- **Inspection:** STO-005 (locked dependencies, SLES gate).
- **Open:** JSON-005 (no conformance corpus or fuzzing).
- **Deviation (needs approval):**
  - STO-001, 003 and 004: direct POSIX, no storage interfaces;
  - ENV-001: startup refusal, no diagnostic report;
  - DASH-001: SSE and `/api/v2/admin` reads, no `/api/status` polling;
  - JSON-001: `serde_json` with project strictness rules.
- **Not applicable (needs approval), proposed:** ENV-002 and 003.
- **Checker:** `scripts/...` evidence (CI tests in other languages) is now
  accepted, checked for existence only.

## Follow-up: CFG and EVT (2026-11-22)

L2-CFG-001 to 011 and L2-EVT-001 to 005 add 16 mappings (98 of 199 total):

- **Partly tested (6):** CFG-002, 003, 004, 006 and 007; EVT-003.
  Binding/policy tests demonstrate selected unknown/missing fields and ranges;
  actual protected/native startup refusals leave no state or endpoints. Remaining
  deserialization/validator coverage and startup sequencing are by inspection.
  Jobs commit without admin subscriptions, and full/disconnected progress channels
  do not block the sender; authoritative transition ownership is by inspection.
  `--check-state` also validates configuration without starting the service, but
  needs existing state and exclusion; its invalid-config path is by inspection.
  CFG-004 explicitly records the numeric settings without application ranges:
  `missing_file_retry_window_seconds` accepts all `u32` values, including zero;
  `max_retained_jobs` and `max_retained_bytes` require only non-zero `u64` values.
  In CFG-002, the stage of destination-binding unknown-field refusal is by
  inspection, not isolated by its test. EVT-005 identifies `file_id` as a per-job
  file index, not a filesystem identity.
- **Inspection (2):** CFG-001 and EVT-004. The bounded config loader uses pinned
  Serde dependencies and standard file I/O. Store writes/version notifications
  serialize on the SQLite worker; the progress board has a mutex. There is no
  dedicated concurrent-publication/multiple-subscriber race test cited.
- **Deviation (needs approval) (7):** CFG-005, 008, 009 and 010; EVT-001, 002
  and 005. Runtime configuration snapshots are shared but the public `Config`
  type is mutable and has no distinct validated form. Validation is fail-fast, with
  incomplete field/value/range diagnostics. Approved SSE notifications use
  versions and progress snapshots, not a typed immutable event bus or identifiers
  on every transfer notification. Bounded stream failures are handled, but the
  single trusted store callback has no panic boundary and general subscriber
  fault isolation is not demonstrated.
- **Open (1):** CFG-011 (no common option-definition/documentation generator
  found). This absence is not an approved scope exclusion.

Each cited test body and the associated code was read, including the config
loader, nested policy/ingress validators, startup entry points, store callback,
SSE send/wait loop and progress IPC/board. In particular, the shutdown range test
checks rejection, not diagnostic completeness, and the timed-wake test uses one
sender: neither is counted as proof of a broader reporting/concurrency property.
The event mapping preserves the approved increment136 live-update behavior and
asks only how to reconcile the L2 wording. Cited tests have no qualification-only
fault branch; native TLS cases require the gate's disposable credentials. This
batch runs the trace checker, not Rust tests or SLES gates; production NFS stays
disabled and no lab evidence is promoted to production qualification.

The same PR restores the 2026-11-03 workflow history line alongside the current
2026-11-21 role decision. It changes no product code or requirements.

## Decisions for the user (all families so far)

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
- **L2-LIF-001:** accept that cancel keeps incomplete destination files, with
  deletion as a separate confirmed action, or reword.
- **L2-LIF-002:** accept cooperative cancellation at step boundaries (no
  buffer-level stop, no pause), or reword.
- **L2-LIF-004:** confirm job pause and resume are out of scope, or keep them
  (Open; a product change).
- **L2-CORE-002:** accept the split job model (core recording plus SQLite
  records; no byte counters in the core), or reword. This also settles the
  scope of L2-CORE-001.
- **L2-LIF-005:** reword the requirement to match the approved behavior:
  unknown or finished jobs are skipped in bulk cancel, not refused.
- **BWL, RSM, REN-001/002:** confirm bandwidth limiting, byte-offset resume and
  rename templates/collision policies are out of the first-release scope, or
  keep any of them (Open; product work).
- **L2-MGR-001:** accept worker threads without a condition-variable queue,
  or reword.
- **L2-XFR-004:** accept errno numbers plus dashboard labels instead of errno
  text, or reword.
- **L2-XFR-002, L2-MGR-002:** settled by the DPR-005 and CORE-002 decisions.
- **L2-STO-001/003/004:** accept direct POSIX storage without an adapter
  interface or object-storage identity, or keep it as future product work.
- **L2-ENV-001 to 003:** accept startup refusal instead of a capability
  diagnostic (002 and 003 proposed not applicable), or reword.
- **L2-DASH-001:** accept SSE plus admin reads instead of polling
  `/api/status`, or reword.
- **L2-JSON-001:** accept the approved `serde_json` dependency with project
  strictness rules, or reword.
- **L2-JSON-005 (Open):** whether to add a JSON conformance corpus and fuzzing
  (product and test work, possibly new tooling).

- **L2-CFG-004 — decided: keep as today (user decision, 2026-11-21).**
  `missing_file_retry_window_seconds` keeps its current behavior: there is no
  application range check, and any `u32` is accepted, including zero. Zero
  expires a missing-file window immediately; 4,000,000,000 seconds is about
  127 years. No range check is requested by this decision. The L2-CFG-004 row's
  validation facts and disposition remain unchanged.
- **L2-CFG-005:** accept shared runtime snapshots with validation at service
  entry points, or require a distinct immutable validated configuration type.
- **L2-CFG-007:** confirm whether guarded `--check-state` (which validates
  configuration and then existing state without starting the service) satisfies
  the intended workflow, or require a standalone configuration check. The L2
  wording does not explicitly require configuration-only behavior; the existing
  command still needs a supported state and exclusive ownership.
- **L2-CFG-008:** accept first-error validation, or keep aggregate configuration
  diagnostics as product work.
- **L2-CFG-009/010:** agree consistent secret-safe section/option/reason and
  valid-option/range context, including whether/how offending values may be
  shown, or accept/reword the current partial diagnostics. This mapping does
  not authorize echoing sensitive values.
- **L2-CFG-011 (Open):** add a shared option definition/documentation generator,
  or explicitly accept separately maintained validation and instructions.
- **L2-EVT-001/005:** reconcile the approved advisory SSE versions and per-job
  progress snapshots with immutable typed event records and job/file identifiers
  on each transfer event. Accept/reword that mechanism or retain further work;
  this is not a unilateral decision that the old requirements are inapplicable.
- **L2-EVT-002:** accept the actual trusted single-callback/bounded SSE-stream
  scope, or require broader subscriber-failure isolation (including callback
  panic protection and failure-to-one/delivery-to-another evidence).

## Not covered

- 101 L2 requirements remain unmapped, along with L3 and the L1 roll-up.
  Mapped rows marked partial, deviation, proposed not applicable or Open are not
  requirement closure; their outstanding evidence/decisions remain above.
- Test evidence does not qualify NFS, systemd or physical faults.
