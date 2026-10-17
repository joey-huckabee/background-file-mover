"""Disposable mounted-file and wrong-owner SQLite state admission checks."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import time


def qualify(run, execute, spawn, restore, server, client, output, config, builds, extra_mounts):
    report = {"passed": False, "cases": [], "fixtures": [], "driver_sha256": hashlib.sha256(
        Path(__file__).read_bytes()).hexdigest(),
        "scope": "Owned local state parent; actual per-file NFS bind mounts with server stopped, and foreign UID files; all three effect commands, both build modes/profiles. No hostile concurrent mount mutation or production NFS approval."}
    owned_mounts = []
    try:
        def snapshot(state, candidate, label):
            metadata = execute(f"stat -c '%d:%i:%u:%g:%a:%h' {state} {state}/jobs.sqlite {candidate}", "1000:1000").stdout
            hashes = []
            # Engine-side copy can inspect a deliberately foreign-owned 0600 file
            # without granting DAC/CHOWN capabilities to the mover's container.
            for index, remote in enumerate((state + "/jobs.sqlite", candidate)):
                local = output / f"{label}-{index}.snapshot"
                run(["cp", client + ":" + remote, str(local)])
                hashes.append(hashlib.sha256(local.read_bytes()).hexdigest())
            return {"sha256": hashes, "metadata": metadata.splitlines()}

        execute("printf 'preserve NFS state sentinel' >/tmp/nfs/sqlite-state-sentinel; chmod 600 /tmp/nfs/sqlite-state-sentinel", "1000:1000")
        sentinel = execute("sha256sum /tmp/nfs/sqlite-state-sentinel", "1000:1000").stdout.split()[0]
        cases = []
        for kind in ("foreign-uid", "nfs-file-mount"):
            suffixes = ("", "-wal", "-shm", "-journal") + (("instance.lock", "control.sock") if kind == "nfs-file-mount" else ())
            for index, suffix in enumerate(suffixes):
                state = f"/tmp/local/sqlite-{kind}-{index}"
                filename = suffix if suffix in ("instance.lock", "control.sock") else "jobs.sqlite" + suffix
                candidate = state + "/" + filename
                execute(f"umask 077; mkdir {state}; printf 'preserve local database' >{state}/jobs.sqlite; printf 'preserve state file' >{candidate}", "1000:1000")
                if kind == "foreign-uid":
                    local_file = output / f"foreign-uid-{index}.content"
                    local_file.write_bytes(b"preserve foreign-owned state file")
                    execute(f"rm {candidate}", "1000:1000")
                    run(["cp", str(local_file), client + ":" + candidate])
                    execute(f"chmod 711 /tmp/local {state}", "1000:1000")
                    try:
                        execute(f"chmod 600 {candidate}")
                    finally:
                        execute(f"chmod 700 /tmp/local {state}", "1000:1000")
                    assert execute(f"stat -c '%u:%a' {candidate}", "1000:1000").stdout.strip() == "0:600"

                else:
                    execute(f"chmod 711 /tmp/local {state}", "1000:1000")
                    try:
                        execute(f"mount --bind /tmp/nfs/sqlite-state-sentinel {candidate}")
                        extra_mounts.append((client, candidate))
                        owned_mounts.append(candidate)
                    finally:
                        execute(f"chmod 700 /tmp/local {state}", "1000:1000")
                    assert execute(f"stat -f -c %t {candidate}", "1000:1000").stdout.strip() == "6969"
                c = dict(config, state_database=state + "/jobs.sqlite", source_root="/tmp/sqlite-source-must-remain-absent")
                local = output / f"sqlite-{kind}-{index}.json"
                local.write_text(json.dumps(c), encoding="utf-8")
                remote = f"/tmp/sqlite-{kind}-{index}.json"
                run(["cp", str(local), client + ":" + remote])
                before = snapshot(state, candidate, f"sqlite-{kind}-{index}-before")
                cases.append((kind, suffix, state, candidate, remote, before))
        try:
            # Refusal must use local mountinfo, without even a remote stat/open.
            run(["exec", server, "rpc.nfsd", "0"])
            for kind, suffix, state, candidate, remote, before in cases:
                for mode, evidence, prefix in builds:
                    for profile in ("debug", "release"):
                        artifact = next(a for a in evidence["profiles"][profile]["artifacts"] if not a["test"])
                        for command in ("", "--initialize-source ", "--transfer-one "):
                            label = f"sqlite-{len(report['cases'])}"
                            tail = " 1" if command.startswith("--transfer-one") else ""
                            process = spawn(f"echo $$ >/tmp/local/{label}.pid; exec {prefix}{profile} {command}{remote}{tail}", label)
                            started = time.monotonic()
                            try:
                                status = process.wait(timeout=8)
                            except subprocess.TimeoutExpired:
                                restore()
                                execute(f"kill -KILL $(cat /tmp/local/{label}.pid) 2>/dev/null || true", "1000:1000")
                                process.wait(timeout=10)
                                raise AssertionError("SQLite state refusal touched blocked NFS")
                            elapsed = time.monotonic() - started
                            expected = ("local ownership/control file is a mount point" if suffix in ("instance.lock", "control.sock")
                                        else "SQLite state file is a mount point") if kind == "nfs-file-mount" else "unsafe SQLite state file"
                            diagnostic = (output / (label + ".log")).read_text()
                            assert status != 0 and elapsed < 8 and expected in diagnostic, diagnostic
                            report["cases"].append({"kind": kind, "sqlite_suffix": suffix, "build": mode,
                                "profile": profile, "command": command.strip() or "service", "binary_sha256": artifact["sha256"],
                                "elapsed_seconds": round(elapsed, 3), "stderr": diagnostic.strip(), "passed": True})
                print(f"SQLite state {kind} {suffix or 'database'}: PASS", flush=True)
        finally:
            restore()
        for kind, suffix, state, candidate, remote, before in cases:
            after = snapshot(state, candidate, "sqlite-" + str(len(report["fixtures"])) + "-after")
            assert before == after, "state bytes/identity/mode changed during refusal"
            parent_fs = execute(f"stat -f -c %t {state}", "1000:1000").stdout.strip()
            assert parent_fs != "6969"
            report["fixtures"].append({"kind": kind, "sqlite_suffix": suffix,
                "local_parent": state, "parent_filesystem_magic": parent_fs,
                "candidate": candidate, "before_hashes_and_metadata": before,
                "after_hashes_and_metadata": after, "preserved": True})
            absent_control = "" if suffix == "control.sock" else f"test ! -e {state}/control.sock && "
            assert execute(absent_control + "test ! -e /tmp/sqlite-source-must-remain-absent", "1000:1000", check=False).returncode == 0
        assert execute("sha256sum /tmp/nfs/sqlite-state-sentinel", "1000:1000").stdout.split()[0] == sentinel
        report["original_bytes_identity_permissions_preserved"] = True
        report["passed"] = True
        return report
    finally:
        # Restore RPC service before unmounting, including failed setup/cases.
        restore()
        for candidate in reversed(owned_mounts):
            state = str(PurePosixPath(candidate).parent)
            # Fixture root has SYS_ADMIN but no DAC override. Permissions are
            # private during every mover run; traversal is only for setup/cleanup.
            execute(f"chmod 711 /tmp/local {state}", "1000:1000")
            try:
                run(["exec", client, "umount", candidate])
                extra_mounts.remove((client, candidate))
            finally:
                execute(f"chmod 700 /tmp/local {state}", "1000:1000")
