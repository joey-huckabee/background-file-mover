"""Typed exception hierarchy for the transfer coordinator.

Every subsystem raises a project-specific exception rooted at :class:`FileMoverError`
rather than leaking raw ``OSError``/``sqlite3`` failures upward. Each layer catches
only the errors it can interpret, attaches context, and re-raises a typed exception
(preserving the original via ``raise ... from error``) so the coordinator can map the
failure to a well-defined job or file state instead of terminating the service.

The hierarchy mirrors the durable workflow stages:

``FileMoverError``
 ├── ``ConfigurationError``
 ├── ``SubmissionError``
 │    ├── ``InvalidSourceError``
 │    ├── ``InvalidDestinationError``
 │    ├── ``SourceNotStableError``
 │    └── ``DuplicateSubmissionError``
 ├── ``ClaimError``
 ├── ``ManifestError``
 ├── ``TransferError``
 │    ├── ``CopyError``
 │    ├── ``DestinationWriteError``
 │    └── ``DestinationPublishError``
 ├── ``IntegrityError``
 │    ├── ``SizeMismatchError``
 │    ├── ``HashMismatchError``
 │    └── ``SourceChangedError``
 ├── ``RepositoryError``
 └── ``RecoveryError``
"""

from __future__ import annotations


class FileMoverError(Exception):
    """Base class for every error raised by the Background File Mover."""


class ConfigurationError(FileMoverError):
    """Configuration could not be loaded, parsed, or validated."""


class SubmissionError(FileMoverError):
    """A transfer job could not be accepted for submission."""


class InvalidSourceError(SubmissionError):
    """The submitted source path is missing, disallowed, or otherwise unusable."""


class InvalidDestinationError(SubmissionError):
    """The submitted destination path is disallowed or conflicts with the source."""


class SourceNotStableError(SubmissionError):
    """A source file changed during the stability observation window."""


class DuplicateSubmissionError(SubmissionError):
    """A job with the same idempotency ``request_id`` has already been accepted."""


class ClaimError(FileMoverError):
    """A source file could not be atomically claimed into the staging directory."""


class ManifestError(FileMoverError):
    """The durable transfer manifest could not be written or replaced."""


class TransferError(FileMoverError):
    """Base class for failures during the copy/verify/publish transfer stages."""


class CopyError(TransferError):
    """A source file could not be copied to its temporary destination."""


class DestinationWriteError(TransferError):
    """The temporary destination file could not be created, written, or synced."""


class DestinationPublishError(TransferError):
    """A verified temporary destination could not be atomically published."""


class IntegrityError(FileMoverError):
    """Base class for integrity-verification failures; both source and temp are retained."""


class SizeMismatchError(IntegrityError):
    """The destination byte count did not match the expected source size."""


class HashMismatchError(IntegrityError):
    """The destination hash did not match the recorded source hash."""


class SourceChangedError(IntegrityError):
    """The source file's identity changed between claim and a later revalidation."""


class RepositoryError(FileMoverError):
    """The durable job-state repository (SQLite) reported an unrecoverable error."""


class RecoveryError(FileMoverError):
    """Startup reconciliation could not resolve durable state against the filesystem."""
