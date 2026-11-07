# Recording filesystem sessions

Automatic delivery now keeps one supervised child alive for one recording.
The child opens and holds the destination namespace lock and performs destination
availability checks, initial staging/hierarchy allocation, new-attempt allocation,
copying/hashing, independent staging verification, publication, published-file
custody checks and every manifest allocation/write/verification/publication or
committed-manifest verification step. The parent performs database operations,
pure protocol decisions and exact manifest construction; no runtime destination
filesystem access remains on the delivery coordinator thread.

This closes the runtime filesystem gaps from increment 12 without passing lock
descriptors back from a child or introducing another dependency. One delivery
session plus one claim child remain the maximum simultaneous filesystem workers.
Both inherit the protected source namespace's locked open description. The
delivery child acquires its own destination lock, keeping destination opens and
lock validation out of the parent. Source observation/allocation/claiming still
use claim children. Handoff and replay now validate source root/namespace custody
in a child, without opening producer paths that were released after 202.

## Commands, receipts and interruption

The internal session mode uses a private Unix socket with four-byte big-endian
length framing and strict Serde requests/replies. Version 1 and monotonically
increasing session sequence numbers are required; stale/missing sequences fail
closed. At most 2,048 commands are allowed per session, sufficient for the bounded
256-file recording. Ordinary requests and all replies are capped at 32 KiB;
manifest requests allow 384 KiB for the existing 128 KiB manifest and JSON escaping.
Manifest replies return only phase, digest and object identity; the parent retains
the exact intent bytes, keeping reply size independent of document length.
Oversized frame lengths are rejected before allocation. No payload file bytes
cross IPC. These are trusted local implementation interfaces, not public REST
contracts or an OS sandbox.

Capacity is checked before staging or restart allocation. Allocation receipts
are saved before copying; copied, verified and publication receipts are saved
between dependent effects. Manifest intent is durable before allocation, its
actual allocated identity is saved before writing, written identity before
verification, and publication intent before the final rename. The parent checks
immutable assignment context and receipt phases; SQLite validates adjacent
transitions and object ownership. Completed manifest bytes remain exactly the
same version-1 serialization as the reference path. The payload integrity path
remains 3N, without source prehashing.

The child validates source namespace and destination lock custody before and
after each command. Parent reads poll with a short socket timeout to observe
shutdown or child exit; that timeout does not limit filesystem work or authorize
redispatch. The common supervisor requests termination and waits for confirmed
exit, including after IPC errors. A child stuck in a kernel call can delay
shutdown indefinitely. On coordinator death, the socket closes; an idle child
exits, while an in-flight effect retains its locks until the child exits. No
replacement is permitted based only on a signal or elapsed deadline.

Allocation gaps are preserved: a directory/staging file created before its
receipt cannot be adopted merely by name. Old partial staging is retained when
allocating a new attempt. No source deletion, staging reclamation, orphan repair
or filesystem fallback is added.

## Qualification boundary

The source singleton lock and local state database still open during daemon
startup. Source-lock bootstrap must be qualified separately, especially with an
unavailable mount; runtime isolation does not establish bounded startup. The
stopped-daemon reference CLI and reference filesystem coordinator remain inline.
NFS is still rejected by the local filesystem capability checks. Stable instance/
root/export authorization, durable allocation intents, physical free-space
margins and distributed worker fencing remain production prerequisites.
Keep offline inspection/repair and registration deferred, and deletion disabled.
Use container-only qualification, not a real SLES host test plan.

Four new exact-service subprocess tests cover staging allocation and restart
with an older partial file preserved; all manifest phases and committed custody
verification with SQLite unchanged until parent receipts; both locks retained
after parent descriptors close and released after child exit; rejection of stale
sequences; oversized frame refusal before allocation; and complete allocation/
writing/verification/publication of a valid V1 document larger than 32 KiB while
returning metadata-only replies smaller than 2 KiB. The large-document fixture
adds JSON whitespace to preserve the same semantic recording metadata. Existing API/replay,
manifest/collision and process-crash suites remain required. This extends the
worker architecture; it does not complete configurable concurrency
(`L1-SYS-017`) or production NFS qualification. Formal Rust trace derivation
remains roadmap work. No dependency, schema, REST endpoint or configuration
change is introduced.

The mandatory gate passed via native WSL in
`rust/validation/20261014T014428Z-8bcb1a54`: 98 tests per profile (10 core,
35 storage, 10 claims, 13 transfer/manifest, 30 executable/API), debug and release.
All 20 executable artifacts passed ELF/loader/library audits and eager relocation
in pinned SLES userspace; maximum required version remains GLIBC_2.18. Six negative
audit controls passed; the external Linux graph remains 42 packages. Container
cleanup recorded no errors. Formatting, Clippy with warnings denied and the
existing trace-matrix check passed. See
[RUST-SLES-EVIDENCE.json](RUST-SLES-EVIDENCE.json).

An earlier 97-test run passed, but review found that full manifest documents in
replies could exceed the 32 KiB reply bound after an effect. Replies now carry
only metadata; the new large-document case exercises that correction through
every manifest phase. The corrected code passed the full gate above. Containers
share the runner kernel/CPU; these results do not qualify old-kernel behavior,
NFS or power-loss durability.
