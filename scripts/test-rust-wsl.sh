#!/usr/bin/env bash
# Stage source on WSL's native filesystem; never build in /mnt/c.
set -euo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
stage_dir="$(mktemp -d /tmp/file-mover-rust.XXXXXX)"
cleanup() {
    case "$stage_dir" in
        /tmp/file-mover-rust.*) rm -rf -- "$stage_dir" ;;
        *) printf 'Refusing cleanup outside the temporary build prefix\n' >&2 ;;
    esac
}
trap cleanup EXIT
tar -C "$repo_dir/rust" --exclude=target -cf - . | tar -C "$stage_dir" -xf -
cd "$stage_dir"
cargo fmt --all -- --check
cargo test --offline --locked --workspace
cargo clippy --offline --locked --workspace --all-targets -- -D warnings
