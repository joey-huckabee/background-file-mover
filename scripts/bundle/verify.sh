#!/bin/sh
# No network access, source/destination probing or SQLite open.
set -eu
LC_ALL=C
export LC_ALL
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
cd "$root"
for tool in sha256sum find sort awk cmp mktemp uname getconf ldd; do
    command -v "$tool" >/dev/null || { echo "Missing OS prerequisite: $tool" >&2; exit 1; }
done
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
trap 'exit 1' HUP INT TERM
test -z "$(find . ! -type f ! -type d -print)" || { echo 'Bundle contains nonregular objects' >&2; exit 1; }
awk 'NF != 2 || $1 !~ /^[0-9a-f]+$/ || length($1) != 64 || $2 !~ /^\.\/[A-Za-z0-9_.+\/-]+$/ || $2 ~ /\/\.\.?(\/|$)/ {exit 1}' SHA256SUMS || { echo 'Invalid checksum inventory' >&2; exit 1; }
awk '{print $2}' SHA256SUMS | sort > "$tmp/expected"
find . -type f ! -path ./SHA256SUMS | sort > "$tmp/actual"
cmp -s "$tmp/expected" "$tmp/actual" || { echo 'Missing or unexpected bundle files' >&2; exit 1; }
sha256sum -c SHA256SUMS > "$tmp/check" 2>&1 || { cat "$tmp/check" >&2; exit 1; }
test "$(uname -s)" = Linux && test "$(uname -m)" = x86_64 || { echo 'Requires Linux x86_64' >&2; exit 1; }
getconf GNU_LIBC_VERSION | awk '$1 == "glibc" {split($2,v,"."); if (v[1]>2 || (v[1]==2 && v[2]>=22)) ok=1} END {exit !ok}' || { echo 'Requires OS glibc >= 2.22' >&2; exit 1; }
ldd -r ./bin/file-mover > "$tmp/ldd" 2>&1 || { cat "$tmp/ldd" >&2; exit 1; }
if grep -E 'not found|undefined symbol' "$tmp/ldd"; then
    echo 'Required OS library/relocation unavailable; use approved offline vendor media' >&2
    exit 1
fi
./bin/file-mover --check-platform > "$tmp/platform"
grep -q 'build=production' "$tmp/platform" || { echo 'Not a production-mode executable' >&2; exit 1; }
echo 'Verified bundle inventory, hashes, OS dependencies and executable smoke check.'
