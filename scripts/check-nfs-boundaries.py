"""Container-only NFS startup/lock/outage qualification; does not enable NFS.

Reuses exact service artifacts from a passing mandatory SLES gate. The saved
E2 server image and preloaded nfs/nfsd modules must be available in the engine.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import time
import traceback
import uuid
from nfs_binding import binding_for, provision

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "scripts/rust-platform.json").read_text())
SERVER = "localhost/background-file-mover-e2-nfs"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gate", type=Path, help="Passing rust/validation run directory")
    parser.add_argument("--connection", default="podman-machine-default-root")
    parser.add_argument("--isolated-startup", action="store_true",
                        help="Require startup termination and child exit before NFS restoration")
    parser.add_argument("--qualification-gate", type=Path,
                        help="Also run normal REST transfers with audited NFS qualification artifacts")
    parser.add_argument("--runtime", action="store_true",
                        help="Also qualify real Rust worker interruption/outage and coordinator death")
    parser.add_argument("--long-outages-only", action="store_true",
                        help="With --runtime, run only the four three-minute runtime cases; retain baseline and OS checks")
    parser.add_argument("--shutdown", action="store_true",
                        help="Qualify local stop/status and ownership during actual hard-NFS worker stalls")
    parser.add_argument("--coordinator-death", action="store_true",
                        help="Qualify original-state exclusion/recovery after coordinator death with blocked/terminating NFS workers")
    parser.add_argument("--death-scope", choices=("claim-copy-verify", "bootstrap-source-read", "bootstrap-existing-state", "publication-manifest", "both-nfs", "separate-exports"),
                        help="With --coordinator-death, select the finite worker-phase matrix (default: claim-copy-verify)")
    parser.add_argument("--ownership", action="store_true",
                        help="Diagnose two-client source exclusion and missing-mount startup; does not approve production NFS")
    parser.add_argument("--enrollment-storage", action="store_true",
                        help="Qualify real ENOSPC on a bounded disposable server export, including safe retry versus review")
    parser.add_argument("--delivery-storage", action="store_true",
                        help="Qualify destination-full payload copying and audited recovery, including original-state restart")
    parser.add_argument("--source-storage", action="store_true",
                        help="Qualify source-space admission and unchanged-policy recovery on a bounded export")
    args = parser.parse_args()
    assert not args.death_scope or args.coordinator_death, "death-scope requires --coordinator-death"
    assert not args.coordinator_death or args.qualification_gate, "coordinator-death checks require qualification artifacts"
    assert sum((args.coordinator_death, args.shutdown, args.runtime)) <= 1, "select one runtime matrix"
    assert not args.shutdown or args.qualification_gate, "shutdown checks require qualification artifacts"
    assert not (args.shutdown and args.runtime), "select shutdown or runtime matrix, not both"
    assert not args.runtime or args.qualification_gate, "runtime checks require qualification artifacts"
    assert not args.long_outages_only or args.runtime, "long-outages-only requires --runtime"
    assert not args.ownership or args.qualification_gate, "ownership probes require qualification artifacts"
    assert not args.enrollment_storage or args.qualification_gate, "storage probes require qualification artifacts"
    assert not args.delivery_storage or args.qualification_gate, "delivery storage probes require qualification artifacts"
    assert not args.source_storage or args.qualification_gate, "source storage probes require qualification artifacts"
    engine = ["podman", "--connection", args.connection]
    gate = args.gate.resolve()
    evidence = json.loads((gate / "report.json").read_text())
    assert evidence["status"] == "PASSED" and evidence["config"] == CONFIG
    assert evidence.get("build_mode", "production") == "production", "boundary checks require production artifacts"
    # Never reuse artifacts after changes to Rust build inputs.
    with tarfile.open(gate / "source.tar.gz") as archive:
        archived_files = set()
        for member in archive.getmembers():
            if member.isfile():
                archived_files.add(member.name)
                path = (ROOT / "rust" / member.name).resolve()
                assert path.is_relative_to(ROOT / "rust")
                assert path.read_bytes() == archive.extractfile(member).read(), member.name
        current_files = set()
        for child in (ROOT / "rust").iterdir():
            if child.name not in {"target", "validation"}:
                candidates = child.rglob("*") if child.is_dir() else [child]
                current_files.update(p.relative_to(ROOT / "rust").as_posix()
                                     for p in candidates if p.is_file())
        assert current_files == archived_files, "Rust source inventory changed"
    qualification = None
    if args.qualification_gate:
        qualification_gate = args.qualification_gate.resolve()
        qualification = json.loads((qualification_gate / "report.json").read_text())
        assert qualification["status"] == "PASSED" and qualification["config"] == CONFIG
        assert qualification["build_mode"] == "nfs-qualification"
        with tarfile.open(qualification_gate / "source.tar.gz") as archive:
            entries = {m.name for m in archive.getmembers() if m.isfile()}
            assert entries == current_files
            for member in archive.getmembers():
                if member.isfile():
                    path = (ROOT / "rust" / member.name).resolve()
                    assert path.is_relative_to(ROOT / "rust")
                    assert path.read_bytes() == archive.extractfile(member).read(), member.name
    label = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    output = ROOT / "rust/validation" / ("nfs-" + label)
    output.mkdir()
    report = {"status": "FAILED", "run_id": "nfs-" + label,
              "isolated_startup_required": args.isolated_startup,
              "gate": gate.name, "runtime": CONFIG["runtime"],
              "source_sha256": evidence["source_sha256"], "checks": {}, "cleanup_errors": []}
    report["coordinator_death_requested"] = args.coordinator_death
    report["coordinator_death_scope"] = args.death_scope or "claim-copy-verify"
    report["shutdown_requested"] = args.shutdown
    report["runtime_requested"] = args.runtime
    report["ownership_requested"] = args.ownership
    report["enrollment_storage_requested"] = args.enrollment_storage
    report["delivery_storage_requested"] = args.delivery_storage
    report["source_storage_requested"] = args.source_storage
    report["runtime_scope"] = "coordinator-death" if args.coordinator_death else "shutdown" if args.shutdown else "long-outages-only" if args.long_outages_only else "all" if args.runtime else "none"
    report["limitations"] = [
        "SLES 12 SP5 userspace on WSL2 kernel, not the SLES kernel or old CPU hardware.",
        "One client and modern controlled server; no cross-client fencing or server reboot/power-loss evidence.",
        "Lock and interrupted metadata probes use OS tools, not Rust claim/copy/publication on NFS.",
        "Service startup rejection is measured; production NFS and source deletion remain disabled.",
    ]
    if args.coordinator_death:
        report["limitations"][2] = "Selected real hard-NFS claim/copy/verification workers after coordinator SIGKILL, while blocked or following local stop. Physical flock closure is distinct from logical process-group epoch ownership; both profiles must retain exclusion with a physically closed guard. Prompt exit is distinct from a surviving kernel-blocked child. No systemd, old-kernel, NAS settlement or takeover qualification."
    if args.coordinator_death and args.death_scope == "bootstrap-source-read":
        report["limitations"][2] = "Eight selected bootstrap/source-read hard-NFS cases in debug/release, while blocked or following local stop. Bootstrap must stay unready without SQLite. Surviving orphans retain logical ownership until actual exit; prompt stop is distinct and does not qualify the surviving terminating branch. The original claim/copy/verification raw-lock-closure regression is retained separately. No systemd, old-kernel, NAS settlement or takeover qualification."
    if args.coordinator_death and args.death_scope == "bootstrap-existing-state":
        report["limitations"][2] = "Eight enrolled-empty/populated bootstrap cases, debug/release, blocked or following stop. Populated state has an accepted job, retained WAL and a 1 MiB partial. Local database/sidecar/staging and remote source/receipt evidence must remain unchanged before recovery, with no SQLite inspection or re-enrollment. NFS source/local destination, one shared modern kernel; no both-NFS crash, systemd, NAS settlement, old-kernel or takeover qualification. Prompt exit is distinct from a surviving terminating orphan."
    if args.coordinator_death and args.death_scope == "publication-manifest":
        report["limitations"][2] = "Twelve selected file pre-publication, durable file-link and durable manifest-link cases, debug/release, blocked or following stop. Release the local rendezvous into unavailable hard NFS and require actual D-state workers. Preserve original payload inode/attempt and existing manifest identity/hash through recovery after old exit. A durable manifest name is distinct from a SQLite Committed job. This does not identify the exact in-flight RPC, prove NAS settlement/power durability, qualify both-NFS crashes, systemd, old kernels or takeover. Prompt stop is distinct from a surviving terminating orphan."
    if args.coordinator_death and args.death_scope == "both-nfs":
        report["limitations"][2] = "Twenty-four selected claim/copy/verification/file-publication/file-link/manifest-link cases: both private roots on the same controlled NFSv4.1 export, local database/epoch, debug/release, blocked or following stop. Require actual D-state blockage before death; distinguish prompt exit from surviving orphans. Preserve original state, source inode/receipt, reused paths and verified publication evidence. This does not qualify separate exports/NAS servers, exact in-flight RPCs, NAS settlement/power durability, systemd, old kernels or takeover."
    if args.coordinator_death and args.death_scope == "separate-exports":
        report["limitations"][2] = "Twenty-four selected claim/copy/verification/file-publication/file-link/manifest-link cases across two distinct tmpfs-backed NFSv4.1 exports/mounts on one server, local database/epoch, joint outage, debug/release, blocked or following stop. Preserve original custody/state and publication evidence. Distinct devices/mount IDs and refused cross-filesystem link are required. No independent NAS failure, exact in-flight RPC, remote settlement, persistent-disk/power durability, systemd, old-kernel or takeover qualification."
    if args.shutdown:
        report["limitations"][2] = "Real workers are released into hard-NFS claim/copy/verification stalls before local stop. Prompt kernel-assisted exit and deadline-held incomplete drain are distinct measured outcomes; absence of a surviving worker does not qualify the uninterruptible deadline branch. No NAS settlement, systemd, reboot or old-kernel proof."
    if args.runtime:
        report["limitations"][2] = "Real Rust cases cover selected claim, source-read, copy-write, verification-read, publication and claim/file/manifest-link points, including 180-second blocked claim and verification outages with live recovery. Claim/file-link crashes hold the local rendezvous during server outage and confirm two owned aliases before recovery; they do not model an in-flight unlink RPC. Longer or indefinite outages, queue saturation and export changes remain unqualified. Other lock/startup probes use OS tools."
        if args.long_outages_only:
            report["limitations"][2] = "Runtime cases in this report cover only 180-second blocked claim and verification outages with live recovery. A small sequential same-ID retry workload observes single-slot submission backpressure, not concurrent flooding or memory bounds. Other interruption cases are not rerun here. Longer/indefinite outages, in-flight link/unlink RPCs and export changes remain unqualified. Other lock/startup probes use OS tools."
    if args.ownership:
        report["limitations"][1] = "Two container clients with distinct network/mount namespaces on one shared modern kernel. Ownership probes diagnose exclusion/missing-mount gaps; they do not prove physical-host fencing, partition/reclaim or safe takeover."
    containers = []
    tasks = []
    network = volume = server = client = None
    mounted = False
    mounted_peers = []
    extra_mounts = []

    def run(arguments, check=True, timeout=45):
        result = subprocess.run(engine + arguments, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=timeout)
        if check and result.returncode:
            raise RuntimeError(f"{arguments}: {result.stdout}{result.stderr}")
        return result

    def execute(script, user=None, check=True, target=None):
        return run(["exec", *(["--user", user] if user else []), target or client,
                    "/bin/sh", "-eu", "-c", script], check=check)

    def spawn(script, name, target=None):
        log = (output / (name + ".log")).open("w", encoding="utf-8")
        process = subprocess.Popen(engine + ["exec", "--user", "1000:1000", "--env", "LD_BIND_NOW=1", target or client,
                                   "/bin/sh", "-eu", "-c", script], stdout=log, stderr=log)
        tasks.append((process, log))
        return process

    def await_file(path):
        for _ in range(30):
            if execute(f"test -f {path}", "1000:1000", check=False).returncode == 0:
                return
            time.sleep(0.2)
        raise RuntimeError(f"missing rendezvous {path}")

    def restore():
        run(["exec", server, "rpc.nfsd", "-G", "10", "-L", "10", "-V", "4", "-p", "2049", "2"])

    try:
        report["server_image"] = run(["image", "inspect", SERVER, "--format", "{{.Id}}"]).stdout.strip()
        network = "bfm-nfs-" + label.lower()
        volume = network + "-data"
        run(["network", "create", "--internal", network])
        run(["volume", "create", volume])
        server = run(["create", "--privileged", "--network", network,
                      "--volume", volume + ":/exports", SERVER]).stdout.strip()
        containers.append(server)
        run(["start", server])
        for _ in range(40):
            if "NFS_READY" in run(["logs", server]).stdout:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("NFS server not ready")
        report["server_packages"] = run(["exec", server, "dpkg-query", "-W"]).stdout.splitlines()
        ip = json.loads(run(["inspect", server]).stdout)[0]["NetworkSettings"]["Networks"][network]["IPAddress"]
        client = run(["create", "--network", network, "--cap-drop", "all", "--cap-add", "SYS_ADMIN",
                      "--security-opt", "no-new-privileges", "--entrypoint", "/bin/sh", CONFIG["runtime"],
                      "-c", "exec sleep infinity"]).stdout.strip()
        containers.append(client)
        run(["start", client])
        execute("mkdir /tmp/nfs")
        execute("mkdir -p /tmp/local/state /tmp/local/destination; chmod 700 /tmp/local /tmp/local/state /tmp/local/destination", "1000:1000")
        options = f"addr={ip},vers=4.1,proto=tcp,port=2049,hard,timeo=10,retrans=1,noac"
        run(["exec", client, "mount", "-i", "-t", "nfs4", "-o", options, ip + ":/", "/tmp/nfs"])
        mounted = True
        report["mounts"] = execute("cat /proc/mounts").stdout.splitlines()
        report["kernel"] = execute("uname -r").stdout.strip()
        assert execute("getconf GNU_LIBC_VERSION").stdout.strip() == "glibc 2.22"
        assert execute("stat -f -c %t /tmp/nfs").stdout.strip() == "6969"
        assert any(" /tmp/nfs " in m and "hard" in m and "vers=4.1" in m for m in report["mounts"])
        execute("mkdir /tmp/nfs/source /tmp/nfs/source/.file-mover; chmod 700 /tmp/nfs/source /tmp/nfs/source/.file-mover", "1000:1000")
        before = execute("stat -c '%d:%i:%u:%a' /tmp/nfs/source /tmp/nfs/source/.file-mover", "1000:1000").stdout
        report["root_identity_before"] = before.splitlines()
        config = {"bind": "127.0.0.1:19876", "generator_id": "fixture",
                  "source_root": "/tmp/nfs/source", "destination_root": "/tmp/local/destination",
                  "state_database": "/tmp/local/state/jobs.sqlite"}
        config["destination_binding"] = binding_for("startup-destination", False, "destination")
        config["source_binding"] = binding_for("startup-source", True)
        provision(run, execute, output, client, "/tmp/nfs/source", config["source_binding"])
        config_path = output / "config.json"
        config_path.write_text(json.dumps(config))
        run(["cp", str(config_path), client + ":/tmp/local/config.json"])
        report["artifacts"] = {}
        for profile in ("debug", "release"):
            artifact = next(a for a in evidence["profiles"][profile]["artifacts"] if not a["test"])
            path = gate / artifact["name"]
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            assert digest == artifact["sha256"]
            report["artifacts"][profile] = digest
            run(["cp", str(path), client + ":/tmp/" + profile])
            execute("chmod 755 /tmp/" + profile)
            assert execute("sha256sum /tmp/" + profile).stdout.split()[0] == digest
            loaded = execute("ldd -r /tmp/" + profile).stdout
            assert "not found" not in loaded and "undefined symbol" not in loaded
            result = execute("LD_BIND_NOW=1 /tmp/" + profile + " /tmp/local/config.json", "1000:1000", check=False)
            assert result.returncode != 0 and "filesystem not qualified" in result.stderr
            assert execute("test ! -e /tmp/local/state/jobs.sqlite", "1000:1000", check=False).returncode == 0
            report["checks"][profile + "_startup_rejected"] = result.stderr.strip()
        if qualification:
            from nfs_baseline import run_baseline
            report["qualification_gate"] = qualification_gate.name
            report["baseline"] = run_baseline(qualification_gate, qualification, run, execute, spawn, output, client)
            if not report["baseline"]["passed"]:
                raise RuntimeError("NFS normal-operation baseline blocked; inspect baseline cases")
            if args.enrollment_storage:
                from nfs_storage import qualify_enrollment_storage
                report["enrollment_storage"] = {"passed": False, "cases": [],
                    "driver_sha256": {name: hashlib.sha256((ROOT / "scripts" / name).read_bytes()).hexdigest()
                                      for name in ("check-nfs-boundaries.py", "nfs_storage.py", "nfs_binding.py")}}
                qualify_enrollment_storage(run, execute, spawn, output, client, server, ip, options,
                                           extra_mounts, report["enrollment_storage"])
                assert report["enrollment_storage"]["passed"]
                expected = {case["profile"]: case["binary_sha256"] for case in report["baseline"]["cases"]}
                assert report["enrollment_storage"]["artifacts"] == expected
            if args.delivery_storage:
                from nfs_delivery_storage import qualify_delivery_storage
                report["delivery_storage"] = {"passed": False, "cases": [],
                    "driver_sha256": {name: hashlib.sha256((ROOT / "scripts" / name).read_bytes()).hexdigest()
                                      for name in ("check-nfs-boundaries.py", "nfs_delivery_storage.py", "nfs_binding.py")}}
                qualify_delivery_storage(run, execute, spawn, output, client, server, ip, options,
                                         extra_mounts, report["delivery_storage"])
                assert report["delivery_storage"]["passed"]
                expected = {case["profile"]: case["binary_sha256"] for case in report["baseline"]["cases"]}
                assert report["delivery_storage"]["artifacts"] == expected
            if args.source_storage:
                from nfs_source_storage import qualify_source_storage
                report["source_storage"] = {"passed": False, "cases": [],
                    "driver_sha256": {name: hashlib.sha256((ROOT / "scripts" / name).read_bytes()).hexdigest()
                                      for name in ("check-nfs-boundaries.py", "nfs_source_storage.py", "nfs_binding.py")}}
                qualify_source_storage(run, execute, spawn, output, client, server, ip, options,
                                       extra_mounts, report["source_storage"])
                assert report["source_storage"]["passed"]
                expected = {case["profile"]: case["binary_sha256"] for case in report["baseline"]["cases"]}
                assert report["source_storage"]["artifacts"] == expected
            if args.ownership:
                peer = run(["create", "--network", network, "--cap-drop", "all", "--cap-add", "SYS_ADMIN",
                            "--security-opt", "no-new-privileges", "--entrypoint", "/bin/sh", CONFIG["runtime"],
                            "-c", "exec sleep infinity"]).stdout.strip()
                containers.append(peer)
                run(["start", peer])
                execute("mkdir /tmp/nfs", target=peer)
                run(["exec", peer, "mount", "-i", "-t", "nfs4", "-o", options, ip + ":/", "/tmp/nfs"])
                mounted_peers.append(peer)
                from nfs_ownership import run_ownership
                report["ownership"] = {"probe_status": "FAILED", "production_authorized": False, "cases": []}
                report["ownership"]["driver_sha256"] = {
                    name: hashlib.sha256((ROOT / "scripts" / name).read_bytes()).hexdigest()
                    for name in ("check-nfs-boundaries.py", "nfs_ownership.py", "nfs_binding.py", "nfs_custody.py", "nfs_enrollment.py")}
                run_ownership(run, execute, spawn, output, client, peer, server,
                              gate, evidence, qualification_gate, qualification, mounted_peers, report["ownership"], restore)
            if args.coordinator_death:
                if args.death_scope == "separate-exports":
                    from nfs_exports import prepare
                    report["separate_exports"] = {"passed": False}
                    prepare(run, execute, server, client, ip, options, extra_mounts, report["separate_exports"])
                from nfs_runtime import run_runtime
                artifact_hashes = dict(report["artifacts"])
                artifact_hashes.update({"qualification-" + c["profile"]: c["binary_sha256"] for c in report["baseline"]["cases"]})
                report["coordinator_death"] = {"passed": False, "cases": [],
                    "driver_sha256": {name: hashlib.sha256((ROOT / "scripts" / name).read_bytes()).hexdigest()
                                      for name in ("check-nfs-boundaries.py", "nfs_runtime.py", "nfs_death.py", "nfs_bootstrap_state.py", "nfs_publication.py", "nfs_both.py", "nfs_exports.py", "nfs_binding.py")}}
                completed = run_runtime(run, execute, spawn, restore, server, output, client,
                                        artifact_hashes, report["coordinator_death"]["cases"], death_only=True,
                                        death_scope=args.death_scope or "claim-copy-verify")
                report["coordinator_death"].update(completed)
                complete = (len(report["coordinator_death"]["cases"]) == 8 if args.death_scope in {"bootstrap-source-read", "bootstrap-existing-state"}
                            else len(report["coordinator_death"]["cases"]) == 24 if args.death_scope in {"both-nfs", "separate-exports"}
                            else len(report["coordinator_death"]["cases"]) == 12 if args.death_scope == "publication-manifest"
                            else 12 <= len(report["coordinator_death"]["cases"]) <= 18)
                assert report["coordinator_death"]["passed"] or complete, "NFS coordinator-death matrix interrupted; inspect cases"
                # A fully observed ownership defect remains a failed matrix.
                # Run retained regressions after safe case cleanup, then fail.

            if args.shutdown:
                from nfs_runtime import run_runtime
                artifact_hashes = dict(report["artifacts"])
                artifact_hashes.update({"qualification-" + c["profile"]: c["binary_sha256"] for c in report["baseline"]["cases"]})
                report["shutdown"] = {"passed": False, "cases": [],
                    "driver_sha256": {name: hashlib.sha256((ROOT / "scripts" / name).read_bytes()).hexdigest()
                                      for name in ("check-nfs-boundaries.py", "nfs_runtime.py", "nfs_shutdown.py", "nfs_binding.py")}}
                completed = run_runtime(run, execute, spawn, restore, server, output, client,
                                        artifact_hashes, report["shutdown"]["cases"], shutdown_only=True)
                report["shutdown"].update(completed)
                assert report["shutdown"]["passed"], "NFS shutdown qualification failed; inspect cases"
            if args.runtime:
                from nfs_runtime import run_runtime
                artifact_hashes = dict(report["artifacts"])
                artifact_hashes.update({"qualification-" + c["profile"]: c["binary_sha256"] for c in report["baseline"]["cases"]})
                report["runtime"] = {"passed": False, "cases": []}
                completed = run_runtime(run, execute, spawn, restore, server, output, client, artifact_hashes, report["runtime"]["cases"], long_only=args.long_outages_only)
                report["runtime"]["passed"] = completed["passed"]
                if not report["runtime"]["passed"]:
                    raise RuntimeError("NFS Rust runtime qualification failed; inspect cases")
        # Local instance state must refuse NFS in BOTH builds, before source/SQLite.
        # All paths below belong to this disposable fixture, not user storage.
        execute("mkdir /tmp/nfs/instance-state; chmod 700 /tmp/nfs/instance-state", "1000:1000")
        assert execute("stat -f -c %t /tmp/nfs/instance-state").stdout.strip() == "6969"
        bad_state = dict(config, source_root="/tmp/instance-source-must-not-be-opened",
                         state_database="/tmp/nfs/instance-state/jobs.sqlite")
        path = output / "nfs-state-config.json"
        path.write_text(json.dumps(bad_state), encoding="utf-8")
        run(["cp", str(path), client + ":/tmp/nfs-state-config.json"])
        report["local_ownership"] = {"passed": False, "cases": [],
            "driver_sha256": {name: hashlib.sha256((ROOT / "scripts" / name).read_bytes()).hexdigest()
                              for name in ("check-nfs-boundaries.py", "nfs_baseline.py", "nfs_binding.py")}}
        builds = [("production", evidence, "/tmp/")]
        if qualification:
            builds.append(("nfs-qualification", qualification, "/tmp/qualification-"))
        for mode, build_evidence, prefix in builds:
            for profile in ("debug", "release"):
                artifact = next(a for a in build_evidence["profiles"][profile]["artifacts"] if not a["test"])
                assert execute("sha256sum " + prefix + profile).stdout.split()[0] == artifact["sha256"]
                for command in ("", "--initialize-source ", "--transfer-one "):
                    started = time.monotonic()
                    suffix = " 1" if command.startswith("--transfer-one") else ""
                    result = execute("LD_BIND_NOW=1 " + prefix + profile + " " + command +
                                     "/tmp/nfs-state-config.json" + suffix, "1000:1000", check=False)
                    elapsed = time.monotonic() - started
                    assert result.returncode != 0 and elapsed < 10
                    expected = "instance state filesystem" if mode == "nfs-qualification" else "filesystem not qualified"
                    assert expected in result.stderr, result.stderr
                    assert execute("test -z \"$(ls -A /tmp/nfs/instance-state)\" && test ! -e /tmp/instance-source-must-not-be-opened",
                                   "1000:1000", check=False).returncode == 0
                    report["local_ownership"]["cases"].append({"build": mode, "profile": profile,
                        "command": command.strip() or "service", "binary_sha256": artifact["sha256"],
                        "elapsed_seconds": round(elapsed, 3), "stderr": result.stderr.strip(),
                        "passed": True, "state_empty": True, "source_absent": True})
        report["local_ownership"]["passed"] = True
        from nfs_state_layout import qualify as qualify_state_layout
        report["sqlite_state_layout"] = qualify_state_layout(
            run, execute, spawn, restore, server, client, output, config, builds, extra_mounts)
        # Model the actual inherited open-file-description lock with OS tools.
        # Child holds fd 9 after coordinator death; no Rust effects are claimed.
        holder = spawn("exec 9<>/tmp/nfs/source/.file-mover/coordinator.lock; flock -xn 9; echo $$ >/tmp/local/parent.pid; /bin/sh -c 'echo $$ >/tmp/local/child.pid; while test ! -e /tmp/local/release-lock; do sleep 0.2; done' & wait", "inherited-lock")
        await_file("/tmp/local/child.pid")
        execute("kill -KILL $(cat /tmp/local/parent.pid)", "1000:1000")
        holder.wait(timeout=10)
        collision = execute("exec 9<>/tmp/nfs/source/.file-mover/coordinator.lock; flock -xn 9", "1000:1000", check=False)
        assert collision.returncode != 0
        execute("touch /tmp/local/release-lock", "1000:1000")
        for _ in range(30):
            if execute("exec 9<>/tmp/nfs/source/.file-mover/coordinator.lock; flock -xn 9", "1000:1000", check=False).returncode == 0:
                break
            time.sleep(0.2)
        else:
            raise RuntimeError("inherited source lock not released")
        report["checks"]["inherited_lock"] = "Parent death retained lock; child exit released it"
        interrupted = spawn("exec 9<>/tmp/nfs/source/.file-mover/coordinator.lock; flock -xn 9; echo $$ >/tmp/local/interrupted.pid; while test ! -e /tmp/local/interrupt-go; do sleep 0.2; done; exec stat /tmp/nfs/source", "interrupted-worker")
        await_file("/tmp/local/interrupted.pid")
        run(["exec", server, "rpc.nfsd", "0"])
        execute("touch /tmp/local/interrupt-go", "1000:1000")
        probe = spawn("echo $$ >/tmp/local/probe.pid; stat -c '%d:%i:%u:%a' /tmp/nfs/source /tmp/nfs/source/.file-mover", "outage-stat")
        await_file("/tmp/local/probe.pid")
        time.sleep(3)
        assert probe.poll() is None, "hard mount unexpectedly returned during outage"
        startup = spawn("echo $$ >/tmp/local/startup.pid; exec /tmp/release /tmp/local/config.json", "outage-startup")
        await_file("/tmp/local/startup.pid")
        time.sleep(3)
        assert startup.poll() is None, "startup unexpectedly returned during outage"
        assert interrupted.poll() is None, "assigned hard-mount operation unexpectedly returned"
        if args.isolated_startup:
            children = execute("pid=$(cat /tmp/local/startup.pid); for task in /proc/$pid/task/*/children; do cat $task; done", "1000:1000").stdout.split()
            assert len(children) == 1, "startup must have exactly one bounded bootstrap child"
            report["checks"]["bootstrap_children_before_signal"] = len(children)
            observed_at = time.monotonic()
            lifecycle = execute("LD_BIND_NOW=1 /tmp/release --status /tmp/local/config.json", "1000:1000")
            local_status = json.loads(lifecycle.stdout)
            assert local_status["phase"] == "Starting" and len(local_status["workers"]) == 1
            elapsed = time.monotonic() - observed_at
            assert elapsed < 5
            report["checks"]["blocked_bootstrap_local_status"] = {
                "elapsed_seconds": round(elapsed, 3), "snapshot": local_status,
                "scope": "Local controller while actual hard-NFS bootstrap is pending; no SQLite/readiness"}
            # A TCP listener may exist, but no HTTP readiness is served yet.
            health = spawn("exec /bin/bash -c 'exec 3<>/dev/tcp/127.0.0.1/19876; printf \"GET /healthz HTTP/1.1\\r\\nHost: localhost\\r\\n\\r\\n\" >&3; cat <&3'", "startup-health")
            time.sleep(1)
            assert health.poll() is None, "startup served an HTTP response before custody"
        execute("kill -TERM $(cat /tmp/local/startup.pid)", "1000:1000")
        time.sleep(1)
        if args.isolated_startup:
            assert startup.wait(timeout=5) == 0
            assert execute("test ! -e /proc/" + children[0], "1000:1000", check=False).returncode == 0
            assert execute("test ! -e /tmp/local/state/jobs.sqlite", "1000:1000", check=False).returncode == 0
            health.wait(timeout=5)
            report["checks"]["isolated_startup"] = "SIGTERM ended service and confirmed bootstrap child exit before server restoration; no SQLite or readiness"
        report["checks"]["startup_sigterm"] = {"exit_observed_before_restore": startup.poll() is not None}
        execute("kill -KILL $(cat /tmp/local/interrupted.pid)", "1000:1000")
        time.sleep(1)
        report["checks"]["kill_during_outage"] = {"exit_observed_before_restore": interrupted.poll() is not None}
        report["checks"]["outage"] = "Metadata and source startup remained pending at 3-second observations"
        restore()
        assert probe.wait(timeout=45) == 0
        assert (startup.wait(timeout=45) == 0) == args.isolated_startup
        assert interrupted.wait(timeout=45) != 0
        assert execute("exec 9<>/tmp/nfs/source/.file-mover/coordinator.lock; flock -xn 9", "1000:1000", check=False).returncode == 0
        for _, log in tasks:
            log.flush()
        assert (output / "outage-stat.log").read_text() == before
        report["root_identity_after"] = (output / "outage-stat.log").read_text().splitlines()
        startup_log = (output / "outage-startup.log").read_text()
        assert "Ready on" not in startup_log
        if args.isolated_startup:
            assert "Source bootstrap termination requested" in startup_log
        else:
            assert "filesystem not qualified" in startup_log
        report["checks"]["restored"] = "Stable root/namespace identity; metadata recovered and source lock became available"
        assert not args.coordinator_death or report["coordinator_death"]["passed"], "NFS coordinator-death qualification failed; inspect case outcomes and required closed-guard coverage"
        report["status"] = "PASSED"
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        report["traceback"] = traceback.format_exc()
    finally:
        # Restore first: killing a task is not evidence that NFS effects ended.
        if server:
            try:
                restore()
            except Exception as error:
                report["cleanup_errors"].append(str(error))
        if client:
            for name in ("parent", "child", "probe", "startup", "interrupted"):
                try:
                    execute(f"if test -f /tmp/local/{name}.pid; then kill -KILL $(cat /tmp/local/{name}.pid) 2>/dev/null || true; fi", "1000:1000")
                except Exception as error:
                    report["cleanup_errors"].append(str(error))
        for process, log in tasks:
            try:
                process.wait(timeout=45)
            except Exception as error:
                report["cleanup_errors"].append(str(error))
            log.close()
        for target, path in reversed(extra_mounts):
            try:
                run(["exec", target, "umount", path])
            except Exception as error:
                report["cleanup_errors"].append(str(error))
        for peer in mounted_peers:
            try:
                run(["exec", peer, "umount", "/tmp/nfs"])
            except Exception as error:
                report["cleanup_errors"].append(str(error))
        if mounted:
            try:
                run(["exec", client, "umount", "/tmp/nfs"])
            except Exception as error:
                report["cleanup_errors"].append(str(error))
        if not report["cleanup_errors"]:
            if server:
                run(["exec", server, "rpc.nfsd", "0"], check=False)
                run(["exec", server, "exportfs", "-au"], check=False)
            for container in reversed(containers):
                result = run(["rm", "--force", container], check=False)
                if result.returncode:
                    report["cleanup_errors"].append(result.stderr)
            for kind, name in (("volume", volume), ("network", network)):
                if name:
                    result = run([kind, "rm", name], check=False)
                    if result.returncode:
                        report["cleanup_errors"].append(result.stderr)
        if report["cleanup_errors"]:
            report["status"] = "FAILED"
            report["recovery_resources"] = {"containers": containers, "network": network, "volume": volume}
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(f"{report['status']}: {output}", flush=True)
        if "error" in report:
            print(report["error"], flush=True)
    return 0 if report["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
