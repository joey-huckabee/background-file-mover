#!/bin/sh
# Runs the integration tests on the target host, over SSH, from the control node.
#
# Layer 2. Takes an inventory host and knows nothing about how it was made.
#
# Each test is copied over and run with sudo, and its output is streamed back.
# Deliberately not an Ansible playbook: these are assertions, not
# configuration, and Ansible's changed/ok reporting obscures which assertion
# failed. A shell script that prints "ok" and "FAIL" is easier to read at the
# moment it matters.
#
# Usage:  sh run-all.sh [inventory] [host-pattern]
set -eu

INVENTORY=${1:-../configure/inventory.ini}
PATTERN=${2:-lab}

cd "$(dirname "$0")"

if [ ! -f "$INVENTORY" ]; then
    echo "no inventory at $INVENTORY" >&2
    echo "copy ../configure/inventory.ini.example and put the VM address in it" >&2
    exit 2
fi

if ! command -v ansible >/dev/null 2>&1; then
    echo "ansible is not installed on this control node" >&2
    echo "run: sh ../prereqs/install-control-node.sh" >&2
    exit 2
fi

fails=0
for test in [0-9][0-9]-*.sh; do
    [ -e "$test" ] || continue
    echo ""
    echo "=============================================================="
    echo "running $test"
    echo "=============================================================="
    # -o so the output is the script's, not Ansible's JSON wrapper. Without it
    # the "ok"/"FAIL" lines arrive as one escaped blob.
    if ansible "$PATTERN" -i "$INVENTORY" \
        --become \
        -m script -a "$test" 2>&1 | sed 's/^/  /'; then
        echo "$test: PASSED"
    else
        echo "$test: FAILED"
        fails=$((fails + 1))
    fi
done

echo ""
if [ "$fails" -ne 0 ]; then
    echo "integration: $fails test file(s) failed"
    exit 1
fi
echo "integration: all tests passed"
