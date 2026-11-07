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
zig c++ -std=c++11 -O2 -Ireference/include reference/http_parser.cpp http-oracle.cpp -o evidence/http-oracle
./evidence/http-oracle corpus/* > evidence/oracle.tsv
printf 'GET /\377 HTTP/1.1\r\n\r\n' > evidence/policy-raw-target
./evidence/http-oracle evidence/policy-raw-target > evidence/policy.tsv
zig c++ -std=c++11 -O2 -Ireference/include reference/json.cpp json-oracle.cpp -o evidence/json-oracle
./evidence/json-oracle json-corpus/* > evidence/json-oracle.tsv
cargo zigbuild --release --locked --target x86_64-unknown-linux-gnu.2.22 -vv > evidence/build.log 2>&1
cargo metadata --locked --filter-platform x86_64-unknown-linux-gnu --format-version 1 > evidence/metadata.json
cargo tree --locked --target x86_64-unknown-linux-gnu -e features > evidence/dependency-features.txt
cargo vendor --locked vendor > evidence/vendor-config.toml 2> evidence/vendor.log
tar -czf evidence/vendor-sources.tar.gz vendor
tar -czf evidence/probe-sources.tar.gz Cargo.toml Cargo.lock rust-toolchain.toml build.sh http-oracle.cpp json-oracle.cpp control probe json cumulative corpus json-corpus reference
find /root/.cache/cargo-zigbuild -name 'zigcc-x86_64-unknown-linux-gnu.2.22-*.sh' -exec cat '{}' ';' > evidence/c-compiler-wrapper.txt
for name in e4-control e4-http e4-cumulative; do
    cp "target/x86_64-unknown-linux-gnu/release/$name" "evidence/artifacts/$name"
done
CARGO_TARGET_DIR=/work/scalar RUSTFLAGS="$RUSTFLAGS --cfg httparse_disable_simd=\"1\"" cargo zigbuild -p e4-http --release --locked --target x86_64-unknown-linux-gnu.2.22 -vv > evidence/scalar-build.log 2>&1
cp scalar/x86_64-unknown-linux-gnu/release/e4-http evidence/artifacts/e4-http-scalar
for name in e4-control e4-http e4-cumulative e4-http-scalar; do
    nm -C "evidence/artifacts/$name" > "evidence/elf/$name-symbols.txt"
    readelf -W -h -l -d -n -V --dyn-syms "evidence/artifacts/$name" > "evidence/elf/$name.txt"
done
sha256sum evidence/artifacts/* evidence/Cargo.lock evidence/*sources.tar.gz > evidence/sha256.txt
printf 'BUILD PASS\n'
