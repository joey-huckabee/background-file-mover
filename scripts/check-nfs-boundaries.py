"""Container-only NFS startup/lock/outage qualification; does not enable NFS.

Reuses exact service artifacts from a passing mandatory SLES gate. The saved
E2 server image and preloaded nfs/nfsd modules must be available in the engine.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "scripts/rust-platform.json").read_text())
SERVER = "localhost/background-file-mover-e2-nfs"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gate", type=Path, help="Passing rust/validation run directory")
    parser.add_argument("--connection", default="podman-machine-default-root")
    parser.add_argument("--isolated-startup", action="store_true",
                        help="Require startup termination and child exit before NFS restoration")
    parser.add_argument("--qualification-gate", type=Path,
                        help="Also run normal REST transfers with audited NFS qualification artifacts")
    parser.add_argument("--runtime", action="store_true",
                        help="Also qualify real Rust worker interruption/outage and coordinator death")
    args = parser.parse_args()
    assert not args.runtime or args.qualification_gate, "runtime checks require qualification artifacts"
    engine = ["podman", "--connection", args.connection]
    gate = args.gate.resolve()
    evidence = json.loads((gate / "report.json").read_text())
    assert evidence["status"] == "PASSED" and evidence["config"] == CONFIG
    assert evidence.get("build_mode", "production") == "production", "boundary checks require production artifacts"
    # Never reuse artifacts after changes to Rust build inputs.
    with tarfile.open(gate / "source.tar.gz") as archive:
        archived_files = set()
        for member in archive.getmembers():
            if member.isfile():
                archived_files.add(member.name)
                path = (ROOT / "rust" / member.name).resolve()
                assert path.is_relative_to(ROOT / "rust")
                assert path.read_bytes() == archive.extractfile(member).read(), member.name
        current_files = set()
        for child in (ROOT / "rust").iterdir():
            if child.name not in {"target", "validation"}:
                candidates = child.rglob("*") if child.is_dir() else [child]
                current_files.update(p.relative_to(ROOT / "rust").as_posix()
                                     for p in candidates if p.is_file())
        assert current_files == archived_files, "Rust source inventory changed"
    qualification = None
    if args.qualification_gate:
        qualification_gate = args.qualification_gate.resolve()
        qualification = json.loads((qualification_gate / "report.json").read_text())
        assert qualification["status"] == "PASSED" and qualification["config"] == CONFIG
        assert qualification["build_mode"] == "nfs-qualification"
        with tarfile.open(qualification_gate / "source.tar.gz") as archive:
            entries = {m.name for m in archive.getmembers() if m.isfile()}
            assert entries == current_files
            for member in archive.getmembers():
                if member.isfile():
                    path = (ROOT / "rust" / member.name).resolve()
                    assert path.is_relative_to(ROOT / "rust")
                    assert path.read_bytes() == archive.extractfile(member).read(), member.name
    label = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    output = ROOT / "rust/validation" / ("nfs-" + label)
    output.mkdir()
    report = {"status": "FAILED", "run_id": "nfs-" + label,
              "isolated_startup_required": args.isolated_startup,
              "gate": gate.name, "runtime": CONFIG["runtime"],
              "source_sha256": evidence["source_sha256"], "checks": {}, "cleanup_errors": []}
    report["runtime_requested"] = args.runtime
    report["limitations"] = [
        "SLES 12 SP5 userspace on WSL2 kernel, not the SLES kernel or old CPU hardware.",
        "One client and modern controlled server; no cross-client fencing or server reboot/power-loss evidence.",
        "Lock and interrupted metadata probes use OS tools, not Rust claim/copy/publication on NFS.",
        "Service startup rejection is measured; production NFS and source deletion remain disabled.",
    ]
    if args.runtime:
        report["limitations"][2] = "Real Rust runtime cases cover selected claim, source-read, copy-write, verification-read, publication and manifest-link points; long outages, interrupted claim/file link intermediates and export changes remain unqualified. Other lock/startup probes use OS tools."
    containers = []
    tasks = []
    network = volume = server = client = None
    mounted = False

    def run(arguments, check=True, timeout=45):
        result = subprocess.run(engine + arguments, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=timeout)
        if check and result.returncode:
            raise RuntimeError(f"{arguments}: {result.stdout}{result.stderr}")
        return result

    def execute(script, user=None, check=True):
        return run(["exec", *(["--user", user] if user else []), client,
                    "/bin/sh", "-eu", "-c", script], check=check)

    def spawn(script, name):
        log = (output / (name + ".log")).open("w", encoding="utf-8")
        process = subprocess.Popen(engine + ["exec", "--user", "1000:1000", "--env", "LD_BIND_NOW=1", client,
                                   "/bin/sh", "-eu", "-c", script], stdout=log, stderr=log)
        tasks.append((process, log))
        return process

    def await_file(path):
        for _ in range(30):
            if execute(f"test -f {path}", "1000:1000", check=False).returncode == 0:
                return
            time.sleep(0.2)
        raise RuntimeError(f"missing rendezvous {path}")

    def restore():
        run(["exec", server, "rpc.nfsd", "-G", "10", "-L", "10", "-V", "4", "-p", "2049", "2"])

    try:
        report["server_image"] = run(["image", "inspect", SERVER, "--format", "{{.Id}}"]).stdout.strip()
        network = "bfm-nfs-" + label.lower()
        volume = network + "-data"
        run(["network", "create", "--internal", network])
        run(["volume", "create", volume])
        server = run(["create", "--privileged", "--network", network,
                      "--volume", volume + ":/exports", SERVER]).stdout.strip()
        containers.append(server)
        run(["start", server])
        for _ in range(40):
            if "NFS_READY" in run(["logs", server]).stdout:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("NFS server not ready")
        report["server_packages"] = run(["exec", server, "dpkg-query", "-W"]).stdout.splitlines()
        ip = json.loads(run(["inspect", server]).stdout)[0]["NetworkSettings"]["Networks"][network]["IPAddress"]
        client = run(["create", "--network", network, "--cap-drop", "all", "--cap-add", "SYS_ADMIN",
                      "--security-opt", "no-new-privileges", "--entrypoint", "/bin/sh", CONFIG["runtime"],
                      "-c", "exec sleep infinity"]).stdout.strip()
        containers.append(client)
        run(["start", client])
        execute("mkdir /tmp/nfs")
        execute("mkdir -p /tmp/local/state /tmp/local/destination; chmod 700 /tmp/local /tmp/local/state /tmp/local/destination", "1000:1000")
        options = f"addr={ip},vers=4.1,proto=tcp,port=2049,hard,timeo=10,retrans=1,noac"
        run(["exec", client, "mount", "-i", "-t", "nfs4", "-o", options, ip + ":/", "/tmp/nfs"])
        mounted = True
        report["mounts"] = execute("cat /proc/mounts").stdout.splitlines()
        report["kernel"] = execute("uname -r").stdout.strip()
        assert execute("getconf GNU_LIBC_VERSION").stdout.strip() == "glibc 2.22"
        assert execute("stat -f -c %t /tmp/nfs").stdout.strip() == "6969"
        assert any(" /tmp/nfs " in m and "hard" in m and "vers=4.1" in m for m in report["mounts"])
        execute("mkdir /tmp/nfs/source /tmp/nfs/source/.file-mover; chmod 700 /tmp/nfs/source /tmp/nfs/source/.file-mover", "1000:1000")
        before = execute("stat -c '%d:%i:%u:%a' /tmp/nfs/source /tmp/nfs/source/.file-mover", "1000:1000").stdout
        report["root_identity_before"] = before.splitlines()
        config = {"bind": "127.0.0.1:19876", "generator_id": "fixture",
                  "source_root": "/tmp/nfs/source", "destination_root": "/tmp/local/destination",
                  "state_database": "/tmp/local/state/jobs.sqlite"}
        config_path = output / "config.json"
        config_path.write_text(json.dumps(config))
        run(["cp", str(config_path), client + ":/tmp/local/config.json"])
        report["artifacts"] = {}
        for profile in ("debug", "release"):
            artifact = next(a for a in evidence["profiles"][profile]["artifacts"] if not a["test"])
            path = gate / artifact["name"]
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            assert digest == artifact["sha256"]
            report["artifacts"][profile] = digest
            run(["cp", str(path), client + ":/tmp/" + profile])
            execute("chmod 755 /tmp/" + profile)
            assert execute("sha256sum /tmp/" + profile).stdout.split()[0] == digest
            loaded = execute("ldd -r /tmp/" + profile).stdout
            assert "not found" not in loaded and "undefined symbol" not in loaded
            result = execute("LD_BIND_NOW=1 /tmp/" + profile + " /tmp/local/config.json", "1000:1000", check=False)
            assert result.returncode != 0 and "filesystem not qualified" in result.stderr
            assert execute("test ! -e /tmp/local/state/jobs.sqlite", "1000:1000", check=False).returncode == 0
            report["checks"][profile + "_startup_rejected"] = result.stderr.strip()
        if qualification:
            from nfs_baseline import run_baseline
            report["qualification_gate"] = qualification_gate.name
            report["baseline"] = run_baseline(qualification_gate, qualification, run, execute, spawn, output, client)
            if not report["baseline"]["passed"]:
                raise RuntimeError("NFS normal-operation baseline blocked; inspect baseline cases")
            if args.runtime:
                from nfs_runtime import run_runtime
                artifact_hashes = dict(report["artifacts"])
                artifact_hashes.update({"qualification-" + c["profile"]: c["binary_sha256"] for c in report["baseline"]["cases"]})
                report["runtime"] = {"passed": False, "cases": []}
                completed = run_runtime(run, execute, spawn, restore, server, output, client, artifact_hashes, report["runtime"]["cases"])
                report["runtime"]["passed"] = completed["passed"]
                if not report["runtime"]["passed"]:
                    raise RuntimeError("NFS Rust runtime qualification failed; inspect cases")
        # Model the actual inherited open-file-description lock with OS tools.
        # Child holds fd 9 after coordinator death; no Rust effects are claimed.
        holder = spawn("exec 9</tmp/nfs/source/.file-mover; flock -xn 9; echo $$ >/tmp/local/parent.pid; /bin/sh -c 'echo $$ >/tmp/local/child.pid; while test ! -e /tmp/local/release-lock; do sleep 0.2; done' & wait", "inherited-lock")
        await_file("/tmp/local/child.pid")
        execute("kill -KILL $(cat /tmp/local/parent.pid)", "1000:1000")
        holder.wait(timeout=10)
        collision = execute("flock -xn /tmp/nfs/source/.file-mover true", "1000:1000", check=False)
        assert collision.returncode != 0
        execute("touch /tmp/local/release-lock", "1000:1000")
        for _ in range(30):
            if execute("flock -xn /tmp/nfs/source/.file-mover true", "1000:1000", check=False).returncode == 0:
                break
            time.sleep(0.2)
        else:
            raise RuntimeError("inherited source lock not released")
        report["checks"]["inherited_lock"] = "Parent death retained lock; child exit released it"
        interrupted = spawn("exec 9</tmp/nfs/source/.file-mover; flock -xn 9; echo $$ >/tmp/local/interrupted.pid; while test ! -e /tmp/local/interrupt-go; do sleep 0.2; done; exec stat /tmp/nfs/source", "interrupted-worker")
        await_file("/tmp/local/interrupted.pid")
        run(["exec", server, "rpc.nfsd", "0"])
        execute("touch /tmp/local/interrupt-go", "1000:1000")
        probe = spawn("echo $$ >/tmp/local/probe.pid; stat -c '%d:%i:%u:%a' /tmp/nfs/source /tmp/nfs/source/.file-mover", "outage-stat")
        await_file("/tmp/local/probe.pid")
        time.sleep(3)
        assert probe.poll() is None, "hard mount unexpectedly returned during outage"
        startup = spawn("echo $$ >/tmp/local/startup.pid; exec /tmp/release /tmp/local/config.json", "outage-startup")
        await_file("/tmp/local/startup.pid")
        time.sleep(3)
        assert startup.poll() is None, "startup unexpectedly returned during outage"
        assert interrupted.poll() is None, "assigned hard-mount operation unexpectedly returned"
        if args.isolated_startup:
            children = execute("pid=$(cat /tmp/local/startup.pid); for task in /proc/$pid/task/*/children; do cat $task; done", "1000:1000").stdout.split()
            assert len(children) == 1, "startup must have exactly one bounded bootstrap child"
            report["checks"]["bootstrap_children_before_signal"] = len(children)
            # A TCP listener may exist, but no HTTP readiness is served yet.
            health = spawn("exec /bin/bash -c 'exec 3<>/dev/tcp/127.0.0.1/19876; printf \"GET /healthz HTTP/1.1\\r\\nHost: localhost\\r\\n\\r\\n\" >&3; cat <&3'", "startup-health")
            time.sleep(1)
            assert health.poll() is None, "startup served an HTTP response before custody"
        execute("kill -TERM $(cat /tmp/local/startup.pid)", "1000:1000")
        time.sleep(1)
        if args.isolated_startup:
            assert startup.wait(timeout=5) == 0
            assert execute("test ! -e /proc/" + children[0], "1000:1000", check=False).returncode == 0
            assert execute("test ! -e /tmp/local/state/jobs.sqlite", "1000:1000", check=False).returncode == 0
            health.wait(timeout=5)
            report["checks"]["isolated_startup"] = "SIGTERM ended service and confirmed bootstrap child exit before server restoration; no SQLite or readiness"
        report["checks"]["startup_sigterm"] = {"exit_observed_before_restore": startup.poll() is not None}
        execute("kill -KILL $(cat /tmp/local/interrupted.pid)", "1000:1000")
        time.sleep(1)
        report["checks"]["kill_during_outage"] = {"exit_observed_before_restore": interrupted.poll() is not None}
        report["checks"]["outage"] = "Metadata and source startup remained pending at 3-second observations"
        restore()
        assert probe.wait(timeout=45) == 0
        assert (startup.wait(timeout=45) == 0) == args.isolated_startup
        assert interrupted.wait(timeout=45) != 0
        assert execute("flock -xn /tmp/nfs/source/.file-mover true", "1000:1000", check=False).returncode == 0
        for _, log in tasks:
            log.flush()
        assert (output / "outage-stat.log").read_text() == before
        report["root_identity_after"] = (output / "outage-stat.log").read_text().splitlines()
        startup_log = (output / "outage-startup.log").read_text()
        assert "Ready on" not in startup_log
        if args.isolated_startup:
            assert "Source bootstrap termination requested" in startup_log
        else:
            assert "filesystem not qualified" in startup_log
        report["checks"]["restored"] = "Stable root/namespace identity; metadata recovered and source lock became available"
        report["status"] = "PASSED"
    except Exception as error:
        report["error"] = str(error)
    finally:
        # Restore first: killing a task is not evidence that NFS effects ended.
        if server:
            try:
                restore()
            except Exception as error:
                report["cleanup_errors"].append(str(error))
        if client:
            for name in ("parent", "child", "probe", "startup", "interrupted"):
                try:
                    execute(f"if test -f /tmp/local/{name}.pid; then kill -KILL $(cat /tmp/local/{name}.pid) 2>/dev/null || true; fi", "1000:1000")
                except Exception as error:
                    report["cleanup_errors"].append(str(error))
        for process, log in tasks:
            try:
                process.wait(timeout=45)
            except Exception as error:
                report["cleanup_errors"].append(str(error))
            log.close()
        if mounted:
            try:
                run(["exec", client, "umount", "/tmp/nfs"])
            except Exception as error:
                report["cleanup_errors"].append(str(error))
        if not report["cleanup_errors"]:
            if server:
                run(["exec", server, "rpc.nfsd", "0"], check=False)
                run(["exec", server, "exportfs", "-au"], check=False)
            for container in reversed(containers):
                result = run(["rm", "--force", container], check=False)
                if result.returncode:
                    report["cleanup_errors"].append(result.stderr)
            for kind, name in (("volume", volume), ("network", network)):
                if name:
                    result = run([kind, "rm", name], check=False)
                    if result.returncode:
                        report["cleanup_errors"].append(result.stderr)
        if report["cleanup_errors"]:
            report["status"] = "FAILED"
            report["recovery_resources"] = {"containers": containers, "network": network, "volume": volume}
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(f"{report['status']}: {output}", flush=True)
        if "error" in report:
            print(report["error"], flush=True)
    return 0 if report["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
