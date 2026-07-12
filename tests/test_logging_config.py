"""Tests for gated, context-aware logging configuration."""

from __future__ import annotations

import logging

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
def test_split_routes_info_to_stdout_and_warning_to_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("INFO")
    log = logging.getLogger("file_mover.test.split")
    log.info("an-info-event")
    log.warning("a-warning-event")
    for handler in logging.getLogger().handlers:
        handler.flush()
    captured = capsys.readouterr()
    assert "an-info-event" in captured.out and "an-info-event" not in captured.err
    assert "a-warning-event" in captured.err and "a-warning-event" not in captured.out


@pytest.mark.requirement("L3-PY-013")
def test_split_installs_two_stream_handlers() -> None:
    import sys

    configure_logging("INFO")
    handlers = logging.getLogger().handlers
    assert len(handlers) == 2
    streams = {getattr(handler, "stream", None) for handler in handlers}
    assert sys.stdout in streams and sys.stderr in streams  # no file handler
