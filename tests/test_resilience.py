"""Resilience over every tool (prd §6, §16, §17): odd inputs never raise, faults hand over."""

import inspect
import json

import pytest

import lib.services as services
from lib.replies import ERROR_CODES

ODD_VALUES = [
    None, "", "   ", 0, -1, 3.0, 1234567.0, float("nan"), True,
    "x" * 5000, "é🙂漢字", "null", "<script>", "'; DROP TABLE", {"a": 1}, ["1"],
]


def _params(fn):
    return [
        p.name
        for p in inspect.signature(fn).parameters.values()
        if p.name not in ("state", "session_state") and p.kind == p.POSITIONAL_OR_KEYWORD
    ]


def _assert_reply_shape(reply) -> None:
    assert isinstance(reply, dict)
    assert reply["status"] in ("ok", "error")
    assert isinstance(reply["data"], dict)
    assert isinstance(reply["tracking_id"], str)
    if reply["status"] == "error":
        assert reply["error"] in ERROR_CODES
        assert isinstance(reply.get("agent_action", ""), str)
    json.dumps(reply, ensure_ascii=False)


@pytest.mark.parametrize("tool", services.ALL_TOOLS)
@pytest.mark.parametrize("logged_in", [False, True])
def test_tools_never_raise_on_odd_arguments(tool, logged_in) -> None:
    fn = getattr(services, tool)
    for odd in ODD_VALUES:
        state = {"account_id": "A1001", "auth_status": "pass", "logged_in": True} if logged_in else {}
        _assert_reply_shape(fn(state=state, **{name: odd for name in _params(fn)}))


@pytest.mark.parametrize("tool", services.ALL_TOOLS)
def test_mock_error_makes_every_tool_hand_over_as_system_unavailable(tool) -> None:
    fn = getattr(services, tool)
    args = {name: "" for name in _params(fn)}
    if tool == "handover_to_person":
        args["reason"] = "user_requested_agent"
    reply = fn(state={"mock_error": "SYSTEM_DOWN"}, **args)
    _assert_reply_shape(reply)
    assert reply["error"] == "SYSTEM_UNAVAILABLE"
    assert "system_unavailable" in reply["agent_action"]


def test_system_unavailable_handover_still_runs_under_mock_error() -> None:
    state = {"mock_error": "SYSTEM_DOWN"}
    reply = services.handover_to_person("system_unavailable", "", state=state)
    assert reply["status"] == "ok" and state["handover_complete"] is True
