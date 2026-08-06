#!/bin/sh
# Asserts that every file in .githooks/ is executable BOTH in the index and in
# the working tree.
#
# Git silently ignores a hook that is not executable. It prints a hint and
# carries on, so the failure mode is not "the hook errored" but "the hook was
# never there" -- indistinguishable, from the outside, from a hook that passed.
#
# This has now regressed twice, both times for the same reason: the hook was
# edited through a tool that rewrites the file, and a rewrite drops the
# permission bits. chmod *before* an edit is undone by the edit. The mode has
# to be restored afterwards, and `git update-index --chmod=+x` records it
# regardless of what the working tree says.
#
# A one-line check is cheaper than noticing months later that nothing has been
# running.
#
# It checks the WORKING TREE as well as the index, because git executes the file
# on disk and the two can disagree. Checking only the index is what let this
# regress a third time: an edit over the \\wsl.localhost UNC path cleared the
# working-tree mode while the index kept 100755, so the gate reported "all
# entries are executable" about a hook git would not run. A gate that inspects
# something other than what the system actually uses is the exact failure it
# exists to catch.
#
# Usage:  sh scripts/assert-hook-mode.sh
set -eu

cd "$(git rev-parse --show-toplevel)"

status=0
found=0

for entry in $(git ls-files -s .githooks/ | awk '{print $1 ":" $4}'); do
    found=1
    mode=${entry%%:*}
    file=${entry#*:}
    if [ "$mode" != "100755" ]; then
        echo "assert-hook-mode: $file is recorded as $mode, not 100755" >&2
        status=1
    fi
    # The file git actually runs. An index mode of 100755 over a working-tree
    # file with no execute bit means the hook is dead locally while every
    # index-based check reports it healthy.
    if [ ! -x "$file" ]; then
        echo "assert-hook-mode: $file is not executable in the working tree" >&2
        status=1
    fi
done

if [ "$found" -eq 0 ]; then
    echo "assert-hook-mode: no files tracked under .githooks/" >&2
    exit 1
fi

if [ "$status" -ne 0 ]; then
    echo "" >&2
    echo "Git ignores a hook that is not executable -- it prints a hint and" >&2
    echo "carries on, so this looks exactly like a hook that passed." >&2
    echo "" >&2
    echo "Fix with:" >&2
    echo "    chmod +x .githooks/*" >&2
    echo "    git update-index --chmod=+x .githooks/pre-commit" >&2
    exit 1
fi

echo "hook-mode OK: all .githooks entries are executable in the index and on disk"
