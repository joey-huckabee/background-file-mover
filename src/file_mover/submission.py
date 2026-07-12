"""``JobSubmissionService`` — validate, claim, record, and acknowledge a submission.

Submission is the durable acknowledgement boundary: it succeeds only after the source
files are claimed, the manifest is written, and the job and its file inventory are
durably recorded (L2-CLI-008). It does **not** copy, verify, or delete anything — that is
the background transfer engine's job (L2-CLI-009). Submission is idempotent by
``request_id``: re-submitting the same request returns the original job without
re-claiming (L2-SUB-001). Any failure leaves already-claimed source files retained
(L2-SUB-005).
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from file_mover.claiming import ClaimedFile, FileClaimManager
from file_mover.configuration import IntegrityConfig, StabilityConfig
from file_mover.exceptions import (
    ClaimError,
    InvalidDestinationError,
    ManifestError,
    RepositoryError,
    SubmissionError,
)
from file_mover.jobs.models import FileRecord, FileState, JobRecord, JobState
from file_mover.jobs.repository import JobRepository
from file_mover.logging_config import GATE
from file_mover.manifests import ManifestWriter
from file_mover.validation import SourceValidator

_LOG = logging.getLogger("file_mover.submission")


@dataclass(frozen=True)
class SubmissionRequest:
    """A validated request to submit a recording set."""

    request_id: str
    scenario_id: str | None
    source_root: Path
    destination_root: Path
    file_list: tuple[Path, ...] | None = None


@dataclass(frozen=True)
class SubmissionResult:
    """The typed outcome of a submission."""

    accepted: bool
    job_id: str | None
    state: JobState
    claimed_file_count: int
    claimed_bytes: int
    error_code: str | None = None
    error_message: str | None = None


def build_submission_request(
    *,
    request_id: str,
    scenario_id: str | None,
    destination: str,
    source: str | None = None,
    file_list: Sequence[str] | None = None,
) -> SubmissionRequest:
    """Build a :class:`SubmissionRequest` from raw string arguments.

    For a directory submission ``source`` is the source root. For a file-list submission
    the source root is the common ancestor directory of the listed files.

    Raises:
        ValueError: If neither ``source`` nor ``file_list`` is provided.
    """
    if source is not None:
        return SubmissionRequest(request_id, scenario_id, Path(source), Path(destination), None)
    if not file_list:
        raise ValueError("submission requires either a source directory or a file list")
    files = tuple(Path(path) for path in file_list)
    common = Path(os.path.commonpath([str(path) for path in files]))
    source_root = common if common.is_dir() else common.parent
    return SubmissionRequest(request_id, scenario_id, source_root, Path(destination), files)


class JobSubmissionService:
    """Orchestrates validation, claiming, manifest writing, and durable recording."""

    def __init__(
        self,
        *,
        validator: SourceValidator,
        claim_manager: FileClaimManager,
        manifest_writer: ManifestWriter,
        repository: JobRepository,
        allowed_source_roots: Sequence[Path],
        allowed_destination_roots: Sequence[Path],
        stability: StabilityConfig,
        integrity: IntegrityConfig,
        job_id_factory: Callable[[], str] = lambda: uuid.uuid4().hex,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Initialise the submission service with its collaborators and policy."""
        self._validator = validator
        self._claim_manager = claim_manager
        self._manifest_writer = manifest_writer
        self._repository = repository
        self._allowed_source_roots = tuple(allowed_source_roots)
        self._allowed_destination_roots = tuple(allowed_destination_roots)
        self._stability = stability
        self._integrity = integrity
        self._new_job_id = job_id_factory
        self._clock = clock

    def submit(self, request: SubmissionRequest) -> SubmissionResult:
        """Validate, claim, record, and acknowledge a submission."""
        existing = self._repository.get_job_by_request_id(request.request_id)
        if existing is not None:
            if __debug__ and GATE.debug:
                _LOG.debug(
                    "duplicate submission returns existing job", extra={"job_id": existing.job_id}
                )
            return SubmissionResult(
                accepted=True,
                job_id=existing.job_id,
                state=existing.state,
                claimed_file_count=existing.file_count,
                claimed_bytes=existing.total_bytes,
            )

        try:
            self._validate_destination(request.destination_root)
            entries = self._validator.inventory(
                request.source_root,
                self._allowed_source_roots,
                file_list=request.file_list,
            )
            if self._stability.enabled:
                self._validator.check_stability(
                    entries,
                    poll_count=self._stability.poll_count,
                    poll_interval_seconds=self._stability.poll_interval_seconds,
                )
        except SubmissionError as error:
            return _rejected(error)

        job_id = self._new_job_id()
        created_at = self._clock()
        try:
            _staging, claimed = self._claim_manager.claim(entries, request.source_root, job_id)
            self._manifest_writer.write(
                job_id, self._build_manifest(job_id, request, claimed, created_at)
            )
            total_bytes = sum(item.identity.size_bytes for item in claimed)
            self._record(job_id, request, claimed, total_bytes, created_at)
        except (ClaimError, ManifestError, RepositoryError) as error:
            return SubmissionResult(
                accepted=False,
                job_id=None,
                state=JobState.FAILED_RETAINED,
                claimed_file_count=0,
                claimed_bytes=0,
                error_code=type(error).__name__,
                error_message=str(error),
            )

        _LOG.info(
            "submission accepted: %d file(s), %d byte(s)",
            len(claimed),
            total_bytes,
            extra={"job_id": job_id},
        )
        return SubmissionResult(
            accepted=True,
            job_id=job_id,
            state=JobState.QUEUED,
            claimed_file_count=len(claimed),
            claimed_bytes=total_bytes,
        )

    def _validate_destination(self, destination: Path) -> None:
        """Confirm the destination is beneath an approved destination root."""
        for root in self._allowed_destination_roots:
            if destination == root or destination.is_relative_to(root):
                return
        raise InvalidDestinationError(f"destination {destination} is not beneath an approved root")

    def _record(
        self,
        job_id: str,
        request: SubmissionRequest,
        claimed: Sequence[ClaimedFile],
        total_bytes: int,
        created_at: float,
    ) -> None:
        """Insert the job and its file inventory durably.

        ``created_at`` is the same timestamp stamped into the manifest, so the durable
        record and the manifest agree (L2-JOB-007).
        """
        self._repository.insert_job(
            JobRecord(
                job_id=job_id,
                state=JobState.QUEUED,
                source_root=str(request.source_root),
                destination_root=str(request.destination_root),
                created_at=created_at,
                updated_at=created_at,
                scenario_id=request.scenario_id,
                request_id=request.request_id,
                file_count=len(claimed),
                total_bytes=total_bytes,
                hash_algorithm=self._integrity.algorithm,
                integrity_mode=self._integrity.mode,
            )
        )
        self._repository.insert_files(
            [
                FileRecord(
                    file_id=f"{job_id}-{index:04d}",
                    job_id=job_id,
                    relative_path=item.relative_path,
                    state=FileState.QUEUED_FOR_COPY,
                    size_bytes=item.identity.size_bytes,
                )
                for index, item in enumerate(claimed)
            ]
        )

    def _build_manifest(
        self,
        job_id: str,
        request: SubmissionRequest,
        claimed: Sequence[ClaimedFile],
        created_at: float,
    ) -> dict[str, Any]:
        """Build the manifest inventory for a claimed job.

        Carries the same ``created_at`` and integrity policy as the durable job record so
        the two never disagree (L2-JOB-007).
        """
        return {
            "job_id": job_id,
            "scenario_id": request.scenario_id,
            "created_at": created_at,
            "source_root": str(request.source_root),
            "destination_root": str(request.destination_root),
            "integrity": {
                "mode": self._integrity.mode.value,
                "algorithm": self._integrity.algorithm.value,
            },
            "files": [
                {"relative_path": item.relative_path, "size_bytes": item.identity.size_bytes}
                for item in claimed
            ],
        }


def _rejected(error: SubmissionError) -> SubmissionResult:
    """Build a rejected result from a submission validation error (source untouched)."""
    return SubmissionResult(
        accepted=False,
        job_id=None,
        state=JobState.FAILED_RETAINED,
        claimed_file_count=0,
        claimed_bytes=0,
        error_code=type(error).__name__,
        error_message=str(error),
    )
