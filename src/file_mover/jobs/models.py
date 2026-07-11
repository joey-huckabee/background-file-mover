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
    SOURCE_UNSTABLE = "source_unstable"
    FAILED_RETAINED = "failed_retained"
    CANCELLED_RETAINED = "cancelled_retained"
    MANUAL_INTERVENTION = "manual_intervention"


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
    INTERNAL_ERROR = 10
