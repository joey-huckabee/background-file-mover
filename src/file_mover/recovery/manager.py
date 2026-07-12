"""``RecoveryManager`` — reconciles interrupted jobs at service startup.

If the service stops mid-transfer, jobs are left in an in-progress state (chiefly
``COPYING``). At startup the recovery manager removes any stale ``.swit-partial-``
temporary files for those jobs and re-queues them (L2-REC-001/002); the scheduler then
reprocesses each, and the coordinator skips files already fully moved, so recovery is
idempotent and never re-copies or re-deletes completed work (L2-REC-003). Decisions come
from observable durable state, not from assumptions about what the previous process
finished (L1-SYS-005).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from file_mover.jobs.models import JobState
from file_mover.jobs.repository import JobRepository

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
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialise the recovery manager.

        Args:
            repository: Durable job repository.
            temporary_file_prefix: Prefix identifying in-progress destination files.
            logger: Optional logger; defaults to ``file_mover.recovery``.
        """
        self._repository = repository
        self._temporary_file_prefix = temporary_file_prefix
        self._logger = logger or logging.getLogger("file_mover.recovery")

    def reconcile(self) -> RecoveryReport:
        """Re-queue interrupted jobs and remove their stale temporary files."""
        requeued = 0
        removed = 0
        for job in self._repository.list_jobs(_INTERRUPTED_STATES):
            removed += self._remove_stale_temporaries(job.destination_root, job.job_id)
            self._repository.reset_job_state(job.job_id, JobState.QUEUED)
            requeued += 1
            self._logger.info("recovered interrupted job %s -> queued", job.job_id)
        return RecoveryReport(requeued_jobs=requeued, removed_temporary_files=removed)

    def _remove_stale_temporaries(self, destination_root: str, job_id: str) -> int:
        """Remove any leftover ``.swit-partial-<job>-*`` files under the destination."""
        root = Path(destination_root)
        if not root.exists():
            return 0
        removed = 0
        for path in root.rglob(f"{self._temporary_file_prefix}{job_id}-*"):
            try:
                path.unlink()
            except OSError:
                self._logger.warning("could not remove stale temporary file %s", path)
            else:
                removed += 1
        return removed
