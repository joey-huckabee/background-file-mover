"""Actual assigned Rust child custody across coordinator death on two NFS clients.

No outage, lock loss or independent-state takeover is authorized by these probes.
"""
import hashlib
import json
import time
from nfs_binding import binding_for, provision


def qualify_inherited_custody(run, execute, spawn, output, client, peer,
                             start, stop, snapshot, cases):
    workers = []
    requests = []

    def observe(target, command, check=True):
        return execute(command, "1000:1000", check=check, target=target)

    def state(pid):
        result = observe(client, f"cat /proc/{pid}/stat", check=False)
        if result.returncode == 0:
            return result.stdout.rsplit(")", 1)[1].split()[0]
        assert observe(client, f"test ! -d /proc/{pid}", check=False).returncode == 0
        return "gone"

    def await_exit(pid):
        for _ in range(60):
            value = state(pid)
            if value in {"gone", "Z"}:
                return value
            time.sleep(0.1)
        raise RuntimeError("assigned worker exit unconfirmed")

    def request(label, method, path, body=None, background=False):
        payload = json.dumps(body) if body is not None else ""
        text = (f"{method} {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n"
                + (f"Content-Type: application/json\r\nContent-Length: {len(payload.encode())}\r\n" if body is not None else "")
                + "\r\n" + payload)
        local = output / (label + "-request.txt")
        local.write_bytes(text.encode())
        remote = "/tmp/local/" + label + "-request.txt"
        run(["cp", str(local), client + ":" + remote])
        command = ("/bin/bash -c 'exec 3<>/dev/tcp/127.0.0.1/19882; "
                   f"cat {remote} >&3; cat <&3'")
        if background:
            process = spawn(command, label, target=client)
            requests.append(process)
            return process
        result = observe(client, command).stdout
        head, content = result.replace("\r\n", "\n").split("\n\n", 1)
        return int(head.split()[1]), json.loads(content)

    try:
        for profile in ("debug", "release"):
            for point in ("claim_apply", "publish"):
                label = "custody-" + profile + "-" + point
                source = "/tmp/nfs/" + label + "/source"
                destination = "/tmp/nfs/" + label + "/destination"
                rendezvous = "/tmp/local/" + label + "/pause"
                observe(client, f"umask 077; mkdir -p {source}/.file-mover {source}/current {destination}/.file-mover; "
                        f"printf 'inherited custody payload' >{source}/current/data.bin")
                provision(run, execute, output, client, source, binding_for(label, True))
                provision(run, execute, output, client, destination, binding_for(label+"-destination", True, "destination"))
                owner_label = label + "-owner"
                owner = start(client, owner_label, profile, source, 19882,
                              initialize=True,
                              binding_label=label, destination=destination, pause=(point, rendezvous))
                assert owner["ready"]
                body = {"generator_id": "fixture", "submission_id": label,
                        "source_path": source + "/current", "files": [{"name": "data.bin"}]}
                posted = request(label+"-post", "POST", "/api/v2/jobs", body, background=True)
                for _ in range(100):
                    ready = observe(client, "cat " + rendezvous + "/ready", check=False)
                    if ready.returncode == 0 and ready.stdout.endswith("\n"):
                        pid, actual = ready.stdout.split()
                        assert pid.isdigit() and actual == point
                        workers.append(pid)
                        break
                    assert owner["process"].poll() is None
                    time.sleep(0.1)
                else:
                    raise RuntimeError("actual worker did not reach custody rendezvous")
                expected_mode = "--internal-claim-worker" if point == "claim_apply" else "--internal-delivery-worker"
                command = observe(client, f"tr '\\000' ' ' </proc/{pid}/cmdline").stdout
                assert expected_mode in command and "/tmp/ownership-qualification-"+profile in command
                parent_pid = observe(client, "cat " + owner["marker"]).stdout.strip()
                assert parent_pid.isdigit()
                children = observe(client, f"for task in /proc/{parent_pid}/task/*/children; do cat $task; done").stdout.split()
                assert set(children) == {pid}
                before = request(label+"-status", "GET", "/api/v2/jobs/1")[1]
                assert before["state"] == ("Accepted" if point == "claim_apply" else "Claimed")
                observe(client, f"kill -STOP {pid}")
                assert state(pid) in {"T", "t"}
                observe(client, "kill -KILL " + parent_pid)
                assert owner["process"].wait(timeout=15) != 0
                competitor = start(peer, label+"-competitor", profile, source, 19883,
                                   binding_label=label, destination=destination)
                assert not competitor["ready"]
                assert state(pid) in {"T", "t"}, "worker did not survive coordinator death"
                scopes = [source] + ([destination] if point == "publish" else [])
                for scope in scopes:
                    conflict = observe(peer, f"test -f {scope}/.file-mover/coordinator.lock; "
                                       f"exec 9<>{scope}/.file-mover/coordinator.lock; flock -xn 9", check=False)
                    assert conflict.returncode == 1 and not conflict.stderr
                result = {"profile": profile, "scenario_id": "SC-062", "point": point,
                          "probe_completed": False, "jobs_submitted": 1, "worker_pid": pid,
                          "worker_command": command, "status_at_pause": before,
                          "coordinator_exit_confirmed": True, "worker_survived_coordinator": True,
                          "cross_client_startup_excluded": True, "competitor": snapshot(competitor),
                          "held_scopes": scopes, "peer_file_lock_controls_excluded": True}
                cases.append(result)
                observe(client, f"kill -KILL {pid}")
                result["worker_exit"] = await_exit(pid)
                for scope in scopes:
                    for _ in range(30):
                        released = observe(peer, f"test -f {scope}/.file-mover/coordinator.lock; "
                                           f"exec 9<>{scope}/.file-mover/coordinator.lock; flock -xn 9", check=False)
                        if released.returncode == 0:
                            break
                        assert released.returncode == 1 and not released.stderr
                        time.sleep(0.2)
                    else:
                        raise RuntimeError("peer did not observe lock release after confirmed worker exit")
                result["peer_file_lock_controls_released_after_worker_exit"] = True
                posted.wait(timeout=15)
                old_reply = (output / (label+"-post.log")).read_text()
                if old_reply.startswith("HTTP/") and point == "claim_apply":
                    assert old_reply.split()[1] != "202"
                recovered = start(client, label+"-recovery", profile, source, 19882,
                                  state_label=owner_label, binding_label=label, destination=destination)
                assert recovered["ready"] and recovered["config_sha256"] == owner["config_sha256"]
                assert request(label+"-replay", "POST", "/api/v2/jobs", body)[0] == 202
                deadline = time.monotonic() + 30
                while True:
                    status = request(label+"-recovery-status", "GET", "/api/v2/jobs/1")[1]
                    if status["state"] == "Committed":
                        break
                    assert time.monotonic() < deadline, status
                    time.sleep(0.2)
                expected = hashlib.sha256(b"inherited custody payload").hexdigest()
                hashes = observe(client, f"sha256sum {source}/.file-mover/1-0/data {destination}/1/data.bin").stdout.splitlines()
                assert [h.split()[0] for h in hashes] == [expected, expected]
                manifest = json.loads(observe(client, f"cat {destination}/1/COMMITTED.json").stdout)
                assert manifest["submission_id"] == label and manifest["files"][0]["sha256"] == expected
                result.update({"same_original_state_recovered": True, "recovered_status": status,
                               "source_retained": True, "hashes": hashes, "probe_completed": True})
                stop(recovered)
                fresh = start(peer, label+"-fresh-state", profile, source, 19883,
                              binding_label=label, destination=destination, allow_state_creation=True)
                assert not fresh["ready"] and "SourceEnrollmentRequired" in fresh["log"]
                fresh_config = "/tmp/local/ownership-"+label+"-fresh-state/config.json"
                rejected = observe(peer, f"/tmp/ownership-qualification-{profile} --initialize-source {fresh_config}", check=False)
                assert rejected.returncode != 0
                assert observe(client, f"sha256sum {source}/.file-mover/1-0/data {destination}/1/data.bin").stdout.splitlines() == hashes
                result["populated_source_fresh_state_refused"] = snapshot(fresh)
                result["explicit_fresh_initialization_refused"] = True
                (output / (label+"-result.json")).write_text(json.dumps(result, indent=2)+"\n")
                print(f"NFS inherited custody {profile}/{point}: PASS (peer excluded through worker exit; original state recovered)", flush=True)
    finally:
        for pid in workers:
            if state(pid) not in {"gone", "Z"}:
                observe(client, f"kill -KILL {pid}")
                await_exit(pid)
        for process in requests:
            process.wait(timeout=15)


def qualify_enrollment(run, execute, spawn, output, client, start, stop, snapshot, cases):
    """Actual process death at local intent and source create/sync/result boundaries.

    These selected pauses are not an outage, in-flight RPC or power-loss test.
    """
    def observe(command, check=True):
        return execute(command, "1000:1000", target=client, check=check)

    def exited(pid):
        result = observe(f"cat /proc/{pid}/stat", check=False)
        return result.returncode != 0 or result.stdout.rsplit(")", 1)[1].split()[0] == "Z"

    for profile in ("debug", "release"):
        for point in ("enrollment_intent", "enrollment_prepared", "enrollment_created",
                      "enrollment_sync", "enrollment_directory_sync", "enrollment_receipt", "enrollment_active"):
            no_receipt = point in {"enrollment_intent", "enrollment_prepared"}
            retry_succeeds = no_receipt or point == "enrollment_active"
            label = "enrollment-"+profile+"-"+point
            source = "/tmp/nfs/"+label+"/source"
            observe(f"umask 077; mkdir -p {source}/.file-mover {source}/current; printf 'producer-owned input' >{source}/current/data")
            provision(run, execute, output, client, source, binding_for(label, True))
            pending = start(client, label, profile, source, 19884, binding_label=label, allow_state_creation=True)
            assert not pending["ready"] and "SourceEnrollmentRequired" in pending["log"]
            base = "/tmp/local/ownership-"+label
            rendezvous = base+"/pause"
            observe(f"umask 077; mkdir {rendezvous}")
            binary = "/tmp/ownership-qualification-"+profile
            marker = base+"/initialize.pid"
            process = spawn(f"echo $$ >{marker}; exec env FILE_MOVER_QUALIFICATION_PAUSE={point} "
                            f"FILE_MOVER_QUALIFICATION_RENDEZVOUS={rendezvous} {binary} --initialize-source {base}/config.json",
                            label+"-initialize", target=client)
            parent = None
            child = None
            try:
                for _ in range(100):
                    ready = observe("cat "+rendezvous+"/ready", check=False)
                    if ready.returncode == 0 and ready.stdout.endswith("\n"):
                        pid, actual = ready.stdout.split()
                        assert pid.isdigit() and actual == point
                        break
                    assert process.poll() is None
                    time.sleep(0.1)
                else:
                    raise RuntimeError("enrollment did not reach rendezvous: "+point)
                parent = observe("cat "+marker).stdout.strip()
                assert parent.isdigit()
                if point in {"enrollment_intent", "enrollment_prepared", "enrollment_active"}:
                    assert pid == parent
                else:
                    child = pid
                    command = observe(f"tr '\\000' ' ' </proc/{child}/cmdline").stdout
                    assert "--internal-enrollment-worker" in command
                    observe("kill -STOP "+child)
                receipt = source+"/.file-mover/source-enrollment.json"
                before = observe(f"stat -c '%d:%i:%u:%a:%s' {receipt}; sha256sum {receipt}", check=False)
                assert (before.returncode == 0) == (not no_receipt)
                observe("kill -KILL "+parent)
                assert process.wait(timeout=15) != 0
                if child:
                    observe("kill -KILL "+child)
                    for _ in range(100):
                        if exited(child):
                            break
                        time.sleep(0.1)
                    else:
                        raise RuntimeError("enrollment child exit unconfirmed")
                blocked = start(client, label+"-pending", profile, source, 19884,
                                state_label=label, binding_label=label, allow_state_recovery=True)
                if point == "enrollment_active":
                    assert blocked["ready"]
                    stop(blocked)
                else:
                    assert not blocked["ready"]
                    assert ("SourceEnrollmentRequired" if point == "enrollment_intent" else "enrollment pending") in blocked["log"]
                retried = observe(f"{binary} --initialize-source {base}/config.json", check=False)
                (output/(label+"-retry.json")).write_text(json.dumps({"returncode":retried.returncode,
                    "stdout":retried.stdout,"stderr":retried.stderr},indent=2)+"\n")
                assert (retried.returncode == 0) == retry_succeeds, retried.stdout+retried.stderr
                if no_receipt:
                    recovered = start(client, label+"-active", profile, source, 19884,
                                      state_label=label, binding_label=label)
                    assert recovered["ready"]
                    stop(recovered)
                else:
                    after = observe(f"stat -c '%d:%i:%u:%a:%s' {receipt}; sha256sum {receipt}")
                    assert after.stdout == before.stdout
                assert observe("cat "+source+"/current/data").stdout == "producer-owned input"
                result = {"scenario_id": "SC-065", "profile": profile, "point": point,
                          "probe_completed": True, "jobs_submitted": 0,
                          "parent_exit_confirmed": True, "child_exit_confirmed": child is not None,
                          "sqlite_main_changed_after_crash_recovery": blocked.get("sqlite_main_changed_after_crash_recovery",False),
                          "ordinary_startup": snapshot(blocked),
                          "explicit_retry_active": retry_succeeds,
                          "ambiguous_receipt_preserved": not retry_succeeds,
                          "producer_input_unchanged": True}
                cases.append(result)
                (output/(label+"-result.json")).write_text(json.dumps(result, indent=2)+"\n")
                print(f"NFS enrollment {profile}/{point}: PASS (startup/retry matched durable phase)", flush=True)
            finally:
                if parent and not exited(parent):
                    observe("kill -KILL "+parent, check=False)
                if child and not exited(child):
                    observe("kill -KILL "+child, check=False)
                process.wait(timeout=30)
                if child:
                    for _ in range(100):
                        if exited(child):
                            break
                        time.sleep(0.1)
                    else:
                        raise RuntimeError("enrollment cleanup child exit unconfirmed")
