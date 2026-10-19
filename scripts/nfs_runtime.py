"""Deterministic real-worker outage checks in the owning private NFS fixture.

All paths, signals and PIDs belong to that fixture. No production NFS enablement.
"""
import hashlib
import json
import time
import traceback
from nfs_binding import binding_for, provision


def run_runtime(run, execute, spawn, restore, server, output, client, artifact_hashes, results, long_only=False, shutdown_only=False, death_only=False, death_scope="claim-copy-verify", endpoints=None, case_runner=None, nfs_root="/tmp/nfs", destination_nfs_root=None):
    expected = hashlib.sha256(bytes(2 * 1048576) + b"0123456789abcdefg").hexdigest()
    claim_points = {"claim_apply", "claim_link", "claim_link_rpc", "claim_unlink_rpc"}
    link_points = {"claim_link", "file_link"}

    class Case:
        def __init__(self, profile, point, production=False, prolonged=False, shutdown=False, shutdown_wait=None, suffix="", both_nfs=False, separate_exports=False, independent_endpoints=False, local_only=False):
            assert not separate_exports or both_nfs
            assert not independent_endpoints or separate_exports
            self.label = "runtime-" + profile + "-" + point + ("-production" if production else "") + ("-long" if prolonged else "")
            if shutdown:
                self.label += "-shutdown-" + ("default60" if shutdown_wait is None else str(shutdown_wait))
            self.label += suffix
            if both_nfs:
                assert not production, "both-NFS effects require qualification artifacts"
                self.label += "-2hosts" if independent_endpoints else "-2exports" if separate_exports else "-both-nfs"
            self.point = point
            self.production = production
            self.base = "/tmp/local/" + self.label
            source_nfs = both_nfs or point in claim_points | {"source_read", "bootstrap", "bootstrap_enrolled", "bootstrap_populated"}
            destination_nfs = both_nfs or (not production and not source_nfs)
            if local_only:
                assert not both_nfs
                source_nfs = destination_nfs = False
            self.source = (nfs_root + "/" + self.label + "/source" if source_nfs else self.base + "/source")
            self.destination = ((destination_nfs_root or nfs_root) + "/" + self.label + "/destination" if destination_nfs else self.base + "/destination")
            if separate_exports:
                self.source = "/tmp/nfs-source/" + self.label + "/source"
                self.destination = "/tmp/nfs-destination/" + self.label + "/destination"
            self.binary = "/tmp/" + (profile if production else "qualification-" + profile)
            self.marker = self.base + "/service.pid"
            self.rendezvous = self.base + "/pause"
            self.counter = 0
            self.processes = []
            self.service_logs = []
            self.worker = None
            self.service = None
            self.result = {"profile": profile, "point": point, "production": production, "passed": False}
            if both_nfs:
                self.result["layout"] = ("both-nfs-separate-exports-local-state" if separate_exports
                                         else "both-nfs-same-export-private-roots-local-state")
            if independent_endpoints:
                self.result["layout"] = "both-nfs-independent-endpoints-local-state"
            digest = execute("sha256sum " + self.binary, "1000:1000").stdout.split()[0]
            assert digest == artifact_hashes[("" if production else "qualification-") + profile]
            self.result["binary_sha256"] = digest
            execute(f"umask 077; mkdir -p {self.source}/.file-mover {self.source}/current/nested {self.destination}/.file-mover {self.base}/state {self.rendezvous}; "
                    f"dd if=/dev/zero of={self.source}/current/nested/data.bin bs=1048576 count=2 2>/dev/null; "
                    f"printf '0123456789abcdefg' >>{self.source}/current/nested/data.bin", "1000:1000")
            assert execute(f"stat -f -c %t {self.base}/state", "1000:1000").stdout.strip() != "6969"
            assert (execute(f"stat -f -c %t {self.source}", "1000:1000").stdout.strip() == "6969") == source_nfs
            assert (execute(f"stat -f -c %t {self.destination}", "1000:1000").stdout.strip() == "6969") == destination_nfs
            if both_nfs:
                self.result["filesystem_types"] = execute(f"stat -f -c %t {self.source} {self.destination} {self.base}/state", "1000:1000").stdout.splitlines()
                assert self.result["filesystem_types"][:2] == ["6969", "6969"]
            if separate_exports:
                self.result["filesystem_devices"] = execute(f"stat -c %d {self.source} {self.destination} {self.base}/state", "1000:1000").stdout.splitlines()
                assert len(set(self.result["filesystem_devices"])) == 3
            self.identities = execute(f"stat -c '%d:%i:%u:%a' {self.source} {self.source}/.file-mover {self.destination} {self.destination}/.file-mover", "1000:1000").stdout
            self.config = {"bind": "127.0.0.1:19878", "generator_id": "fixture", "source_root": self.source,
                           "destination_root": self.destination, "state_database": self.base + "/state/jobs.sqlite"}
            if shutdown and shutdown_wait is not None:
                self.config["shutdown_wait_seconds"] = shutdown_wait
            self.config["destination_binding"] = binding_for(self.label+"-destination", destination_nfs, "destination")
            self.config["source_binding"] = binding_for(self.label, source_nfs)
            if independent_endpoints:
                self.config["destination_binding"]["endpoint_id"] = "fixture-nfs-destination"
                self.config["source_binding"]["endpoint_id"] = "fixture-nfs-source"
                self.result["source_payload_at_setup"] = execute(f"stat -c '%d:%i:%s' {self.source}/current/nested/data.bin; sha256sum {self.source}/current/nested/data.bin", "1000:1000").stdout.splitlines()
            provision(run, execute, output, client, self.destination, self.config["destination_binding"])
            provision(run, execute, output, client, self.source, self.config["source_binding"])
            local = output / (self.label + "-config.json")
            local.write_text(json.dumps(self.config))
            self.config_path = self.base + "/config.json"
            run(["cp", str(local), client + ":" + self.config_path])
            if point != "bootstrap":
                execute(f"{self.binary} --initialize-source {self.config_path}", "1000:1000")
            self.body = {"generator_id": "fixture", "submission_id": self.label, "source_path": self.source + "/current",
                         "files": [{"name": "nested/data.bin"}]}

        def request(self, method, path, body=None, asynchronous=False, connected_marker=None):
            self.counter += 1
            name = self.label + "-request-" + str(self.counter)
            payload = json.dumps(body).encode() if body is not None else b""
            raw = (f"{method} {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\nContent-Type: application/json\r\nContent-Length: {len(payload)}\r\n\r\n").encode() + payload
            local = output / name
            local.write_bytes(raw)
            remote = self.base + "/request-" + str(self.counter)
            run(["cp", str(local), client + ":" + remote])
            connected = f": >{connected_marker}; " if connected_marker else ""
            script = f"exec /bin/bash -c 'exec 3<>/dev/tcp/127.0.0.1/{getattr(self, 'request_port', 19878)}; cat {remote} >&3; {connected}cat <&3'"
            if asynchronous:
                process = spawn(script, name)
                self.processes.append(process)
                return process, output / (name + ".log")
            response = execute(script, "1000:1000", check=False)
            if response.returncode:
                raise RuntimeError(response.stderr)
            return self.parse(response.stdout)

        @staticmethod
        def parse(text):
            head, payload = text.replace("\r\n", "\n").split("\n\n", 1)
            return int(head.split()[1]), json.loads(payload)

        def launch(self, paused, pause_point=None):
            self.counter += 1
            name = self.label + "-service-" + str(self.counter)
            environment = (f"FILE_MOVER_QUALIFICATION_PAUSE={pause_point or self.point} FILE_MOVER_QUALIFICATION_RENDEZVOUS={self.rendezvous} " if paused else "")
            self.service = spawn(f"echo $$ >{self.marker}; exec env {environment}{self.binary} {self.config_path}", name)
            self.service_logs.append(name + ".log")
            self.processes.append(self.service)

        def start(self, paused, pause_point=None):
            self.launch(paused, pause_point)
            for _ in range(30):
                if self.service.poll() is not None:
                    raise RuntimeError("runtime service startup failed: " + (output / self.service_logs[-1]).read_text())
                try:
                    if self.request("GET", "/healthz")[0] == 200:
                        return
                except (RuntimeError, ValueError):
                    time.sleep(0.2)
            raise RuntimeError("runtime startup health unavailable")

        def state(self, pid):
            assert str(pid).isdigit()
            stat = execute(f"cat /proc/{pid}/stat", "1000:1000", check=False)
            if stat.returncode:
                absent = execute(f"test ! -d /proc/{pid}", "1000:1000", check=False)
                if absent.returncode == 0:
                    return ""
                raise RuntimeError("worker process state unavailable; exit is unconfirmed")
            return stat.stdout.rsplit(")", 1)[1].split()[0]

        def signal(self, pid, signal):
            assert str(pid).isdigit() and signal in {"TERM", "KILL", "STOP", "CONT"}
            execute(f"kill -{signal} {pid} 2>/dev/null || true", "1000:1000")

        def service_pid(self):
            pid = execute("cat " + self.marker, "1000:1000").stdout.strip()
            assert pid.isdigit()
            return pid

        def children(self):
            pid = self.service_pid()
            text = execute(f"for task in /proc/{pid}/task/*/children; do cat $task; done", "1000:1000").stdout
            return sorted(set(text.split()))

        def await_pause(self, point=None):
            point = point or self.point
            for _ in range(60):
                response = execute(f"cat {self.rendezvous}/ready", "1000:1000", check=False)
                if response.returncode == 0 and response.stdout.endswith("\n") and len(response.stdout.split()) == 2:
                    pid, operation = response.stdout.split()
                    assert pid.isdigit() and operation == point
                    assert self.children() == [pid], "not exactly one live assigned worker"
                    command = execute(f"tr '\\000' ' ' </proc/{pid}/cmdline", "1000:1000").stdout
                    expected_mode = "--internal-claim-worker" if point in claim_points else "--internal-delivery-worker"
                    assert self.binary in command and expected_mode in command
                    self.worker = pid
                    self.result["paused_worker"] = {"pid": pid, "command": command}
                    return
                time.sleep(0.1)
            raise RuntimeError("worker never reached qualification rendezvous")

        def await_exit(self, pid):
            # An orphan may be a zombie under the fixture's minimal PID 1.
            # Z proves exit/files closed; it does not mean PID 1 reaped it.
            for _ in range(60):
                state = self.state(pid)
                if state in {"", "Z"}:
                    return state or "gone"
                time.sleep(0.2)
            raise RuntimeError("worker exit not confirmed")

        def link_names(self):
            if self.point == "claim_link":
                return self.source + "/current/nested/data.bin", self.source + "/.file-mover/1-0/data"
            assert self.point == "file_link"
            return self.destination + "/1/.staging/1.part", self.destination + "/1/nested/data.bin"

        def owned_aliases(self):
            old, new = self.link_names()
            aliases = execute(f"stat -c '%d:%i:%h:%s' {old} {new}", "1000:1000").stdout.splitlines()
            assert len(aliases) == 2 and aliases[0] == aliases[1]
            assert aliases[0].split(":")[2:] == ["2", str(2 * 1048576 + 17)]
            assert [line.split()[0] for line in execute(f"sha256sum {old} {new}", "1000:1000").stdout.splitlines()] == [expected, expected]
            return aliases

        def recover(self, restart=True):
            if restart:
                self.start(False)
            for _ in range(18 if not restart else 1):
                code, replay = self.request("POST", "/api/v2/jobs", self.body)
                if code == 202:
                    break
                assert not restart and code == 503 and replay["error"] in {"handoff_pending", "service_busy"}
                assert replay["retryable"]
                assert not replay["source_paths_released"]
                time.sleep(1)
            assert code == 202 and replay["job_id"] == "1" and replay["source_paths_released"]
            for _ in range(180):
                code, status = self.request("GET", "/api/v2/jobs/1")
                assert code == 200
                if status["state"] == "Committed":
                    self.result["recovered_status"] = status
                    return status
                assert status["details"]["condition"] != "ReviewRequired", status
                time.sleep(1)
            raise RuntimeError("recording did not recover to Committed")

        def prolonged_outage(self, status, posted):
            # The rendezvous has already been released into real hard-mounted
            # NFS operations. All observations below use local state or /proc.
            started = time.monotonic()
            coordinator = self.service_pid()
            self.result["live_coordinator_pid"] = coordinator
            samples = []
            retry_thresholds = iter((0, 60, 120))
            next_retry = next(retry_thresholds)
            self.result["long_outage_samples"] = samples
            while True:
                elapsed = time.monotonic() - started
                began = time.monotonic()
                assert self.request("GET", "/healthz")[0] == 200
                health_seconds = time.monotonic() - began
                began = time.monotonic()
                code, during = self.request("GET", "/api/v2/jobs/1")
                status_seconds = time.monotonic() - began
                assert code == 200 and health_seconds < 5 and status_seconds < 5
                assert during["state"] == status["state"]
                assert during["source_paths_released"] == status["source_paths_released"]
                assert during["details"]["files"] == status["details"]["files"]
                assert during["details"]["manifest_phase"] == status["details"]["manifest_phase"]
                assert self.children() == [self.worker], "worker accumulated or was replaced during outage"
                assert self.service.poll() is None and self.service_pid() == coordinator
                worker_state = self.state(self.worker)
                assert worker_state == "D", "long-outage worker did not remain kernel-blocked"
                if self.point == "verify_read":
                    assert execute(f"test ! -e {self.rendezvous}/read-completed", "1000:1000", check=False).returncode == 0
                sample = {"elapsed_seconds": round(elapsed, 3), "health_seconds": round(health_seconds, 3),
                          "status_seconds": round(status_seconds, 3), "worker_state": worker_state,
                          "children": [self.worker], "status": during}
                samples.append(sample)
                # A timed-out HTTP waiter leaves its command in the single-slot
                # submission queue. Later sequential retries may see service_busy.
                # This is not a concurrent flood or memory-capacity measurement.
                if next_retry is not None and elapsed >= next_retry:
                    code, replay = self.request("POST", "/api/v2/jobs", self.body)
                    sample["retry"] = [code, replay]
                    if self.point in claim_points:
                        assert code == 503 and replay["error"] in {"handoff_pending", "service_busy"}
                        assert replay["retryable"] and not replay["source_paths_released"]
                    else:
                        assert code == 202 and replay["job_id"] == "1" and replay["source_paths_released"]
                    assert self.children() == [self.worker]
                    next_retry = next(retry_thresholds, None)
                print(f"NFS long outage {self.label}: {elapsed:.0f}/180 seconds, health/status responsive, one blocked worker", flush=True)
                if elapsed >= 180:
                    break
                time.sleep(min(15, 180 - elapsed))
            self.result["outage_observation_seconds"] = round(time.monotonic() - started, 3)
            assert self.result["outage_observation_seconds"] >= 180
            assert sum("retry" in sample for sample in samples) == 3
            if self.point in claim_points:
                assert any(sample.get("retry", [None, {}])[1].get("error") == "service_busy" for sample in samples)
                self.result["submission_backpressure_observed"] = True
            if self.point in claim_points:
                process, response_path = posted
                assert process.wait(timeout=5) == 0
                reply = self.parse(response_path.read_text())
                assert reply[0] == 503 and not reply[1]["source_paths_released"]
                self.result["initial_handoff_response_during_outage"] = reply
            restore()
            recovery_started = time.monotonic()
            recovered = self.recover(restart=False)
            assert self.service.poll() is None and self.service_pid() == coordinator
            self.result["recovery_without_restart"] = True
            self.result["recovery_after_restore_seconds"] = round(time.monotonic() - recovery_started, 3)
            assert recovered["details"]["files"][0]["attempt"] == 1
            assert recovered["details"]["source_cleanup_enabled"] is False
            if self.point in claim_points:
                execute(f"printf 'next recording' >{self.source}/current/nested/data.bin", "1000:1000")
                code, replay = self.request("POST", "/api/v2/jobs", self.body)
                assert code == 202 and replay["job_id"] == "1" and replay["source_paths_released"]
            assert execute(f"cat {self.source}/current/nested/data.bin", "1000:1000").stdout == "next recording"
            self.verify()
            self.result["passed"] = True

        def verify(self):
            private = self.source + "/.file-mover/1-0/data"
            final = self.destination + "/1/nested/data.bin"
            hashes = execute(f"sha256sum {private} {final}", "1000:1000").stdout.splitlines()
            assert [line.split()[0] for line in hashes] == [expected, expected]
            manifest = json.loads(execute(f"cat {self.destination}/1/COMMITTED.json", "1000:1000").stdout)
            assert manifest["version"] == 1 and manifest["submission_id"] == self.label
            assert manifest["generator_id"] == "fixture" and manifest["job_id"] == "1"
            assert [(f["path"], f["size_bytes"], f["algorithm"], f["sha256"]) for f in manifest["files"]] == [("nested/data.bin", 2 * 1048576 + 17, "sha256", expected)]
            assert execute(f"stat -c '%d:%i:%u:%a' {self.source} {self.source}/.file-mover {self.destination} {self.destination}/.file-mover", "1000:1000").stdout == self.identities
            self.result.update({"hashes": hashes, "manifest": manifest, "root_identities_stable": True, "source_retained": True})
            if "manifest_hash_before_outage" in self.result:
                assert execute(f"sha256sum {self.destination}/1/COMMITTED.json", "1000:1000").stdout.split()[0] == self.result["manifest_hash_before_outage"]

        def cleanup(self):
            restore()  # Always restore before trying to terminate/reap hard-mount users.
            if self.worker:
                self.signal(self.worker, "CONT")
                self.signal(self.worker, "KILL")
            if self.service and self.service.poll() is None:
                self.signal(self.service_pid(), "TERM")
            for process in self.processes:
                process.wait(timeout=30)
            if self.worker:
                self.result["cleanup_worker_exit"] = self.await_exit(self.worker)
            self.result["service_logs"] = {name: (output / name).read_text() for name in self.service_logs}

    if case_runner is not None:
        return case_runner(Case)

    if death_only:
        from nfs_death import run_death
        return run_death(Case, run, execute, spawn, restore, server, output, client, results, death_scope, endpoints)

    if shutdown_only:
        from nfs_shutdown import run_shutdown
        return run_shutdown(Case, run, execute, spawn, restore, server, output, client, results)

    for profile in ("debug", "release"):
        cases = [(point, False) for point in ("production_controls_ignored", "claim_apply", "claim_link", "source_read", "copy_chunk", "verify_read", "publish", "file_link", "manifest_link")]
        cases += [("claim_apply", True), ("verify_read", True)]
        if long_only:
            cases = [(point, prolonged) for point, prolonged in cases if prolonged]
        for point, prolonged in cases:
            case = None
            try:
                case = Case(profile, "copy_chunk" if point == "production_controls_ignored" else point, point == "production_controls_ignored", prolonged)
                case.result["case"] = point + ("_long" if prolonged else "")
                case.result["scenario_id"] = {
                    "production_controls_ignored": "SC-035", "claim_apply": "SC-037",
                    "source_read": "SC-041", "copy_chunk": "SC-038", "verify_read": "SC-042",
                    "publish": "SC-039", "manifest_link": "SC-040",
                    "claim_link": "SC-049", "file_link": "SC-050",
                }[point]
                if prolonged:
                    case.result["scenario_id"] = "SC-051" if point == "claim_apply" else "SC-052"
                case.start(True)
                if case.production:
                    assert case.request("POST", "/api/v2/jobs", case.body)[0] == 202
                    for _ in range(60):
                        status = case.request("GET", "/api/v2/jobs/1")[1]
                        if status["state"] == "Committed":
                            break
                        time.sleep(0.2)
                    assert status["state"] == "Committed"
                    assert execute(f"test ! -e {case.rendezvous}/ready", "1000:1000", check=False).returncode == 0
                    case.verify()
                    case.result["passed"] = True
                    continue
                posted = case.request("POST", "/api/v2/jobs", case.body, asynchronous=point in claim_points)
                if point not in claim_points:
                    assert posted[0] == 202
                    execute(f"printf 'next recording' >{case.source}/current/nested/data.bin", "1000:1000")
                case.await_pause()
                status = case.request("GET", "/api/v2/jobs/1")[1]
                case.result["status_at_pause"] = status
                if point in claim_points:
                    assert status["state"] == "Accepted" and not status["source_paths_released"]
                else:
                    assert status["state"] == "Claimed"
                    expected_phase = {"source_read": "Intent", "copy_chunk": "Intent", "verify_read": "Copied", "publish": "PublishIntent", "file_link": "PublishIntent", "manifest_link": "Published"}[point]
                    assert status["details"]["files"][0]["transfer_phase"] == expected_phase
                if point == "copy_chunk":
                    size = int(execute(f"stat -c %s {case.destination}/1/.staging/1.part", "1000:1000").stdout)
                    assert size == 1048576
                    case.result["partial_bytes_before_outage"] = size
                if point == "manifest_link":
                    assert status["details"]["manifest_phase"] == 3
                    aliases = execute(f"stat -c '%d:%i:%h:%s' {case.destination}/1/.staging/COMMITTED.part {case.destination}/1/COMMITTED.json", "1000:1000").stdout.splitlines()
                    assert len(aliases) == 2 and aliases[0] == aliases[1] and aliases[0].split(":")[2] == "2"
                    case.result["manifest_aliases_before_outage"] = aliases
                    case.result["manifest_hash_before_outage"] = execute(f"sha256sum {case.destination}/1/COMMITTED.json", "1000:1000").stdout.split()[0]
                if point in link_points:
                    case.result["owned_aliases_before_outage"] = case.owned_aliases()
                    assert execute(f"test ! -e {case.destination}/1/COMMITTED.json", "1000:1000", check=False).returncode == 0
                    case.result["completion_manifest_absent_at_pause"] = True
                if prolonged:
                    assert execute(f"test ! -e {case.destination}/1/COMMITTED.json", "1000:1000", check=False).returncode == 0
                    case.result["completion_manifest_absent_at_pause"] = True
                run(["exec", server, "rpc.nfsd", "0"])
                # Keep new link cases at the exact durable two-name boundary.
                # Killing there during the outage tests two-name reconciliation,
                # rather than letting an in-flight unlink complete on restore.
                if point not in link_points:
                    execute(f"umask 077; : >{case.rendezvous}/go", "1000:1000")
                case.result["pause_released_during_outage"] = point not in link_points
                time.sleep(3)
                assert case.state(case.worker) not in {"", "Z"}
                assert case.children() == [case.worker], "replacement before confirmed worker exit"
                if point in {"source_read", "verify_read"}:
                    # Advice can be ignored: fail if the payload loop finished
                    # and only a later metadata operation is stuck on NFS.
                    assert execute(f"test ! -e {case.rendezvous}/read-completed", "1000:1000", check=False).returncode == 0
                    case.result["payload_read_incomplete_during_outage"] = True
                    case.result["cache_advice"] = "per-file Random and DontNeed before the read rendezvous"
                    case.result["outage_worker_state"] = case.state(case.worker)
                    assert case.result["outage_worker_state"] == "D", "fixture did not observe a kernel-blocked payload reader"
                    case.result["outage_worker_wait_channel"] = execute(f"cat /proc/{case.worker}/wchan", "1000:1000", check=False).stdout.strip()
                started = time.monotonic()
                assert case.request("GET", "/healthz")[0] == 200
                case.result["outage_health_seconds"] = round(time.monotonic() - started, 3)
                during = case.request("GET", "/api/v2/jobs/1")[1]
                assert during["state"] == status["state"] and during["details"]["files"] == status["details"]["files"]
                assert case.children() == [case.worker]
                case.result["outage_status"] = during
                if prolonged:
                    case.prolonged_outage(status, posted)
                    continue
                if point == "publish":
                    case.signal(case.worker, "STOP")
                    case.signal(case.service_pid(), "KILL")
                    assert case.service.wait(timeout=10) != 0
                    assert execute(f"exec 9<>{case.source}/.file-mover/coordinator.lock; flock -xn 9", "1000:1000", check=False).returncode != 0
                    competitor_config = dict(case.config, bind="127.0.0.1:19879", state_database=case.base + "/competitor.sqlite")
                    local = output / (case.label + "-competitor.json")
                    local.write_text(json.dumps(competitor_config))
                    run(["cp", str(local), client + ":" + case.base + "/competitor.json"])
                    competitor = spawn(f"exec {case.binary} {case.base}/competitor.json", case.label + "-competitor")
                    case.processes.append(competitor)
                    assert competitor.wait(timeout=15) != 0
                    assert execute(f"test ! -e {case.base}/competitor.sqlite", "1000:1000", check=False).returncode == 0
                    assert "Ready on" not in (output / (case.label + "-competitor.log")).read_text()
                    restore()
                    assert execute(f"exec 9<>{case.source}/.file-mover/coordinator.lock; flock -xn 9", "1000:1000", check=False).returncode != 0
                    case.result["coordinator_death"] = "Actual assigned child retained source custody; competing startup refused before SQLite/readiness"
                    case.signal(case.worker, "CONT")
                    case.result["worker_exit_after_restore"] = case.await_exit(case.worker)
                    final = case.destination + "/1/nested/data.bin"
                    present = execute(f"test -f {final}", "1000:1000", check=False).returncode == 0
                    case.result["publication_present_before_restart"] = present
                    if present:
                        digest = execute("sha256sum " + final, "1000:1000").stdout.split()[0]
                        assert digest == expected
                        case.result["publication_hash_before_restart"] = digest
                else:
                    if point != "claim_apply":
                        case.signal(case.worker, "KILL")
                    case.signal(case.service_pid(), "TERM")
                    time.sleep(0.5)
                    case.result["worker_exit_observed_before_restore"] = case.state(case.worker) in {"", "Z"}
                    case.result["service_exit_observed_before_restore"] = case.service.poll() is not None
                    restore()
                    case.result["worker_exit_after_restore"] = case.await_exit(case.worker)
                    assert case.service.wait(timeout=30) == 0
                    if point in claim_points:
                        process, response_path = posted
                        process.wait(timeout=15)
                        response = response_path.read_text()
                        if response.startswith("HTTP/"):
                            reply = case.parse(response)
                            assert reply[0] != 202 and not reply[1]["source_paths_released"]
                            case.result["interrupted_handoff_response"] = reply
                        elif response.strip():
                            case.result["interrupted_handoff_transport"] = response
                if point in link_points:
                    case.result["owned_aliases_before_recovery"] = case.owned_aliases()
                    assert case.result["owned_aliases_before_recovery"] == case.result["owned_aliases_before_outage"]
                    assert execute(f"test ! -e {case.destination}/1/COMMITTED.json", "1000:1000", check=False).returncode == 0
                    case.result["completion_manifest_absent_before_recovery"] = True
                recovered = case.recover()
                assert recovered["details"]["source_cleanup_enabled"] is False
                attempt = recovered["details"]["files"][0]["attempt"]
                if point in {"source_read", "copy_chunk"}:
                    assert attempt == 2
                    old = case.destination + "/1/.staging/1.part"
                    assert execute(f"test -f {old}", "1000:1000", check=False).returncode == 0
                    case.result["preserved_partial_bytes"] = int(execute(f"stat -c %s {old}", "1000:1000").stdout)
                else:
                    assert attempt == 1
                if point == "manifest_link":
                    assert execute(f"test ! -e {case.destination}/1/.staging/COMMITTED.part", "1000:1000", check=False).returncode == 0
                    assert execute(f"stat -c %h {case.destination}/1/COMMITTED.json", "1000:1000").stdout.strip() == "1"
                if point in link_points:
                    old, new = case.link_names()
                    assert execute(f"test ! -e {old}", "1000:1000", check=False).returncode == 0
                    identity = execute(f"stat -c '%d:%i:%h:%s' {new}", "1000:1000").stdout.strip()
                    before = case.result["owned_aliases_before_outage"][0].split(":")
                    assert identity.split(":") == before[:2] + ["1", before[3]]
                    case.result["owned_binding_after_recovery"] = identity
                    if point == "claim_link":
                        execute(f"printf 'next recording' >{old}", "1000:1000")
                        code, replay = case.request("POST", "/api/v2/jobs", case.body)
                        assert code == 202 and replay["job_id"] == "1" and replay["source_paths_released"]
                if point != "claim_apply":
                    assert execute(f"cat {case.source}/current/nested/data.bin", "1000:1000").stdout == "next recording"
                case.verify()
                case.result["passed"] = True
            except Exception as error:
                if case:
                    case.result["error"] = f"{type(error).__name__}: {error}"
                    case.result["failure_traceback"] = traceback.format_exc()
                else:
                    raise
            finally:
                if case:
                    try:
                        case.cleanup()
                    except Exception as error:
                        case.result["passed"] = False
                        case.result["cleanup_error"] = str(error)
                        results.append(case.result)
                        raise RuntimeError("runtime fixture cleanup uncertain") from error
                    results.append(case.result)
                    (output / (case.label + "-result.json")).write_text(json.dumps(case.result, indent=2) + "\n")
                    print(f"NFS runtime {profile}/{case.result['case']}: {'PASS' if case.result['passed'] else 'FAILED'}", flush=True)
    return {"passed": all(r["passed"] for r in results), "cases": results}
