# Supervised background payload workers

The user approved deferring offline inspection and repair at the completed
increment-10 boundary. Worker isolation and controlled NFS qualification now
take priority over additional operator tooling. No offline inspection or repair
command was started or left partially implemented.

Automatic background delivery now runs each copy and independent staging
verification in a child process of the same `file-mover` executable. There is
one live payload child at a time. The child handles the potentially large reads,
writes, SHA-256 computation and staging synchronization; it cannot access SQLite
through this protocol and performs no claiming, allocation, publication, manifest
commitment or deletion. The coordinator's existing SQLite owner validates and
persists each returned transition before proceeding. The normal integrity path
remains source read + staging write + staging reread, or 3N logical I/O.

## Assignment and custody

`--internal-payload-worker` is an internal mode, not an operator command or new
deployed executable. A private Unix socket carries exactly one versioned JSON
assignment and one receipt. Requests are capped at 32 KiB and receipts at 2 KiB;
unknown/duplicate fields and invalid phases/identities are rejected. No payload
bytes travel over IPC. The assignment contains the durable claim/transfer
observations, job/file/attempt and paths. It carries no database path. The parent
checks the returned job/file/attempt/phase and verifies that verification did not
change the copied identity/digest; the store checks immutable transfer context
and valid adjacent transitions before saving the receipt.

The source and destination namespace locks are duplicated into the child's
standard input/output descriptors. These descriptors are directories, not data
streams; standard error is the private socket. The child validates their identity
against the authorized namespace paths before effects. Both processes hold the
same locked open descriptions, so closing the parent's copies does not release
custody while a child remains alive. No unrelated descriptors are intentionally
inherited. This is local filesystem custody, not distributed NFS fencing.

The supervisor polls child exit off the Tokio executor. On shutdown/error it
requests termination and waits for confirmed exit before releasing the assignment;
it never starts a replacement merely because a timeout or signal occurred. A
stuck process or unrecoverable reaping error can still delay shutdown indefinitely.
The three-second IPC bounds do not limit copy duration or prove cancellation.
Successful child exit without a valid receipt is an uncertain operation; existing
durable transfer reconciliation applies, preserving retained sources/staging.

## Scope and evidence

Tests use the exact qualified service executable to copy and verify a staged file,
showing the database remains unchanged until the parent saves each receipt and
that neither final files nor the completion manifest are published by the child.
They prove both namespace locks remain held after parent descriptors close and
become available after the child is killed and reaped. Malformed, oversized,
forbidden-phase and invalid-private-name assignments preserve the source, empty
staging allocation and durable intent. Existing automatic multi-file delivery,
manifest, restart, collision and filesystem process-crash tests remain required.

This is a partial implementation of the process-worker architecture in
[RUST-DIRECTION.md](RUST-DIRECTION.md), not completion of configurable concurrency
(`L1-SYS-017`) or production NFS support. Formal Rust L2/L3 trace derivation remains
roadmap work. No schema, dependency, REST contract or startup configuration change
is introduced. The stopped-daemon `--transfer-one` reference command still runs
inline. Claiming, allocation, publication, reconciliation reads and manifests still
use the local thread path; some can block. Offline repair, source deletion and NFS
remain disabled. Root replacement/mount authorization, full coordinator-death
faults, durable assignments for remaining effects, scheduler readiness and bounded
worker replacement require later increments before enabling NFS.

The mandatory gate passed via native WSL in
`rust/validation/20261014T000348Z-19b307e8`: 91 tests per profile (10 core,
35 storage, 10 claims, 13 transfer/manifest, 23 executable/API), debug and release.
All 20 executable artifacts passed ELF/loader/library audits and eager relocation
in pinned SLES userspace; maximum required version is GLIBC_2.18. Six negative
audit controls passed, the external Linux dependency graph remains 42 packages,
and container cleanup recorded no errors. Formatting, Clippy with warnings denied,
and the existing trace-matrix check passed. The earlier attempt stopped at a
compile error in protocol-error conversion, corrected before this full passing run.
See [RUST-SLES-EVIDENCE.json](RUST-SLES-EVIDENCE.json). Containers share the runner
kernel/CPU; these results do not qualify old-kernel behavior or NFS durability.
