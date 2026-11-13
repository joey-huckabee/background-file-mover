#!/usr/bin/env python3
"""Disposable File Mover dashboard demo for WSL (development and demos only).

Builds a native binary with the SLES gate's SQLite options, creates throwaway
state, TLS certificates and an admin account, runs the service as a transient
systemd unit, and submits synthetic jobs so the dashboard can be watched
updating live. Not a qualified build, deployment or real data.

From Windows use the wrapper:   scripts\\demo\\fm-demo.cmd COMMAND [OPTIONS]
Inside WSL (as root):           python3 scripts/demo/fm-demo.py COMMAND [OPTIONS]

Commands:
  build                 Build the demo binary from the WSL clone.
  setup [--jobs N]      Fresh demo state with N delivered jobs (default 10).
  start | stop | status Run, stop or inspect the demo service.
  add-job [--count N] [--interval S] [--size-mb M] [--files K]
                        Submit synthetic jobs while the dashboard is open.
  reset                 Stop the service and delete all demo state.
"""
import argparse, json, os, pwd, shutil, socket, stat, subprocess, sys, time, uuid
from pathlib import Path

USER = os.environ.get("FM_DEMO_USER", "joey")
try:
    ACCOUNT = pwd.getpwnam(USER)
except KeyError:
    sys.exit(f"fm-demo: no WSL account named {USER}")
if ACCOUNT.pw_uid == 0:
    sys.exit("fm-demo: the demo user must not be root")
REPO = Path(os.environ.get("FM_DEMO_REPO", f"{ACCOUNT.pw_dir}/GIT/background-file-mover-testing"))
# Fixed, never configurable: every destructive step stays inside this directory.
DATA = Path(ACCOUNT.pw_dir) / "fm-demo"
MARKER = DATA / ".fm-demo"
EXE = DATA / "target/release/file-mover"
ROOT = DATA / "run"
CONFIG = ROOT / "config.json"
UNIT = "fm-demo-review"
PRODUCER_PORT, ADMIN_PORT = 18080, 9443
PASSWORD = os.environ.get("FM_DEMO_PASSWORD", "review-demo-2026")
SQLITE_FLAGS = ("-USQLITE_THREADSAFE -DSQLITE_THREADSAFE=1 -DSQLITE_OMIT_LOAD_EXTENSION -DSQLITE_DQS=0 "
                "-USQLITE_DEFAULT_MEMSTATUS -DSQLITE_DEFAULT_MEMSTATUS=0 -DSQLITE_ENABLE_API_ARMOR")
HERE = Path(__file__).resolve().parent
NAMESPACE = HERE.parent / "dev-wsl-namespace.sh"


def say(text):
    print(f"fm-demo: {text}", flush=True)


def fail(text):
    sys.exit(f"fm-demo: {text}")


def is_root():
    return os.geteuid() == 0


def own_dir(path):
    """True if `path` is a real directory (no symlink) owned by the demo user."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return False
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != ACCOUNT.pw_uid:
        fail(f"{path} is not a directory owned by {USER}; refusing")
    return True


def demo_data(create=False):
    """Validate (or create) the dedicated demo directory and its marker."""
    if Path(os.path.realpath(DATA)) != DATA:
        fail(f"{DATA} must not involve symlinks; refusing")
    if not own_dir(DATA):
        if not create:
            fail(f"no demo directory at {DATA}; use: fm-demo build")
        if is_root():
            fail("create the demo directory as the demo user (fm-demo build)")
        DATA.mkdir(mode=0o700)
    if not MARKER.exists():
        if not create:
            fail(f"{DATA} has no {MARKER.name} marker; not created by fm-demo, refusing")
        MARKER.write_text("Disposable File Mover demo data; managed by scripts/demo/fm-demo.py\n")
    elif os.lstat(MARKER).st_uid != ACCOUNT.pw_uid or os.path.islink(MARKER):
        fail(f"{MARKER} is not owned by {USER}; refusing")
    if os.path.lexists(ROOT):
        own_dir(ROOT)


def state_unowned():
    """True only if no mover instance or surviving worker owns the demo state.
    Uses the mover's own instance lock (--check-state), not process names."""
    if not (ROOT / "state/jobs.sqlite").exists():
        return True  # nothing was ever initialized, so nothing can own it
    if not EXE.exists():
        fail("cannot verify that no demo service is running without the demo binary")
    args = [str(EXE), "--check-state", str(CONFIG)]
    r = subprocess.run(args, capture_output=True) if not is_root() else as_user(args, capture_output=True)
    if r.returncode == 0:
        return True
    text = r.stderr.decode(errors="replace").strip()
    if "owns state" in text:
        return False
    fail(f"could not verify the demo state is unowned: {text}")


def unit_inactive():
    r = subprocess.run(["systemctl", "is-active", UNIT], capture_output=True, text=True)
    return r.stdout.strip() in ("inactive", "failed", "unknown", "")


def as_user(args, **kw):
    """Run as the demo user in the alias-free mount namespace."""
    return subprocess.run(["bash", str(NAMESPACE), *args], **kw)


def inner(command, extra):
    """Re-run this script as the demo user inside the namespace."""
    if not is_root():
        fail("run through scripts\\demo\\fm-demo.cmd (or as root in WSL)")
    demo_data()
    r = as_user(["python3", str(Path(__file__).resolve()), command, "--inner", *extra])
    sys.exit(r.returncode)


# ---------- build ----------
def cmd_build(_):
    if is_root():
        r = subprocess.run(["setpriv", f"--reuid={USER}", f"--regid={USER}", "--init-groups",
                            "env", f"HOME=/home/{USER}", "python3", str(Path(__file__).resolve()), "build"])
        sys.exit(r.returncode)
    env = dict(os.environ, LIBSQLITE3_FLAGS=SQLITE_FLAGS, CARGO_TARGET_DIR=str(DATA / "target"),
               PATH=f"{Path.home()}/.cargo/bin:" + os.environ.get("PATH", ""))
    head = subprocess.run(["git", "-C", str(REPO), "log", "--oneline", "-1"], capture_output=True, text=True)
    demo_data(create=True)
    say(f"building from {REPO} at {head.stdout.strip() or 'unknown commit'}")
    subprocess.run(["cargo", "build", "-q", "--release", "-p", "file-mover"], cwd=REPO / "rust", env=env, check=True)
    say(f"built {EXE}")


# ---------- service helpers (inside the namespace, as the user) ----------
def run_exe(*args, stdin=None):
    r = subprocess.run([str(EXE), *args], input=stdin, capture_output=True)
    if r.returncode:
        fail(f"{args[0]} failed: {r.stderr.decode(errors='replace').strip()}")


def start_child():
    log = ROOT / "service.log"
    offset = log.stat().st_size if log.exists() else 0
    child = subprocess.Popen([str(EXE), str(CONFIG)], stdout=open(log, "ab"), stderr=subprocess.STDOUT)
    for _ in range(300):
        if b"Ready on" in log.read_bytes()[offset:]:
            return child
        if child.poll() is not None:
            fail(log.read_text(errors="replace")[offset:])
        time.sleep(0.05)
    fail("service did not become ready")


def stop_child(child):
    run_exe("--stop", str(CONFIG))
    child.wait(timeout=20)


def http(sock, method, path, body=b""):
    head = (f"{method} {path} HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n\r\n").encode()
    sock.sendall(head + body)
    out = b""
    while chunk := sock.recv(65536):
        out += chunk
    head, _, payload = out.partition(b"\r\n\r\n")
    return int(head.split()[1]), json.loads(payload or b"null")


def submit(files, sizes):
    current = ROOT / "source/current"
    for rel, size in zip(files, sizes):
        path = current / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(path.parent, 0o700)
        with open(path, "wb") as f:
            remaining = size
            while remaining:
                chunk = min(remaining, 4 << 20)
                f.write(os.urandom(chunk))
                remaining -= chunk
    body = {"recording_id": str(uuid.uuid4()), "generator_id": "recorder", "source_directory": str(current),
            "files": files, "expected_sizes_bytes": {k: str(v) for k, v in zip(files, sizes)}}
    try:
        s = socket.create_connection(("127.0.0.1", PRODUCER_PORT), timeout=30)
    except OSError:
        fail("demo service is not running; use: fm-demo start")
    try:
        return http(s, "POST", "/api/v2/jobs", json.dumps(body).encode())
    finally:
        s.close()


def job_files(name, count, size_mb):
    names = ["video.mkv", "audio.wav", "notes.txt", "metadata.json", "camera2.mkv"]
    files, sizes = [], []
    for i in range(count):
        base = names[i] if i < len(names) else f"part-{i}.bin"
        files.append(f"{name}/{base}")
        sizes.append(int(size_mb * (1 << 20)) if i == 0 else max(1, int(size_mb * (1 << 20)) // (4 * (i + 1))))
    return files, sizes


# ---------- setup ----------
def reap(child):
    """Stop a service this command started, and wait for it to exit."""
    if child is None or child.poll() is not None:
        return
    subprocess.run([str(EXE), "--stop", str(CONFIG)], capture_output=True)
    try:
        child.wait(timeout=20)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()


def cmd_setup(a):
    if not a.inner:
        if not unit_inactive():
            fail("demo service is running; use: fm-demo stop (or reset)")
        if not EXE.exists():
            fail("no demo binary; use: fm-demo build")
        inner("setup", ["--jobs", str(a.jobs)])
    if is_root():
        fail("internal setup must not run as root")
    demo_data()
    if os.path.lexists(ROOT):
        if not state_unowned():
            fail("a mover still owns the demo state; stop it first")
        shutil.rmtree(ROOT)
    child = None
    try:
        _setup_state(a)
        child = start_child()  # records the active source pairing account commands need
        stop_child(child)
        child = None
        _setup_account()
        child = start_child()
        for n in range(a.jobs):
            files, sizes = job_files(f"session-{n + 1:03d}", 2 + n % 2, 0.02 + (n % 7) * 0.01)
            status, body = submit(files, sizes)
            if status != 202:
                fail(f"job {n + 1}: {status} {body}")
        time.sleep(2)
        stop_child(child)
        child = None
    finally:
        reap(child)
    say(f"ready with {a.jobs} jobs; next: fm-demo start")


def _setup_state(a):
    ROOT.mkdir(parents=True)
    os.chmod(ROOT, 0o700)
    for name in ["state", "operator", "accounts", "admin-tls", "source", "source/current",
                 "source/.file-mover", "destination", "destination/.file-mover"]:
        (ROOT / name).mkdir()
        os.chmod(ROOT / name, 0o700)
    binding = lambda role, root, endpoint, marker: {"version": 3, "coordinator_id": "demo-owner", "root_id": root,
        "endpoint_id": endpoint, "marker_id": marker, "filesystem": "local", "role": role}
    source = binding("source", "local-source", "demo-local", "demo-marker")
    destination = binding("destination", "configured-local", "demo-local-destination", "demo-destination-marker")
    for name, b, marker in [("source", source, "source-binding.json"), ("destination", destination, "destination-binding.json")]:
        area = ROOT / name / ".file-mover"
        (area / "coordinator.lock").write_bytes(b"")
        os.chmod(area / "coordinator.lock", 0o600)
        (area / marker).write_text(json.dumps(b))
        os.chmod(area / marker, 0o600)
    fixtures = DATA / "tls"
    shutil.rmtree(fixtures, ignore_errors=True)
    (DATA / "tls.tar").unlink(missing_ok=True)
    subprocess.run([sys.executable, str(REPO / "scripts/tls_proof_fixture.py"), "--output", str(fixtures),
                    "--archive", str(DATA / "tls.tar")], check=True, capture_output=True)
    for name in ["server.der", "server.key.der", "ca.der"]:
        shutil.copy(fixtures / name, ROOT / "admin-tls" / name)
        os.chmod(ROOT / "admin-tls" / name, 0o600 if name.endswith("key.der") else 0o400)
    config = {"bind": f"127.0.0.1:{PRODUCER_PORT}",
              "native_ingress": {"transport": "http", "operator_socket": str(ROOT / "operator/api.sock")},
              "generator_id": "recorder", "source_root": str(ROOT / "source"),
              "destination_root": str(ROOT / "destination"), "state_database": str(ROOT / "state/jobs.sqlite"),
              "source_binding": source, "destination_binding": destination, "shutdown_wait_seconds": 5}
    CONFIG.write_text(json.dumps(config))
    run_exe("--initialize-source", str(CONFIG))


def _setup_account():
    config = json.loads(CONFIG.read_text())
    run_exe("--admin-account-init", str(CONFIG), "--account-dir", str(ROOT / "accounts"), "--stdin",
            stdin=json.dumps({"username": "admin", "password": PASSWORD, "confirm_password": PASSWORD}).encode())
    config["admin_ingress"] = {"bind": f"127.0.0.1:{ADMIN_PORT}", "authority": f"localhost:{ADMIN_PORT}",
        "server_certificates": [str(ROOT / "admin-tls/server.der")], "server_key": str(ROOT / "admin-tls/server.key.der"),
        "server_ca_certificates": [str(ROOT / "admin-tls/ca.der")], "account_directory": str(ROOT / "accounts")}
    CONFIG.write_text(json.dumps(config))


# ---------- service control (root) ----------
def cmd_start(_):
    if not is_root():
        fail("run through scripts\\demo\\fm-demo.cmd (or as root in WSL)")
    demo_data()
    if not CONFIG.exists():
        fail("no demo state; use: fm-demo setup")
    if not unit_inactive():
        say("already running")
        return status_line()
    sock = ROOT / "operator/api.sock"
    if os.path.lexists(sock):
        # Left by a hard stop. Remove it only after the mover's own instance
        # lock proves nothing owns the demo state.
        if not state_unowned():
            fail("a mover still owns the demo state; not touching its socket")
        sock.unlink()
    log = DATA / "service-unit.log"
    subprocess.run(["systemd-run", f"--unit={UNIT}", "--collect", "--quiet",
                    f"--property=StandardOutput=append:{log}", f"--property=StandardError=append:{log}",
                    "bash", str(NAMESPACE), str(EXE), str(CONFIG)], check=True)
    for _ in range(100):
        if probe() == 200:
            return status_line()
        time.sleep(0.2)
    fail(f"service did not answer; see {log}")


def cmd_stop(_):
    if unit_inactive():
        say("not running")
        return
    r = subprocess.run(["systemctl", "stop", UNIT], capture_output=True, text=True)
    if r.returncode != 0 or not unit_inactive():
        fail(f"could not stop {UNIT}: {r.stderr.strip()}")
    say("stopped")


def probe():
    import ssl, http.client
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.set_alpn_protocols(["http/1.1"])  # the admin listener requires ALPN http/1.1
    try:
        c = http.client.HTTPSConnection("localhost", ADMIN_PORT, context=ctx, timeout=3)
        c.request("GET", "/")
        return c.getresponse().status
    except (OSError, http.client.HTTPException):
        return None


def status_line(_=None):
    active = subprocess.run(["systemctl", "is-active", UNIT], capture_output=True, text=True).stdout.strip()
    code = probe()
    say(f"service {active or 'inactive'}; dashboard {'up' if code == 200 else 'down'}")
    if code == 200:
        print(f"  open https://localhost:{ADMIN_PORT}/   sign in: admin / {PASSWORD}")


def cmd_add_job(a):
    if not a.inner:
        inner("add-job", ["--count", str(a.count), "--interval", str(a.interval),
                          "--size-mb", str(a.size_mb), "--files", str(a.files)])
    if is_root():
        fail("internal add-job must not run as root")
    demo_data()
    for i in range(a.count):
        name = f"demo-{time.strftime('%H%M%S')}-{uuid.uuid4().hex[:4]}"
        status, body = submit(*job_files(name, a.files, a.size_mb))
        if status == 202:
            say(f"job #{body['job_id']} accepted ({a.files} files, {a.size_mb:g} MiB main file)")
        else:
            say(f"submission refused: {status} {body}")
        if i + 1 < a.count:
            time.sleep(a.interval)


def cmd_reset(_):
    demo_data()
    cmd_stop(None)
    if not os.path.lexists(ROOT):
        say("nothing to remove")
        return
    if not state_unowned():
        fail("a mover still owns the demo state; not deleting it")
    shutil.rmtree(ROOT)
    say(f"removed {ROOT}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("build").set_defaults(fn=cmd_build)
    s = sub.add_parser("setup")
    s.add_argument("--jobs", type=int, default=10)
    s.add_argument("--inner", action="store_true", help=argparse.SUPPRESS)
    s.set_defaults(fn=cmd_setup)
    sub.add_parser("start").set_defaults(fn=cmd_start)
    sub.add_parser("stop").set_defaults(fn=cmd_stop)
    sub.add_parser("status").set_defaults(fn=status_line)
    j = sub.add_parser("add-job")
    j.add_argument("--count", type=int, default=1)
    j.add_argument("--interval", type=float, default=3.0, help="seconds between jobs")
    j.add_argument("--size-mb", type=float, default=3.0, help="size of each job's main file")
    j.add_argument("--files", type=int, default=2, help="files per job (1-5 named, more as parts)")
    j.add_argument("--inner", action="store_true", help=argparse.SUPPRESS)
    j.set_defaults(fn=cmd_add_job)
    sub.add_parser("reset").set_defaults(fn=cmd_reset)
    a = p.parse_args()
    if getattr(a, "count", 1) < 1 or getattr(a, "files", 1) < 1 or getattr(a, "jobs", 0) < 0:
        fail("counts must be positive")
    a.fn(a)


if __name__ == "__main__":
    main()
