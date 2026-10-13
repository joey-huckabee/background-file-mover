# Roadmap

This file contains future work and unresolved decisions for the Rust transfer
coordinator. Remove tasks when they are complete; keep implementation evidence
in the result documents, changelog and trace matrix.

## Next work

Work on `feature/rust-transfer-coordinator`. Read
[RUST-DIRECTION.md](RUST-DIRECTION.md) and [CONVERSATION.md](../CONVERSATION.md)
before implementation.

- [ ] Reconcile the requirements with claiming, cross-filesystem transfers,
  recording-set completion manifests and supervised worker processes.
- [ ] Review the proposed [transfer protocol](TRANSFER-PROTOCOL.md) and
  [REST contract](REST-API-DRAFT.md) with the producer/consumer workflow; settle
  acknowledgement, handoff, naming and retention contracts before Rust code.
- [ ] Derive schema, transition definitions and the fault matrix from the protocol.
  Implement streamed source hashing and destination reread verification using
  [INTEGRITY-DESIGN.md](INTEGRITY-DESIGN.md).
- [ ] Revise the detailed milestone schedule in
  [RUST-MIGRATION-PLAN.md](RUST-MIGRATION-PLAN.md) around the agreed protocol.
- [ ] Decide which dashboard and integration scenarios to reuse from
  [DASHBOARD-DESIGN-NOTES.md](DASHBOARD-DESIGN-NOTES.md) and
  [INTEGRATION-DESIGN-NOTES.md](INTEGRATION-DESIGN-NOTES.md).

Experiments remain paused. Do not automatically start E6 or another package
experiment, or begin a component-for-component port.

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
- [ ] Implement preserved recording hierarchies with safe destination-parent
  creation/synchronization, manifest paths and prefix/reserved-name collision tests.
- [ ] Implement optional generator grouping and pinned layout replay; validate
  generator path components and filesystem/S3-prefix collision behavior.
- [ ] Implement configurable postcommit source cleanup, including recorded job
  policy/current startup authorization, retained-source accounting and independent
  cleanup retries. Keep initial development profiles deletion-disabled.
- [ ] Implement the configurable five-minute default and persistent retry windows,
  operator review/resume, retained partial claims and non-202 blocked responses.
- [ ] Define durable pending job/byte limits and source-space margins for handoff
  during destination outages; test partial claims, admission refusal and restart
  reservation reconciliation without deleting retained source data.
- [ ] Validate the protocol's applied/not-applied/uncertain outcome model and
  ownership evidence against partial claims, publication and stale worker effects.
- [ ] Finalize the versioned completion manifest schema and validation under the
  confirmed consumer wait-for-COMMITTED.json contract; settle filename encoding,
  metadata policy and downstream retention through source cleanup.
- [ ] Design one scheduler state owner, a dedicated local SQLite owner and bounded
  command/result channels. Prioritize claims/reconciliation and coalesce progress
  without starving durable acknowledgements.
- [ ] Specify supervised filesystem worker processes, private IPC, per-endpoint
  admission budgets, worker replacement limits and uncertain-assignment fencing.
  Define behavior when a hard-mounted NFS operation does not return.
- [ ] Define integrity-policy details around streamed hashing and destination
  verification, identifiers, schema, naming/collision
  behavior, manifests and root-ID/relative-path API boundaries.
- [ ] Decide authentication/authorization before non-loopback deployment; preserve
  application-level restrictions to approved roots and permitted operations.
- [ ] Finalize the registration/access draft: approved path mapping for shared NFS,
  scoped enrollment bootstrap, issuance recovery, token rotation, operator roles
  and independently restricted local/remote tokenless profiles.
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
- [ ] Establish the production workspace, locked dependency/features policy,
  licensing/notices and reproducible offline builds. Package toolchain, targets
  and native prerequisites as well as vendored Cargo sources.
- [ ] Require production ELF/interpreter/library audits and execution of the same
  artifact in the pinned userspace after dependency, feature or compiler changes.
- [ ] Define compatible systemd-enabled and RHEL 9 container variants, MAC policy
  coverage, CPU-baseline coverage and controlled NFS failure tests. Reuse the
  [NFS fixture](NFS-TEST-FIXTURE.md) where appropriate and state durability limits.

## Implementation milestones

Finalize the scope and order during protocol design. Each milestone must deliver
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
| R6 | Local durable repository | Dedicated owner, durable job/file/operation evidence, migrations and real write-failure tests |
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
- [ ] Implement tested schema migrations against retained database fixtures.
  Remove destructive delete-and-restart advice for databases protecting recordings.
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
