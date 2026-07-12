"""``JobControlSignals`` — thread-safe pause/cancel delivery to in-flight copies.

Control commands (``pause``/``cancel``) arrive on the control-server thread pool while a
job may be copying on the scheduler thread. There is no operating-system primitive to
pause or cancel a regular-file copy, so this registry is the bridge for **cooperative
cancellation**: a handler records a :class:`~file_mover.jobs.models.ControlSignal` for a
job id, and the copy loop polls it at each buffer boundary via the callback from
:meth:`interrupt_check_for`, raising :class:`CopyInterrupted` at a safe point
(L2-LIF-002). The signal is a small, bounded ``dict`` guarded by a lock — the copy path
never blocks on it beyond a dictionary lookup.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from file_mover.exceptions import CopyInterrupted
from file_mover.jobs.models import ControlSignal


class JobControlSignals:
    """A thread-safe map of job id → pending pause/cancel signal."""

    def __init__(self) -> None:
        """Initialise an empty, lock-guarded signal registry."""
        self._lock = threading.Lock()
        self._signals: dict[str, ControlSignal] = {}

    def request(self, job_id: str, signal: ControlSignal) -> None:
        """Record a pending ``signal`` for ``job_id`` (overwrites any earlier request)."""
        with self._lock:
            self._signals[job_id] = signal

    def poll(self, job_id: str) -> ControlSignal | None:
        """Return the pending signal for ``job_id``, or ``None`` if none is set."""
        with self._lock:
            return self._signals.get(job_id)

    def clear(self, job_id: str) -> None:
        """Drop any pending signal for ``job_id`` (idempotent)."""
        with self._lock:
            self._signals.pop(job_id, None)

    def interrupt_check_for(self, job_id: str) -> Callable[[], None]:
        """Return a callable that raises :class:`CopyInterrupted` if ``job_id`` is signalled.

        Passed into the copy loop; called once per buffer so a pause/cancel takes effect at
        the next safe point rather than mid-write.
        """

        def _check() -> None:
            if self.poll(job_id) is not None:
                raise CopyInterrupted(f"job {job_id} interrupted by operator")

        return _check
