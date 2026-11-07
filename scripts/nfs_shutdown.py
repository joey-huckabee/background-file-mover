"""Actual hard-NFS shutdown observations; never synthesize a kernel-held child."""
import json
import time
import traceback


def run_shutdown(Case, run, execute, spawn, restore, server, output, client, results):
    def cli(case, command, config=None):
        started = time.monotonic()
        response = execute(f"LD_BIND_NOW=1 {case.binary} {command} {config or case.config_path}", "1000:1000", check=False)
        elapsed = time.monotonic() - started
        assert elapsed < 5, "local control touched unavailable NFS or exceeded fixture bound"
        assert response.returncode in (0, 2), response.stderr
        return {"exit_code": response.returncode, "elapsed_seconds": round(elapsed, 3),
                "snapshot": json.loads(response.stdout)}

    def asynchronous(case, command, config, name):
        process = spawn(f"exec {case.binary} {command} {config}", name)
        case.processes.append(process)
        return process, output / (name + ".log")

    def control_result(process, path):
        lines = [line for line in path.read_text().splitlines() if line.startswith("{")]
        assert len(lines) == 1, path.read_text()
        return {"exit_code": process.returncode, "snapshot": json.loads(lines[0])}

    def competitors(case, config, stage):
        rows = []
        for index, command in enumerate(("", "--initialize-source ", "--transfer-one ")):
            tail = " 1" if command.startswith("--transfer-one") else ""
            name = case.label + f"-competitor-{stage}-{index}"
            began = time.monotonic()
            process = spawn(f"exec {case.binary} {command}{config}{tail}", name)
            case.processes.append(process)
            assert process.wait(timeout=6) != 0
            diagnostic = (output / (name + ".log")).read_text()
            assert "local instance or surviving worker already owns state" in diagnostic, diagnostic
            rows.append({"command": command.strip() or "service", "elapsed_seconds": round(time.monotonic() - began, 3),
                         "refused": True, "diagnostic": diagnostic.strip()})
        return rows

    for profile in ("debug", "release"):
        for point in ("claim_apply", "copy_chunk", "verify_read"):
            for wait in (2, None):
                case = None
                try:
                    case = Case(profile, point, shutdown=True, shutdown_wait=wait)
                    budget = 60 if wait is None else wait
                    result = case.result
                    result.update({"scenario_id": "SC-093", "shutdown_wait_seconds": budget,
                                   "default_omitted": wait is None, "samples": []})
                    case.start(True)
                    posted = case.request("POST", "/api/v2/jobs", case.body, asynchronous=point == "claim_apply")
                    if point != "claim_apply":
                        assert posted[0] == 202 and posted[1]["source_paths_released"]
                        execute(f"printf 'next recording' >{case.source}/current/nested/data.bin", "1000:1000")
                    case.await_pause()
                    before = case.request("GET", "/api/v2/jobs/1")[1]
                    result["status_before_outage"] = before
                    assert before["state"] == ("Accepted" if point == "claim_apply" else "Claimed")
                    if point == "copy_chunk":
                        assert execute(f"stat -c %s {case.destination}/1/.staging/1.part", "1000:1000").stdout.strip() == "1048576"
                    competing = dict(case.config, bind="127.0.0.1:0", shutdown_wait_seconds=3600)
                    local = output / (case.label + "-next-config.json")
                    local.write_text(json.dumps(competing), encoding="utf-8")
                    next_config = case.base + "/next-config.json"
                    run(["cp", str(local), client + ":" + next_config])
                    run(["exec", server, "rpc.nfsd", "0"])
                    execute(f"umask 077; : >{case.rendezvous}/go", "1000:1000")
                    time.sleep(3)
                    assert case.state(case.worker) == "D", "no actual kernel-blocked worker observed"
                    assert case.children() == [case.worker]
                    if point == "verify_read":
                        assert execute(f"test ! -e {case.rendezvous}/read-completed", "1000:1000", check=False).returncode == 0
                    result["blocked_worker"] = {"pid": case.worker, "state": "D",
                        "wait_channel": execute(f"cat /proc/{case.worker}/wchan", "1000:1000", check=False).stdout.strip(),
                        "pause_released": True, "nfs_server_stopped": True}
                    initial = cli(case, "--status")
                    assert initial["snapshot"]["phase"] == "Running"
                    assert initial["snapshot"]["shutdown_wait_seconds"] == budget
                    identity = initial["snapshot"]["instance_id"]
                    result["running_local_status"] = initial
                    result["competitors_while_blocked"] = competitors(case, next_config, "blocked")
                    began = time.monotonic()
                    stop, stop_path = asynchronous(case, "--stop", case.config_path, case.label + "-stop")
                    repeated = None
                    previous_remaining = None
                    while stop.poll() is None:
                        assert time.monotonic() - began < budget + 8, "stop controller exceeded configured bound"
                        observation = cli(case, "--status", next_config)
                        snapshot = observation["snapshot"]
                        observation["since_stop_seconds"] = round(time.monotonic() - began, 3)
                        observation["worker_state"] = case.state(case.worker)
                        result["samples"].append(observation)
                        if snapshot["phase"] in ("Draining", "ShutdownIncomplete"):
                            assert snapshot["instance_id"] == identity
                            assert snapshot["shutdown_wait_seconds"] == budget, "next-start config extended live budget"
                            remaining = snapshot["shutdown_remaining_ms"]
                            if previous_remaining is not None:
                                assert remaining <= previous_remaining
                            previous_remaining = remaining
                            if observation["worker_state"] == "D":
                                assert snapshot["workers"] == [int(case.worker)]
                            if repeated is None:
                                repeated = asynchronous(case, "--stop", next_config, case.label + "-repeat-stop")
                                case.signal(case.service_pid(), "TERM")
                        elif snapshot["phase"] in ("NoActiveOwner", "OwnerUnavailable"):
                            assert case.state(case.worker) in ("", "Z"), "control unavailable while blocked worker remains"
                        else:
                            assert snapshot["phase"] == "Running", snapshot
                        print(f"NFS shutdown {case.label}: {observation['since_stop_seconds']:.1f}s {snapshot['phase']} worker={observation['worker_state'] or 'gone'}", flush=True)
                        if stop.poll() is None:
                            time.sleep(0.2 if budget == 2 else 5)
                    stop.wait(timeout=5)
                    result["stop"] = control_result(stop, stop_path)
                    result["stop"]["elapsed_seconds"] = round(time.monotonic() - began, 3)
                    assert result["stop"]["elapsed_seconds"] < budget + 8
                    response = result["stop"]["snapshot"]
                    assert response["instance_id"] == identity and response["shutdown_wait_seconds"] == budget
                    if response["phase"] == "ShutdownIncomplete":
                        assert stop.returncode == 2 and case.service.poll() is None
                        assert response["shutdown_remaining_ms"] == 0
                        assert response["message"] == "shutdown incomplete; restart blocked"
                        state = case.state(case.worker)
                        result["outcome"] = "incomplete_worker_retained" if state == "D" else "incomplete_exit_race"
                        result["worker_at_deadline"] = state
                        result["competitors_after_deadline"] = competitors(case, next_config, "expired")
                        expired = cli(case, "--status", next_config)
                        assert expired["exit_code"] == 2 and expired["snapshot"]["phase"] == "ShutdownIncomplete"
                        assert expired["snapshot"]["instance_id"] == identity
                        result["expired_local_status"] = expired
                    else:
                        assert response["phase"] == "Stopped" and stop.returncode == 0
                        assert case.service.wait(timeout=5) == 0
                        assert case.state(case.worker) in ("", "Z")
                        result["outcome"] = "prompt_kernel_assisted_exit"
                    if repeated:
                        repeated[0].wait(timeout=6)
                        result["repeat_stop"] = control_result(*repeated)
                        repeated_snapshot = result["repeat_stop"]["snapshot"]
                        if repeated_snapshot["phase"] in ("NoActiveOwner", "OwnerUnavailable"):
                            assert response["phase"] == "Stopped"
                            result["repeat_stop_after_prompt_exit"] = True
                        else:
                            assert repeated_snapshot["instance_id"] == identity
                            assert repeated_snapshot["shutdown_wait_seconds"] == budget
                    # Guard release/exit never authorizes restart while RPCs are
                    # unavailable. Restore first, then use original-state recovery.
                    restore()
                    assert case.service.wait(timeout=30) == 0
                    result["worker_exit_after_restore"] = case.await_exit(case.worker)
                    case.worker = None  # Never signal a stale/reused PID during cleanup.
                    if point == "claim_apply":
                        posted[0].wait(timeout=15)
                        reply_text = posted[1].read_text()
                        if reply_text.startswith("HTTP/"):
                            reply = case.parse(reply_text)
                            assert reply[0] != 202 and not reply[1]["source_paths_released"]
                            result["interrupted_handoff"] = reply
                        else:
                            result["interrupted_handoff_transport"] = reply_text
                    free = cli(case, "--status")
                    assert free["exit_code"] == 0 and free["snapshot"]["phase"] == "NoActiveOwner"
                    result["local_status_after_exit"] = free
                    recovered = case.recover()
                    assert recovered["details"]["source_cleanup_enabled"] is False
                    if point == "claim_apply":
                        execute(f"printf 'next recording' >{case.source}/current/nested/data.bin", "1000:1000")
                    elif point == "copy_chunk":
                        assert recovered["details"]["files"][0]["attempt"] == 2
                        assert execute(f"test -f {case.destination}/1/.staging/1.part", "1000:1000", check=False).returncode == 0
                        result["old_partial_preserved"] = True
                    else:
                        assert recovered["details"]["files"][0]["attempt"] == 1
                    assert case.request("POST", "/api/v2/jobs", case.body)[0] == 202
                    assert execute(f"cat {case.source}/current/nested/data.bin", "1000:1000").stdout == "next recording"
                    case.verify()
                    result.update({"original_state_recovery": True, "producer_reused_path_preserved": True,
                                   "restart_only_after_restore_and_exit": True, "passed": True})
                except Exception as error:
                    if case:
                        case.result.update({"error": f"{type(error).__name__}: {error}", "traceback": traceback.format_exc()})
                finally:
                    if case:
                        try:
                            case.cleanup()
                        except Exception as error:
                            case.result["cleanup_error"] = str(error)
                            case.result["passed"] = False
                        results.append(case.result)
                        print(f"NFS shutdown {case.label}: {'PASS' if case.result['passed'] else 'BLOCKED'}", flush=True)
                if not results[-1]["passed"]:
                    return {"passed": False}
    return {"passed": len(results) == 12 and all(c["passed"] for c in results),
            "kernel_held_deadline_cases": sum(c["outcome"] == "incomplete_worker_retained" for c in results),
            "prompt_exit_cases": sum(c["outcome"] == "prompt_kernel_assisted_exit" for c in results)}
