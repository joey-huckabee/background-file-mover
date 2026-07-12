"""``TransferCoordinator`` — job-level orchestration of the durable transfer workflow.

The coordinator owns *the job*: it walks a queued job's files, delegates each file's
mechanics to a :class:`~file_mover.transfer.file_mover.FileMover`, aggregates progress,
and decides what to do when a file fails — classify the error into a
retry/retain/reject disposition and record it durably (L2-RTY-001..005), or route an
integrity/collision failure to manual intervention (L3-INT-007, L2-DST-002/003). The
per-file mechanics (copy → verify → publish → delete-source) live in ``FileMover`` so
that this class stays focused on orchestration.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from file_mover.exceptions import TransferError
from file_mover.jobs.models import (
    ErrorDisposition,
    ExistingDestinationPolicy,
    FileRecord,
    FileState,
    IntegrityMode,
    JobState,
)
from file_mover.jobs.repository import JobRepository
from file_mover.transfer.copy_engine import BufferedFileCopyEngine
from file_mover.transfer.file_mover import FileMover
from file_mover.transfer.integrity import IntegrityVerifier
from file_mover.transfer.retry import ErrorClassifier, compute_backoff


class TransferCoordinator:
    """Transfers a job's claimed files to their destinations with integrity and retry."""

    def __init__(
        self,
        *,
        repository: JobRepository,
        copy_engine: BufferedFileCopyEngine,
        integrity_verifier: IntegrityVerifier,
        error_classifier: ErrorClassifier,
        claim_directory_name: str,
        integrity_enabled: bool,
        integrity_mode: IntegrityMode,
        destination_policy: ExistingDestinationPolicy,
        retry_initial_delay_seconds: float,
        retry_max_delay_seconds: float,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Initialise the coordinator with its collaborators and transfer policy."""
        self._repository = repository
        self._classifier = error_classifier
        self._retry_initial = retry_initial_delay_seconds
        self._retry_max = retry_max_delay_seconds
        self._clock = clock
        self._file_mover = FileMover(
            repository=repository,
            copy_engine=copy_engine,
            integrity_verifier=integrity_verifier,
            claim_directory_name=claim_directory_name,
            integrity_enabled=integrity_enabled,
            integrity_mode=integrity_mode,
            destination_policy=destination_policy,
        )

    def process_job(self, job_id: str) -> JobState:
        """Transfer every file of a queued job and return the resulting job state."""
        job = self._repository.get_job(job_id)
        if job is None:
            raise TransferError(f"cannot process unknown job {job_id!r}")
        if job.state is not JobState.QUEUED:
            return job.state

        self._repository.transition_job(job_id, JobState.COPYING)
        moved_bytes = 0
        for file in self._repository.list_files(job_id):
            if file.state is FileState.MOVE_COMPLETE:
                # Already moved on a previous (interrupted) run; reprocessing is idempotent.
                moved_bytes += file.size_bytes
                continue
            try:
                outcome = self._file_mover.move(job, file)
            except TransferError as error:
                return self._fail_job(job_id, file, error)
            if outcome is FileState.MOVE_COMPLETE:
                moved_bytes += file.size_bytes
                self._repository.update_file(file.file_id, state=FileState.MOVE_COMPLETE)
            else:
                return self._route_to_manual(job_id, file, outcome)

        self._repository.record_job_progress(job_id, moved_bytes)
        self._repository.transition_job(job_id, JobState.COMPLETED)
        return JobState.COMPLETED

    def _route_to_manual(self, job_id: str, file: FileRecord, outcome: FileState) -> JobState:
        """Record an integrity/collision failure and route the job to manual intervention."""
        self._repository.update_file(
            file.file_id, state=outcome, last_error="integrity or destination collision"
        )
        self._repository.record_job_error(job_id, f"file {file.relative_path}: {outcome.value}")
        self._repository.transition_job(job_id, JobState.MANUAL_INTERVENTION)
        return JobState.MANUAL_INTERVENTION

    def _fail_job(self, job_id: str, file: FileRecord, error: TransferError) -> JobState:
        """Classify an I/O failure and record the durable retry/retain outcome."""
        self._repository.update_file(
            file.file_id, state=FileState.FAILED_RETAINED, last_error=str(error)
        )
        if self._classifier.classify(error) is ErrorDisposition.RETRY:
            job = self._repository.get_job(job_id)
            attempt = (job.attempt_count if job is not None else 0) + 1
            delay = compute_backoff(
                attempt,
                initial_seconds=self._retry_initial,
                maximum_seconds=self._retry_max,
            )
            self._repository.record_job_error(
                job_id, str(error), next_retry_time=self._clock() + delay
            )
            self._repository.transition_job(job_id, JobState.RETRY_WAIT)
            return JobState.RETRY_WAIT
        self._repository.record_job_error(job_id, str(error))
        self._repository.transition_job(job_id, JobState.FAILED_RETAINED)
        return JobState.FAILED_RETAINED
