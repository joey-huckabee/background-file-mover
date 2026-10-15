"""Real hard-mounted receipt-read startup/shutdown qualification in owned scopes.

Read cancellation is observed, not assumed. Restore NFS before cleanup if a child
cannot exit during the outage. This is not lock-loss or takeover qualification.
"""
import json
import time
from nfs_binding import binding_for, provision


def qualify_receipt_shutdown(run, execute, spawn, restore, server, output, client, peer,
                            start, stop, cases):
    def observe(command, check=True, target=None):
        return execute(command, "1000:1000", check=check, target=target or client)

    def state(pid):
        result = observe(f"cat /proc/{pid}/stat", check=False)
        if result.returncode:
            assert observe(f"test ! -d /proc/{pid}", check=False).returncode == 0
            return "gone"
        return result.stdout.rsplit(")", 1)[1].split()[0]

    for profile in ("debug", "release"):
        label = "receipt-shutdown-"+profile
        source = "/tmp/nfs/"+label+"/source"
        base = "/tmp/local/ownership-"+label
        observe(f"umask 077; mkdir -p {source}/.file-mover {source}/current; printf 'unsubmitted recording' >{source}/current/data")
        provision(run, execute, output, client, source, binding_for(label, True))
        owner = start(client, label, profile, source, 19885, binding_label=label, initialize=True)
        assert owner["ready"]
        stop(owner)
        receipt = source+"/.file-mover/source-enrollment.json"
        before = observe(f"stat -c '%d:%i:%u:%a:%s' {receipt}; sha256sum {receipt}").stdout
        database = observe("sha256sum "+base+"/state/jobs.sqlite").stdout
        rendezvous = base+"/pause"
        marker = base+"/restart.pid"
        observe(f"umask 077; mkdir {rendezvous}")
        name = label+"-blocked"
        process = spawn(f"echo $$ >{marker}; exec env FILE_MOVER_QUALIFICATION_PAUSE=enrollment_read "
                        f"FILE_MOVER_QUALIFICATION_RENDEZVOUS={rendezvous} "
                        f"/tmp/ownership-qualification-{profile} {base}/config.json", name, target=client)
        parent = child = health = None
        result = {"scenario_id": "SC-069", "profile": profile, "probe_completed": False, "jobs_submitted": 0}
        cases.append(result)
        try:
            for _ in range(50):
                marked = observe("cat "+marker, check=False)
                if marked.returncode == 0 and marked.stdout.strip().isdigit():
                    parent = marked.stdout.strip()
                    break
                assert process.poll() is None
                time.sleep(0.1)
            assert parent is not None, "receipt startup PID unavailable"
            for _ in range(100):
                ready = observe("cat "+rendezvous+"/ready", check=False)
                if ready.returncode == 0 and ready.stdout.endswith("\n"):
                    child, point = ready.stdout.split()
                    assert child.isdigit() and point == "enrollment_read"
                    break
                assert process.poll() is None
                time.sleep(0.1)
            else:
                raise RuntimeError("receipt reader did not reach rendezvous")
            command = observe(f"tr '\\000' ' ' </proc/{child}/cmdline").stdout
            assert "--internal-enrollment-worker" in command

            def children():
                return sorted(set(observe(f"for task in /proc/{parent}/task/*/children; do cat $task; done").stdout.split()))

            assert children() == [child]
            run(["exec", server, "rpc.nfsd", "0"])
            observe(": >"+rendezvous+"/go")
            for _ in range(50):
                if state(child) == "D":
                    break
                assert process.poll() is None
                time.sleep(0.1)
            assert state(child) == "D", "receipt payload read was not kernel-blocked"
            assert observe("test ! -e "+rendezvous+"/read-completed", check=False).returncode == 0
            result["reader_wait_channel"] = observe(f"cat /proc/{child}/wchan", check=False).stdout.strip()
            result["reader_kernel_blocked"] = True
            result["read_incomplete_before_metadata"] = True
            health = spawn("exec /bin/bash -c 'exec 3<>/dev/tcp/127.0.0.1/19885; "
                           "printf \"GET /healthz HTTP/1.1\\r\\nHost: localhost\\r\\nConnection: close\\r\\n\\r\\n\" >&3; cat <&3'",
                           label+"-health", target=client)
            time.sleep(1)
            assert health.poll() is None and children() == [child]
            observe("kill -TERM "+parent)
            deadline = time.monotonic()+5
            while process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.1)
            early = process.poll() is not None
            result["service_exit_before_restore"] = early
            if early:
                assert process.returncode == 0 and state(child) in {"gone", "Z"}
            else:
                assert children() in ([child], []), "blocked shutdown started a replacement child"
                result["shutdown_limitation"] = "Child exit was not confirmed within five seconds; NFS restoration was required."
            result["child_exit_before_restore"] = state(child) in {"gone", "Z"}
            assert "Ready on" not in (output/(name+".log")).read_text()
            restore()
            assert process.wait(timeout=45) == 0
            assert state(child) in {"gone", "Z"}
            health.wait(timeout=15)
            assert "HTTP/1.1 200" not in (output/(label+"-health.log")).read_text()
            assert "Ready on" not in (output/(name+".log")).read_text()
            assert observe(f"stat -c '%d:%i:%u:%a:%s' {receipt}; sha256sum {receipt}").stdout == before
            assert observe("sha256sum "+base+"/state/jobs.sqlite").stdout == database
            assert observe("cat "+source+"/current/data").stdout == "unsubmitted recording"
            assert observe(f"exec 9<>{source}/.file-mover/coordinator.lock; flock -xn 9", target=peer).returncode == 0
            restarted = start(client, label+"-recovery", profile, source, 19885,
                              state_label=label, binding_label=label)
            assert restarted["ready"]
            stop(restarted)
            result.update({"probe_completed": True, "no_readiness_before_shutdown": True,
                           "same_original_state_restarted": True, "receipt_database_input_unchanged": True,
                           "peer_lock_available_after_confirmed_exit_and_restore": True})
            (output/(label+"-result.json")).write_text(json.dumps(result, indent=2)+"\n")
            print(f"NFS receipt startup/shutdown {profile}: PASS (exit before restoration={early})", flush=True)
        finally:
            restore()
            if parent and process.poll() is None:
                observe("kill -TERM "+parent, check=False)
            process.wait(timeout=45)
            if child and state(child) not in {"gone", "Z"}:
                observe("kill -KILL "+child, check=False)
                for _ in range(100):
                    if state(child) in {"gone", "Z"}:
                        break
                    time.sleep(0.1)
                assert state(child) in {"gone", "Z"}, "receipt child cleanup exit unconfirmed"
            if health is not None:
                health.wait(timeout=15)
