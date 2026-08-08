#!/bin/sh
# Gate: the systemd unit is valid, and its ExecStart matches the flags the
# daemon actually accepts.
#
# A unit file is configuration that nothing compiles and no test imports, so a
# typo in it survives every other gate in this repository and is discovered by
# an operator, at deploy time, on the target. `systemd-analyze verify` catches
# unknown keys, bad directive values and malformed sections; running the real
# binary with the unit's own arguments catches the rest -- a renamed flag, a
# subcommand that moved, a --check that no longer exits zero.
#
# Skips (exit 0) when systemd-analyze is unavailable, which is the case in
# containers without systemd. That is a deliberate hole: making it fatal would
# mean the gate could not run at all in the GCC 4.8.5 image. It is announced
# rather than silent, because a gate that skips quietly is the failure mode
# this project has hit six times.

set -eu

UNIT=${1:-deploy/systemd/file-mover.service}
DAEMON=${2:-}

if [ ! -f "$UNIT" ]; then
    echo "assert-unit-valid: FAIL: no such unit file: $UNIT" >&2
    exit 1
fi

status=0

# --- 1. syntax and directive validity ------------------------------------

if command -v systemd-analyze >/dev/null 2>&1; then
    # verify reports on every unit it pulls in, including the host's own
    # broken ones, and its exit status does not distinguish. So filter to
    # complaints about THIS unit, and ignore the one that is expected on a
    # machine where the daemon is not installed at its deployed path.
    out=$(systemd-analyze verify "$UNIT" 2>&1 || true)
    problems=$(printf '%s\n' "$out" \
        | grep "$(basename "$UNIT")" \
        | grep -v 'is not executable: No such file or directory' \
        || true)
    if [ -n "$problems" ]; then
        echo "assert-unit-valid: FAIL: systemd-analyze rejected $UNIT" >&2
        printf '%s\n' "$problems" >&2
        status=1
    else
        echo "assert-unit-valid: ok: $UNIT passes systemd-analyze verify"
    fi
else
    echo "assert-unit-valid: SKIP: systemd-analyze unavailable (unit syntax unverified)"
fi

# --- 2. the ExecStartPre arguments still work against the real binary ----

if [ -n "$DAEMON" ] && [ -x "$DAEMON" ]; then
    args=$(grep '^ExecStartPre=' "$UNIT" | head -1 | sed 's/^ExecStartPre=[^ ]*//')

    # Checked BEFORE the binary is invoked, and fatal to the rest of this
    # section. Without --check the command below is not a validation, it is
    # the service: it binds a port and runs until killed, so the gate hangs
    # instead of failing. Found by the gate's own negative test, which sat
    # there for two minutes.
    case "$args" in
        *--check*) ;;
        *)
            echo "assert-unit-valid: FAIL: ExecStartPre does not pass --check" >&2
            echo "  L2-CTL-019 requires configuration validation before start." >&2
            echo "  (skipping the argument check: without --check, running the" >&2
            echo "   unit's command would start the service, not validate it.)" >&2
            exit 1
            ;;
    esac

    # Run the daemon with the unit's own arguments against a known-good
    # config, so a flag the unit uses but the binary dropped is caught here
    # rather than by systemd refusing to start the unit.
    tmp=$(mktemp -d)
    trap 'rm -rf "$tmp"' EXIT
    mkdir -p "$tmp/state"
    # The shipped reference config, with only the database path redirected --
    # so this checks the file that actually ships, not a fixture that agrees
    # with the parser by construction.
    #
    # Matched against the EXACT deployed default rather than `database_path =
    # anything`. A blanket rewrite would replace whatever is on that line,
    # including a value that is empty or malformed, so the gate would repair
    # the defect it exists to find. Caught by the selftest's fourth case.
    sed "s#^database_path *= */var/lib/file-mover/file-mover.db *\$#database_path = $tmp/state/file-mover.db#" \
        config/file-mover.ini > "$tmp/file-mover.ini"

    # Substitute the unit's config path for the temporary one; everything else
    # about the invocation is taken verbatim from the unit.
    real_args=$(printf '%s' "$args" \
        | sed "s#/etc/file-mover/file-mover.ini#$tmp/file-mover.ini#")
    # Bounded even though --check is required above: a gate that can hang is a
    # gate that stops CI rather than failing it, and "--check always exits" is
    # an assumption, not a guarantee.
    runner=""
    if command -v timeout >/dev/null 2>&1; then
        runner="timeout 30"
    fi

    # shellcheck disable=SC2086
    if $runner "$DAEMON" $real_args >"$tmp/out" 2>&1; then
        echo "assert-unit-valid: ok: daemon accepts the unit's ExecStartPre arguments"
    else
        echo "assert-unit-valid: FAIL: daemon rejected the unit's own arguments" >&2
        echo "  ran: $DAEMON $real_args" >&2
        sed 's/^/  /' "$tmp/out" >&2
        status=1
    fi
else
    echo "assert-unit-valid: SKIP: daemon binary not supplied (arguments unverified)"
fi

exit $status
