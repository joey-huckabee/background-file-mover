#!/bin/sh
# Enforces L2-DASH-002 and L2-DASH-003 on the embedded dashboard page.
#
# L2-DASH-003 is the one requirement in this project where the attack lands in
# somebody else's process. Every dynamic value on the page is a filesystem path
# or an error string, and a path is attacker-influenced in exactly the way the
# L1-SEC invariants already assume: whoever can create a file chooses its name.
# A name containing markup, assigned to innerHTML, is script execution in the
# operator's browser -- and the operator holds the one session with authority
# over this service.
#
# The requirement's stated method is "Test (T), Inspection (I)". Inspection is
# the method that quietly stops happening: it holds until someone adds one quick
# innerHTML for a bit of formatting and no tool objects. This is the mechanism.
#
# There is a matching TEST in tests/test_dashboard.cpp, which asserts the same
# properties against the string the binary actually serves. Two checks of one
# rule, deliberately: this one can be deleted in a commit, and that one cannot
# be satisfied by a page that is not shipped.
#
# Usage:  sh scripts/assert-dashboard-safe.sh
set -eu

cd "$(dirname "$0")/.."

PAGE=src/dashboard.cpp

if [ ! -f "$PAGE" ]; then
    echo "assert-dashboard-safe: FAIL: no such file: $PAGE" >&2
    exit 1
fi

status=0

# --- L2-DASH-003: no HTML-parsing sink may be written ---------------------
#
# innerHTML is banned outright, including `innerHTML = ""`. That assignment is
# genuinely harmless, and allowing it would mean this gate has to tell safe
# assignments from unsafe ones -- a judgement it cannot make from a regex, and
# a foothold for the next one. clear() uses removeChild instead; it is three
# lines and needs no exception.
#
# Comments are NOT stripped here, unlike the other source gates. The rule is
# explained in the page's own comments by name, so stripping them would be
# necessary -- except that a comment mentioning innerHTML in a file whose entire
# job is to never use it is worth a second pair of eyes anyway. The rationale
# therefore says "the property is never written" rather than spelling the
# identifier, and the gate stays absolute.
banned_sinks='innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval[[:space:]]*\(|new[[:space:]]+Function[[:space:]]*\(|\.srcdoc'

hits=$(grep -nE "$banned_sinks" "$PAGE" || true)
if [ -n "$hits" ]; then
    echo "assert-dashboard-safe: FAIL: the page writes to an HTML-parsing sink" >&2
    printf '%s\n' "$hits" | sed "s|^|  $PAGE:|" >&2
    echo "" >&2
    echo "L2-DASH-003: insert dynamic values with textContent or" >&2
    echo "createTextNode only. A filesystem path is attacker-chosen input and" >&2
    echo "the operator's browser is the one session with authority here." >&2
    status=1
fi

# --- L2-DASH-002: nothing may be fetched from the network -----------------
#
# The service runs on an isolated network and ships as one executable. A page
# that pulls a stylesheet or a font from a CDN goes blank where it is deployed,
# and hands a third party script execution in the operator's browser where it
# does not.
banned_remote='https?://|//cdn\.|<link[^>]+href|<script[^>]+src|@import|fonts\.googleapis'

hits=$(grep -nEi "$banned_remote" "$PAGE" || true)
if [ -n "$hits" ]; then
    echo "assert-dashboard-safe: FAIL: the page references an external resource" >&2
    printf '%s\n' "$hits" | sed "s|^|  $PAGE:|" >&2
    echo "" >&2
    echo "L2-DASH-002: the dashboard must function with no network access." >&2
    status=1
fi

# --- the page must actually be the one that ships -------------------------
#
# A gate that scans a file nothing serves is the failure mode this project
# keeps finding in its own apparatus. src/dashboard.cpp is the only place the
# page exists, and router.cpp must be the thing that serves it.
if ! grep -q 'dashboard_html()' src/router.cpp; then
    echo "assert-dashboard-safe: FAIL: router.cpp does not serve dashboard_html()" >&2
    echo "  this gate would then be scanning a page nobody can reach" >&2
    status=1
fi

if [ "$status" -ne 0 ]; then
    exit 1
fi

echo "dashboard-safe OK: no HTML sinks, no external resources, page is served"
