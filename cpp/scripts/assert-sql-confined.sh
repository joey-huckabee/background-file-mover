#!/bin/sh
# Enforces L2-JOB-009: SQL and the vendored sqlite3.h are confined to the
# repository implementation. No other translation unit includes the database
# header or embeds SQL.
#
# Why this is a gate and not a review note. L2-JOB-009 is written as
# Verification: Inspection, and inspection is exactly the method that decays --
# it holds until the week someone needs one quick query somewhere else and no
# tool objects. The containment is the point of ADR-0010's repository
# interface: if SQL leaks into the manager or the REST layer, replacing or
# fixing the storage engine stops being a local change.
#
# The same reasoning as the vendored-hash gate. A rule nothing checks is a rule
# that erodes quietly, and the erosion is invisible in a passing build.
#
# Usage:  sh scripts/assert-sql-confined.sh
set -eu

cd "$(dirname "$0")/.."

# The allowlist is explicit and deliberately short, so adding a third file is a
# decision someone has to make here rather than a side effect of an include.
#
#   src/store.cpp            the repository itself -- the point of the rule
#   tests/test_sqlite_vendor.cpp
#                            the vendoring smoke test. It must reach the
#                            vendored header directly: what it verifies is that
#                            sqlite3.h and sqlite3.c are the same pinned
#                            release, which cannot be observed through an
#                            abstraction over them. It contains no SQL that
#                            expresses job behaviour.
allowed_header='^src/store\.cpp$|^tests/test_sqlite_vendor\.cpp$'

status=0

# Both checks run against the source with `//` comments stripped. Without that
# the gate fires on prose: this rule is one worth explaining in comments, and
# the first version flagged store.hpp for the sentence saying it does not
# include sqlite3.h. A gate that punishes documentation trains people to stop
# writing it.
#
# The include check is additionally anchored to a real preprocessor directive
# rather than to the filename appearing anywhere.
include_re='^[[:space:]]*#[[:space:]]*include.*sqlite3\.h'

# Anchored to a statement keyword at the start of a string literal, which is
# how SQL is actually written here -- so a variable named `update_state` or a
# function called `begin` does not trip it.
sql_re='"[[:space:]]*(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|PRAGMA|BEGIN|COMMIT|ROLLBACK)[[:space:]]'

for f in $(find src include tests fuzz -name '*.cpp' -o -name '*.hpp' 2>/dev/null | sort); do
    if printf '%s\n' "$f" | grep -qE "$allowed_header"; then
        continue
    fi

    stripped=$(sed 's://.*::' "$f")

    hits=$(printf '%s\n' "$stripped" | grep -nE "$include_re" || true)
    if [ -n "$hits" ]; then
        echo "assert-sql-confined: $f includes sqlite3.h" >&2
        echo "$hits" | sed "s|^|  $f:|" >&2
        status=1
    fi

    hits=$(printf '%s\n' "$stripped" | grep -nE "$sql_re" || true)
    if [ -n "$hits" ]; then
        echo "assert-sql-confined: $f embeds SQL" >&2
        echo "$hits" | sed "s|^|  $f:|" >&2
        status=1
    fi
done

if [ "$status" -ne 0 ]; then
    echo "" >&2
    echo "L2-JOB-009: SQL and sqlite3.h belong behind the JobStore interface" >&2
    echo "in src/store.cpp (ADR-0010). Add a method there rather than a query" >&2
    echo "here; if the containment boundary genuinely needs to move, change" >&2
    echo "this gate deliberately and say why." >&2
    exit 1
fi

echo "sql-confined OK: sqlite3.h and SQL appear only where L2-JOB-009 allows"
