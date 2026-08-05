#!/bin/sh
# Enforces L2-SEC-008: the software never invokes system(3) or any shell.
#
# External commands, if any ever return, are launched with fork and execvp
# using an argument vector -- so there is no shell metacharacter interpretation
# for a filename to inject into. Recording filenames are attacker-influenced by
# definition: whoever can create a file chooses its name.
#
# ADR-0011 already removed the external-command transfer strategy for this
# reason, which makes this gate cheap insurance rather than a live constraint:
# nothing today wants to run a command, and this is how it stays that way.
#
# Tests are covered too, deliberately. A test that shells out to `rm -rf` for
# cleanup is a small convenience that teaches the pattern this forbids.
#
# Usage:  sh scripts/assert-no-shell.sh
set -eu

cd "$(dirname "$0")/.."

# system( and popen( are the shell-invoking calls. The execl family is banned
# in its shell-searching forms; execvp with a vector is what L2-SEC-008
# explicitly permits, so it is not listed.
banned='(^|[^_[:alnum:]])(system|popen|execlp|execl)[[:space:]]*\(|/bin/sh|/bin/bash'

status=0
for f in $(find src include tests fuzz -name '*.cpp' -o -name '*.hpp' 2>/dev/null | sort); do
    # Comments stripped first: this rule is worth explaining in prose, and a
    # gate that fires on its own documentation trains people to delete the
    # documentation.
    hits=$(sed 's://.*::' "$f" | grep -nE "$banned" || true)
    if [ -n "$hits" ]; then
        echo "assert-no-shell: $f invokes a shell" >&2
        echo "$hits" | sed "s|^|  $f:|" >&2
        status=1
    fi
done

if [ "$status" -ne 0 ]; then
    echo "" >&2
    echo "L2-SEC-008: never system(3), popen(3) or a shell. Use fork plus" >&2
    echo "execvp with an argument vector, so no metacharacter interpretation" >&2
    echo "exists for a filename to inject into. See ADR-0011." >&2
    exit 1
fi

echo "no-shell OK: no shell invocation in src, include, tests or fuzz"
