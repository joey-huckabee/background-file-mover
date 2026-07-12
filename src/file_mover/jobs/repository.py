"""``JobRepository`` protocol — the durable job/file state interface.

The transfer coordinator, query service, and recovery manager depend on this narrow
Protocol rather than on SQLite directly, so tests can substitute an in-memory fake. The
concrete implementation is :class:`file_mover.jobs.sqlite_repository.SQLiteJobRepository`.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Protocol

from file_mover.jobs.models import FileRecord, JobRecord, JobState, JobStatistics


class JobRepository(Protocol):
    """Durable persistence for jobs and their files."""

    def initialize(self) -> None:
        """Create the schema and apply migrations (idempotent)."""

    def insert_job(self, job: JobRecord) -> None:
        """Insert a new job record."""

    def get_job(self, job_id: str) -> JobRecord | None:
        """Return the job with ``job_id``, or ``None`` if absent."""

    def list_jobs(self, states: Collection[JobState] | None = None) -> list[JobRecord]:
        """Return jobs, optionally filtered to the given states, newest first."""

    def insert_files(self, files: Collection[FileRecord]) -> None:
        """Insert file records for a job."""

    def list_files(self, job_id: str) -> list[FileRecord]:
        """Return the files belonging to ``job_id`` in deterministic order."""

    def transition_job(self, job_id: str, to_state: JobState) -> None:
        """Transition a job to ``to_state``, enforcing the allowed-transition map."""

    def record_job_error(
        self, job_id: str, message: str, *, next_retry_time: float | None = None
    ) -> None:
        """Record a failure on a job, incrementing its attempt count."""

    def statistics(self) -> JobStatistics:
        """Return aggregate job statistics."""

    def close(self) -> None:
        """Close all open database connections."""
