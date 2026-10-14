"""Deterministic real-worker outage checks in the owning private NFS fixture.

All paths, signals and PIDs belong to that fixture. No production NFS enablement.
"""
import hashlib
import json
import time
import traceback


def run_runtime(run, execute, spawn, restore, server, output, client, artifact_hashes, results):
    expected = hashlib.sha256(bytes(2 * 1048576) + b"0123456789abcdefg").hexdigest()

    class Case:
        def __init__(self, profile, point, production=False):
            self.label = "runtime-" + profile + "-" + point + ("-production" if production else "")
            self.point = point
            self.production = production
            self.base = "/tmp/local/" + self.label
            self.source = ("/tmp/nfs/" + self.label + "/source" if point == "claim_apply" else self.base + "/source")
            self.destination = (self.base + "/destination" if point == "claim_apply" or production else "/tmp/nfs/" + self.label + "/destination")
            self.binary = "/tmp/" + (profile if production else "qualification-" + profile)
            self.marker = self.base + "/service.pid"
            self.rendezvous = self.base + "/pause"
            self.counter = 0
            self.processes = []
            self.service_logs = []
            self.worker = None
            self.service = None
            self.result = {"profile": profile, "point": point, "production": production, "passed": False}
            digest = execute("sha256sum " + self.binary, "1000:1000").stdout.split()[0]
            assert digest == artifact_hashes[("" if production else "qualification-") + profile]
            self.result["binary_sha256"] = digest
            execute(f"umask 077; mkdir -p {self.source}/.file-mover {self.source}/current/nested {self.destination}/.file-mover {self.base}/state {self.rendezvous}; "
                    f"dd if=/dev/zero of={self.source}/current/nested/data.bin bs=1048576 count=2 2>/dev/null; "
                    f"printf '0123456789abcdefg' >>{self.source}/current/nested/data.bin", "1000:1000")
            assert execute(f"stat -f -c %t {self.base}/state", "1000:1000").stdout.strip() != "6969"
            assert (execute(f"stat -f -c %t {self.source}", "1000:1000").stdout.strip() == "6969") == (point == "claim_apply")
            assert (execute(f"stat -f -c %t {self.destination}", "1000:1000").stdout.strip() == "6969") == (not production and point != "claim_apply")
            self.identities = execute(f"stat -c '%d:%i:%u:%a' {self.source} {self.source}/.file-mover {self.destination} {self.destination}/.file-mover", "1000:1000").stdout
            self.config = {"bind": "127.0.0.1:19878", "generator_id": "fixture", "source_root": self.source,
                           "destination_root": self.destination, "state_database": self.base + "/state/jobs.sqlite"}
            local = output / (self.label + "-config.json")
            local.write_text(json.dumps(self.config))
            self.config_path = self.base + "/config.json"
            run(["cp", str(local), client + ":" + self.config_path])
            self.body = {"generator_id": "fixture", "submission_id": self.label, "source_path": self.source + "/current",
                         "files": [{"name": "nested/data.bin"}]}

        def request(self, method, path, body=None, asynchronous=False):
            self.counter += 1
            name = self.label + "-request-" + str(self.counter)
            payload = json.dumps(body).encode() if body is not None else b""
            raw = (f"{method} {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\nContent-Type: application/json\r\nContent-Length: {len(payload)}\r\n\r\n").encode() + payload
            local = output / name
            local.write_bytes(raw)
            remote = self.base + "/request-" + str(self.counter)
            run(["cp", str(local), client + ":" + remote])
            script = f"exec /bin/bash -c 'exec 3<>/dev/tcp/127.0.0.1/19878; cat {remote} >&3; cat <&3'"
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

        def start(self, paused):
            self.counter += 1
            name = self.label + "-service-" + str(self.counter)
            environment = (f"FILE_MOVER_QUALIFICATION_PAUSE={self.point} FILE_MOVER_QUALIFICATION_RENDEZVOUS={self.rendezvous} " if paused else "")
            self.service = spawn(f"echo $$ >{self.marker}; exec env {environment}{self.binary} {self.config_path}", name)
            self.service_logs.append(name + ".log")
            self.processes.append(self.service)
            for _ in range(30):
                if self.service.poll() is not None:
                    raise RuntimeError("runtime service startup failed: " + (output / (name + ".log")).read_text())
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

        def await_pause(self):
            for _ in range(60):
                response = execute(f"cat {self.rendezvous}/ready", "1000:1000", check=False)
                if response.returncode == 0 and response.stdout.endswith("\n") and len(response.stdout.split()) == 2:
                    pid, operation = response.stdout.split()
                    assert pid.isdigit() and operation == self.point
                    assert self.children() == [pid], "not exactly one live assigned worker"
                    command = execute(f"tr '\\000' ' ' </proc/{pid}/cmdline", "1000:1000").stdout
                    expected_mode = "--internal-claim-worker" if self.point == "claim_apply" else "--internal-delivery-worker"
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

        def recover(self):
            self.start(False)
            code, replay = self.request("POST", "/api/v2/jobs", self.body)
            assert code == 202 and replay["job_id"] == "1" and replay["source_paths_released"]
            for _ in range(60):
                code, status = self.request("GET", "/api/v2/jobs/1")
                assert code == 200
                if status["state"] == "Committed":
                    self.result["recovered_status"] = status
                    return status
                assert status["details"]["condition"] != "ReviewRequired", status
                time.sleep(0.2)
            raise RuntimeError("recording did not recover to Committed")

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

    for profile in ("debug", "release"):
        for point in ("production_controls_ignored", "claim_apply", "copy_chunk", "publish", "manifest_link"):
            case = None
            try:
                case = Case(profile, "copy_chunk" if point == "production_controls_ignored" else point, point == "production_controls_ignored")
                case.result["case"] = point
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
                posted = case.request("POST", "/api/v2/jobs", case.body, asynchronous=point == "claim_apply")
                if point != "claim_apply":
                    assert posted[0] == 202
                    execute(f"printf 'next recording' >{case.source}/current/nested/data.bin", "1000:1000")
                case.await_pause()
                status = case.request("GET", "/api/v2/jobs/1")[1]
                case.result["status_at_pause"] = status
                if point == "claim_apply":
                    assert status["state"] == "Accepted" and not status["source_paths_released"]
                else:
                    assert status["state"] == "Claimed"
                    expected_phase = {"copy_chunk": "Intent", "publish": "PublishIntent", "manifest_link": "Published"}[point]
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
                run(["exec", server, "rpc.nfsd", "0"])
                execute(f"umask 077; : >{case.rendezvous}/go", "1000:1000")
                time.sleep(3)
                assert case.state(case.worker) not in {"", "Z"}
                assert case.children() == [case.worker], "replacement before confirmed worker exit"
                started = time.monotonic()
                assert case.request("GET", "/healthz")[0] == 200
                case.result["outage_health_seconds"] = round(time.monotonic() - started, 3)
                during = case.request("GET", "/api/v2/jobs/1")[1]
                assert during["state"] == status["state"] and during["details"]["files"] == status["details"]["files"]
                assert case.children() == [case.worker]
                case.result["outage_status"] = during
                if point == "publish":
                    case.signal(case.worker, "STOP")
                    case.signal(case.service_pid(), "KILL")
                    assert case.service.wait(timeout=10) != 0
                    assert execute(f"flock -xn {case.source}/.file-mover true", "1000:1000", check=False).returncode != 0
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
                    assert execute(f"flock -xn {case.source}/.file-mover true", "1000:1000", check=False).returncode != 0
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
                    if point == "claim_apply":
                        process, response_path = posted
                        process.wait(timeout=15)
                        response = response_path.read_text()
                        if response.startswith("HTTP/"):
                            reply = case.parse(response)
                            assert reply[0] != 202 and not reply[1]["source_paths_released"]
                            case.result["interrupted_handoff_response"] = reply
                        elif response.strip():
                            case.result["interrupted_handoff_transport"] = response
                recovered = case.recover()
                assert recovered["details"]["source_cleanup_enabled"] is False
                attempt = recovered["details"]["files"][0]["attempt"]
                if point == "copy_chunk":
                    assert attempt == 2
                    old = case.destination + "/1/.staging/1.part"
                    assert execute(f"test -f {old}", "1000:1000", check=False).returncode == 0
                    case.result["preserved_partial_bytes"] = int(execute(f"stat -c %s {old}", "1000:1000").stdout)
                else:
                    assert attempt == 1
                if point == "manifest_link":
                    assert execute(f"test ! -e {case.destination}/1/.staging/COMMITTED.part", "1000:1000", check=False).returncode == 0
                    assert execute(f"stat -c %h {case.destination}/1/COMMITTED.json", "1000:1000").stdout.strip() == "1"
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
                    print(f"NFS runtime {profile}/{point}: {'PASS' if case.result['passed'] else 'FAILED'}", flush=True)
    return {"passed": all(r["passed"] for r in results), "cases": results}
