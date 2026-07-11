"""Tests for the CLI parser surface and dispatch."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

from file_mover.cli import create_parser, main
from file_mover.jobs.models import ExitCode

_MINIMAL_CONFIG = (
    "[paths]\n" "allowed_source_roots = /recordings\n" "allowed_destination_roots = /processing\n"
)


def _write_config(tmp_path: Path, text: str) -> str:
    path = tmp_path / "file-mover.ini"
    path.write_text(text, encoding="utf-8")
    return str(path)


@pytest.mark.requirement("L3-CLI-001")
def test_create_parser_is_pure_and_builds() -> None:
    # Building the parser must not raise and must expose the documented commands.
    parser = create_parser()
    help_text = parser.format_help()
    for command in ("submit", "status", "list", "retry", "stats", "doctor", "recover", "service"):
        assert command in help_text


@pytest.mark.requirement("L2-CLI-003")
def test_version_action_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert "file-mover" in capsys.readouterr().out


@pytest.mark.requirement("L2-CLI-011")
def test_no_command_prints_help_and_returns_invalid_argument() -> None:
    assert main([]) == ExitCode.INVALID_ARGUMENT


@pytest.mark.requirement("L3-CLI-005")
def test_invalid_choice_is_rejected_before_dispatch() -> None:
    # argparse rejects unknown subcommands with exit code 2 before any handler runs.
    with pytest.raises(SystemExit) as excinfo:
        main(["nonsense-command"])
    assert excinfo.value.code == 2


@pytest.mark.requirement("L2-CLI-002")
@pytest.mark.parametrize(
    "argv",
    [
        ["status", "job-123"],
        ["list"],
        ["retry", "job-123"],
        ["stats"],
        ["recover"],
        ["submit", "--scenario-id", "s1", "--source", "/recordings/s1", "--destination", "/p"],
    ],
)
def test_known_commands_report_not_implemented(argv: list[str]) -> None:
    # Foundation milestone: every command parses and returns OPERATION_FAILED.
    assert main(argv) == ExitCode.OPERATION_FAILED


@pytest.mark.requirement("L2-CLI-002")
def test_service_without_subcommand_is_invalid() -> None:
    assert main(["service"]) == ExitCode.INVALID_ARGUMENT


@pytest.mark.requirement("L3-CLI-005")
def test_submit_requires_a_source() -> None:
    # --source / --file-list are mutually exclusive and required.
    with pytest.raises(SystemExit) as excinfo:
        main(["submit", "--scenario-id", "s1", "--destination", "/p"])
    assert excinfo.value.code == 2


@pytest.mark.requirement("L2-CLI-011")
def test_module_entry_point_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    # Exercise `python -m file_mover` in-process so __main__.py is covered.
    monkeypatch.setattr("sys.argv", ["file-mover"])
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("file_mover", run_name="__main__")
    assert excinfo.value.code == ExitCode.INVALID_ARGUMENT


@pytest.mark.requirement("L2-CFG-007")
def test_config_validate_accepts_valid_config(tmp_path: Path) -> None:
    path = _write_config(tmp_path, _MINIMAL_CONFIG)
    assert main(["config", "validate", "--config", path]) == ExitCode.SUCCESS


@pytest.mark.requirement("L2-CLI-004")
def test_config_validate_valid_json_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_config(tmp_path, _MINIMAL_CONFIG)
    code = main(["config", "validate", "--config", path, "--output", "json"])
    assert code == ExitCode.SUCCESS
    assert json.loads(capsys.readouterr().out)["status"] == "ok"


@pytest.mark.requirement("L2-CFG-006")
def test_config_validate_rejects_invalid_config(tmp_path: Path) -> None:
    path = _write_config(tmp_path, "[nonsense]\nx = 1\n")
    assert main(["config", "validate", "--config", path]) == ExitCode.CONFIGURATION_ERROR


@pytest.mark.requirement("L2-CLI-004")
def test_config_validate_json_output_on_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_config(tmp_path, "[nonsense]\nx = 1\n")
    code = main(["config", "validate", "--config", path, "--output", "json"])
    assert code == ExitCode.CONFIGURATION_ERROR
    payload = json.loads(capsys.readouterr().out)  # stdout must be pure JSON
    assert payload["error_code"] == "CONFIGURATION_INVALID"
    assert any(issue["section"] == "nonsense" for issue in payload["issues"])


@pytest.mark.requirement("L2-CLI-002")
def test_config_without_subcommand_is_invalid() -> None:
    assert main(["config"]) == ExitCode.INVALID_ARGUMENT


@pytest.mark.requirement("L2-CFG-007")
def test_doctor_validates_configuration(tmp_path: Path) -> None:
    path = _write_config(tmp_path, _MINIMAL_CONFIG)
    assert main(["doctor", "--config", path]) == ExitCode.SUCCESS


@pytest.mark.requirement("L2-CFG-006")
def test_config_validate_missing_file_human(tmp_path: Path) -> None:
    missing = str(tmp_path / "nope.ini")
    assert main(["config", "validate", "--config", missing]) == ExitCode.CONFIGURATION_ERROR


@pytest.mark.requirement("L2-CFG-006")
def test_config_validate_missing_file_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = str(tmp_path / "nope.ini")
    code = main(["config", "validate", "--config", missing, "--output", "json"])
    assert code == ExitCode.CONFIGURATION_ERROR
    payload = json.loads(capsys.readouterr().out)
    assert payload["error_code"] == "CONFIGURATION_ERROR"


@pytest.mark.requirement("L2-CTL-010")
def test_health_reports_service_unavailable_when_down(tmp_path: Path) -> None:
    # No service is listening at the (default) socket path -> SERVICE_UNAVAILABLE, and on
    # a non-POSIX host AF_UNIX is unavailable, which maps to the same controlled result.
    path = _write_config(tmp_path, _MINIMAL_CONFIG)
    assert main(["health", "--config", path]) == ExitCode.SERVICE_UNAVAILABLE


@pytest.mark.requirement("L2-CTL-008")
def test_service_run_reports_unavailable_without_lockable_state(tmp_path: Path) -> None:
    # state_directory cannot be locked (missing dir on POSIX; no fcntl elsewhere): the
    # service refuses to start with a controlled SERVICE_UNAVAILABLE rather than crashing.
    config_text = (
        "[service]\nstate_directory = /nonexistent-swit-dir/state\n"
        "[paths]\nallowed_source_roots = /recordings\n"
        "allowed_destination_roots = /processing\n"
    )
    path = _write_config(tmp_path, config_text)
    assert main(["service", "run", "--config", path]) == ExitCode.SERVICE_UNAVAILABLE
