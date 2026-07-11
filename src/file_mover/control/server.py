"""``ControlSocketServer`` — accepts local control connections for the service.

The server binds an ``AF_UNIX`` stream socket, handles a stale socket safely at bind
time (L2-CTL-008), and serves one request per connection on a small thread pool kept
separate from the transfer workers (L2-CTL-007). A malformed or oversized request is
answered with an error response and never crashes the server (L2-CTL-004).

The connection-handling logic (:meth:`ControlSocketServer.serve_connection`) operates on
any connected stream socket, so it is exercised directly over a :func:`socket.socketpair`
in tests; only :meth:`bind` and :meth:`serve_forever` are ``AF_UNIX``-specific.
"""

from __future__ import annotations

import logging
import os
import socket
import stat
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from file_mover.constants import DEFAULT_MAXIMUM_MESSAGE_BYTES, PROTOCOL_VERSION
from file_mover.control import protocol
from file_mover.control.dispatcher import CommandDispatcher
from file_mover.exceptions import ControlProtocolError, ServiceLockError

_DEFAULT_ACCEPT_TIMEOUT = 1.0
_DEFAULT_BACKLOG = 16


class ControlSocketServer:
    """Serves control requests over a Unix-domain stream socket."""

    def __init__(
        self,
        socket_path: str,
        dispatcher: CommandDispatcher,
        *,
        maximum_message_bytes: int = DEFAULT_MAXIMUM_MESSAGE_BYTES,
        socket_mode: int = 0o660,
        max_workers: int = 8,
        accept_timeout: float = _DEFAULT_ACCEPT_TIMEOUT,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialise the server.

        Args:
            socket_path: Filesystem path the control socket is bound at.
            dispatcher: Routes decoded requests to command handlers.
            maximum_message_bytes: Largest accepted request body.
            socket_mode: Permission bits applied to the bound socket.
            max_workers: Size of the control thread pool.
            accept_timeout: Poll interval for the accept loop so shutdown is responsive.
            logger: Optional logger; defaults to ``file_mover.control.server``.
        """
        self._path = socket_path
        self._dispatcher = dispatcher
        self._max_bytes = maximum_message_bytes
        self._socket_mode = socket_mode
        self._max_workers = max_workers
        self._accept_timeout = accept_timeout
        self._logger = logger or logging.getLogger("file_mover.control.server")
        self._socket: socket.socket | None = None
        self._stop = threading.Event()

    def serve_connection(self, conn: socket.socket) -> None:
        """Handle a single request/response exchange on a connected socket.

        Never raises: malformed input yields an error response, and a failure to send is
        logged. Safe to call on any connected stream socket.

        Args:
            conn: The connected client socket.
        """
        try:
            request = protocol.receive_message(conn, self._max_bytes)
        except ControlProtocolError as error:
            self._logger.warning("control: rejecting malformed request: %s", error)
            self._try_send(conn, _protocol_error_response(str(error)))
            return
        response = self._dispatcher.dispatch(request)
        self._try_send(conn, response)

    def _try_send(self, conn: socket.socket, message: dict[str, Any]) -> None:
        """Best-effort send of a response; failures are logged, not raised."""
        try:
            protocol.send_message(conn, message)
        except (OSError, ControlProtocolError) as error:
            self._logger.warning("control: failed to send response: %s", error)

    def bind(self) -> None:
        """Bind the Unix control socket, recovering from a stale socket safely."""
        _prepare_socket_path(self._path)
        server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server_socket.bind(self._path)
            os.chmod(self._path, self._socket_mode)  # noqa: PTH101 - AF_UNIX path, not a Path op
            server_socket.listen(_DEFAULT_BACKLOG)
        except OSError:
            server_socket.close()
            raise
        self._socket = server_socket

    def serve_forever(self) -> None:
        """Accept and serve connections until :meth:`stop` is called."""
        if self._socket is None:
            raise RuntimeError("bind() must be called before serve_forever()")
        self._socket.settimeout(self._accept_timeout)
        with ThreadPoolExecutor(
            max_workers=self._max_workers, thread_name_prefix="swit-control"
        ) as pool:
            while not self._stop.is_set():
                try:
                    conn, _ = self._socket.accept()
                except TimeoutError:
                    continue
                except OSError:
                    if self._stop.is_set():
                        break
                    raise
                pool.submit(self._serve_and_close, conn)

    def _serve_and_close(self, conn: socket.socket) -> None:
        """Serve one connection and always close it."""
        try:
            self.serve_connection(conn)
        finally:
            conn.close()

    def stop(self) -> None:
        """Signal the accept loop to exit."""
        self._stop.set()

    def close(self) -> None:
        """Close the listening socket and remove the socket file."""
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        path = Path(self._path)
        if path.is_socket():
            path.unlink(missing_ok=True)


def _prepare_socket_path(path: str) -> None:
    """Ensure ``path`` is free to bind, handling a stale socket safely.

    Absent path -> nothing to do. A live socket (a probe connects) -> refuse to start. A
    dead socket (connection refused) -> remove it. Any non-socket file -> refuse to
    remove it (L2-CTL-008).

    Raises:
        ServiceLockError: If another instance is listening, or an unexpected non-socket
            file occupies the path.
    """
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return
    if not stat.S_ISSOCK(info.st_mode):
        raise ServiceLockError(f"refusing to remove non-socket file at control path {path}")
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        probe.connect(path)
    except ConnectionRefusedError:
        os.unlink(path)  # noqa: PTH108 - AF_UNIX socket path, not a Path op
        return
    except OSError as error:
        raise ServiceLockError(f"cannot probe existing control socket {path}: {error}") from error
    finally:
        probe.close()
    raise ServiceLockError(f"another service instance is listening on {path}")


def _protocol_error_response(message: str) -> dict[str, Any]:
    """Build an error response for a request that could not be decoded."""
    return {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": None,
        "success": False,
        "error": {"code": "PROTOCOL_ERROR", "message": message},
    }
