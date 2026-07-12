"""Tests for the service command handlers (cross-platform; no socket)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from file_mover.configuration import ConfigurationLoader
from file_mover.constants import PROTOCOL_VERSION
from file_mover.jobs.models import JobRecord, JobState
from file_mover.jobs.sqlite_repository import SQLiteJobRepository
from file_mover.service import BackgroundMoverService, _resolve_state_selector

_MINIMAL = (
    "[paths]\n" "allowed_source_roots = /recordings\n" "allowed_destination_roots = /processing\n"
)


def _service_with_job(tmp_path: Path) -> tuple[BackgroundMoverService, SQLiteJobRepository]:
    config = ConfigurationLoader().load_text(_MINIMAL)
    repo = SQLiteJobRepository(str(tmp_path / "jobs.db"))
    repo.initialize()
    repo.insert_job(
        JobRecord(
            "j1",
            JobState.QUEUED,
            "/recordings/s1",
            "/processing/s1",
            1.0,
            1.0,
            total_bytes=100,
            bytes_copied=40,
        )
    )
    return BackgroundMoverService(config, repository=repo), repo


def _dispatch(
    service: BackgroundMoverService, command: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    dispatcher = service._build_dispatcher()  # exercise the handler map directly
    return dispatcher.dispatch(
        {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": "r",
            "command": command,
            "arguments": arguments,
        }
    )


@pytest.mark.requirement("L2-CTL-010")
def test_health_handler(tmp_path: Path) -> None:
    service, repo = _service_with_job(tmp_path)
    try:
        response = _dispatch(service, "health", {})
        assert response["success"] is True
        assert response["result"]["service_state"] == "running"
    finally:
        repo.close()


@pytest.mark.requirement("L2-JOB-006")
def test_status_handler_found_and_missing(tmp_path: Path) -> None:
    service, repo = _service_with_job(tmp_path)
    try:
        found = _dispatch(service, "status", {"job_id": "j1"})
        assert found["result"]["found"] is True
        assert found["result"]["job"]["state"] == "queued"
        assert _dispatch(service, "status", {"job_id": "nope"})["result"]["found"] is False
        assert _dispatch(service, "status", {"job_id": 123})["result"]["found"] is False
    finally:
        repo.close()


@pytest.mark.requirement("L2-JOB-006")
def test_list_handler(tmp_path: Path) -> None:
    service, repo = _service_with_job(tmp_path)
    try:
        active = _dispatch(service, "list", {"state": "active"})
        assert [job["job_id"] for job in active["result"]["jobs"]] == ["j1"]
        assert len(_dispatch(service, "list", {"state": "all"})["result"]["jobs"]) == 1
    finally:
        repo.close()


@pytest.mark.requirement("L2-CTL-004")
def test_list_handler_unknown_state_is_isolated(tmp_path: Path) -> None:
    service, repo = _service_with_job(tmp_path)
    try:
        response = _dispatch(service, "list", {"state": "bogus"})
        assert response["success"] is False
        assert response["error"]["code"] == "INTERNAL_ERROR"
    finally:
        repo.close()


@pytest.mark.requirement("L2-JOB-006")
def test_stats_handler(tmp_path: Path) -> None:
    service, repo = _service_with_job(tmp_path)
    try:
        result = _dispatch(service, "stats", {})["result"]
        assert result["total_jobs"] == 1
        assert result["total_bytes"] == 100
        assert result["jobs_by_state"]["queued"] == 1
    finally:
        repo.close()


@pytest.mark.requirement("L2-JOB-006")
def test_resolve_state_selector() -> None:
    assert _resolve_state_selector("all") is None
    assert _resolve_state_selector("queued") == frozenset({JobState.QUEUED})
    with pytest.raises(ValueError, match="unknown"):
        _resolve_state_selector("bogus")
