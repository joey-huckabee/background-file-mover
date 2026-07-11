"""Tests for project-wide constants (markers, defaults, protocol values)."""

from __future__ import annotations

import pytest

from file_mover import constants


@pytest.mark.requirement("L1-SYS-004")
def test_on_disk_markers_are_swit_prefixed() -> None:
    # The hybrid naming decision: generic command, SWIT-prefixed on-disk markers.
    assert constants.CLAIM_DIRECTORY_NAME == ".swit-moving"
    assert constants.TEMPORARY_FILE_PREFIX == ".swit-partial-"


@pytest.mark.requirement("L1-SYS-004")
def test_claim_directory_name_is_a_single_component() -> None:
    assert "/" not in constants.CLAIM_DIRECTORY_NAME
    assert "\\" not in constants.CLAIM_DIRECTORY_NAME


@pytest.mark.requirement("L2-COPY-002")
def test_copy_buffer_default_respects_floor() -> None:
    assert constants.DEFAULT_COPY_BUFFER_SIZE_BYTES >= constants.MINIMUM_COPY_BUFFER_SIZE_BYTES


@pytest.mark.requirement("L3-PY-006")
def test_protocol_version_is_positive() -> None:
    assert constants.PROTOCOL_VERSION >= 1
    assert constants.LENGTH_PREFIX_BYTES == 4
