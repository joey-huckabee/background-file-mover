"""``RecoveryManager`` — reconciles interrupted jobs at service startup.

If the service stops mid-transfer, jobs are left in an in-progress state (chiefly
``COPYING``). At startup the recovery manager re-queues them (L2-REC-001/002); the
scheduler then reprocesses each, and the coordinator skips files already fully moved, so
recovery is idempotent and never re-copies or re-deletes completed work (L2-REC-003).
Decisions come from observable durable state, not from assumptions about what the previous
process finished (L1-SYS-005).

What happens to a job's ``.swit-partial-`` temporary depends on ``resume_partial_files``:
when resume is **disabled** the stale partial is removed so the file restarts from byte
zero (the original behaviour); when resume is **enabled** the fsynced partial is *kept* so
the coordinator continues it from its current size, and only a verification failure later
discards it (L2-RSM-002).

An operator ``PAUSED`` job is deliberately *not* an interrupted state — it survives a
restart still paused until an explicit ``resume``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from file_mover.jobs.models import JobState
from file_mover.jobs.repository import JobRepository
from file_mover.transfer.partials import remove_job_partials

_INTERRUPTED_STATES = frozenset(
    {
        JobState.CLAIMING,
        JobState.HASHING_SOURCE,
        JobState.COPYING,
        JobState.VERIFYING,
        JobState.PUBLISHING,
        JobState.SOURCE_CLEANUP,
    }
)


@dataclass(frozen=True)
class RecoveryReport:
    """A summary of the reconciliation performed at startup."""

    requeued_jobs: int
    removed_temporary_files: int


class RecoveryManager:
    """Reconciles interrupted jobs against the filesystem at startup."""

    def __init__(
        self,
        *,
        repository: JobRepository,
        temporary_file_prefix: str,
        resume_partial_files: bool = False,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialise the recovery manager.

        Args:
            repository: Durable job repository.
            temporary_file_prefix: Prefix identifying in-progress destination files.
            resume_partial_files: Keep interrupted partials for resume rather than removing
                them (L2-RSM-002).
            logger: Optional logger; defaults to ``file_mover.recovery``.
        """
        self._repository = repository
        self._temporary_file_prefix = temporary_file_prefix
        self._resume_partial_files = resume_partial_files
        self._logger = logger or logging.getLogger("file_mover.recovery")

    def reconcile(self) -> RecoveryReport:
        """Re-queue interrupted jobs, removing stale partials only when resume is disabled."""
        requeued = 0
        removed = 0
        for job in self._repository.list_jobs(_INTERRUPTED_STATES):
            if not self._resume_partial_files:
                removed += remove_job_partials(
                    job.destination_root,
                    job.job_id,
                    self._temporary_file_prefix,
                    logger=self._logger,
                )
            self._repository.reset_job_state(job.job_id, JobState.QUEUED)
            requeued += 1
            self._logger.info("recovered interrupted job %s -> queued", job.job_id)
        return RecoveryReport(requeued_jobs=requeued, removed_temporary_files=removed)
