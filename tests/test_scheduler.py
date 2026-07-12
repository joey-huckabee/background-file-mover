"""Tests for the transfer scheduler and end-to-end recovery reprocess (cross-platform)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from file_mover.claiming import FileClaimManager
from file_mover.configuration import StabilityConfig
from file_mover.jobs.models import ExistingDestinationPolicy, HashAlgorithm, IntegrityMode, JobState
from file_mover.jobs.sqlite_repository import SQLiteJobRepository
from file_mover.manifests import ManifestWriter
from file_mover.recovery.manager import RecoveryManager
from file_mover.submission import JobSubmissionService, SubmissionRequest
from file_mover.transfer.coordinator import TransferCoordinator
from file_mover.transfer.copy_engine import BufferedFileCopyEngine
from file_mover.transfer.integrity import IntegrityVerifier
from file_mover.transfer.retry import ErrorClassifier
from file_mover.transfer.scheduler import TransferScheduler
from file_mover.validation import SourceValidator

_BUFFER = 64 * 1024


def _setup(
    tmp_path: Path, *, clock: Callable[[], float] = lambda: 1000.0, max_concurrent_jobs: int = 1
) -> tuple[SQLiteJobRepository, JobSubmissionService, TransferScheduler, Path, Path]:
    source_root = tmp_path / "recordings"
    dest_root = tmp_path / "processing"
    source_root.mkdir()
    dest_root.mkdir()
    repo = SQLiteJobRepository(str(tmp_path / "jobs.db"))
    repo.initialize()
    job_ids = iter(["job-1", "job-2", "job-3"])
    submission = JobSubmissionService(
        validator=SourceValidator(
            claim_directory_name=".swit-moving", reject_symbolic_links=True, sleeper=lambda _s: None
        ),
        claim_manager=FileClaimManager(claim_directory_name=".swit-moving"),
        manifest_writer=ManifestWriter(tmp_path / "manifests"),
        repository=repo,
        allowed_source_roots=[source_root],
        allowed_destination_roots=[dest_root],
        stability=StabilityConfig(enabled=False, poll_count=2, poll_interval_seconds=0.0),
        job_id_factory=lambda: next(job_ids),
    )
    coordinator = TransferCoordinator(
        repository=repo,
        copy_engine=BufferedFileCopyEngine(
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
        clock=clock,
    )
    scheduler = TransferScheduler(
        repository=repo,
        coordinator=coordinator,
        max_concurrent_jobs=max_concurrent_jobs,
        clock=clock,
    )
    return repo, submission, scheduler, source_root, dest_root


@pytest.mark.requirement("L2-REC-004")
def test_scheduler_processes_a_queued_job(tmp_path: Path) -> None:
    repo, submission, scheduler, source_root, dest_root = _setup(tmp_path)
    (source_root / "a.dat").write_bytes(b"hello")
    submission.submit(SubmissionRequest("r", None, source_root, dest_root))

    assert scheduler.run_once() == ["job-1"]
    assert (dest_root / "a.dat").read_bytes() == b"hello"
    job = repo.get_job("job-1")
    assert job is not None and job.state is JobState.COMPLETED
    assert scheduler.run_once() == []  # nothing runnable now
    repo.close()


@pytest.mark.requirement("L2-RTY-004")
def test_scheduler_runs_due_retry_and_skips_future_retry(tmp_path: Path) -> None:
    repo, submission, scheduler, source_root, dest_root = _setup(tmp_path)
    (source_root / "a.dat").write_bytes(b"hello")
    submission.submit(SubmissionRequest("r", None, source_root, dest_root))
    # Move the job to a future retry; it must not be picked up at clock=1000.
    repo.reset_job_state("job-1", JobState.RETRY_WAIT)
    repo.record_job_error("job-1", "stalled", next_retry_time=5000.0)
    assert scheduler.run_once() == []
    # Make the retry due; the scheduler re-queues and processes it.
    repo.record_job_error("job-1", "stalled", next_retry_time=500.0)
    assert scheduler.run_once() == ["job-1"]
    job = repo.get_job("job-1")
    assert job is not None and job.state is JobState.COMPLETED
    repo.close()


@pytest.mark.requirement("L2-REC-004")
def test_scheduler_respects_max_concurrent_jobs(tmp_path: Path) -> None:
    repo, submission, scheduler, source_root, dest_root = _setup(tmp_path, max_concurrent_jobs=1)
    (source_root / "a.dat").write_bytes(b"one")
    submission.submit(SubmissionRequest("r1", None, source_root, dest_root))
    (source_root / "b.dat").write_bytes(b"two")
    submission.submit(SubmissionRequest("r2", None, source_root, dest_root))
    processed = scheduler.run_once()
    assert len(processed) == 1  # limited to one job per tick
    repo.close()


@pytest.mark.requirement("L2-REC-003")
def test_recovery_reprocess_is_idempotent(tmp_path: Path) -> None:
    repo, submission, scheduler, source_root, dest_root = _setup(tmp_path)
    (source_root / "a.dat").write_bytes(b"hello")
    submission.submit(SubmissionRequest("r", None, source_root, dest_root))
    assert scheduler.run_once() == ["job-1"]
    assert repo.get_job("job-1").state is JobState.COMPLETED  # type: ignore[union-attr]

    # Simulate a crash recorded after completion: reset to an interrupted state, recover,
    # and reprocess. Completed files are skipped, so no re-copy/re-delete error occurs.
    repo.reset_job_state("job-1", JobState.COPYING)
    RecoveryManager(repository=repo, temporary_file_prefix=".swit-partial-").reconcile()
    assert scheduler.run_once() == ["job-1"]
    assert repo.get_job("job-1").state is JobState.COMPLETED  # type: ignore[union-attr]
    assert (dest_root / "a.dat").read_bytes() == b"hello"
    repo.close()
