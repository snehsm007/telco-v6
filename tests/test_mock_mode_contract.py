"""PRD §17 / §21: every tool has a working mock_mode branch and a well-formed error envelope."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from lib import services

TOOLS = list(services.ALL_TOOLS)


def _call(tool: str, state: dict) -> dict:
    fn = getattr(services, f"{tool}_impl")
    params = inspect.signature(fn).parameters
    args = {
        name: ""
        for name, p in params.items()
        if p.default is inspect.Parameter.empty and p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
    }
    return fn(**args, state=state)


@pytest.mark.parametrize("tool", TOOLS)
def test_every_tool_marks_mock_mode_replies(tool: str) -> None:
    reply = _call(tool, {"mock_mode": "True"})
    assert reply["mock_mode"] is True
    assert reply["data"]["mock_mode"] is True
    if reply["status"] == "error":
        assert reply["error"] and reply["message"] == reply["error_message"]


@pytest.mark.parametrize("tool", TOOLS)
def test_no_mock_marker_outside_mock_mode(tool: str) -> None:
    reply = _call(tool, {})
    assert "mock_mode" not in reply
    if reply["status"] == "error":
        assert reply["message"]


def test_mock_mode_never_mocks_login() -> None:
    """PRD §5: auth state is never mocked, even with mock_mode on."""
    from lib.billing import get_billing_summary_impl

    state = {"mock_mode": "True"}
    services.lookup_account_impl("514-555-0199", state=state)
    gate = get_billing_summary_impl(state=state)
    assert gate["error"] == "NOT_LOGGED_IN" and gate["mock_mode"] is True


def test_graded_app_defaults_to_mock_mode() -> None:
    app = json.loads(Path("cxas_app/app.json").read_text(encoding="utf-8"))
    decl = {v["name"]: v for v in app["variableDeclarations"]}
    assert decl["mock_mode"]["schema"]["default"] == "True"
