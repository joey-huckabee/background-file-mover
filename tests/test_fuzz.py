"""No-panic fuzz harness (L1-ROB-001).

Feeds deterministic pseudo-random input to every external interaction surface — the
control protocol decoder, the command dispatcher, the configuration loader, and the CLI
argument vector — and asserts that only *documented* exceptions ever occur. Any other
escaping exception is a "panic" and fails the test.

The PRNG is seeded (``FILE_MOVER_FUZZ_SEED``) so a failure is reproducible, and the
iteration count is configurable (``FILE_MOVER_FUZZ_ITERATIONS``) so CI runs a fast fixed
sweep while the scheduled ``fuzz`` workflow runs a much deeper burn-in over the same
first iterations.
"""

from __future__ import annotations

import os
import random
import socket
import string
import struct
from typing import Any

import pytest

from file_mover.cli import main
from file_mover.configuration import ConfigurationLoader
from file_mover.control import protocol
from file_mover.control.dispatcher import CommandDispatcher
from file_mover.exceptions import ConfigurationError, ControlProtocolError

_ITERATIONS = int(os.environ.get("FILE_MOVER_FUZZ_ITERATIONS", "256"))
_SEED = int(os.environ.get("FILE_MOVER_FUZZ_SEED", "20260712"))
_ALPHABET = string.ascii_letters + string.digits + string.punctuation + " \t\n"


def _rng() -> random.Random:
    return random.Random(_SEED)


def _random_bytes(rng: random.Random, max_length: int = 96) -> bytes:
    return bytes(rng.randint(0, 255) for _ in range(rng.randint(0, max_length)))


def _random_text(rng: random.Random, max_length: int = 160) -> str:
    return "".join(rng.choice(_ALPHABET) for _ in range(rng.randint(0, max_length)))


def _random_json_object(rng: random.Random) -> dict[str, Any]:
    def _value() -> Any:
        return rng.choice(
            [
                rng.randint(-5, 5),
                _random_text(rng, 8),
                None,
                [rng.randint(0, 3)],
                {"nested": rng.randint(0, 3)},
                True,
            ]
        )

    keys = ["protocol_version", "request_id", "command", "arguments", _random_text(rng, 6)]
    return {rng.choice(keys): _value() for _ in range(rng.randint(0, 5))}


@pytest.mark.requirement("L1-ROB-001")
def test_decode_message_never_panics() -> None:
    rng = _rng()
    for _ in range(_ITERATIONS):
        try:
            result = protocol.decode_message(_random_bytes(rng))
        except ControlProtocolError:
            continue
        assert isinstance(result, dict)


@pytest.mark.requirement("L1-ROB-001")
def test_receive_message_never_panics() -> None:
    rng = _rng()
    for _ in range(_ITERATIONS):
        sender, receiver = socket.socketpair()
        try:
            # Sometimes prepend a real length prefix so the body path is exercised too.
            body = _random_bytes(rng, 48)
            framed = (
                struct.pack("!I", len(body)) + body if rng.random() < 0.5 else _random_bytes(rng)
            )
            sender.sendall(framed)
            sender.close()
            try:
                message = protocol.receive_message(receiver, maximum_bytes=4096)
            except ControlProtocolError:
                continue
            assert isinstance(message, dict)
        finally:
            receiver.close()


@pytest.mark.requirement("L1-ROB-001")
def test_dispatcher_never_panics() -> None:
    dispatcher = CommandDispatcher({"health": lambda _a: {"ok": True}})
    rng = _rng()
    for _ in range(_ITERATIONS):
        response = dispatcher.dispatch(_random_json_object(rng))  # must never raise
        assert isinstance(response, dict)
        assert "success" in response


@pytest.mark.requirement("L1-ROB-001")
def test_configuration_loader_never_panics() -> None:
    loader = ConfigurationLoader()
    rng = _rng()
    for _ in range(_ITERATIONS):
        try:
            loader.load_text(_random_text(rng))
        except ConfigurationError:
            continue


@pytest.mark.requirement("L1-ROB-001")
def test_cli_main_never_panics(tmp_path: Any) -> None:
    # A config path that does not exist, so commands that reach it fail fast and no real
    # service is contacted.
    missing_config = str(tmp_path / "no-such-config.ini")
    vocabulary = [
        "submit",
        "status",
        "list",
        "stats",
        "health",
        "doctor",
        "recover",
        "config",
        "validate",
        "service",
        "run",
        "retry",
        "throttle",
        "50MB",
        "0",
        "-1",
        "--config",
        missing_config,
        "--output",
        "json",
        "human",
        "--scenario-id",
        "s",
        "--source",
        "/x",
        "--destination",
        "/y",
        "-v",
        "-vv",
        "--version",
        "job-1",
        "--",
        "garbage",
        "",
    ]
    rng = _rng()
    for _ in range(_ITERATIONS):
        argv = [rng.choice(vocabulary) for _ in range(rng.randint(0, 5))]
        try:
            code = main(argv)
        except SystemExit:
            continue  # argparse rejects bad arguments this way
        assert isinstance(code, int)
