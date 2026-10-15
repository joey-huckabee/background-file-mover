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
                (output / (label+"-result.json")).write_text(json.dumps(result, indent=2)+"\n")
                print(f"NFS inherited custody {profile}/{point}: PASS (peer excluded through worker exit; original state recovered)", flush=True)
    finally:
        for pid in workers:
            if state(pid) not in {"gone", "Z"}:
                observe(client, f"kill -KILL {pid}")
                await_exit(pid)
        for process in requests:
            process.wait(timeout=15)
