"""Tests for the submission/claiming pipeline (cross-platform)."""

from __future__ import annotations

import json
import socket
from collections.abc import Callable
from pathlib import Path

import pytest

from file_mover.claiming import FileClaimManager
from file_mover.configuration import IntegrityConfig, StabilityConfig
from file_mover.jobs.models import FileState, HashAlgorithm, IntegrityMode, JobState
from file_mover.jobs.sqlite_repository import SQLiteJobRepository
from file_mover.manifests import ManifestWriter
from file_mover.submission import (
    JobSubmissionService,
    SubmissionRequest,
    build_submission_request,
)
from file_mover.validation import SourceValidator

_STABLE = StabilityConfig(enabled=False, poll_count=2, poll_interval_seconds=0.0)
_INTEGRITY = IntegrityConfig(
    enabled=True,
    mode=IntegrityMode.SOURCE_AND_DESTINATION_HASH,
    algorithm=HashAlgorithm.SHA256,
)


def _build_service(
    tmp_path: Path,
    *,
    stability: StabilityConfig = _STABLE,
    sleeper: Callable[[float], None] = lambda _seconds: None,
    job_id_factory: Callable[[], str] = lambda: "job-1",
) -> tuple[JobSubmissionService, SQLiteJobRepository, Path, Path]:
    source_root = tmp_path / "recordings"
    dest_root = tmp_path / "processing"
    source_root.mkdir()
    dest_root.mkdir()
    repo = SQLiteJobRepository(str(tmp_path / "jobs.db"), time_source=lambda: 100.0)
    repo.initialize()
    service = JobSubmissionService(
        validator=SourceValidator(
            claim_directory_name=".swit-moving", reject_symbolic_links=True, sleeper=sleeper
        ),
        claim_manager=FileClaimManager(claim_directory_name=".swit-moving"),
        manifest_writer=ManifestWriter(tmp_path / "manifests"),
        repository=repo,
        allowed_source_roots=[source_root],
        allowed_destination_roots=[dest_root],
        stability=stability,
        integrity=_INTEGRITY,
        job_id_factory=job_id_factory,
        clock=lambda: 100.0,
    )
    return service, repo, source_root, dest_root


@pytest.mark.requirement("L2-SUB-002")
@pytest.mark.requirement("L3-SUB-001")
@pytest.mark.requirement("L2-DST-005")
@pytest.mark.requirement("L2-CLI-009")
def test_submit_claims_records_and_writes_manifest(tmp_path: Path) -> None:
    service, repo, source_root, dest_root = _build_service(tmp_path)
    (source_root / "host01.dat").write_bytes(b"aaa")
    (source_root / "sub").mkdir()
    (source_root / "sub" / "host02.dat").write_bytes(b"bbbb")

    result = service.submit(SubmissionRequest("req-1", "scn", source_root, dest_root))

    assert result.accepted is True
    assert result.claimed_file_count == 2
    assert result.claimed_bytes == 7
    assert result.state is JobState.QUEUED
    # Sources have been claimed into the per-job staging directory.
    assert not (source_root / "host01.dat").exists()
    staging = source_root / ".swit-moving" / "job-1"
    assert (staging / "host01.dat").read_bytes() == b"aaa"
    assert (staging / "sub" / "host02.dat").read_bytes() == b"bbbb"
    # Durably recorded.
    job = repo.get_job("job-1")
    assert job is not None
    assert job.state is JobState.QUEUED
    assert job.request_id == "req-1"
    files = repo.list_files("job-1")
    assert {f.relative_path for f in files} == {"host01.dat", "sub/host02.dat"}
    assert all(f.state is FileState.QUEUED_FOR_COPY for f in files)
    # Manifest written atomically.
    assert (tmp_path / "manifests" / "job-1.json").exists()
    repo.close()


@pytest.mark.requirement("L3-SUB-002")
def test_manifest_writer_writes_atomically(tmp_path: Path) -> None:
    writer = ManifestWriter(tmp_path / "m")
    path = writer.write("job-1", {"files": [{"relative_path": "a"}]})
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == writer.schema_version
    assert payload["files"] == [{"relative_path": "a"}]
    assert not (tmp_path / "m" / ".job-1.json.tmp").exists()  # no temp left behind


@pytest.mark.requirement("L2-SUB-001")
def test_submit_is_idempotent_by_request_id(tmp_path: Path) -> None:
    service, repo, source_root, dest_root = _build_service(tmp_path)
    (source_root / "a.dat").write_bytes(b"x")

    first = service.submit(SubmissionRequest("req-1", None, source_root, dest_root))
    assert first.accepted and first.job_id == "job-1"
    # Re-submitting the same request returns the original job without re-claiming.
    second = service.submit(SubmissionRequest("req-1", None, source_root, dest_root))
    assert second.accepted and second.job_id == "job-1"
    assert second.claimed_file_count == 1
    assert len(repo.list_jobs()) == 1
    repo.close()


@pytest.mark.requirement("L2-SUB-003")
def test_submit_rejects_empty_source(tmp_path: Path) -> None:
    service, repo, source_root, dest_root = _build_service(tmp_path)
    result = service.submit(SubmissionRequest("req-1", None, source_root, dest_root))
    assert result.accepted is False
    assert result.error_code == "InvalidSourceError"
    repo.close()


@pytest.mark.requirement("L2-FS-005")
def test_submit_rejects_source_outside_allowed_roots(tmp_path: Path) -> None:
    service, repo, _source_root, dest_root = _build_service(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "a.dat").write_bytes(b"x")
    result = service.submit(SubmissionRequest("req-1", None, outside, dest_root))
    assert result.accepted is False
    assert result.error_code == "InvalidSourceError"
    assert (outside / "a.dat").exists()  # untouched
    repo.close()


@pytest.mark.requirement("L2-SUB-005")
def test_submit_rejects_destination_outside_allowed_roots(tmp_path: Path) -> None:
    service, repo, source_root, _dest_root = _build_service(tmp_path)
    (source_root / "a.dat").write_bytes(b"x")
    result = service.submit(SubmissionRequest("req-1", None, source_root, tmp_path / "elsewhere"))
    assert result.accepted is False
    assert result.error_code == "InvalidDestinationError"
    assert (source_root / "a.dat").exists()  # source retained, never claimed
    repo.close()


@pytest.mark.requirement("L2-CLI-008")
def test_submit_file_list(tmp_path: Path) -> None:
    service, repo, source_root, dest_root = _build_service(tmp_path)
    first = source_root / "a.dat"
    first.write_bytes(b"x")
    (source_root / "sub").mkdir()
    second = source_root / "sub" / "b.dat"
    second.write_bytes(b"yy")
    request = build_submission_request(
        request_id="req-1",
        scenario_id=None,
        destination=str(dest_root),
        file_list=[str(first), str(second)],
    )
    result = service.submit(request)
    assert result.accepted is True
    assert result.claimed_file_count == 2
    repo.close()


@pytest.mark.requirement("L2-POSIX-006")
def test_submit_detects_unstable_source(tmp_path: Path) -> None:
    source_root = tmp_path / "recordings"
    dest_root = tmp_path / "processing"
    source_root.mkdir()
    dest_root.mkdir()
    target = source_root / "a.dat"
    target.write_bytes(b"x")

    def growing_sleeper(_seconds: float) -> None:
        target.write_bytes(b"xyz")  # size changes between observations

    repo = SQLiteJobRepository(str(tmp_path / "jobs.db"))
    repo.initialize()
    service = JobSubmissionService(
        validator=SourceValidator(
            claim_directory_name=".swit-moving",
            reject_symbolic_links=True,
            sleeper=growing_sleeper,
        ),
        claim_manager=FileClaimManager(claim_directory_name=".swit-moving"),
        manifest_writer=ManifestWriter(tmp_path / "manifests"),
        repository=repo,
        allowed_source_roots=[source_root],
        allowed_destination_roots=[dest_root],
        stability=StabilityConfig(enabled=True, poll_count=2, poll_interval_seconds=0.0),
        integrity=_INTEGRITY,
    )
    result = service.submit(SubmissionRequest("req-1", None, source_root, dest_root))
    assert result.accepted is False
    assert result.error_code == "SourceNotStableError"
    assert target.exists()  # retained
    repo.close()


@pytest.mark.requirement("L2-JOB-007")
@pytest.mark.requirement("L3-JOB-003")
def test_manifest_and_record_carry_consistent_metadata(tmp_path: Path) -> None:
    service, repo, source_root, dest_root = _build_service(tmp_path)
    (source_root / "host01.dat").write_bytes(b"aaa")

    result = service.submit(SubmissionRequest("req-1", "scn", source_root, dest_root))
    assert result.accepted is True

    job = repo.get_job("job-1")
    assert job is not None
    manifest = json.loads((tmp_path / "manifests" / "job-1.json").read_text(encoding="utf-8"))

    # The manifest and the durable job record agree on creation time and integrity policy.
    assert manifest["created_at"] == job.created_at == 100.0
    assert manifest["integrity"] == {"mode": "source-and-destination-hash", "algorithm": "sha256"}
    assert job.integrity_mode is IntegrityMode.SOURCE_AND_DESTINATION_HASH
    assert job.hash_algorithm is HashAlgorithm.SHA256
    repo.close()


@pytest.mark.requirement("L2-POSIX-002")
@pytest.mark.requirement("L2-FS-004")
@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="creating symlinks needs POSIX here")
def test_submit_rejects_symlinks(tmp_path: Path) -> None:
    service, repo, source_root, dest_root = _build_service(tmp_path)
    real = tmp_path / "outside-target.dat"
    real.write_bytes(b"x")
    (source_root / "link.dat").symlink_to(real)
    result = service.submit(SubmissionRequest("req-1", None, source_root, dest_root))
    assert result.accepted is False
    assert result.error_code == "InvalidSourceError"
    repo.close()
