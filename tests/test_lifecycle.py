"""Tests for the cancel/pause/resume lifecycle service (SQLite-backed, cross-platform)."""

from __future__ import annotations

from pathlib import Path

import pytest

from file_mover.control.lifecycle import JobLifecycleService
from file_mover.jobs.models import ControlSignal, JobRecord, JobState
from file_mover.jobs.sqlite_repository import SQLiteJobRepository
from file_mover.transfer.control_signals import JobControlSignals

_PREFIX = ".swit-partial-"


def _service(
    tmp_path: Path, state: JobState, *, destination_root: str = "/processing/s"
) -> tuple[JobLifecycleService, SQLiteJobRepository, JobControlSignals]:
    repo = SQLiteJobRepository(str(tmp_path / "jobs.db"))
    repo.initialize()
    repo.insert_job(
        JobRecord("j1", state, "/recordings/s", destination_root, 1.0, 1.0, total_bytes=10)
    )
    signals = JobControlSignals()
    service = JobLifecycleService(repository=repo, signals=signals, temporary_file_prefix=_PREFIX)
    return service, repo, signals


@pytest.mark.requirement("L2-LIF-004")
def test_pause_queued_job_transitions_directly(tmp_path: Path) -> None:
    service, repo, signals = _service(tmp_path, JobState.QUEUED)
    try:
        result = service.handle_pause({"job_id": "j1"})
        assert result["accepted"] is True
        assert result["state"] == "paused"
        assert repo.get_job("j1").state is JobState.PAUSED
        assert signals.poll("j1") is None  # not running -> no cooperative signal needed
    finally:
        repo.close()


@pytest.mark.requirement("L2-LIF-002")
def test_pause_copying_job_signals_cooperatively(tmp_path: Path) -> None:
    service, repo, signals = _service(tmp_path, JobState.COPYING)
    try:
        result = service.handle_pause({"job_id": "j1"})
        assert result["accepted"] is True
        assert result["state"] == "copying"  # still copying; will stop at a safe point
        assert signals.poll("j1") is ControlSignal.PAUSE
        assert repo.get_job("j1").state is JobState.COPYING  # unchanged until the loop stops
    finally:
        repo.close()


@pytest.mark.requirement("L2-LIF-004")
def test_pause_is_idempotent(tmp_path: Path) -> None:
    service, repo, _ = _service(tmp_path, JobState.PAUSED)
    try:
        assert service.handle_pause({"job_id": "j1"})["accepted"] is True
        assert repo.get_job("j1").state is JobState.PAUSED
    finally:
        repo.close()


@pytest.mark.requirement("L2-LIF-004")
def test_resume_paused_job_requeues_and_clears_signal(tmp_path: Path) -> None:
    service, repo, signals = _service(tmp_path, JobState.PAUSED)
    signals.request("j1", ControlSignal.PAUSE)  # a stale signal from the earlier pause
    try:
        result = service.handle_resume({"job_id": "j1"})
        assert result["accepted"] is True
        assert result["state"] == "queued"
        assert repo.get_job("j1").state is JobState.QUEUED
        assert signals.poll("j1") is None  # cleared so it does not immediately re-pause
    finally:
        repo.close()


@pytest.mark.requirement("L2-LIF-005")
def test_resume_non_paused_is_rejected(tmp_path: Path) -> None:
    service, repo, _ = _service(tmp_path, JobState.QUEUED)
    try:
        result = service.handle_resume({"job_id": "j1"})
        assert result["accepted"] is False
        assert result["error_code"] == "INVALID_STATE"
    finally:
        repo.close()


@pytest.mark.requirement("L2-LIF-001")
def test_cancel_paused_job_retains_source_and_removes_partial(tmp_path: Path) -> None:
    dest = tmp_path / "processing"
    dest.mkdir()
    partial = dest / f"{_PREFIX}j1-f1"
    partial.write_bytes(b"half")
    service, repo, _ = _service(tmp_path, JobState.PAUSED, destination_root=str(dest))
    try:
        result = service.handle_cancel({"job_id": "j1"})
        assert result["accepted"] is True
        assert result["state"] == "cancelled_retained"
        assert repo.get_job("j1").state is JobState.CANCELLED_RETAINED
        assert not partial.exists()  # incomplete partial discarded
    finally:
        repo.close()


@pytest.mark.requirement("L2-LIF-002")
def test_cancel_copying_job_signals_cooperatively(tmp_path: Path) -> None:
    service, repo, signals = _service(tmp_path, JobState.COPYING)
    try:
        result = service.handle_cancel({"job_id": "j1"})
        assert result["accepted"] is True
        assert signals.poll("j1") is ControlSignal.CANCEL
    finally:
        repo.close()


@pytest.mark.requirement("L2-LIF-003")
def test_cancel_completed_job_is_rejected(tmp_path: Path) -> None:
    service, repo, _ = _service(tmp_path, JobState.COMPLETED)
    try:
        result = service.handle_cancel({"job_id": "j1"})
        assert result["accepted"] is False
        assert result["error_code"] == "INVALID_STATE"
    finally:
        repo.close()


@pytest.mark.requirement("L2-LIF-005")
def test_unknown_job_and_missing_id_are_typed_errors(tmp_path: Path) -> None:
    service, repo, _ = _service(tmp_path, JobState.QUEUED)
    try:
        assert service.handle_pause({"job_id": "nope"})["error_code"] == "NOT_FOUND"
        assert service.handle_pause({})["error_code"] == "BAD_REQUEST"
        assert service.handle_cancel({"job_id": 123})["error_code"] == "BAD_REQUEST"
    finally:
        repo.close()
