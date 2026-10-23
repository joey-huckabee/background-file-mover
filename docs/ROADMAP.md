# Roadmap

This file contains future work and unresolved decisions for the Rust transfer
coordinator. Remove tasks when they are complete; keep implementation evidence
in the result documents, changelog and trace matrix.

## First-release finish line

Work on `feature/rust-transfer-coordinator`. Use the
[first-release checklist](RUST-FIRST-RELEASE.md) and
[release-closure matrix](RUST-RELEASE-CLOSURE.md) as the work scheduler. All eight
FR gates require closure; each qualification package must name its finite RC
cells, expected outcomes and retained evidence before execution. Do not select
another NFS experiment merely because more combinations are possible.

## Next work

Read [the shutdown handoff](REST-CONTRACT-HANDOFF.md) before resuming. Next resolve
request equivalence/file ordering and remaining ID/schema details before OpenAPI.

- [ ] Complete remaining request/schema and persisted-state decisions and execute
  [API-I01-06](REST-ERROR-SCENARIOS.md) within P01/P02/P03. Preserve the approved
  error mappings, envelope and retry timing (groups 1-15). Current missing-file
  behavior remains 503 until implementation; do not mistake approval for runtime
  support. Cover every API-E01-70 disposition and preserve original custody.
  Replace the unused Rust producer format directly; no old-wire adapter or
  deprecation work is required. Encode approved expected_sizes_bytes all-or-nothing
  and default-disabled checking, including ignored complete maps when off.
  Use current configuration for existing unfinished size checks, without per-job
  setting snapshots. Finalize config/replay ordering without discarding custody
  evidence or confirmed handoff. Qualify API-E61-70 and document SC-139/140.

- [ ] P01: Freeze versioned OpenAPI, manifest validation and supported route,
  retry/error, ID-retention, encoding/path and metadata contracts. Reconcile
  draft-only features against active requirements without silently dropping them.
- [ ] P02-03: Implement protected producer ingress/caller binding and the selected
  authenticated remote proxy; complete RA-01-16. Keep registration deferred.
- [ ] P04: Persist allocation intent/receipts for claim-private, recording,
  payload-staging and manifest-staging objects. Qualify crash boundaries and
  conservative ambiguous/foreign refusal; offline repair stays deferred.
- [ ] P05: Close the finite NFS matrix using exact existing evidence first.
  Resolve actual mount inventory and blocked RPC/server-durability capability
  decisions. Preserve owned delayed-effect reconciliation/refusal; no timeout or
  local guard release proves settlement. Keep production NFS disabled.
- [ ] P06-07: Close remaining capacity and shipping-profile lifecycle cells;
  preserve existing-job retries, bounded queues/workers, default-off admission,
  configurable default-60 shutdown and exclusion through actual worker exit.
- [ ] P08: Implement independently recoverable postcommit source cleanup after
  its safety prerequisites pass. Require job policy/current authorization and
  verified receipts; default off, production deletion still disabled.
- [ ] P09: Deliver shipping package/unit/account/confinement, disconnected build,
  provisioning and state-preserving upgrade/rollback/cutover procedures.
- [ ] P10-11: Complete Rust L1/L2/L3/test traceability and DOC-01-05 user guides;
  maintain them alongside implementation, separate from historical C++ evidence.
- [ ] P12: Rehearse the exact candidate, rerun both required SLES gates and close
  every FR gate before proposing production authorization or release.

Resolve D01-05 from the closure review when their packages approach: mount
inventory, proxy package/account, supported manager/kernel/container profile,
unproven durability/server faults, and compatible rollback/cutover. Keep testing
container-only; do not add a real SLES installation requirement. Equivalent-228
results do not prove exact vendor-maintenance packages or physical NAS behavior.
Unreproducible required faults remain blocked pending an explicit disposition.

The sections below preserve broader future obligations and unresolved design
items. P01/P10 must reconcile their requirement scope with FR-01-08; a mention
here neither adds an automatic release prerequisite nor withdraws one. Optional
adapters/repair/UI and cross-host authority remain deferred. Experiments E1-E5
stay stopped; do not automatically start E6. Every Rust build/test must use the
[SLES gate](RUST-SLES-GATE.md), not host-only cargo tests. Retain the opt-in NFS
qualification capability permanently.

## Design decisions

- [ ] Finalize bounded POST handoff waits and exact retry/backoff timing; implement
  agreed temporary retry versus stop/log handling for correction/review errors
  for the agreed 202-after-all-claims recorder workflow; settle idempotency retention
  and control semantics, then produce OpenAPI.
- [ ] Derive L2/L3 and Rust tests for generator identity/source-directory/file-name
  submission, configured destination routing, pinned route replay and caller binding
  from the additive requirements in [L1-REQ.md](L1-REQ.md).
- [ ] Derive claim-size evidence and tests for omitted/expected/zero/mismatched
  sizes, explicit subfolder paths, symlink/mount escape and directory preservation.
- [ ] Implement optional generator grouping and pinned layout replay; validate
  generator path components and filesystem/S3-prefix collision behavior.
- [ ] Implement configurable postcommit source cleanup, including recorded job
  policy/current startup authorization, retained-source accounting and independent
  cleanup retries. Keep initial development profiles deletion-disabled.
- [ ] Add timer-driven missing-file retries, clock-anomaly diagnostics and bounded backoff.
- [ ] Complete remaining [source-space acceptance evidence](SOURCE-SPACE-ADMISSION-DESIGN.md):
  physical-disk/quota/inode and external-write races, broader concurrent queue
  flooding and actual hard-NFS statistics interruptions/export
  changes. Preserve default-off configuration, accepted-key recovery and existing
  limits. Do not promote the protected-local slice to production NFS support.
- [ ] Validate the protocol's applied/not-applied/uncertain outcome model and
  ownership evidence against partial claims, publication and stale worker effects.
- [ ] Finalize the versioned completion manifest schema and validation under the
  confirmed consumer wait-for-COMMITTED.json contract; settle filename encoding,
  metadata policy and downstream retention through source cleanup.
- [ ] Design one scheduler state owner, a dedicated local SQLite owner and bounded
  command/result channels. Prioritize claims/reconciliation and coalesce progress
  without starving durable acknowledgements.
- [ ] Extend payload supervision with durable assignments for remaining effects,
  per-endpoint admission budgets, worker replacement limits and uncertain-assignment
  fencing. Define behavior when a hard-mounted NFS operation does not return.
- [ ] Define integrity-policy details around streamed hashing and destination
  verification, identifiers, schema, naming/collision
  behavior, manifests and root-ID/relative-path API boundaries.
- [ ] Reconcile requirement IDs and scope annotations for the redesigned service.
  Explicitly implement, revise or withdraw requirements rather than silently
  treating historical tests or deferred annotations as Rust evidence.

## Build and deployment constraints

Target x86_64 GNU/Linux with glibc 2.22 and conservative CPU settings. Use a
modern controlled build host, no musl, and existing target runtime libraries.
Qualify in pinned SLES 12 SP5-equivalent containers; an actual SLES host is not
required. Containers share the runner kernel and CPU, so document unexercised
platform behavior and use targeted unsupported-syscall tests.

- [ ] Qualify the user's build project, including target selection, native SQLite
  compiler forwarding and artifact provenance.
- [ ] Expand the workspace as effect crates are needed, with locked dependency/features policy,
  licensing/notices and reproducible offline builds. Package toolchain, targets
  and native prerequisites as well as vendored Cargo sources.
- [ ] Require production ELF/interpreter/library audits and execution of the same
  artifact in the pinned userspace after dependency, feature or compiler changes.
- [ ] Define compatible systemd-enabled and RHEL 9 container variants, MAC policy
  coverage, CPU-baseline coverage and controlled NFS failure tests. Reuse the
  [NFS fixture](NFS-TEST-FIXTURE.md) where appropriate and state durability limits.

## Implementation milestones

Use short tested increments above to develop portions of these release milestones.
Do not wait for every milestone's design before starting independent core work.
Each milestone must deliver
its required behavior and appropriate failure-boundary evidence before release.
The intended increments are core protocol/persistence; a recoverable transfer
with deletion disabled; gated cleanup/production operation; measured optimization.

| Milestone | Future deliverable | Completion gate |
|---|---|---|
| R0 | Requirements and protocol decisions | Accepted/Claimed semantics, streaming-hash evidence timing, recovery model and architecture agreed |
| R1 | Platform and isolation qualification | User's builder, container contract, filesystem capabilities and blocked-worker policy qualified |
| R2 | Workspace and offline build foundation | Four-crate boundaries, locked minimal features, reviewed licenses and reproducible disconnected build |
| R3 | Rust requirements evidence and CI | Separate Rust traceability, meaningful line/branch coverage, fault-injection and production-target gates |
| R4 | Core types, configuration and policies | Pure transitions, idempotency, naming, root/path rules and validation tests |
| R5 | API and serialization boundaries | Framework/strictness decisions, bounded input and hostile JSON/HTTP/IPC/manifest tests |
| R6 | Durable repository extensions | Filesystem-operation evidence, tested migrations, async integration and additional crash/write-failure coverage |
| R7 | Filesystem boundary and capabilities | Descriptor-relative safety, source claims, mount checks, exclusive staging and no-clobber strategies |
| R8 | Transfer protocol and recovery | Cross-filesystem copy/verification/publication and crash reconciliation, initially without source deletion |
| R9 | Scheduling and worker supervision | Bounded tasks/queues/processes, retry/control semantics, progress isolation and safe draining |
| R10 | REST commands and read API | Acceptance/claim visibility, idempotency, paginated queries and responsive hostile-client behavior |
| R11 | Daemon and systemd lifecycle | Ordered startup/stop, singleton ownership, readiness/watchdog and genuine lifecycle failure tests |
| R12 | Recording completion, cleanup and operator workflows | Manifest-gated consumption, authorized cleanup, offline UI and safe filename rendering |
| R13 | Packaging and operational qualification | Compatible container deployment, actual confinement checks, NFS failure evidence and operational diagnostics |
| R14 | Cutover, documentation and retirement | Migration/rollback rehearsal, source-namespace ownership, current docs and archived reference implementations |

SQLite/filesystem operations must stay outside Tokio's executor and manager
locks. Bound admission as well as thread count. Stop admission and drain started
work before runtime teardown; task abort and timeout do not cancel a running
blocking operation. Protect authoritative state from observer/logging failures.

## Dependency qualification when resumed

Choose packages for the agreed architecture and qualify only the required
features. Do not treat candidate names as compatibility approval.

- [ ] Decide whether to adopt thiserror; if requested, qualify representative
  phase-sensitive errors, chaining, host macros and the cumulative target artifact.
- [ ] Evaluate Axum/Tower/Tower HTTP for the API while retaining strict input,
  duplicate-field, framing and resource-limit tests.
- [ ] Evaluate integrity, diagnostics, CLI, identifier, systemd and INI candidates
  against the protocol and existing interfaces; review their full graphs/licenses.
- [ ] Requalify affected configurations when production runtime or worker
  supervision needs features beyond the selected minimal settings.

## Release and operational obligations

- [ ] Build a crash/fault matrix around durable intent, claiming, writes, sync,
  verification, publication, recording manifests and source deletion. Test entry
  swaps, collisions, missing paths, interrupted link/unlink and recovery ambiguity.
- [ ] Expand migration qualification using retained released databases, interrupted
  upgrades and an independently fenced backup/rollback procedure. Remove destructive
  delete-and-restart advice for databases protecting recordings.
- [ ] Measure meaningful branch coverage and justify real uncovered failure paths;
  distinguish compiler artifacts from untested behavior before setting gates.
- [ ] Test service accounts, path permissions, configuration/start failures,
  lifecycle reuse, active-work shutdown and systemd sandboxing. Prove dedicated
  SELinux/AppArmor confinement rather than inferring it from an empty denial log.
  Apply the integration design notes and verify harness failure propagation before
  relying on these checks as CI gates.
- [ ] Set managed write paths, document endpoint/security-tool exclusions and
  detect disappeared NFS mounts. Distinguish liveness, readiness, storage health
  and transfer progress; avoid restart loops and unbounded worker replacements.
- [ ] Bound status-query memory and UI requests at their actual allocation/admission
  boundaries. Keep offline assets and DOM text insertion safe for hostile filenames.
  Apply [DASHBOARD-DESIGN-NOTES.md](DASHBOARD-DESIGN-NOTES.md) during API/UI design.
- [ ] Add structured phase diagnostics and bounded-cardinality metrics for backlog,
  blocked workers, throughput, sync/commit latency and pending cleanup.
- [ ] Rewrite architecture, configuration, CLI, logging, deployment, user,
  feature-interaction, maintainer and 12-factor documentation as the Rust contracts
  settle. Keep deployment artifacts and documentation under relevant CI checks.
- [ ] Rehearse cutover and rollback with durable state and transfer ownership.
  Prevent old and new daemons from manipulating the same source namespace.

## Optional backlog requiring a scope decision

Registration/token authentication is explicitly deferred. If separately scheduled,
implement the selected one-time generator setup key, issuance recovery,
rotation/operator roles and restricted tokenless profiles from the registration
draft before enabling those options. The first remote profile instead requires
implementation and qualification of the [authenticated proxy contract](REMOTE-API-ACCESS-CONTRACT.md).
Preserve approved source/path mapping and deployment trust boundaries; registration
does not gate independent core/storage/local or authenticated-proxy increments.

Prioritize these after a correct recoverable transfer baseline; none implicitly
changes the integrity or source-retention guarantees.

- Durable resumable chunks with validated retained prefixes and synchronized checkpoints.
- Measured copy/buffer/concurrency optimization, kernel-copy fallbacks and bandwidth limits.
- Per-job policy overrides constrained by system policy, size limits and free-space margins.
- Versioned destination collision policy that retains existing data without overwriting.
- Claim-directory cleanup and explicit handling of unexpected leftover files.
- Manual retry/reconciliation tools, offline database inspection and durable audit timelines.
- Advanced priorities and storage-endpoint scheduling budgets.
- Qualify S3 delivery behind the generator contract: dependencies/target compatibility,
  multipart ownership, checksum evidence, conditional publication and cleanup receipts.
  Multi-host takeover requires explicit distributed ownership/fencing.
- Directory/filename-filter submission, alternative spool transport and additional
  platform support only with explicit contracts and qualification.
