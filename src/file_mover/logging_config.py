"""Centralized, gated, context-aware standard-library logging.

Logging is configured exactly once, at the application boundary (CLI / service startup),
via :func:`configure_logging`. Business classes obtain ``logging.getLogger("file_mover.
<area>")`` and never install handlers of their own; job/file correlation is carried in
**structured fields** (``extra={"job_id": …, "file_id": …}``) via :func:`bind`, not in the
logger name (L3-PY-013/014).

Three separated concerns live here:

* **Level policy** — :class:`LogGate`, a set of per-level booleans computed once by
  :func:`configure_logging`. Hot paths read these flags directly so a disabled level costs
  a single predicted branch — never the standard ``isEnabledFor`` machinery, argument
  evaluation, formatting, or dispatch. A level of ``OFF`` disables everything.
* **Emission + context** — :class:`ContextLogger` / :func:`bind`, a merging
  ``LoggerAdapter`` that carries accumulated context onto every record.
* **Formatting** — :class:`ContextFormatter`, which appends any bound context fields to the
  rendered line and leaves context-free records untouched.

Zero-cost DEBUG: guard hot-path debug lines with ``if __debug__ and GATE.debug:``. Under
``python -O`` (``__debug__ is False``) the whole block — argument evaluation included — is
removed from the compiled bytecode, so production can run with literally no DEBUG overhead
while a non-``-O`` process keeps DEBUG toggleable at the cost of one boolean read.
"""

from __future__ import annotations

import logging
from collections.abc import MutableMapping
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_FILE_MAX_BYTES = 10 * 1024 * 1024
_FILE_BACKUP_COUNT = 5
_CONTEXT_KEYS = ("job_id", "file_id")


class LogGate:
    """Per-level on/off flags, set once at configuration; read at guarded call sites."""

    __slots__ = ("enabled", "debug", "info", "warning", "error")

    def __init__(self) -> None:
        """Start fully disabled until :func:`configure_logging` computes the flags."""
        self.enabled = False
        self.debug = False
        self.info = False
        self.warning = False
        self.error = False

    def _set_from(self, numeric_level: int, *, enabled: bool) -> None:
        """Recompute every flag from the effective numeric level (or all off)."""
        self.enabled = enabled
        self.debug = enabled and numeric_level <= logging.DEBUG
        self.info = enabled and numeric_level <= logging.INFO
        self.warning = enabled and numeric_level <= logging.WARNING
        self.error = enabled and numeric_level <= logging.ERROR


# Module singleton read at every guarded call site (e.g. ``if GATE.info: log.info(...)``).
GATE = LogGate()


class ContextFormatter(logging.Formatter):
    """Formatter that appends bound context fields (``job_id``/``file_id``) when present."""

    def format(self, record: logging.LogRecord) -> str:
        """Render the base line, appending ``key=value`` for any bound context fields."""
        base = super().format(record)
        parts = [f"{key}={getattr(record, key)}" for key in _CONTEXT_KEYS if hasattr(record, key)]
        return f"{base} [{' '.join(parts)}]" if parts else base


class ContextLogger(logging.LoggerAdapter):  # type: ignore[type-arg]
    """A ``LoggerAdapter`` that *merges* its bound context into each record's ``extra``."""

    def process(
        self, msg: Any, kwargs: MutableMapping[str, Any]
    ) -> tuple[Any, MutableMapping[str, Any]]:
        """Merge the adapter's bound context with any per-call ``extra``."""
        merged = dict(self.extra or {})
        call_extra = kwargs.get("extra")
        if call_extra:
            merged.update(call_extra)
        kwargs["extra"] = merged
        return msg, kwargs


def bind(base: logging.Logger | ContextLogger, **context: object) -> ContextLogger:
    """Return a :class:`ContextLogger` carrying ``context`` merged with any already bound.

    Nested binds accumulate: ``bind(bind(log, job_id=j), file_id=f)`` carries both.
    """
    if isinstance(base, ContextLogger):
        return ContextLogger(base.logger, {**(base.extra or {}), **context})
    return ContextLogger(base, dict(context))


def configure_logging(
    level: str = "WARNING",
    *,
    to_stderr: bool = True,
    log_file: Path | None = None,
) -> None:
    """Configure root logging and the :data:`GATE` from ``level``.

    Args:
        level: ``DEBUG``/``INFO``/``WARNING``/``ERROR``/``OFF``; unknown values fall back to
            ``WARNING``. ``OFF`` disables the gate and installs a null handler.
        to_stderr: Emit records to stderr (the systemd journal). Default ``True``.
        log_file: When given, also emit to a size-rotating file at this path; a failure to
            open it falls back to stderr rather than aborting startup.
    """
    off = level.strip().upper() == "OFF"
    numeric = _numeric_level(level)
    GATE._set_from(numeric, enabled=not off)

    if off:
        logging.basicConfig(
            level=logging.CRITICAL + 1, handlers=[logging.NullHandler()], force=True
        )
        return

    formatter = ContextFormatter(_LOG_FORMAT)
    handlers: list[logging.Handler] = []
    if to_stderr:
        handlers.append(_stderr_handler(formatter))
    if log_file is not None:
        file_handler = _file_handler(log_file, formatter)
        if file_handler is not None:
            handlers.append(file_handler)
    if not handlers:
        handlers.append(_stderr_handler(formatter))  # never leave the service silent

    logging.basicConfig(level=numeric, handlers=handlers, force=True)


def _numeric_level(level: str) -> int:
    """Resolve a level name to its numeric value, defaulting to ``WARNING``."""
    numeric = logging.getLevelName(level.strip().upper())
    return numeric if isinstance(numeric, int) else logging.WARNING


def _stderr_handler(formatter: logging.Formatter) -> logging.Handler:
    """Build a stderr stream handler with the shared context formatter."""
    handler = logging.StreamHandler()
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
