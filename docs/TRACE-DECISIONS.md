# L2 decisions for the user

Decision cohort from main `6bfd27e`, answered by the user on **2026-11-22**.
The original [trace](TRACE-L2.md) had 65 deviations and 14 proposed
not-applicable rows: **79 IDs assigned once to 12 decisions**, plus 16
supplementary pending items from
[increment170](RUST-INCREMENT-170.md#decisions-for-the-user-all-families-so-far).
The index preserves that original cohort after the approved mapping changes;
it is not a second ballot or the set of rows still awaiting a decision.

The original ballot accepted every recommendation; the later CLI-006 logging
decision below supersedes only its no-managed-log-files clause and static stream
policy. Decisions D01–D03 and D05–D09 originally accepted
rewording; D04 excludes its features from the first release; D10–D12 retain
requirements as approved backlog. Each affected trace row records its decision.
The short approved requirement wording is in the row notes; updating L2-REQ.md
itself is a follow-up. Evidence was not promoted beyond its existing scope.

The options below are retained as the decision record. Approval of wording
neither proves behavior nor grants implementation, deployment, deletion,
dependency or operational-state authorization. NFS remains disabled in production
and all release gates remain open. The two decisions settled on 2026-11-21
remain separate. Frozen v2/legacy bytes, original-state recovery and prior
safety authorizations are unchanged.

## Later user decisions and logging backlog (2026-11-22)

- **Accepted 2026-11-22 — L2-JOB-014 (D02):** the restored rule that a failed
  record/unrecorded effect never authorizes source deletion or silent continuation.
- **Accepted 2026-11-22 — L2-SEC-008 (D06):** the restored unconditional ban on
  `system(3)`/shell invocation; Rust Command with explicit argv is the mechanism,
  not a restriction of that ban to worker launches.
- **Rejected 2026-11-22 — L2-CLI-006 (supersedes this part of D07):** the
  software-manages-no-log-files clause. Replace it with configurable daemon
  logging: leveled journal stderr plus an explicitly enabled managed/rotated
  file; default OFF; configuration-file levels off/error/warn/info/debug;
  restart applies changes. Enablement requires both configuration opt-in and a
  file path/name. Sinks must not block copy/claim/delivery loops or convert log
  write/full-disk errors into transfer failures. Secret redaction, non-terminal
  service/automation and command-result stdout remain required.

**Approved backlog (2026-11-22): L2-CLI-006 — configurable logging, pending
review of [LOGGING-DESIGN.md](LOGGING-DESIGN.md) before implementation.** This
is a later obligation, additional to the original D10–D12 backlog table below;
it is not an approval of the design's proposed limits or unresolved assumptions.
Confirm minimal OFF-mode readiness/error stderr versus total silence. Today's
readiness actually uses stdout; the proposed stream move is identified in the
design. No new crate is approved, and no runtime behavior changes here.

The original 79-ID cohort, D07 answer and index below remain historical audit
records. CLI-006's existing trace Inspection describes the old implementation,
not coverage of this newly approved backlog. Its formal requirement/disposition
and checker bookkeeping must be reconciled together after design review;
recording the decision does not claim logging shipped or overwrite evidence.

## D01 — Cancellation, deletion and retained partials

**Decided 2026-11-22: (a) — user accepted the recommendation.**

**Question:** Should the requirements describe the approved separate cancellation, deletion and cleanup actions?

**Today and difference:** Cancellation is cooperative between steps, preserves source and unfinished destination data, and skips unknown/finished jobs in bulk. Explicitly confirmed deletion can remove held copies of delivered copy-mode jobs (without move mode’s fresh re-check of the delivered set) and of settled cancelled jobs whose files were never published. Uncertain partials stay until proven safe cleanup after delivery or confirmed deletion, rather than disappearing at requeue.

- **(a)** Accept and reword these rules, including the explicit-deletion exception. Risk: a deliberate confirmed deletion can remove the remaining held copy; cancellation itself must never imply deletion.
- **(b)** Keep the literal older rules in the backlog for contract reconciliation. Cost: different cancel/delete timing and semantics need a separately reviewed design and compatibility assessment; existing approvals do not silently change.

**Recommendation: (a).** The existing separation and custody checks preserve the user-approved destructive-action boundary.

**Original approval-needed IDs:** `L2-DPR-006`, `L2-DEL-004`, `L2-CLN-002`, `L2-REC-002`, `L2-LIF-001`, `L2-LIF-002`, `L2-LIF-005`.

## D02 — Publication and the payload-effect boundary

**Decided 2026-11-22: (a) — user accepted the recommendation.**

**Question:** Should the approved explicit-list, durable-intent and staged no-clobber protocol replace older inventory and rename prescriptions?

**Today and difference:** The producer lists exact paths; claims can be partial and preserve their first durable indices. SQLite intent precedes payload relocation, though observation/empty-area allocation comes first. The mover copies, syncs and verifies staging, then uses no-clobber rename or exclusive link/unlink and a completion manifest. It retains uncertain facts after state-write failures; it does not blindly discard an admitted job. This differs from sorted all-or-nothing discovery, rename-only/two-hop publication and a single discard-or-halt commit point.

- **(a)** Accept and reword around these actual boundaries. Risk: the link pair has a recoverable two-name intermediate; cross-client visibility and server durability still need D11 qualification.
- **(b)** Keep the stronger/literal prescriptions as backlog design work. Cost: discovery/order, intent and publication changes can affect frozen identity and recovery; no implementation or weakening of custody is authorized.

**Recommendation: (a).** This records the approved preservation protocol without claiming that local tests qualify NFS.

**Original approval-needed IDs:** `L2-DPR-005`, `L2-XFR-002`, `L2-POSIX-002`, `L2-POSIX-003`, `L2-POSIX-004`, `L2-POSIX-005`, `L2-JOB-013`, `L2-JOB-014`, `L2-NFS-007`.

## D03 — The durable job model

**Decided 2026-11-22: (a) — user accepted the recommendation.**

**Question:** Should the split core-and-SQLite model and explicit enrollment/upgrade workflow be the job contract?

**Today and difference:** SQLite holds the accepted inventory and custody records; COMMITTED.json is written on completion. Core phases, store cancellation/retry/problem records and live counters are separate. One SQLite-owner thread serves callers. Startup refuses missing enrolled state and incompatible schemas; initialization and guarded migration are explicit. Job and manifest do not share the requested creation-time/integrity-mode fields, and problems are informational rather than an error iff FAILED field.

- **(a)** Accept and reword the actual model, including the metadata limitation and historical per-file deferral. Risk: consumers cannot rely on a common creation timestamp, a monolithic FAILED record or an acceptance-time manifest file.
- **(b)** Keep those model/metadata requirements as backlog work. Cost: schema, migration, public-contract and recovery design; do not restore automatic conversion or missing-state adoption.

**Recommendation: (a).** The approved store/custody model is authoritative and preserves original-state recovery.

**Original approval-needed IDs:** `L2-SUB-004`, `L2-CORE-002`, `L2-MGR-002`, `L2-JOB-003`, `L2-JOB-004`, `L2-JOB-007`, `L2-JOB-010`, `L2-JOB-011`.

## D04 — Earlier-design features outside the first release

**Decided 2026-11-22: (c) — user accepted the recommendation.**

**Question:** Should pause, bandwidth controls, byte-offset resume, rename templates and optional kernel-copy selection stay outside the first release?

**Today and difference:** These features are absent: copies are unthrottled buffered streams, interrupted files restart into a new attempt from byte zero, original relative names are preserved, and collisions never clobber. Stop/cancel are not job pause. Kernel copy is optional in the wording and is never selected, so there is no kernel-backend fallback branch.

- **(a)** Reword the requirements to describe the current reduced feature set. Cost: removes the older promises rather than retaining an explicit later-release scope boundary.
- **(b)** Keep the features in the product backlog for this release. Cost: scheduling, capacity, API and recovery design plus new qualification; scope and delivery time grow.
- **(c)** Approve out of scope for the first release, preserving current safety rules. Risk: no throughput cap, no job pause, more repeated I/O on restart and no naming customization; later inclusion needs separate approval.

**Recommendation: (c).** Optional features should not displace qualification of the already approved safe transfer path.

**Original approval-needed IDs:** `L2-LIF-004`, `L2-BWL-001`, `L2-BWL-002`, `L2-BWL-003`, `L2-BWL-004`, `L2-RSM-001`, `L2-RSM-002`, `L2-RSM-003`, `L2-REN-001`, `L2-REN-002`, `L2-COPY-011`.

## D05 — Bounded delivery retries

**Decided 2026-11-22: (a) — user accepted the recommendation.**

**Question:** Should fixed bounded reconciliation attempts followed by review remain the delivery-retry policy?

**Today and difference:** Binding refusals go straight to review; other unclassified failures, including potentially permanent ones, get at most three persisted failures before review. Capacity delays are 30/60 seconds before subsequent attempts; other delays are five seconds. The limits are fixed, and a retry grants no new filesystem authority. This is not a configurable permanent/transient taxonomy. It does not revisit either settled 2026-11-21 decision.

- **(a)** Accept and reword the fixed bounded policy. Risk: some permanent faults consume extra I/O before review and operators cannot tune the delays.
- **(b)** Retain configurable limits/permanent-failure classification in the backlog. Cost: phase-aware classification, persisted-policy and replay tests; classifiers must not authorize uncertain effects.

**Recommendation: (a).** The existing limits are approved and attempts still require valid custody; external-loss and NFS safety stay in D10/D11.

**Original approval-needed IDs:** `L2-RTY-002`, `L2-RTY-005`.

## D06 — Rust construction and storage architecture

**Decided 2026-11-22: (a) — user accepted the recommendation.**

**Question:** Should the approved Rust libraries, typed construction and direct POSIX/actor architecture replace older implementation prescriptions?

**Today and difference:** The mover uses pinned serde_json with stricter project rules, typed mutable Config values validated at entry points, concrete POSIX/SQLite effects, worker channels, a current-thread reactor, a fixed TLS executor and separate lifecycle handling. It has no general dependency-injection/object-storage interface, condition-variable queue or C++ build. Rust argv process launch and Tokio signal-receiver tasks replace literal C process/flag mechanisms. Callback/task code is not an OS signal handler.

- **(a)** Accept and reword these mechanisms and the current POSIX-only scope; retire the C++-specific obligation conditionally. Risk: object backends/general injection need later refactoring; dependency/native audits and signal safety are still required.
- **(b)** Keep the literal mechanisms/general interfaces as backlog design work. Cost: broad construction and test changes; approved dependencies, native target checks and custody cannot be bypassed.

**Recommendation: (a).** Safe approved Rust mechanisms should be judged by their guarantees, with verification gaps retained in D12.

**Original approval-needed IDs:** `L2-MGR-001`, `L2-STO-001`, `L2-STO-003`, `L2-STO-004`, `L2-ARC-003`, `L2-ARC-007`, `L2-JSON-001`, `L2-CFG-005`, `L2-SEC-008`, `L2-CTL-006`, `L2-CTL-014`, `L2-CTL-017`.

## D07 — CLI, startup diagnostics and operator text

**Decided 2026-11-22: (a) — user accepted the recommendation.**

**Later clarification, 2026-11-22:** CLI-006’s no-managed-files/static logging
limit is superseded by the approved logging backlog above. This answer is the
original ballot record, not acceptance of that superseded clause.

**Question:** Should the current flag-based CLI and fail-closed, secret-safe diagnostic contract replace broader CLI/reporting prescriptions?

**Today and difference:** Local commands use mode flags; producer submission and several job operations are HTTP APIs, not a submit CLI. Startup validates mandatory capabilities instead of producing a full optional-capability report. Validation stops at its first error; diagnostics omit some option/value/range context, use numeric errno plus dashboard labels, and display ordinary Rust errors without a traceback. Service stream routing lacks the specified severity dispatcher. Config-only validation is reserved for D12.

- **(a)** Accept and document these limits. Risk: more validation iterations, less uniform context/severity filtering and no promised CLI route equivalents or optional-capability report; secret values remain excluded.
- **(b)** Keep richer CLI, report and diagnostic requirements in the backlog. Cost: command/output contracts and tests; richer messages must not echo credentials or arbitrary unsafe text.

**Recommendation: (a).** Current commands fail closed and the user approved readable errors; convenience differences need no new runtime surface.

**Original approval-needed IDs:** `L2-ENV-001`, `L2-ENV-002`, `L2-ENV-003`, `L2-XFR-004`, `L2-CFG-008`, `L2-CFG-009`, `L2-CFG-010`, `L2-CLI-001`, `L2-CLI-002`, `L2-CLI-006`, `L2-CLI-008`, `L2-CLI-009`, `L2-CLI-010`.

## D08 — Dashboard updates and event scope

**Decided 2026-11-22: (a) — user accepted the recommendation.**

**Question:** Should the dashboard remain an authenticated snapshot/SSE view rather than a general immutable event bus?

**Today and difference:** The embedded page uses admin reads and advisory/coalesced SSE changes, not GET /api/status polling. Store notifications use a trusted version callback; each SSE receiver is independent. Progress aggregates active files by job and reports a representative per-job file index, rather than identifiers on every immutable transfer event. A general subscriber panic-isolation contract is not demonstrated.

- **(a)** Accept and reword this limited trusted-callback/snapshot scope. Risk: no authoritative event history or general subscriber-failure guarantee; the trusted SQLite-thread callback has no panic boundary, so general subscriber panic isolation is explicitly not promised.
- **(b)** Keep a generic typed event-bus/fault-isolation contract in the backlog. Cost: additional publication, identity, buffering and concurrency design/tests; transfers remain independent of dashboard sessions.

**Recommendation: (a).** This preserves the approved live-update design without promoting notifications into custody evidence.

**Original approval-needed IDs:** `L2-DASH-001`, `L2-EVT-001`, `L2-EVT-002`, `L2-EVT-005`.

## D09 — Versioned control-plane audiences

**Decided 2026-11-22: (a) — user accepted the recommendation.**

**Question:** Should the requirements describe the approved versioned, audience-separated HTTP/HTTPS and local-control interfaces?

**Today and difference:** Binding is explicit rather than defaulted; producer jobs, private operator/control and authenticated browser routes are separate. Producer non-submission paths may return 403 to avoid disclosure. Ordinary JSON replies use length/close framing, while admin documents/assets and SSE differ. Native Rust HTTPS is already approved; the reverse-proxy prohibition and unversioned route inventory are obsolete.

- **(a)** Align the requirement wording with the approved interfaces and exceptions. Risk: callers must use the proper audience/version and cannot depend on legacy aliases or a universal all-JSON response model.
- **(b)** Keep the conflicting older interface wording as backlog contract work. Cost: unresolved release documentation and compatibility design; this does not authorize proxy deployment, a legacy adapter or unauthenticated reads.

**Recommendation: (a).** The architecture and contract were already approved; this choice reconciles wording rather than reopening TLS selection.

**Original approval-needed IDs:** `L2-CTL-001`, `L2-CTL-002`, `L2-CTL-005`, `L2-CTL-010`, `L2-CTL-013`, `L2-CTL-016`.

## D10 — Interference, identity and external-loss safety

**Decided 2026-11-22: (b) — user accepted the recommendation.**

**Question:** Should the stronger identity, timeout, progress and missing-both safety obligations remain in the backlog until their scope and evidence are established?

**Today and difference:** Descriptor checks use durable identities and protected parents, not a preceding stat/compare for every open. Exact relative names replace universal realpath canonicalization. Blocking workers retain custody beyond coordinator deadlines; one claim worker or SQLite owner can still stall its queue. Missing/unprovable paths use blocked/uncertain/review handling, not a distinct immediate failed-external state. There is no privileged-writer fence or proof that a timer cancels remote effects.

- **(a)** Accept this narrower threat/progress model and reword explicitly. Risk: stronger hostile-writer, per-entry timeout/progress and external-quarantine guarantees would no longer be promised.
- **(b)** Keep the safety obligations and add threat-model, feasibility, classification and adversarial-test work to the backlog. Cost: substantial design/qualification; literal extra stats or forced timeout teardown cannot substitute for fencing. Preserve current guards, original state and exact-name rules during any work.

**Recommendation: (b).** These differences affect data-safety/security claims and should not be waived without a focused safety decision.

**Original approval-needed IDs:** `L2-SEC-002`, `L2-SEC-006`, `L2-SEC-009`, `L2-SEC-010`, `L2-SEC-011`.

## D11 — Production NFS obligations

**Decided 2026-11-22: (b) — user accepted the recommendation.**

**Question:** Should NFS error, artifact, visibility and durability obligations remain pending until separately authorized target-export qualification?

**Today and difference:** Production NFS is disabled. There is no dedicated ESTALE scheduling class; enrollment rejects unknown namespace entries, including silly-rename artifacts; numeric errno details are not retry authority. Strategy logging is incomplete. Mount/attribute observations are limited, and local fallback tests plus controlled real-export labs do not qualify actual NAS backing-storage, cross-client caches or power-loss durability. D02 covers L2-NFS-007’s publication-mechanism rewording; D11 retains its separate cross-client visibility and server/export/storage qualification limits.

- **(a)** Limit requirements to today's local-only capability and existing lab evidence. Risk: this narrows the intended NFS release promise and cannot enable production NFS.
- **(b)** Retain phase-aware NFS classification/artifact handling and target visibility/server/export/storage qualification in the backlog. Cost: controlled target environments, hardware/fault access and separate authorization; no retry or takeover may be inferred from timeouts.
- **(c)** Approve NFS out of scope for the first release, keeping production refusal. Risk: changes the release's intended source-storage use case; later support still needs full qualification.

**Recommendation: (b).** The missing evidence and authority rules affect custody and durability; a build label or lab pass is insufficient.

**Original approval-needed IDs:** `L2-NFS-004`.

## D12 — Release checks and host security integration

**Decided 2026-11-22: (b) — user accepted the recommendation.**

**Question:** Should the remaining validation, verification and host-integration obligations stay explicit backlog items rather than be waived?

**Today and difference:** Guarded --check-state opens SQLite; it is not the requested config-only preflight. The pending list also requests leftover reporting, shared config documentation, external JSON corpus/fuzzing, a separate TSan tier, manager ready/stopping/watchdog integration, target MAC/hardened shipping and endpoint-security exclusion verification. Existing helpers, candidate units and dashboard heartbeats do not establish all of these. The separate Open-row triage records the verification/feature gaps; it does not close them.

- **(a)** Accept current limits and reword/exclude these obligations explicitly. Risk: gives up requested deployment/security assurance and some operator diagnostics; existing safety controls and release gates remain unchanged.
- **(b)** Keep the requirements and create scoped implementation/test/qualification backlog items. Cost: tooling plus platform-specific design and local gates; manager restart must preserve blocked-worker exclusion and the original stop deadline. No feature implementation or operational policy change is authorized by this sheet.

**Recommendation: (b).** Preflight, race detection and host-security gaps need evidence and deliberate closure, not optimistic wording.

**Original approval-needed IDs:** `L2-CTL-019`.

## Supplementary items outside the original 79 approval rows

These 16 originally Open/Partly tested items also appear in increment170’s
decision list. Their packages are decided above. D03 reconciles CORE-001/JOB-001
wording without upgrading their evidence; D11/D12 retain the other items as
approved backlog. They are not additions to the original 79-ID cohort.

| Pending L2 ID | Decision | Question within that package |
|---|---|---|
| L2-ARC-008 | D12 | Separate race-detector CI evidence. |
| L2-CFG-007 | D12 | State-dependent inspection versus config-only preflight. |
| L2-CFG-011 | D12 | Shared option definitions and generated documentation. |
| L2-CLN-004 | D12 | Report preserved extra files rather than leaving silent leftovers. |
| L2-CORE-001 | D03 | The complete core/store state-model split. |
| L2-CTL-011 | D12 | Manager readiness/stopping notifications. |
| L2-CTL-012 | D12 | Manager liveness/restart policy. |
| L2-JOB-001 | D03 | Historical per-file deferral versus approved records. |
| L2-JSON-005 | D12 | Independent JSON corpus/fuzz coverage. |
| L2-NFS-001 | D11 | Per-tree strategy logging and actual export support. |
| L2-NFS-005 | D11 | Silly-rename artifact tolerance. |
| L2-NFS-008 | D11 | Actual target server/export/storage durability evidence. |
| L2-POSIX-012 | D11 | Errno specificity versus NFS classification/authority. |
| L2-SEC-013 | D12 | Target SELinux/AppArmor policy and labels. |
| L2-SEC-014 | D12 | Full hardened deployment unit. |
| L2-SEC-016 | D12 | Endpoint-security exclusion verification. |

## Approved backlog

**Approved 2026-11-22 (D10–D12, option b):** retain these obligations;
implementation, design details and target qualification need separately scoped
work. Each retained ID appears once in this list. Shared deliverables are grouped
rather than duplicated. Existing Partial/Open/Deviation dispositions remain;
approval to retain work is not approval of a safety exception or a passing test.

| Item | Decision | L2 IDs | Retained work |
|---|---|---|---|
| Identity and substitution | D10 | L2-SEC-002 | Establish the stronger identity/threat model and adversarial substitution guarantees without treating NOFOLLOW or extra stat calls as fencing. |
| Exact names and canonicalization | D10 | L2-SEC-006 | Reconcile the stronger absolute-path obligation with approved exact relative UTF-8 names through a focused safety design; no normalization or permission expansion is approved. |
| Per-call timeout safety | D10 | L2-SEC-009 | Establish feasible deadline/entry-failure guarantees while preserving custody through actual blocked-worker exit. |
| Independent progress | D10 | L2-SEC-010 | Define and demonstrate progress isolation despite stalled claim workers, delivery workers or SQLite. |
| External-loss classification | D10 | L2-SEC-011 | Define missing-both diagnosis, quarantine/review and retry authority without adopting unrelated files or inferring settled effects from timeouts. |
| NFS errno classification | D11 | L2-NFS-004, L2-POSIX-012 | Define phase-aware ESTALE/error classification, scheduling authority and real-export errno evidence. |
| Per-tree NFS strategy | D11 | L2-NFS-001 | Add selected-strategy reporting and establish actual target-export capabilities. |
| NFS artifact tolerance | D11 | L2-NFS-005 | Resolve enrollment’s known unknown-entry refusal without adopting/deleting unknown bytes, and qualify other managed-directory silly-rename paths. Fail-closed enrollment exemption is not approved. |
| Server-side durability | D11 | L2-NFS-008 | Qualify actual target server/export/storage persistence and consumer-cache visibility separately from D02’s NFS-007 mechanism rewording; lab protocol facts are not a production or power-loss pass. |
| Config-only preflight | D12 | L2-CTL-019, L2-CFG-007 | Add a standalone no-store/no-service configuration check with secret-safe diagnostics; guarded state inspection remains separate. |
| Leftover reporting | D12 | L2-CLN-004 | Report preserved unexpected extra files to the operator rather than leave them silently. |
| Shared config definitions | D12 | L2-CFG-011 | Share validation/options and generated documentation with drift verification. |
| JSON verification | D12 | L2-JSON-005 | Run a pinned independent conformance corpus and coverage-guided fuzzing; retain findings as regressions. |
| Race-detector tier | D12 | L2-ARC-008 | Establish and enforce an applicable separate TSan CI tier, including native instrumentation limits. |
| Manager lifecycle | D12 | L2-CTL-011 | Implement and qualify ready/stopping notifications against the supported manager. |
| Manager liveness | D12 | L2-CTL-012 | Design and qualify heartbeat/hang/restart policy without bypassing worker exclusion or the original shutdown deadline. |
| MAC integration | D12 | L2-SEC-013 | Establish pre-publication destination SELinux labeling and qualified path-specific AppArmor policy. |
| Hardened shipping | D12 | L2-SEC-014 | Complete and qualify the target service unit and its writable-path restrictions. |
| Endpoint-security verification | D12 | L2-SEC-016 | Select supported read-only exclusion queries and report actual policy coverage/freshness, including unknown results. |

## Approval ID index

Every ID in the original 79-row approval cohort appears once in this index and
belongs to the same single decision as its section’s list above.

| L2 ID | Decision |
|---|---|
| L2-ARC-003 | D06 |
| L2-ARC-007 | D06 |
| L2-BWL-001 | D04 |
| L2-BWL-002 | D04 |
| L2-BWL-003 | D04 |
| L2-BWL-004 | D04 |
| L2-CFG-005 | D06 |
| L2-CFG-008 | D07 |
| L2-CFG-009 | D07 |
| L2-CFG-010 | D07 |
| L2-CLI-001 | D07 |
| L2-CLI-002 | D07 |
| L2-CLI-006 | D07 |
| L2-CLI-008 | D07 |
| L2-CLI-009 | D07 |
| L2-CLI-010 | D07 |
| L2-CLN-002 | D01 |
| L2-COPY-011 | D04 |
| L2-CORE-002 | D03 |
| L2-CTL-001 | D09 |
| L2-CTL-002 | D09 |
| L2-CTL-005 | D09 |
| L2-CTL-006 | D06 |
| L2-CTL-010 | D09 |
| L2-CTL-013 | D09 |
| L2-CTL-014 | D06 |
| L2-CTL-016 | D09 |
| L2-CTL-017 | D06 |
| L2-CTL-019 | D12 |
| L2-DASH-001 | D08 |
| L2-DEL-004 | D01 |
| L2-DPR-005 | D02 |
| L2-DPR-006 | D01 |
| L2-ENV-001 | D07 |
| L2-ENV-002 | D07 |
| L2-ENV-003 | D07 |
| L2-EVT-001 | D08 |
| L2-EVT-002 | D08 |
| L2-EVT-005 | D08 |
| L2-JOB-003 | D03 |
| L2-JOB-004 | D03 |
| L2-JOB-007 | D03 |
| L2-JOB-010 | D03 |
| L2-JOB-011 | D03 |
| L2-JOB-013 | D02 |
| L2-JOB-014 | D02 |
| L2-JSON-001 | D06 |
| L2-LIF-001 | D01 |
| L2-LIF-002 | D01 |
| L2-LIF-004 | D04 |
| L2-LIF-005 | D01 |
| L2-MGR-001 | D06 |
| L2-MGR-002 | D03 |
| L2-NFS-004 | D11 |
| L2-NFS-007 | D02 |
| L2-POSIX-002 | D02 |
| L2-POSIX-003 | D02 |
| L2-POSIX-004 | D02 |
| L2-POSIX-005 | D02 |
| L2-REC-002 | D01 |
| L2-REN-001 | D04 |
| L2-REN-002 | D04 |
| L2-RSM-001 | D04 |
| L2-RSM-002 | D04 |
| L2-RSM-003 | D04 |
| L2-RTY-002 | D05 |
| L2-RTY-005 | D05 |
| L2-SEC-002 | D10 |
| L2-SEC-006 | D10 |
| L2-SEC-008 | D06 |
| L2-SEC-009 | D10 |
| L2-SEC-010 | D10 |
| L2-SEC-011 | D10 |
| L2-STO-001 | D06 |
| L2-STO-003 | D06 |
| L2-STO-004 | D06 |
| L2-SUB-004 | D03 |
| L2-XFR-002 | D02 |
| L2-XFR-004 | D07 |

## Self-check

```sh
python3 scripts/check_trace_decisions.py
python3 scripts/check_trace.py
```

The first check compares the original decision lists and index against the
union of retained approval-needed rows, approved rewordings and approved
first-release exclusions in TRACE-L2.md. It rejects missing/extra IDs, duplicate
assignments, differing section/index decisions and missing/incorrect answer
markers. Supplementary items must exist outside the original cohort, and the
approved backlog must cover every D10–D12 item exactly once. It checks coverage
and bookkeeping, not the merits or sufficiency of evidence. The trace checker
validates IDs, evidence references and allowed dispositions; neither checker
rewrites requirements or proves qualification.
