"""Evidence for selected file/manifest publication deaths; no SQLite inspection."""
import hashlib


def objects(case, execute):
    root = case.destination + "/1/"
    names = (".staging/1.part", "nested/data.bin", ".staging/COMMITTED.part", "COMMITTED.json")
    # All names come from fixed ASCII fixture paths, never user input.
    assert all(c.isalnum() or c in "/._-" for c in root)
    command = ""
    for name in names:
        path = root + name
        command += (f"if test -e {path}; then printf '{name} '; "
                    f"stat -c '%d:%i:%h:%s' {path}; sha256sum {path}; "
                    f"else printf '{name} absent\\n'; fi; ")
    lines = iter(execute(command, "1000:1000").stdout.splitlines())
    result = {}
    for line in lines:
        name, value = line.split()
        if value == "absent":
            result[name] = None
        else:
            device, inode, links, size = map(int, value.split(":"))
            result[name] = dict(device=device, inode=inode, links=links, size=size,
                                sha256=next(lines).split()[0])
    assert set(result) == set(names)
    return result


def same_object(observed, expected):
    assert observed is not None
    assert all(observed[k] == expected[k] for k in ("device", "inode", "size", "sha256")), (observed, expected)


def before(case, execute):
    value = objects(case, execute)
    case.result["publication_before_outage"] = value
    details = case.result["status_before_outage"]["details"]
    assert details["source_cleanup_enabled"] is False
    assert details["files"][0]["attempt"] == 1
    assert details["files"][0]["transfer_phase"] == ("Published" if case.point == "manifest_link" else "PublishIntent")
    payload = value["nested/data.bin"] if case.point == "manifest_link" else value[".staging/1.part"]
    assert payload["sha256"] == hashlib.sha256(bytes(2 * 1048576) + b"0123456789abcdefg").hexdigest()
    assert payload["size"] == 2 * 1048576 + 17
    if case.point == "publish":
        assert payload["links"] == 1 and value["nested/data.bin"] is None
    elif case.point == "file_link":
        assert payload == value["nested/data.bin"] and payload["links"] == 2
    else:
        assert payload["links"] == 1 and value[".staging/1.part"] is None
        assert details["manifest_phase"] == 3
        assert value["COMMITTED.json"] == value[".staging/COMMITTED.part"]
        assert value["COMMITTED.json"]["links"] == 2
        case.result["manifest_hash_before_outage"] = value["COMMITTED.json"]["sha256"]
    if case.point != "manifest_link":
        assert value["COMMITTED.json"] is None and value[".staging/COMMITTED.part"] is None
    case.result["publication_scenario_id"] = {"publish": "SC-039", "file_link": "SC-050", "manifest_link": "SC-040"}[case.point]


def after_exit(case, execute):
    value = objects(case, execute)
    case.result["publication_after_old_exit"] = value
    original = case.result["publication_before_outage"]
    payload = original["nested/data.bin"] if case.point == "manifest_link" else original[".staging/1.part"]
    present = [value[n] for n in (".staging/1.part", "nested/data.bin") if value[n] is not None]
    assert present
    for obj in present:
        same_object(obj, payload)
        assert obj["links"] == len(present)
    if case.point in {"file_link", "manifest_link"}:
        assert value["nested/data.bin"] is not None
    if case.point == "manifest_link":
        same_object(value["COMMITTED.json"], original["COMMITTED.json"])
        aliases = [value[n] for n in (".staging/COMMITTED.part", "COMMITTED.json") if value[n] is not None]
        for obj in aliases:
            same_object(obj, original["COMMITTED.json"])
            assert obj["links"] == len(aliases)
    else:
        # A worker has no SQLite handle or authority to start the manifest step.
        assert value["COMMITTED.json"] is None and value[".staging/COMMITTED.part"] is None
    case.result["payload_final_visible_before_recovery"] = value["nested/data.bin"] is not None
    case.result["manifest_visible_before_recovery"] = value["COMMITTED.json"] is not None


def recovered(case, execute, status):
    value = objects(case, execute)
    original = case.result["publication_before_outage"]
    expected = original["nested/data.bin"] if case.point == "manifest_link" else original[".staging/1.part"]
    same_object(value["nested/data.bin"], expected)
    assert value["nested/data.bin"]["links"] == 1 and value[".staging/1.part"] is None
    assert value[".staging/COMMITTED.part"] is None and value["COMMITTED.json"]["links"] == 1
    if case.point == "manifest_link":
        same_object(value["COMMITTED.json"], original["COMMITTED.json"])
    assert status["state"] == "Committed" and status["details"]["files"][0]["attempt"] == 1
    assert execute(f"test ! -e {case.destination}/1/.staging/2.part", "1000:1000", check=False).returncode == 0
    case.result["publication_after_recovery"] = value
    case.result["original_payload_inode_preserved"] = True
    case.result["publication_recovered_on_attempt_one"] = True
