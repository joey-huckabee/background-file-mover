#!/bin/sh
# Bans permission-based failure injection in the test suite.
#
# A test that induces a failure by removing write permission -- chmod 0500 on a
# directory, chmod 0400 on a file -- asserts nothing when the process is root,
# because root bypasses the permission check entirely. The operation simply
# succeeds and the test goes green having exercised the opposite path from the
# one it names.
#
# This is not hypothetical. C4's retry tests induced a pre-commit abort by
# making the destination directory read-only. That worked under WSL as an
# ordinary user and silently tested NOTHING in the GCC 4.8.5 fidelity
# container, which runs as root: the move succeeded, the job reached DONE, and
# six assertions about retry scheduling failed against a retry that had never
# been attempted. The failure was visible only because the fidelity tier runs
# the full suite rather than a compile.
#
# The project already has a uid-independent way to force a pre-commit abort:
# occupy the staging name so the commit rename fails with EEXIST. Both the C3
# mover suite and the C4 manager suite use it. EEXIST is returned to root and
# to nobody alike.
#
# Scoped to tests deliberately. Production code may legitimately need chmod;
# what is banned is depending on a permission denial to prove a behaviour.
#
# Usage:  sh scripts/assert-no-permission-tests.sh
set -eu

cd "$(dirname "$0")/.."

# Only modes that REMOVE owner write are banned. chmod itself is fine and the
# suite has honest uses of it -- test_fsops.cpp sets 0777 and 01777 to build
# world-writable and sticky directories, which is the condition under test
# rather than a way of making something fail.
#
# The owner digit is the one that matters, because these tests create the files
# they operate on and therefore own them. Write is bit 2, so an owner digit of
# 0, 1, 4 or 5 denies it. The alternation covers three-digit modes (0500) and
# four-digit modes with a setuid/sticky prefix (01500); the trailing guard stops
# the three-digit branch matching the first four characters of 01777.
#
# fchmod and fchmodat are included: the hazard is the permission bit, not the
# spelling of the call that sets it.
deny_write='0([0145][0-7][0-7]|[0-7][0145][0-7][0-7])([^0-7]|$)'
banned="(^|[^_[:alnum:]])(chmod|fchmod|fchmodat)[[:space:]]*\\([^;]*$deny_write"

status=0
for f in $(find tests -name '*.cpp' -o -name '*.hpp' 2>/dev/null | sort); do
    # Comments stripped first, so the rule can be explained next to the code it
    # governs without the gate firing on its own rationale.
    hits=$(sed 's://.*::' "$f" | grep -nE "$banned" || true)
    if [ -n "$hits" ]; then
        echo "assert-no-permission-tests: $f injects failure via permissions" >&2
        echo "$hits" | sed "s|^|  $f:|" >&2
        status=1
    fi
done

if [ "$status" -ne 0 ]; then
    echo "" >&2
    echo "A permission denial is not a failure the fidelity tier can observe:" >&2
    echo "that container runs as root, and root bypasses the check. The test" >&2
    echo "passes locally and asserts nothing in CI." >&2
    echo "" >&2
    echo "Force a pre-commit abort by occupying the staging name instead, so" >&2
    echo "the commit rename fails with EEXIST. See Fixture::occupy_staging_name" >&2
    echo "in tests/test_manager.cpp and the collision case in tests/test_mover.cpp." >&2
    exit 1
fi

echo "no-permission-tests OK: no permission-based failure injection in tests"
