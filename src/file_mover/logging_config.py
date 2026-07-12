"""Centralized, gated, context-aware standard-library logging.

Logging is configured exactly once, at the service boundary, via :func:`configure_logging`.
Business classes obtain ``logging.getLogger("file_mover.<area>")`` and never install handlers
of their own; job/file correlation is carried in **structured fields**
(``extra={"job_id": …, "file_id": …}``) via :func:`bind`, not in the logger name
(L3-PY-013/014).

Twelve-factor: the service writes its event stream and lets the environment route it. It
manages no log files — ``INFO``/``DEBUG`` go to **stdout** and ``WARNING``/``ERROR`` to
**stderr** (the daemon has no result stream on stdout to protect). The CLI is separate: it
keeps stdout for its command *result* and its own diagnostics on stderr.

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
import sys
from collections.abc import MutableMapping
from typing import Any

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
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


def configure_logging(level: str = "WARNING") -> None:
    """Configure the :data:`GATE` and route the event stream to stdout/stderr.

    Twelve-factor: the application writes its event stream and lets the environment
    (systemd's journal, a log shipper) route and store it. Records below ``WARNING``
    (``INFO``/``DEBUG``) go to **stdout** and ``WARNING``/``ERROR``/``CRITICAL`` go to
    **stderr** — the daemon has no result stream on stdout to protect. The app manages no
    log files (L3-PY-013).

    Args:
        level: ``DEBUG``/``INFO``/``WARNING``/``ERROR``/``OFF``; unknown values fall back to
            ``WARNING``. ``OFF`` disables the gate and installs a null handler.
    """
    off = level.strip().upper() == "OFF"
    numeric = _numeric_level(level)
    GATE.enabled = not off
    GATE.debug = not off and numeric <= logging.DEBUG
    GATE.info = not off and numeric <= logging.INFO
    GATE.warning = not off and numeric <= logging.WARNING
    GATE.error = not off and numeric <= logging.ERROR

    if off:
        logging.basicConfig(
            level=logging.CRITICAL + 1, handlers=[logging.NullHandler()], force=True
        )
        return

    formatter = ContextFormatter(_LOG_FORMAT)
    stdout_handler = _stream_handler(sys.stdout, formatter, numeric)
    stdout_handler.addFilter(_below_warning)  # INFO/DEBUG only; WARNING+ go to stderr
    stderr_handler = _stream_handler(sys.stderr, formatter, logging.WARNING)
    logging.basicConfig(level=numeric, handlers=[stdout_handler, stderr_handler], force=True)


def _numeric_level(level: str) -> int:
    """Resolve a level name to its numeric value, defaulting to ``WARNING``."""
    numeric = logging.getLevelName(level.strip().upper())
    return numeric if isinstance(numeric, int) else logging.WARNING


def _stream_handler(
    stream: Any, formatter: logging.Formatter, level: int
) -> logging.StreamHandler[Any]:
    """Build a stream handler at ``level`` with the shared context formatter."""
    handler = logging.StreamHandler(stream)
    handler.setFormatter(formatter)
    handler.setLevel(level)
    return handler


def _below_warning(record: logging.LogRecord) -> bool:
    """Filter passing only records below ``WARNING`` (stdout gets INFO/DEBUG)."""
    return record.levelno < logging.WARNING
