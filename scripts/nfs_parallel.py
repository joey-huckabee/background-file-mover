"""Parallel delivery on real NFS (increment 153): concurrent kernel-blocked
delivery workers at shutdown, and delivery throughput by worker count.

Never synthesizes a blocked child: the NFS server is stopped once two
delivery sessions have both staged part of their copy on the NFS destination,
so both are held in the kernel. Uses the shared runtime Case (local state, local source, NFS
destination) with `delivery_concurrency` from the matrix."""
from nfs_fixture_contract import SECOND_RECORDING_ID, THIRD_RECORDING_ID, producer_request
import json
import time
import traceback

LARGE_MIB = 1024
THROUGHPUT_JOBS = 4
THROUGHPUT_MIB = 256


def _workers(case, execute):
    """Live delivery-worker children of the service."""
    rows = []
    for pid in case.children():
        command = execute(f"tr '\\000' ' ' </proc/{pid}/cmdline", "1000:1000", check=False).stdout
        if "--internal-delivery-worker" in command and case.state(pid) not in ("", "Z"):
            rows.append(pid)
    return sorted(rows, key=int)


def _committed(case, job, deadline):
    while time.monotonic() < deadline:
        code, body = case.request("GET", f"/api/v2/jobs/{job}")
        if code == 200 and body["state"] == "Committed":
            return body
        assert body.get("details", {}).get("condition") not in ("ReviewRequired", "Cancelled"), body
        time.sleep(0.5)
    raise RuntimeError(f"job {job} not committed in time")


def _recording(execute, case, name, mib, recording_id):
    execute(f"umask 077; mkdir -p {case.source}/current/{name}; "
            f"dd if=/dev/urandom of={case.source}/current/{name}/data.bin bs=1048576 count={mib} 2>/dev/null; sync",
            "1000:1000")
    digest = execute(f"sha256sum {case.source}/current/{name}/data.bin", "1000:1000").stdout.split()[0]
    body = producer_request(case.source + "/current", {f"{name}/data.bin": mib * 1048576}, recording_id=recording_id)
    return body, digest


def run_parallel_shutdown(Case, run, execute, spawn, restore, server, output, client, results, concurrency):
    """SC-199: two concurrent delivery sessions, each with a partial staged
    copy, blocked by a hard-NFS outage keep the established shutdown rule: ShutdownIncomplete at the original deadline
    with both workers listed, state ownership refused to competitors, restart
    only after NFS restoration and both workers' exit, then both recordings
    delivered intact."""
    assert concurrency >= 2
    for profile in ("debug", "release"):
        case = None
        try:
            case = Case(profile, "copy_chunk", shutdown=True, shutdown_wait=2, suffix="-parallel")
            result = case.result
            result.update({"scenario_id": "SC-199", "shutdown_wait_seconds": 2, "samples": []})
            bodies = [_recording(execute, case, name, LARGE_MIB, rid)
                      for name, rid in (("first", SECOND_RECORDING_ID), ("second", THIRD_RECORDING_ID))]
            case.start(False)
            jobs = []
            for body, _ in bodies:
                code, reply = case.request("POST", "/api/v2/jobs", body)
                assert code == 202 and reply["source_paths_released"], reply
                jobs.append(reply["job_id"])
            # Both deliveries running at once on the NFS destination.
            for _ in range(300):
                workers = _workers(case, execute)
                if len(workers) == 2:
                    break
                time.sleep(0.1)
            assert len(workers) == 2, f"two concurrent delivery workers not observed: {workers}"
            result["concurrent_workers"] = workers
            # Copy-phase evidence: both sessions have staged bytes (and are not
            # finished) before the outage.
            staged = {}
            for _ in range(300):
                staged = {}
                for body, _ in bodies:
                    sizes = execute(f"stat -c %s {case.destination}/{body['recording_id']}/.staging/*.part 2>/dev/null || true",
                                    "1000:1000").stdout.split()
                    staged[body["recording_id"]] = [int(s) for s in sizes]
                if all(any(0 < s < LARGE_MIB * 1048576 for s in v) for v in staged.values()):
                    break
                time.sleep(0.1)
            assert all(any(0 < s < LARGE_MIB * 1048576 for s in v) for v in staged.values()), f"both copies not in progress: {staged}"
            result["staged_bytes_before_outage"] = staged
            run(["exec", server, "rpc.nfsd", "0"])
            time.sleep(3)
            states = {pid: case.state(pid) for pid in workers}
            result["blocked_workers"] = states
            assert all(s == "D" for s in states.values()), f"not both kernel-blocked: {states}"
            status = execute(f"LD_BIND_NOW=1 {case.binary} --status {case.config_path}", "1000:1000", check=False)
            assert status.returncode in (0, 2), status.stderr
            assert json.loads(status.stdout)["phase"] == "Running"
            began = time.monotonic()
            stop = spawn(f"exec {case.binary} --stop {case.config_path}", case.label + "-stop")
            case.processes.append(stop)
            stop.wait(timeout=2 + 8)
            lines = [l for l in (output / (case.label + "-stop.log")).read_text().splitlines() if l.startswith("{")]
            assert len(lines) == 1
            snapshot = json.loads(lines[0])
            result["stop"] = {"exit_code": stop.returncode, "snapshot": snapshot,
                              "elapsed_seconds": round(time.monotonic() - began, 3)}
            assert stop.returncode == 2 and snapshot["phase"] == "ShutdownIncomplete", snapshot
            assert snapshot["shutdown_remaining_ms"] == 0
            assert sorted(snapshot["workers"]) == sorted(int(p) for p in workers), snapshot
            # Competing owners are refused while either worker survives (own
            # port, so only state ownership can refuse it).
            competing = dict(case.config, bind="127.0.0.1:0")
            local = output / (case.label + "-competitor-config.json")
            local.write_text(json.dumps(competing), encoding="utf-8")
            next_config = case.base + "/competitor-config.json"
            run(["cp", str(local), client + ":" + next_config])
            name = case.label + "-competitor"
            competitor = spawn(f"exec {case.binary} {next_config}", name)
            case.processes.append(competitor)
            assert competitor.wait(timeout=6) != 0
            diagnostic = (output / (name + ".log")).read_text()
            assert "local instance or surviving worker already owns state" in diagnostic, diagnostic
            result["competitor_refused"] = True
            restore()
            assert case.service.wait(timeout=30) == 0
            result["worker_exit_after_restore"] = {pid: case.await_exit(pid) for pid in workers}
            free = execute(f"LD_BIND_NOW=1 {case.binary} --status {case.config_path}", "1000:1000", check=False)
            assert json.loads(free.stdout)["phase"] == "NoActiveOwner"
            case.start(False)
            deadline = time.monotonic() + 300
            for job, (body, digest) in zip(jobs, bodies):
                committed = _committed(case, job, deadline)
                name = body["files"][0]
                delivered = execute(f"sha256sum {case.destination}/{body['recording_id']}/{name}", "1000:1000").stdout.split()[0]
                assert delivered == digest, (job, delivered, digest)
                result.setdefault("recovered", []).append({"job_id": job, "attempts": [f["attempt"] for f in committed["details"]["files"]]})
            result.update({"restart_only_after_restore_and_exit": True, "both_delivered_intact": True, "passed": True})
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
                print(f"NFS parallel shutdown {case.label}: {'PASS' if case.result['passed'] else 'BLOCKED'}", flush=True)
        if not results[-1]["passed"]:
            return {"passed": False}
    return {"passed": len(results) == 2 and all(c["passed"] for c in results)}


def run_parallel_throughput(Case, execute, results, concurrency):
    """SC-200 (measurement): THROUGHPUT_JOBS jobs of THROUGHPUT_MIB each from a
    local source to the NFS destination, release build, this worker count.
    Timed from the first submission to the last observed commit; digests are
    verified after the clock stops, so they never compete with deliveries."""
    case = None
    try:
        case = Case("release", "copy_chunk", suffix="-throughput")
        result = case.result
        result.update({"scenario_id": "SC-200", "jobs": THROUGHPUT_JOBS, "mib_per_job": THROUGHPUT_MIB})
        bodies = []
        for index, rid in enumerate(("44444444-4444-4444-8444-44444444444" + str(i) for i in range(THROUGHPUT_JOBS))):
            bodies.append(_recording(execute, case, f"t{index}", THROUGHPUT_MIB, rid))
        case.start(False)
        began = time.monotonic()
        deadline = began + 900  # Submissions and deliveries share one bound.
        jobs = []
        for body, _ in bodies:
            while True:
                code, reply = case.request("POST", "/api/v2/jobs", body)
                if code == 202:
                    break
                assert code == 503 and reply.get("retryable"), reply
                assert time.monotonic() < deadline, "submission not accepted in time"
                time.sleep(0.25)
            jobs.append(reply["job_id"])
        for job in jobs:
            _committed(case, job, deadline)
        elapsed = time.monotonic() - began
        for body, digest in bodies:
            name = body["files"][0]
            delivered = execute(f"sha256sum {case.destination}/{body['recording_id']}/{name}", "1000:1000").stdout.split()[0]
            assert delivered == digest
        total = THROUGHPUT_JOBS * THROUGHPUT_MIB
        result.update({"elapsed_seconds": round(elapsed, 2), "mib_per_second": round(total / elapsed, 1), "passed": True})
        print(f"NFS throughput c={concurrency}: {total} MiB in {elapsed:.1f} s = {total / elapsed:.1f} MiB/s", flush=True)
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
    return {"passed": bool(results) and results[-1]["passed"]}
