"""Additional custody evidence for two private roots on one controlled NFS export."""
import hashlib
from nfs_bootstrap_state import receipt_evidence


def payload(case, execute, path):
    return execute(f"stat -c '%d:%i:%s' {path}; sha256sum {path}", "1000:1000").stdout.splitlines()


def before(case, execute):
    result = case.result
    path = case.source + ("/current/nested/data.bin" if case.point == "claim_apply" else "/.file-mover/1-0/data")
    result["source_payload_before"] = payload(case, execute, path)
    assert result["source_payload_before"][1].split()[0] == hashlib.sha256(bytes(2 * 1048576) + b"0123456789abcdefg").hexdigest()
    result["database_identity_before"] = execute(f"stat -c '%d:%i' {case.base}/state/jobs.sqlite", "1000:1000").stdout
    result["enrollment_receipt_before"] = receipt_evidence(case, execute)
    if case.point == "copy_chunk":
        result["copy_partial_before"] = payload(case, execute, case.destination + "/1/.staging/1.part")


def recovered(case, execute):
    result = case.result
    result["source_payload_after"] = payload(case, execute, case.source + "/.file-mover/1-0/data")
    assert result["source_payload_after"][0] == result["source_payload_before"][0]
    assert result["source_payload_after"][1].split()[0] == result["source_payload_before"][1].split()[0]
    result["database_identity_after"] = execute(f"stat -c '%d:%i' {case.base}/state/jobs.sqlite", "1000:1000").stdout
    result["enrollment_receipt_after"] = receipt_evidence(case, execute)
    assert result["database_identity_after"] == result["database_identity_before"]
    assert result["enrollment_receipt_after"] == result["enrollment_receipt_before"]
    if case.point == "copy_chunk":
        result["copy_partial_after"] = payload(case, execute, case.destination + "/1/.staging/1.part")
        # The blocked old worker may finish its authorized write before exit.
        # Recovery must retain that old allocation, never overwrite or reuse it.
        old_size = int(result["copy_partial_after"][0].split(":")[-1])
        assert result["copy_partial_after"][0].split(":")[:2] == result["copy_partial_before"][0].split(":")[:2]
        assert 1048576 <= old_size <= 2 * 1048576 + 17
        expected = bytes(min(old_size, 2 * 1048576)) + b"0123456789abcdefg"[:max(0, old_size - 2 * 1048576)]
        assert result["copy_partial_after"][1].split()[0] == hashlib.sha256(expected).hexdigest()
    result["original_source_inode_preserved"] = True
    result["original_database_and_enrollment_preserved"] = True
