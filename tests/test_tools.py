"""Contract checks for every tool in ALL_TOOLS (docs/tdd.md §2-3).

Placeholder domain tools (raising NotImplementedError) are skipped; each check
starts covering a tool as soon as its impl lands.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from lib.replies import ERROR_CODES
from lib.services import ALL_TOOLS
from tests.tool_registry import LOGIN_REQUIRED, call, impl, is_implemented, tool_params

ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = ROOT / "cxas_app" / "tools"
SHARED = ("lookup_account", "send_login_code", "check_login_code", "check_secret_pin", "handover_to_person", "send_sms_notification")


def _need(name: str) -> None:
    if not is_implemented(name):
        pytest.skip(f"{name} is still a placeholder (NotImplementedError)")


def test_shared_tools_are_implemented() -> None:
    for name in SHARED:
        assert is_implemented(name), name


def test_login_required_list_names_real_tools() -> None:
    assert LOGIN_REQUIRED <= set(ALL_TOOLS)


@pytest.mark.parametrize("name", ALL_TOOLS)
def test_impl_signature(name: str) -> None:
    _need(name)
    params = inspect.signature(impl(name)).parameters
    for internal in ("state", "session_state", "language"):
        assert internal in params, f"{name}_impl lacks {internal}"
        assert params[internal].default in (None, ""), f"{name}_impl {internal} needs a default"
    assert any(p.kind is p.VAR_KEYWORD for p in params.values()), f"{name}_impl lacks **kwargs"


@pytest.mark.parametrize("name", ALL_TOOLS)
def test_mock_error_is_a_system_error(name: str) -> None:
    _need(name)
    reason = {"reason": "user_requested_agent"} if name == "handover_to_person" else {}
    reply = call(name, {"mock_error": "SYSTEM_DOWN"}, "en-US", **reason)
    assert reply["status"] == "error" and reply["error"] == "SYSTEM_UNAVAILABLE", name
    assert "system_unavailable" in reply["agent_action"]


@pytest.mark.parametrize("name", sorted(LOGIN_REQUIRED))
def test_account_tools_require_login(name: str) -> None:
    _need(name)
    for state in (
        {"account_id": "A1001", "identification_status": "Pass"},
        {"account_id": "A1001", "identification_status": "Pass", "auth_status": "code_sent"},
        {"account_id": "A1001", "identification_status": "Pass", "auth_status": "locked"},
    ):
        reply = call(name, state, "en-US")
        assert reply.get("error") == "NOT_LOGGED_IN", f"{name} ran without login: {reply}"


@pytest.mark.parametrize("name", ALL_TOOLS)
def test_wrapper_matches_impl(name: str) -> None:
    _need(name)
    path = TOOLS_DIR / name / "python_function" / "python_code.py"
    assert path.is_file(), f"missing wrapper {path}"
    assert (TOOLS_DIR / name / f"{name}.json").is_file()
    spec = json.loads((TOOLS_DIR / name / f"{name}.json").read_text(encoding="utf-8"))
    assert spec["pythonFunction"]["name"] == name
    src = path.read_text(encoding="utf-8")
    head = src.split("# --- BEGIN GENERATED SHARED BUNDLE", 1)[0]
    assert "from __future__ import annotations" not in head, f"{name} wrapper must not use postponed annotations"
    fn = next(n for n in ast.parse(head).body if isinstance(n, ast.FunctionDef) and n.name == name)
    wrapper_params = [a.arg for a in fn.args.args]
    assert "language" in wrapper_params
    assert "state" not in wrapper_params and "session_state" not in wrapper_params
    assert sorted(p for p in wrapper_params if p != "language") == sorted(tool_params(name)), name
    assert f"{name}_impl" in head


@pytest.mark.parametrize("name", ALL_TOOLS)
def test_wrapper_runs_with_platform_context(name: str, monkeypatch) -> None:
    _need(name)
    mod = importlib.import_module(f"cxas_app.tools.{name}.python_function.python_code")
    state = {"mock_error": "SYSTEM_DOWN"}
    monkeypatch.setattr(mod, "context", SimpleNamespace(state=state), raising=False)
    kwargs = {p: "" for p in tool_params(name)}
    if name == "handover_to_person":
        kwargs["reason"] = "user_requested_agent"
    reply = getattr(mod, name)(**kwargs)
    assert reply["error"] == "SYSTEM_UNAVAILABLE"
    assert state.get("last_tracking_id") == reply["tracking_id"]


@pytest.mark.parametrize("name", ALL_TOOLS)
def test_empty_arguments_never_crash_and_errors_are_documented(name: str) -> None:
    _need(name)
    for state in ({}, {"account_id": "A1001", "auth_status": "pass", "logged_in": True}):
        reply = call(name, dict(state), "en-US")
        assert reply["status"] in ("ok", "error")
        assert reply["tracking_id"]
        if reply["status"] == "error":
            assert reply["error"] in ERROR_CODES
            assert 0 < len(reply["agent_action"]) <= 120
