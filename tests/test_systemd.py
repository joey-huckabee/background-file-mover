"""Tests for the sd_notify service-manager notifier."""

from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest

from file_mover import systemd

_POSIX = pytest.mark.skipif(
    not hasattr(socket, "AF_UNIX"), reason="requires AF_UNIX datagram sockets (POSIX)"
)


@pytest.mark.requirement("L3-PY-010")
def test_notify_is_noop_without_notify_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOTIFY_SOCKET", raising=False)
    assert systemd.notify_ready() is False


@pytest.mark.requirement("L3-PY-010")
def test_notify_returns_false_on_unreachable_socket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A stale / missing socket path (or no AF_UNIX at all) must not raise.
    monkeypatch.setenv("NOTIFY_SOCKET", str(tmp_path / "does-not-exist.sock"))
    assert systemd.notify_watchdog() is False


@_POSIX
@pytest.mark.requirement("L2-CTL-011")
def test_notify_ready_and_stopping_send_datagrams(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    server.bind(str(tmp_path / "notify.sock"))
    server.settimeout(5)
    monkeypatch.setenv("NOTIFY_SOCKET", str(tmp_path / "notify.sock"))
    try:
        assert systemd.notify_ready() is True
        assert server.recv(64) == b"READY=1"
        assert systemd.notify_stopping() is True
        assert server.recv(64) == b"STOPPING=1"
    finally:
        server.close()


@_POSIX
@pytest.mark.requirement("L2-CTL-012")
def test_notify_watchdog_sends_keepalive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    server = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    server.bind(str(tmp_path / "notify.sock"))
    server.settimeout(5)
    monkeypatch.setenv("NOTIFY_SOCKET", str(tmp_path / "notify.sock"))
    try:
        assert systemd.notify_watchdog() is True
        assert server.recv(64) == b"WATCHDOG=1"
    finally:
        server.close()


@pytest.mark.skipif(sys.platform != "linux", reason="abstract sockets are Linux-only")
@pytest.mark.requirement("L3-PY-010")
def test_notify_translates_abstract_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    server = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    server.bind("\0file-mover-notify-test")  # abstract namespace (leading NUL)
    server.settimeout(5)
    monkeypatch.setenv("NOTIFY_SOCKET", "@file-mover-notify-test")  # '@' -> NUL
    try:
        assert systemd.notify("READY=1") is True
        assert server.recv(64) == b"READY=1"
    finally:
        server.close()
