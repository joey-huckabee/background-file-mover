"""Fault injection at destructive boundaries: failures must retain source data."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from file_mover.claiming import FileClaimManager
from file_mover.configuration import StabilityConfig
from file_mover.exceptions import DestinationPublishError, ManifestError, RepositoryError
from file_mover.jobs.models import (
    ExistingDestinationPolicy,
    HashAlgorithm,
    IntegrityMode,
    JobState,
)
from file_mover.jobs.sqlite_repository import SQLiteJobRepository
from file_mover.manifests import ManifestWriter
from file_mover.submission import JobSubmissionService, SubmissionRequest
from file_mover.transfer.coordinator import TransferCoordinator
from file_mover.transfer.copy_engine import BufferedFileCopyEngine
from file_mover.transfer.integrity import IntegrityVerifier
from file_mover.transfer.retry import ErrorClassifier
from file_mover.validation import SourceValidator

_BUFFER = 64 * 1024


def _submission(
    tmp_path: Path, repo: SQLiteJobRepository, *, manifest_writer: ManifestWriter | None = None
) -> tuple[JobSubmissionService, Path, Path]:
    source_root = tmp_path / "recordings"
    dest_root = tmp_path / "processing"
    source_root.mkdir(exist_ok=True)
    dest_root.mkdir(exist_ok=True)
    service = JobSubmissionService(
        validator=SourceValidator(
            claim_directory_name=".swit-moving", reject_symbolic_links=True, sleeper=lambda _s: None
        ),
        claim_manager=FileClaimManager(claim_directory_name=".swit-moving"),
        manifest_writer=manifest_writer or ManifestWriter(tmp_path / "manifests"),
        repository=repo,
        allowed_source_roots=[source_root],
        allowed_destination_roots=[dest_root],
        stability=StabilityConfig(enabled=False, poll_count=2, poll_interval_seconds=0.0),
        job_id_factory=lambda: "job-1",
    )
    return service, source_root, dest_root


class _FailingPublishEngine(BufferedFileCopyEngine):
    """Copies normally but fails at the atomic publish step."""

    def publish(self, temporary: Path, final: Path) -> None:
        raise DestinationPublishError("publish failed (injected)")


@pytest.mark.requirement("L1-SYS-003")
def test_publish_failure_retains_source_and_temp(tmp_path: Path) -> None:
    repo = SQLiteJobRepository(str(tmp_path / "jobs.db"))
    repo.initialize()
    submission, source_root, dest_root = _submission(tmp_path, repo)
    (source_root / "a.dat").write_bytes(b"hello")
    submission.submit(SubmissionRequest("r", None, source_root, dest_root))
    coordinator = TransferCoordinator(
        repository=repo,
        copy_engine=_FailingPublishEngine(
            buffer_size_bytes=_BUFFER, temporary_file_prefix=".swit-partial-"
        ),
        integrity_verifier=IntegrityVerifier(
            algorithm=HashAlgorithm.SHA256, buffer_size_bytes=_BUFFER
        ),
        error_classifier=ErrorClassifier(),
        claim_directory_name=".swit-moving",
        integrity_enabled=True,
        integrity_mode=IntegrityMode.SOURCE_AND_DESTINATION_HASH,
        destination_policy=ExistingDestinationPolicy.FAIL,
        retry_initial_delay_seconds=10.0,
        retry_max_delay_seconds=900.0,
    )

    state = coordinator.process_job("job-1")

    assert state is JobState.FAILED_RETAINED  # not COMPLETED
    assert (source_root / ".swit-moving" / "job-1" / "a.dat").exists()  # source retained
    assert not (dest_root / "a.dat").exists()  # not published
    assert any(p.name.startswith(".swit-partial-") for p in dest_root.iterdir())  # temp retained
    repo.close()


class _FailingManifestWriter(ManifestWriter):
    """A manifest writer that always fails."""

    def write(self, job_id: str, manifest: dict[str, Any]) -> Path:
        raise ManifestError("manifest write failed (injected)")


@pytest.mark.requirement("L2-SUB-005")
def test_manifest_failure_during_submit_retains_claimed_files(tmp_path: Path) -> None:
    repo = SQLiteJobRepository(str(tmp_path / "jobs.db"))
    repo.initialize()
    submission, source_root, _dest_root = _submission(
        tmp_path, repo, manifest_writer=_FailingManifestWriter(tmp_path / "manifests")
    )
    (source_root / "a.dat").write_bytes(b"hello")

    result = submission.submit(SubmissionRequest("r", None, source_root, _dest_root))

    assert result.accepted is False
    assert result.error_code == "ManifestError"
    assert (source_root / ".swit-moving" / "job-1" / "a.dat").exists()  # claimed, retained
    assert repo.get_job("job-1") is None  # never recorded
    repo.close()


class _FailingInsertRepository(SQLiteJobRepository):
    """A repository whose job insert always fails."""

    def insert_job(self, job: Any) -> None:
        raise RepositoryError("insert failed (injected)")


@pytest.mark.requirement("L2-SUB-005")
def test_repository_failure_during_submit_is_not_accepted(tmp_path: Path) -> None:
    repo = _FailingInsertRepository(str(tmp_path / "jobs.db"))
    repo.initialize()
    submission, source_root, dest_root = _submission(tmp_path, repo)
    (source_root / "a.dat").write_bytes(b"hello")

    result = submission.submit(SubmissionRequest("r", None, source_root, dest_root))

    assert result.accepted is False
    assert result.error_code == "RepositoryError"
    assert (source_root / ".swit-moving" / "job-1" / "a.dat").exists()  # claimed, retained
    repo.close()
