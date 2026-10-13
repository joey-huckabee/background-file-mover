# Rust SQLite acceptance increment

`mover-store` adds real durable acceptance/replay on a local SQLite database,
owned by a dedicated thread. The bounded command queue has capacity 32 and the
SQLite busy timeout is 250 ms. Public methods are blocking; future async handlers
must use a bounded adapter outside the executor.

## Acceptance behavior

One transaction records generator/submission identity, ordered required files,
optional expected sizes, normalized source context, pinned destination and
grouping/deletion policy, missing-file retry duration and source reservations.
Acknowledgement follows commit. Replay loads the original job/context rather than
applying a new route; changed details conflict. Reservations prevent a different
job/generator taking the same normalized source path, and survive restart.

All successful results still have Pending handoff. There is no filesystem claim,
HTTP 202 or source deletion in this increment. The source/destination context is
administrator-resolved input; physical roots, mount aliases and local-state
placement are deployment prerequisites to enforce in upcoming effect/startup work.
Request serialization and optional metadata beyond the current core model remain
API work. No old C++ database is automatically adopted.

Schema version 1 uses an application ID, relational integrity and stored required
file count. Unsupported/foreign schemas are retained and rejected. Missing file
rows or damaged reservation ledgers fail closed. No migration to another version
or destructive reset is implemented; future changes need explicit migration tests.

## Dependency and platform evidence

Use E1's rusqlite 0.40.1 (defaults off, bundled on), libsqlite3-sys 0.38.2 and
SQLite 3.53.2. All eleven external crate versions/checksums and declared licenses
match E1; no other direct Rust dependency was introduced. The build harness
provisions locked sources separately, then compiles offline/network-disabled with
the same THREADSAFE=1, OMIT_LOAD_EXTENSION, DQS=0, DEFAULT_MEMSTATUS=0 and
ENABLE_API_ARMOR settings. Store open reads back WAL/FULL/foreign keys and options.

The mandatory cargo-zigbuild GNU/glibc 2.22 gate passed on 2026-10-13 with
**26 tests in each profile**: ten core tests and sixteen storage tests. The ignored
child helper is explicitly invoked by the process-reopen test. Formatting and
Clippy pass. All six emitted test binaries require at most GLIBC_2.18; storage
adds only libm to the prior libc/libdl/libpthread/loader imports. There is no
shared SQLite, alternative loader, newer/private glibc or runtime search path.
Six negative ELF controls pass; exact artifact hashes are checked before SLES
execution as UID 1000 with no capabilities/network and eager binding.

[RUST-SLES-EVIDENCE.json](RUST-SLES-EVIDENCE.json) contains the current passing
inputs, dependency licenses, per-profile counts and artifact hashes/imports.
Raw local evidence stays under ignored `rust/validation/`. This qualifies the
exercised artifacts against SLES userspace, not old-kernel/power-loss behavior.

## Storage tests

Tests cover durable settings/compile options, optional u64 size round-trip,
reopen without claim acknowledgement, pinned replay/conflicting bodies,
generator-scoped IDs, cross-generator reservations, changed root mapping,
writer contention/retry, read-only failure, a real deferred-FK COMMIT failure,
rollback of partially inserted lists, foreign/future schema rejection,
concurrent replay serialization, separate-process reopen, abrupt exit followed by
recovery from an uncheckpointed committed WAL, missing stored files,
invalid normalized context and missing reservations blocking startup.

The tests are in [mover-store/src/tests.rs](../rust/crates/mover-store/src/tests.rs).
Failure cases verify no job/file/reservation acceptance is left from failed
transactions; retries can use the same original identity after correction.

## Requirement scope

This provides lower-layer evidence for L1-API-009 and L1-SYS-025, and transaction
failure/retention foundations for the claim protocol. The full REST/claim/transfer
requirements remain unfinished. Rust L2/L3 and automatic test discovery still
need deliberate integration; historical C++ coverage is not relabeled as Rust.

Next increment: durable filesystem-operation intent and one real source claim,
then reconciliation before release of source reservations/202. Registration and
authentication remain deferred; E6 remains paused.
