"""``TransferCoordinator`` — drives claimed files through the durable transfer workflow.

For each file the coordinator runs ``verify claimed identity -> (optional) hash source ->
copy to a temporary destination -> verify size (and hash) -> atomically publish -> fsync
the directory -> revalidate the source identity -> delete the claimed source`` (the
per-file workflow in ``docs/ARCHITECTURE.md``). A source is deleted only after its
destination is published and verified (L1-SYS-003); an integrity failure or a
destination collision retains both the source and any temporary file and routes the job
to manual intervention (L3-INT-007, L2-DST-002/003). I/O failures are classified into a
retry/retain/reject disposition and recorded durably (L2-RTY-001..005).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from file_mover.exceptions import CopyError, TransferError
from file_mover.jobs.models import (
    ErrorDisposition,
    ExistingDestinationPolicy,
    FileRecord,
    FileState,
    IntegrityMode,
    JobRecord,
    JobState,
)
from file_mover.jobs.repository import JobRepository
from file_mover.transfer.copy_engine import BufferedFileCopyEngine
from file_mover.transfer.integrity import IntegrityVerifier
from file_mover.transfer.retry import ErrorClassifier, compute_backoff
from file_mover.validation import identity_of

_HASH_MODES = frozenset({IntegrityMode.SOURCE_HASH, IntegrityMode.SOURCE_AND_DESTINATION_HASH})


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
        self._copy_engine = copy_engine
        self._verifier = integrity_verifier
        self._classifier = error_classifier
        self._claim_directory_name = claim_directory_name
        self._integrity_enabled = integrity_enabled
        self._integrity_mode = integrity_mode
        self._destination_policy = destination_policy
        self._retry_initial = retry_initial_delay_seconds
        self._retry_max = retry_max_delay_seconds
        self._clock = clock

    @property
    def _needs_source_hash(self) -> bool:
        return self._integrity_enabled and self._integrity_mode in _HASH_MODES

    @property
    def _needs_destination_hash(self) -> bool:
        return (
            self._integrity_enabled
            and self._integrity_mode is IntegrityMode.SOURCE_AND_DESTINATION_HASH
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
                outcome = self._transfer_file(job, file)
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

    def _transfer_file(self, job: JobRecord, file: FileRecord) -> FileState:
        """Run the durable per-file workflow; return the terminal file state."""
        claimed = (
            Path(job.source_root) / self._claim_directory_name / job.job_id / file.relative_path
        )
        final = Path(job.destination_root) / file.relative_path
        self._repository.update_file(file.file_id, state=FileState.COPYING)

        if final.exists():
            return self._handle_existing_destination(claimed, final)

        try:
            source_identity = identity_of(claimed)
        except OSError as error:
            raise CopyError(f"claimed source missing: {claimed}: {error}") from error

        source_hash = self._verifier.hash_file(claimed) if self._needs_source_hash else None
        outcome = self._copy_engine.copy_to_temp(claimed, final.parent, job.job_id, file.file_id)

        if outcome.bytes_written != source_identity.size_bytes:
            return FileState.INTEGRITY_FAILED  # temporary destination retained

        destination_hash = None
        if self._needs_destination_hash:
            destination_hash = self._verifier.hash_file(outcome.temporary_path)
            if source_hash is None or not IntegrityVerifier.compare(source_hash, destination_hash):
                return FileState.INTEGRITY_FAILED  # source and temp retained

        self._copy_engine.publish(outcome.temporary_path, final)
        self._repository.update_file(
            file.file_id, source_hash=source_hash, destination_hash=destination_hash
        )
        try:
            current_identity = identity_of(claimed)
        except OSError as error:
            raise CopyError(f"cannot re-stat claimed source before deletion: {claimed}") from error
        if current_identity != source_identity:
            raise CopyError(f"claimed source changed before deletion: {claimed}")
        try:
            claimed.unlink(missing_ok=True)
        except OSError as error:
            raise CopyError(f"cannot delete claimed source {claimed}: {error}") from error
        return FileState.MOVE_COMPLETE

    def _handle_existing_destination(self, claimed: Path, final: Path) -> FileState:
        """Reuse an identical existing destination or treat it as a collision."""
        if (
            self._destination_policy is ExistingDestinationPolicy.VERIFY_AND_REUSE
            and self._destination_matches(claimed, final)
        ):
            claimed.unlink(missing_ok=True)  # destination already correct; drop the claim
            return FileState.MOVE_COMPLETE
        return FileState.INTEGRITY_FAILED  # differing collision -> manual intervention

    def _destination_matches(self, claimed: Path, final: Path) -> bool:
        """Return whether an existing destination is identical to the claimed source."""
        try:
            if identity_of(claimed).size_bytes != final.stat().st_size:
                return False
        except OSError:
            return False
        if self._needs_source_hash:
            return IntegrityVerifier.compare(
                self._verifier.hash_file(claimed), self._verifier.hash_file(final)
            )
        return True

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
