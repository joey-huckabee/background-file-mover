"""``ControlClient`` — sends one framed request to the running service.

The client generates a ``request_id`` per request, sends a single framed request, and
verifies the response echoes that id (L3-CTL-003). When no service is listening it raises
:class:`~file_mover.exceptions.ServiceUnavailableError` so the CLI can exit with
``SERVICE_UNAVAILABLE`` and never start work of its own.

:meth:`ControlClient.exchange_over` works on any connected stream socket (exercised over
a :func:`socket.socketpair` in tests); only :meth:`send` is ``AF_UNIX``-specific.
"""

from __future__ import annotations

import socket
import uuid
from collections.abc import Callable, Mapping
from typing import Any

from file_mover.constants import DEFAULT_MAXIMUM_MESSAGE_BYTES, PROTOCOL_VERSION
from file_mover.control import protocol
from file_mover.exceptions import ControlProtocolError, ServiceUnavailableError

_DEFAULT_CONNECT_TIMEOUT = 5.0


class ControlClient:
    """A short-lived client that exchanges one request/response with the service."""

    def __init__(
        self,
        socket_path: str,
        *,
        maximum_message_bytes: int = DEFAULT_MAXIMUM_MESSAGE_BYTES,
        connect_timeout: float = _DEFAULT_CONNECT_TIMEOUT,
        request_id_factory: Callable[[], str] | None = None,
    ) -> None:
        """Initialise the client.

        Args:
            socket_path: Path of the service control socket.
            maximum_message_bytes: Largest accepted response body.
            connect_timeout: Socket connect/receive timeout in seconds.
            request_id_factory: Optional id generator (defaults to a random hex uuid);
                injectable for deterministic tests.
        """
        self._path = socket_path
        self._max_bytes = maximum_message_bytes
        self._timeout = connect_timeout
        self._new_request_id = request_id_factory or (lambda: uuid.uuid4().hex)

    def exchange_over(
        self,
        sock: socket.socket,
        command: str,
        arguments: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send one request over ``sock`` and return the validated response.

        Args:
            sock: A connected stream socket.
            command: The command name.
            arguments: Optional command arguments.

        Returns:
            The decoded response object.

        Raises:
            ControlProtocolError: If the response id does not match the request id.
        """
        request_id = self._new_request_id()
        request = {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": request_id,
            "command": command,
            "arguments": dict(arguments or {}),
        }
        protocol.send_message(sock, request)
        response = protocol.receive_message(sock, self._max_bytes)
        echoed = response.get("request_id")
        if echoed != request_id:
            raise ControlProtocolError(
                f"response request_id {echoed!r} does not match request {request_id!r}"
            )
        return response

    def send(self, command: str, arguments: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Connect to the control socket, exchange one request, and return the response.

        Args:
            command: The command name.
            arguments: Optional command arguments.

        Returns:
            The decoded response object.

        Raises:
            ServiceUnavailableError: If no service is listening.
        """
        sock = self._connect()
        try:
            return self.exchange_over(sock, command, arguments)
        finally:
            sock.close()

    def _connect(self) -> socket.socket:
        """Open and connect an AF_UNIX socket, mapping failures to unavailability."""
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        except (AttributeError, OSError) as error:
            raise ServiceUnavailableError(
                f"AF_UNIX control sockets are unavailable on this platform: {error}"
            ) from error
        sock.settimeout(self._timeout)
        try:
            sock.connect(self._path)
        except OSError as error:
            sock.close()
            raise ServiceUnavailableError(
                f"no service is listening at {self._path}: {error}"
            ) from error
        return sock
