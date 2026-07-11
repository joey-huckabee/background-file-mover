"""Tests for the typed exception hierarchy."""

from __future__ import annotations

import pytest

from file_mover.exceptions import (
    ClaimError,
    ConfigurationError,
    CopyError,
    DuplicateSubmissionError,
    FileMoverError,
    HashMismatchError,
    IntegrityError,
    InvalidSourceError,
    RepositoryError,
    SubmissionError,
    TransferError,
)


@pytest.mark.requirement("L1-SYS-010")
@pytest.mark.parametrize(
    ("error", "base"),
    [
        (ConfigurationError, FileMoverError),
        (SubmissionError, FileMoverError),
        (InvalidSourceError, SubmissionError),
        (DuplicateSubmissionError, SubmissionError),
        (ClaimError, FileMoverError),
        (CopyError, TransferError),
        (TransferError, FileMoverError),
        (HashMismatchError, IntegrityError),
        (IntegrityError, FileMoverError),
        (RepositoryError, FileMoverError),
    ],
)
def test_exception_parentage(error: type[Exception], base: type[Exception]) -> None:
    assert issubclass(error, base)
    assert issubclass(error, FileMoverError)


@pytest.mark.requirement("L1-SYS-010")
def test_exceptions_preserve_cause() -> None:
    original = OSError("stale handle")
    try:
        raise ClaimError("could not claim host01.dat") from original
    except ClaimError as raised:
        assert raised.__cause__ is original
