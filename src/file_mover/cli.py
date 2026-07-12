"""Command-line control interface for the Background File Mover.

The CLI is a thin, short-lived *client* of the durable background service — never
the transfer engine itself. :func:`create_parser` builds the argument parser and
performs no I/O, no database access, and starts no threads (L3-CLI-001.1). Each
subcommand delegates to a small handler that will (in later milestones) translate
the parsed arguments into a typed request, dispatch it to the service over the
control socket, render the result, and return a documented :class:`ExitCode`.

The parser surface is complete. ``config validate`` / ``doctor`` (M2) and ``health`` /
``service run`` (M3) are wired end-to-end; the remaining job commands (submit, status,
list, retry, stats, recover) report "not yet implemented" until their milestones land
(see ``docs/ROADMAP.md``).
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from file_mover import __version__
from file_mover.configuration import (
    ApplicationConfig,
    ConfigurationLoader,
    ConfigurationValidationError,
)
from file_mover.constants import APP_NAME, DEFAULT_CONFIG_PATH
from file_mover.control.client import ControlClient
from file_mover.exceptions import ConfigurationError, ServiceLockError, ServiceUnavailableError
from file_mover.jobs.models import ExitCode
from file_mover.logging_config import configure_logging
from file_mover.service import BackgroundMoverService


def _add_global_options(parser: argparse.ArgumentParser) -> None:
    """Attach options common to every invocation to ``parser``.

    Args:
        parser: The parser (top level or subcommand) to augment.
    """
    parser.add_argument(
        "--config",
        metavar="PATH",
        default=str(DEFAULT_CONFIG_PATH),
        help=f"path to the configuration file (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="increase verbosity: -v for INFO, -vv for DEBUG (default: WARNING)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="explicit log level; overrides -v/-vv when provided",
    )
    parser.add_argument(
        "--output",
        choices=["human", "json"],
        default="human",
        help="result rendering: human-readable (default) or machine JSON on stdout",
    )


def create_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser and all subcommands.

    This function is pure: it constructs parsers only and performs no I/O, database
    access, or thread creation (L3-CLI-001.1). Bad arguments and invalid choices are
    rejected here, before any service is contacted (L3-CLI-001.5).

    Returns:
        The fully configured top-level :class:`argparse.ArgumentParser`.
    """
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description="Durable background transfer coordinator for large simulation recordings.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{APP_NAME} {__version__}",
    )
    _add_global_options(parser)

    subcommands = parser.add_subparsers(dest="command", metavar="<command>")

    submit = subcommands.add_parser("submit", help="submit a completed recording set")
    _add_global_options(submit)
    submit.add_argument("--scenario-id", required=True, help="operator scenario identifier")
    source_group = submit.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--source", metavar="DIR", help="source directory to submit")
    source_group.add_argument(
        "--file-list", metavar="FILE", help="file containing newline-separated source paths"
    )
    submit.add_argument("--destination", required=True, metavar="DIR", help="destination root")

    status = subcommands.add_parser("status", help="show one job by id")
    _add_global_options(status)
    status.add_argument("job_id", help="job identifier")

    list_cmd = subcommands.add_parser("list", help="list jobs, optionally filtered by state")
    _add_global_options(list_cmd)
    list_cmd.add_argument(
        "--state",
        default="active",
        help="filter by job state group or name (default: active)",
    )

    retry = subcommands.add_parser("retry", help="retry a retained failed job")
    _add_global_options(retry)
    retry.add_argument("job_id", help="job identifier")

    _add_global_options(subcommands.add_parser("stats", help="show durable service statistics"))

    _add_global_options(subcommands.add_parser("health", help="query the running service"))

    config = subcommands.add_parser("config", help="configuration operations")
    config_sub = config.add_subparsers(dest="config_command", metavar="<config-command>")
    _add_global_options(
        config_sub.add_parser(
            "validate", help="validate configuration without starting the service"
        )
    )

    _add_global_options(
        subcommands.add_parser("doctor", help="validate configuration and filesystem access")
    )
    _add_global_options(
        subcommands.add_parser("recover", help="reconcile durable state after an interruption")
    )

    service = subcommands.add_parser("service", help="background service operations")
    service_sub = service.add_subparsers(dest="service_command", metavar="<service-command>")
    _add_global_options(
        service_sub.add_parser(
            "run", help="run the service in the foreground (systemd entry point)"
        )
    )

    return parser


def _not_implemented(command: str) -> ExitCode:
    """Report that ``command`` has no behavior yet in this milestone.

    Args:
        command: The command name to name in the diagnostic.

    Returns:
        :attr:`ExitCode.OPERATION_FAILED`.
    """
    print(
        f"{APP_NAME}: '{command}' is not implemented yet "
        f"(Foundation milestone; see docs/ROADMAP.md).",
        file=sys.stderr,
    )
    return ExitCode.OPERATION_FAILED


def _render_configuration_error(error: ConfigurationError, output: str) -> None:
    """Render a configuration load/validation failure (stdout JSON or stderr text)."""
    if isinstance(error, ConfigurationValidationError):
        if output == "json":
            payload = {
                "error_code": "CONFIGURATION_INVALID",
                "issues": [
                    {
                        "section": issue.section,
                        "option": issue.option,
                        "value": issue.value,
                        "message": issue.message,
                    }
                    for issue in error.issues
                ],
            }
            print(json.dumps(payload, indent=2))
        else:
            print(f"{APP_NAME}: {error}", file=sys.stderr)
            for issue in error.issues:
                location = issue.section
                if issue.option is not None:
                    location = f"{issue.section}.{issue.option}"
                print(f"  [{location}] {issue.message}", file=sys.stderr)
        return
    if output == "json":
        print(json.dumps({"error_code": "CONFIGURATION_ERROR", "message": str(error)}))
    else:
        print(f"{APP_NAME}: {error}", file=sys.stderr)


def _load_configuration(config_path: str, output: str) -> ApplicationConfig | ExitCode:
    """Load configuration, rendering and returning an exit code on failure.

    Returns:
        The validated configuration, or :attr:`ExitCode.CONFIGURATION_ERROR`.
    """
    try:
        return ConfigurationLoader().load(config_path)
    except ConfigurationError as error:
        _render_configuration_error(error, output)
        return ExitCode.CONFIGURATION_ERROR


def _validate_configuration(config_path: str, output: str) -> ExitCode:
    """Load and validate the configuration file, rendering the outcome.

    Machine output (``--output json``) is written to stdout; human diagnostics go to
    stderr (L2-CLI-005/006).

    Returns:
        :attr:`ExitCode.SUCCESS` if valid, otherwise :attr:`ExitCode.CONFIGURATION_ERROR`.
    """
    result = _load_configuration(config_path, output)
    if isinstance(result, ExitCode):
        return result
    if output == "json":
        print(json.dumps({"status": "ok", "message": "configuration valid"}))
    else:
        print("configuration valid")
    return ExitCode.SUCCESS


def _resolve_log_level(args: argparse.Namespace) -> str:
    """Resolve the effective log level from ``--log-level`` or ``-v``/``-vv``."""
    if args.log_level is not None:
        return str(args.log_level)
    return {0: "WARNING", 1: "INFO"}.get(args.verbose, "DEBUG")


def _query_service(
    config: ApplicationConfig, command: str, arguments: dict[str, Any]
) -> dict[str, Any] | ExitCode:
    """Send one command to the running service, mapping failures to exit codes.

    Returns:
        The response ``result`` object on success, or an :class:`ExitCode`
        (``SERVICE_UNAVAILABLE`` when nothing is listening, ``OPERATION_FAILED`` on a
        service error response).
    """
    client = ControlClient(str(config.service.socket_path))
    try:
        response = client.send(command, arguments)
    except ServiceUnavailableError as error:
        print(f"{APP_NAME}: {error}", file=sys.stderr)
        return ExitCode.SERVICE_UNAVAILABLE
    if not response.get("success"):
        print(f"{APP_NAME}: service error: {response.get('error', {})}", file=sys.stderr)
        return ExitCode.OPERATION_FAILED
    result = response.get("result", {})
    return result if isinstance(result, dict) else {}


def _handle_health(args: argparse.Namespace) -> ExitCode:
    """Query the running service's health over the control socket."""
    config = _load_configuration(args.config, args.output)
    if isinstance(config, ExitCode):
        return config
    result = _query_service(config, "health", {})
    if isinstance(result, ExitCode):
        return result
    if args.output == "json":
        print(json.dumps(result))
    else:
        for key, value in result.items():
            print(f"{key}: {value}")
    return ExitCode.SUCCESS


def _handle_status(args: argparse.Namespace) -> ExitCode:
    """Show one job by id."""
    config = _load_configuration(args.config, args.output)
    if isinstance(config, ExitCode):
        return config
    result = _query_service(config, "status", {"job_id": args.job_id})
    if isinstance(result, ExitCode):
        return result
    if args.output == "json":
        print(json.dumps(result))
        return ExitCode.SUCCESS if result.get("found") else ExitCode.JOB_NOT_FOUND
    if not result.get("found"):
        print(f"{APP_NAME}: job {args.job_id!r} not found", file=sys.stderr)
        return ExitCode.JOB_NOT_FOUND
    job = result.get("job") or {}
    for key, value in job.items():
        print(f"{key}: {value}")
    return ExitCode.SUCCESS


def _handle_list(args: argparse.Namespace) -> ExitCode:
    """List jobs, optionally filtered by state."""
    config = _load_configuration(args.config, args.output)
    if isinstance(config, ExitCode):
        return config
    result = _query_service(config, "list", {"state": args.state})
    if isinstance(result, ExitCode):
        return result
    if args.output == "json":
        print(json.dumps(result))
        return ExitCode.SUCCESS
    jobs = result.get("jobs", [])
    if not jobs:
        print("(no matching jobs)")
    for job in jobs:
        print(
            f"{job['job_id']}  {job['state']}  "
            f"files={job['file_count']}  bytes={job['bytes_copied']}/{job['total_bytes']}"
        )
    return ExitCode.SUCCESS


def _handle_stats(args: argparse.Namespace) -> ExitCode:
    """Show durable service statistics."""
    config = _load_configuration(args.config, args.output)
    if isinstance(config, ExitCode):
        return config
    result = _query_service(config, "stats", {})
    if isinstance(result, ExitCode):
        return result
    if args.output == "json":
        print(json.dumps(result))
        return ExitCode.SUCCESS
    print(f"total_jobs: {result.get('total_jobs')}")
    print(f"total_bytes: {result.get('total_bytes')}")
    print(f"bytes_copied: {result.get('bytes_copied')}")
    by_state = result.get("jobs_by_state", {})
    if isinstance(by_state, dict):
        for state, count in by_state.items():
            print(f"  {state}: {count}")
    return ExitCode.SUCCESS


def _handle_submit(args: argparse.Namespace) -> ExitCode:
    """Submit a completed recording set to the running service."""
    config = _load_configuration(args.config, args.output)
    if isinstance(config, ExitCode):
        return config
    arguments: dict[str, Any] = {
        "request_id": uuid.uuid4().hex,
        "scenario_id": args.scenario_id,
        "destination": args.destination,
    }
    if args.source:
        arguments["source"] = args.source
    if args.file_list:
        try:
            lines = Path(args.file_list).read_text(encoding="utf-8").splitlines()
        except OSError as error:
            print(f"{APP_NAME}: cannot read file list: {error}", file=sys.stderr)
            return ExitCode.INVALID_ARGUMENT
        arguments["file_list"] = [line.strip() for line in lines if line.strip()]

    result = _query_service(config, "submit", arguments)
    if isinstance(result, ExitCode):
        return result

    accepted = bool(result.get("accepted"))
    if args.output == "json":
        print(json.dumps(result))
        return ExitCode.SUCCESS if accepted else ExitCode.JOB_REJECTED
    if accepted:
        print(
            f"accepted {result.get('job_id')} "
            f"({result.get('claimed_file_count')} files, {result.get('claimed_bytes')} bytes)"
        )
        return ExitCode.SUCCESS
    print(
        f"{APP_NAME}: submission rejected "
        f"({result.get('error_code')}): {result.get('error_message')}",
        file=sys.stderr,
    )
    return ExitCode.JOB_REJECTED


def _handle_service_run(args: argparse.Namespace) -> ExitCode:
    """Load configuration and run the service in the foreground."""
    result = _load_configuration(args.config, args.output)
    if isinstance(result, ExitCode):
        return result
    configure_logging(_resolve_log_level(args))
    try:
        return ExitCode(BackgroundMoverService(result).run())
    except ServiceLockError as error:
        print(f"{APP_NAME}: {error}", file=sys.stderr)
        return ExitCode.SERVICE_UNAVAILABLE


def _handle_config(args: argparse.Namespace) -> ExitCode:
    """Dispatch a ``config`` subcommand."""
    if getattr(args, "config_command", None) != "validate":
        print(
            f"{APP_NAME}: 'config' requires a subcommand (e.g. 'config validate').",
            file=sys.stderr,
        )
        return ExitCode.INVALID_ARGUMENT
    return _validate_configuration(args.config, args.output)


def _handle_doctor(args: argparse.Namespace) -> ExitCode:
    """Run diagnostic checks. Milestone 2 covers configuration validation only."""
    print(
        f"{APP_NAME}: doctor — configuration checks only; "
        f"filesystem and service checks arrive in later milestones.",
        file=sys.stderr,
    )
    return _validate_configuration(args.config, args.output)


def main(argv: Sequence[str] | None = None) -> int:  # pylint: disable=too-many-return-statements
    """CLI entry point.

    Parses real arguments (``sys.argv`` when ``argv`` is ``None``), dispatches to the
    matching command handler, and returns its :class:`ExitCode`. A missing command
    prints help and returns :attr:`ExitCode.INVALID_ARGUMENT`.

    Args:
        argv: Argument vector excluding the program name; defaults to ``sys.argv[1:]``.

    Returns:
        The integer process exit status.
    """
    parser = create_parser()
    args = parser.parse_args(argv)

    command = getattr(args, "command", None)
    if command is None:
        parser.print_help(sys.stderr)
        return int(ExitCode.INVALID_ARGUMENT)

    if command == "config":
        return int(_handle_config(args))

    if command == "doctor":
        return int(_handle_doctor(args))

    if command == "health":
        return int(_handle_health(args))

    if command == "status":
        return int(_handle_status(args))

    if command == "list":
        return int(_handle_list(args))

    if command == "stats":
        return int(_handle_stats(args))

    if command == "submit":
        return int(_handle_submit(args))

    if command == "service":
        service_command = getattr(args, "service_command", None)
        if service_command is None:
            print(
                f"{APP_NAME}: 'service' requires a subcommand (e.g. 'service run').",
                file=sys.stderr,
            )
            return int(ExitCode.INVALID_ARGUMENT)
        if service_command == "run":
            return int(_handle_service_run(args))
        return int(_not_implemented(f"service {service_command}"))

    return int(_not_implemented(command))
