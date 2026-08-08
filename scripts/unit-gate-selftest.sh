#!/bin/sh
# Negative test for assert-unit-valid.sh: proves it fails on the defects it
# claims to catch, and passes on a clean tree.
#
# Run by hand, not from CI -- it edits the real unit file and the real
# reference config in place and would race a concurrent build. Kept rather than
# done once, for the same reason gate-selftest.sh is: the next person to relax
# a check here needs a way to see they have relaxed it.
#
# Case 2 is the one worth reading. Removing --check from ExecStartPre used to
# make the gate HANG rather than fail: without --check the unit's command is
# not a validation, it is the service, so the gate started the daemon and
# waited for it forever. A gate that hangs stops CI instead of failing it.
set -u
cd "$(dirname "$0")/.."

GATE="sh scripts/assert-unit-valid.sh"
BIN=${1:-cpp/build/x86_64-linux-gnu-11-default/filemover}
UNIT=deploy/systemd/file-mover.service
CFG=config/file-mover.ini

if [ ! -x "$BIN" ]; then
    echo "usage: $0 [path-to-filemover-binary]" >&2
    echo "  (build it first: make -C cpp daemon)" >&2
    exit 2
fi

unit_bak=$(mktemp)
cfg_bak=$(mktemp)
cp "$UNIT" "$unit_bak"
cp "$CFG" "$cfg_bak"
restore() { cp "$unit_bak" "$UNIT"; cp "$cfg_bak" "$CFG"; }
# Restores on interrupt too: a killed selftest that leaves an injected defect
# in the working tree is worse than no selftest.
trap 'restore; rm -f "$unit_bak" "$cfg_bak"' EXIT INT TERM

fails=0

# Baseline first, or every rejection case below could pass for the wrong
# reason -- a gate that fails on everything catches nothing.
if $GATE "$UNIT" "$BIN" >/dev/null 2>&1; then
    echo "ok   (baseline clean)"
else
    echo "FAIL (baseline): the tree already fails the gate" >&2
    $GATE "$UNIT" "$BIN"
    exit 1
fi

expect_fail() {
    label=$1
    if $GATE "$UNIT" "$BIN" >/dev/null 2>&1; then
        echo "FAIL ($label): gate passed with the defect injected"
        fails=$((fails + 1))
    else
        echo "ok   ($label)"
    fi
    restore
}

printf 'InvalidDirectiveHere=yes\n' >> "$UNIT"
expect_fail "unknown directive in unit"

sed -i 's/^ExecStartPre=\(.*\) --check$/ExecStartPre=\1/' "$UNIT"
expect_fail "ExecStartPre lost --check"

printf '\n[transfer]\nmax_concurrent_jobs = 4\n' >> "$CFG"
expect_fail "reference config drifted from the parser"

sed -i 's/^database_path *=.*/database_path =/' "$CFG"
expect_fail "reference config missing a required value"

if $GATE "$UNIT" "$BIN" >/dev/null 2>&1; then
    echo "ok   (clean tree still passes)"
else
    echo "FAIL (restore): the tree did not come back clean"
    fails=$((fails + 1))
fi

echo "selftest failures: $fails"
exit $fails
