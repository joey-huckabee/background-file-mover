"""Control-response presentation — record/enum → JSON-ready ``dict`` serialisation.

These pure functions are the single place that maps durable records and enums onto the
wire shapes the control protocol returns. Keeping them out of
:mod:`file_mover.service` separates the *wire format* concern from the *service
lifecycle* concern (a Fowler separation of concerns): the service and its command
handlers decide *what* to answer; this module decides *how* it is shaped for JSON.
"""

from __future__ import annotations

from typing import Any

from file_mover.diagnostics import CheckResult
from file_mover.jobs.models import (
    ACTIVE_JOB_STATES,
    JobRecord,
    JobState,
    JobStatistics,
)
from file_mover.submission import SubmissionResult


def resolve_state_selector(selector: str) -> frozenset[JobState] | None:
    """Map a ``list`` state selector to a set of states (``None`` means all).

    Raises:
        ValueError: If ``selector`` is neither ``active``/``all`` nor a known state name.
    """
    lowered = selector.strip().lower()
    if lowered in {"all", ""}:
        return None
    if lowered == "active":
        return ACTIVE_JOB_STATES
    try:
        return frozenset({JobState(lowered)})
    except ValueError as error:
        raise ValueError(f"unknown job state selector {selector!r}") from error


def job_to_dict(job: JobRecord) -> dict[str, Any]:
    """Serialise a :class:`JobRecord` for a control response."""
    return {
        "job_id": job.job_id,
        "state": job.state.value,
        "scenario_id": job.scenario_id,
        "source_root": job.source_root,
        "destination_root": job.destination_root,
        "file_count": job.file_count,
        "total_bytes": job.total_bytes,
        "bytes_copied": job.bytes_copied,
        "attempt_count": job.attempt_count,
        "last_error": job.last_error,
    }


def statistics_to_dict(stats: JobStatistics) -> dict[str, Any]:
    """Serialise :class:`JobStatistics` for a control response."""
    return {
        "total_jobs": stats.total_jobs,
        "total_bytes": stats.total_bytes,
        "bytes_copied": stats.bytes_copied,
        "jobs_by_state": {state.value: count for state, count in stats.jobs_by_state.items()},
    }


def submission_result_to_dict(result: SubmissionResult) -> dict[str, Any]:
    """Serialise a :class:`SubmissionResult` for a control response."""
    return {
        "accepted": result.accepted,
        "job_id": result.job_id,
        "state": result.state.value,
        "claimed_file_count": result.claimed_file_count,
        "claimed_bytes": result.claimed_bytes,
        "error_code": result.error_code,
        "error_message": result.error_message,
    }


def check_result_to_dict(result: CheckResult) -> dict[str, Any]:
    """Serialise an environment :class:`CheckResult` for ``doctor`` output."""
    return {
        "name": result.name,
        "requirement": result.requirement.value,
        "status": result.status.value,
        "detail": result.detail,
    }


def submission_error(code: str, message: str) -> dict[str, Any]:
    """Build a rejected submission response for a malformed request."""
    return {
        "accepted": False,
        "job_id": None,
        "state": JobState.FAILED_RETAINED.value,
        "claimed_file_count": 0,
        "claimed_bytes": 0,
        "error_code": code,
        "error_message": message,
    }
