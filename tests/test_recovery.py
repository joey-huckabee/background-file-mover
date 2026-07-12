"""Tests for startup recovery reconciliation (cross-platform)."""

from __future__ import annotations

from pathlib import Path

import pytest

from file_mover.jobs.models import JobRecord, JobState
from file_mover.jobs.sqlite_repository import SQLiteJobRepository
from file_mover.recovery.manager import RecoveryManager


def _repo(tmp_path: Path) -> SQLiteJobRepository:
    repo = SQLiteJobRepository(str(tmp_path / "jobs.db"), time_source=lambda: 100.0)
    repo.initialize()
    return repo


def _insert_job(repo: SQLiteJobRepository, tmp_path: Path, job_id: str, state: JobState) -> Path:
    dest = tmp_path / "processing"
    dest.mkdir(exist_ok=True)
    repo.insert_job(JobRecord(job_id, state, str(tmp_path / "recordings"), str(dest), 1.0, 1.0))
    return dest


@pytest.mark.requirement("L2-REC-002")
def test_reconcile_requeues_interrupted_and_removes_temps(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    dest = _insert_job(repo, tmp_path, "j1", JobState.COPYING)
    (dest / ".swit-partial-j1-0000").write_bytes(b"partial")
    (dest / "sub").mkdir()
    (dest / "sub" / ".swit-partial-j1-0001").write_bytes(b"partial2")
    (dest / ".swit-partial-other-0000").write_bytes(b"keep")  # a different job's temp

    report = RecoveryManager(repository=repo, temporary_file_prefix=".swit-partial-").reconcile()

    assert report.requeued_jobs == 1
    assert report.removed_temporary_files == 2
    job = repo.get_job("j1")
    assert job is not None and job.state is JobState.QUEUED
    assert not (dest / ".swit-partial-j1-0000").exists()
    assert (dest / ".swit-partial-other-0000").exists()  # untouched
    repo.close()


@pytest.mark.requirement("L2-REC-001")
def test_reconcile_leaves_terminal_and_queued_jobs(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _insert_job(repo, tmp_path, "done", JobState.COMPLETED)
    _insert_job(repo, tmp_path, "ready", JobState.QUEUED)

    report = RecoveryManager(repository=repo, temporary_file_prefix=".swit-partial-").reconcile()

    assert report.requeued_jobs == 0
    assert repo.get_job("done") is not None
    assert repo.get_job("done").state is JobState.COMPLETED  # type: ignore[union-attr]
    assert repo.get_job("ready").state is JobState.QUEUED  # type: ignore[union-attr]
    repo.close()


@pytest.mark.requirement("L2-REC-002")
def test_reconcile_with_missing_destination_is_safe(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert_job(
        JobRecord("j1", JobState.COPYING, "/recordings", "/nonexistent-dest-xyz", 1.0, 1.0)
    )
    report = RecoveryManager(repository=repo, temporary_file_prefix=".swit-partial-").reconcile()
    assert report.requeued_jobs == 1
    assert report.removed_temporary_files == 0
    repo.close()
