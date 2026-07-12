"""Tests for the SQLite job repository (cross-platform)."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from file_mover.exceptions import RepositoryError
from file_mover.jobs.models import (
    ACTIVE_JOB_STATES,
    FileRecord,
    FileState,
    JobRecord,
    JobState,
    is_allowed_job_transition,
)
from file_mover.jobs.sqlite_repository import SQLiteJobRepository


def _repo(tmp_path: Path) -> SQLiteJobRepository:
    repo = SQLiteJobRepository(str(tmp_path / "jobs.db"), time_source=lambda: 100.0)
    repo.initialize()
    return repo


def _job(
    job_id: str = "j1", *, state: JobState = JobState.SUBMITTED, **kwargs: object
) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        state=state,
        source_root="/recordings/s1",
        destination_root="/processing/s1",
        created_at=1.0,
        updated_at=1.0,
        **kwargs,  # type: ignore[arg-type]
    )


@pytest.mark.requirement("L2-JOB-004")
def test_initialize_is_idempotent(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.initialize()  # second call must be a no-op
    assert repo.list_jobs() == []
    repo.close()


@pytest.mark.requirement("L2-JOB-001")
def test_insert_and_get_job(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert_job(_job(total_bytes=500, scenario_id="scn"))
    fetched = repo.get_job("j1")
    assert fetched is not None
    assert fetched.state is JobState.SUBMITTED
    assert fetched.total_bytes == 500
    assert fetched.scenario_id == "scn"
    assert repo.get_job("missing") is None
    repo.close()


@pytest.mark.requirement("L2-JOB-001")
def test_duplicate_job_id_raises(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert_job(_job())
    with pytest.raises(RepositoryError):
        repo.insert_job(_job())
    repo.close()


@pytest.mark.requirement("L2-JOB-006")
def test_list_jobs_filters_by_state(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert_job(_job("a", state=JobState.QUEUED))
    repo.insert_job(_job("b", state=JobState.COMPLETED))
    active_ids = {job.job_id for job in repo.list_jobs(ACTIVE_JOB_STATES)}
    assert active_ids == {"a"}
    assert {job.job_id for job in repo.list_jobs()} == {"a", "b"}
    assert repo.list_jobs(set()) == []
    repo.close()


@pytest.mark.requirement("L2-JOB-005")
def test_legal_transition_updates_state(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert_job(_job())
    repo.transition_job("j1", JobState.VALIDATING)
    job = repo.get_job("j1")
    assert job is not None
    assert job.state is JobState.VALIDATING
    assert job.updated_at == 100.0  # stamped by the injected clock
    repo.close()


@pytest.mark.requirement("L2-JOB-005")
def test_illegal_transition_rejected(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert_job(_job(state=JobState.VALIDATING))
    with pytest.raises(RepositoryError, match="illegal"):
        repo.transition_job("j1", JobState.COMPLETED)
    repo.close()


@pytest.mark.requirement("L2-JOB-005")
def test_transition_unknown_job_rejected(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    with pytest.raises(RepositoryError, match="unknown"):
        repo.transition_job("nope", JobState.VALIDATING)
    repo.close()


@pytest.mark.requirement("L2-RTY-003")
def test_record_job_error_increments_attempt(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert_job(_job())
    repo.record_job_error("j1", "disk full", next_retry_time=200.0)
    job = repo.get_job("j1")
    assert job is not None
    assert job.attempt_count == 1
    assert job.last_error == "disk full"
    assert job.next_retry_time == 200.0
    repo.close()


@pytest.mark.requirement("L2-JOB-001")
def test_insert_and_list_files_with_cascade(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert_job(_job(file_count=2))
    repo.insert_files(
        [
            FileRecord("f2", "j1", "host02.dat", FileState.QUEUED_FOR_COPY, size_bytes=20),
            FileRecord("f1", "j1", "host01.dat", FileState.QUEUED_FOR_COPY, size_bytes=10),
        ]
    )
    files = repo.list_files("j1")
    assert [f.relative_path for f in files] == ["host01.dat", "host02.dat"]  # sorted
    repo.close()


@pytest.mark.requirement("L2-JOB-006")
def test_statistics_aggregate(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert_job(_job("a", state=JobState.QUEUED, total_bytes=100, bytes_copied=40))
    repo.insert_job(_job("b", state=JobState.QUEUED, total_bytes=200, bytes_copied=60))
    repo.insert_job(_job("c", state=JobState.COMPLETED, total_bytes=50, bytes_copied=50))
    stats = repo.statistics()
    assert stats.total_jobs == 3
    assert stats.total_bytes == 350
    assert stats.bytes_copied == 150
    assert stats.jobs_by_state[JobState.QUEUED] == 2
    repo.close()


@pytest.mark.requirement("L2-JOB-001")
def test_open_failure_raises_repository_error(tmp_path: Path) -> None:
    # A path whose parent directory does not exist cannot be opened.
    repo = SQLiteJobRepository(str(tmp_path / "no-such-dir" / "jobs.db"))
    with pytest.raises(RepositoryError):
        repo.initialize()


@pytest.mark.requirement("L2-REC-002")
def test_reset_job_state_bypasses_transition_map(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert_job(_job(state=JobState.COPYING))
    # A COPYING -> QUEUED reset is not a normal transition, but recovery may force it.
    repo.reset_job_state("j1", JobState.QUEUED)
    job = repo.get_job("j1")
    assert job is not None and job.state is JobState.QUEUED
    repo.close()


@pytest.mark.requirement("L2-REC-004")
def test_list_runnable_job_ids(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert_job(_job("queued", state=JobState.QUEUED))
    repo.insert_job(_job("due", state=JobState.RETRY_WAIT, next_retry_time=500.0))
    repo.insert_job(_job("future", state=JobState.RETRY_WAIT, next_retry_time=5000.0))
    repo.insert_job(_job("done", state=JobState.COMPLETED))
    runnable = set(repo.list_runnable_job_ids(1000.0, limit=10))
    assert runnable == {"queued", "due"}
    assert len(repo.list_runnable_job_ids(1000.0, limit=1)) == 1  # respects the limit
    repo.close()


@pytest.mark.requirement("L2-JOB-005")
def test_transition_map_terminals_are_closed() -> None:
    assert not is_allowed_job_transition(JobState.COMPLETED, JobState.QUEUED)
    assert is_allowed_job_transition(JobState.FAILED_RETAINED, JobState.QUEUED)


@pytest.mark.requirement("L2-JOB-002")
@pytest.mark.requirement("L3-JOB-001")
def test_wal_journal_mode_is_enabled(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert_job(_job())
    repo.close()
    connection = sqlite3.connect(str(tmp_path / "jobs.db"))
    try:
        mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        assert str(mode).lower() == "wal"
    finally:
        connection.close()


@pytest.mark.requirement("L3-JOB-002")
def test_corrupt_stored_state_raises_repository_error(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert_job(_job())
    # Corrupt the stored state out-of-band, then confirm reads fail safely (no panic).
    connection = sqlite3.connect(str(tmp_path / "jobs.db"))
    try:
        connection.execute("UPDATE jobs SET state = 'bogus' WHERE job_id = 'j1'")
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(RepositoryError, match="corrupt"):
        repo.get_job("j1")
    repo.close()


@pytest.mark.requirement("L2-JOB-003")
def test_each_thread_gets_its_own_connection(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.insert_job(_job())
    errors: list[Exception] = []

    def worker() -> None:
        try:
            assert repo.get_job("j1") is not None
        except Exception as error:  # record any failure for the assertion below
            errors.append(error)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    assert not errors
    assert len(repo._connections) >= 2  # main thread + worker thread each opened one
    repo.close()
