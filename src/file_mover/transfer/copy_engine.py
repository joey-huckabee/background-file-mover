"""``BufferedFileCopyEngine`` — bounded-memory copy to a temporary destination.

Each file is copied in a bounded read/write loop into a ``.swit-partial-<job>-<file>``
temporary file created exclusively (``O_CREAT | O_EXCL``, plus ``O_NOFOLLOW`` where
available) so an existing or symlinked destination is never overwritten (L2-COPY-005/006,
L2-POSIX-008). The temporary file is flushed and ``fsync``ed before it is atomically
published with ``Path.replace`` and the destination directory is fsynced where the
platform allows it (L2-DPR-002/005, L2-POSIX-009/010/011).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from file_mover.exceptions import CopyError, DestinationPublishError, DestinationWriteError


@dataclass(frozen=True)
class CopyOutcome:
    """The result of copying a file to its temporary destination."""

    temporary_path: Path
    bytes_written: int


class BufferedFileCopyEngine:
    """Copies files into exclusively-created temporary destinations and publishes them."""

    def __init__(self, *, buffer_size_bytes: int, temporary_file_prefix: str) -> None:
        """Initialise the copy engine.

        Args:
            buffer_size_bytes: Bounded copy-buffer size.
            temporary_file_prefix: Prefix for in-progress destination files.
        """
        self._buffer_size_bytes = buffer_size_bytes
        self._temporary_file_prefix = temporary_file_prefix

    def copy_to_temp(
        self, source: Path, destination_dir: Path, job_id: str, file_id: str
    ) -> CopyOutcome:
        """Copy ``source`` into a fresh temporary file in ``destination_dir``.

        Returns:
            The temporary path and the exact number of bytes written.

        Raises:
            DestinationWriteError: If the temporary file cannot be created exclusively.
            CopyError: If reading or writing fails.
        """
        destination_dir.mkdir(parents=True, exist_ok=True)
        temporary = destination_dir / f"{self._temporary_file_prefix}{job_id}-{file_id}"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_NOFOLLOW", 0)  # POSIX-only hardening
        try:
            descriptor = os.open(temporary, flags, 0o644)
        except OSError as error:
            raise DestinationWriteError(
                f"cannot create temporary destination {temporary}: {error}"
            ) from error

        bytes_written = 0
        try:
            with source.open("rb") as reader:
                while True:
                    chunk = reader.read(self._buffer_size_bytes)
                    if not chunk:
                        break
                    _write_all(descriptor, chunk)
                    bytes_written += len(chunk)
            os.fsync(descriptor)
        except OSError as error:
            os.close(descriptor)
            raise CopyError(f"copy failed for {source}: {error}") from error
        os.close(descriptor)
        return CopyOutcome(temporary_path=temporary, bytes_written=bytes_written)

    def publish(self, temporary: Path, final: Path) -> None:
        """Atomically publish ``temporary`` as ``final`` and fsync the directory.

        Raises:
            DestinationPublishError: If the rename fails.
        """
        try:
            temporary.replace(final)
        except OSError as error:
            raise DestinationPublishError(f"cannot publish {final}: {error}") from error
        _fsync_directory(final.parent)


def _write_all(descriptor: int, data: bytes) -> None:
    """Write all of ``data`` to ``descriptor``, handling short writes."""
    view = memoryview(data)
    while view:
        written = os.write(descriptor, view)
        view = view[written:]


def _fsync_directory(directory: Path) -> None:
    """Best-effort fsync of a directory (a no-op where the platform disallows it)."""
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return  # e.g. Windows cannot open a directory as a file descriptor
    try:
        os.fsync(descriptor)
    except OSError:
        pass  # some filesystems reject directory fsync
    finally:
        os.close(descriptor)
