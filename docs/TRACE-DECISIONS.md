# L2 decisions for the user

Draft from main `6bfd27e`, 2026-11-22. **No answers are recorded here.**
The [trace](TRACE-L2.md) maps all 199 L2 requirements but leaves 65 deviations
and 14 proposed not-applicable rows awaiting approval. This sheet assigns each
of those **79 IDs to exactly one of 12 decisions**. The index repeats that
assignment for auditing; it is not another decision. Evidence/details remain in
the trace and [increment170's pending list](RUST-INCREMENT-170.md#decisions-for-the-user-all-families-so-far).

Reply with one letter per decision, for example `D01 a, D02 a, ...`. Each choice
applies to the whole stated package; if a package needs splitting, leave it
unanswered and name the exception. Recommendations are proposals, not approvals.
(a) accepts/reconciles the described behavior; (b) retains obligations as backlog;
(c), where offered, proposes a first-release scope exclusion. Accepting wording
does not mark evidence Tested, qualify NFS, close release gates or authorize
implementation, deployment, deletion, dependencies or operational-state changes.
The two decisions already settled on 2026-11-21 are excluded from this ballot.
Frozen v2/legacy bytes, guarded original-state recovery and existing user
approvals remain in force until a separate explicit change is agreed.

## D01 — Cancellation, deletion and retained partials

**Question:** Should the requirements describe the approved separate cancellation, deletion and cleanup actions?

**Today and difference:** Cancellation is cooperative between steps, preserves source and unfinished destination data, and skips unknown/finished jobs in bulk. Explicitly confirmed deletion can remove held copies of cancelled or copy-mode jobs without a verified destination. Uncertain partials stay until proven safe cleanup after delivery or confirmed deletion, rather than disappearing at requeue.

- **(a)** Accept and reword these rules, including the explicit-deletion exception. Risk: a deliberate confirmed deletion can remove the remaining held copy; cancellation itself must never imply deletion.
- **(b)** Keep the literal older rules in the backlog for contract reconciliation. Cost: different cancel/delete timing and semantics need a separately reviewed design and compatibility assessment; existing approvals do not silently change.

**Recommendation: (a).** The existing separation and custody checks preserve the user-approved destructive-action boundary.

**Approval-needed IDs:** `L2-DPR-006`, `L2-DEL-004`, `L2-CLN-002`, `L2-REC-002`, `L2-LIF-001`, `L2-LIF-002`, `L2-LIF-005`.

## D02 — Publication and the payload-effect boundary

**Question:** Should the approved explicit-list, durable-intent and staged no-clobber protocol replace older inventory and rename prescriptions?

**Today and difference:** The producer lists exact paths; claims can be partial and preserve their first durable indices. SQLite intent precedes payload relocation, though observation/empty-area allocation comes first. The mover copies, syncs and verifies staging, then uses no-clobber rename or exclusive link/unlink and a completion manifest. It retains uncertain facts after state-write failures; it does not blindly discard an admitted job. This differs from sorted all-or-nothing discovery, rename-only/two-hop publication and a single discard-or-halt commit point.

- **(a)** Accept and reword around these actual boundaries. Risk: the link pair has a recoverable two-name intermediate; cross-client visibility and server durability still need D11 qualification.
- **(b)** Keep the stronger/literal prescriptions as backlog design work. Cost: discovery/order, intent and publication changes can affect frozen identity and recovery; no implementation or weakening of custody is authorized.

**Recommendation: (a).** This records the approved preservation protocol without claiming that local tests qualify NFS.

**Approval-needed IDs:** `L2-DPR-005`, `L2-XFR-002`, `L2-POSIX-002`, `L2-POSIX-003`, `L2-POSIX-004`, `L2-POSIX-005`, `L2-JOB-013`, `L2-JOB-014`, `L2-NFS-007`.

## D03 — The durable job model

**Question:** Should the split core-and-SQLite model and explicit enrollment/upgrade workflow be the job contract?

**Today and difference:** SQLite holds the accepted inventory and custody records; COMMITTED.json is written on completion. Core phases, store cancellation/retry/problem records and live counters are separate. One SQLite-owner thread serves callers. Startup refuses missing enrolled state and incompatible schemas; initialization and guarded migration are explicit. Job and manifest do not share the requested creation-time/integrity-mode fields, and problems are informational rather than an error iff FAILED field.

- **(a)** Accept and reword the actual model, including the metadata limitation and historical per-file deferral. Risk: consumers cannot rely on a common creation timestamp, a monolithic FAILED record or an acceptance-time manifest file.
- **(b)** Keep those model/metadata requirements as backlog work. Cost: schema, migration, public-contract and recovery design; do not restore automatic conversion or missing-state adoption.

**Recommendation: (a).** The approved store/custody model is authoritative and preserves original-state recovery.

**Approval-needed IDs:** `L2-SUB-004`, `L2-CORE-002`, `L2-MGR-002`, `L2-JOB-003`, `L2-JOB-004`, `L2-JOB-007`, `L2-JOB-010`, `L2-JOB-011`.

## D04 — Earlier-design features outside the first release

**Question:** Should pause, bandwidth controls, byte-offset resume, rename templates and optional kernel-copy selection stay outside the first release?

**Today and difference:** These features are absent: copies are unthrottled buffered streams, interrupted files restart into a new attempt from byte zero, original relative names are preserved, and collisions never clobber. Stop/cancel are not job pause. Kernel copy is optional in the wording and is never selected, so there is no kernel-backend fallback branch.

- **(a)** Reword the requirements to describe the current reduced feature set. Cost: removes the older promises rather than retaining an explicit later-release scope boundary.
- **(b)** Keep the features in the product backlog for this release. Cost: scheduling, capacity, API and recovery design plus new qualification; scope and delivery time grow.
- **(c)** Approve out of scope for the first release, preserving current safety rules. Risk: no throughput cap, no job pause, more repeated I/O on restart and no naming customization; later inclusion needs separate approval.

**Recommendation: (c).** Optional features should not displace qualification of the already approved safe transfer path.

**Approval-needed IDs:** `L2-LIF-004`, `L2-BWL-001`, `L2-BWL-002`, `L2-BWL-003`, `L2-BWL-004`, `L2-RSM-001`, `L2-RSM-002`, `L2-RSM-003`, `L2-REN-001`, `L2-REN-002`, `L2-COPY-011`.

## D05 — Bounded delivery retries

**Question:** Should fixed bounded reconciliation attempts followed by review remain the delivery-retry policy?

**Today and difference:** Binding refusals go straight to review; other unclassified failures, including potentially permanent ones, get at most three persisted failures before review. Capacity delays are 30/60 seconds before subsequent attempts; other delays are five seconds. The limits are fixed, and a retry grants no new filesystem authority. This is not a configurable permanent/transient taxonomy. It does not revisit either settled 2026-11-21 decision.

- **(a)** Accept and reword the fixed bounded policy. Risk: some permanent faults consume extra I/O before review and operators cannot tune the delays.
- **(b)** Retain configurable limits/permanent-failure classification in the backlog. Cost: phase-aware classification, persisted-policy and replay tests; classifiers must not authorize uncertain effects.

**Recommendation: (a).** The existing limits are approved and attempts still require valid custody; external-loss and NFS safety stay in D10/D11.

**Approval-needed IDs:** `L2-RTY-002`, `L2-RTY-005`.

## D06 — Rust construction and storage architecture

**Question:** Should the approved Rust libraries, typed construction and direct POSIX/actor architecture replace older implementation prescriptions?

**Today and difference:** The mover uses pinned serde_json with stricter project rules, typed mutable Config values validated at entry points, concrete POSIX/SQLite effects, worker channels, a current-thread reactor, a fixed TLS executor and separate lifecycle handling. It has no general dependency-injection/object-storage interface, condition-variable queue or C++ build. Rust argv process launch and Tokio signal-receiver tasks replace literal C process/flag mechanisms. Callback/task code is not an OS signal handler.

- **(a)** Accept and reword these mechanisms and the current POSIX-only scope; retire the C++-specific obligation conditionally. Risk: object backends/general injection need later refactoring; dependency/native audits and signal safety are still required.
- **(b)** Keep the literal mechanisms/general interfaces as backlog design work. Cost: broad construction and test changes; approved dependencies, native target checks and custody cannot be bypassed.

**Recommendation: (a).** Safe approved Rust mechanisms should be judged by their guarantees, with verification gaps retained in D12.

**Approval-needed IDs:** `L2-MGR-001`, `L2-STO-001`, `L2-STO-003`, `L2-STO-004`, `L2-ARC-003`, `L2-ARC-007`, `L2-JSON-001`, `L2-CFG-005`, `L2-SEC-008`, `L2-CTL-006`, `L2-CTL-014`, `L2-CTL-017`.

## D07 — CLI, startup diagnostics and operator text

**Question:** Should the current flag-based CLI and fail-closed, secret-safe diagnostic contract replace broader CLI/reporting prescriptions?

**Today and difference:** Local commands use mode flags; producer submission and several job operations are HTTP APIs, not a submit CLI. Startup validates mandatory capabilities instead of producing a full optional-capability report. Validation stops at its first error; diagnostics omit some option/value/range context, use numeric errno plus dashboard labels, and display ordinary Rust errors without a traceback. Service stream routing lacks the specified severity dispatcher. Config-only validation is reserved for D12.

- **(a)** Accept and document these limits. Risk: more validation iterations, less uniform context/severity filtering and no promised CLI route equivalents or optional-capability report; secret values remain excluded.
- **(b)** Keep richer CLI, report and diagnostic requirements in the backlog. Cost: command/output contracts and tests; richer messages must not echo credentials or arbitrary unsafe text.

**Recommendation: (a).** Current commands fail closed and the user approved readable errors; convenience differences need no new runtime surface.

**Approval-needed IDs:** `L2-ENV-001`, `L2-ENV-002`, `L2-ENV-003`, `L2-XFR-004`, `L2-CFG-008`, `L2-CFG-009`, `L2-CFG-010`, `L2-CLI-001`, `L2-CLI-002`, `L2-CLI-006`, `L2-CLI-008`, `L2-CLI-009`, `L2-CLI-010`.

## D08 — Dashboard updates and event scope

**Question:** Should the dashboard remain an authenticated snapshot/SSE view rather than a general immutable event bus?

**Today and difference:** The embedded page uses admin reads and advisory/coalesced SSE changes, not GET /api/status polling. Store notifications use a trusted version callback; each SSE receiver is independent. Progress aggregates active files by job and reports a representative per-job file index, rather than identifiers on every immutable transfer event. A general subscriber panic-isolation contract is not demonstrated.

- **(a)** Accept and reword this limited trusted-callback/snapshot scope. Risk: no authoritative event history or general subscriber-failure guarantee; callback isolation evidence is not waived by accepting SSE.
- **(b)** Keep a generic typed event-bus/fault-isolation contract in the backlog. Cost: additional publication, identity, buffering and concurrency design/tests; transfers remain independent of dashboard sessions.

**Recommendation: (a).** This preserves the approved live-update design without promoting notifications into custody evidence.

**Approval-needed IDs:** `L2-DASH-001`, `L2-EVT-001`, `L2-EVT-002`, `L2-EVT-005`.

## D09 — Versioned control-plane audiences

**Question:** Should the requirements describe the approved versioned, audience-separated HTTP/HTTPS and local-control interfaces?

**Today and difference:** Binding is explicit rather than defaulted; producer jobs, private operator/control and authenticated browser routes are separate. Producer non-submission paths may return 403 to avoid disclosure. Ordinary JSON replies use length/close framing, while admin documents/assets and SSE differ. Native Rust HTTPS is already approved; the reverse-proxy prohibition and unversioned route inventory are obsolete.

- **(a)** Align the requirement wording with the approved interfaces and exceptions. Risk: callers must use the proper audience/version and cannot depend on legacy aliases or a universal all-JSON response model.
- **(b)** Keep the conflicting older interface wording as backlog contract work. Cost: unresolved release documentation and compatibility design; this does not authorize proxy deployment, a legacy adapter or unauthenticated reads.

**Recommendation: (a).** The architecture and contract were already approved; this choice reconciles wording rather than reopening TLS selection.

**Approval-needed IDs:** `L2-CTL-001`, `L2-CTL-002`, `L2-CTL-005`, `L2-CTL-010`, `L2-CTL-013`, `L2-CTL-016`.

## D10 — Interference, identity and external-loss safety

**Question:** Should the stronger identity, timeout, progress and missing-both safety obligations remain in the backlog until their scope and evidence are established?

**Today and difference:** Descriptor checks use durable identities and protected parents, not a preceding stat/compare for every open. Exact relative names replace universal realpath canonicalization. Blocking workers retain custody beyond coordinator deadlines; one claim worker or SQLite owner can still stall its queue. Missing/unprovable paths use blocked/uncertain/review handling, not a distinct immediate failed-external state. There is no privileged-writer fence or proof that a timer cancels remote effects.

- **(a)** Accept this narrower threat/progress model and reword explicitly. Risk: stronger hostile-writer, per-entry timeout/progress and external-quarantine guarantees would no longer be promised.
- **(b)** Keep the safety obligations and add threat-model, feasibility, classification and adversarial-test work to the backlog. Cost: substantial design/qualification; literal extra stats or forced timeout teardown cannot substitute for fencing. Preserve current guards, original state and exact-name rules during any work.

**Recommendation: (b).** These differences affect data-safety/security claims and should not be waived without a focused safety decision.

**Approval-needed IDs:** `L2-SEC-002`, `L2-SEC-006`, `L2-SEC-009`, `L2-SEC-010`, `L2-SEC-011`.

## D11 — Production NFS obligations

**Question:** Should NFS error, artifact, visibility and durability obligations remain pending until separately authorized target-export qualification?

**Today and difference:** Production NFS is disabled. There is no dedicated ESTALE scheduling class or complete silly-rename policy proof; numeric errno details are not retry authority. Strategy logging is incomplete. Mount/attribute observations are limited, and local fallback tests plus controlled real-export labs do not qualify actual NAS backing-storage, cross-client caches or power-loss durability. D02 can reconcile publication wording without closing these limits.

- **(a)** Limit requirements to today's local-only capability and existing lab evidence. Risk: this narrows the intended NFS release promise and cannot enable production NFS.
- **(b)** Retain phase-aware NFS classification/artifact handling and target visibility/server/export/storage qualification in the backlog. Cost: controlled target environments, hardware/fault access and separate authorization; no retry or takeover may be inferred from timeouts.
- **(c)** Approve NFS out of scope for the first release, keeping production refusal. Risk: changes the release's intended source-storage use case; later support still needs full qualification.

**Recommendation: (b).** The missing evidence and authority rules affect custody and durability; a build label or lab pass is insufficient.

**Approval-needed IDs:** `L2-NFS-004`.

## D12 — Release checks and host security integration

**Question:** Should the remaining validation, verification and host-integration obligations stay explicit backlog items rather than be waived?

**Today and difference:** Guarded --check-state opens SQLite; it is not the requested config-only preflight. The pending list also requests leftover reporting, shared config documentation, external JSON corpus/fuzzing, a separate TSan tier, manager ready/stopping/watchdog integration, target MAC/hardened shipping and endpoint-security exclusion verification. Existing helpers, candidate units and dashboard heartbeats do not establish all of these. Part B will triage the ten Open rows separately.

- **(a)** Accept current limits and reword/exclude these obligations explicitly. Risk: gives up requested deployment/security assurance and some operator diagnostics; existing safety controls and release gates remain unchanged.
- **(b)** Keep the requirements and create scoped implementation/test/qualification backlog items. Cost: tooling plus platform-specific design and local gates; manager restart must preserve blocked-worker exclusion and the original stop deadline. No feature implementation or operational policy change is authorized by this sheet.

**Recommendation: (b).** Preflight, race detection and host-security gaps need evidence and deliberate closure, not optimistic wording.

**Approval-needed IDs:** `L2-CTL-019`.

## Pending items outside the 79 approval rows

These 16 Open/Partly tested items also appear in increment170's pending list.
They belong to the same single-choice packages above but are **not** additions
to the approval-ID count. Their dispositions/evidence are unchanged; accepting
a package cannot turn missing feature/qualification evidence into a pass.

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

## Approval ID index

Every approval-needed ID appears once in this index and belongs to the same
single decision as its section's list above.

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

The first check compares the decision lists and index against the current
approval-needed rows in TRACE-L2.md, rejecting missing/extra IDs, duplicate
assignments, nonexistent decisions or differing table/section assignments.
It also verifies the supplementary pending-item IDs exist and are outside the
79-row set. It checks coverage, not the merits of any recommendation. It does
not rewrite dispositions or requirements; after user answers, subsequent PRs
must reconcile this pending index with any approved mapping changes.
