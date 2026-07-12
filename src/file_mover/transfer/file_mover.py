"""``FileMover`` — the durable per-file transfer workflow.

Extracted from :class:`~file_mover.transfer.coordinator.TransferCoordinator` so that
job-level orchestration (which file next, how to record a job failure, when to retry) is
separated from the single-file mechanics (verify the claim, hash, copy to a temp,
verify, publish, re-check identity, delete the source). The coordinator owns *the job*;
this class owns *one file* (a Fowler separation of concerns).

For each file the workflow is ``verify claimed identity -> (optional) hash source ->
copy to a temporary destination -> verify size (and hash) -> atomically publish -> fsync
the directory -> revalidate the source identity -> delete the claimed source``. A source
is deleted only after its destination is published and verified (L1-SYS-003); an
integrity failure or a differing destination collision retains both the source and any
temporary file and returns a non-``MOVE_COMPLETE`` state so the job routes to manual
intervention (L3-INT-007, L2-DST-002/003). I/O failures raise :class:`TransferError`.
"""

from __future__ import annotations

from pathlib import Path

from file_mover.exceptions import CopyError
from file_mover.jobs.models import (
    ExistingDestinationPolicy,
    FileRecord,
    FileState,
    IntegrityMode,
    JobRecord,
)
from file_mover.jobs.repository import JobRepository
from file_mover.transfer.copy_engine import BufferedFileCopyEngine
from file_mover.transfer.integrity import IntegrityVerifier
from file_mover.validation import identity_of

_HASH_MODES = frozenset({IntegrityMode.SOURCE_HASH, IntegrityMode.SOURCE_AND_DESTINATION_HASH})


class FileMover:
    """Moves one claimed file to its destination with integrity and durable state."""

    def __init__(
        self,
        *,
        repository: JobRepository,
        copy_engine: BufferedFileCopyEngine,
        integrity_verifier: IntegrityVerifier,
        claim_directory_name: str,
        integrity_enabled: bool,
        integrity_mode: IntegrityMode,
        destination_policy: ExistingDestinationPolicy,
    ) -> None:
        """Initialise the file mover with its collaborators and integrity policy."""
        self._repository = repository
        self._copy_engine = copy_engine
        self._verifier = integrity_verifier
        self._claim_directory_name = claim_directory_name
        self._integrity_enabled = integrity_enabled
        self._integrity_mode = integrity_mode
        self._destination_policy = destination_policy

    @property
    def _needs_source_hash(self) -> bool:
        return self._integrity_enabled and self._integrity_mode in _HASH_MODES

    @property
    def _needs_destination_hash(self) -> bool:
        return (
            self._integrity_enabled
            and self._integrity_mode is IntegrityMode.SOURCE_AND_DESTINATION_HASH
        )

    def move(self, job: JobRecord, file: FileRecord) -> FileState:
        """Run the durable per-file workflow; return the terminal file state.

        Raises:
            TransferError: On an I/O failure the coordinator should classify.
        """
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
        return self._delete_verified_source(claimed, source_identity)

    def _delete_verified_source(self, claimed: Path, source_identity: object) -> FileState:
        """Re-check the claimed source is unchanged, then delete it (L1-SYS-003)."""
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
