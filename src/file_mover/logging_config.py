"""Centralized standard-library logging configuration.

Logging is configured exactly once, at the application boundary (CLI / service startup),
via :func:`configure_logging`. Diagnostics are written to stderr so machine output on
stdout stays clean (L2-CLI-006). Business classes obtain
``logging.getLogger("file_mover.<area>")`` and never install handlers of their own.
"""

from __future__ import annotations

import logging
import sys

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(level: str = "WARNING") -> None:
    """Configure root logging to stderr at ``level``.

    Args:
        level: One of ``DEBUG``/``INFO``/``WARNING``/``ERROR``; unknown values fall back
            to ``WARNING``.
    """
    numeric = logging.getLevelName(level.upper())
    if not isinstance(numeric, int):
        numeric = logging.WARNING
    logging.basicConfig(level=numeric, stream=sys.stderr, format=_LOG_FORMAT, force=True)
