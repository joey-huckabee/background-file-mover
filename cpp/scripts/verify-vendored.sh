#!/bin/sh
# Verifies that every vendored file matches the SHA-256 recorded in
# VENDORED.md (ADR-0004: vendored files are never edited).
#
# Usage:  sh scripts/verify-vendored.sh
#
# Why this exists: a repository-wide sed once rewrote an identifier inside
# the vendored Catch2 header (normaliseString -> normalizeString). The build
# passed, because the declaration and definition were renamed consistently,
# and every other gate passed too. Nothing detected it except comparing the
# hash. An edit to a vendored file is invisible to a compiler and obvious to
# a checksum, so the checksum has to be a gate.
set -eu

VENDORED_MD="${1:-VENDORED.md}"

if [ ! -f "$VENDORED_MD" ]; then
    echo "error: $VENDORED_MD not found (run from cpp/)" >&2
    exit 1
fi

failures=0
checked=0

# Rows look like:
#   | Name | tag | `path/to/file` | `sha256` | License | vendored |
# Only rows whose status is "vendored" carry a real hash; pending rows say TBD.
while IFS= read -r line; do
    case "$line" in
        \|*vendored\ \|*) ;;
        *) continue ;;
    esac

    path=$(printf '%s' "$line" | sed -n 's/.*| `\([^`]*\)` | `\([0-9a-f]\{64\}\)` .*/\1/p')
    want=$(printf '%s' "$line" | sed -n 's/.*| `\([^`]*\)` | `\([0-9a-f]\{64\}\)` .*/\2/p')

    [ -n "$path" ] || continue
    [ -n "$want" ] || continue

    checked=$((checked + 1))

    if [ ! -f "$path" ]; then
        echo "MISSING  $path" >&2
        failures=$((failures + 1))
        continue
    fi

    got=$(sha256sum "$path" | cut -d' ' -f1)
    if [ "$got" = "$want" ]; then
        printf 'OK       %s\n' "$path"
    else
        echo "MODIFIED $path" >&2
        echo "         recorded: $want" >&2
        echo "         actual:   $got" >&2
        echo "         Vendored files are never edited (ADR-0004). Either" >&2
        echo "         restore the file, or -- if the change is intended --" >&2
        echo "         re-pin the tag and update VENDORED.md deliberately." >&2
        failures=$((failures + 1))
    fi
done < "$VENDORED_MD"

if [ "$checked" -eq 0 ]; then
    echo "error: no vendored rows with a hash found in $VENDORED_MD" >&2
    exit 1
fi

if [ "$failures" -ne 0 ]; then
    echo "" >&2
    echo "$failures vendored file(s) do not match their recorded hash." >&2
    exit 1
fi

echo "$checked vendored file(s) verified against $VENDORED_MD"
