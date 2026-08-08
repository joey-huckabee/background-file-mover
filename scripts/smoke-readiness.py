#!/usr/bin/env python3
"""End-to-end smoke test for sd_notify readiness (L2-CTL-011, L2-CTL-012).

The unit tests prove notify_service_manager puts the right bytes on the wire.
They do NOT prove the daemon sends READY=1 at the right MOMENT, and that is the
entire claim Type=notify makes to systemd: when READY arrives, the service can
be used. If READY were sent before the listener was accepting, every unit
ordered After= this one would start against a service that refuses connections,
and nothing in the C++ test suite would notice.

So this drives the real binary:

  1. bind a datagram socket and hand its path to the daemon as $NOTIFY_SOCKET
  2. start the daemon
  3. wait for READY=1 -- and the instant it arrives, before anything else,
     connect to the HTTP port and issue a real request. A refused connection
     here means READY was premature.
  4. SIGTERM, expect STOPPING=1 and exit 0

Run by hand or from CI. Requires only the standard library.
"""

import os
import signal
import socket
import subprocess
import sys
import tempfile
import time

TIMEOUT = 20.0


def fail(msg):
    print("smoke-readiness: FAIL: %s" % msg, file=sys.stderr)
    sys.exit(1)


def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def recv_notification(sock, deadline):
    """Read one datagram, or None on timeout."""
    while time.time() < deadline:
        sock.settimeout(max(0.05, deadline - time.time()))
        try:
            return sock.recv(4096).decode("utf-8", "replace")
        except socket.timeout:
            return None
    return None


def check_ordering(daemon):
    """READY=1 must never be sent when the listener never opened.

    Deterministic, where connecting-on-READY is not. The port is occupied
    before the daemon starts, so its bind is GUARANTEED to fail:

      correct code -- bind fails, start fails, no READY is ever sent
      premature READY -- READY is sent, and only then does the bind fail

    There is no race to lose: the daemon cannot reach a working listener no
    matter how fast it is, so any READY at all is proof the notification came
    before the socket was up.
    """
    tmp = tempfile.mkdtemp(prefix="fm-order-")
    notify_path = os.path.join(tmp, "notify.sock")
    cfg_path = os.path.join(tmp, "file-mover.ini")
    db_path = os.path.join(tmp, "state.db")

    # Hold the port for the duration.
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    port = blocker.getsockname()[1]

    with open(cfg_path, "w") as fh:
        fh.write(
            "[http]\nbind = 127.0.0.1\nport = %d\n\n"
            "[storage]\ndatabase_path = %s\n" % (port, db_path)
        )

    notify = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    notify.bind(notify_path)

    env = dict(os.environ)
    env["NOTIFY_SOCKET"] = notify_path

    proc = subprocess.Popen(
        [daemon, "--config", cfg_path],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        try:
            rc = proc.wait(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            fail("daemon did not exit though its port was already taken")

        if rc == 0:
            fail("daemon exited 0 though it could not bind its port")

        deadline = time.time() + 1.0
        while time.time() < deadline:
            msg = recv_notification(notify, deadline)
            if msg is None:
                break
            if "READY=1" in msg:
                fail(
                    "READY=1 was sent although the listener never opened -- "
                    "readiness is being reported before the socket accepts, "
                    "so dependent units would start against a dead port"
                )
        print("smoke-readiness: ok: no READY=1 when the listener never opened")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        notify.close()
        blocker.close()
        for path in (notify_path, cfg_path, db_path):
            try:
                os.unlink(path)
            except OSError:
                pass
        try:
            os.rmdir(tmp)
        except OSError:
            pass


def main():
    if len(sys.argv) < 2:
        print("usage: %s <path-to-filemover>" % sys.argv[0], file=sys.stderr)
        return 2
    daemon = os.path.abspath(sys.argv[1])
    if not os.access(daemon, os.X_OK):
        fail("not executable: %s" % daemon)

    tmp = tempfile.mkdtemp(prefix="fm-smoke-")
    notify_path = os.path.join(tmp, "notify.sock")
    db_path = os.path.join(tmp, "state.db")
    cfg_path = os.path.join(tmp, "file-mover.ini")
    port = free_port()

    with open(cfg_path, "w") as fh:
        fh.write(
            "[http]\nbind = 127.0.0.1\nport = %d\n\n"
            "[storage]\ndatabase_path = %s\n" % (port, db_path)
        )

    notify = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    notify.bind(notify_path)

    env = dict(os.environ)
    env["NOTIFY_SOCKET"] = notify_path
    # A watchdog interval short enough that the test sees pings without
    # waiting, and WATCHDOG_PID set to the child so the guard admits them.
    env["WATCHDOG_USEC"] = "400000"  # 0.4 s -> pings every 0.2 s

    proc = subprocess.Popen(
        [daemon, "--config", cfg_path],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    deadline = time.time() + TIMEOUT
    ready_seen = False
    try:
        while time.time() < deadline:
            msg = recv_notification(notify, deadline)
            if msg is None:
                break
            if "READY=1" in msg:
                ready_seen = True
                break
            if proc.poll() is not None:
                break

        if not ready_seen:
            out = b""
            if proc.poll() is not None:
                out = proc.stdout.read()
            fail(
                "no READY=1 within %.0fs (exit=%s, output=%r)"
                % (TIMEOUT, proc.poll(), out[:2000])
            )

        # A liveness check, NOT the ordering proof. Connecting the instant
        # READY arrives looks like it would catch a premature READY, and it
        # does not: the daemon binds microseconds later and wins the race
        # every time. Verified by injecting a premature READY -- this passed.
        # The real ordering proof is check_ordering() below.
        try:
            conn = socket.create_connection(("127.0.0.1", port), timeout=5.0)
        except OSError as exc:
            fail(
                "READY=1 arrived but the port was not accepting: %s "
                "(a unit ordered After= this one would fail)" % exc
            )
        conn.sendall(b"GET /healthz HTTP/1.1\r\nHost: localhost\r\n\r\n")
        response = conn.recv(4096)
        conn.close()
        if b"200" not in response.split(b"\r\n")[0]:
            fail("healthz did not answer 200: %r" % response[:200])
        print("smoke-readiness: ok: READY=1 arrived and the service answered")

        # Watchdog pings. WATCHDOG_PID is left unset above, which the daemon
        # treats as "the interval is mine" -- so with WATCHDOG_USEC=0.4s it
        # must ping about every 0.2s, and two pings inside two seconds is a
        # generous floor. Asserted rather than reported: an unfired watchdog
        # thread means systemd kills the service every WatchdogSec, and the
        # symptom is a service that restarts forever for no visible reason.
        pings = 0
        ping_deadline = time.time() + 2.0
        while time.time() < ping_deadline:
            msg = recv_notification(notify, ping_deadline)
            if msg and "WATCHDOG=1" in msg:
                pings += 1
                if pings >= 2:
                    break
        if pings < 2:
            fail("only %d WATCHDOG=1 pings in 2s with a 0.2s interval" % pings)
        print("smoke-readiness: ok: watchdog pinged %d times" % pings)

        # Shutdown.
        proc.send_signal(signal.SIGTERM)
        stop_deadline = time.time() + TIMEOUT
        stopping_seen = False
        while time.time() < stop_deadline:
            msg = recv_notification(notify, stop_deadline)
            if msg is None:
                break
            if "STOPPING=1" in msg:
                stopping_seen = True
                break
        if not stopping_seen:
            fail("no STOPPING=1 after SIGTERM")

        try:
            rc = proc.wait(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            fail("daemon did not exit within %.0fs of SIGTERM" % TIMEOUT)
        if rc != 0:
            out = proc.stdout.read()
            fail("daemon exited %d after SIGTERM (output=%r)" % (rc, out[:2000]))
        print("smoke-readiness: ok: STOPPING=1 sent and the daemon exited 0")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        notify.close()
        for path in (notify_path, cfg_path, db_path, db_path + ".lock"):
            try:
                os.unlink(path)
            except OSError:
                pass
        try:
            os.rmdir(tmp)
        except OSError:
            pass

    check_ordering(daemon)
    check_singleton(daemon)

    print("smoke-readiness: PASS")
    return 0


def check_singleton(daemon):
    """A second daemon on one database must refuse to start (L2-CTL-008).

    Tested against the real binary because this is what an operator meets: a
    unit restarted while the old process is still draining, or a hand-run
    daemon against a live service. The C++ tests cover Service::start; this
    covers the process, including that it exits non-zero so systemd sees a
    failure rather than a second instance it thinks is fine.
    """
    tmp = tempfile.mkdtemp(prefix="fm-single-")
    db_path = os.path.join(tmp, "state.db")
    cfg_path = os.path.join(tmp, "file-mover.ini")
    first_port = free_port()
    second_port = free_port()

    def write_cfg(path, port):
        with open(path, "w") as fh:
            fh.write(
                "[http]\nbind = 127.0.0.1\nport = %d\n\n"
                "[storage]\ndatabase_path = %s\n" % (port, db_path)
            )

    write_cfg(cfg_path, first_port)
    second_cfg = os.path.join(tmp, "second.ini")
    # A DIFFERENT port, so a refusal cannot be blamed on the address already
    # being in use. The only thing the two share is the database.
    write_cfg(second_cfg, second_port)

    env = dict(os.environ)
    env.pop("NOTIFY_SOCKET", None)

    first = subprocess.Popen(
        [daemon, "--config", cfg_path],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        # Wait until it is genuinely up, or the second one would be refused
        # for the wrong reason.
        deadline = time.time() + TIMEOUT
        up = False
        while time.time() < deadline:
            try:
                socket.create_connection(("127.0.0.1", first_port),
                                         timeout=0.5).close()
                up = True
                break
            except OSError:
                if first.poll() is not None:
                    break
                time.sleep(0.05)
        if not up:
            fail("first daemon never came up (exit=%s)" % first.poll())

        # The expected outcome is a prompt non-zero exit. Timing out is the
        # headline failure, not an error in the harness: a second daemon that
        # keeps running is exactly the corruption this prevents, and it must
        # be reported as that rather than as a traceback.
        try:
            second = subprocess.run(
                [daemon, "--config", second_cfg],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            fail(
                "a second daemon started against a live database and kept "
                "running -- two instances are now sharing one state database"
            )
        if second.returncode == 0:
            fail("a second daemon started against a live database")
        output = second.stdout.decode("utf-8", "replace")
        if "already running" not in output:
            fail(
                "second daemon failed, but not with the singleton message: %r"
                % output[:400]
            )
        print("smoke-readiness: ok: a second daemon is refused (%s)"
              % output.strip().splitlines()[-1][:90])
    finally:
        if first.poll() is None:
            first.terminate()
            try:
                first.wait(timeout=TIMEOUT)
            except subprocess.TimeoutExpired:
                first.kill()
                first.wait()

    # The lock must not outlive its holder: after the first exits, a fresh
    # start succeeds. Otherwise every restart would be an outage.
    third = subprocess.run(
        [daemon, "--config", cfg_path, "--check"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        timeout=TIMEOUT,
    )
    if third.returncode != 0:
        fail("--check failed after the holder exited: %r"
             % third.stdout.decode("utf-8", "replace")[:400])

    third = subprocess.Popen(
        [daemon, "--config", cfg_path],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.time() + TIMEOUT
        restarted = False
        while time.time() < deadline:
            try:
                socket.create_connection(("127.0.0.1", first_port),
                                         timeout=0.5).close()
                restarted = True
                break
            except OSError:
                if third.poll() is not None:
                    break
                time.sleep(0.05)
        if not restarted:
            fail(
                "could not restart after the lock holder exited (exit=%s) -- "
                "the lock outlived its process" % third.poll()
            )
        print("smoke-readiness: ok: the lock does not outlive its holder")
    finally:
        if third.poll() is None:
            third.terminate()
            try:
                third.wait(timeout=TIMEOUT)
            except subprocess.TimeoutExpired:
                third.kill()
                third.wait()
        for path in (cfg_path, second_cfg, db_path, db_path + ".lock"):
            try:
                os.unlink(path)
            except OSError:
                pass
        try:
            os.rmdir(tmp)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
