"""Enumerated vocabulary for jobs, files, integrity, retry, and CLI exit codes.

Finite operational choices are modelled as enums (never bare strings) so that
misspellings fail loudly and the durable state machine is exhaustive. String-valued
enums (``str, Enum``) serialise directly into configuration, manifests, and the
control protocol; :class:`ExitCode` is an :class:`~enum.IntEnum` because it becomes a
process exit status.

The record dataclasses (``JobRecord``, ``FileRecord``) and the allowed-transition map
are added in Milestone 4 alongside the SQLite repository.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum


class JobState(str, Enum):
    """Lifecycle state of a whole transfer job.

    The nominal path is ``SUBMITTED -> ... -> COMPLETED``. The ``*_RETAINED`` and
    ``MANUAL_INTERVENTION`` terminals always preserve the claimed source data — a
    failed transfer never deletes a source file.
    """

    SUBMITTED = "submitted"
    VALIDATING = "validating"
    CLAIMING = "claiming"
    CLAIMED = "claimed"
    HASHING_SOURCE = "hashing_source"
    QUEUED = "queued"
    COPYING = "copying"
    VERIFYING = "verifying"
    PUBLISHING = "publishing"
    SOURCE_CLEANUP = "source_cleanup"
    COMPLETED = "completed"
    RETRY_WAIT = "retry_wait"
    PAUSED = "paused"
    SOURCE_UNSTABLE = "source_unstable"
    FAILED_RETAINED = "failed_retained"
    CANCELLED_RETAINED = "cancelled_retained"
    MANUAL_INTERVENTION = "manual_intervention"


class ControlSignal(str, Enum):
    """An operator lifecycle request delivered to an in-flight copy (cooperative).

    Set on a job by a ``pause``/``cancel`` control command and polled by the copy loop at
    each buffer boundary; there is no OS primitive to pause a regular-file copy, so the
    copy stops at a safe point of its own accord (L2-LIF-002).
    """

    PAUSE = "pause"
    CANCEL = "cancel"


class FileState(str, Enum):
    """Lifecycle state of a single file within a job.

    A file counts as fully moved only once it reaches ``MOVE_COMPLETE`` (copied,
    verified, published, and source-deleted) — not merely ``COPIED``.
    """

    QUEUED_FOR_HASH = "queued_for_hash"
    QUEUED_FOR_COPY = "queued_for_copy"
    COPYING = "copying"
    COPIED = "copied"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    SOURCE_CLEANUP = "source_cleanup"
    SOURCE_DELETED = "source_deleted"
    MOVE_COMPLETE = "move_complete"
    INTEGRITY_FAILED = "integrity_failed"
    SKIPPED_NOT_EMPTY = "skipped_not_empty"
    SOURCE_UNSTABLE = "source_unstable"
    FAILED_RETAINED = "failed_retained"


class HashAlgorithm(str, Enum):
    """Integrity hash algorithms, all provided by :mod:`hashlib`."""

    SHA256 = "sha256"
    SHA512 = "sha512"
    BLAKE2B = "blake2b"


class IntegrityMode(str, Enum):
    """Integrity-verification workflow selected in configuration."""

    METADATA = "metadata"
    SOURCE_HASH = "source-hash"
    SOURCE_AND_DESTINATION_HASH = "source-and-destination-hash"


class ExistingDestinationPolicy(str, Enum):
    """Policy applied when a final destination file already exists.

    Overwriting is deliberately unsupported for the first release: recorded
    simulation data must never be silently replaced.
    """

    FAIL = "fail"
    VERIFY_AND_REUSE = "verify-and-reuse"


class ErrorDisposition(Enum):
    """How the coordinator should handle a classified operational error."""

    RETRY = "retry"
    RETAIN_AND_FAIL = "retain_and_fail"
    REJECT_JOB = "reject_job"
    SERVICE_FATAL = "service_fatal"


class ExitCode(IntEnum):
    """Documented process exit codes returned by the CLI.

    Machine-consumable and stable: orchestration scripts branch on these values.
    """

    SUCCESS = 0
    OPERATION_FAILED = 1
    INVALID_ARGUMENT = 2
    CONFIGURATION_ERROR = 3
    SERVICE_UNAVAILABLE = 4
    JOB_REJECTED = 5
    JOB_NOT_FOUND = 6
    PARTIAL_SUCCESS = 7
    ENVIRONMENT_UNSUPPORTED = 8
    INTERNAL_ERROR = 10


@dataclass(frozen=True)
class JobRecord:
    """A durable transfer-job record."""

    job_id: str
    state: JobState
    source_root: str
    destination_root: str
    created_at: float
    updated_at: float
    scenario_id: str | None = None
    request_id: str | None = None
    file_count: int = 0
    total_bytes: int = 0
    bytes_copied: int = 0
    attempt_count: int = 0
    next_retry_time: float | None = None
    last_error: str | None = None


@dataclass(frozen=True)
class FileRecord:
    """A durable record for one file within a job."""

    file_id: str
    job_id: str
    relative_path: str
    state: FileState
    size_bytes: int = 0
    bytes_copied: int = 0
    source_hash: str | None = None
    destination_hash: str | None = None
    attempt_count: int = 0
    last_error: str | None = None


@dataclass(frozen=True)
class JobStatistics:
    """Aggregate, durably-derived job statistics."""

    total_jobs: int
    total_bytes: int
    bytes_copied: int
    jobs_by_state: dict[JobState, int] = field(default_factory=dict)


# The allowed job state-machine transitions. Every terminal maps to the empty set;
# ``FAILED_RETAINED`` and ``MANUAL_INTERVENTION`` allow a manual re-queue (L2-RTY-006).
ALLOWED_JOB_TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.SUBMITTED: frozenset({JobState.VALIDATING, JobState.FAILED_RETAINED}),
    JobState.VALIDATING: frozenset(
        {JobState.CLAIMING, JobState.SOURCE_UNSTABLE, JobState.FAILED_RETAINED}
    ),
    JobState.CLAIMING: frozenset({JobState.CLAIMED, JobState.FAILED_RETAINED}),
    JobState.CLAIMED: frozenset(
        {JobState.HASHING_SOURCE, JobState.QUEUED, JobState.FAILED_RETAINED}
    ),
    JobState.HASHING_SOURCE: frozenset({JobState.QUEUED, JobState.FAILED_RETAINED}),
    JobState.QUEUED: frozenset({JobState.COPYING, JobState.PAUSED, JobState.CANCELLED_RETAINED}),
    JobState.COPYING: frozenset(
        {
            JobState.VERIFYING,
            JobState.COMPLETED,
            JobState.RETRY_WAIT,
            JobState.PAUSED,
            JobState.FAILED_RETAINED,
            JobState.CANCELLED_RETAINED,
            JobState.MANUAL_INTERVENTION,
        }
    ),
    JobState.VERIFYING: frozenset(
        {
            JobState.PUBLISHING,
            JobState.RETRY_WAIT,
            JobState.FAILED_RETAINED,
            JobState.MANUAL_INTERVENTION,
        }
    ),
    JobState.PUBLISHING: frozenset(
        {
            JobState.SOURCE_CLEANUP,
            JobState.RETRY_WAIT,
            JobState.FAILED_RETAINED,
            JobState.MANUAL_INTERVENTION,
        }
    ),
    JobState.SOURCE_CLEANUP: frozenset({JobState.COMPLETED, JobState.MANUAL_INTERVENTION}),
    JobState.RETRY_WAIT: frozenset(
        {
            JobState.QUEUED,
            JobState.COPYING,
            JobState.PAUSED,
            JobState.FAILED_RETAINED,
            JobState.CANCELLED_RETAINED,
        }
    ),
    JobState.PAUSED: frozenset({JobState.QUEUED, JobState.CANCELLED_RETAINED}),
    JobState.SOURCE_UNSTABLE: frozenset(
        {JobState.VALIDATING, JobState.FAILED_RETAINED, JobState.CANCELLED_RETAINED}
    ),
    JobState.COMPLETED: frozenset(),
    JobState.FAILED_RETAINED: frozenset(
        {JobState.QUEUED, JobState.VALIDATING, JobState.CANCELLED_RETAINED}
    ),
    JobState.CANCELLED_RETAINED: frozenset(),
    JobState.MANUAL_INTERVENTION: frozenset(
        {JobState.QUEUED, JobState.FAILED_RETAINED, JobState.CANCELLED_RETAINED}
    ),
}


def is_allowed_job_transition(from_state: JobState, to_state: JobState) -> bool:
    """Return whether a job may transition from ``from_state`` to ``to_state``."""
    return to_state in ALLOWED_JOB_TRANSITIONS.get(from_state, frozenset())


# Jobs that are finished and require no further work.
TERMINAL_JOB_STATES: frozenset[JobState] = frozenset(
    {JobState.COMPLETED, JobState.CANCELLED_RETAINED}
)

# "Active" jobs for the default `list` filter: anything not finished, including
# retained/failed jobs that need operator attention.
ACTIVE_JOB_STATES: frozenset[JobState] = frozenset(
    state for state in JobState if state not in TERMINAL_JOB_STATES
)
