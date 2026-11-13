#!/bin/bash
# Development only (WSL). Build with the SLES gate's SQLite compile options and
# run the real-service TLS/admin tests natively. Not qualification evidence:
# the SLES gate (scripts/check-rust-sles.py / PR CI) remains required.
# Usage (from the repo root, inside dev-wsl-namespace.sh):
#   wsl -u root -- bash scripts/dev-wsl-namespace.sh bash scripts/dev-local-tls-tests.sh [TEST_FILTER]
set -e
export PATH="$HOME/.cargo/bin:/usr/local/bin:/usr/bin:/bin"
cd "$(dirname "$0")/../rust"
export LIBSQLITE3_FLAGS="-USQLITE_THREADSAFE -DSQLITE_THREADSAFE=1 -DSQLITE_OMIT_LOAD_EXTENSION -DSQLITE_DQS=0 -USQLITE_DEFAULT_MEMSTATUS -DSQLITE_DEFAULT_MEMSTATUS=0 -DSQLITE_ENABLE_API_ARMOR"
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$HOME/fm-local-tests/target}"
fixtures=$(mktemp -d /tmp/fm-tls-XXXXXX)
trap 'rm -rf "$fixtures"' EXIT
python3 ../scripts/tls_proof_fixture.py --output "$fixtures/der" --archive "$fixtures/der.tar" >/dev/null
cargo build -q -p file-mover
FILE_MOVER_TLS_FIXTURES="$fixtures/der" FILE_MOVER_TEST_EXECUTABLE="$CARGO_TARGET_DIR/debug/file-mover" \
  cargo test -q -p file-mover --test tls ${1:+"$1"}
