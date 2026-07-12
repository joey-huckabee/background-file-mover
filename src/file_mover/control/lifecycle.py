"""``JobLifecycleService`` — the ``cancel`` / ``pause`` / ``resume`` control operations.

Kept separate from :class:`~file_mover.service.BackgroundMoverService` (lifecycle) and the
query/submit handlers so the *job-lifecycle-control* concern lives in one place. Each
operation reconciles two worlds: a job that is **not** running is transitioned directly
with a compare-and-set (so a concurrent scheduler pick cannot be clobbered), while a job
that **is** copying is signalled through :class:`JobControlSignals` and stopped
cooperatively by the copy loop (there is no OS primitive to pause a file copy). A cancel
always retains the claimed source and only discards the incomplete partial
(L1-SYS-003, L2-LIF-001/002/003).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any

from file_mover.jobs.models import ControlSignal, JobRecord, JobState
from file_mover.jobs.repository import JobRepository
from file_mover.transfer.control_signals import JobControlSignals
from file_mover.transfer.partials import remove_job_partials

# Non-running states a request can transition directly (compare-and-set).
_PAUSABLE = frozenset({JobState.QUEUED, JobState.RETRY_WAIT})
_CANCELLABLE = frozenset(
    {
        JobState.QUEUED,
        JobState.RETRY_WAIT,
        JobState.PAUSED,
        JobState.SOURCE_UNSTABLE,
        JobState.FAILED_RETAINED,
        JobState.MANUAL_INTERVENTION,
    }
)


class JobLifecycleService:
    """Applies operator pause/cancel/resume requests to durable jobs and in-flight copies."""

    def __init__(
        self,
        *,
        repository: JobRepository,
        signals: JobControlSignals,
        temporary_file_prefix: str,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialise with the durable repository, the signal registry, and the temp prefix."""
        self._repository = repository
        self._signals = signals
        self._prefix = temporary_file_prefix
        self._logger = logger or logging.getLogger("file_mover.lifecycle")

    def handle_pause(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Control handler for ``pause``."""
        return self._for_job(arguments, self._pause)

    def handle_cancel(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Control handler for ``cancel``."""
        return self._for_job(arguments, self._cancel)

    def handle_resume(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Control handler for ``resume``."""
        return self._for_job(arguments, self._resume)

    def _for_job(
        self,
        arguments: Mapping[str, Any],
        action: Callable[[JobRecord], dict[str, Any]],
    ) -> dict[str, Any]:
        """Resolve the ``job_id`` argument and dispatch to a per-job action."""
        job_id = arguments.get("job_id")
        if not isinstance(job_id, str):
            return _rejected(None, "BAD_REQUEST", "job_id is required")
        job = self._repository.get_job(job_id)
        if job is None:
            return _rejected(job_id, "NOT_FOUND", f"job {job_id!r} not found")
        return action(job)

    def _copying_now(self, job_id: str) -> bool:
        """Whether the job is (still) copying after a lost compare-and-set race."""
        current = self._repository.get_job(job_id)
        return current is not None and current.state is JobState.COPYING

    def _pause(self, job: JobRecord) -> dict[str, Any]:
        if job.state is JobState.PAUSED:
            return _accepted(job.job_id, JobState.PAUSED)  # idempotent
        if job.state is JobState.COPYING:
            self._signals.request(job.job_id, ControlSignal.PAUSE)
            return _accepted(job.job_id, JobState.COPYING)
        if self._repository.transition_job_if(job.job_id, _PAUSABLE, JobState.PAUSED):
            return _accepted(job.job_id, JobState.PAUSED)
        if self._copying_now(job.job_id):
            self._signals.request(job.job_id, ControlSignal.PAUSE)
            return _accepted(job.job_id, JobState.COPYING)
        return _rejected(job.job_id, "INVALID_STATE", f"cannot pause a {job.state.value} job")

    def _cancel(self, job: JobRecord) -> dict[str, Any]:
        if job.state is JobState.COPYING:
            self._signals.request(job.job_id, ControlSignal.CANCEL)
            return _accepted(job.job_id, JobState.COPYING)
        if self._repository.transition_job_if(
            job.job_id, _CANCELLABLE, JobState.CANCELLED_RETAINED
        ):
            remove_job_partials(job.destination_root, job.job_id, self._prefix, logger=self._logger)
            return _accepted(job.job_id, JobState.CANCELLED_RETAINED)
        if self._copying_now(job.job_id):
            self._signals.request(job.job_id, ControlSignal.CANCEL)
            return _accepted(job.job_id, JobState.COPYING)
        return _rejected(job.job_id, "INVALID_STATE", f"cannot cancel a {job.state.value} job")

    def _resume(self, job: JobRecord) -> dict[str, Any]:
        if self._repository.transition_job_if(job.job_id, {JobState.PAUSED}, JobState.QUEUED):
            self._signals.clear(job.job_id)  # drop any stale pause signal before it re-runs
            return _accepted(job.job_id, JobState.QUEUED)
        return _rejected(job.job_id, "INVALID_STATE", f"cannot resume a {job.state.value} job")


def _accepted(job_id: str | None, state: JobState) -> dict[str, Any]:
    """Build an accepted lifecycle response."""
    return {
        "accepted": True,
        "job_id": job_id,
        "state": state.value,
        "error_code": None,
        "error_message": None,
    }


def _rejected(job_id: str | None, code: str, message: str) -> dict[str, Any]:
    """Build a rejected lifecycle response."""
    return {
        "accepted": False,
        "job_id": job_id,
        "state": None,
        "error_code": code,
        "error_message": message,
    }
