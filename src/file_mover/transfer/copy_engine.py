"""``BufferedFileCopyEngine`` — copy to a temporary destination, then publish atomically.

Each file is copied into a ``.swit-partial-<job>-<file>`` temporary file created
exclusively (``O_CREAT | O_EXCL``, plus ``O_NOFOLLOW`` where available) so an existing or
symlinked destination is never overwritten (L2-COPY-005/006, L2-POSIX-008). The temporary
file is flushed and ``fsync``ed before it is atomically published with ``Path.replace``
and the destination directory is fsynced where the platform allows it
(L2-DPR-002/005, L2-POSIX-009/010/011).

The copy itself uses one of two strategies (L2-COPY-011):

* **Kernel-assisted** (``use_kernel_copy=True``, the default): ``os.copy_file_range``
  moves bytes directly between the two file descriptors inside the kernel, without
  bouncing every byte through this process — faster for large files. It is attempted only
  when the syscall is available, and any "not supported" outcome (missing syscall,
  cross-filesystem, or a filesystem that declines it) falls back cleanly to the buffered
  loop (L3-PY-009). Genuine I/O errors are not masked — they propagate.
* **Buffered** (the fallback, and always used when disabled or unavailable): a bounded
  ``read``/``write`` loop that copies at most one buffer at a time (L2-COPY-001).

When a :class:`~file_mover.transfer.ratelimit.RateLimiter` with a non-zero rate is
supplied, the engine **forces the buffered strategy** and paces it: kernel-assisted copy
moves bytes entirely inside the kernel, so there is no userspace loop in which to apply a
throttle. The buffered loop consumes tokens after each write, keeping aggregate throughput
under the configured ceiling (L2-BWL-001, L3-PY-011).

Both strategies produce byte-identical output; the destination is re-hashed afterwards
regardless, so integrity verification is unaffected by the strategy.
"""

from __future__ import annotations

import errno
import os
from dataclasses import dataclass
from pathlib import Path

from file_mover.exceptions import CopyError, DestinationPublishError, DestinationWriteError
from file_mover.transfer.ratelimit import RateLimiter


def _resolve_errnos(*names: str) -> frozenset[int]:
    """Resolve the given errno names that exist on this platform."""
    return frozenset(getattr(errno, name) for name in names if hasattr(errno, name))


# ``copy_file_range`` outcomes that mean "this pair/filesystem cannot be kernel-copied";
# on any of these we fall back to the buffered loop rather than failing the transfer.
# EXDEV in particular is expected across two different mounts on older kernels.
_KERNEL_FALLBACK_ERRNOS = _resolve_errnos("ENOSYS", "EOPNOTSUPP", "ENOTSUP", "EXDEV", "EINVAL")


def _kernel_copy_available() -> bool:
    """Whether ``os.copy_file_range`` exists on this interpreter/platform."""
    return hasattr(os, "copy_file_range")


@dataclass(frozen=True)
class CopyOutcome:
    """The result of copying a file to its temporary destination."""

    temporary_path: Path
    bytes_written: int


class BufferedFileCopyEngine:
    """Copies files into exclusively-created temporary destinations and publishes them."""

    def __init__(
        self,
        *,
        buffer_size_bytes: int,
        temporary_file_prefix: str,
        use_kernel_copy: bool = True,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        """Initialise the copy engine.

        Args:
            buffer_size_bytes: Bounded copy-buffer / kernel-copy chunk size.
            temporary_file_prefix: Prefix for in-progress destination files.
            use_kernel_copy: Attempt ``os.copy_file_range`` (with buffered fallback) when
                available; set ``False`` to always use the buffered loop.
            rate_limiter: Optional shared throughput limiter. When it has a non-zero rate
                the engine forces the buffered strategy and paces each write through it;
                an unlimited (or absent) limiter imposes no ceiling and no overhead.
        """
        self._buffer_size_bytes = buffer_size_bytes
        self._temporary_file_prefix = temporary_file_prefix
        self._use_kernel_copy = use_kernel_copy
        self._rate_limiter = rate_limiter

    def copy_to_temp(
        self, source: Path, destination_dir: Path, job_id: str, file_id: str
    ) -> CopyOutcome:
        """Copy ``source`` into a fresh temporary file in ``destination_dir``.

        Returns:
            The temporary path and the exact number of bytes written.

        Raises:
            DestinationWriteError: If the temporary file cannot be created exclusively.
            CopyError: If opening the source, reading, or writing fails.
        """
        destination_dir.mkdir(parents=True, exist_ok=True)
        temporary = destination_dir / f"{self._temporary_file_prefix}{job_id}-{file_id}"
        destination_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            destination_fd = os.open(temporary, destination_flags, 0o644)
        except OSError as error:
            raise DestinationWriteError(
                f"cannot create temporary destination {temporary}: {error}"
            ) from error

        try:
            source_fd = os.open(source, os.O_RDONLY)
        except OSError as error:
            os.close(destination_fd)
            raise CopyError(f"cannot open source {source}: {error}") from error

        try:
            bytes_written = self._copy(source_fd, destination_fd)
            os.fsync(destination_fd)
        except OSError as error:
            os.close(source_fd)
            os.close(destination_fd)
            raise CopyError(f"copy failed for {source}: {error}") from error
        os.close(source_fd)
        os.close(destination_fd)
        return CopyOutcome(temporary_path=temporary, bytes_written=bytes_written)

    def _rate_limited(self) -> bool:
        """Whether an active (non-zero) throughput limit is in force."""
        return self._rate_limiter is not None and not self._rate_limiter.is_unlimited()

    def _copy(self, source_fd: int, destination_fd: int) -> int:
        """Copy from ``source_fd`` to ``destination_fd`` and return the byte count."""
        # A throughput limit can only be applied in the userspace buffered loop, so an
        # active limiter forces the buffered strategy over kernel-assisted copy.
        if self._use_kernel_copy and _kernel_copy_available() and not self._rate_limited():
            return self._copy_via_kernel(source_fd, destination_fd)
        return _copy_via_buffer(
            source_fd, destination_fd, self._buffer_size_bytes, self._rate_limiter
        )

    def _copy_via_kernel(self, source_fd: int, destination_fd: int) -> int:
        """Kernel-assisted copy with a safe buffered fallback on unsupported outcomes."""
        total = 0
        try:
            while True:
                copied = os.copy_file_range(source_fd, destination_fd, self._buffer_size_bytes)
                if copied == 0:
                    break
                total += copied
        except OSError as error:
            if error.errno not in _KERNEL_FALLBACK_ERRNOS:
                raise  # a genuine I/O error — do not mask it
            # Discard any partial output and copy the whole file with the buffered loop.
            os.ftruncate(destination_fd, 0)
            os.lseek(destination_fd, 0, os.SEEK_SET)
            os.lseek(source_fd, 0, os.SEEK_SET)
            return _copy_via_buffer(
                source_fd, destination_fd, self._buffer_size_bytes, self._rate_limiter
            )
        return total

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


def _copy_via_buffer(
    source_fd: int,
    destination_fd: int,
    buffer_size_bytes: int,
    rate_limiter: RateLimiter | None = None,
) -> int:
    """Copy with a bounded read/write loop; return the exact byte count.

    When ``rate_limiter`` is supplied, each written chunk is accounted through it after
    the write so aggregate throughput stays under the configured ceiling (a no-op when the
    limiter is unlimited).
    """
    total = 0
    while True:
        chunk = os.read(source_fd, buffer_size_bytes)
        if not chunk:
            break
        _write_all(destination_fd, chunk)
        total += len(chunk)
        if rate_limiter is not None:
            rate_limiter.throttle(len(chunk))
    return total


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
