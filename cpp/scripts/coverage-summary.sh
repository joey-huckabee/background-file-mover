#!/bin/sh
# Summarizes gcov output for the C++ tree.
#
# Usage:  sh scripts/coverage-summary.sh <gcov-report-dir> [markdown]
#
# gcov annotates each source line with an execution count in the first
# colon-delimited field:
#     "    -:  12:// a comment"          not instrumented
#     "    5:  13:  int x = 1;"          executed 5 times
#     "#####:  14:  unreachable();"      instrumented but never executed
#
# Coverage is (instrumented - never-executed) / instrumented. Lines marked
# "-" are excluded from both sides: comments and declarations are not
# coverable, and counting them inflates the number.
set -eu

DIR="${1:-build/coverage/report}"
FORMAT="${2:-plain}"

if [ ! -d "$DIR" ]; then
    echo "coverage-summary: no such directory: $DIR" >&2
    exit 1
fi

total_inst=0
total_miss=0
found=0

if [ "$FORMAT" = "markdown" ]; then
    printf '| File | Covered | Instrumented | Coverage |\n'
    printf '|---|---:|---:|---:|\n'
fi

for f in "$DIR"/*.gcov; do
    [ -e "$f" ] || continue
    found=1

    inst=$(awk -F: '$1 ~ /^ *[0-9]+$/ || $1 ~ /^ *#+$/ { n++ } END { print n+0 }' "$f")
    miss=$(awk -F: '$1 ~ /^ *#+$/                       { n++ } END { print n+0 }' "$f")
    cov=$((inst - miss))

    if [ "$inst" -eq 0 ]; then
        pct="n/a"
    else
        pct=$(awk "BEGIN { printf \"%.1f%%\", $cov * 100 / $inst }")
    fi

    name=$(basename "$f" .gcov)
    if [ "$FORMAT" = "markdown" ]; then
        printf '| `%s` | %s | %s | %s |\n' "$name" "$cov" "$inst" "$pct"
    else
        printf '%-20s %5s / %-5s  %s\n' "$name" "$cov" "$inst" "$pct"
    fi

    total_inst=$((total_inst + inst))
    total_miss=$((total_miss + miss))
done

if [ "$found" -eq 0 ]; then
    echo "coverage-summary: no .gcov files in $DIR" >&2
    exit 1
fi

total_cov=$((total_inst - total_miss))
if [ "$total_inst" -eq 0 ]; then
    total_pct="n/a"
else
    total_pct=$(awk "BEGIN { printf \"%.1f%%\", $total_cov * 100 / $total_inst }")
fi

if [ "$FORMAT" = "markdown" ]; then
    printf '| **total** | **%s** | **%s** | **%s** |\n' \
        "$total_cov" "$total_inst" "$total_pct"
else
    printf '%-20s %5s / %-5s  %s\n' "TOTAL" "$total_cov" "$total_inst" "$total_pct"
fi
