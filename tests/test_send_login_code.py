from types import SimpleNamespace

import cxas_app.tools.send_login_code.python_function.python_code as tool


def test_send_login_code_uses_the_account_in_session_state(monkeypatch) -> None:
    session = SimpleNamespace(
        state={"account_id": "A1001", "phone_last4": "0186", "auth_status": "none", "auth_failure_count": 0.0}
    )
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.send_login_code()
    assert reply["status"] == "ok"
    assert reply["data"]["destination_last4"] == "0186"
    assert session.state["auth_status"] == "code_sent"


def test_send_login_code_email_step_up(monkeypatch) -> None:
    state = {"account_id": "A1001", "auth_status": "pass", "logged_in": True}
    monkeypatch.setattr(tool, "context", state, raising=False)
    reply = tool.send_login_code(channel="email")
    assert reply["data"]["purpose"] == "step_up" and "email_masked" in reply["data"]
    assert state["code_purpose"] == "step_up"


def test_send_login_code_locked_and_no_session(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", SimpleNamespace(state={"auth_failure_count": 3.0}), raising=False)
    assert tool.send_login_code()["error"] == "TOO_MANY_ATTEMPTS"
    monkeypatch.setattr(tool, "context", None, raising=False)
    assert tool.send_login_code()["status"] == "ok"


def test_send_login_code_mock_error(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "mock_error": "SYSTEM_DOWN"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.send_login_code()
    assert reply["status"] == "error"
    assert reply["error"] == "SYSTEM_UNAVAILABLE"
