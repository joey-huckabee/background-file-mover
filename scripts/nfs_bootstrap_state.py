"""Owned enrolled/bootstrap fixture evidence; snapshots never open SQLite."""
import hashlib


def file_evidence(execute, paths):
    # Paths are fixed, whitespace-free descendants of the owning fixture.
    assert all(p.startswith("/tmp/") and all(c.isalnum() or c in "/._-" for c in p) for p in paths)
    command = ("for f in " + " ".join(paths) + "; do if test -e \"$f\"; then "
               "stat -c '%n:%d:%i:%u:%g:%a:%h:%s:%y:%z' \"$f\"; sha256sum \"$f\"; "
               "else printf 'absent:%s\\n' \"$f\"; fi; done")
    return execute(command, "1000:1000").stdout


def destination_evidence(case, execute):
    return file_evidence(execute, [
        case.destination + "/.file-mover/destination-binding.json",
        case.destination + "/1/.staging/1.part", case.destination + "/1/.staging/2.part",
        case.destination + "/1/nested/data.bin", case.destination + "/1/COMMITTED.json"])


def local_evidence(case, execute, both_nfs=False):
    database = case.base + "/state/jobs.sqlite"
    if both_nfs:
        return file_evidence(execute, [database + s for s in ("", "-wal", "-shm", "-journal")] + [case.config_path])
    return file_evidence(execute, [database + s for s in ("", "-wal", "-shm", "-journal")] + [
        case.config_path, case.destination + "/.file-mover/destination-binding.json",
        case.destination + "/1/.staging/1.part", case.destination + "/1/.staging/2.part",
        case.destination + "/1/nested/data.bin",
        case.destination + "/1/COMMITTED.json"])


def receipt_evidence(case, execute):
    return file_evidence(execute, [case.source + "/.file-mover/" + name for name in (
        "source-enrollment.json", "source-binding.json", "coordinator.lock")])


def source_evidence(case, execute):
    return receipt_evidence(case, execute) + file_evidence(execute, [
        case.source + "/current/nested/data.bin", case.source + "/.file-mover/1-0/data"])


def partial_evidence(case, execute):
    path = case.destination + "/1/.staging/1.part"
    return execute(f"stat -c '%d:%i:%s' {path}; sha256sum {path}", "1000:1000").stdout


def prepare(case, execute, status, both_nfs=False):
    result = case.result
    result["bootstrap_state_kind"] = "populated" if case.point == "bootstrap_populated" else "enrolled-empty"
    if case.point == "bootstrap_populated":
        case.start(True, pause_point="copy_chunk")
        code, accepted = case.request("POST", "/api/v2/jobs", case.body)
        assert code == 202 and accepted["job_id"] == "1" and accepted["source_paths_released"]
        result["seed_acceptance"] = [code, accepted]
        execute(f"printf 'next recording' >{case.source}/current/nested/data.bin", "1000:1000")
        case.await_pause("copy_chunk")
        result["seed_worker"] = dict(result["paused_worker"])
        result["seed_job_status"] = case.request("GET", "/api/v2/jobs/1")[1]
        assert result["seed_job_status"]["state"] == "Claimed"
        assert result["seed_job_status"]["details"]["files"][0]["attempt"] == 1
        assert result["seed_job_status"]["details"]["files"][0]["transfer_phase"] == "Intent"
        partial = partial_evidence(case, execute)
        assert partial.splitlines()[0].split(":")[-1] == "1048576"
        assert partial.splitlines()[1].split()[0] == hashlib.sha256(bytes(1048576)).hexdigest()
        result["seed_partial"] = partial
        # Kill the coordinator first: a live coordinator must not react to the
        # seed worker's death, retry and allocate an unreceipted second attempt.
        coordinator = case.service_pid()
        case.signal(coordinator, "KILL")
        assert case.service.wait(timeout=10) == 137
        result["seed_coordinator_pid"] = coordinator
        result["seed_coordinator_exited_before_worker_kill"] = True
        case.signal(case.worker, "KILL")
        result["seed_worker_exit"] = case.await_exit(case.worker)
        case.worker = None
        status(case, "NoActiveOwner")
        names = execute(f"ls -A1 {case.destination}/1/.staging", "1000:1000").stdout
        assert names == "1.part\n", "seed left an unintended allocation"
        result["seed_staging_names"] = names.splitlines()
        execute(f"test -s {case.base}/state/jobs.sqlite-wal", "1000:1000")
        result["retained_wal_before_bootstrap"] = True
    else:
        status(case, "NoActiveOwner")
    result["database_identity_before"] = execute(f"stat -c '%d:%i' {case.base}/state/jobs.sqlite", "1000:1000").stdout
    result["bootstrap_local_before"] = local_evidence(case, execute, both_nfs)
    result["bootstrap_source_before"] = source_evidence(case, execute)
    result["enrollment_receipt_before"] = receipt_evidence(case, execute)
    if both_nfs:
        result["bootstrap_destination_before"] = destination_evidence(case, execute)
        path = case.source + ("/.file-mover/1-0/data" if case.point == "bootstrap_populated" else "/current/nested/data.bin")
        result["source_payload_identity_before"] = execute(f"stat -c '%d:%i:%s' {path}", "1000:1000").stdout
        result["destination_binding_before"] = file_evidence(execute, [case.destination + "/.file-mover/destination-binding.json"])


def recovered_both(case, execute):
    result = case.result
    result["source_payload_identity_after"] = execute(f"stat -c '%d:%i:%s' {case.source}/.file-mover/1-0/data", "1000:1000").stdout
    assert result["source_payload_identity_after"] == result["source_payload_identity_before"]
    result["destination_binding_after"] = file_evidence(execute, [case.destination + "/.file-mover/destination-binding.json"])
    assert result["destination_binding_after"] == result["destination_binding_before"]
    result["original_source_inode_preserved"] = True
    result["original_destination_binding_preserved"] = True
