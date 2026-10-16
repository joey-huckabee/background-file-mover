"""Destination-full copying and audited recovery on the fixture's bounded export.

Only fixed filler files in a 32 MiB tmpfs are removed. Never repair staging,
change SQLite or delete claimed sources. Uses the exact SLES-gated executable.
"""
import hashlib
import json
import time
from nfs_binding import binding_for, provision


def qualify_delivery_storage(run, execute, spawn, output, client, server, ip, options,
                             extra_mounts, report):
    mount, export = "/tmp/delivery-space", "/exports/delivery-space"
    size = 2*1048576+17
    digest = hashlib.sha256(b"A"*(2*1048576)+b"0123456789abcdefg").hexdigest()
    prefix_digest = hashlib.sha256(b"A"*1048576).hexdigest()

    def server_command(command, check=True):
        return run(["exec", server, "/bin/sh", "-eu", "-c", command], check=check)

    def observe(command, check=True):
        return execute(command, "1000:1000", target=client, check=check)

    server_command(f"mkdir {export}; mount -t tmpfs -o size=32m,nr_inodes=512,mode=1777 tmpfs {export}; "
                   f"mkdir {export}/fill; exportfs -i -o rw,sync,no_subtree_check,no_root_squash,fsid=30 '*:{export}'")
    execute("mkdir "+mount, target=client)
    run(["exec", client, "mount", "-i", "-t", "nfs4", "-o", options, ip+":/delivery-space", mount])
    extra_mounts.append((client, mount))
    report["mounts"] = execute("cat /proc/mounts", target=client).stdout.splitlines()
    report["server_mounts"] = server_command("cat /proc/mounts").stdout.splitlines()
    assert any(f" {mount} nfs4 " in line and "vers=4.1" in line and "hard" in line for line in report["mounts"])
    assert any(f" {export} tmpfs " in line and "size=32768k" in line and "nr_inodes=512" in line for line in report["server_mounts"])
    assert observe("getconf GNU_LIBC_VERSION").stdout.strip() == "glibc 2.22"
    report["scope"] = "Real bounded server tmpfs exhaustion during payload copying; live and restarted review/resume in debug/release. No injected errno or pause controls; no physical-disk/quota, power-loss, lost-lock or fencing qualification."

    def capacity():
        return [int(n) for n in server_command("stat -f -c '%b %f %a %c %d %S' "+export).stdout.split()]

    for profile in ("debug", "release"):
        binary = "/tmp/qualification-"+profile
        report.setdefault("artifacts", {})[profile] = observe("sha256sum "+binary).stdout.split()[0]
        for recovery in ("live", "restart"):
            label = "delivery-space-"+profile+"-"+recovery
            base = "/tmp/local/"+label
            source, destination = base+"/source", mount+"/"+label
            remote_destination = export+"/"+label
            observe(f"umask 077; mkdir -p {base}/state {source}/.file-mover {source}/current/nested {destination}/.file-mover; "
                    f"dd if=/dev/zero bs=1048576 count=2 2>/dev/null | tr '\\000' A >{source}/current/nested/data.bin; "
                    f"printf '0123456789abcdefg' >>{source}/current/nested/data.bin")
            assert observe("stat -f -c %t "+base+"/state").stdout.strip() != "6969"
            assert observe("sha256sum "+source+"/current/nested/data.bin").stdout.split()[0] == digest
            original = observe("stat -c '%d:%i:%u:%a:%s' "+source+"/current/nested/data.bin").stdout
            source_binding = binding_for(label, False)
            destination_binding = binding_for(label+"-destination", True, "destination")
            provision(run, execute, output, client, source, source_binding)
            provision(run, execute, output, client, destination, destination_binding)
            config = {"bind": "127.0.0.1:19887", "generator_id": "fixture", "source_root": source,
                      "destination_root": destination, "state_database": base+"/state/jobs.sqlite",
                      "source_binding": source_binding, "destination_binding": destination_binding}
            local = output/(label+"-config.json")
            local.write_text(json.dumps(config))
            run(["cp", str(local), client+":"+base+"/config.json"])
            observe(f"LD_BIND_NOW=1 {binary} --initialize-source {base}/config.json")
            roots = observe(f"stat -c '%d:%i:%u:%a' {source} {source}/.file-mover {destination} {destination}/.file-mover").stdout
            result = {"scenario_id": "SC-071", "profile": profile, "recovery": recovery, "passed": False,
                      "jobs_submitted": 1, "config_sha256": hashlib.sha256(local.read_bytes()).hexdigest(),
                      "samples": [], "health_status_seconds": [], "service_logs": {}}
            report["cases"].append(result)
            service, marker, counter, starts = None, base+"/service.pid", 0, 0

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
                response = observe("/bin/bash -c 'exec 3<>/dev/tcp/127.0.0.1/19887; "
                                   f"cat {remote} >&3; cat <&3'").stdout
                head, content = response.replace("\r\n", "\n").split("\n\n", 1)
                return int(head.split()[1]), json.loads(content)

            def status():
                began = time.monotonic()
                assert request("GET", "/healthz")[0] == 200
                code, body = request("GET", "/api/v2/jobs/1")
                assert code == 200
                elapsed = time.monotonic()-began
                result["health_status_seconds"].append(round(elapsed, 3))
                assert elapsed < 15, "health/status exceeded selected fixture window including engine overhead"
                return body

            def pid():
                value = observe("cat "+marker).stdout.strip()
                assert value.isdigit()
                return value

            def start():
                nonlocal service, starts
                starts += 1
                name = label+"-service-"+str(starts)
                service = spawn(f"echo $$ >{marker}; exec {binary} {base}/config.json", name, target=client)
                result["service_logs"][name] = ""
                for _ in range(100):
                    assert service.poll() is None, (output/(name+".log")).read_text()
                    if "Ready on" in (output/(name+".log")).read_text():
                        assert request("GET", "/healthz")[0] == 200
                        return pid()
                    time.sleep(0.1)
                raise RuntimeError("destination-full fixture startup did not reach readiness")

            def stop():
                if service is not None:
                    if service.poll() is None:
                        observe("kill -TERM "+pid())
                    assert service.wait(timeout=30) == 0

            def no_commit():
                assert observe(f"test ! -e {destination}/1/COMMITTED.json; test ! -e {destination}/1/nested/data.bin", check=False).returncode == 0
                assert server_command(f"test ! -e {remote_destination}/1/COMMITTED.json; test ! -e {remote_destination}/1/nested/data.bin", check=False).returncode == 0

            def partials():
                return server_command(f"for n in 1 2 3; do stat -c '%d:%i:%u:%a:%s' {remote_destination}/1/.staging/$n.part; "
                                      f"sha256sum {remote_destination}/1/.staging/$n.part; done").stdout

            body = {"generator_id": "fixture", "submission_id": label, "source_path": source+"/current",
                    "files": [{"name": "nested/data.bin"}]}
            private = source+"/.file-mover/1-0/data"
            try:
                owner_pid = start()
                free = capacity()
                assert free[0]*free[5] == 32*1048576 and free[1]*free[5] > 4*1048576
                filled = server_command(f"dd if=/dev/zero of={export}/fill/blocks bs=4096", check=False)
                assert filled.returncode != 0 and "No space left on device" in filled.stderr
                assert capacity()[1] == 0
                server_command(f"truncate -s -1048576 {export}/fill/blocks")
                result.update({"capacity_before": free, "fill_stderr": filled.stderr, "capacity_at_submission": capacity()})
                assert result["capacity_at_submission"][1]*free[5] == 1048576
                code, handoff = request("POST", "/api/v2/jobs", body)
                result["handoff"] = [code, handoff]
                assert code == 202 and handoff["job_id"] == "1" and handoff["source_paths_released"]
                assert observe("stat -c '%d:%i:%u:%a:%s' "+private).stdout == original
                observe(f"printf 'next recording' >{source}/current/nested/data.bin")
                deadline = time.monotonic()+120
                while True:
                    current = status()
                    result["samples"].append(current)
                    assert current["state"] == "Claimed" and current["source_paths_released"]
                    no_commit()
                    assert time.monotonic() < deadline, current
                    if current["details"]["condition"] == "ReviewRequired":
                        break
                    time.sleep(0.2)
                result["review_status"] = current
                assert current["details"]["delivery_retry"]["failures"] == 3
                assert current["details"]["files"][0]["attempt"] == 3
                assert current["details"]["files"][0]["transfer_phase"] == "Intent"
                assert capacity()[1] == 0
                partial = remote_destination+"/1/.staging/1.part"
                result["partial_server_bytes"] = int(server_command("stat -c %s "+partial).stdout)
                result["partial_server_sha256"] = server_command("sha256sum "+partial).stdout.split()[0]
                assert result["partial_server_bytes"] == 1048576 and result["partial_server_sha256"] == prefix_digest
                saved = partials()
                result["partials_at_review"] = saved
                assert observe("sha256sum "+private).stdout.split()[0] == digest
                if recovery == "restart":
                    stop()
                    owner_pid = start()
                    assert status() == current
                    assert partials() == saved
                    result["review_survived_original_state_restart"] = True
                server_command(f"rm {export}/fill/blocks")
                result["capacity_restored"] = capacity()
                time.sleep(1)
                assert status() == current
                no_commit()
                assert partials() == saved
                resume = {"command_id": label+"-resume", "expected_review_epoch": current["details"]["review_epoch"],
                          "reason": "Restored capacity in the owned destination fixture"}
                code, receipt = request("POST", "/api/v2/jobs/1/resume", resume)
                result["resume"] = [code, receipt]
                assert code == 200 and receipt["details"]["action"] == "DeliveryResumeScheduled"
                code, replay = request("POST", "/api/v2/jobs/1/resume", resume)
                assert code == 200 and replay["details"]["replay"] is True
                result["resume_replay"] = replay
                deadline = time.monotonic()+120
                while True:
                    completed = status()
                    if completed["state"] == "Committed":
                        break
                    assert completed["details"]["condition"] != "ReviewRequired", completed
                    assert time.monotonic() < deadline, completed
                    time.sleep(0.2)
                assert pid() == owner_pid
                assert completed["details"]["files"][0]["attempt"] == 4
                assert completed["details"]["source_cleanup_enabled"] is False
                assert completed["details"]["latest_resume"]["command_id"] == resume["command_id"]
                assert partials() == saved
                final = destination+"/1/nested/data.bin"
                hashes = observe(f"sha256sum {private} {final}").stdout.splitlines()
                assert [line.split()[0] for line in hashes] == [digest, digest]
                assert server_command("sha256sum "+remote_destination+"/1/nested/data.bin").stdout.split()[0] == digest
                manifest_text = observe(f"cat {destination}/1/COMMITTED.json").stdout
                manifest = json.loads(manifest_text)
                assert manifest["version"] == 1 and manifest["job_id"] == "1"
                assert manifest["generator_id"] == "fixture" and manifest["submission_id"] == label
                assert [(f["path"], f["size_bytes"], f["algorithm"], f["sha256"]) for f in manifest["files"]] == [("nested/data.bin", size, "sha256", digest)]
                assert server_command("cat "+remote_destination+"/1/COMMITTED.json").stdout == manifest_text
                code, submission_replay = request("POST", "/api/v2/jobs", body)
                assert code == 202 and submission_replay["job_id"] == "1" and submission_replay["source_paths_released"]
                result["submission_replay"] = submission_replay
                assert observe(f"cat {source}/current/nested/data.bin").stdout == "next recording"
                assert observe("stat -c '%d:%i:%u:%a:%s' "+private).stdout == original
                assert observe(f"stat -c '%d:%i:%u:%a' {source} {source}/.file-mover {destination} {destination}/.file-mover").stdout == roots
                result.update({"completed_status": completed, "manifest": manifest, "hashes": hashes,
                               "source_retained": True, "producer_reused_path_unchanged": True,
                               "old_partials_preserved": True, "recovered_job_id": "1", "recovery_coordinator_pid_stable": True})
                if recovery == "restart":
                    stop()
                    start()
                    assert status() == completed
                    assert observe(f"cat {destination}/1/COMMITTED.json").stdout == manifest_text
                    result["commit_survived_original_state_restart"] = True
                result["passed"] = True
            finally:
                # Restore bounded capacity before shutdown; never remove sources/staging.
                server_command(f"rm -f {export}/fill/blocks")
                stop()
                result["service_logs"] = {name: (output/(name+".log")).read_text() for name in result["service_logs"]}
                (output/(label+"-result.json")).write_text(json.dumps(result, indent=2)+"\n")
            print(f"NFS destination full {profile}/{recovery}: PASS (claimed source retained; audited resume committed)", flush=True)
    report["passed"] = True
