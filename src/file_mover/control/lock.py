"""``ProcessLock`` — a singleton advisory lock guaranteeing one live service.

Implemented with ``fcntl.flock`` on a lock file (L3-CTL-004): the first process holds an
exclusive non-blocking lock; a second acquisition fails immediately with
:class:`~file_mover.exceptions.ServiceLockError` (L2-CTL-009). The module imports on any
platform — ``fcntl`` is POSIX-only, so it is imported defensively and acquisition refuses
to run without it.
"""

from __future__ import annotations

import os

from file_mover.exceptions import ServiceLockError

try:
    import fcntl
except ImportError:  # pragma: no cover - fcntl is POSIX-only
    fcntl = None  # type: ignore[assignment]


class ProcessLock:
    """An exclusive, non-blocking file lock held for the lifetime of the service."""

    def __init__(self, lock_path: str) -> None:
        """Initialise the lock.

        Args:
            lock_path: Path of the lock file (its containing directory must exist).
        """
        self._path = lock_path
        self._fd: int | None = None

    def acquire(self) -> None:
        """Acquire the exclusive lock.

        Raises:
            ServiceLockError: If ``fcntl`` is unavailable, or another process holds it.
        """
        if fcntl is None:  # pragma: no cover - POSIX-only guard
            raise ServiceLockError("the process lock requires a POSIX platform")
        try:
            descriptor = os.open(self._path, os.O_CREAT | os.O_RDWR, 0o644)
        except OSError as error:
            raise ServiceLockError(f"cannot open lock file {self._path}: {error}") from error
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            os.close(descriptor)
            raise ServiceLockError(
                f"another service instance holds the lock at {self._path}"
            ) from error
        os.ftruncate(descriptor, 0)
        os.write(descriptor, f"{os.getpid()}\n".encode())
        self._fd = descriptor

    def release(self) -> None:
        """Release the lock and close the descriptor (idempotent)."""
        if self._fd is None:
            return
        if fcntl is not None:  # pragma: no branch - always true once acquired
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        os.close(self._fd)
        self._fd = None

    def __enter__(self) -> ProcessLock:
        """Acquire the lock on entry."""
        self.acquire()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        """Release the lock on exit (exception info is not consumed)."""
        self.release()
