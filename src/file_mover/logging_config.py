"""Centralized standard-library logging configuration.

Planned for Milestone 3. Logging is configured exactly once at the application
boundary (CLI / service startup); business classes obtain
``logging.getLogger("file_mover.<area>")`` and never install handlers. Job and file
identifiers travel as structured ``extra`` fields rather than in the logger name, so
records correlate across a job without proliferating randomly-named loggers.

See ``docs/ARCHITECTURE.md`` (logging levels) and ``docs/ROADMAP.md`` (M3).
"""

from __future__ import annotations
