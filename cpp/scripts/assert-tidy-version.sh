#!/bin/sh
# Refuses to report success for a clang-tidy too old to run the checks CI runs.
#
# CI uses clang-tidy-20. A developer with clang-tidy 14 gets a clean local run
# because the checks that fail in CI did not exist in their binary -- so the
# gate reports PASS while having tested less than it claims. That is the
# failure this repository keeps finding in its own apparatus, and the
# countermeasure is the same each time: fail closed rather than silently narrow.
#
# Concretely: misc-const-correctness arrived in clang-tidy 17. C4 was clean on
# 14 locally and failed CI with twenty errors from that one check.
#
# Usage:  sh scripts/assert-tidy-version.sh <clang-tidy-binary> <min-major>
set -eu

tidy=${1:-clang-tidy}
want=${2:-17}

if ! command -v "$tidy" >/dev/null 2>&1; then
    echo "assert-tidy-version: '$tidy' not found" >&2
    exit 1
fi

# "Ubuntu LLVM version 14.0.0" / "LLVM version 20.1.2" -- take the first
# dotted version on the version line and keep its major component.
line=$("$tidy" --version 2>/dev/null | grep -i 'version' | head -1)
major=$(printf '%s\n' "$line" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 |
        cut -d. -f1)

if [ -z "$major" ]; then
    echo "assert-tidy-version: cannot parse a version from '$line'" >&2
    exit 1
fi

if [ "$major" -lt "$want" ]; then
    echo "assert-tidy-version: $tidy is major version $major; this gate needs $want or newer" >&2
    echo "" >&2
    echo "  found: $line" >&2
    echo "" >&2
    echo "CI runs clang-tidy-20. An older binary does not know about the checks" >&2
    echo "CI enforces, so it would report a clean run having tested less than it" >&2
    echo "claims -- misc-const-correctness, for one, arrived in clang-tidy 17." >&2
    echo "" >&2
    echo "Install a newer one and point the build at it:" >&2
    echo "    sudo apt-get install clang-tidy-20" >&2
    echo "    make tidy TIDY=clang-tidy-20" >&2
    echo "" >&2
    echo "Or run the gate the way CI does, in the CI image:" >&2
    echo "    make check-ci" >&2
    exit 1
fi

echo "tidy-version OK: $tidy is major $major (>= $want)"
