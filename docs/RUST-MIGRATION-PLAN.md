# Rust delivery plan

The current work scheduler is [ROADMAP.md](ROADMAP.md),
[RUST-FIRST-RELEASE.md](RUST-FIRST-RELEASE.md) and the finite
[release-closure matrix](RUST-RELEASE-CLOSURE.md). Approved behavior is recorded
in the API contract bundle and TRANSFER-PROTOCOL.md. Source cleanup does not
waive requirements, activate features or establish deployment readiness.

## Retained release deliverables

These milestone labels retain the broader deliverable inventory. They are not
claims of completion or instructions to reopen approved product decisions.

| Milestone | Deliverable | Required evidence |
|---|---|---|
| R0 | Scope and architecture | Approved contracts and named baseline/compatibility fixtures |
| R1 | GNU platform qualification | Pinned container inputs, target execution, explicit kernel/CPU/NFS limits |
| R2 | Dependencies and disconnected build | Audited graph/features/licenses and reproducible toolchain/sysroot inputs |
| R3 | Requirements and CI | Rust L1/L2/L3 dispositions and discovered test references, with no inherited coverage claims |
| R4 | Core/configuration/policies | Deterministic behavior and strict bounded validation |
| R5 | JSON and HTTP boundary | Independent hostile/valid corpora, framing/Unicode/duplicate-key tests and bounded fuzzing |
| R6 | Durable repository | Supported schemas, real write faults, monotonic IDs, WAL/FULL/FK, safe refusal and guarded backups |
| R7 | Filesystem effects | Descriptor-relative traversal, root binding, no-clobber, race tests and retained ownership |
| R8 | Delivery and recovery | Kill-at-phase, write/capacity failure, uncertainty/reconciliation and postcommit handling |
| R9 | Scheduling/workers/events | Bounded resources, deliberate interleavings, safe shutdown and nonauthoritative observations |
| R10 | REST and bounded reads | Approved wire/status/error/auth contracts and hostile-client tests |
| R11 | Service lifecycle | Exact process/account/systemd/confinement and original-state recovery evidence |
| R12 | Admin dashboard | Self-contained assets, XSS/CSRF/session controls and approved operator workflows |
| R13 | Packaging and qualification | Disconnected installation/build, notices, pinned userspace and finite controlled NFS evidence |
| R14 | Release cutover | Qualified artifacts, usable compatible rollback and complete operator/producer/consumer docs |

## Invariants and qualification

- Keep one Rust executable/configuration/service with the approved crate/process
  boundaries. Supervised child processes cannot make stuck NFS I/O cancellable.
- Keep local SQLite ownership, short WAL/FULL/FK transactions, bounded queues and
  capacity. A canceled waiter is not cancellation of a started transaction.
- Preserve original state, custody, enrollment, file indices, immutable manifests,
  receipts and high-water marks across supported upgrades; refuse unsupported
  schemas/identity capabilities before payload access. Never reset a nonempty
  database or restore stale state over newer custody.
- Use controlled independent fixtures for crashes, partial effects, missing data,
  collisions, ambiguous outcomes and corruption. Never compare services against
  the same production recording trees or databases.
- Preserve descriptor-relative traversal, strict paths and regular files,
  explicit no-clobber publication, qualified fallbacks, native error handling
  and actual directory synchronization. Atomic rename is not durable commitment.
- Preserve 3N logical data I/O: source hash during copying, then destination
  staging reread and verification. No separate source prehash. Manifest/cleanup
  ordering, source immutability and uncertainty rules stay in the protocol.
- Test hostile JSON/HTTP inputs, bounded buffering/admission/timeouts, Unicode,
  numeric exactness, duplicate assertions, serialization, and actual security
  boundaries. Add deterministic concurrency and phase interruption tests.
- Run both cargo-libc/SLES modes for changed Rust/build inputs, independent ELF
  and relocation audits, exact target tests, and affected native/NFS/systemd
  qualification. Host-only unit tests and simulated faults are insufficient.
- Audit dependency graph, features, licenses/notices, package provenance and
  offline prerequisites. Cargo source vendoring alone does not provide the
  compiler, target sysroot or native requirements.
- Measure throughput, submission/status latency, resources and recovery against
  named controlled Rust workloads; record limits during prolonged NFS stalls.
  A coverage percentage cannot replace crash/failure or native storage tests.
- Complete Rust requirement/test discovery under P10/RC-23, including inspection,
  analysis, demonstrations and explicit unqualified dispositions.

## Operator cutover and rollback

Rehearse on copied test state/recordings under qualified exclusion: stop
admission, drain, confirm old workers exit, preserve a consistent WAL-aware
backup, install a qualified compatible artifact and verify original-state
recovery. Prove incompatible launch refusal and declare exact supported
upgrade/rollback paths. A previous binary is not a rollback candidate merely
because it exists. Preserve filesystem/state correspondence; never restore an
old database over moves already performed.

Release requires the final artifact, complete guides and all eight release
gates. Source cleanup and a main merge do not authorize deployment, conversion,
automatic cleanup, production NFS or source deletion. Current schema migration
apply and UUID/manifest-v2 activation remain disabled.

See [the dependency pins](DEPENDENCY-QUALIFICATION.md),
[license policy](LICENSE-POLICY.md), [integrity design](INTEGRITY-DESIGN.md),
[offline installation](OFFLINE-INSTALL.md) and
[restart runbook](RUST-RESTART-RUNBOOK.md).
