"""Tests for the enumerated job/file/integrity vocabulary."""

from __future__ import annotations

import hashlib

import pytest

from file_mover.jobs.models import (
    ErrorDisposition,
    ExistingDestinationPolicy,
    ExitCode,
    FileState,
    HashAlgorithm,
    IntegrityMode,
    JobState,
)


@pytest.mark.requirement("L3-INT-001")
def test_hash_algorithms_are_supported_by_hashlib() -> None:
    for algorithm in HashAlgorithm:
        # Every configured algorithm must be constructible from the stdlib.
        assert hashlib.new(algorithm.value) is not None


@pytest.mark.requirement("L1-SYS-006")
def test_integrity_modes_are_stable_strings() -> None:
    assert IntegrityMode.SOURCE_AND_DESTINATION_HASH.value == "source-and-destination-hash"
    assert {m.value for m in IntegrityMode} == {
        "metadata",
        "source-hash",
        "source-and-destination-hash",
    }


@pytest.mark.requirement("L2-DST-002")
def test_existing_destination_policy_excludes_overwrite() -> None:
    # Overwriting recorded data is deliberately unsupported in the first release.
    assert {p.value for p in ExistingDestinationPolicy} == {"fail", "verify-and-reuse"}


@pytest.mark.requirement("L1-SYS-007")
def test_state_enums_have_expected_terminals() -> None:
    assert JobState.COMPLETED in JobState
    assert JobState.FAILED_RETAINED in JobState
    assert FileState.MOVE_COMPLETE in FileState


@pytest.mark.requirement("L2-RTY-001")
def test_error_dispositions_cover_all_outcomes() -> None:
    assert {d.name for d in ErrorDisposition} == {
        "RETRY",
        "RETAIN_AND_FAIL",
        "REJECT_JOB",
        "SERVICE_FATAL",
    }


@pytest.mark.requirement("L2-CLI-003")
def test_exit_codes_are_distinct_integers() -> None:
    values = [int(code) for code in ExitCode]
    assert len(values) == len(set(values))
    assert ExitCode.SUCCESS == 0
