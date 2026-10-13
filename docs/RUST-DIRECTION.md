# Rust direction and next-session handoff

Recorded 2026-10-13 on `feature/rust-transfer-coordinator`. The user supplied
[CONVERSATION.md](../CONVERSATION.md) as the new direction. This supersedes the
earlier same-filesystem-only release scope and component-for-component port.
Preserve the conversation as design input; its claims about existing defects
are review leads, not verified findings merely because they appear there.

## Intended architecture

Design a durable transfer coordinator using Rust ownership, explicit effects,
bounded resources and established libraries. Preserve useful requirements and
crash/fault evidence without copying C++ internal architecture or temporary scope
restrictions. Use one executable, configuration file and systemd service.

The proposed architecture has an asynchronous coordinator, one scheduler state
owner, a dedicated local SQLite owner thread, bounded command/result channels,
and supervised filesystem workers as child processes of the same executable in
an internal worker mode. Reserve claim/reconciliation capacity. Coalesce progress
without starving durable acknowledgements. Process isolation cannot make stuck
NFS calls reliably cancellable: bound replacement workers and reconcile/fence
uncertain assignments before redispatch.

Four proposed crates have meaningful boundaries: `mover-core` for pure decisions,
`mover-store` for SQLite, `mover-fs` for filesystem effects, and `file-mover` for
API/coordination/operations. Use narrow fault-injection interfaces, not a generic
backend framework. A future object-storage protocol would have different semantics.

## Proposed protocol for review

[TRANSFER-PROTOCOL.md](TRANSFER-PROTOCOL.md) defines claim custody, copied-file
evidence, manifest commitment, cleanup authorization and crash reconciliation.
[REST-API-DRAFT.md](REST-API-DRAFT.md) proposes the producer submission/status
contract. Review the API and producer/consumer handoff before freezing the design.

- Separate durable `Accepted` from confirmed `Claimed`. Producer source-path reuse
  is allowed only after claim confirmation. Require completed files, closed writers,
  explicit handoff and idempotent submission; pathname changes do not stop writers.
- Record intent before effects, claim into a private source-filesystem namespace,
  copy into exclusively owned destination staging, verify, publish without clobber,
  commit the recording set, then authorize source cleanup.
- Publish an immutable completion manifest carrying file identities, sizes and
  integrity evidence. Consumers must honor it. Per-file publication is not an atomic
  transaction spanning a recording set, SQLite and multiple filesystems.
- Model applied, not-applied and uncertain/partially applied outcomes. Recovery
  requires operation ownership and content evidence, not merely an existing name.
  Cleanup requires a validated publication receipt.
- Keep local SQLite ownership, short WAL/FULL/foreign-key transactions, durable
  operation records and tested migrations. Assign disjoint source ownership across
  instances; local databases are not a distributed queue or fencing mechanism.
- Enforce approved roots/relative paths, descriptor-relative traversal, regular
  files, private namespaces, mount identity and qualified no-clobber capabilities.
  Do not require openat2 or newer-kernel-only facilities.

**Agreed integrity plan:** calculate the source hash during copying, then reread
destination staging and compare its hash/size before publication and cleanup.
The normal path is 3N logical data I/O: source read + destination write + destination
reread. A 100 GB file copies 100 GB of payload and accounts for roughly 300 GB of
logical I/O, not 300 GB necessarily crossing the network. There is no separate
source prehash pass. Persist the completed digest after copying and retain the
claimed source for interruption recovery. See [INTEGRITY-DESIGN.md](INTEGRITY-DESIGN.md)
for sequencing, source immutability, recovery and the future S3 checksum distinction.
Two workers and 4 MiB buffers are benchmark suggestions, not production decisions.
Resumable chunks and optimized copy paths follow a correct retained-source baseline.

## Packages and deployment

E1–E5 qualify exact configurations of bundled rusqlite/SQLite, rustix, Serde/JSON,
httparse and Tokio. Tokio retains signal-hook-registry transitively. The broader
conversation proposes Axum/Tower/Tower HTTP, sha2, thiserror, tracing/subscriber,
clap, uuid, sd-notify and rust-ini. These and proposed development tools are
candidates, not qualified dependencies. Review features, graphs and licenses.
Axum would replace the application-maintained HTTP surface; preserve E4 framing
evidence and strict JSON/API tests when framework extractors are introduced.
Use [DASHBOARD-DESIGN-NOTES.md](DASHBOARD-DESIGN-NOTES.md) for the offline/security
requirements and status-query/polling findings when designing the operator UI.

Retain x86_64 GNU/glibc 2.22, baseline CPU settings, no musl, modern controlled
builds and pinned SLES-equivalent container validation. The user's builder remains
unqualified; cargo-zigbuild is the reference. The conversation's actual-host test
suggestion does not override the user's explicit container-only preference.
Preserve the [NFS fixture note](NFS-TEST-FIXTURE.md). Old kernel/CPU and storage
durability coverage remain limited. Disconnected builds need toolchain/targets,
native prerequisites and notices as well as vendored Cargo sources.
Use [INTEGRATION-DESIGN-NOTES.md](INTEGRATION-DESIGN-NOTES.md) for deployment
checks, confinement gaps and fail-closed harness requirements.

## Resume here

Experiments are stopped at the user's request. E6/thiserror is **unrun** and must
not automatically be next. No production Rust implementation has started. The
earlier fifteen milestones retain useful obligations but need scope/sequence revision.

Next session: read this handoff, the protocol/API drafts, CONVERSATION.md,
experiment results and the branch [review](BRANCH-REVIEW.md). Work through the
producer-facing Accepted/Claimed contract, reconcile requirements and refine
the proposed protocol using the agreed streaming-hash/destination-reread plan.
Revise the roadmap around four increments:

1. Core protocol, durable evidence and local persistence.
2. One recoverable cross-filesystem transfer with deletion disabled initially.
3. Gated cleanup, manifests, admission, worker isolation and operational diagnostics.
4. Measured optimization, then optional resumption/copy fast paths/dashboard work.

Start on the feature branch. Do not automatically resume experiments or start a
line-for-line port. Preserve branch work as reference before any cleanup. During
cutover, old and new daemons must not manipulate the same source namespace.
