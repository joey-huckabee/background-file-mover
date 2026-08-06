#!/bin/sh
# Negative test for assert-no-permission-tests.sh: proves it accepts the modes
# it must accept and rejects the modes it must reject.
#
# Run by hand, not from CI -- it writes a probe file into tests/ and would race
# a concurrent build. Every gate in this project is negative-tested by injecting
# the violation it claims to catch; this is that test, kept rather than done
# once, because the accept/reject boundary here is a regex over octal modes and
# the next person to adjust it needs a way to check they have not widened it.
#
# The probe file is written into the real tests/ directory, because the gate
# resolves its own root and scans that -- an earlier version of this harness
# wrote the probe into a temp tree the gate never looked at, so every case
# "passed" by scanning the clean repository instead. Cleaned up on exit.
set -u
cd "$(dirname "$0")/.."

probe=tests/zz_gate_probe.cpp
trap 'rm -f "$probe"' EXIT INT TERM

check() {
    label=$1
    line=$2
    want=$3
    printf 'void f() { %s }\n' "$line" > "$probe"
    sh scripts/assert-no-permission-tests.sh >/dev/null 2>&1
    got=$?
    rm -f "$probe"
    if [ "$got" -eq "$want" ]; then
        echo "ok   ($label)"
    else
        echo "FAIL ($label): wanted exit $want, got $got  --  $line"
    fi
}

# Sanity: the repository itself must be clean, or every rejection case below
# would pass for the wrong reason.
if ! sh scripts/assert-no-permission-tests.sh >/dev/null 2>&1; then
    echo "FAIL (baseline): the tree already violates the gate" >&2
    exit 1
fi
echo "ok   (baseline clean)"

# Must be ACCEPTED (exit 0): granting permission, not denying it.
check "0777 grant"        '::chmod(p, 0777);'   0
check "01777 sticky"      '::chmod(p, 01777);'  0
check "0700 owner-all"    '::chmod(p, 0700);'   0
check "0600 owner-rw"     '::chmod(p, 0600);'   0

# Must be REJECTED (exit 1): owner loses write, so root ignores it.
check "0500 deny write"   '::chmod(p, 0500);'   1
check "0400 read-only"    '::chmod(p, 0400);'   1
check "0000 no access"    '::chmod(p, 0000);'   1
check "01500 sticky+deny" '::chmod(p, 01500);'  1
check "fchmod 0400"       '::fchmod(fd, 0400);' 1
