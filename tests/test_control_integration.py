"""Cross-platform control server/client integration over a socketpair."""

from __future__ import annotations

import socket
import struct
import threading
from collections.abc import Mapping
from typing import Any

import pytest

from file_mover.control import protocol
from file_mover.control.client import ControlClient
from file_mover.control.dispatcher import CommandDispatcher
from file_mover.control.server import ControlSocketServer


def _health(_arguments: Mapping[str, Any]) -> dict[str, Any]:
    return {"service_state": "running"}


@pytest.mark.requirement("L2-CTL-001")
def test_full_request_response_over_socketpair() -> None:
    server = ControlSocketServer("unused", CommandDispatcher({"health": _health}))
    server_side, client_side = socket.socketpair()
    worker = threading.Thread(target=server.serve_connection, args=(server_side,))
    worker.start()
    try:
        client = ControlClient("unused", request_id_factory=lambda: "fixed-id")
        response = client.exchange_over(client_side, "health")
        assert response["success"] is True
        assert response["result"] == {"service_state": "running"}
        assert response["request_id"] == "fixed-id"
    finally:
        worker.join(timeout=5)
        server_side.close()
        client_side.close()


@pytest.mark.requirement("L2-CTL-004")
def test_server_answers_malformed_request_without_crashing() -> None:
    server = ControlSocketServer("unused", CommandDispatcher({}))
    server_side, client_side = socket.socketpair()
    worker = threading.Thread(target=server.serve_connection, args=(server_side,))
    worker.start()
    try:
        client_side.sendall(struct.pack("!I", 5) + b"nojso")  # 5-byte body, invalid JSON
        response = protocol.receive_message(client_side)
        assert response["success"] is False
        assert response["error"]["code"] == "PROTOCOL_ERROR"
    finally:
        worker.join(timeout=5)
        server_side.close()
        client_side.close()


@pytest.mark.requirement("L3-CTL-003")
def test_client_rejects_mismatched_response_id() -> None:
    # A server that always replies with the wrong request_id.
    server_side, client_side = socket.socketpair()

    def _bad_server() -> None:
        protocol.receive_message(server_side)
        protocol.send_message(server_side, {"request_id": "wrong", "success": True, "result": {}})

    worker = threading.Thread(target=_bad_server)
    worker.start()
    try:
        client = ControlClient("unused", request_id_factory=lambda: "expected")
        with pytest.raises(Exception, match="does not match"):
            client.exchange_over(client_side, "health")
    finally:
        worker.join(timeout=5)
        server_side.close()
        client_side.close()
