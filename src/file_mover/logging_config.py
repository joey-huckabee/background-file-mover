"""Centralized standard-library logging configuration.

Logging is configured exactly once, at the application boundary (CLI / service startup),
via :func:`configure_logging`. Diagnostics are written to stderr so machine output on
stdout stays clean (L2-CLI-006). Business classes obtain
``logging.getLogger("file_mover.<area>")`` and never install handlers of their own.

The service resolves the level and destinations from the ``[logging]`` configuration
section (an explicit CLI ``-v``/``--log-level`` takes precedence); see
:func:`file_mover.cli._handle_service_run` (L3-PY-013).
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_FILE_MAX_BYTES = 10 * 1024 * 1024
_FILE_BACKUP_COUNT = 5


def configure_logging(
    level: str = "WARNING",
    *,
    to_stderr: bool = True,
    log_file: Path | None = None,
) -> None:
    """Configure root logging at ``level`` to stderr and/or a rotating file.

    Args:
        level: One of ``DEBUG``/``INFO``/``WARNING``/``ERROR``; unknown values fall back
            to ``WARNING``.
        to_stderr: Emit records to stderr (the systemd journal). Default ``True``.
        log_file: When given, also emit to a size-rotated file at this path. If the file
            cannot be opened, logging falls back to stderr rather than failing startup.
    """
    numeric = logging.getLevelName(level.upper())
    if not isinstance(numeric, int):
        numeric = logging.WARNING

    formatter = logging.Formatter(_LOG_FORMAT)
    handlers: list[logging.Handler] = []
    if to_stderr:
        handlers.append(_stderr_handler(formatter))
    if log_file is not None:
        file_handler = _file_handler(log_file, formatter)
        if file_handler is not None:
            handlers.append(file_handler)
    if not handlers:
        # Never leave the service silent (e.g. journal off and the file unopenable).
        handlers.append(_stderr_handler(formatter))

    logging.basicConfig(level=numeric, handlers=handlers, force=True)


def _stderr_handler(formatter: logging.Formatter) -> logging.Handler:
    """Build a stderr stream handler with the shared format."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)
    return handler


def _file_handler(log_file: Path, formatter: logging.Formatter) -> logging.Handler | None:
    """Build a rotating file handler, or ``None`` if the file cannot be opened."""
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_file,
            maxBytes=_FILE_MAX_BYTES,
            backupCount=_FILE_BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError:
        return None  # fall back to stderr; a log path issue must not abort startup
    handler.setFormatter(formatter)
    return handler
