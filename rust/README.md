# Incremental Rust implementation

The first member is `mover-core`, a dependency-free pure protocol library. Add
`mover-store`, `mover-fs` and the executable as tested slices require them.
Confirmation methods trust validated durable receipts from their eventual callers;
the state model itself performs no HTTP, SQL, hashing or filesystem effects.

Current rules cover relative paths/prefix collisions, optional sizes, all-file
handoff, stable replay, pinned policy, publication/set commitment and cleanup
authorization. Actual ownership/path containment, NFS behavior, missing-file
deadlines, API resource limits and crash reconciliation remain subsequent work.
Replay currently preserves file-list order; API normalization is still open.

## Checks

On a native Linux checkout with the pinned Rust 1.99.0 toolchain:

```sh
cd rust
cargo fmt --all -- --check
cargo test --offline --locked --workspace
cargo clippy --offline --locked --workspace --all-targets -- -D warnings
```

For this Windows checkout, run from WSL:

```sh
bash /mnt/c/Users/Joey/Documents/GIT-GitHub/joey-huckabee/background-file-mover/scripts/test-rust-wsl.sh
```

The script stages sources in a unique `/tmp/file-mover-rust.*` directory, builds
on WSL's native filesystem and removes that temporary build. It does not modify
the historical WSL Git checkout. Cargo is offline/locked; the pinned toolchain
and components must already be installed for disconnected execution.

These host logic tests are not SLES ELF/runtime qualification. Production remains
x86_64 GNU/glibc 2.22 with equivalent-container gates, no musl. Package experiments
remain paused. See [increment evidence](../docs/RUST-INCREMENT-01.md).
