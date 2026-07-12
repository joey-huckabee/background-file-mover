"""``ManifestWriter`` — durable, atomically-replaced JSON transfer manifests.

A manifest is a human-readable inventory and integrity record for one job. It is written
through a temporary file that is flushed, ``fsync``ed, and then atomically renamed over
the final name (L3-INT-004), so a reader never observes a half-written manifest.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from file_mover.exceptions import ManifestError

_MANIFEST_SCHEMA_VERSION = 1


class ManifestWriter:
    """Writes per-job manifests atomically into a manifest directory."""

    def __init__(self, manifest_directory: Path) -> None:
        """Initialise the writer.

        Args:
            manifest_directory: Directory the manifests are written into.
        """
        self._directory = Path(manifest_directory)

    @property
    def schema_version(self) -> int:
        """The manifest schema version this writer emits."""
        return _MANIFEST_SCHEMA_VERSION

    def write(self, job_id: str, manifest: dict[str, Any]) -> Path:
        """Write ``manifest`` for ``job_id`` atomically and return its path.

        Raises:
            ManifestError: If the manifest cannot be written or replaced.
        """
        final = self._directory / f"{job_id}.json"
        temporary = self._directory / f".{job_id}.json.tmp"
        payload = {"schema_version": _MANIFEST_SCHEMA_VERSION, **manifest}
        data = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
            try:
                os.write(descriptor, data)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            temporary.replace(final)
        except OSError as error:
            raise ManifestError(f"cannot write manifest for {job_id}: {error}") from error
        return final
