"""Observe ownership gaps using exact audited services in an owned NFS fixture.

A completed diagnostic is not approval of the measured unsafe behavior. No jobs
are submitted while overlapping coordinators run. All state databases are local.
"""
import hashlib
import json
import time
from nfs_binding import binding_for, provision


def run_ownership(run, execute, spawn, output, client, peer, server,
                  gate, evidence, qualification_gate, qualification, mounted_peers, report):
    services = []
    holders = []
    cases = report["cases"]

    def observe(target, script, check=True):
        return execute(script, "1000:1000", check=check, target=target)

    def start(target, label, profile, source, port, state_label=None, production=False):
        base = "/tmp/local/ownership-" + (state_label or label)
        observe(target, f"umask 077; mkdir -p {base}/state {base}/destination/.file-mover")
        assert observe(target, f"stat -f -c %t {base}/state").stdout.strip() != "6969"
        config = {"bind": f"127.0.0.1:{port}", "generator_id": "fixture", "source_root": source,
                  "destination_root": base + "/destination", "state_database": base + "/state/jobs.sqlite"}
        config["source_binding"] = binding_for("ownership-" + profile, True)
        before_db = observe(target, "sha256sum " + config["state_database"], check=False)
        local = output / ("ownership-" + label + "-config.json")
        local.write_text(json.dumps(config))
        run(["cp", str(local), target + ":" + base + "/config.json"])
        binary = "/tmp/ownership-" + ("production-" if production else "qualification-") + profile
        marker = "/tmp/local/ownership-" + label + ".pid"
        process = spawn(f"echo $$ >{marker}; exec {binary} {base}/config.json", "ownership-" + label, target=target)
        service = {"target": target, "process": process, "marker": marker, "label": label,
                   "database": config["state_database"], "port": port,
                   "config_sha256": hashlib.sha256(local.read_bytes()).hexdigest()}
        services.append(service)
        for _ in range(100):
            log = (output / ("ownership-" + label + ".log")).read_text()
            if "Ready on" in log:
                assert process.poll() is None
                reply = observe(target, f"/bin/bash -c 'exec 3<>/dev/tcp/127.0.0.1/{port}; "
                                "printf \"GET /healthz HTTP/1.1\\r\\nHost: localhost\\r\\nConnection: close\\r\\n\\r\\n\" >&3; cat <&3'")
                head, body = reply.stdout.replace("\r\n", "\n").split("\n\n", 1)
                assert head.split()[1] == "200"
                service["response"] = json.loads(body)
                service["ready"] = True
                break
            if process.poll() is not None:
                assert process.returncode != 0
                assert "Error:" in log and "No such file" not in log
                if before_db.returncode == 0:
                    assert observe(target, "sha256sum " + service["database"]).stdout == before_db.stdout
                    service["sqlite_unchanged"] = True
                else:
                    assert observe(target, "test ! -e " + service["database"], check=False).returncode == 0
                service["ready"] = False
                break
            time.sleep(0.2)
        else:
            raise RuntimeError("ownership startup outcome unconfirmed: " + label)
        service["log"] = log
        return service

    def stop(service):
        process = service["process"]
        if process.poll() is None:
            pid = observe(service["target"], "cat " + service["marker"]).stdout.strip()
            assert pid.isdigit()
            observe(service["target"], "kill -TERM " + pid)
            assert process.wait(timeout=30) == 0

    def snapshot(service):
        return {k: service[k] for k in ("label", "database", "config_sha256", "ready", "log")}

    try:
        report["clients"] = []
        for target in (client, peer):
            namespaces = observe(target, "readlink /proc/self/ns/net /proc/self/ns/mnt").stdout.splitlines()
            mounts = observe(target, "cat /proc/mounts").stdout.splitlines()
            assert any(" /tmp/nfs " in m and "vers=4.1" in m and "hard" in m and "local_lock=none" in m for m in mounts)
            assert observe(target, "getconf GNU_LIBC_VERSION").stdout.strip() == "glibc 2.22"
            report["clients"].append({"container": target, "namespaces": namespaces, "mounts": mounts})
        assert all(report["clients"][0]["namespaces"][i] != report["clients"][1]["namespaces"][i] for i in (0, 1))
        info = run(["exec", server, "/bin/sh", "-eu", "-c",
                    "for file in /proc/fs/nfsd/clients/*/info; do echo CLIENT_INFO; cat $file; done"]).stdout
        assert info.count("CLIENT_INFO") >= 2, "server did not expose two NFS client identities"
        report["server_client_info"] = info

        for profile in ("debug", "release"):
            for mode, directory, gate_report in (("production", gate, evidence), ("qualification", qualification_gate, qualification)):
                artifact = next(a for a in gate_report["profiles"][profile]["artifacts"] if not a["test"])
                path = directory / artifact["name"]
                assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
                for target in (client, peer):
                    remote = "/tmp/ownership-" + mode + "-" + profile
                    run(["cp", str(path), target + ":" + remote])
                    execute("chmod 755 " + remote, target=target)
                    assert observe(target, "sha256sum " + remote).stdout.split()[0] == artifact["sha256"]
                report.setdefault("artifacts", {})[mode + "-" + profile] = artifact["sha256"]

            source = "/tmp/nfs/ownership-" + profile + "/source"
            observe(client, f"umask 077; mkdir -p {source}/.file-mover; printf 'shared export witness' >{source}/witness")
            provision(run, execute, output, client, source, binding_for("ownership-" + profile, True))
            identities = [observe(target, f"stat -c '%i:%u:%a' {source} {source}/.file-mover; sha256sum {source}/witness").stdout
                          for target in (client, peer)]
            assert identities[0] == identities[1]
            owner = start(client, profile + "-owner", profile, source, 19880)
            assert owner["ready"]
            same = start(client, profile + "-same", profile, source, 19881)
            assert not same["ready"], "same-client singleton control failed"
            other = start(peer, profile + "-peer", profile, source, 19880)
            case = {"profile": profile, "scenario_id": "SC-053", "probe_completed": True,
                    "shared_root_observations": identities, "owner": snapshot(owner), "same_client": snapshot(same),
                    "other_client": snapshot(other), "cross_client_startup_excluded": not other["ready"],
                    "jobs_submitted": 0}
            cases.append(case)
            stop(other)
            stop(owner)

            # Positive control: a regular file opened RDWR must have observable
            # remote lock exclusion. This is an OS probe, not a Rust fence.
            lockfile = source + "/.file-mover/regular-lock-control"
            release = "/tmp/local/ownership-" + profile + "-release"
            ready = "/tmp/local/ownership-" + profile + "-lock-ready"
            holder = spawn(f"umask 077; exec 9<>{lockfile}; flock -xn 9; echo $$ >{ready}; "
                           f"while test ! -e {release}; do sleep 0.2; done", "ownership-" + profile + "-file-lock", target=client)
            holders.append((holder, release))
            for _ in range(30):
                if observe(client, "test -f " + ready, check=False).returncode == 0:
                    break
                assert holder.poll() is None
                time.sleep(0.2)
            else:
                raise RuntimeError("regular-file control did not acquire lock")
            conflict = observe(peer, f"exec 9<>{lockfile}; flock -xn 9", check=False)
            assert conflict.returncode == 1 and not conflict.stderr
            observe(client, ": >" + release)
            assert holder.wait(timeout=15) == 0
            assert observe(peer, f"exec 9<>{lockfile}; flock -xn 9").returncode == 0
            case["regular_file_remote_exclusion_control"] = True
            (output / ("ownership-" + profile + "-cross-client-result.json")).write_text(json.dumps(case, indent=2) + "\n")
            print(f"NFS ownership {profile}: same-client excluded; cross-client excluded={case['cross_client_startup_excluded']}; regular-file remote control passed", flush=True)

        # With all peer services stopped, remove only its own mount. Root owns
        # this empty mount point, so it may chmod it without adding CAP_CHOWN.
        run(["exec", peer, "umount", "/tmp/nfs"])
        mounted_peers.remove(peer)
        execute("chmod 1777 /tmp/nfs", target=peer)
        for profile in ("debug", "release"):
            source = "/tmp/nfs/ownership-" + profile + "/source"
            observe(peer, f"umask 077; mkdir -p {source}/.file-mover")
            # Even a copied matching marker must not authorize local fallback.
            provision(run, execute, output, peer, source, binding_for("ownership-" + profile, True))
            filesystem = observe(peer, "stat -f -c %t " + source).stdout.strip()
            assert filesystem != "6969"
            fallback = start(peer, profile + "-fallback", profile, source, 19880, state_label=profile + "-peer")
            previous = next(c["other_client"] for c in cases if c["profile"] == profile and c["scenario_id"] == "SC-053")
            assert fallback["config_sha256"] == previous["config_sha256"]
            assert not fallback["ready"] and fallback.get("sqlite_unchanged")
            case = {"profile": profile, "scenario_id": "SC-054", "probe_completed": True,
                    "filesystem_after_unmount": filesystem, "same_config_and_state_database": True,
                    "missing_mount_startup_rejected": not fallback["ready"], "qualification": snapshot(fallback), "jobs_submitted": 0}
            cases.append(case)
            stop(fallback)
            # The normal production build must still reject NFS (owning runner's
            # control), but an underlying local filesystem is currently allowed.
            production = start(peer, profile + "-fallback-production", profile, source, 19880, production=True)
            case["production_local_startup_rejected"] = not production["ready"]
            assert not production["ready"]
            case["production"] = snapshot(production)
            stop(production)
            (output / ("ownership-" + profile + "-missing-mount-result.json")).write_text(json.dumps(case, indent=2) + "\n")
            print(f"NFS missing-mount {profile}: qualification rejected={case['missing_mount_startup_rejected']}; production rejected={case['production_local_startup_rejected']}", flush=True)
        report["probe_status"] = "PASSED"
        report["protection_complete"] = all(c.get("cross_client_startup_excluded", c.get("missing_mount_startup_rejected", False)) for c in cases)
    finally:
        # No outages are introduced by these probes. Never abandon live services
        # before the owning runner attempts normal unmount and resource removal.
        for holder, release in holders:
            observe(client, ": >" + release)
            holder.wait(timeout=30)
        for service in reversed(services):
            stop(service)
        report["service_logs"] = {s["label"]: (output / ("ownership-" + s["label"] + ".log")).read_text() for s in services}
