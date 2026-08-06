#!/bin/sh
# Asserts that a compilation database actually covers the given sources.
#
# Usage:  sh scripts/assert-compile-db.sh compile_commands.json src/a.cpp ...
#
# Why this exists: `bear` records what it *observes*. If the tree is already
# built, `bear -- make all` sees no compiler invocations and writes an empty
# database. clang-tidy then prints
#
#     Skipping src/foo.cpp. Compile command not found.
#
# and exits 0 — so the gate reports success having analyzed nothing. That is
# a false green, and it is invisible unless someone reads the log closely.
# Always `make clean` before `bear`, and run this afterwards to prove it.
set -eu

DB="${1:?usage: assert-compile-db.sh <compile_commands.json> <source>...}"
shift

if [ ! -f "$DB" ]; then
    echo "error: $DB does not exist." >&2
    echo "       Generate it with:  make clean-all && bear -- make all" >&2
    exit 1
fi

missing=0
for src in "$@"; do
    base=$(basename "$src")
    if ! grep -q "$base" "$DB"; then
        echo "error: $DB has no compile command for $src" >&2
        missing=1
    fi
done

if [ "$missing" -ne 0 ]; then
    echo >&2
    echo "       The database is stale or empty. bear only records compiler" >&2
    echo "       invocations it actually observes, so a pre-built tree yields" >&2
    echo "       nothing. Run:  make clean-all && bear -- make all" >&2
    exit 1
fi

count=$(grep -c '"file"' "$DB" || echo 0)
echo "compile database OK: $count entries, all requested sources present"
