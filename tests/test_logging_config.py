"""Tests for centralized logging configuration (level, stderr, rotating file)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from file_mover.logging_config import configure_logging


@pytest.fixture(autouse=True)
def _restore_logging() -> object:
    """Snapshot and restore root logging so these tests don't leak global state."""
    root = logging.getLogger()
    saved_level, saved_handlers = root.level, root.handlers[:]
    yield
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)


@pytest.mark.requirement("L3-PY-013")
def test_level_is_applied_and_unknown_falls_back() -> None:
    configure_logging("DEBUG")
    assert logging.getLogger().level == logging.DEBUG
    configure_logging("nonsense")
    assert logging.getLogger().level == logging.WARNING


@pytest.mark.requirement("L3-PY-013")
def test_writes_to_rotating_file(tmp_path: Path) -> None:
    log_file = tmp_path / "logs" / "file-mover.log"  # parent created on demand
    configure_logging("INFO", to_stderr=False, log_file=log_file)
    logging.getLogger("file_mover.test").info("hello-from-file")
    for handler in logging.getLogger().handlers:
        handler.flush()
    assert log_file.exists()
    assert "hello-from-file" in log_file.read_text(encoding="utf-8")


@pytest.mark.requirement("L3-PY-013")
def test_never_silent_when_all_destinations_off() -> None:
    configure_logging("INFO", to_stderr=False, log_file=None)
    assert logging.getLogger().handlers  # a stderr fallback is always installed


@pytest.mark.requirement("L3-PY-013")
def test_unopenable_log_file_falls_back_without_raising(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_bytes(b"x")  # a file where the log directory is expected
    configure_logging("INFO", to_stderr=False, log_file=blocker / "x.log")
    assert logging.getLogger().handlers  # falls back to stderr, no exception
