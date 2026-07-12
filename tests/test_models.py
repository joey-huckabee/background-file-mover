"""Tests for the enumerated job/file/integrity vocabulary."""

from __future__ import annotations

import hashlib

import pytest

from file_mover.jobs.models import (
    ACTIVE_JOB_STATES,
    TERMINAL_JOB_STATES,
    ErrorDisposition,
    ExistingDestinationPolicy,
    ExitCode,
    FileState,
    HashAlgorithm,
    IntegrityMode,
    JobState,
    is_allowed_job_transition,
)


@pytest.mark.requirement("L2-LIF-004")
def test_pause_cancel_and_resume_transitions() -> None:
    assert is_allowed_job_transition(JobState.QUEUED, JobState.PAUSED)
    assert is_allowed_job_transition(JobState.COPYING, JobState.PAUSED)
    assert is_allowed_job_transition(JobState.RETRY_WAIT, JobState.PAUSED)
    assert is_allowed_job_transition(JobState.PAUSED, JobState.QUEUED)  # resume
    assert is_allowed_job_transition(JobState.PAUSED, JobState.CANCELLED_RETAINED)
    assert is_allowed_job_transition(JobState.COPYING, JobState.CANCELLED_RETAINED)
    assert is_allowed_job_transition(JobState.MANUAL_INTERVENTION, JobState.CANCELLED_RETAINED)
    # PAUSED is a non-terminal, non-runnable holding state.
    assert JobState.PAUSED in ACTIVE_JOB_STATES
    assert JobState.PAUSED not in TERMINAL_JOB_STATES
    assert not is_allowed_job_transition(JobState.COMPLETED, JobState.PAUSED)
    assert not is_allowed_job_transition(JobState.CANCELLED_RETAINED, JobState.QUEUED)


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
