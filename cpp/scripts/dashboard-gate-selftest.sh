#!/bin/sh
# Negative test for assert-dashboard-safe.sh.
#
# Run by hand, not from CI -- it edits src/dashboard.cpp and src/router.cpp in
# place and would race a concurrent build. Kept rather than done once, for the
# reason gate-selftest.sh is: the next person to add an exception to that gate
# needs a way to see what they have let through.
set -u
cd "$(dirname "$0")/.."

GATE="sh scripts/assert-dashboard-safe.sh"
PAGE=src/dashboard.cpp
ROUTER=src/router.cpp

page_bak=$(mktemp)
router_bak=$(mktemp)
cp "$PAGE" "$page_bak"
cp "$ROUTER" "$router_bak"
restore() { cp "$page_bak" "$PAGE"; cp "$router_bak" "$ROUTER"; }
trap 'restore; rm -f "$page_bak" "$router_bak"' EXIT INT TERM

fails=0

if $GATE >/dev/null 2>&1; then
    echo "ok   (baseline clean)"
else
    echo "FAIL (baseline): the tree already fails the gate" >&2
    $GATE
    exit 1
fi

expect_fail() {
    label=$1
    if $GATE >/dev/null 2>&1; then
        echo "FAIL ($label): gate passed with the defect injected"
        fails=$((fails + 1))
    else
        echo "ok   ($label)"
    fi
    restore
}

# L2-DASH-003: the sinks, one at a time. Each is a distinct way to hand a
# filename to the HTML parser, and a gate that catches only the famous one is
# a gate that gets bypassed by the second-most-famous one.
sed -i 's|td.appendChild(document.createTextNode(|td.innerHTML = String(value); td.appendChild(document.createTextNode(|' "$PAGE"
expect_fail "innerHTML assignment"

sed -i 's|while (node.firstChild) { node.removeChild(node.firstChild); }|node.innerHTML = "";|' "$PAGE"
expect_fail "innerHTML = \"\" (the harmless-looking one)"

sed -i 's|body.appendChild(row);|body.insertAdjacentHTML("beforeend", "<tr></tr>");|' "$PAGE"
expect_fail "insertAdjacentHTML"

sed -i 's|var d = new Date(ms);|var d = eval("new Date(ms)");|' "$PAGE"
expect_fail "eval"

sed -i 's|<title>Background File Mover</title>|<title>x</title><script src="https://cdn.example/x.js"></script>|' "$PAGE"
expect_fail "external script"

sed -i 's|<style>|<link rel="stylesheet" href="https://fonts.googleapis.com/x"><style>|' "$PAGE"
expect_fail "external stylesheet"

sed -i 's|:root { color-scheme: light dark; }|@import url("https://example/x.css");|' "$PAGE"
expect_fail "@import"

# The gate must also refuse to pass while scanning a page nobody serves.
sed -i 's|dashboard_html()|unreachable_page()|g' "$ROUTER"
expect_fail "page not wired into the router"

if $GATE >/dev/null 2>&1; then
    echo "ok   (clean tree still passes)"
else
    echo "FAIL (restore): the tree did not come back clean"
    fails=$((fails + 1))
fi

echo "selftest failures: $fails"
exit $fails
