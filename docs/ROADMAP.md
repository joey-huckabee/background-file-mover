# Roadmap

This file contains future work and unresolved decisions for the Rust transfer
coordinator. Remove tasks when they are complete; keep implementation evidence
in the result documents, changelog and trace matrix.

## First-release finish line

Use [the first-release checklist](RUST-FIRST-RELEASE.md) to prioritize the eight
open release gates. The sections below retain broader future obligations; they
are not all prerequisites for the first release. Do not use increment counts as
release progress. Deferred capabilities remain deferred unless explicitly added.

Next qualify remaining NFS operation/synchronization and shutdown boundaries,
remaining endpoint-failure directions/phases beyond selected source-copy
interruptions, remaining fresh/later source bootstrap and destination recovery
phases, native SLES manager/cgroup compatibility, actual account control/persistent
deployment and remaining hard-NFS/systemd operation/deadline behavior (SH-01–04/06–14). Preserve independently retained
exclusion through actual worker exit; local ownership observations alone cannot
authorize uncertain-effect redispatch or prove remote settlement.
Keep delayed NFS
operations/reconciliation, actual mount/version/security discovery, same/separate
shares and remaining systemd lifecycle qualification open (SH-10–14); a free local lock or
a timeout is not remote-settlement proof. No NAS-admin fencing facility is assumed
for this restricted profile. Keep stronger cross-host/re-enrollment controls deferred.
Select the proxy package and implement/qualify the [remote access design](REMOTE-API-ACCESS-CONTRACT.md),
RA-01–16, alongside remaining FR-01 details and FR-02 capacity cases. Keep
registration deferred, existing-job recovery intact and production NFS/deletion off.

Declare the supported manager/package and kernel profile and qualify its
remaining deployment behavior. Exact SLES-maintenance RPM patches remain
untested by the approved equivalent-228 lab; do not infer them from version
labels or compiled directive names. Complete actual account control, persistent
deployment and remaining hard-NFS lifecycle phase/deadline evidence. Keep testing container-only,
with no real SLES installation requirement, and maintain the
[testing limitations](TESTING-LIMITATIONS.md) and [lab procedure](SYSTEMD-LIFECYCLE-LAB.md).
Preserve unit-scoped shutdown when packaging: a rejected contender must not run
a global stop controller against the legitimate owner. Qualify the shipping
unit's account, restart and timeout behavior for the declared supported profile.
Define and qualify remaining shipping-unit restart/recovery policy across other
hard-NFS phases, longer outages and endurance, including supported operator
intervention. Retain conservative ownership when unit MainPID is zero or the
unit is failed while an old worker remains alive.

## Next work

Work on `feature/rust-transfer-coordinator`. Read
[RUST-DIRECTION.md](RUST-DIRECTION.md) and [CONVERSATION.md](../CONVERSATION.md)
before implementation.

- [ ] Qualify remaining buffered NMP-41B bootstrap/claim/publication/manifest
  interruption/death/RPC and synchronization boundaries, plus untested
  copy/verification endpoint directions, cache/size/load and outage-duration cases.
  Retain noac NMP-41N evidence separately. Keep production NFS/deletion disabled.
- [ ] Qualify remaining claim/namespace and synchronization RPC reply-loss boundaries
  in the declared shipping mount/export profile; do not substitute buffered OS
  controls for unobserved service COMMIT/fsync boundaries. Cover
  server recovery and delayed-effect settlement, remaining
  synchronization boundaries, outages beyond the selected three-minute cases,
  concurrent queue flooding and export changes.
- [ ] Complete the producer/consumer guides, restart/shutdown troubleshooting and
  deployment matrix tracked by [RUST-SCENARIOS.md](RUST-SCENARIOS.md)
  (DOC-01/02/04/05); keep future adapter/repair guides (DOC-06) deferred. Maintain
  the [operator guide](RUST-OPERATOR-GUIDE.md) as behavior changes. Update the
  scenario catalog with each increment, including success, retry, review and
  recovery situations, actual evidence and remaining documentation obligations.
- [ ] Qualify enrollment against block-device/quota exhaustion, server I/O errors,
  in-flight synchronization RPCs and power loss. Preserve conservative review for
  ambiguous creation; use [the enrollment contract](FENCED-ENROLLMENT-DESIGN.md).
- [ ] Select and qualify an independently enforced fence before implementing
  populated/legacy-state re-enrollment or legitimate changes to strict observed
  pins. Preserve original job/route evidence. Complete authenticated export/root
  identity qualification; copied markers/observations are not global authority.
- [ ] Complete remaining SH-01–04/06–14 for the confirmed same-host/local-state
  profile: remaining guard/storage/death-phase cases, deployment persistence and
  mount/account policy, remaining bounded-shutdown cases,
  native SLES systemd/cgroups, account/persistence and combined hard-NFS lifecycle,
  actual NFS mount/root validation and delayed-effect owned
  recovery/refusal. Preserve the NF scope mapping; cross-host exclusion/fencer
  integration and takeover/re-enrollment remain deferred. No guard-release or
  fixed-wait shortcut for uncertain storage effects.
- [ ] Define and qualify worker-health/stall and lost-coordinator diagnostics
  beyond existing assignment/channel/shutdown limits. Preserve bounded workers,
  termination requests and confirmed-exit exclusion; a worker blocked in the
  kernel cannot execute a self-timeout, and uncertainty cannot authorize retry
  or replacement. Keep orphan killing/adoption out of unserved local control.
- [ ] Extend diagnostics to remaining root/traversal metadata failures and
  logical custody/integrity refusals.
- [ ] Extend retry classification beyond confirmed payload-copy ENOSPC; decide
  configurable/jittered intervals and longer capacity waits with retained-attempt
  accounting. Qualify block-device/quota free-space margins and admission during
  destination shortages; use [the retry policy](DELIVERY-RETRY-POLICY.md).
- [ ] Implement configurable gated source cleanup only after worker/filesystem
  failure qualification passes.
- [ ] Deferred: offline custody/orphan inspection and explicit repair tooling.
  Use worker/NFS failure evidence to determine what operators need. Preserve
  [RETENTION-REPAIR-DESIGN.md](RETENTION-REPAIR-DESIGN.md) for prerequisites;
  allocation ownership and fencing still precede any repair effects.
- [ ] Derive L2/L3 and Rust traceability alongside each increment. Refine protocol,
  schema and fault cases before the dependent effect, not before all Rust code.
- [ ] Extend acceptance persistence for API metadata, future schema migrations,
  bounded async integration and crash/power-loss evidence as effects are introduced.
- [ ] Extend the local claim slice for production: persisted namespace-allocation
  intent/orphan reconciliation, stable instance/root/mount authorization, filesystem
  capability qualification across the supported endpoint configurations.
  Qualify process supervision/fencing before remote claims; do not enable NFS yet.
- [ ] Decide which dashboard and integration scenarios to reuse from
  [DASHBOARD-DESIGN-NOTES.md](DASHBOARD-DESIGN-NOTES.md) and
  [INTEGRATION-DESIGN-NOTES.md](INTEGRATION-DESIGN-NOTES.md).

Experiments remain paused. Do not automatically start E6 or another package
experiment, or begin a component-for-component port.

Every incremental build/test must pass [the SLES gate](RUST-SLES-GATE.md) using
cargo-zigbuild for glibc 2.22, ELF audits and exact target test execution. Host-only
passes are insufficient; keep this gate as SQLite/effects/dependencies are added.

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
