"""``CommandDispatcher`` — routes decoded control requests to registered handlers.

The dispatcher owns an explicit ``{command_name: handler}`` mapping and never performs
dynamic dispatch on a user-supplied name (L3-CTL-002). It validates the request envelope
(protocol version, request id, command), rejects unknown commands, and isolates handler
failures so a raising handler produces an error response rather than crashing the service
(L2-CTL-004). Every response echoes the request id (L3-CTL-003).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from file_mover.constants import PROTOCOL_VERSION

CommandHandler = Callable[[Mapping[str, Any]], dict[str, Any]]
"""A handler maps a request's ``arguments`` mapping to a result object."""


class CommandDispatcher:
    """Validates control requests and dispatches them to command handlers."""

    def __init__(self, handlers: Mapping[str, CommandHandler]) -> None:
        """Initialise with the command handler map.

        Args:
            handlers: Mapping of command name to handler. Copied defensively.
        """
        self._handlers: dict[str, CommandHandler] = dict(handlers)

    @property
    def commands(self) -> tuple[str, ...]:
        """The registered command names, sorted."""
        return tuple(sorted(self._handlers))

    def dispatch(  # pylint: disable=too-many-return-statements
        self, request: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Validate and route one request, returning the response object.

        This never raises for an invalid request or a failing handler: every outcome
        maps to a success or error response object.

        Args:
            request: The decoded request envelope.

        Returns:
            A response object (``success: true`` with ``result`` or ``success: false``
            with ``error``).
        """
        request_id = request.get("request_id")
        if not isinstance(request_id, str):
            return _error(None, "BAD_REQUEST", "missing or invalid request_id")

        if request.get("protocol_version") != PROTOCOL_VERSION:
            return _error(
                request_id,
                "UNSUPPORTED_PROTOCOL",
                f"expected protocol_version {PROTOCOL_VERSION}",
            )

        command = request.get("command")
        if not isinstance(command, str):
            return _error(request_id, "BAD_REQUEST", "missing or invalid command")

        handler = self._handlers.get(command)
        if handler is None:
            return _error(request_id, "UNKNOWN_COMMAND", f"unknown command {command!r}")

        arguments = request.get("arguments", {})
        if not isinstance(arguments, Mapping):
            return _error(request_id, "BAD_REQUEST", "arguments must be an object")

        try:
            result = handler(arguments)
        except Exception as error:  # pylint: disable=broad-exception-caught
            # A handler failure must never take down the control server (L2-CTL-004).
            return _error(request_id, "INTERNAL_ERROR", str(error))

        return _success(request_id, result)


def _success(request_id: str, result: dict[str, Any]) -> dict[str, Any]:
    """Build a success response echoing ``request_id``."""
    return {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request_id,
        "success": True,
        "result": result,
    }


def _error(request_id: str | None, code: str, message: str) -> dict[str, Any]:
    """Build an error response echoing ``request_id`` (``None`` if unparseable)."""
    return {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request_id,
        "success": False,
        "error": {"code": code, "message": message},
    }
