"""Removal of a job's ``.swit-partial-`` temporary destination files.

Shared by startup recovery (drop stale partials when resume is disabled) and the
``cancel`` lifecycle command (discard a paused job's partial). Kept as one small helper so
the "find and remove this job's partials" concern lives in exactly one place.
"""

from __future__ import annotations

import logging
from pathlib import Path


def remove_job_partials(
    destination_root: str | Path,
    job_id: str,
    temporary_file_prefix: str,
    *,
    logger: logging.Logger | None = None,
) -> int:
    """Remove every ``<prefix><job_id>-*`` partial under ``destination_root``.

    Returns the number of files removed; a partial that cannot be removed is logged and
    skipped rather than raising, so cleanup never aborts the caller.
    """
    root = Path(destination_root)
    if not root.exists():
        return 0
    removed = 0
    for path in root.rglob(f"{temporary_file_prefix}{job_id}-*"):
        try:
            path.unlink()
        except OSError:
            if logger is not None:
                logger.warning("could not remove partial file %s", path)
        else:
            removed += 1
    return removed
