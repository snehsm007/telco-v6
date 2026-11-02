from types import SimpleNamespace

import cxas_app.tools.update_contact_profile.python_function.python_code as tool


def test_update_contact_profile_reads_and_writes_session_state(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "phone_last4": "0186", "identification_status": "Pass", "auth_status": "pass", "logged_in": True})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.update_contact_profile("mobile_number", "613 555 0147")
    assert reply["status"] == "ok"
    assert reply["data"]["new_value_masked"].endswith("0147")
    assert "6135550147" not in str(reply)
    assert session.state["contact_updates"].startswith("mobile_number:")


def test_update_contact_profile_without_a_session() -> None:
    assert tool.update_contact_profile("email", "a@b.example")["error"] == "NOT_LOGGED_IN"


def test_update_contact_profile_mock_error(monkeypatch) -> None:
    session = SimpleNamespace(state={"mock_error": "SYSTEM_DOWN"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    assert tool.update_contact_profile("email", "a@b.example")["error"] == "SYSTEM_UNAVAILABLE"
