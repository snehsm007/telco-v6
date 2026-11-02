from types import SimpleNamespace

import cxas_app.tools.manage_mfa.python_function.python_code as tool


def test_manage_mfa_reads_and_writes_session_state(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "phone_last4": "0186", "identification_status": "Pass", "auth_status": "pass", "logged_in": True})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.manage_mfa("enable")
    assert reply["status"] == "ok"
    assert reply["data"]["mfa_enabled"] is True
    assert session.state["mfa_state"] == "enabled"
    assert tool.manage_mfa("disable")["error"] == "STEP_UP_REQUIRED"


def test_manage_mfa_without_a_session() -> None:
    assert tool.manage_mfa("enable")["error"] == "NOT_LOGGED_IN"


def test_manage_mfa_mock_error(monkeypatch) -> None:
    session = SimpleNamespace(state={"mock_error": "SYSTEM_DOWN"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    assert tool.manage_mfa("enable")["error"] == "SYSTEM_UNAVAILABLE"
