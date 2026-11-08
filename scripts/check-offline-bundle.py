#!/usr/bin/env python3
"""Exercise an offline bundle in a disposable pinned SLES container, without downloads."""
from nfs_fixture_contract import RECORDING_ID, producer_request, validate_writer_bytes
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    archive = args.archive.resolve(strict=True)
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            path = Path(member.name)
            if path.is_absolute() or ".." in path.parts or not (member.isfile() or member.isdir()):
                raise ValueError("unsafe bundle archive member")
        names = {m.name.split("/")[0] for m in tar.getmembers()}
        if len(names) != 1:
            raise ValueError("expected one bundle root")
        name = names.pop()
        metadata = json.load(tar.extractfile(name + "/bundle.json"))
    runtime = json.loads((ROOT / "scripts/rust-platform.json").read_text())["runtime"]
    report = {"status": "FAILED", "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "bundle": metadata["name"], "runtime": runtime,
              "checker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "checks": []}
    owned = None
    binary = None
    base = "/tmp/offline-work/live"

    def run(*cmd, ok=True):
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if ok and result.returncode:
            raise RuntimeError(str(cmd[:4]) + "\n" + result.stdout + result.stderr)
        return result

    def execute(*cmd, ok=True):
        return run("podman", "exec", "--user", "1000:1000", owned, "/usr/bin/setsid", "--wait", *cmd, ok=ok)

    def http(method, path, body=None):
        payload = "" if body is None else json.dumps(body, separators=(",", ":"))
        request = f"{method} {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\nContent-Length: {len(payload)}\r\nContent-Type: application/json\r\n\r\n{payload}"
        client = ('use Socket; alarm 5; socket(S,PF_INET,SOCK_STREAM,0) or die $!; '
                  'connect(S,sockaddr_in(8080,inet_aton("127.0.0.1"))) or die $!; '
                  'my $r=$ARGV[0]; my $sent=0; while($sent<length($r)) { '
                  'my $n=syswrite(S,$r,length($r)-$sent,$sent); die $! unless defined($n) && $n>0; $sent+=$n; } '
                  'shutdown(S,1); while(1) { my $n=sysread(S,my $b,65536); die $! unless defined($n); last unless $n; print $b; }')
        response = execute("/usr/bin/perl", "-e", client, request, ok=False)
        if response.returncode or not response.stdout.startswith("HTTP/"):
            return 0, (response.stdout + response.stderr)[-1000:]
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
        owned = run("podman", "create", "--pull=never", "--network", "none", "--user", "1000:1000", "--cap-drop", "all", "--security-opt", "no-new-privileges", "--entrypoint", "/bin/sh", runtime, "-c", "exec sleep infinity").stdout.strip()
        run("podman", "start", owned)
        mode = run("podman", "inspect", "--format", "{{.HostConfig.NetworkMode}}", owned).stdout.strip()
        assert mode == "none"
        report["network"] = mode
        # The pinned minimal runtime lacks tar. Transfer an extracted directory,
        # as documented for targets without an archive tool; verification still
        # runs entirely in SLES before installation/executable use.
        with tempfile.TemporaryDirectory() as directory:
            with tarfile.open(archive) as tar:
                tar.extractall(directory, filter="data")
            run("podman", "cp", directory + "/.", owned + ":/tmp/offline-work")
        report["checks"].append("host extracts archive for minimal target without tar; target verifies complete copied inventory")
        unpacked = "/tmp/offline-work/" + name
        installed = "/tmp/offline-work/installed"
        execute("sh", unpacked + "/verify.sh")
        execute("sh", unpacked + "/install.sh", installed)
        execute("sh", installed + "/verify.sh")
        report["checks"].append("offline verify/install/reverify as UID/GID 1000, no external networking")
        assert execute("sh", unpacked + "/install.sh", installed, ok=False).returncode != 0
        assert execute("sh", unpacked + "/install.sh", "/tmp/offline-work/../unsafe", ok=False).returncode != 0
        assert execute("sh", unpacked + "/install.sh", unpacked + "/nested-install", ok=False).returncode != 0
        report["checks"].append("existing, noncanonical and bundle-nested installation destinations refuse")
        execute("/bin/sh", "-c", "cp -R " + shlex.quote(unpacked) + " /tmp/offline-work/tampered; printf extra >> /tmp/offline-work/tampered/bin/file-mover")
        assert execute("sh", "/tmp/offline-work/tampered/install.sh", "/tmp/offline-work/should-not-exist", ok=False).returncode != 0
        assert execute("test", "-e", "/tmp/offline-work/should-not-exist", ok=False).returncode != 0
        execute("/bin/sh", "-c", "cp -R " + shlex.quote(unpacked) + " /tmp/offline-work/extra; touch /tmp/offline-work/extra/unlisted")
        assert execute("sh", "/tmp/offline-work/extra/verify.sh", ok=False).returncode != 0
        report["checks"].append("tampered executable and extra file refuse before installation")
        config = json.loads((ROOT / "rust/config/local.example.json").read_text())
        config.update(source_root=base + "/source", destination_root=base + "/destination", state_database=base + "/state/jobs.sqlite")
        execute("mkdir", "-m", "700", base, base + "/source", base + "/destination", base + "/state", base + "/source/.file-mover", base + "/destination/.file-mover", base + "/source/input")
        for role in ("source", "destination"):
            marker = json.dumps(config[role + "_binding"], separators=(",", ":"))
            script = "umask 077; printf %s " + shlex.quote(marker) + " > " + base + f"/{role}/.file-mover/{role}-binding.json; : > " + base + f"/{role}/.file-mover/coordinator.lock"
            execute("/bin/sh", "-c", script)
        execute("/bin/sh", "-c", "umask 077; printf %s " + shlex.quote(json.dumps(config)) + " > " + base + "/config.json; printf 'offline bundle payload' > " + base + "/source/input/data")
        binary = installed + "/bin/file-mover"
        execute(binary, "--initialize-source", base + "/config.json")
        launch = "exec /usr/bin/setsid --wait " + shlex.quote(binary) + " " + base + "/config.json > " + base + "/service.log 2>&1"
        run("podman", "exec", "--user", "1000:1000", "-d", owned, "/bin/sh", "-c", launch)
        def healthy():
            code, data = http("GET", "/healthz")
            report["last_health"] = {"code": code, "body": data}
            return code == 200
        wait_for(healthy, "installed service not ready")
        submission = producer_request(base + "/source/input", {"data": len(b"offline bundle payload")}, generator_id=config["generator_id"])
        report["submission"] = submission
        status, body = http("POST", "/api/v2/jobs", submission)
        if status != 202:
            raise RuntimeError(f"submission failed {status}: {body}")
        accepted = json.loads(body)
        assert accepted == dict(job_id=accepted["job_id"], recording_id=RECORDING_ID, accepted=True, source_paths_released=True)
        job = str(accepted["job_id"])
        def committed():
            code, data = http("GET", "/api/v2/jobs/" + job)
            return code == 200 and json.loads(data).get("state") == "Committed"
        wait_for(committed, "installed service did not commit payload")
        payload = execute("cat", base + "/destination/" + RECORDING_ID + "/data").stdout
        assert payload == "offline bundle payload"
        manifest_bytes = execute("cat", base + "/destination/" + RECORDING_ID + "/COMMITTED.json").stdout
        manifest = validate_writer_bytes(manifest_bytes.encode("utf-8"), submission)
        entry = manifest["files"][0]
        assert entry["path"] == "data" and entry["size_bytes"] == str(len(payload.encode("utf-8")))
        assert entry["algorithm"] == "sha256" and entry["sha256"] == hashlib.sha256(payload.encode()).hexdigest()
        assert execute("cat", base + "/source/.file-mover/" + job + "-0/data").stdout == payload
        execute(binary, "--stop", base + "/config.json")
        run("podman", "exec", "--user", "1000:1000", "-d", owned, "/bin/sh", "-c", launch)
        wait_for(healthy, "installed service did not restart")
        assert committed()
        code, replay = http("POST", "/api/v2/jobs", submission)
        assert code == 202 and json.loads(replay) == accepted
        assert execute("cat", base + "/destination/" + RECORDING_ID + "/COMMITTED.json").stdout == manifest_bytes
        execute(binary, "--stop", base + "/config.json")
        execute("sh", installed + "/verify.sh")
        report["checks"].append("installed executable initializes, serves HTTP, commits exact payload/manifest SHA-256, retains source, stops/restarts and replays the same job without changing its manifest")
        report["status"] = "PASSED"
    except Exception as error:
        report["error"] = str(error)
        if owned and binary:
            report["service_log"] = execute("cat", base + "/service.log", ok=False).stdout[-4000:]
            status = execute(binary, "--status", base + "/config.json", ok=False)
            report["local_status"] = status.stdout + status.stderr
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
