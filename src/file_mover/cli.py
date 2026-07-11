"""Command-line control interface for the Background File Mover.

The CLI is a thin, short-lived *client* of the durable background service — never
the transfer engine itself. :func:`create_parser` builds the argument parser and
performs no I/O, no database access, and starts no threads (L3-CLI-001.1). Each
subcommand delegates to a small handler that will (in later milestones) translate
the parsed arguments into a typed request, dispatch it to the service over the
control socket, render the result, and return a documented :class:`ExitCode`.

Milestone 1 ships the full parser surface — ``--help``, ``--version``, verbosity
flags, and every subcommand — with handlers that report "not yet implemented" and
return :attr:`ExitCode.OPERATION_FAILED`. The socket client, service, and per-command
result rendering arrive in Milestones 2-7 (see ``docs/ROADMAP.md``).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from file_mover import __version__
from file_mover.constants import APP_NAME, DEFAULT_CONFIG_PATH
from file_mover.jobs.models import ExitCode


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

    stats = subcommands.add_parser("stats", help="show durable service statistics")
    _add_global_options(stats)

    doctor = subcommands.add_parser("doctor", help="validate configuration and filesystem access")
    _add_global_options(doctor)

    recover = subcommands.add_parser(
        "recover", help="reconcile durable state after an interruption"
    )
    _add_global_options(recover)

    service = subcommands.add_parser("service", help="background service operations")
    service_sub = service.add_subparsers(dest="service_command", metavar="<service-command>")
    service_run = service_sub.add_parser(
        "run", help="run the service in the foreground (systemd entry point)"
    )
    _add_global_options(service_run)

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


def main(argv: Sequence[str] | None = None) -> int:
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

    if command == "service":
        service_command = getattr(args, "service_command", None)
        if service_command is None:
            print(
                f"{APP_NAME}: 'service' requires a subcommand (e.g. 'service run').",
                file=sys.stderr,
            )
            return int(ExitCode.INVALID_ARGUMENT)
        return int(_not_implemented(f"service {service_command}"))

    return int(_not_implemented(command))
