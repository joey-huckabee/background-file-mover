"""Tests for the configuration loader, validation, and immutable model."""

from __future__ import annotations

import dataclasses
from pathlib import Path, PurePosixPath

import pytest

from file_mover.configuration import (
    ApplicationConfig,
    ConfigurationLoader,
    ConfigurationValidationError,
    _float_converter,
    _posix_path,
    _posix_path_list,
    describe_schema,
)
from file_mover.exceptions import ConfigurationError
from file_mover.jobs.models import HashAlgorithm, IntegrityMode

REPO_ROOT = Path(__file__).resolve().parent.parent
REFERENCE_CONFIG = REPO_ROOT / "config" / "file-mover.ini"

# A minimal config: only the required [paths] options are given; every other section
# falls back to compiled defaults.
MINIMAL_CONFIG = """
[paths]
allowed_source_roots = /recordings
allowed_destination_roots = /processing
"""


def _load(text: str) -> ApplicationConfig:
    return ConfigurationLoader().load_text(text)


def _issues(text: str) -> list[tuple[str, str | None]]:
    with pytest.raises(ConfigurationValidationError) as excinfo:
        _load(text)
    return [(issue.section, issue.option) for issue in excinfo.value.issues]


@pytest.mark.requirement("L2-CFG-001")
def test_shipped_reference_config_loads() -> None:
    config = ConfigurationLoader().load(str(REFERENCE_CONFIG))
    assert isinstance(config, ApplicationConfig)
    assert config.paths.claim_directory_name == ".swit-moving"
    assert config.paths.temporary_file_prefix == ".swit-partial-"


@pytest.mark.requirement("L2-CFG-001")
def test_typed_values_and_enums() -> None:
    config = ConfigurationLoader().load(str(REFERENCE_CONFIG))
    assert config.integrity.mode is IntegrityMode.SOURCE_AND_DESTINATION_HASH
    assert config.integrity.algorithm is HashAlgorithm.SHA256
    assert config.transfer.copy_buffer_size_bytes == 8388608
    assert config.control.socket_mode == 0o660
    assert config.stability.poll_count == 2
    assert config.paths.allowed_source_roots == (PurePosixPath("/recordings"),)


@pytest.mark.requirement("L2-CFG-001")
def test_defaults_applied_for_absent_sections() -> None:
    config = _load(MINIMAL_CONFIG)
    assert config.service.shutdown_timeout_seconds == 60
    assert config.service.poll_interval_seconds == 2.0
    assert config.transfer.max_concurrent_files == 2
    assert config.transfer.use_kernel_copy is True  # default
    assert config.integrity.enabled is True
    assert config.logging.level == "INFO"


@pytest.mark.requirement("L2-COPY-011")
def test_use_kernel_copy_can_be_disabled() -> None:
    config = _load(f"{MINIMAL_CONFIG}\n[transfer]\nuse_kernel_copy = false\n")
    assert config.transfer.use_kernel_copy is False


@pytest.mark.requirement("L2-CFG-005")
def test_application_config_is_immutable() -> None:
    config = _load(MINIMAL_CONFIG)
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.service.shutdown_timeout_seconds = 5  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.paths.claim_directory_name = "x"  # type: ignore[misc]


@pytest.mark.requirement("L2-CFG-002")
def test_unknown_section_is_rejected() -> None:
    text = MINIMAL_CONFIG + "\n[bogus]\nkey = value\n"
    assert ("bogus", None) in _issues(text)


@pytest.mark.requirement("L2-CFG-002")
def test_unknown_option_is_rejected() -> None:
    text = MINIMAL_CONFIG + "\n[integrity]\nenable = true\n"  # misspelled 'enabled'
    assert ("integrity", "enable") in _issues(text)


@pytest.mark.requirement("L2-CFG-002")
def test_duplicate_section_is_a_parse_error() -> None:
    text = MINIMAL_CONFIG + "\n[paths]\nclaim_directory_name = .other\n"
    with pytest.raises(ConfigurationValidationError) as excinfo:
        _load(text)
    assert len(excinfo.value.issues) == 1


@pytest.mark.requirement("L2-CFG-003")
def test_missing_required_option_is_rejected() -> None:
    text = "[paths]\nallowed_source_roots = /recordings\n"  # no destinations
    assert ("paths", "allowed_destination_roots") in _issues(text)


@pytest.mark.requirement("L2-CFG-003")
def test_missing_required_section_is_rejected() -> None:
    assert ("paths", None) in _issues("[service]\nshutdown_timeout_seconds = 60\n")


@pytest.mark.requirement("L2-CFG-004")
@pytest.mark.parametrize(
    ("section", "option", "value"),
    [
        ("service", "shutdown_timeout_seconds", "zero"),
        ("control", "socket_mode", "not-octal"),
        ("integrity", "enabled", "maybe"),
        ("integrity", "mode", "md5"),
        ("integrity", "algorithm", "crc32"),
        ("transfer", "copy_buffer_size_bytes", "1024"),  # below the 64 KiB floor
        ("transfer", "retry_max_delay_seconds", "abc"),  # non-numeric float
        ("transfer", "retry_initial_delay_seconds", "0"),  # exclusive lower bound (> 0)
        ("transfer", "retry_max_delay_seconds", "-1"),  # inclusive lower bound (>= 0)
        ("stability", "poll_count", "1"),  # below the minimum of 2
        ("logging", "level", "TRACE"),
        ("paths", "allowed_source_roots", "relative/path"),  # non-absolute (list)
        ("paths", "allowed_source_roots", ""),  # empty list
        ("paths", "claim_directory_name", "has/slash"),
        ("paths", "claim_directory_name", ""),  # empty single component
        ("paths", "temporary_file_prefix", ""),  # empty prefix
        ("paths", "temporary_file_prefix", "a/b"),  # prefix with separator
        ("service", "state_directory", ""),  # empty single path
        ("service", "state_directory", "relative"),  # non-absolute single path
    ],
)
def test_invalid_values_are_rejected(section: str, option: str, value: str) -> None:
    # Build a config with valid required paths, then inject the one bad value into its
    # own section (avoiding a duplicate [paths] section when section == "paths").
    config: dict[str, dict[str, str]] = {
        "paths": {
            "allowed_source_roots": "/recordings",
            "allowed_destination_roots": "/processing",
        }
    }
    config.setdefault(section, {})[option] = value
    text = "".join(
        f"[{sec}]\n" + "".join(f"{key} = {val}\n" for key, val in options.items())
        for sec, options in config.items()
    )
    assert (section, option) in _issues(text)


@pytest.mark.requirement("L2-CFG-004")
def test_cross_field_retry_bounds() -> None:
    text = (
        f"{MINIMAL_CONFIG}\n[transfer]\n"
        "retry_initial_delay_seconds = 100\nretry_max_delay_seconds = 10\n"
    )
    assert ("transfer", "retry_max_delay_seconds") in _issues(text)


@pytest.mark.requirement("L2-CFG-004")
def test_cross_field_source_destination_overlap() -> None:
    text = "[paths]\nallowed_source_roots = /data\nallowed_destination_roots = /data/out\n"
    assert ("paths", "allowed_destination_roots") in _issues(text)


@pytest.mark.requirement("L2-CFG-004")
def test_cross_field_state_directory_under_source() -> None:
    text = (
        "[paths]\nallowed_source_roots = /recordings\nallowed_destination_roots = /processing\n"
        "[service]\nstate_directory = /recordings/state\n"
    )
    assert ("service", "state_directory") in _issues(text)


@pytest.mark.requirement("L2-CFG-004")
def test_source_root_may_nest_under_state_directory() -> None:
    # A source root beneath the state directory is valid; only a state directory nested
    # inside a source root is rejected (the check is directional, not symmetric).
    config = _load(
        "[service]\nstate_directory = /data\n"
        "[paths]\nallowed_source_roots = /data/recordings\n"
        "allowed_destination_roots = /processing\n"
    )
    assert config.service.state_directory == PurePosixPath("/data")


@pytest.mark.requirement("L2-CFG-008")
def test_all_issues_reported_together() -> None:
    text = (
        "[bogus]\nx = 1\n"
        "[transfer]\ncopy_buffer_size_bytes = 10\nmax_concurrent_files = 0\n"
        "[integrity]\nmode = md5\n"
    )
    # Missing required [paths], unknown section, three bad values -> many issues at once.
    with pytest.raises(ConfigurationValidationError) as excinfo:
        _load(text)
    assert len(excinfo.value.issues) >= 5


@pytest.mark.requirement("L2-CFG-009")
def test_issue_records_identify_section_option_value_message() -> None:
    with pytest.raises(ConfigurationValidationError) as excinfo:
        _load(f"{MINIMAL_CONFIG}\n[stability]\npoll_count = 1\n")
    issue = next(i for i in excinfo.value.issues if i.option == "poll_count")
    assert issue.section == "stability"
    assert issue.value == "1"
    assert "2" in issue.message


@pytest.mark.requirement("L2-CFG-011")
def test_describe_schema_covers_sections_and_options() -> None:
    text = describe_schema()
    assert "[service]" in text
    assert "[paths]" in text
    assert "allowed_source_roots (required)" in text
    assert "claim_directory_name" in text


@pytest.mark.requirement("L2-CFG-003")
def test_unreadable_file_raises_configuration_error() -> None:
    with pytest.raises(ConfigurationError):
        ConfigurationLoader().load(str(REPO_ROOT / "config" / "does-not-exist.ini"))


@pytest.mark.requirement("L2-CFG-004")
def test_float_converter_without_minimum_accepts_any_number() -> None:
    assert _float_converter()("2.5") == 2.5


@pytest.mark.requirement("L2-CFG-004")
def test_path_converters_reject_nul_bytes() -> None:
    # NUL bytes can't travel through INI text, so exercise the guards directly.
    with pytest.raises(ValueError, match="NUL"):
        _posix_path("/a\x00b")
    with pytest.raises(ValueError, match="NUL"):
        _posix_path_list("/a\x00b")
