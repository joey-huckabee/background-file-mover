"""Tests for the length-prefixed JSON control protocol (cross-platform)."""

from __future__ import annotations

import socket
import struct

import pytest

from file_mover.control import protocol
from file_mover.exceptions import ControlProtocolError


@pytest.mark.requirement("L2-CTL-002")
def test_encode_decode_roundtrip() -> None:
    framed = protocol.encode_message({"command": "health", "n": 1})
    assert protocol.decode_message(framed[4:]) == {"command": "health", "n": 1}


@pytest.mark.requirement("L3-PY-006")
def test_length_prefix_is_four_byte_big_endian() -> None:
    framed = protocol.encode_message({})  # body is "{}" -> 2 bytes
    assert framed[:4] == struct.pack("!I", 2)
    assert len(framed) == 6


@pytest.mark.requirement("L2-CTL-002")
def test_send_and_receive_over_socketpair() -> None:
    sender, receiver = socket.socketpair()
    try:
        protocol.send_message(sender, {"hello": "world"})
        assert protocol.receive_message(receiver) == {"hello": "world"}
    finally:
        sender.close()
        receiver.close()


@pytest.mark.requirement("L2-CTL-003")
def test_oversized_message_rejected_before_reading_body() -> None:
    sender, receiver = socket.socketpair()
    try:
        sender.sendall(struct.pack("!I", 10_000_000))  # header only; no body follows
        with pytest.raises(ControlProtocolError, match="exceeds"):
            protocol.receive_message(receiver, maximum_bytes=1024)
    finally:
        sender.close()
        receiver.close()


@pytest.mark.requirement("L2-CTL-004")
def test_empty_message_rejected() -> None:
    sender, receiver = socket.socketpair()
    try:
        sender.sendall(struct.pack("!I", 0))
        with pytest.raises(ControlProtocolError, match="empty"):
            protocol.receive_message(receiver)
    finally:
        sender.close()
        receiver.close()


@pytest.mark.requirement("L3-CTL-001")
def test_truncated_message_raises_on_close() -> None:
    sender, receiver = socket.socketpair()
    try:
        sender.sendall(struct.pack("!I", 100) + b"short")  # claims 100 bytes, sends 5
        sender.close()  # EOF before the full body arrives
        with pytest.raises(ControlProtocolError, match="closed"):
            protocol.receive_message(receiver)
    finally:
        receiver.close()


@pytest.mark.requirement("L2-CTL-004")
def test_malformed_json_body_rejected() -> None:
    with pytest.raises(ControlProtocolError, match="malformed"):
        protocol.decode_message(b"not json{{{")


@pytest.mark.requirement("L2-CTL-004")
def test_non_object_json_rejected() -> None:
    with pytest.raises(ControlProtocolError, match="object"):
        protocol.decode_message(b"[1, 2, 3]")


@pytest.mark.requirement("L2-CTL-002")
def test_unserialisable_message_raises() -> None:
    with pytest.raises(ControlProtocolError):
        protocol.encode_message({"bad": object()})
