#!/bin/sh
set -eu
cd /work
mkdir -p evidence/artifacts evidence/elf
export RUSTFLAGS='-C target-cpu=x86-64'
export LIBSQLITE3_FLAGS='-USQLITE_THREADSAFE -DSQLITE_THREADSAFE=1 -DSQLITE_OMIT_LOAD_EXTENSION -DSQLITE_DQS=0 -USQLITE_DEFAULT_MEMSTATUS -DSQLITE_DEFAULT_MEMSTATUS=0 -DSQLITE_ENABLE_API_ARMOR'
export CC_ENABLE_DEBUG_OUTPUT=1
rustup toolchain install 1.99.0 --profile minimal --component rustfmt,clippy --target x86_64-unknown-linux-gnu > evidence/rust-toolchain-install.txt 2>&1
{
    rustc --version --verbose
    cargo --version
    cargo-zigbuild --version
    zig version
    printf 'RUSTFLAGS=%s\nLIBSQLITE3_FLAGS=%s\n' "$RUSTFLAGS" "$LIBSQLITE3_FLAGS"
} > evidence/toolchain.txt
if [ ! -f Cargo.lock ]; then cargo generate-lockfile; fi
cp Cargo.lock evidence/Cargo.lock
cargo fmt --all --check
cargo zigbuild --release --locked --target x86_64-unknown-linux-gnu.2.22 -vv > evidence/build.log 2>&1
zig cc -target x86_64-linux-gnu.2.22 -mcpu=x86_64 -O2 deny-rename.c -o evidence/artifacts/deny-rename
cargo metadata --locked --filter-platform x86_64-unknown-linux-gnu --format-version 1 > evidence/metadata.json
cargo tree --locked --target x86_64-unknown-linux-gnu -e features > evidence/dependency-features.txt
cargo vendor --locked vendor > evidence/vendor-config.toml 2> evidence/vendor.log
tar -czf evidence/vendor-sources.tar.gz vendor
tar -czf evidence/probe-sources.tar.gz Cargo.toml Cargo.lock rust-toolchain.toml build.sh deny-rename.c control probe cumulative
find /root/.cache/cargo-zigbuild -name 'zigcc-x86_64-unknown-linux-gnu.2.22-*.sh' -exec cat '{}' ';' > evidence/c-compiler-wrapper.txt
for name in e2-control e2-rustix e2-cumulative; do
    cp "target/x86_64-unknown-linux-gnu/release/$name" "evidence/artifacts/$name"
done
for name in e2-control e2-rustix e2-cumulative deny-rename; do
    readelf -W -h -l -d -n -V --dyn-syms "evidence/artifacts/$name" > "evidence/elf/$name.txt"
done
sha256sum evidence/artifacts/* evidence/Cargo.lock evidence/*sources.tar.gz > evidence/sha256.txt
printf 'BUILD PASS\n'
