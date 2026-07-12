"""``TransferScheduler`` — drives runnable jobs through the transfer coordinator.

One scheduler tick (:meth:`TransferScheduler.run_once`) selects the runnable jobs —
those ``QUEUED``, or ``RETRY_WAIT`` whose ``next_retry_time`` has passed — up to the
configured job concurrency, re-queues any due retry, and processes each through the
coordinator (L2-REC-004). The service runs this on a background thread; the tick itself
is synchronous and host-independent, so it is tested directly.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from file_mover.jobs.models import JobState
from file_mover.jobs.repository import JobRepository
from file_mover.logging_config import GATE
from file_mover.transfer.coordinator import TransferCoordinator

_LOG = logging.getLogger("file_mover.transfer.scheduler")


class TransferScheduler:
    """Selects and processes runnable transfer jobs."""

    def __init__(
        self,
        *,
        repository: JobRepository,
        coordinator: TransferCoordinator,
        max_concurrent_jobs: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Initialise the scheduler.

        Args:
            repository: Durable job repository.
            coordinator: Transfer coordinator that processes a job.
            max_concurrent_jobs: Upper bound on jobs selected per tick.
            clock: Time source used to evaluate retry readiness; injectable for tests.
        """
        self._repository = repository
        self._coordinator = coordinator
        self._max_concurrent_jobs = max_concurrent_jobs
        self._clock = clock

    def run_once(self) -> list[str]:
        """Process the runnable jobs for this tick and return their ids."""
        processed: list[str] = []
        runnable = self._repository.list_runnable_job_ids(
            self._clock(), limit=self._max_concurrent_jobs
        )
        if __debug__ and GATE.debug and runnable:
            _LOG.debug("scheduler tick: %d runnable job(s)", len(runnable))
        for job_id in runnable:
            job = self._repository.get_job(job_id)
            if job is None:
                continue
            if job.state is JobState.RETRY_WAIT:
                self._repository.transition_job(job_id, JobState.QUEUED)
            self._coordinator.process_job(job_id)
            processed.append(job_id)
        return processed
