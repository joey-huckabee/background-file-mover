"""AF_UNIX / fcntl integration tests (POSIX only; skipped elsewhere)."""

from __future__ import annotations

import socket
import threading
from pathlib import Path

import pytest

from file_mover.configuration import ConfigurationLoader
from file_mover.control.client import ControlClient
from file_mover.control.dispatcher import CommandDispatcher
from file_mover.control.lock import ProcessLock
from file_mover.control.server import ControlSocketServer
from file_mover.exceptions import ServiceLockError
from file_mover.jobs.models import JobRecord, JobState
from file_mover.jobs.sqlite_repository import SQLiteJobRepository
from file_mover.service import BackgroundMoverService

pytestmark = pytest.mark.skipif(
    not hasattr(socket, "AF_UNIX"), reason="requires AF_UNIX and fcntl (POSIX)"
)


@pytest.mark.requirement("L3-CTL-004")
def test_process_lock_is_exclusive(tmp_path: Path) -> None:
    lock_path = str(tmp_path / "svc.lock")
    first = ProcessLock(lock_path)
    first.acquire()
    try:
        with pytest.raises(ServiceLockError):
            ProcessLock(lock_path).acquire()
    finally:
        first.release()
    # Once released, the lock can be re-acquired.
    reacquired = ProcessLock(lock_path)
    reacquired.acquire()
    reacquired.release()


@pytest.mark.requirement("L2-CTL-008")
def test_process_lock_context_manager(tmp_path: Path) -> None:
    lock_path = str(tmp_path / "svc.lock")
    with ProcessLock(lock_path), pytest.raises(ServiceLockError):
        ProcessLock(lock_path).acquire()


@pytest.mark.requirement("L2-CTL-001")
def test_server_and_client_over_unix_socket(tmp_path: Path) -> None:
    socket_path = str(tmp_path / "control.sock")
    server = ControlSocketServer(socket_path, CommandDispatcher({"health": lambda _a: {"ok": 1}}))
    server.bind()
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        response = ControlClient(socket_path).send("health")
        assert response["success"] is True
        assert response["result"] == {"ok": 1}
    finally:
        server.stop()
        worker.join(timeout=5)
        server.close()


@pytest.mark.requirement("L2-CTL-007")
def test_bind_removes_dead_stale_socket(tmp_path: Path) -> None:
    socket_path = tmp_path / "control.sock"
    # Leave a socket file behind with nothing listening on it.
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stale.bind(str(socket_path))
    stale.close()
    assert socket_path.exists()
    server = ControlSocketServer(str(socket_path), CommandDispatcher({}))
    server.bind()  # must succeed by removing the dead socket
    server.close()


@pytest.mark.requirement("L2-CTL-007")
def test_bind_refuses_non_socket_file(tmp_path: Path) -> None:
    socket_path = tmp_path / "control.sock"
    socket_path.write_text("not a socket", encoding="utf-8")
    server = ControlSocketServer(str(socket_path), CommandDispatcher({}))
    with pytest.raises(ServiceLockError, match="non-socket"):
        server.bind()


@pytest.mark.requirement("L2-CTL-009")
def test_service_run_serves_queries_then_stops(tmp_path: Path) -> None:
    config_text = (
        f"[service]\n"
        f"state_directory = {tmp_path}\n"
        f"socket_path = {tmp_path / 'control.sock'}\n"
        f"[paths]\n"
        f"allowed_source_roots = /recordings\n"
        f"allowed_destination_roots = /processing\n"
    )
    config = ConfigurationLoader().load_text(config_text)
    repository = SQLiteJobRepository(str(tmp_path / "jobs.db"))
    repository.initialize()
    repository.insert_job(
        JobRecord("j1", JobState.QUEUED, "/recordings/s1", "/processing/s1", 1.0, 1.0)
    )
    service = BackgroundMoverService(config, repository=repository)
    worker = threading.Thread(
        target=lambda: service.run(install_signal_handlers=False), daemon=True
    )
    worker.start()
    try:
        assert service.wait_ready(timeout=5)
        client = ControlClient(str(config.service.socket_path))
        assert client.send("health")["result"]["service_state"] == "running"
        status = client.send("status", {"job_id": "j1"})
        assert status["result"]["job"]["state"] == "queued"
        listed = client.send("list", {"state": "active"})
        assert [job["job_id"] for job in listed["result"]["jobs"]] == ["j1"]
        assert client.send("stats", {})["result"]["total_jobs"] == 1
    finally:
        service.request_stop()
        worker.join(timeout=5)
        repository.close()


@pytest.mark.requirement("L2-CLI-008")
def test_service_run_accepts_submission_over_socket(tmp_path: Path) -> None:
    source_root = tmp_path / "recordings"
    dest_root = tmp_path / "processing"
    source_root.mkdir()
    dest_root.mkdir()
    (source_root / "host01.dat").write_bytes(b"payload")
    config_text = (
        f"[service]\n"
        f"state_directory = {tmp_path}\n"
        f"socket_path = {tmp_path / 'control.sock'}\n"
        f"database_path = {tmp_path / 'jobs.db'}\n"
        f"manifest_directory = {tmp_path / 'manifests'}\n"
        f"[paths]\n"
        f"allowed_source_roots = {source_root}\n"
        f"allowed_destination_roots = {dest_root}\n"
        f"[stability]\n"
        f"enabled = false\n"
    )
    config = ConfigurationLoader().load_text(config_text)
    service = BackgroundMoverService(config)
    worker = threading.Thread(
        target=lambda: service.run(install_signal_handlers=False), daemon=True
    )
    worker.start()
    try:
        assert service.wait_ready(timeout=5)
        client = ControlClient(str(config.service.socket_path))
        submitted = client.send(
            "submit",
            {
                "request_id": "req-1",
                "scenario_id": "scn",
                "source": str(source_root),
                "destination": str(dest_root),
            },
        )
        assert submitted["result"]["accepted"] is True
        assert submitted["result"]["claimed_file_count"] == 1
        listed = client.send("list", {"state": "active"})
        assert len(listed["result"]["jobs"]) == 1
    finally:
        service.request_stop()
        worker.join(timeout=5)
