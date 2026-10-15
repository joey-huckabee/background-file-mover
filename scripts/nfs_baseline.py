"""REST-driven normal-operation checks using audited qualification executables.

Called only after the owning runner establishes its isolated hard NFS fixture.
All shell paths are fixed fixture paths; no producer/user paths are interpolated.
"""
import hashlib
import json
import time
from nfs_binding import binding_for, provision


def run_baseline(gate, evidence, run, execute, spawn, output, client):
    results = []
    expected = [hashlib.sha256(b"NFS qualification\n").hexdigest(),
                hashlib.sha256(bytes(2 * 1048576) + b"0123456789abcdefg").hexdigest(),
                hashlib.sha256(b"").hexdigest()]
    names = ["top.txt", "nested/data.bin", "empty"]
    sizes = [18, 2 * 1048576 + 17, 0]

    def request(method, path, body=None):
        payload = json.dumps(body).encode() if body is not None else b""
        raw = (f"{method} {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n"
               f"Content-Type: application/json\r\nContent-Length: {len(payload)}\r\n\r\n").encode() + payload
        local = output / "baseline-request"
        local.write_bytes(raw)
        run(["cp", str(local), client + ":/tmp/baseline-request"])
        result = execute("/bin/bash -c 'exec 3<>/dev/tcp/127.0.0.1/19877; cat /tmp/baseline-request >&3; cat <&3'",
                         "1000:1000", check=False)
        if result.returncode:
            raise RuntimeError(result.stderr)
        head, payload = result.stdout.split("\n\n", 1)
        return int(head.split()[1]), json.loads(payload)

    for profile in ("debug", "release"):
        artifact = next(a for a in evidence["profiles"][profile]["artifacts"] if not a["test"])
        binary = gate / artifact["name"]
        digest = hashlib.sha256(binary.read_bytes()).hexdigest()
        assert digest == artifact["sha256"]
        remote_binary = "/tmp/qualification-" + profile
        run(["cp", str(binary), client + ":" + remote_binary])
        execute("chmod 755 " + remote_binary)
        assert execute("sha256sum " + remote_binary).stdout.split()[0] == digest
        loaded = execute("ldd -r " + remote_binary).stdout
        assert "not found" not in loaded and "undefined symbol" not in loaded
        assert "build=nfs-qualification" in execute(remote_binary + " --check-platform", "1000:1000").stdout
        for direction in ("source", "destination", "both"):
            label = profile + "-" + direction
            source = ("/tmp/local/" if direction == "destination" else "/tmp/nfs/") + label + "/source"
            destination = ("/tmp/local/" if direction == "source" else "/tmp/nfs/") + label + "/destination"
            state = "/tmp/local/" + label + "/state"
            execute(f"umask 077; mkdir -p {source}/.file-mover {source}/current/nested {destination}/.file-mover {state}; "
                    f"printf 'NFS qualification\\n' >{source}/current/top.txt; "
                    f"dd if=/dev/zero of={source}/current/nested/data.bin bs=1048576 count=2 2>/dev/null; "
                    f"printf '0123456789abcdefg' >>{source}/current/nested/data.bin; : >{source}/current/empty", "1000:1000")
            # Assert the actual directional filesystems; never test an underlying directory.
            assert (execute(f"stat -f -c %t {source}", "1000:1000").stdout.strip() == "6969") == (direction != "destination")
            assert (execute(f"stat -f -c %t {destination}", "1000:1000").stdout.strip() == "6969") == (direction != "source")
            assert execute(f"stat -f -c %t {state}", "1000:1000").stdout.strip() != "6969"
            config = {"bind": "127.0.0.1:19877", "generator_id": "fixture", "source_root": source,
                      "destination_root": destination, "state_database": state + "/jobs.sqlite"}
            config["destination_binding"] = binding_for(label+"-destination", direction != "source", "destination")
            provision(run, execute, output, client, destination, config["destination_binding"])
            config["source_binding"] = binding_for(label, direction != "destination")
            provision(run, execute, output, client, source, config["source_binding"])
            config_path = output / (label + "-config.json")
            config_path.write_text(json.dumps(config))
            run(["cp", str(config_path), client + ":/tmp/baseline-config.json"])
            process = spawn(f"echo $$ >/tmp/local/baseline.pid; exec {remote_binary} /tmp/baseline-config.json", label)
            result = {"profile": profile, "direction": direction, "binary_sha256": digest, "passed": False}
            try:
                for _ in range(20):
                    if process.poll() is not None:
                        raise RuntimeError("qualification startup failed")
                    try:
                        if request("GET", "/healthz")[0] == 200:
                            break
                    except (RuntimeError, ValueError):
                        time.sleep(0.2)
                else:
                    raise RuntimeError("no startup health response")
                body = {"generator_id": "fixture", "submission_id": label, "source_path": source + "/current",
                        "files": [{"name": name} for name in names]}
                code, response = request("POST", "/api/v2/jobs", body)
                result["handoff"] = {"code": code, "body": response}
                if code != 202:
                    result["stage"] = "handoff"
                    result["status"] = request("GET", "/api/v2/jobs/1")
                    result["original_hashes"] = execute("sha256sum " + " ".join(source + "/current/" + n for n in names), "1000:1000").stdout.splitlines()
                    result["source_intact"] = [line.split()[0] for line in result["original_hashes"]] == expected
                    result["manifest_absent"] = execute(f"test ! -e {destination}/1/COMMITTED.json", "1000:1000", check=False).returncode == 0
                    continue
                assert request("POST", "/api/v2/jobs", body)[0] == 202
                for name in names:
                    execute(f"printf 'next recording' >{source}/current/{name}", "1000:1000")
                deadline = time.monotonic() + 30
                while True:
                    status = request("GET", "/api/v2/jobs/1")
                    result["status"] = status
                    if status[1]["state"] == "Committed":
                        break
                    if status[1].get("details", {}).get("condition") == "ReviewRequired" or time.monotonic() >= deadline:
                        result["stage"] = "delivery"
                        break
                    time.sleep(0.5)
                private = [source + f"/.file-mover/1-{i}/data" for i in range(3)]
                result["private_hashes"] = execute("sha256sum " + " ".join(private), "1000:1000").stdout.splitlines()
                assert [line.split()[0] for line in result["private_hashes"]] == expected
                result["source_retained"] = True
                for name in names:
                    assert execute(f"cat {source}/current/{name}", "1000:1000").stdout == "next recording"
                result["original_paths_reused"] = True
                if result.get("stage") == "delivery":
                    result["manifest_absent"] = execute(f"test ! -e {destination}/1/COMMITTED.json", "1000:1000", check=False).returncode == 0
                    stage = destination + "/1/.staging/1.part"
                    if execute(f"test -f {stage}", "1000:1000", check=False).returncode == 0:
                        result["first_stage_hash"] = execute(f"sha256sum {stage}", "1000:1000").stdout.split()[0]
                        result["first_stage_intact"] = result["first_stage_hash"] == expected[0]
                        assert result["first_stage_intact"]
                    continue
                manifest = json.loads(execute(f"cat {destination}/1/COMMITTED.json", "1000:1000").stdout)
                assert manifest["version"] == 1 and manifest["submission_id"] == label
                assert [(f["path"], f["size_bytes"], f["algorithm"], f["sha256"]) for f in manifest["files"]] == list(zip(names, sizes, ["sha256"] * 3, expected))
                actual = execute("sha256sum " + " ".join(destination + "/1/" + n for n in names), "1000:1000").stdout.splitlines()
                assert [line.split()[0] for line in actual] == expected
                result["manifest"] = manifest
                result["passed"] = True
            except Exception as error:
                result["error"] = str(error)
            finally:
                execute("kill -TERM $(cat /tmp/local/baseline.pid) 2>/dev/null || true", "1000:1000")
                assert process.wait(timeout=30) == 0, "baseline service did not shut down cleanly"
                result["service_log"] = (output / (label + ".log")).read_text()
                results.append(result)
                print(f"NFS baseline {label}: {'PASS' if result['passed'] else 'BLOCKED'}", flush=True)
    return {"passed": all(r["passed"] for r in results), "cases": results}
