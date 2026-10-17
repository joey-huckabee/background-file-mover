"""Selected actual hard-NFS coordinator-death checks in a disposable fixture."""
import json
import time
import traceback


def run_death(Case, run, execute, spawn, restore, server, output, client, results):
    def status(case, expected):
        began = time.monotonic()
        reply = execute(f"LD_BIND_NOW=1 {case.binary} --status {case.config_path}", "1000:1000", check=False)
        elapsed = time.monotonic() - began
        assert elapsed < 5 and reply.returncode in (0, 2), reply.stderr
        value = json.loads(reply.stdout)
        assert value["phase"] == expected, value
        return {"exit_code": reply.returncode, "elapsed_seconds": round(elapsed, 3), "snapshot": value}

    def probe(case):
        # Independent, nonblocking local flock only; never starts a replacement
        # or touches SQLite/NFS if a terminating child's guard was released early.
        path = case.base + "/state/instance.lock"
        before = execute(f"stat -c '%d:%i:%s:%u:%a' {path}", "1000:1000").stdout.strip()
        reply = execute(f"test -f {path}; flock -n -E 73 {path} true", "1000:1000", check=False)
        assert reply.returncode in (0, 73), reply.stderr
        after = execute(f"stat -c '%d:%i:%s:%u:%a' {path}", "1000:1000").stdout.strip()
        assert before == after
        return {"contended": reply.returncode == 73, "exit_code": reply.returncode, "identity": before}

    def competitors(case):
        rows = []
        config = dict(case.config, bind="127.0.0.1:0")
        path = output / (case.label + "-competitor.json")
        path.write_text(json.dumps(config), encoding="utf-8")
        remote = case.base + "/competitor.json"
        run(["cp", str(path), client + ":" + remote])
        for index, command in enumerate(("", "--initialize-source ", "--transfer-one ")):
            name = case.label + f"-competitor-{index}"
            tail = " 1" if command.startswith("--transfer-one") else ""
            began = time.monotonic()
            process = spawn(f"exec {case.binary} {command}{remote}{tail}", name)
            case.processes.append(process)
            assert process.wait(timeout=6) != 0
            diagnostic = (output / (name + ".log")).read_text()
            assert "local instance or surviving worker already owns state" in diagnostic, diagnostic
            rows.append({"command": command.strip() or "service", "elapsed_seconds": round(time.monotonic() - began, 3),
                         "refused": True, "diagnostic": diagnostic.strip()})
        return rows

    for profile in ("debug", "release"):
        for point in ("claim_apply", "copy_chunk", "verify_read"):
            for phase in ("blocked", "terminating"):
                case = None
                result = {"profile": profile, "point": point, "death_phase": phase, "passed": False}
                try:
                    case = Case(profile, point, shutdown=True, shutdown_wait=2, suffix="-death-" + phase)
                    case.result.update(result)
                    result = case.result
                    result["scenario_id"] = "SC-092"
                    case.start(True)
                    posted = case.request("POST", "/api/v2/jobs", case.body, asynchronous=point == "claim_apply")
                    if point != "claim_apply":
                        assert posted[0] == 202 and posted[1]["source_paths_released"]
                        execute(f"printf 'next recording' >{case.source}/current/nested/data.bin", "1000:1000")
                    case.await_pause()
                    result["status_before_outage"] = case.request("GET", "/api/v2/jobs/1")[1]
                    assert result["status_before_outage"]["state"] == ("Accepted" if point == "claim_apply" else "Claimed")
                    if point == "copy_chunk":
                        assert execute(f"stat -c %s {case.destination}/1/.staging/1.part", "1000:1000").stdout.strip() == "1048576"
                    coordinator = case.service_pid()
                    result["coordinator_pid"] = coordinator
                    worker = case.worker
                    run(["exec", server, "rpc.nfsd", "0"])
                    execute(f"umask 077; : >{case.rendezvous}/go", "1000:1000")
                    time.sleep(3)
                    assert case.state(worker) == "D" and case.children() == [worker]
                    if point == "verify_read":
                        assert execute(f"test ! -e {case.rendezvous}/read-completed", "1000:1000", check=False).returncode == 0
                    result["blocked_worker"] = {"pid": worker, "state": "D", "pause_released": True,
                        "nfs_server_stopped": True, "status": status(case, "Running")}
                    result["guard_before_death"] = probe(case)
                    assert result["guard_before_death"]["contended"]
                    if phase == "terminating":
                        name = case.label + "-stop"
                        process = spawn(f"exec {case.binary} --stop {case.config_path}", name)
                        case.processes.append(process)
                        began = time.monotonic()
                        process.wait(timeout=10)
                        lines = [line for line in (output / (name + ".log")).read_text().splitlines() if line.startswith("{")]
                        assert len(lines) == 1
                        reply = json.loads(lines[0])
                        result["stop"] = {"exit_code": process.returncode, "snapshot": reply,
                                          "elapsed_seconds": round(time.monotonic() - began, 3)}
                        assert reply["shutdown_wait_seconds"] == 2
                        if reply["phase"] == "Stopped":
                            assert process.returncode == 0 and case.service.wait(timeout=5) == 0
                            assert case.state(worker) in ("", "Z")
                            result["outcome"] = "prompt_exit_before_coordinator_kill"
                        else:
                            assert reply["phase"] == "ShutdownIncomplete" and process.returncode == 2
                            assert reply["shutdown_remaining_ms"] == 0 and case.service.poll() is None
                            assert case.state(worker) == "D"
                            result["stop_pending_worker_status"] = execute(f"cat /proc/{worker}/status", "1000:1000").stdout
                    if "outcome" not in result:
                        # Kill only the coordinator PID, never its process group.
                        case.signal(coordinator, "KILL")
                        result["coordinator_exit_code"] = case.service.wait(timeout=10)
                        assert result["coordinator_exit_code"] != 0 and case.state(coordinator) in ("", "Z")
                        samples = []
                        result["orphan_samples"] = samples
                        for index in range(3):
                            state = case.state(worker)
                            snapshot = {"worker_state": state, "guard": probe(case)}
                            snapshot["worker_state_after_probe"] = case.state(worker)
                            samples.append(snapshot)
                            assert state == snapshot["worker_state_after_probe"] == "D", "worker did not remain kernel-blocked across guard observation"
                            held = snapshot["guard"]["contended"]
                            if not held:
                                result["ownership_lost"] = True
                                snapshot["worker_status"] = execute(f"cat /proc/{worker}/status", "1000:1000").stdout
                            snapshot["local_status"] = status(case, "OwnerUnavailable" if held else "NoActiveOwner")
                            assert snapshot["local_status"]["exit_code"] == (2 if held else 0)
                            snapshot["worker_state_after_status"] = case.state(worker)
                            assert snapshot["worker_state_after_status"] == "D"
                            if index < 2:
                                time.sleep(1)
                        if result.get("ownership_lost"):
                            # Preserve evidence of the defect, never dispatch a
                            # conflicting writer just to demonstrate it.
                            result["competitors_skipped_for_safety"] = True
                            result["outcome"] = "live_orphan_without_local_ownership"
                            result["failure"] = "kernel-blocked worker outlives local guard; controller reports NoActiveOwner"
                        else:
                            result["competitors_after_death"] = competitors(case)
                            assert case.state(worker) == "D" and probe(case)["contended"]
                            result["outcome"] = "blocked_orphan_retains_ownership" if phase == "blocked" else "terminating_orphan_retains_ownership"
                    # A free local guard never authorizes restart during outage.
                    restore()
                    result["worker_exit_after_restore"] = case.await_exit(worker)
                    case.worker = None  # Do not signal stale/reused PIDs in cleanup.
                    if point == "claim_apply":
                        posted[0].wait(timeout=15)
                        text = posted[1].read_text()
                        if text.startswith("HTTP/"):
                            reply = case.parse(text)
                            assert reply[0] != 202 and not reply[1]["source_paths_released"]
                            result["interrupted_handoff"] = reply
                        else:
                            result["interrupted_handoff_transport"] = text
                    result["guard_after_exit"] = probe(case)
                    assert not result["guard_after_exit"]["contended"]
                    result["local_status_after_exit"] = status(case, "NoActiveOwner")
                    recovered = case.recover()
                    assert recovered["details"]["source_cleanup_enabled"] is False
                    if point == "claim_apply":
                        execute(f"printf 'next recording' >{case.source}/current/nested/data.bin", "1000:1000")
                    if point == "copy_chunk":
                        assert recovered["details"]["files"][0]["attempt"] == 2
                        assert execute(f"test -f {case.destination}/1/.staging/1.part", "1000:1000", check=False).returncode == 0
                        result["old_partial_preserved"] = True
                    if point == "verify_read":
                        assert recovered["details"]["files"][0]["attempt"] == 1
                    assert case.request("POST", "/api/v2/jobs", case.body)[0] == 202
                    assert execute(f"cat {case.source}/current/nested/data.bin", "1000:1000").stdout == "next recording"
                    case.verify()
                    result.update({"original_state_recovery": True, "producer_reused_path_preserved": True,
                                   "restart_only_after_restore_and_exit": True, "passed": not result.get("ownership_lost", False)})
                except Exception as error:
                    result.update({"error": f"{type(error).__name__}: {error}", "traceback": traceback.format_exc()})
                finally:
                    if case:
                        try:
                            case.cleanup()
                        except Exception as error:
                            result["cleanup_error"] = str(error)
                            result["passed"] = False
                    results.append(result)
                    print(f"NFS coordinator death {profile}/{point}/{phase}: {'PASS' if result['passed'] else 'BLOCKED'} ({result.get('outcome', result.get('error', 'unknown'))})", flush=True)
                if not result["passed"] and (not result.get("ownership_lost") or result.get("error") or result.get("cleanup_error")):
                    return {"passed": False}
    terminating_profiles = {c["profile"] for c in results
                            if c["outcome"] == "terminating_orphan_retains_ownership"}
    return {"passed": len(results) == 12 and all(c["passed"] for c in results)
                      and terminating_profiles == {"debug", "release"},
            "ownership_loss_cases": sum(c.get("ownership_lost", False) for c in results),
            "blocked_orphan_cases": sum(c["outcome"] == "blocked_orphan_retains_ownership" for c in results),
            "terminating_orphan_cases": sum(c["outcome"] == "terminating_orphan_retains_ownership" for c in results),
            "prompt_exit_cases": sum(c["outcome"] == "prompt_exit_before_coordinator_kill" for c in results)}
