"""Tests for gated, context-aware logging configuration."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from file_mover.logging_config import (
    GATE,
    ContextFormatter,
    bind,
    configure_logging,
)


@pytest.fixture(autouse=True)
def _restore_logging() -> object:
    """Snapshot/restore root logging and the GATE so tests don't leak global state."""
    root = logging.getLogger()
    saved_level, saved_handlers = root.level, root.handlers[:]
    saved_gate = (GATE.enabled, GATE.debug, GATE.info, GATE.warning, GATE.error)
    yield
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)
    GATE.enabled, GATE.debug, GATE.info, GATE.warning, GATE.error = saved_gate


@pytest.mark.requirement("L3-PY-014")
def test_gate_flags_track_the_level() -> None:
    configure_logging("DEBUG")
    assert (GATE.enabled, GATE.debug, GATE.info, GATE.warning, GATE.error) == (
        True,
        True,
        True,
        True,
        True,
    )
    configure_logging("WARNING")
    assert (GATE.debug, GATE.info, GATE.warning) == (False, False, True)
    configure_logging("ERROR")
    assert (GATE.info, GATE.warning, GATE.error) == (False, False, True)


@pytest.mark.requirement("L3-PY-014")
def test_off_disables_the_gate_and_installs_null_handler() -> None:
    configure_logging("OFF")
    assert GATE.enabled is False
    assert (GATE.debug, GATE.info, GATE.warning, GATE.error) == (False, False, False, False)
    handlers = logging.getLogger().handlers
    assert len(handlers) == 1 and isinstance(handlers[0], logging.NullHandler)


@pytest.mark.requirement("L3-PY-014")
def test_context_formatter_appends_bound_fields() -> None:
    formatter = ContextFormatter("%(message)s")
    plain = logging.LogRecord("x", logging.INFO, __file__, 1, "no context", None, None)
    assert formatter.format(plain) == "no context"
    with_ctx = logging.LogRecord("x", logging.INFO, __file__, 1, "with context", None, None)
    with_ctx.job_id, with_ctx.file_id = "J1", "F2"
    rendered = formatter.format(with_ctx)
    assert rendered == "with context [job_id=J1 file_id=F2]"


@pytest.mark.requirement("L3-PY-014")
def test_bind_merges_nested_context(caplog: pytest.LogCaptureFixture) -> None:
    GATE.enabled = GATE.info = True
    base = logging.getLogger("file_mover.test.bind")
    file_log = bind(bind(base, job_id="J1"), file_id="F2")  # nested binds accumulate
    with caplog.at_level(logging.INFO, logger="file_mover.test.bind"):
        file_log.info("event")
    record = caplog.records[-1]
    assert record.job_id == "J1" and record.file_id == "F2"  # both fields on the record


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
