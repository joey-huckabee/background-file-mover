"""Tests for the CLI parser surface and dispatch (no service behavior yet)."""

from __future__ import annotations

import runpy

import pytest

from file_mover.cli import create_parser, main
from file_mover.jobs.models import ExitCode


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
        ["doctor"],
        ["recover"],
        ["submit", "--scenario-id", "s1", "--source", "/recordings/s1", "--destination", "/p"],
        ["service", "run"],
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
