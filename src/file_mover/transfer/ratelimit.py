"""``RateLimiter`` — a thread-safe token-bucket throughput limiter (stdlib only).

There is no portable operating-system syscall to rate-limit ordinary file I/O. The
kernel options that exist are ill-suited to this service: `tc`/traffic-shaping is
per-interface, coarse, needs root, and is not process-specific; cgroup v2 `io.max`
throttles *block-device* I/O, not the NFS *network* path the mover actually uses. So —
like `rsync --bwlimit`, `scp -l`, `curl --limit-rate`, and `pv -L` — the limit is enforced
in userspace, in the buffered copy loop, by a token bucket (L2-BWL-001, L3-PY-011).

A bucket fills at ``bytes_per_second`` tokens per second up to a one-second burst
capacity. :meth:`throttle` accounts for the bytes just written and sleeps exactly long
enough to keep the average rate at or below the limit. A single limiter is shared by every
concurrent file copy, so the cap is **global** across the service, not per file
(L2-BWL-003). A rate of ``0`` means unlimited — :meth:`throttle` returns immediately with
no locking cost worth avoiding (L2-BWL-004). :meth:`set_rate` changes the limit live, which
is how the ``throttle`` control command adjusts throughput without a restart (L2-BWL-002).

The clock and sleep function are injected so tests drive pacing deterministically without
real wall-clock delays; production uses :func:`time.monotonic` and :func:`time.sleep`.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

# Burst capacity as a multiple of the per-second rate. One second of headroom lets a copy
# that briefly stalls (e.g. an NFS hiccup) catch back up to the average without exceeding
# it over any multi-second window.
_BURST_SECONDS = 1.0


class RateLimiter:
    """A thread-safe token-bucket limiter capping aggregate copy throughput."""

    def __init__(
        self,
        bytes_per_second: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        """Initialise the limiter.

        Args:
            bytes_per_second: Throughput ceiling in bytes per second; ``0`` (or negative)
                means unlimited.
            clock: Monotonic time source in seconds; injectable for deterministic tests.
            sleeper: Blocking sleep function; injectable for deterministic tests.
        """
        self._lock = threading.Lock()
        self._clock = clock
        self._sleeper = sleeper
        self._rate = max(0, int(bytes_per_second))
        self._tokens = float(self._rate)
        self._updated_at = clock()

    @property
    def bytes_per_second(self) -> int:
        """The current throughput ceiling (``0`` means unlimited)."""
        with self._lock:
            return self._rate

    def is_unlimited(self) -> bool:
        """Whether the limiter imposes no ceiling (rate ``0``)."""
        with self._lock:
            return self._rate <= 0

    def set_rate(self, bytes_per_second: int) -> int:
        """Change the throughput ceiling in place and return the new rate.

        The change takes effect for the next :meth:`throttle` call, so it affects copies
        already in flight — this is what makes the limit *dynamic* (L2-BWL-002).

        Args:
            bytes_per_second: New ceiling in bytes per second; ``0`` means unlimited.

        Returns:
            The applied rate (clamped to ``>= 0``).
        """
        with self._lock:
            self._rate = max(0, int(bytes_per_second))
            # Never let the bucket carry more than one burst of the new (possibly lower)
            # rate, and reset the fill clock so elapsed idle time is not paid out at the
            # old rate.
            self._tokens = min(self._tokens, self._rate * _BURST_SECONDS)
            self._updated_at = self._clock()
            return self._rate

    def throttle(self, byte_count: int) -> None:
        """Account for ``byte_count`` bytes and block long enough to honour the limit.

        Refills the bucket for the time elapsed since the last call, spends
        ``byte_count`` tokens, and — if the bucket cannot cover them — sleeps for exactly
        the time the deficit needs to accrue at the current rate. A no-op when unlimited
        or when ``byte_count`` is not positive.

        Args:
            byte_count: The number of bytes just transferred.
        """
        if byte_count <= 0:
            return
        with self._lock:
            if self._rate <= 0:
                return
            now = self._clock()
            capacity = self._rate * _BURST_SECONDS
            self._tokens = min(capacity, self._tokens + (now - self._updated_at) * self._rate)
            self._updated_at = now
            if self._tokens >= byte_count:
                self._tokens -= byte_count
                return
            deficit = byte_count - self._tokens
            self._tokens = 0.0
            wait_seconds = deficit / self._rate
        # Sleep outside the lock so other copy threads can keep accounting; the deficit
        # tokens are treated as spent, so the average rate stays bounded.
        self._sleeper(wait_seconds)
