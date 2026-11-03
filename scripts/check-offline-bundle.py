#!/usr/bin/env python3
"""Exercise an offline bundle in a disposable pinned SLES container, without downloads."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import tarfile
import time

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    archive = args.archive.resolve(strict=True)
    with tarfile.open(archive) as tar:
        names = {m.name.split("/")[0] for m in tar.getmembers()}
        if len(names) != 1:
            raise ValueError("expected one bundle root")
        name = names.pop()
        metadata = json.load(tar.extractfile(name + "/bundle.json"))
    runtime = json.loads((ROOT / "scripts/rust-platform.json").read_text())["runtime"]
    report = {"status": "FAILED", "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "bundle": metadata["name"], "runtime": runtime, "checks": []}
    owned = None

    def run(*cmd, ok=True):
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if ok and result.returncode:
            raise RuntimeError(str(cmd[:4]) + "\n" + result.stdout + result.stderr)
        return result

    def execute(*cmd, ok=True):
        return run("podman", "exec", "--user", "1000:1000", owned, *cmd, ok=ok)

    def http(method, path, body=None):
        payload = "" if body is None else json.dumps(body, separators=(",", ":"))
        request = f"{method} {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\nContent-Length: {len(payload)}\r\nContent-Type: application/json\r\n\r\n{payload}"
        command = "exec 3<>/dev/tcp/127.0.0.1:8080; printf %s " + shlex.quote(request) + " >&3; cat <&3"
        response = execute("/bin/bash", "-c", command, ok=False)
        if response.returncode or not response.stdout.startswith("HTTP/"):
            return 0, ""
        head, _, data = response.stdout.partition("\n\n")
        return int(head.split()[1]), data

    def wait_for(check, message):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if check():
                return
            time.sleep(0.1)
        raise RuntimeError(message)

    try:
        owned = run("podman", "create", "--pull=never", "--network", "none", "--cap-drop", "all", "--security-opt", "no-new-privileges", "--entrypoint", "/bin/sh", runtime, "-c", "exec sleep infinity").stdout.strip()
        run("podman", "start", owned)
        mode = run("podman", "inspect", "--format", "{{.HostConfig.NetworkMode}}", owned).stdout.strip()
        assert mode == "none"
        report["network"] = mode
        run("podman", "cp", str(archive), owned + ":/tmp/bundle.tar.gz")
        execute("/bin/sh", "-c", "mkdir -m 700 /tmp/offline-work; cd /tmp/offline-work; tar -xzf /tmp/bundle.tar.gz")
        unpacked = "/tmp/offline-work/" + name
        installed = "/tmp/offline-work/installed"
        execute("sh", unpacked + "/verify.sh")
        execute("sh", unpacked + "/install.sh", installed)
        execute("sh", installed + "/verify.sh")
        report["checks"].append("offline verify/install/reverify as UID/GID 1000, no external networking")
        assert execute("sh", unpacked + "/install.sh", installed, ok=False).returncode != 0
        assert execute("sh", unpacked + "/install.sh", "/tmp/offline-work/../unsafe", ok=False).returncode != 0
        report["checks"].append("existing and noncanonical installation destinations refuse")
        execute("/bin/sh", "-c", "cp -R " + shlex.quote(unpacked) + " /tmp/offline-work/tampered; printf extra >> /tmp/offline-work/tampered/bin/file-mover")
        assert execute("sh", "/tmp/offline-work/tampered/install.sh", "/tmp/offline-work/should-not-exist", ok=False).returncode != 0
        assert execute("test", "-e", "/tmp/offline-work/should-not-exist", ok=False).returncode != 0
        execute("/bin/sh", "-c", "cp -R " + shlex.quote(unpacked) + " /tmp/offline-work/extra; touch /tmp/offline-work/extra/unlisted")
        assert execute("sh", "/tmp/offline-work/extra/verify.sh", ok=False).returncode != 0
        report["checks"].append("tampered executable and extra file refuse before installation")
        config = json.loads((ROOT / "rust/config/local.example.json").read_text())
        base = "/tmp/offline-work/live"
        config.update(source_root=base + "/source", destination_root=base + "/destination", state_database=base + "/state/jobs.sqlite")
        execute("mkdir", "-m", "700", base, base + "/source", base + "/destination", base + "/state", base + "/source/.file-mover", base + "/destination/.file-mover", base + "/source/input")
        for role in ("source", "destination"):
            marker = json.dumps(config[role + "_binding"], separators=(",", ":"))
            script = "umask 077; printf %s " + shlex.quote(marker) + " > " + base + f"/{role}/.file-mover/{role}-binding.json; : > " + base + f"/{role}/.file-mover/coordinator.lock"
            execute("/bin/sh", "-c", script)
        execute("/bin/sh", "-c", "umask 077; printf %s " + shlex.quote(json.dumps(config)) + " > " + base + "/config.json; printf 'offline bundle payload' > " + base + "/source/input/data")
        binary = installed + "/bin/file-mover"
        execute(binary, "--initialize-source", base + "/config.json")
        run("podman", "exec", "--user", "1000:1000", "-d", owned, "/usr/bin/setsid", "--wait", binary, base + "/config.json")
        wait_for(lambda: http("GET", "/healthz")[0] == 200, "installed service not ready")
        status, body = http("POST", "/api/v2/jobs", {"generator_id": config["generator_id"], "submission_id": "offline-bundle", "source_path": base + "/source/input", "files": [{"name": "data"}]})
        if status != 202:
            raise RuntimeError(f"submission failed {status}: {body}")
        accepted = json.loads(body)
        job = str(accepted["job_id"])
        def committed():
            code, data = http("GET", "/api/v2/jobs/" + job)
            return code == 200 and json.loads(data).get("state") == "Committed"
        wait_for(committed, "installed service did not commit payload")
        execute(binary, "--stop", base + "/config.json")
        execute("sh", installed + "/verify.sh")
        report["checks"].append("installed executable initializes fresh local scope, serves HTTP, accepts/copies/verifies/commits a recording and stops")
        report["status"] = "PASSED"
    except Exception as error:
        report["error"] = str(error)
    finally:
        if owned:
            result = run("podman", "rm", "-f", owned, ok=False)
            if result.returncode:
                report["status"] = "FAILED"
                report["cleanup_error"] = result.stdout + result.stderr
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
