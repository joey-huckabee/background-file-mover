"""Real enrollment ENOSPC on a private, bounded tmpfs exported by the fixture.

Never fill the host filesystem. No production fault selector or manual receipt
repair is used. Retain original state and distinguish no creation from uncertain
creation. This tests NFS error handling, not block-device/power-loss durability.
"""
import hashlib
import json
import sqlite3
import time
from nfs_binding import binding_for, provision


def qualify_enrollment_storage(run, execute, spawn, output, client, server, ip, options,
                               extra_mounts, report):
    mount = "/tmp/enrollment-space"
    export = "/exports/enrollment-space"

    def server_command(command, check=True):
        return run(["exec", server, "/bin/sh", "-eu", "-c", command], check=check)

    def observe(command, check=True):
        return execute(command, "1000:1000", check=check, target=client)

    server_command(f"mkdir {export}; mount -t tmpfs -o size=4m,nr_inodes=128,mode=1777 tmpfs {export}; "
                   f"mkdir {export}/fill; exportfs -i -o rw,sync,no_subtree_check,no_root_squash,fsid=29 '*:{export}'")
    execute("mkdir "+mount, target=client)
    run(["exec", client, "mount", "-i", "-t", "nfs4", "-o", options, ip+":/enrollment-space", mount])
    extra_mounts.append((client, mount))
    report["mounts"] = execute("cat /proc/mounts", target=client).stdout.splitlines()
    report["server_mounts"] = server_command("cat /proc/mounts").stdout.splitlines()
    assert any(f" {mount} nfs4 " in m and "vers=4.1" in m and "hard" in m for m in report["mounts"])
    assert any(f" {export} tmpfs " in m and "size=4096k" in m and "nr_inodes=128" in m
               for m in report["server_mounts"])
    assert observe("getconf GNU_LIBC_VERSION").stdout.strip() == "glibc 2.22"
    assert observe("stat -f -c %t "+mount).stdout.strip() == "6969"
    report["scope"] = "Real server tmpfs block/inode exhaustion over hard NFSv4.1; no injected fault selector, disk hardware, EIO or power-loss qualification."

    def capacity():
        # total blocks, free blocks, available blocks, total/free inodes, block size
        return [int(n) for n in server_command("stat -f -c '%b %f %a %c %d %S' "+export).stdout.split()]

    for profile in ("debug", "release"):
        binary = "/tmp/qualification-"+profile
        report.setdefault("artifacts", {})[profile] = observe("sha256sum "+binary).stdout.split()[0]
        for exhaustion in ("inodes", "blocks"):
            label = "storage-"+profile+"-"+exhaustion
            source = mount+"/"+label
            base = "/tmp/local/"+label
            observe(f"umask 077; mkdir -p {source}/.file-mover {source}/current {base}/state {base}/destination/.file-mover; "
                    f"printf 'producer-owned input' >{source}/current/data")
            source_binding = binding_for(label, True)
            destination_binding = binding_for(label+"-destination", False, "destination")
            provision(run, execute, output, client, source, source_binding)
            provision(run, execute, output, client, base+"/destination", destination_binding)
            config = {"bind": "127.0.0.1:19886", "generator_id": "fixture", "source_root": source,
                      "destination_root": base+"/destination", "state_database": base+"/state/jobs.sqlite",
                      "source_binding": source_binding, "destination_binding": destination_binding}
            local = output/(label+"-config.json")
            local.write_text(json.dumps(config))
            run(["cp", str(local), client+":"+base+"/config.json"])
            before = observe(f"stat -c '%d:%i:%u:%a' {source} {source}/.file-mover; "
                             f"sha256sum {source}/current/data {source}/.file-mover/source-binding.json "
                             f"{source}/.file-mover/coordinator.lock").stdout

            def state_snapshot(suffix):
                # The service is stopped. Copy its whole local state directory so
                # any remaining WAL accompanies the database; inspect only the copy.
                snapshot = output/(label+"-"+suffix)
                snapshot.mkdir()
                run(["cp", client+":"+base+"/state/.", str(snapshot)])
                with sqlite3.connect((snapshot/"jobs.sqlite").resolve().as_uri()+"?mode=ro", uri=True) as db:
                    assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
                    assert db.execute("SELECT COUNT(*) FROM jobs").fetchone() == (0,)
                    return db.execute("SELECT receipt,object FROM source_ownership WHERE singleton=1").fetchone()

            free = capacity()
            assert free[1] > 0 and free[4] > 0 and free[0]*free[5] == 4*1024*1024
            if exhaustion == "blocks":
                filled = server_command(f"dd if=/dev/zero of={export}/fill/blocks bs=4096", check=False)
            else:
                filled = server_command(f"i=0; while test $i -lt 256; do : >{export}/fill/inode-$i; i=$((i+1)); done", check=False)
            assert filled.returncode != 0 and "No space left on device" in filled.stderr
            full = capacity()
            assert full[1 if exhaustion == "blocks" else 4] == 0, full
            result = {"scenario_id": "SC-070", "profile": profile, "exhaustion": exhaustion,
                      "passed": False, "jobs_submitted": 0, "capacity_before": free, "capacity_full": full,
                      "fill_returncode": filled.returncode, "fill_stderr": filled.stderr}
            report["cases"].append(result)
            receipt = source+"/.file-mover/source-enrollment.json"
            try:
                failed = observe(f"LD_BIND_NOW=1 {binary} --initialize-source {base}/config.json", check=False)
                result["initialization"] = {"returncode": failed.returncode, "stderr": failed.stderr}
                assert failed.returncode != 0 and "create_receipt" in failed.stderr and "errno=28" in failed.stderr, failed.stderr
                assert "preserve original state and source for review" in failed.stderr
                prepared = state_snapshot("failed")
                assert prepared is not None and prepared[1] is None
                created = observe(f"stat -c '%d:%i:%u:%a:%s' {receipt}; sha256sum {receipt}", check=False)
                assert (created.returncode == 0) == (exhaustion == "blocks"), created.stderr
                if exhaustion == "blocks":
                    assert "enrollment_write errno=28" in failed.stderr
                    # A failed NFS write can leave different cached/client and
                    # server lengths. Neither length nor matching text authorizes
                    # adoption. Record both views; preserve the created object.
                    result["receipt_at_error"] = {"client": created.stdout,
                        "server": server_command(f"stat -c '%d:%i:%u:%a:%s' {export}/{label}/.file-mover/source-enrollment.json; "
                                                 f"sha256sum {export}/{label}/.file-mover/source-enrollment.json").stdout}
                blocked = observe(f"LD_BIND_NOW=1 {binary} {base}/config.json", check=False)
                assert blocked.returncode != 0 and "enrollment pending" in blocked.stderr, blocked.stderr
                assert state_snapshot("pending") == prepared
            finally:
                # Only our fixed filler directory inside the bounded mount.
                server_command(f"rm -f {export}/fill/blocks {export}/fill/inode-*")
            result["capacity_restored"] = capacity()
            assert result["capacity_restored"][1] > 0 and result["capacity_restored"][4] > 0
            def receipt_views():
                return {"client": observe(f"stat -c '%d:%i:%u:%a:%s' {receipt}; sha256sum {receipt}").stdout,
                        "server": server_command(f"stat -c '%d:%i:%u:%a:%s' {export}/{label}/.file-mover/source-enrollment.json; "
                                                 f"sha256sum {export}/{label}/.file-mover/source-enrollment.json").stdout}
            preserved = receipt_views() if exhaustion == "blocks" else None
            if preserved:
                for view in ("client", "server"):
                    assert preserved[view].splitlines()[0].split(":")[:4] == result["receipt_at_error"][view].splitlines()[0].split(":")[:4]
            result["receipt_before_retry"] = preserved
            retried = observe(f"LD_BIND_NOW=1 {binary} --initialize-source {base}/config.json", check=False)
            result["retry"] = {"returncode": retried.returncode, "stderr": retried.stderr}
            active = state_snapshot("retried")
            assert active[0] == prepared[0]
            if exhaustion == "blocks":
                assert retried.returncode != 0 and active[1] is None
                result["receipt_after_retry"] = receipt_views()
                assert result["receipt_after_retry"] == preserved
                result["created_receipt_preserved_for_review"] = True
            else:
                assert retried.returncode == 0 and active[1] is not None, retried.stderr
                assert observe("cat "+receipt).stdout == prepared[0]
                marker = base+"/service.pid"
                service = spawn(f"echo $$ >{marker}; exec {binary} {base}/config.json", label+"-recovered", target=client)
                try:
                    for _ in range(100):
                        assert service.poll() is None
                        if "Ready on" in (output/(label+"-recovered.log")).read_text():
                            break
                        time.sleep(0.1)
                    else:
                        raise RuntimeError("no-creation enrollment retry did not reach readiness")
                    health = observe("/bin/bash -c 'exec 3<>/dev/tcp/127.0.0.1/19886; "
                                     "printf \"GET /healthz HTTP/1.1\\r\\nHost: localhost\\r\\nConnection: close\\r\\n\\r\\n\" >&3; cat <&3'")
                    assert health.stdout.startswith("HTTP/1.1 200")
                finally:
                    if service.poll() is None:
                        pid = observe("cat "+marker).stdout.strip()
                        assert pid.isdigit()
                        observe("kill -TERM "+pid)
                    assert service.wait(timeout=30) == 0
                assert state_snapshot("stopped") == active
                result["no_creation_retry_activated_and_ready"] = True
            after = observe(f"stat -c '%d:%i:%u:%a' {source} {source}/.file-mover; "
                            f"sha256sum {source}/current/data {source}/.file-mover/source-binding.json "
                            f"{source}/.file-mover/coordinator.lock").stdout
            assert after == before
            result.update({"passed": True, "source_binding_lock_input_unchanged": True,
                           "pending_before_retry": True, "state_receipt_sha256": hashlib.sha256(prepared[0].encode()).hexdigest()})
            (output/(label+"-result.json")).write_text(json.dumps(result, indent=2)+"\n")
            print(f"NFS actual ENOSPC {profile}/{exhaustion}: PASS (retry matched creation evidence)", flush=True)
    report["passed"] = True
