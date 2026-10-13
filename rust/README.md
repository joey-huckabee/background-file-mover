# Incremental Rust implementation

Members are `mover-core`, a dependency-free pure protocol library,
`mover-store`, the E1-qualified SQLite repository, and `mover-fs`, the
E2-qualified rustix local claim worker. Add the executable in the API slice.
Confirmation methods trust validated durable receipts from their eventual callers;
the state model itself performs no HTTP, SQL, hashing or filesystem effects.

Current rules cover relative paths/prefix collisions, optional sizes, all-file
handoff, stable replay, pinned policy, publication/set commitment and cleanup
authorization. Local claims check descriptor-relative traversal, ownership,
identity, private custody and actual size, with process-exit reconciliation.
NFS behavior, persistent missing-file deadlines, API resource limits and full
production mount/worker qualification remain subsequent work.
Replay currently preserves file-list order; API normalization is still open.

The [store](crates/mover-store/README.md) persists acceptance/replay and pinned
policy on one dedicated database thread. The [claim worker](crates/mover-fs/src/lib.rs)
commits intent before a no-clobber rename, synchronizes the effect, then commits
its receipt. Only all-file receipts authorize Ready202; no HTTP endpoint or
post-transfer source deletion exists yet. See [increment 03](../docs/RUST-INCREMENT-03.md)
for evidence, supported local setup and remaining effects.

## Checks

Every build/test validation must include the pinned SLES 12 SP5/glibc 2.22 gate.
From the repository root on Windows or Linux with Python and Podman:

```sh
python scripts/check-rust-sles.py
```

For this Windows checkout, run from WSL:

```sh
bash /mnt/c/Users/Joey/Documents/GIT-GitHub/joey-huckabee/background-file-mover/scripts/test-rust-wsl.sh
```

The WSL helper invokes the same Python gate through native Podman. Sources are
copied into the builder's native container filesystem; compilation never happens
under `/mnt/c`. It does not change the historical WSL checkout. The pinned builder
uses Rust 1.99.0, cargo-zigbuild 0.23.4 and Zig 0.16.0, with target
`x86_64-unknown-linux-gnu.2.22` and baseline x86-64 CPU flags.

The gate checks formatting/Clippy, zigbuilds debug and release targets, audits
every emitted executable and runs the exact test binaries in pinned SLES userspace
as UID 1000 with eager binding, no capabilities and no network. Host-only
`cargo test` is not a completed validation. Future service executables also need
their own runtime smoke/behavior checks; add those as executable slices arrive.

Cargo compilation is offline/locked. Missing pinned images, toolchain and locked
crate sources require provisioning network access; retain their caches for offline
runs. Logs, binaries and a source snapshot remain in ignored `rust/validation/`.
Created containers are removed; the named toolchain cache is retained. No validation
data/source archive is uploaded by CI. The registry source cache is also retained.
See [the platform gate](../docs/RUST-SLES-GATE.md)
and [increment evidence](../docs/RUST-INCREMENT-01.md). Package experiments remain
paused. Containers share the runner kernel/CPU, not an actual old SLES kernel.
