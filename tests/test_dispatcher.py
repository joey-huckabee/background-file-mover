"""Tests for the control-command dispatcher (cross-platform)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from file_mover.constants import PROTOCOL_VERSION
from file_mover.control.dispatcher import CommandDispatcher


def _echo(arguments: Mapping[str, Any]) -> dict[str, Any]:
    return {"echo": dict(arguments)}


def _request(
    command: str = "ping",
    *,
    request_id: str | None = "r1",
    version: int | None = PROTOCOL_VERSION,
    arguments: Any = None,
) -> dict[str, Any]:
    request: dict[str, Any] = {"protocol_version": version, "request_id": request_id}
    request["command"] = command
    if arguments is not None:
        request["arguments"] = arguments
    return request


@pytest.mark.requirement("L3-CTL-002")
def test_known_command_is_dispatched() -> None:
    dispatcher = CommandDispatcher({"ping": _echo})
    response = dispatcher.dispatch(_request("ping", arguments={"x": 1}))
    assert response["success"] is True
    assert response["result"] == {"echo": {"x": 1}}


@pytest.mark.requirement("L3-CTL-003")
def test_response_echoes_request_id() -> None:
    dispatcher = CommandDispatcher({"ping": _echo})
    assert dispatcher.dispatch(_request(request_id="abc"))["request_id"] == "abc"


@pytest.mark.requirement("L3-CTL-002")
def test_commands_are_reported_sorted() -> None:
    dispatcher = CommandDispatcher({"b": _echo, "a": _echo})
    assert dispatcher.commands == ("a", "b")


@pytest.mark.requirement("L2-CTL-005")
def test_unknown_command_rejected() -> None:
    dispatcher = CommandDispatcher({"ping": _echo})
    response = dispatcher.dispatch(_request("nope"))
    assert response["success"] is False
    assert response["error"]["code"] == "UNKNOWN_COMMAND"


@pytest.mark.requirement("L2-CTL-002")
def test_missing_request_id_is_bad_request() -> None:
    dispatcher = CommandDispatcher({"ping": _echo})
    response = dispatcher.dispatch(_request(request_id=None))
    assert response["error"]["code"] == "BAD_REQUEST"


@pytest.mark.requirement("L2-CTL-002")
def test_unsupported_protocol_version_rejected() -> None:
    dispatcher = CommandDispatcher({"ping": _echo})
    response = dispatcher.dispatch(_request(version=999))
    assert response["error"]["code"] == "UNSUPPORTED_PROTOCOL"


@pytest.mark.requirement("L2-CTL-005")
def test_missing_command_is_bad_request() -> None:
    dispatcher = CommandDispatcher({"ping": _echo})
    response = dispatcher.dispatch({"protocol_version": PROTOCOL_VERSION, "request_id": "r"})
    assert response["error"]["code"] == "BAD_REQUEST"


@pytest.mark.requirement("L2-CTL-002")
def test_non_object_arguments_rejected() -> None:
    dispatcher = CommandDispatcher({"ping": _echo})
    response = dispatcher.dispatch(_request(arguments="not-an-object"))
    assert response["error"]["code"] == "BAD_REQUEST"


@pytest.mark.requirement("L2-CTL-004")
def test_handler_exception_is_isolated() -> None:
    def boom(_arguments: Mapping[str, Any]) -> dict[str, Any]:
        raise RuntimeError("kaboom")

    dispatcher = CommandDispatcher({"boom": boom})
    response = dispatcher.dispatch(_request("boom"))
    assert response["success"] is False
    assert response["error"]["code"] == "INTERNAL_ERROR"
    assert "kaboom" in response["error"]["message"]
