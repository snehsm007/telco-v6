from types import SimpleNamespace

import cxas_app.tools.execute_suspend_restore.python_function.python_code as tool


def test_execute_suspend_restore_reads_and_writes_session_state(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "phone_last4": "0186", "identification_status": "Pass", "auth_status": "pass", "logged_in": True})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.execute_suspend_restore("suspend", "lost_stolen")
    assert reply["status"] == "ok"
    assert session.state["service_status"] == "suspended_lost_stolen"
    assert tool.execute_suspend_restore("restore")["data"]["new_state"] == "active"
    assert session.state["service_status"] == "active"


def test_execute_suspend_restore_without_a_session() -> None:
    assert tool.execute_suspend_restore("suspend", "travel")["error"] == "NOT_LOGGED_IN"


def test_execute_suspend_restore_mock_error(monkeypatch) -> None:
    session = SimpleNamespace(state={"mock_error": "SYSTEM_DOWN"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    assert tool.execute_suspend_restore("suspend", "travel")["error"] == "SYSTEM_UNAVAILABLE"
