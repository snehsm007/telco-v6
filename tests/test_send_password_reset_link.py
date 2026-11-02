from types import SimpleNamespace

import cxas_app.tools.send_password_reset_link.python_function.python_code as tool


def test_send_password_reset_link_reads_and_writes_session_state(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "phone_last4": "0186", "identification_status": "Pass"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.send_password_reset_link()
    assert reply["status"] == "ok"
    assert reply["data"]["destination_last4"] == "0186"
    assert session.state["password_reset_count"] == 1
    assert "http" not in str(reply)


def test_send_password_reset_link_without_a_session() -> None:
    assert tool.send_password_reset_link()["error"] == "NOT_IDENTIFIED"


def test_send_password_reset_link_mock_error(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "identification_status": "Pass", "mock_error": "SYSTEM_DOWN"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    assert tool.send_password_reset_link()["error"] == "SYSTEM_UNAVAILABLE"
