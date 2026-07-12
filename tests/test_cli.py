"""Tests for the CLI parser surface and dispatch."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

import file_mover.cli as cli_module
from file_mover.cli import _parse_byte_rate, create_parser, main
from file_mover.diagnostics import EnvironmentCheck, Requirement
from file_mover.jobs.models import ExitCode

_MINIMAL_CONFIG = (
    "[paths]\n" "allowed_source_roots = /recordings\n" "allowed_destination_roots = /processing\n"
)


def _write_config(tmp_path: Path, text: str) -> str:
    path = tmp_path / "file-mover.ini"
    path.write_text(text, encoding="utf-8")
    return str(path)


class _FakeClient:
    """A ControlClient stand-in that returns a canned response."""

    def __init__(self, response: dict[str, object], *_args: object, **_kwargs: object) -> None:
        self._response = response

    def send(self, _command: str, _arguments: object = None) -> dict[str, object]:
        return self._response


def _patch_client(monkeypatch: pytest.MonkeyPatch, response: dict[str, object]) -> None:
    monkeypatch.setattr(
        "file_mover.cli.ControlClient", lambda *a, **k: _FakeClient(response, *a, **k)
    )


def _ok(result: dict[str, object]) -> dict[str, object]:
    return {"protocol_version": 1, "request_id": "r", "success": True, "result": result}


def _env_check(
    available: bool, requirement: Requirement = Requirement.REQUIRED
) -> EnvironmentCheck:
    return EnvironmentCheck("cap", requirement, lambda: (available, "detail"))


def _patch_env(monkeypatch: pytest.MonkeyPatch, checks: list[EnvironmentCheck]) -> None:
    # Make doctor's environment checks deterministic regardless of the test host.
    monkeypatch.setattr("file_mover.cli.default_checks", lambda **_kwargs: checks)


@pytest.mark.requirement("L3-CLI-001")
def test_create_parser_is_pure_and_builds() -> None:
    # Building the parser must not raise and must expose the documented commands.
    parser = create_parser()
    help_text = parser.format_help()
    commands = (
        "submit",
        "status",
        "list",
        "retry",
        "stats",
        "throttle",
        "pause",
        "resume",
        "cancel",
        "doctor",
        "recover",
    )
    for command in (*commands, "service"):
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
        ["retry", "job-123"],
        ["recover"],
    ],
)
def test_known_commands_report_not_implemented(argv: list[str]) -> None:
    # Foundation milestone: every command parses and returns OPERATION_FAILED.
    assert main(argv) == ExitCode.OPERATION_FAILED


@pytest.mark.requirement("L2-CLI-002")
def test_service_without_subcommand_is_invalid() -> None:
    assert main(["service"]) == ExitCode.INVALID_ARGUMENT


@pytest.mark.requirement("L2-CLI-010")
def test_main_converts_unexpected_error_to_internal_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(_args: object) -> ExitCode:
        raise RuntimeError("kaboom")

    monkeypatch.setitem(cli_module._COMMAND_HANDLERS, "stats", _boom)
    path = _write_config(tmp_path, _MINIMAL_CONFIG)
    assert main(["stats", "--config", path]) == ExitCode.INTERNAL_ERROR


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
def test_doctor_validates_configuration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_env(monkeypatch, [])  # no environment checks -> passes regardless of host
    path = _write_config(tmp_path, _MINIMAL_CONFIG)
    assert main(["doctor", "--config", path]) == ExitCode.SUCCESS


@pytest.mark.requirement("L3-PY-013")
def test_doctor_reports_advisories(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env(monkeypatch, [])
    path = _write_config(tmp_path, _MINIMAL_CONFIG + "[transfer]\nmax_bytes_per_second = 1000\n")
    assert main(["doctor", "--config", path]) == ExitCode.SUCCESS
    captured = capsys.readouterr()
    assert "configuration valid" in captured.out
    assert "advisory:" in captured.err and "bandwidth limit" in captured.err


@pytest.mark.requirement("L3-PY-013")
def test_doctor_json_includes_advisories(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env(monkeypatch, [])
    path = _write_config(tmp_path, _MINIMAL_CONFIG + "[transfer]\nmax_bytes_per_second = 1000\n")
    assert main(["doctor", "--config", path, "--output", "json"]) == ExitCode.SUCCESS
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert any("bandwidth" in note for note in payload["advisories"])


@pytest.mark.requirement("L2-ENV-001")
def test_doctor_passes_when_environment_ok(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env(monkeypatch, [_env_check(True), _env_check(False, Requirement.OPTIONAL)])
    path = _write_config(tmp_path, _MINIMAL_CONFIG)
    assert main(["doctor", "--config", path]) == ExitCode.SUCCESS  # warnings do not fail
    assert "[pass]" in capsys.readouterr().out


@pytest.mark.requirement("L2-ENV-001")
def test_doctor_fails_when_required_capability_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env(monkeypatch, [_env_check(False)])  # a required capability is missing
    path = _write_config(tmp_path, _MINIMAL_CONFIG)
    assert main(["doctor", "--config", path]) == ExitCode.ENVIRONMENT_UNSUPPORTED
    assert "environment unsupported" in capsys.readouterr().err


@pytest.mark.requirement("L2-ENV-001")
def test_doctor_json_reports_environment(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_env(monkeypatch, [_env_check(False)])
    path = _write_config(tmp_path, _MINIMAL_CONFIG)
    code = main(["doctor", "--config", path, "--output", "json"])
    assert code == ExitCode.ENVIRONMENT_UNSUPPORTED
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "environment_unsupported"
    assert payload["environment"][0]["status"] == "fail"


@pytest.mark.requirement("L3-PY-013")
def test_cli_log_level_override_precedence() -> None:
    from argparse import Namespace

    assert cli_module._cli_log_level_override(Namespace(log_level="ERROR", verbose=0)) == "ERROR"
    assert cli_module._cli_log_level_override(Namespace(log_level=None, verbose=1)) == "INFO"
    assert cli_module._cli_log_level_override(Namespace(log_level=None, verbose=2)) == "DEBUG"
    # No CLI flag -> None, so the config level applies.
    assert cli_module._cli_log_level_override(Namespace(log_level=None, verbose=0)) is None


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


@pytest.mark.requirement("L2-JOB-006")
@pytest.mark.parametrize(
    "argv",
    [["status", "j1"], ["list"], ["stats"], ["pause", "j1"], ["resume", "j1"], ["cancel", "j1"]],
)
def test_query_commands_report_service_unavailable_when_down(
    tmp_path: Path, argv: list[str]
) -> None:
    path = _write_config(tmp_path, _MINIMAL_CONFIG)
    assert main([*argv, "--config", path]) == ExitCode.SERVICE_UNAVAILABLE


@pytest.mark.requirement("L2-LIF-004")
@pytest.mark.parametrize("command", ["pause", "resume", "cancel"])
def test_lifecycle_commands_render_accepted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    _patch_client(monkeypatch, _ok({"accepted": True, "job_id": "j1", "state": "paused"}))
    path = _write_config(tmp_path, _MINIMAL_CONFIG)
    assert main([command, "j1", "--config", path]) == ExitCode.SUCCESS
    assert f"{command} accepted for j1" in capsys.readouterr().out


@pytest.mark.requirement("L2-LIF-005")
def test_lifecycle_unknown_job_is_job_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_client(
        monkeypatch,
        _ok({"accepted": False, "job_id": "j9", "error_code": "NOT_FOUND", "error_message": "x"}),
    )
    path = _write_config(tmp_path, _MINIMAL_CONFIG)
    assert main(["cancel", "j9", "--config", path]) == ExitCode.JOB_NOT_FOUND


@pytest.mark.requirement("L2-JOB-006")
def test_status_found_renders_human(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_client(monkeypatch, _ok({"found": True, "job": {"job_id": "j1", "state": "queued"}}))
    path = _write_config(tmp_path, _MINIMAL_CONFIG)
    assert main(["status", "j1", "--config", path]) == ExitCode.SUCCESS
    assert "state: queued" in capsys.readouterr().out


@pytest.mark.requirement("L2-JOB-006")
def test_status_not_found_returns_job_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_client(monkeypatch, _ok({"found": False, "job": None}))
    path = _write_config(tmp_path, _MINIMAL_CONFIG)
    assert main(["status", "j9", "--config", path]) == ExitCode.JOB_NOT_FOUND
    assert main(["status", "j9", "--config", path, "--output", "json"]) == ExitCode.JOB_NOT_FOUND


@pytest.mark.requirement("L2-CLI-004")
def test_list_and_stats_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_config(tmp_path, _MINIMAL_CONFIG)
    job = {"job_id": "j1", "state": "queued", "file_count": 2, "bytes_copied": 5, "total_bytes": 10}
    _patch_client(monkeypatch, _ok({"jobs": [job]}))
    assert main(["list", "--config", path]) == ExitCode.SUCCESS
    assert "j1" in capsys.readouterr().out
    assert main(["list", "--config", path, "--output", "json"]) == ExitCode.SUCCESS

    _patch_client(monkeypatch, _ok({"jobs": []}))
    assert main(["list", "--config", path]) == ExitCode.SUCCESS
    assert "no matching jobs" in capsys.readouterr().out

    _patch_client(
        monkeypatch,
        _ok(
            {"total_jobs": 1, "total_bytes": 10, "bytes_copied": 5, "jobs_by_state": {"queued": 1}}
        ),
    )
    assert main(["stats", "--config", path]) == ExitCode.SUCCESS
    assert "total_jobs: 1" in capsys.readouterr().out
    assert main(["stats", "--config", path, "--output", "json"]) == ExitCode.SUCCESS


@pytest.mark.requirement("L2-CTL-010")
def test_health_renders_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_client(monkeypatch, _ok({"service_state": "running"}))
    path = _write_config(tmp_path, _MINIMAL_CONFIG)
    assert main(["health", "--config", path, "--output", "json"]) == ExitCode.SUCCESS
    assert json.loads(capsys.readouterr().out)["service_state"] == "running"


@pytest.mark.requirement("L2-CTL-005")
def test_service_error_response_is_operation_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "file_mover.cli.ControlClient",
        lambda *a, **k: _FakeClient(
            {"success": False, "error": {"code": "UNKNOWN_COMMAND", "message": "x"}}
        ),
    )
    path = _write_config(tmp_path, _MINIMAL_CONFIG)
    assert main(["health", "--config", path]) == ExitCode.OPERATION_FAILED


@pytest.mark.requirement("L2-CLI-008")
def test_submit_reports_service_unavailable_when_down(tmp_path: Path) -> None:
    path = _write_config(tmp_path, _MINIMAL_CONFIG)
    argv = [
        "submit",
        "--scenario-id",
        "s",
        "--source",
        "/recordings/s",
        "--destination",
        "/processing/s",
        "--config",
        path,
    ]
    assert main(argv) == ExitCode.SERVICE_UNAVAILABLE


@pytest.mark.requirement("L2-CLI-008")
def test_submit_renders_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(
        monkeypatch,
        _ok(
            {
                "accepted": True,
                "job_id": "jx",
                "claimed_file_count": 2,
                "claimed_bytes": 10,
                "state": "queued",
            }
        ),
    )
    path = _write_config(tmp_path, _MINIMAL_CONFIG)
    argv = [
        "submit",
        "--scenario-id",
        "s",
        "--source",
        "/recordings/s",
        "--destination",
        "/processing/s",
        "--config",
        path,
    ]
    assert main(argv) == ExitCode.SUCCESS


@pytest.mark.requirement("L2-CLI-008")
def test_submit_renders_rejected_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(
        monkeypatch,
        _ok(
            {
                "accepted": False,
                "error_code": "InvalidSourceError",
                "error_message": "x",
                "job_id": None,
                "state": "failed_retained",
                "claimed_file_count": 0,
                "claimed_bytes": 0,
            }
        ),
    )
    path = _write_config(tmp_path, _MINIMAL_CONFIG)
    argv = [
        "submit",
        "--scenario-id",
        "s",
        "--source",
        "/recordings/s",
        "--destination",
        "/processing/s",
        "--config",
        path,
        "--output",
        "json",
    ]
    assert main(argv) == ExitCode.JOB_REJECTED


@pytest.mark.requirement("L2-CLI-008")
def test_submit_reads_file_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(
        monkeypatch,
        _ok(
            {
                "accepted": True,
                "job_id": "jx",
                "claimed_file_count": 1,
                "claimed_bytes": 3,
                "state": "queued",
            }
        ),
    )
    file_list = tmp_path / "files.txt"
    file_list.write_text("/recordings/s/a.dat\n\n", encoding="utf-8")
    path = _write_config(tmp_path, _MINIMAL_CONFIG)
    argv = [
        "submit",
        "--scenario-id",
        "s",
        "--file-list",
        str(file_list),
        "--destination",
        "/processing/s",
        "--config",
        path,
    ]
    assert main(argv) == ExitCode.SUCCESS


@pytest.mark.requirement("L2-CLI-008")
def test_submit_missing_file_list_is_invalid_argument(tmp_path: Path) -> None:
    path = _write_config(tmp_path, _MINIMAL_CONFIG)
    argv = [
        "submit",
        "--scenario-id",
        "s",
        "--file-list",
        str(tmp_path / "nope.txt"),
        "--destination",
        "/processing/s",
        "--config",
        path,
    ]
    assert main(argv) == ExitCode.INVALID_ARGUMENT


@pytest.mark.requirement("L2-BWL-001")
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0", 0),
        ("1000", 1000),
        ("50MB", 50_000_000),
        ("50mb", 50_000_000),
        ("1GiB", 1024**3),
        ("64KiB", 65536),
        ("2G", 2_000_000_000),
        ("1.5M", 1_500_000),
    ],
)
def test_parse_byte_rate_accepts_suffixes(text: str, expected: int) -> None:
    assert _parse_byte_rate(text) == expected


@pytest.mark.requirement("L2-BWL-001")
@pytest.mark.parametrize("text", ["", "abc", "-5", "10Q", "MB", "1.2.3"])
def test_parse_byte_rate_rejects_bad_values(text: str) -> None:
    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        _parse_byte_rate(text)


@pytest.mark.requirement("L2-BWL-002")
def test_throttle_reports_service_unavailable_when_down(tmp_path: Path) -> None:
    path = _write_config(tmp_path, _MINIMAL_CONFIG)
    assert main(["throttle", "50MB", "--config", path]) == ExitCode.SERVICE_UNAVAILABLE


@pytest.mark.requirement("L2-BWL-002")
def test_throttle_renders_applied_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_client(monkeypatch, _ok({"accepted": True, "bytes_per_second": 50_000_000}))
    path = _write_config(tmp_path, _MINIMAL_CONFIG)
    assert main(["throttle", "50MB", "--config", path]) == ExitCode.SUCCESS
    assert "50000000 bytes/sec" in capsys.readouterr().out
    # JSON rendering and the "unlimited" branch.
    _patch_client(monkeypatch, _ok({"accepted": True, "bytes_per_second": 0}))
    assert main(["throttle", "0", "--config", path]) == ExitCode.SUCCESS
    assert "unlimited" in capsys.readouterr().out
    assert main(["throttle", "0", "--config", path, "--output", "json"]) == ExitCode.SUCCESS


@pytest.mark.requirement("L2-BWL-002")
def test_throttle_rejected_is_invalid_argument(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_client(
        monkeypatch,
        _ok({"accepted": False, "bytes_per_second": 0, "error_message": "bad"}),
    )
    path = _write_config(tmp_path, _MINIMAL_CONFIG)
    assert main(["throttle", "100", "--config", path]) == ExitCode.INVALID_ARGUMENT


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


@pytest.mark.requirement("L3-PY-013")
def test_configure_service_logging_applies_config(monkeypatch: pytest.MonkeyPatch) -> None:
    from argparse import Namespace

    from file_mover.configuration import ConfigurationLoader

    captured: dict[str, object] = {}
    monkeypatch.setattr(
        cli_module,
        "configure_logging",
        lambda level, *, to_stderr, log_file: captured.update(
            level=level, to_stderr=to_stderr, log_file=log_file
        ),
    )
    config = ConfigurationLoader().load_text(
        _MINIMAL_CONFIG
        + "[logging]\nlevel = DEBUG\nlog_to_file = true\nlog_directory = /var/log/xyz\n"
    )
    cli_module._configure_service_logging(Namespace(log_level=None, verbose=0), config)
    assert captured["level"] == "DEBUG"  # config level applied (no CLI override)
    assert captured["to_stderr"] is True  # log_to_journal default
    log_file = captured["log_file"]
    assert log_file is not None and log_file.name == "file-mover.log"


@pytest.mark.requirement("L3-PY-013")
def test_configure_service_logging_cli_level_wins_and_no_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argparse import Namespace

    from file_mover.configuration import ConfigurationLoader

    captured: dict[str, object] = {}
    monkeypatch.setattr(
        cli_module,
        "configure_logging",
        lambda level, *, to_stderr, log_file: captured.update(level=level, log_file=log_file),
    )
    config = ConfigurationLoader().load_text(_MINIMAL_CONFIG + "[logging]\nlevel = ERROR\n")
    cli_module._configure_service_logging(Namespace(log_level=None, verbose=2), config)  # -vv
    assert captured["level"] == "DEBUG"  # CLI verbosity overrides the config ERROR level
    assert captured["log_file"] is None  # log_to_file defaults false -> no file handler
