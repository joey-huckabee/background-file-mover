#!/bin/sh
# Enforces L3-CPP-052: parsers must classify characters with explicit ranges,
# never through <cctype> or the locale-sensitive C conversion functions.
#
# Why this is a source gate and not only a unit test. The runtime test in
# tests/test_http_parser.cpp switches to tr_TR.UTF-8 and re-parses, which is
# the real proof — but setlocale returns NULL when the locale is not generated,
# and it is not generated in any of our CI containers. That test therefore
# degrades to a warning exactly where it would otherwise run. Grepping the
# source cannot be skipped by the environment.
#
# The Turkish case is the concrete hazard: std::tolower('I') under tr_TR does
# not yield 'i', so a locale-sensitive parser keys "IF-MATCH" under "iF-mATCH"
# and every header lookup misses.
#
# Usage:  sh scripts/assert-locale-free.sh <source> [<source>...]
set -eu

if [ "$#" -eq 0 ]; then
    echo "usage: $0 <source> [<source>...]" >&2
    exit 2
fi

# Word-boundary matched so a comment mentioning the hazard by name does not
# trip the gate — only real calls and includes do.
banned='<cctype>|<ctype\.h>|\bstd::(isalnum|isalpha|isdigit|isspace|isupper|islower|isxdigit|ispunct|isprint|iscntrl|tolower|toupper)\b|(^|[^_[:alnum:]])(isalnum|isalpha|isdigit|isspace|isupper|islower|isxdigit|tolower|toupper)[[:space:]]*\(|\b(strtoull|strtoul|strtoll|strtol|atoi|atol|atoll)[[:space:]]*\('

status=0
for src in "$@"; do
    if [ ! -f "$src" ]; then
        echo "assert-locale-free: no such file: $src" >&2
        status=1
        continue
    fi

    # Strip // comments and blank lines before matching. Block comments are
    # not stripped; none of the banned tokens appear inside one today, and a
    # false positive here fails loudly rather than passing silently.
    hits=$(sed 's://.*::' "$src" | grep -n -E "$banned" || true)

    if [ -n "$hits" ]; then
        echo "assert-locale-free: $src uses locale-sensitive classification" >&2
        echo "$hits" | sed "s|^|  $src:|" >&2
        status=1
    fi
done

if [ "$status" -ne 0 ]; then
    echo "" >&2
    echo "L3-CPP-052: use explicit ASCII range checks instead. See" >&2
    echo "docs/HAND-ROLLED-COMPONENTS.md and src/http_parser.cpp for the" >&2
    echo "pattern (is_digit/is_lower_alpha/to_lower_ascii)." >&2
    exit 1
fi

echo "locale-free OK: $# file(s) free of <cctype> and strtoul-family calls"
