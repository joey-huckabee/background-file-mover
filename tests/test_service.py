"""Tests for the service command handlers (cross-platform; no socket)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from file_mover.claiming import FileClaimManager
from file_mover.configuration import ConfigurationLoader, StabilityConfig
from file_mover.constants import PROTOCOL_VERSION
from file_mover.jobs.models import JobRecord, JobState
from file_mover.jobs.sqlite_repository import SQLiteJobRepository
from file_mover.manifests import ManifestWriter
from file_mover.presentation import resolve_state_selector as _resolve_state_selector
from file_mover.service import BackgroundMoverService
from file_mover.submission import JobSubmissionService
from file_mover.validation import SourceValidator

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


@pytest.mark.requirement("L2-BWL-002")
def test_throttle_handler_sets_live_limit_and_is_reflected_in_health(tmp_path: Path) -> None:
    service, repo = _service_with_job(tmp_path)
    try:
        service._build_scheduler(repo)  # creates the shared rate limiter
        # health reports the starting (unlimited) ceiling.
        assert _dispatch(service, "health", {})["result"]["max_bytes_per_second"] == 0
        response = _dispatch(service, "throttle", {"bytes_per_second": 5_000_000})
        assert response["success"] is True
        assert response["result"]["accepted"] is True
        assert response["result"]["bytes_per_second"] == 5_000_000
        # The limiter is live and observable through health.
        assert service._rate_limiter is not None
        assert service._rate_limiter.bytes_per_second == 5_000_000
        assert _dispatch(service, "health", {})["result"]["max_bytes_per_second"] == 5_000_000
        # Zero removes the limit again.
        cleared = _dispatch(service, "throttle", {"bytes_per_second": 0})
        assert cleared["result"]["accepted"] is True
        assert service._rate_limiter.is_unlimited() is True
    finally:
        repo.close()


@pytest.mark.requirement("L2-BWL-002")
def test_throttle_handler_rejects_bad_values(tmp_path: Path) -> None:
    service, repo = _service_with_job(tmp_path)
    try:
        service._build_scheduler(repo)
        for bad in ({"bytes_per_second": -1}, {"bytes_per_second": "fast"}, {}):
            response = _dispatch(service, "throttle", bad)
            assert response["success"] is True  # the command runs; the request is rejected
            assert response["result"]["accepted"] is False
            assert response["result"]["error_code"] == "BAD_REQUEST"
        # A rejected request must not change the live limit.
        assert service._rate_limiter is not None
        assert service._rate_limiter.bytes_per_second == 0
    finally:
        repo.close()


@pytest.mark.requirement("L2-BWL-002")
def test_throttle_handler_rejects_boolean_masquerading_as_int(tmp_path: Path) -> None:
    service, repo = _service_with_job(tmp_path)
    try:
        service._build_scheduler(repo)
        response = _dispatch(service, "throttle", {"bytes_per_second": True})
        assert response["result"]["accepted"] is False
        assert response["result"]["error_code"] == "BAD_REQUEST"
    finally:
        repo.close()


@pytest.mark.requirement("L2-LIF-004")
def test_pause_and_resume_handlers_via_dispatcher(tmp_path: Path) -> None:
    service, repo = _service_with_job(tmp_path)  # job j1 is QUEUED
    try:
        paused = _dispatch(service, "pause", {"job_id": "j1"})
        assert paused["result"]["accepted"] is True
        assert repo.get_job("j1").state is JobState.PAUSED
        resumed = _dispatch(service, "resume", {"job_id": "j1"})
        assert resumed["result"]["state"] == "queued"
        assert repo.get_job("j1").state is JobState.QUEUED
        # A cancel then reaches the terminal retained state.
        cancelled = _dispatch(service, "cancel", {"job_id": "j1"})
        assert cancelled["result"]["state"] == "cancelled_retained"
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


@pytest.mark.requirement("L2-CTL-004")
def test_require_helpers_raise_when_not_running() -> None:
    config = ConfigurationLoader().load_text(_MINIMAL)
    service = BackgroundMoverService(config)  # nothing opened yet
    with pytest.raises(RuntimeError):
        service._require_repository()
    with pytest.raises(RuntimeError):
        service._require_submission()


@pytest.mark.requirement("L2-REC-001")
def test_build_scheduler_and_reconcile(tmp_path: Path) -> None:
    config = ConfigurationLoader().load_text(_MINIMAL)
    repo = SQLiteJobRepository(str(tmp_path / "jobs.db"))
    repo.initialize()
    service = BackgroundMoverService(config, repository=repo)
    assert service._build_scheduler(repo) is not None
    service._reconcile(repo)  # no interrupted jobs -> a safe no-op
    repo.close()


@pytest.mark.requirement("L2-REC-004")
def test_scheduler_loop_runs_a_tick_then_stops(tmp_path: Path) -> None:
    config = ConfigurationLoader().load_text(_MINIMAL)
    service = BackgroundMoverService(config)
    ticks: list[int] = []

    class _OneShotScheduler:
        def run_once(self) -> list[str]:
            ticks.append(1)
            service.request_stop()  # end the loop after one tick
            return []

    service._scheduler = _OneShotScheduler()  # type: ignore[assignment]
    service._scheduler_loop()
    assert ticks == [1]


@pytest.mark.requirement("L2-REC-004")
def test_scheduler_loop_survives_a_failing_tick(tmp_path: Path) -> None:
    config = ConfigurationLoader().load_text(_MINIMAL)
    service = BackgroundMoverService(config)

    class _BoomScheduler:
        def run_once(self) -> list[str]:
            service.request_stop()
            raise RuntimeError("tick blew up")

    service._scheduler = _BoomScheduler()  # type: ignore[assignment]
    service._scheduler_loop()  # must not raise


@pytest.mark.requirement("L2-CTL-004")
def test_submit_handler_rejects_malformed_requests(tmp_path: Path) -> None:
    service, repo = _service_with_job(tmp_path)  # submission service not open
    try:
        missing = _dispatch(service, "submit", {})
        assert missing["result"]["accepted"] is False
        assert missing["result"]["error_code"] == "BAD_REQUEST"
        no_source = _dispatch(service, "submit", {"request_id": "r", "destination": "/processing"})
        assert no_source["result"]["error_code"] == "BAD_REQUEST"
    finally:
        repo.close()


@pytest.mark.requirement("L2-SUB-002")
def test_submit_handler_claims_and_records(tmp_path: Path) -> None:
    config = ConfigurationLoader().load_text(_MINIMAL)
    source_root = tmp_path / "recordings"
    dest_root = tmp_path / "processing"
    source_root.mkdir()
    dest_root.mkdir()
    (source_root / "a.dat").write_bytes(b"xyz")
    repo = SQLiteJobRepository(str(tmp_path / "jobs.db"))
    repo.initialize()
    service = BackgroundMoverService(config, repository=repo)
    # Inject a submission service scoped to the tmp roots (config roots are POSIX).
    service._submission = JobSubmissionService(
        validator=SourceValidator(
            claim_directory_name=".swit-moving", reject_symbolic_links=True, sleeper=lambda _s: None
        ),
        claim_manager=FileClaimManager(claim_directory_name=".swit-moving"),
        manifest_writer=ManifestWriter(tmp_path / "manifests"),
        repository=repo,
        allowed_source_roots=[source_root],
        allowed_destination_roots=[dest_root],
        stability=StabilityConfig(enabled=False, poll_count=2, poll_interval_seconds=0.0),
        job_id_factory=lambda: "jx",
    )
    try:
        response = _dispatch(
            service,
            "submit",
            {
                "request_id": "r",
                "scenario_id": "s",
                "source": str(source_root),
                "destination": str(dest_root),
            },
        )
        assert response["success"] is True
        assert response["result"]["accepted"] is True
        assert response["result"]["job_id"] == "jx"
        assert response["result"]["claimed_file_count"] == 1
    finally:
        repo.close()
