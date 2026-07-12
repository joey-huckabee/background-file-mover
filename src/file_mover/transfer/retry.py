"""``ErrorClassifier`` and bounded exponential backoff.

An operational error is classified into an
:class:`~file_mover.jobs.models.ErrorDisposition` from its type and ``errno`` before any
retry decision is made (L2-RTY-001/002): transient NFS/network errors are retryable,
operator-remediable errors (out of space, read-only, permission) are retained for
intervention, and clear request/config errors reject the job. The default is the
conservative *retain* — a transfer is never abandoned in a way that could lose data.

The ``errno`` constants are looked up defensively so the module imports on any platform
(several are POSIX-only).
"""

from __future__ import annotations

import errno

from file_mover.exceptions import IntegrityError
from file_mover.jobs.models import ErrorDisposition


def _errnos(*names: str) -> frozenset[int]:
    """Resolve the given errno names that exist on this platform."""
    return frozenset(getattr(errno, name) for name in names if hasattr(errno, name))


# Transient conditions worth retrying with backoff.
_RETRYABLE = _errnos(
    "ESTALE",
    "EIO",
    "ETIMEDOUT",
    "ECONNRESET",
    "ECONNREFUSED",
    "EHOSTUNREACH",
    "ENETUNREACH",
    "EBUSY",
    "EAGAIN",
)
# Conditions that need operator action; retain the claimed source and fail.
_RETAIN = _errnos("ENOSPC", "EDQUOT", "EROFS", "EACCES", "EPERM")
# Clear request/configuration errors: reject the job.
_REJECT = _errnos("ENOTDIR", "EINVAL", "EXDEV", "ENAMETOOLONG")


class ErrorClassifier:
    """Maps an operational error to an :class:`ErrorDisposition`."""

    def classify(self, error: Exception) -> ErrorDisposition:
        """Classify ``error`` into a retry/retain/reject disposition.

        Integrity failures always retain (both source and temporary destination are
        kept); otherwise the disposition follows the underlying ``errno``, defaulting to
        the conservative *retain-and-fail*.
        """
        if isinstance(error, IntegrityError):
            return ErrorDisposition.RETAIN_AND_FAIL
        code = _errno_of(error)
        if code in _RETRYABLE:
            return ErrorDisposition.RETRY
        if code in _RETAIN:
            return ErrorDisposition.RETAIN_AND_FAIL
        if code in _REJECT:
            return ErrorDisposition.REJECT_JOB
        return ErrorDisposition.RETAIN_AND_FAIL


def _errno_of(error: BaseException) -> int | None:
    """Return the first ``errno`` found on ``error`` or its exception chain."""
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, OSError) and current.errno is not None:
            return current.errno
        current = current.__cause__
    return None


def compute_backoff(attempt: int, *, initial_seconds: float, maximum_seconds: float) -> float:
    """Return the backoff delay for a 1-based ``attempt`` number, capped at the maximum."""
    if attempt < 1:
        return initial_seconds
    delay = initial_seconds * (2.0 ** (attempt - 1))
    return min(delay, maximum_seconds)
