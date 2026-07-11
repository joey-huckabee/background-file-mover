"""Length-prefixed JSON message framing shared by the control server and client.

Each message on the control socket is a UTF-8 JSON object preceded by a 4-byte
big-endian unsigned length prefix (:data:`~file_mover.constants.LENGTH_PREFIX_BYTES`).
The transport is any connected stream socket, so the same functions serve the AF_UNIX
control socket in production and a :func:`socket.socketpair` in tests.

``receive_message`` rejects an over-large frame *before* allocating its body
(L2-CTL-003) and ``receive_exactly`` loops on ``recv`` until the full frame arrives or
the peer closes the connection (L3-CTL-001).
"""

from __future__ import annotations

import json
import socket
import struct
from typing import Any

from file_mover.constants import DEFAULT_MAXIMUM_MESSAGE_BYTES, LENGTH_PREFIX_BYTES
from file_mover.exceptions import ControlProtocolError

_LENGTH_STRUCT = struct.Struct("!I")  # 4-byte big-endian unsigned integer
_RECV_CHUNK = 65536

# Guard against a mismatch between the wire format and the advertised prefix width.
if _LENGTH_STRUCT.size != LENGTH_PREFIX_BYTES:  # pragma: no cover - configuration invariant
    raise RuntimeError("length prefix width does not match the framing struct")


def encode_message(message: dict[str, Any]) -> bytes:
    """Serialise a message object to a length-prefixed JSON frame.

    Args:
        message: The JSON-serialisable message object.

    Returns:
        The framed bytes: a 4-byte big-endian length prefix followed by the UTF-8 body.

    Raises:
        ControlProtocolError: If the message cannot be serialised to JSON.
    """
    try:
        body = json.dumps(message).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ControlProtocolError(f"cannot encode control message: {error}") from error
    return _LENGTH_STRUCT.pack(len(body)) + body


def decode_message(body: bytes) -> dict[str, Any]:
    """Parse a message body into a JSON object.

    Args:
        body: The raw UTF-8 JSON body (without the length prefix).

    Returns:
        The decoded message object.

    Raises:
        ControlProtocolError: If the body is not valid UTF-8 JSON or is not an object.
    """
    try:
        parsed: Any = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ControlProtocolError(f"malformed control message body: {error}") from error
    if not isinstance(parsed, dict):
        raise ControlProtocolError("control message must be a JSON object")
    return parsed


def send_message(sock: socket.socket, message: dict[str, Any]) -> None:
    """Send one framed message over ``sock``.

    Args:
        sock: A connected stream socket.
        message: The JSON-serialisable message object.
    """
    sock.sendall(encode_message(message))


def receive_exactly(sock: socket.socket, count: int) -> bytes:
    """Read exactly ``count`` bytes from ``sock``, looping over ``recv``.

    Args:
        sock: A connected stream socket.
        count: The number of bytes to read.

    Returns:
        Exactly ``count`` bytes.

    Raises:
        ControlProtocolError: If the peer closes the connection before ``count`` bytes
            have been read.
    """
    chunks: list[bytes] = []
    remaining = count
    while remaining > 0:
        chunk = sock.recv(min(remaining, _RECV_CHUNK))
        if not chunk:
            raise ControlProtocolError("connection closed while reading a control message")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def receive_message(
    sock: socket.socket, maximum_bytes: int = DEFAULT_MAXIMUM_MESSAGE_BYTES
) -> dict[str, Any]:
    """Receive one framed message from ``sock``.

    The declared frame length is checked against ``maximum_bytes`` before the body is
    read, so an oversized frame is rejected without allocating it (L2-CTL-003).

    Args:
        sock: A connected stream socket.
        maximum_bytes: The largest accepted body size.

    Returns:
        The decoded message object.

    Raises:
        ControlProtocolError: If the frame is empty, oversized, truncated, or malformed.
    """
    header = receive_exactly(sock, LENGTH_PREFIX_BYTES)
    (length,) = _LENGTH_STRUCT.unpack(header)
    if length == 0:
        raise ControlProtocolError("received an empty control message")
    if length > maximum_bytes:
        raise ControlProtocolError(
            f"control message length {length} exceeds the maximum of {maximum_bytes} bytes"
        )
    body = receive_exactly(sock, length)
    return decode_message(body)
