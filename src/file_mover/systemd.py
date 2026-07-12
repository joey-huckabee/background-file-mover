"""Minimal ``sd_notify`` service-manager notification (standard library only).

When systemd starts the service with ``Type=notify`` it sets ``NOTIFY_SOCKET`` to an
``AF_UNIX`` datagram socket and waits for a ``READY=1`` message before considering the
unit started — so units ordered after the mover, and orchestration keyed off "service
started", never race the control socket into existence (L2-CTL-011). The same channel
carries a periodic ``WATCHDOG=1`` liveness signal so a hung service is restarted
(L2-CTL-012), and a ``STOPPING=1`` message during the drain.

This is implemented with a plain ``socket`` datagram — no ``libsystemd`` dependency
(L3-PY-010). Every function is a safe no-op (returns ``False``) when ``NOTIFY_SOCKET`` is
unset or the send fails, so the service runs identically outside systemd, in tests, and
on non-POSIX hosts.
"""

from __future__ import annotations

import os
import socket

_NOTIFY_SOCKET_ENV = "NOTIFY_SOCKET"


def notify(state: str) -> bool:
    """Send a service ``state`` line to ``$NOTIFY_SOCKET``.

    Args:
        state: An ``sd_notify`` assignment such as ``"READY=1"``.

    Returns:
        ``True`` if the datagram was sent, ``False`` if notification is unavailable or
        the send failed (never raises).
    """
    address = os.environ.get(_NOTIFY_SOCKET_ENV)
    if not address:
        return False
    # A leading '@' selects the Linux abstract namespace, encoded as a leading NUL byte.
    if address.startswith("@"):
        address = "\0" + address[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.sendto(state.encode("utf-8"), address)
    except (OSError, AttributeError):
        return False  # NOTIFY_SOCKET stale, or AF_UNIX unavailable on this platform
    return True


def notify_ready() -> bool:
    """Tell the service manager the service is ready to serve (``READY=1``)."""
    return notify("READY=1")


def notify_stopping() -> bool:
    """Tell the service manager the service is shutting down (``STOPPING=1``)."""
    return notify("STOPPING=1")


def notify_watchdog() -> bool:
    """Send a watchdog liveness keep-alive (``WATCHDOG=1``)."""
    return notify("WATCHDOG=1")
