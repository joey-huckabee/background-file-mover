"""Selected actual hard-NFS coordinator-death checks in a disposable fixture."""
import hashlib
import json
import time
import traceback


def run_death(Case, run, execute, spawn, restore, server, output, client, results, scope="claim-copy-verify", endpoints=None):
    def status(case, expected):
        began = time.monotonic()
        reply = execute(f"LD_BIND_NOW=1 {case.binary} --status {case.config_path}", "1000:1000", check=False)
        elapsed = time.monotonic() - began
        assert elapsed < 5 and reply.returncode in (0, 2), reply.stderr
        value = json.loads(reply.stdout)
        if expected is not None:
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

    assert scope in {"claim-copy-verify", "bootstrap-source-read", "bootstrap-existing-state", "publication-manifest", "both-nfs", "separate-exports", "independent-endpoints", "source-mid-copy"}
    independent = scope in {"independent-endpoints", "source-mid-copy"}
    assert not independent or endpoints is not None
    both_nfs = scope in {"both-nfs", "separate-exports", "independent-endpoints", "source-mid-copy"}
    points = {"claim-copy-verify": ("claim_apply", "copy_chunk", "verify_read"),
              "bootstrap-source-read": ("bootstrap", "source_read"),
              "bootstrap-existing-state": ("bootstrap_enrolled", "bootstrap_populated"),
              "publication-manifest": ("publish", "file_link", "manifest_link"),
              "both-nfs": ("claim_apply", "copy_chunk", "verify_read", "publish", "file_link", "manifest_link"),
              "separate-exports": ("claim_apply", "copy_chunk", "verify_read", "publish", "file_link", "manifest_link"),
              "independent-endpoints": ("claim_apply", "source_read", "copy_chunk", "verify_read", "publish", "file_link", "manifest_link"),
              "source-mid-copy": ("source_copy",)}[scope]
    publication_points = {"publish", "file_link", "manifest_link"}
    bootstrap_points = {"bootstrap", "bootstrap_enrolled", "bootstrap_populated"}
    cases = [(profile, point, phase, 0) for profile in ("debug", "release")
             for point in points
             for phase in ("blocked", "terminating")]
    closed_profiles = set()
    for profile, point, phase, repetition in cases:
        case = None
        result = {"profile": profile, "point": point, "death_phase": phase, "repetition": repetition, "passed": False}
        try:
            case = Case(profile, point, shutdown=True, shutdown_wait=2, suffix="-death-" + phase + (f"-repeat-{repetition}" if repetition else ""), both_nfs=both_nfs, separate_exports=scope in {"separate-exports", "independent-endpoints", "source-mid-copy"}, independent_endpoints=independent)
            case.result.update(result)
            result = case.result
            result["scenario_id"] = "SC-092"
            failed_endpoint = "source" if point in {"claim_apply", "source_read", "source_copy"} else "destination"
            if independent:
                result["failed_endpoint"] = failed_endpoint
            if scope == "bootstrap-existing-state":
                from nfs_bootstrap_state import prepare, local_evidence, source_evidence, receipt_evidence, partial_evidence
                prepare(case, execute, status)
            if point in bootstrap_points:
                # No pause hook: launch into an actual unavailable hard mount.
                run(["exec", server, "rpc.nfsd", "0"])
                case.launch(False)
                for _ in range(12):
                    initial = status(case, None)
                    if initial["snapshot"]["phase"] == "Starting" and len(initial["snapshot"]["workers"]) == 1:
                        case.worker = str(initial["snapshot"]["workers"][0])
                        break
                    assert case.service.poll() is None
                    time.sleep(0.1)
                else:
                    raise AssertionError("bootstrap child not observed through local control")
                result["startup_status"] = initial
                command = execute(f"tr '\\000' ' ' </proc/{case.worker}/cmdline", "1000:1000").stdout
                assert case.binary in command and "--internal-bootstrap-worker" in command
                result["paused_worker"] = {"pid": case.worker, "command": command, "fixture_pause": False}
            else:
                case.start(True)
            coordinator = case.service_pid()
            result["coordinator_pid"] = coordinator
            epoch_path = case.base + "/state/workers.json"
            epoch = json.loads(execute(f"cat {epoch_path}", "1000:1000").stdout)
            assert epoch["version"] == 1 and epoch["group"] == int(coordinator)
            assert execute(f"stat -c '%u:%a:%h' {epoch_path}", "1000:1000").stdout.strip() == "1000:600:1"
            assert execute(f"test ! -e {case.base}/state/workers.next", "1000:1000", check=False).returncode == 0
            result["worker_epoch_before_death"] = epoch
            posted = None
            if point in bootstrap_points:
                # Local-only observations; never stat the unavailable source.
                time.sleep(3)
                worker = case.worker
                assert case.state(worker) == "D" and case.children() == [worker]
                initial = status(case, "Starting")
                assert initial["snapshot"]["workers"] == [int(worker)]
                connected = case.base + "/health-connected"
                health = case.request("GET", "/healthz", asynchronous=True, connected_marker=connected)
                for _ in range(5):
                    if execute(f"test -f {connected}", "1000:1000", check=False).returncode == 0:
                        break
                    time.sleep(0.1)
                else:
                    raise AssertionError("bootstrap health request was not sent")
                result["bootstrap_health_request_sent"] = True
                assert health[0].poll() is None and not health[1].read_text()
                result["bootstrap_health_pending"] = True
                if scope == "bootstrap-existing-state":
                    observed = local_evidence(case, execute)
                    assert observed == result["bootstrap_local_before"], "existing local state changed during blocked bootstrap"
                    result["bootstrap_local_while_blocked"] = observed
                else:
                    execute(f"test ! -e {case.base}/state/jobs.sqlite && test ! -e {case.base}/state/jobs.sqlite-wal && test ! -e {case.base}/state/jobs.sqlite-shm", "1000:1000")
                    result["database_absent_before_death"] = True
                result["blocked_worker"] = {"pid": worker, "state": "D", "pause_released": False,
                    "nfs_server_stopped": True, "status": initial}
            else:
                posted = case.request("POST", "/api/v2/jobs", case.body, asynchronous=point == "claim_apply")
                if point != "claim_apply":
                    assert posted[0] == 202 and posted[1]["source_paths_released"]
                    execute(f"printf 'next recording' >{case.source}/current/nested/data.bin", "1000:1000")
                case.await_pause()
                result["status_before_outage"] = case.request("GET", "/api/v2/jobs/1")[1]
                assert result["status_before_outage"]["state"] == ("Accepted" if point == "claim_apply" else "Claimed")
                if point in {"copy_chunk", "source_read", "source_copy"}:
                    size = execute(f"stat -c %s {case.destination}/1/.staging/1.part", "1000:1000").stdout.strip()
                    assert size == ("0" if point == "source_read" else "1048576")
                    result["partial_bytes_before_outage"] = int(size)
                if both_nfs:
                    from nfs_both import before as both_before, recovered as both_recovered
                    both_before(case, execute)
                if point in publication_points:
                    from nfs_publication import before, after_exit, recovered as publication_recovered
                    before(case, execute)
                assert case.service_pid() == coordinator
                worker = case.worker
                if independent:
                    result["endpoint_outage"] = endpoints.stop(failed_endpoint)
                else:
                    run(["exec", server, "rpc.nfsd", "0"])
                execute(f"umask 077; : >{case.rendezvous}/go", "1000:1000")
                time.sleep(3)
                assert case.state(worker) == "D" and case.children() == [worker]
                if independent:
                    result["healthy_endpoint_while_worker_blocked"] = endpoints.during(failed_endpoint)
                    assert case.state(worker) == "D"
                if point in {"verify_read", "source_read", "source_copy"}:
                    assert execute(f"test ! -e {case.rendezvous}/read-completed", "1000:1000", check=False).returncode == 0
                    result["read_not_completed_during_outage"] = True
                if point == "source_copy":
                    syscall = execute(f"cat /proc/{worker}/syscall").stdout.strip()
                    # x86_64 read(2), with the descriptor still naming claimed source.
                    fields = syscall.split()
                    assert len(fields) == 9 and fields[0] == "0", syscall
                    descriptor = int(fields[1], 16)
                    target = execute(f"readlink /proc/{worker}/fd/{descriptor}", "1000:1000").stdout.strip()
                    assert target == case.source + "/.file-mover/1-0/data", target
                    assert int(fields[3], 16) == 1048576, syscall
                    worker_status = execute(f"cat /proc/{worker}/status", "1000:1000").stdout
                    security = {k: v.strip() for line in worker_status.splitlines() if ":" in line
                                for k, v in [line.split(":", 1)] if k in {"Uid", "CapInh", "CapPrm", "CapEff", "NoNewPrivs"}}
                    assert security["Uid"].split() == ["1000"] * 4 and security["NoNewPrivs"] == "1"
                    assert all(int(security[k], 16) == 0 for k in ("CapInh", "CapPrm", "CapEff"))
                    result["blocked_source_read_syscall"] = {"raw": syscall, "fd": descriptor, "target": target,
                                                           "worker_security": security}
                    assert case.state(worker) == "D"
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
                        result["kernel_closed_guard"] = True
                        snapshot["worker_status"] = execute(f"cat /proc/{worker}/status", "1000:1000").stdout
                    snapshot["local_status"] = status(case, None)
                    snapshot["logical_ownership_retained"] = (snapshot["local_status"]["snapshot"]["phase"] == "OwnerUnavailable"
                        and snapshot["local_status"]["exit_code"] == 2)
                    if not snapshot["logical_ownership_retained"]:
                        result["ownership_lost"] = True
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
                    assert case.state(worker) == "D"
                    assert status(case, "OwnerUnavailable")["exit_code"] == 2
                    result["outcome"] = "blocked_orphan_retains_ownership" if phase == "blocked" else "terminating_orphan_retains_ownership"
                if independent:
                    assert case.state(worker) == "D"
                    result["healthy_endpoint_while_orphan_blocked"] = endpoints.during(failed_endpoint)
                    assert case.state(worker) == "D"
            if point == "source_copy":
                from nfs_both import payload
                result["partial_while_source_unavailable"] = payload(case, execute, case.destination + "/1/.staging/1.part")
                assert result["partial_while_source_unavailable"] == result["copy_partial_before"]
                assert execute(f"test ! -e {case.rendezvous}/read-completed", "1000:1000", check=False).returncode == 0
                result["read_not_completed_before_restore"] = True
            assert json.loads(execute(f"cat {epoch_path}", "1000:1000").stdout) == epoch
            result["epoch_preserved_until_old_exit"] = True
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
            if point in bootstrap_points:
                health[0].wait(timeout=10)
                assert "200 OK" not in health[1].read_text()
                if scope == "bootstrap-existing-state":
                    result["bootstrap_local_after_old_exit"] = local_evidence(case, execute)
                    result["bootstrap_source_after_old_exit"] = source_evidence(case, execute)
                    assert result["bootstrap_local_after_old_exit"] == result["bootstrap_local_before"], "database/WAL/staging changed before recovery"
                    assert result["bootstrap_source_after_old_exit"] == result["bootstrap_source_before"], "receipt/source changed before recovery"
                    result["existing_state_preserved_before_recovery"] = True
                    result["re_enrollment_performed"] = False
                else:
                    execute(f"test ! -e {case.base}/state/jobs.sqlite && test ! -e {case.base}/state/jobs.sqlite-wal && test ! -e {case.base}/state/jobs.sqlite-shm", "1000:1000")
                    result["database_absent_after_old_exit"] = True
                    result["source_hash_before_first_submission"] = execute(f"sha256sum {case.source}/current/nested/data.bin", "1000:1000").stdout.split()[0]
                    assert result["source_hash_before_first_submission"] == hashlib.sha256(bytes(2 * 1048576) + b"0123456789abcdefg").hexdigest()
                    # First enrollment is explicit, after the old worker is gone.
                    execute(f"{case.binary} --initialize-source {case.config_path}", "1000:1000")
                    result["explicit_initialization_after_old_exit"] = True
            if point in publication_points:
                after_exit(case, execute)
            recovered = case.recover()
            replacement_epoch = json.loads(execute(f"cat {epoch_path}", "1000:1000").stdout)
            assert replacement_epoch["group"] == int(case.service_pid()) and replacement_epoch["group"] != epoch["group"]
            assert all(replacement_epoch[k] == epoch[k] for k in ("version", "boot", "namespace", "guard"))
            result["worker_epoch_after_recovery"] = replacement_epoch
            assert recovered["details"]["source_cleanup_enabled"] is False
            if point in {"claim_apply", "bootstrap", "bootstrap_enrolled"}:
                execute(f"printf 'next recording' >{case.source}/current/nested/data.bin", "1000:1000")
            if point in {"copy_chunk", "source_read", "source_copy", "bootstrap_populated"}:
                assert recovered["details"]["files"][0]["attempt"] == 2
                assert execute(f"test -f {case.destination}/1/.staging/1.part", "1000:1000", check=False).returncode == 0
                result["old_partial_preserved"] = True
            if point in {"verify_read", "bootstrap", "bootstrap_enrolled"}:
                assert recovered["details"]["files"][0]["attempt"] == 1
            assert case.request("POST", "/api/v2/jobs", case.body)[0] == 202
            assert execute(f"cat {case.source}/current/nested/data.bin", "1000:1000").stdout == "next recording"
            case.verify()
            if point in publication_points:
                publication_recovered(case, execute, recovered)
            if both_nfs:
                both_recovered(case, execute)
            if scope == "bootstrap-existing-state":
                result["database_identity_after_recovery"] = execute(f"stat -c '%d:%i' {case.base}/state/jobs.sqlite", "1000:1000").stdout
                result["enrollment_receipt_after_recovery"] = receipt_evidence(case, execute)
                assert result["database_identity_after_recovery"] == result["database_identity_before"]
                assert result["enrollment_receipt_after_recovery"] == result["enrollment_receipt_before"]
                if point == "bootstrap_populated":
                    result["partial_after_recovery"] = partial_evidence(case, execute)
                    assert result["partial_after_recovery"] == result["seed_partial"], "old partial bytes/inode/size changed"
                    result["populated_job_replayed"] = True
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
            print(f"NFS coordinator death {profile}/{point}/{phase}/repeat-{repetition}: {'PASS' if result['passed'] else 'BLOCKED'} ({result.get('outcome', result.get('error', 'unknown'))})", flush=True)
        if not result["passed"] and (not result.get("ownership_lost") or result.get("error") or result.get("cleanup_error")):
            return {"passed": False}
        if result.get("kernel_closed_guard") and result["passed"]:
            closed_profiles.add(profile)
        if scope == "claim-copy-verify" and point == "verify_read" and phase == "terminating" and profile not in closed_profiles and repetition < 3:
            cases.append((profile, point, phase, repetition + 1))
    terminating_profiles = {c["profile"] for c in results
                            if c["outcome"] == "terminating_orphan_retains_ownership"}
    closed_profiles = {c["profile"] for c in results if c.get("kernel_closed_guard")}
    if scope in {"bootstrap-source-read", "bootstrap-existing-state", "publication-manifest", "both-nfs", "separate-exports", "independent-endpoints", "source-mid-copy"}:
        passed = len(results) == len(points) * 4 and all(c["passed"] for c in results) and {
            (c["profile"], c["point"]) for c in results
            if c["outcome"] == "blocked_orphan_retains_ownership"
        } == {(p, point) for p in ("debug", "release") for point in points}
    else:
        passed = (12 <= len(results) <= 18 and all(c["passed"] for c in results)
                  and terminating_profiles == {"debug", "release"}
                  and closed_profiles == {"debug", "release"})
    return {"passed": passed, "scope": scope,
            "raw_lock_closure_required": scope == "claim-copy-verify",
            "core_cases": sum(c["repetition"] == 0 for c in results),
            "verification_repetitions": sum(c["repetition"] > 0 for c in results),
            "required_closed_guard_profiles": sorted(closed_profiles),
            "kernel_closed_guard_cases": sum(c.get("kernel_closed_guard", False) for c in results),
            "ownership_loss_cases": sum(c.get("ownership_lost", False) for c in results),
            "blocked_orphan_cases": sum(c["outcome"] == "blocked_orphan_retains_ownership" for c in results),
            "terminating_orphan_cases": sum(c["outcome"] == "terminating_orphan_retains_ownership" for c in results),
            "prompt_exit_cases": sum(c["outcome"] == "prompt_exit_before_coordinator_kill" for c in results)}
