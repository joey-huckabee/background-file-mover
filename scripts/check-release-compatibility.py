#!/usr/bin/env python3
"""Exercise retained SLES-qualified predecessor/current binaries on disposable state.

No compilation, download, installation, mounts or operational paths. This is a
bounded RC-20/24 check, not shipping lifecycle/NFS or working rollback approval.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sqlite3
from contextlib import closing
import tarfile
import time

from nfs_fixture_contract import producer_request, validate_writer_bytes

ROOT = Path(__file__).resolve().parents[1]
BASE = "/tmp/release-compatibility"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args, timeout=30, **kwargs):
    return subprocess.run(args, capture_output=True, timeout=timeout, check=True, **kwargs).stdout


def git(*args):
    return run(["git", "-C", str(ROOT), *args], text=True).strip()


def checked_gate(folder, commit, runtime, mode="production"):
    folder = folder.resolve(strict=True)
    report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "PASSED" and report.get("cleanup_error") is None
    assert report["build_mode"] == mode and report["config"]["runtime"] == runtime
    assert sha(folder / "source.tar.gz") == report["source_sha256"]
    paths = git("ls-tree", "-r", "--name-only", commit, "rust").splitlines()
    expected = {p.removeprefix("rust/"): hashlib.sha256(run(
        ["git", "-C", str(ROOT), "show", commit + ":" + p])).hexdigest() for p in paths}
    with tarfile.open(folder / "source.tar.gz") as archive:
        actual = {m.name: hashlib.sha256(archive.extractfile(m).read()).hexdigest()
                  for m in archive.getmembers() if m.isfile()}
    assert actual == expected, "gate source differs from declared Git commit"
    return folder, report, dict(commit=commit, rust_tree=git("rev-parse", commit + ":rust"),
                               source_files=len(expected), report_sha256=sha(folder / "report.json"),
                               source_sha256=report["source_sha256"], gate=str(folder))


def artifact(gate, profile):
    folder, report, _ = gate
    name = profile + "-0-file-mover"
    item = next(a for a in report["profiles"][profile]["artifacts"] if a["name"] == name)
    path = folder / name
    assert sha(path) == item["sha256"]
    for suffix in (".elf", ".ldd", ".smoke"):
        assert (folder / (name + suffix)).is_file()
    return path, item["sha256"]


def exercise(profile, gates, folder, runtime, result):
    cid = None
    daemon = None
    log = None
    try:
        cid = run(["podman", "create", "--pull=never", "--network", "none",
                   "--cap-drop", "all", "--security-opt", "no-new-privileges",
                   "--entrypoint", "/bin/sh", runtime, "-c", "exec sleep infinity"], text=True).strip()
        run(["podman", "start", cid])
        assert run(["podman", "inspect", "--format", "{{.HostConfig.NetworkMode}}", cid], text=True).strip() == "none"
        prefix = ["podman", "exec", "--user", "1000:1000", "--env", "LD_BIND_NOW=1", cid,
                  "/usr/bin/setsid", "--wait"]

        def command(tool, *args):
            return prefix + ["/tmp/" + tool, *args]

        def capture(label, tool, *args, success=True):
            response = subprocess.run(command(tool, *args), capture_output=True, timeout=35)
            (folder / (label + ".stdout")).write_bytes(response.stdout)
            (folder / (label + ".stderr")).write_bytes(response.stderr)
            assert (response.returncode == 0) == success, (label, response.returncode, response.stderr)
            return response

        def write(path, content):
            run(["podman", "exec", "-i", "--user", "1000:1000", cid, "sh", "-c",
                 'umask 077; cat > "$1"', "write", BASE + "/" + path], input=content)

        def read(path):
            return run(prefix + ["cat", BASE + "/" + path])

        def snapshot(paths):
            return {p: dict(sha256=hashlib.sha256(read(p)).hexdigest(), identity=run(
                prefix + ["stat", "-c", "%d:%i:%s", BASE + "/" + p], text=True).strip()) for p in paths}

        def verified_contents(component, manifest, expected):
            assert len(manifest["files"]) == len(expected)
            assert {entry["path"] for entry in manifest["files"]} == set(expected)
            for entry in manifest["files"]:
                content = expected[entry["path"]]
                assert read("destination/" + component + "/" + entry["path"]) == content
                size = len(content) if manifest["version"] == 1 else str(len(content))
                assert entry["size_bytes"] == size and entry["algorithm"] == "sha256"
                assert entry["sha256"] == hashlib.sha256(content).hexdigest()

        def http(method, route, body=None):
            data = b"" if body is None else json.dumps(body, separators=(",", ":")).encode()
            request = (method + " " + route + " HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: "
                       + str(len(data)) + "\r\nConnection: close\r\n\r\n").encode() + data
            response = run(prefix + ["bash", "-c", 'exec 3<>/dev/tcp/127.0.0.1/39091; printf "%s" "$1" >&3; cat <&3',
                                     "http", request.decode("utf-8")])
            head, body = response.split(b"\r\n\r\n", 1)
            return int(head.split()[1]), json.loads(body)

        def start(tool):
            nonlocal daemon, log
            assert daemon is None
            log = (folder / (tool + "-daemon-" + str(time.monotonic_ns()) + ".log")).open("wb")
            daemon = subprocess.Popen(command(tool, BASE + "/config.json"), stdout=log, stderr=log)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                assert daemon.poll() is None, "daemon exited before readiness; inspect logs"
                try:
                    if http("GET", "/healthz")[0] == 200:
                        return
                except (subprocess.CalledProcessError, ValueError):
                    pass
                time.sleep(.05)
            raise AssertionError("readiness timeout")

        def stop(tool):
            nonlocal daemon, log
            capture(tool + "-stop-" + str(time.monotonic_ns()), tool, "--stop", BASE + "/config.json")
            assert daemon.wait(timeout=15) == 0
            daemon = None
            log.close()
            log = None

        def committed(job):
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                code, status = http("GET", "/api/v2/jobs/" + str(job))
                if code == 200 and status["state"] == "Committed":
                    return status
                time.sleep(.05)
            raise AssertionError(("commit timeout", status))

        for tool, gate in gates.items():
            path, digest = artifact(gate, profile)
            result[tool + "_sha256"] = digest
            run(["podman", "cp", str(path), cid + ":/tmp/" + tool])
            run(["podman", "exec", cid, "chmod", "0555", "/tmp/" + tool])
        directories = ["", "state", "source", "source/current", "source/.file-mover",
                       "destination", "destination/.file-mover"]
        run(prefix + ["mkdir", "-m", "0700", "-p", *[BASE + "/" + p for p in directories]])
        source = dict(version=3, coordinator_id="test-owner", root_id="local-source",
                      endpoint_id="test-local", marker_id="test-marker", filesystem="local", role="source")
        destination = dict(source, root_id="configured-local", endpoint_id="test-local-destination",
                           marker_id="test-destination-marker", role="destination")
        for directory, binding, name in [("source", source, "source-binding.json"),
                                         ("destination", destination, "destination-binding.json")]:
            write(directory + "/.file-mover/coordinator.lock", b"")
            write(directory + "/.file-mover/" + name, json.dumps(binding).encode())
        config = dict(bind="127.0.0.1:39091", generator_id="recorder", source_root=BASE + "/source",
                      source_binding=source, destination_root=BASE + "/destination", destination_binding=destination,
                      state_database=BASE + "/state/jobs.sqlite", missing_file_retry_window_seconds=300)
        write("config.json", json.dumps(config).encode())
        # A distinct listener prevents a port collision from masquerading as
        # proof that the durable instance guard excludes the contender.
        write("contender.json", json.dumps(dict(config, bind="127.0.0.1:39092")).encode())
        write("source/current/data", b"original committed recording")
        capture("initialize", "schema11", "--initialize-source", BASE + "/config.json")
        refused = capture("schema11-normal-refusal", "target", BASE + "/config.json", success=False)
        assert b"MigrationRequired" in refused.stderr
        start("schema11")
        # A competing binary must not stop or replace the admitted owner.
        refused = capture("live-predecessor-excludes-target", "target", BASE + "/contender.json", success=False)
        assert b"local instance or surviving worker already owns state" in refused.stderr and http("GET", "/healthz")[0] == 200
        complete = dict(generator_id="recorder", submission_id="complete", source_path=BASE + "/source/current", files=[dict(name="data")])
        pending = dict(complete, submission_id="pending", files=[dict(name="later")])
        code, first = http("POST", "/api/v2/jobs", complete)
        assert code == 202 and first["job_id"] == "1"
        committed(1)
        verified_contents("1", json.loads(read("destination/1/COMMITTED.json")),
                          {"data": b"original committed recording"})
        code, second = http("POST", "/api/v2/jobs", pending)
        assert code == 503 and second["job_id"] == "2"
        stop("schema11")
        preserved_paths = ["source/.file-mover/1-0/data", "destination/1/data", "destination/1/COMMITTED.json",
                           "source/.file-mover/source-enrollment.json"]
        before = snapshot(preserved_paths)
        run(["podman", "cp", cid + ":" + BASE + "/state", str(folder / "schema11-state")])
        migrated = capture("migration", "target", "--migrate-state", BASE + "/config.json", "--backup-dir", BASE + "/backup", "--confirm")
        assert json.loads(migrated.stdout)["converted"] is True
        run(["podman", "cp", cid + ":" + BASE + "/state", str(folder / "migrated-state")])
        # Inspect only stopped disposable copies, including their retained WAL.
        with closing(sqlite3.connect((folder / "schema11-state/jobs.sqlite").as_uri() + "?mode=ro", uri=True)) as old_db, \
                closing(sqlite3.connect((folder / "migrated-state/jobs.sqlite").as_uri() + "?mode=ro", uri=True)) as new_db:
            assert old_db.execute("PRAGMA user_version").fetchone() == (11,)
            assert new_db.execute("PRAGMA user_version").fetchone() == (14,)
            tables = [r[0] for r in old_db.execute("SELECT name FROM sqlite_schema WHERE type='table'")]
            for table in tables:
                quoted = '"' + table.replace('"', '""') + '"'
                columns = [r[1] for r in old_db.execute("PRAGMA table_info(" + quoted + ")")]
                selected = ",".join('"' + c.replace('"', '""') + '"' for c in columns)
                query = "SELECT " + selected + " FROM " + quoted + " ORDER BY rowid"
                assert old_db.execute(query).fetchall() == new_db.execute(query).fetchall(), table
            result["migration_tables_preserved"] = tables
        refused = capture("partial-legacy-refusal", "target", BASE + "/config.json", success=False)
        assert b"UnsupportedIdentity" in refused.stderr and snapshot(preserved_paths) == before
        start("legacy")
        # Prevent new destination allocation while allowing the existing root
        # authorization and source handoff. Restore before target recovery.
        run(prefix + ["chmod", "0500", BASE + "/destination"])
        write("source/current/later", b"legacy pending recording")
        code, finished = http("POST", "/api/v2/jobs", pending)
        assert code == 202 and finished["job_id"] == "2"
        code, unfinished = http("GET", "/api/v2/jobs/2")
        assert code == 200 and unfinished["state"] != "Committed"
        stop("legacy")
        run(prefix + ["chmod", "0700", BASE + "/destination"])
        # Whole-set custody, including unfinished delivery, is admitted by target.
        start("target")
        assert committed(1)["details"]["submission_id"] == "complete"
        assert committed(2)["details"]["submission_id"] == "pending"
        legacy_manifest = json.loads(read("destination/2/COMMITTED.json"))
        assert legacy_manifest["version"] == 1
        verified_contents("2", legacy_manifest, {"later": b"legacy pending recording"})
        assert snapshot(preserved_paths) == before
        refused = capture("live-target-excludes-predecessor", "legacy", BASE + "/contender.json", success=False)
        assert b"local instance or surviving worker already owns state" in refused.stderr and http("GET", "/healthz")[0] == 200
        write("source/current/new-a", b"uuid original a")
        write("source/current/new-b", b"uuid original b")
        request = producer_request(BASE + "/source/current", {"new-b": 15, "new-a": 15}, generator_id="recorder")
        # Size comparison is default-off; immutable assertions are still retained.
        code, receipt = http("POST", "/api/v2/jobs", request)
        assert code == 202 and receipt["job_id"] == "3", receipt
        committed(3)
        manifest_path = "destination/" + request["recording_id"] + "/COMMITTED.json"
        raw = read(manifest_path)
        manifest = validate_writer_bytes(raw, request)
        verified_contents(request["recording_id"], manifest,
                          {"new-a": b"uuid original a", "new-b": b"uuid original b"})
        v2_paths = [manifest_path, "destination/" + request["recording_id"] + "/new-a",
                    "destination/" + request["recording_id"] + "/new-b"]
        original_v2 = snapshot(v2_paths)
        stop("target")
        refused = capture("mixed-state-predecessor-refusal", "legacy", BASE + "/config.json", success=False)
        assert b"UnsupportedIdentity" in refused.stderr
        assert snapshot(preserved_paths) == before and snapshot(v2_paths) == original_v2
        write("source/current/new-a", b"producer reused path a")
        write("source/current/new-b", b"producer reused path b")
        start("target")
        replay = dict(request, files=list(reversed(request["files"])))
        code, repeated = http("POST", "/api/v2/jobs", replay)
        assert code == 202 and repeated == receipt
        assert read("source/current/new-a") == b"producer reused path a"
        assert read("source/current/new-b") == b"producer reused path b"
        assert snapshot(preserved_paths) == before and snapshot(v2_paths) == original_v2
        stop("target")
        capture("final-inspection", "target", "--check-state", BASE + "/config.json")
        run(["podman", "cp", cid + ":" + BASE + "/state", str(folder / "final-state")])
        run(["podman", "cp", cid + ":" + BASE + "/backup", str(folder / "backup")])
        result.update(status="PASSED", legacy_files=before, v2_files=original_v2,
                      legacy_at_cutover=unfinished,
                      receipt=receipt, checks=["schema11_normal_refusal_and_explicit_migration",
                      "live_predecessor_target_mutual_exclusion", "partial_legacy_refusal_then_predecessor_handoff",
                      "legacy_v1_recovery_preservation", "mixed_state_predecessor_refusal",
                      "uuid_restart_permuted_replay_and_reused_paths"])
    finally:
        if cid:
            response = subprocess.run(["podman", "rm", "--force", cid], capture_output=True, timeout=45)
            result["cleanup_error"] = None if response.returncode == 0 else response.stderr.decode(errors="replace")
            if response.returncode:
                raise RuntimeError("owned fixture container cleanup failed")
        if daemon:
            daemon.wait(timeout=15)
        if log:
            log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema11-gate", type=Path, required=True)
    parser.add_argument("--legacy-gate", type=Path, required=True)
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runtime = json.loads((ROOT / "scripts/rust-platform.json").read_text(encoding="utf-8"))["runtime"]
    gates = dict(schema11=checked_gate(args.schema11_gate, "2a31f233982669a8821bee42bf9691b27c1f39e7", runtime),
                 legacy=checked_gate(args.legacy_gate, "215cf93965f946f07cab99d2c0d25281ae743d78", runtime),
                 target=checked_gate(args.gate, git("rev-parse", "HEAD"), runtime))
    output = args.output.resolve()
    output.mkdir(mode=0o700)  # Never overwrite an earlier run.
    report = dict(status="FAILED", started_utc=datetime.now(timezone.utc).isoformat(), runtime=runtime,
                  checker_sha256=sha(Path(__file__)), helper_sha256=sha(ROOT / "scripts/nfs_fixture_contract.py"),
                  gates={k: v[2] for k, v in gates.items()}, profiles={},
                  limits="Disposable local roots in pinned SLES userspace; no NFS, shipping service, physical durability or working downgrade claim")
    try:
        for profile in ("debug", "release"):
            folder = output / profile
            folder.mkdir()
            result = dict(status="FAILED")
            report["profiles"][profile] = result
            exercise(profile, gates, folder, runtime, result)
        report["status"] = "PASSED"
    except Exception as error:
        report["error"] = repr(error)
        raise
    finally:
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
