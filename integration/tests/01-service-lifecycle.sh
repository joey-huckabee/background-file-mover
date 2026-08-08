#!/bin/sh
# Phase 1: the service lifecycle as systemd sees it.
#
# This is the test that retires the largest open risk in the project. Every
# other tier proves the daemon works when a test starts it in-process. None of
# them can say whether systemd can start it, whether Type=notify readiness is
# what systemd observes, whether a bad config fails the unit at ExecStartPre,
# or whether the drain on stop actually completes.
#
# Runs ON THE TARGET HOST, over SSH, driven by run-all.sh. Knows nothing about
# how the host was provisioned.
#
# Usage:  sh 01-service-lifecycle.sh
set -eu

# No path to the binary here on purpose: every assertion below asks systemd what
# it actually did, rather than inspecting the thing systemd was asked to run.
UNIT=file-mover.service
CONF=/etc/file-mover/file-mover.ini
PORT=8080

# Private scratch directory rather than fixed /tmp names. The failure list is
# read back at the end to decide this script's exit status, so a stale or
# unwritable file at a predictable path does not just lose output -- it decides
# whether the suite passes. Ownership is the realistic way that happens: run
# once as root, once as a user, and the second run inherits the first's verdict.
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT INT TERM
FAILURES="$TMP/failures"
CONF_BAK="$TMP/fm-conf.bak"

pass() { echo "  ok   $1"; }
fail() { echo "  FAIL $1" >&2; echo "$1" >> "$FAILURES"; }

: > "$FAILURES"

echo "== 01 service lifecycle =="

# --- it is running at all -------------------------------------------------
if systemctl is-active --quiet "$UNIT"; then
    pass "unit is active"
else
    fail "unit is not active"
    systemctl status "$UNIT" --no-pager --lines=30 || true
    exit 1
fi

# --- Type=notify: systemd's own view -------------------------------------
#
# THE assertion this whole environment exists for. With Type=simple systemd
# would report the service active the moment exec returned -- before the port
# was open. Asking systemd for the unit's Type and confirming it reached
# "running" rather than merely "start" is the only way to check the readiness
# protocol from the outside.
type_is=$(systemctl show -p Type --value "$UNIT")
if [ "$type_is" = "notify" ]; then
    pass "unit is Type=notify"
else
    fail "unit is Type=$type_is, expected notify"
fi

substate=$(systemctl show -p SubState --value "$UNIT")
if [ "$substate" = "running" ]; then
    pass "systemd observed readiness (SubState=running)"
else
    fail "SubState=$substate, expected running -- READY=1 may not have arrived"
fi

# --- the port is actually open --------------------------------------------
if curl -fsS --max-time 5 "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then
    pass "control plane answers /healthz"
else
    fail "control plane did not answer on port $PORT"
fi

if curl -fsS --max-time 5 "http://127.0.0.1:$PORT/api/status" | grep -q '"running":true'; then
    pass "status reports running"
else
    fail "status did not report running"
fi

# --- the dashboard is served ----------------------------------------------
if curl -fsS --max-time 5 "http://127.0.0.1:$PORT/" | head -1 | grep -q 'DOCTYPE html'; then
    pass "dashboard is served"
else
    fail "dashboard was not served"
fi

# --- it runs as the service account, not root -----------------------------
main_pid=$(systemctl show -p MainPID --value "$UNIT")
if [ -n "$main_pid" ] && [ "$main_pid" != "0" ]; then
    owner=$(ps -o user= -p "$main_pid" | tr -d ' ')
    if [ "$owner" = "file-mover" ]; then
        pass "running as the file-mover account"
    else
        fail "running as '$owner', expected file-mover"
    fi
else
    fail "no MainPID"
fi

# --- the hardening in the unit is real ------------------------------------
#
# Each of these is a claim deploy/systemd/file-mover.service makes. systemd
# reports what it actually applied, which is not always what was asked for --
# a directive it does not understand is ignored with a warning nobody reads.
for pair in "NoNewPrivileges=yes" "ProtectSystem=strict" "PrivateTmp=yes" "ProtectHome=yes" "UMask=0077"; do
    key=${pair%%=*}
    want=${pair#*=}
    got=$(systemctl show -p "$key" --value "$UNIT")
    # systemd normalises booleans and prints UMask in octal without a leading 0
    case "$key:$got" in
        UMask:0077|UMask:77) got=yes; want=yes ;;
        *:yes|*:strict) : ;;
    esac
    if [ "$got" = "$want" ]; then
        pass "$key is $want"
    else
        fail "$key is '$got', expected '$want'"
    fi
done

cap=$(systemctl show -p CapabilityBoundingSet --value "$UNIT")
if [ -z "$cap" ] || [ "$cap" = "" ]; then
    pass "CapabilityBoundingSet is empty"
else
    fail "CapabilityBoundingSet is '$cap', expected empty"
fi

# --- SELinux recorded no denials ------------------------------------------
#
# The reason this lab is a RHEL host at all. A denial here is a FINDING -- it
# means the service needs a policy module before it can be deployed -- not a
# broken test.
if command -v ausearch >/dev/null 2>&1; then
    denials=$(ausearch -m AVC -ts recent 2>/dev/null | grep -c 'denied' || true)
    if [ "${denials:-0}" -eq 0 ]; then
        pass "no recent SELinux denials"
    else
        fail "$denials SELinux denial(s) recorded -- see: ausearch -m AVC -ts recent"
        ausearch -m AVC -ts recent 2>/dev/null | tail -20 || true
    fi
else
    echo "  SKIP ausearch unavailable; SELinux denials unchecked"
fi

# --- a bad configuration fails the unit at ExecStartPre -------------------
#
# L2-CTL-019. Tested by actually breaking the config and asking systemd to
# start, because that is the path an operator hits: --check passing in a shell
# proves less than the unit refusing to come up.
echo "  (restarting with a deliberately broken config)"
cp "$CONF" "$CONF_BAK"
printf '\n[nonsense]\nkey = value\n' >> "$CONF"
systemctl stop "$UNIT"
if systemctl start "$UNIT" 2>/dev/null; then
    fail "the unit started with an invalid configuration"
    systemctl stop "$UNIT" || true
else
    pass "ExecStartPre refused an invalid configuration"
fi
cp "$CONF_BAK" "$CONF"

# --- a clean restart still works ------------------------------------------
if systemctl start "$UNIT" && systemctl is-active --quiet "$UNIT"; then
    pass "service starts again with the configuration restored"
else
    fail "service did not recover after the bad-config test"
    journalctl -u "$UNIT" --no-pager --lines=30 || true
fi

# --- stop drains rather than being killed ---------------------------------
#
# TimeoutStopSec is 120 because a move past its commit point must finish. If
# stop took the full timeout, systemd killed it -- which means shutdown did not
# drain, and a move could have been torn in half.
start_s=$(date +%s)
systemctl stop "$UNIT"
end_s=$(date +%s)
elapsed=$((end_s - start_s))
if [ "$elapsed" -lt 100 ]; then
    pass "stop completed in ${elapsed}s (drained, not killed)"
else
    fail "stop took ${elapsed}s -- systemd probably SIGKILLed it at TimeoutStopSec"
fi

result=$(systemctl show -p Result --value "$UNIT")
if [ "$result" = "success" ]; then
    pass "unit result is success"
else
    fail "unit result is '$result', expected success"
fi

# Leave the host as we found it.
systemctl start "$UNIT" || true

if [ -s "$FAILURES" ]; then
    echo ""
    echo "FAILURES:"
    sed 's/^/  /' "$FAILURES"
    exit 1
fi
echo "01 service lifecycle: all checks passed"
