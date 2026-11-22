# Rust traceability status

Formal L1/L2/L3 derivation and verification discovery remain open under
P10/RC-23 of [the release closure](RUST-RELEASE-CLOSURE.md). There is currently
no generated Rust requirement-coverage percentage. Do not infer verification
from requirement existence or reuse historical coverage figures.

- [L1](L1-REQ.md): system requirements and approved Rust additions.
- [L2](L2-REQ.md): functional architectural obligations; applicability and Rust
  evidence dispositions still require review.
- [L3](L3-REQ.md): retained functional and durability obligations.
- [Scenarios](RUST-SCENARIOS.md): stable user situations and actual evidence.
- [Release matrix](RUST-RELEASE-CLOSURE.md): finite remaining acceptance work.
- [Current build evidence](STATE-BACKUP-EVIDENCE.json): named source/artifacts
  and bounded SLES results, not proof of all requirements or production release.

## Plan

Started in [increment 170](RUST-INCREMENT-170.md). It proceeds one step at a
time, each a small reviewed PR:

1. **L2 to Rust evidence**, one L2 family per increment, in
   [TRACE-L2.md](TRACE-L2.md). Each requirement gets a disposition and cited
   tests or code. `scripts/check_trace.py` (CI `admin-ui` job) checks the IDs
   and cited tests and reports the mapped count.
2. **Decisions for the user**, collected as they arise and never made alone:
   - deviations (Rust meets the intent differently);
   - proposed "not applicable" requirements (for example Python-era
     mechanisms, or features outside the Rust first release);
   - rewording.
3. **L3:** the current [L3](L3-REQ.md) names retired Python mechanisms
   (`hashlib`, `ManifestWriter`). Replacing or retiring it is a user decision
   after step 1. Until then, L3 IDs are not reused.
4. **L1 roll-up:** an L1 requirement is traced when all its L2 children are
   Tested, or accepted as deviations or not applicable.

Progress: DPR, DST, DEL, CLN, SUB, FS, REC, RTY, LIF, CORE, BWL, RSM, REN, XFR,
MGR, STO, ENV, DASH, JSON, CFG and EVT (98 of 199 L2) mapped.

All eight release gates remain open. Product approvals and source/state safety
requirements are unchanged by source cleanup.
