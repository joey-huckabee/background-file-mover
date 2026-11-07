"""Native source admission on a bounded NFS export; no injected errors.

Only the fixture-owned filler is removed. Never change state, policy or claimed
sources to restore admission. Reuse exact artifacts from the mandatory SLES gate.
"""
import hashlib
import json
import time
from nfs_binding import binding_for, provision


def qualify_source_storage(run, execute, spawn, output, client, server, ip, options,
                           extra_mounts, report):
    mount, export = "/tmp/source-space", "/exports/source-space"

    def server_command(command, check=True):
        return run(["exec", server, "/bin/sh", "-eu", "-c", command], check=check)

    def observe(command, check=True):
        return execute(command, "1000:1000", target=client, check=check)

    server_command(f"mkdir {export}; mount -t tmpfs -o size=32m,nr_inodes=512,mode=1777 tmpfs {export}; "
                   f"mkdir {export}/fill; exportfs -i -o rw,sync,no_subtree_check,no_root_squash,fsid=38 '*:{export}'")
    execute("mkdir "+mount, target=client)
    run(["exec", client, "mount", "-i", "-t", "nfs4", "-o", options, ip+":/source-space", mount])
    extra_mounts.append((client, mount))
    report["mounts"] = execute("cat /proc/mounts", target=client).stdout.splitlines()
    report["server_mounts"] = server_command("cat /proc/mounts").stdout.splitlines()
    assert any(f" {mount} nfs4 " in m and "vers=4.1" in m and "hard" in m for m in report["mounts"])
    assert any(f" {export} tmpfs " in m and "size=32768k" in m and "nr_inodes=512" in m for m in report["server_mounts"])
    assert observe("getconf GNU_LIBC_VERSION").stdout.strip() == "glibc 2.22"
    report["scope"] = "Native bounded 32 MiB server tmpfs source depletion/restoration, unchanged enabled policy and live coordinator, local SQLite/destination, hard NFSv4.1, debug/release. No quota/inode exhaustion, blocked statistics RPC, physical disk, power-loss or fencing qualification."

    def capacity():
        return [int(n) for n in server_command("stat -f -c '%b %f %a %c %d %S' "+export).stdout.split()]

    for profile in ("debug", "release"):
        binary = "/tmp/qualification-"+profile
        report.setdefault("artifacts", {})[profile] = observe("sha256sum "+binary).stdout.split()[0]
        label = "source-space-"+profile
        base, source = "/tmp/local/"+label, mount+"/"+label
        destination = base+"/destination"
        observe(f"umask 077; mkdir -p {base}/state {destination}/.file-mover {source}/.file-mover {source}/current/nested; "
                f"printf 'claimed source' >{source}/current/nested/first; "
                f"printf 'partial source' >{source}/current/nested/a; "
                f"printf 'new source' >{source}/current/nested/new")
        assert observe("stat -f -c %t "+base+"/state").stdout.strip() != "6969"
        assert observe("stat -f -c %t "+source).stdout.strip() == "6969"
        source_binding = binding_for(label, True)
        destination_binding = binding_for(label+"-destination", False, "destination")
        provision(run, execute, output, client, source, source_binding)
        provision(run, execute, output, client, destination, destination_binding)
        config = {"bind": "127.0.0.1:19888", "generator_id": "fixture", "source_root": source,
                  "destination_root": destination, "state_database": base+"/state/jobs.sqlite",
                  "source_binding": source_binding, "destination_binding": destination_binding,
                  "source_space_admission": {"enabled": True, "min_available_bytes": 4*1048576,
                    "min_available_percent": 5, "max_sample_age_seconds": 5, "probe_timeout_seconds": 2}}
        local = output/(label+"-config.json")
        local.write_text(json.dumps(config), encoding="utf-8")
        run(["cp", str(local), client+":"+base+"/config.json"])
        config_hash = hashlib.sha256(local.read_bytes()).hexdigest()
        observe(f"LD_BIND_NOW=1 {binary} --initialize-source {base}/config.json")
        result = {"profile": profile, "scenario_ids": ["SC-076", "SC-078", "SC-080", "SC-081"],
                  "passed": False, "config_sha256": config_hash, "observations": []}
        report["cases"].append(result)
        counter, service = 0, None
        marker = base+"/service.pid"

        def request(method, path, body=None):
            nonlocal counter
            counter += 1
            payload = json.dumps(body).encode() if body is not None else b""
            name = label+"-request-"+str(counter)
            raw = (f"{method} {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n"
                   f"Content-Type: application/json\r\nContent-Length: {len(payload)}\r\n\r\n").encode()+payload
            (output/name).write_bytes(raw)
            remote = base+"/request-"+str(counter)
            run(["cp", str(output/name), client+":"+remote])
            response = observe("/bin/bash -c 'exec 3<>/dev/tcp/127.0.0.1/19888; "
                               f"cat {remote} >&3; cat <&3'").stdout
            head, content = response.replace("\r\n", "\n").split("\n\n", 1)
            return int(head.split()[1]), json.loads(content)

        def submission(key, names):
            return {"generator_id": "fixture", "submission_id": label+"-"+key,
                    "source_path": source+"/current", "files": [{"name": "nested/"+n} for n in names]}

        def snapshot():
            code, body = request("GET", "/api/v2/retention")
            assert code == 200
            return body["details"]

        def until_response(body, code, error=None):
            deadline = time.monotonic()+20
            while True:
                actual, reply = request("POST", "/api/v2/jobs", body)
                result["observations"].append({"code": actual, "reply": reply})
                if actual == code and (error is None or reply.get("error") == error):
                    return reply
                assert actual == 503 and reply["error"] == "source_space_unavailable", reply
                assert time.monotonic() < deadline, reply
                time.sleep(1.1)

        def committed(job):
            deadline = time.monotonic()+30
            while True:
                code, body = request("GET", "/api/v2/jobs/"+job)
                assert code == 200
                if body["state"] == "Committed":
                    return body
                assert time.monotonic() < deadline, body
                time.sleep(0.2)

        first = submission("claimed", ["first"])
        partial = submission("partial", ["a", "b"])
        new = submission("new", ["new"])
        originals = {}
        for name in ("first", "a", "new"):
            path = source+"/current/nested/"+name
            originals[name] = observe("stat -c '%d:%i:%u:%a:%s' "+path).stdout
        try:
            service = spawn(f"echo $$ >{marker}; exec {binary} {base}/config.json", label, target=client)
            for _ in range(100):
                assert service.poll() is None, (output/(label+".log")).read_text(encoding="utf-8")
                if "Ready on" in (output/(label+".log")).read_text(encoding="utf-8"):
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("source-space fixture did not become ready")
            pid = observe("cat "+marker).stdout.strip()
            assert pid.isdigit()
            first_reply = until_response(first, 202)
            assert first_reply["job_id"] == "1" and first_reply["source_paths_released"]
            committed("1")
            code, pending = request("POST", "/api/v2/jobs", partial)
            assert code == 503 and pending["error"] == "handoff_pending", pending
            assert not pending["source_paths_released"]
            assert observe("stat -c '%d:%i:%u:%a:%s' "+source+"/.file-mover/2-0/data").stdout == originals["a"]
            observe(f"printf 'producer next first' >{source}/current/nested/first")
            result["capacity_before"] = capacity()
            assert result["capacity_before"][0]*result["capacity_before"][5] == 32*1048576
            filled = server_command(f"dd if=/dev/zero of={export}/fill/blocks bs=4096", check=False)
            assert filled.returncode != 0 and "No space left on device" in filled.stderr
            assert capacity()[1] == 0
            server_command(f"truncate -s -1048576 {export}/fill/blocks")
            result["fill_stderr"] = filled.stderr
            result["capacity_low"] = capacity()
            assert result["capacity_low"][1]*result["capacity_low"][5] == 1048576
            time.sleep(5.1)  # Expire the sufficient sample; no policy change.
            refused = until_response(new, 503, "source_space_low")
            assert not refused["source_paths_released"] and "job_id" not in refused
            low = snapshot()
            sample = low["source_space_admission"]
            assert sample["state"] == "Low", sample
            assert int(sample["observed_available_bytes"]) < int(sample["required_available_bytes"])
            assert int(sample["required_available_bytes"]) == 4*1048576
            assert low["retained_jobs"] == 2
            assert request("GET", "/api/v2/jobs/3")[0] == 404
            assert observe(f"test ! -e {source}/.file-mover/3-0", check=False).returncode == 0
            assert observe("stat -c '%d:%i:%u:%a:%s' "+source+"/current/nested/new").stdout == originals["new"]
            result["low_status"] = low
            code, replay = request("POST", "/api/v2/jobs", first)
            assert code == 202 and replay["job_id"] == "1" and replay["source_paths_released"]
            code, missing = request("POST", "/api/v2/jobs", partial)
            assert code == 503 and missing["error"] == "handoff_pending"
            assert not missing["source_paths_released"]
            observe(f"printf 'late partial source' >{source}/current/nested/b")
            code, finished = request("POST", "/api/v2/jobs", partial)
            assert code == 202 and finished["job_id"] == "2" and finished["source_paths_released"]
            committed("2")
            observe(f"printf 'producer next partial' >{source}/current/nested/a")
            # A fresh refusal after partial recovery proves capacity is still Low.
            refused_again = until_response(new, 503, "source_space_low")
            assert not refused_again["source_paths_released"] and "job_id" not in refused_again
            assert snapshot()["retained_jobs"] == 2
            assert request("GET", "/healthz")[0] == 200
            server_command(f"rm {export}/fill/blocks")
            result["capacity_restored"] = capacity()
            assert result["capacity_restored"][2]*result["capacity_restored"][5] > 4*1048576
            time.sleep(5.1)
            recovered = until_response(new, 202)
            assert recovered["job_id"] == "3" and recovered["source_paths_released"]
            committed("3")
            assert observe("cat "+marker).stdout.strip() == pid
            assert observe("sha256sum "+base+"/config.json").stdout.split()[0] == config_hash
            # Source identity, payload and consumer evidence all survive native fill.
            expected = {"1": [("first", "claimed source", "1-0")],
                        "2": [("a", "partial source", "2-0"), ("b", "late partial source", "2-1")],
                        "3": [("new", "new source", "3-0")]}
            manifests = {}
            for job, files in expected.items():
                manifest = json.loads(observe(f"cat {destination}/{job}/COMMITTED.json").stdout)
                assert manifest["job_id"] == job and manifest["version"] == 1
                for name, content, private in files:
                    digest = hashlib.sha256(content.encode()).hexdigest()
                    assert observe(f"sha256sum {source}/.file-mover/{private}/data").stdout.split()[0] == digest
                    assert observe(f"sha256sum {destination}/{job}/nested/{name}").stdout.split()[0] == digest
                    entry = next(f for f in manifest["files"] if f["path"] == "nested/"+name)
                    assert entry["size_bytes"] == len(content) and entry["sha256"] == digest and entry["algorithm"] == "sha256"
                    if name in originals:
                        assert observe(f"stat -c '%d:%i:%u:%a:%s' {source}/.file-mover/{private}/data").stdout == originals[name]
                manifests[job] = manifest
            assert observe(f"cat {source}/current/nested/first").stdout == "producer next first"
            assert observe(f"cat {source}/current/nested/a").stdout == "producer next partial"
            result.update({"recovered_reply": recovered, "manifests": manifests,
                           "coordinator_pid_unchanged": True, "policy_unchanged": True,
                           "source_retained": True, "producer_reused_paths_preserved": True,
                           "partial_recovery_while_low": True, "passed": True})
        finally:
            server_command(f"rm -f {export}/fill/blocks")
            if service is not None:
                if service.poll() is None:
                    observe("kill -TERM $(cat "+marker+")")
                assert service.wait(timeout=30) == 0
            result["service_log"] = (output/(label+".log")).read_text(encoding="utf-8")
            (output/(label+"-result.json")).write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
        print(f"NFS source space {profile}: PASS (native Low refusal, partial replay, unchanged-policy live recovery)", flush=True)
    report["passed"] = True
