"""The long-running ``BackgroundMoverService`` and its startup/shutdown lifecycle.

Milestone 3 delivers the first executable slice: the service acquires the singleton
process lock, binds the control socket (recovering from a stale socket safely), answers
``health``, and shuts down cleanly on ``SIGTERM``/``SIGINT``. The SQLite state, transfer
scheduler, and recovery reconciliation arrive in later milestones (see ``docs/ROADMAP.md``).

The signal handlers only set a thread-safe stop event; the drain happens on the main
thread. Tests drive the service on a worker thread with ``install_signal_handlers=False``
and stop it via :meth:`request_stop`.
"""

from __future__ import annotations

import logging
import signal
import threading
from collections.abc import Mapping
from typing import Any

from file_mover import __version__
from file_mover.configuration import ApplicationConfig
from file_mover.constants import PROTOCOL_VERSION
from file_mover.control.dispatcher import CommandDispatcher
from file_mover.control.lock import ProcessLock
from file_mover.control.server import ControlSocketServer

_LOCK_FILENAME = "service.lock"


class BackgroundMoverService:
    """Owns the control server, the singleton lock, and the shutdown lifecycle."""

    def __init__(self, config: ApplicationConfig, *, logger: logging.Logger | None = None) -> None:
        """Initialise the service.

        Args:
            config: The validated application configuration.
            logger: Optional logger; defaults to ``file_mover.service``.
        """
        self._config = config
        self._logger = logger or logging.getLogger("file_mover.service")
        self._server: ControlSocketServer | None = None
        self._stopping = threading.Event()
        self._ready = threading.Event()

    def run(self, *, install_signal_handlers: bool = True) -> int:
        """Acquire the lock, bind the socket, and serve until stopped.

        Args:
            install_signal_handlers: Install SIGTERM/SIGINT handlers (only possible on
                the main thread; disable when driving the service from a worker thread).

        Returns:
            ``0`` on a clean shutdown.
        """
        lock = ProcessLock(str(self._config.service.state_directory / _LOCK_FILENAME))
        lock.acquire()
        try:
            server = ControlSocketServer(
                str(self._config.service.socket_path),
                self._build_dispatcher(),
                maximum_message_bytes=self._config.control.maximum_message_bytes,
                socket_mode=self._config.control.socket_mode,
                max_workers=self._config.control.max_concurrent_requests,
                logger=self._logger,
            )
            server.bind()
            self._server = server
            if install_signal_handlers:
                self._install_signal_handlers()
            self._ready.set()
            self._logger.info("control service ready at %s", self._config.service.socket_path)
            server.serve_forever()
        finally:
            if self._server is not None:
                self._server.close()
                self._server = None
            self._ready.clear()
            lock.release()
        return 0

    def wait_ready(self, timeout: float | None = None) -> bool:
        """Block until the service is serving (or ``timeout`` elapses)."""
        return self._ready.wait(timeout)

    def request_stop(self) -> None:
        """Signal the service to stop accepting connections and drain."""
        self._stopping.set()
        if self._server is not None:
            self._server.stop()

    def _build_dispatcher(self) -> CommandDispatcher:
        """Build the control-command dispatcher for this service."""
        return CommandDispatcher({"health": self._handle_health})

    def _handle_health(self, _arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Return the service health snapshot."""
        return {
            "service_state": "stopping" if self._stopping.is_set() else "running",
            "protocol_version": PROTOCOL_VERSION,
            "app_version": __version__,
            "socket_path": str(self._config.service.socket_path),
        }

    def _install_signal_handlers(self) -> None:
        """Install SIGTERM/SIGINT handlers that only set the stop event."""

        def _handle(signum: int, _frame: object) -> None:
            self._logger.info("received signal %s; shutting down", signum)
            self.request_stop()

        signal.signal(signal.SIGTERM, _handle)
        signal.signal(signal.SIGINT, _handle)
