from types import SimpleNamespace

import cxas_app.tools.get_appointment_and_ticket_status.python_function.python_code as tool

LOGGED_IN = {"account_id": "A1001", "phone_last4": "0186", "auth_status": "pass", "logged_in": True}


def test_get_appointment_and_ticket_status_reads_session_state(monkeypatch) -> None:
    session = SimpleNamespace(state={**LOGGED_IN, "fx_technician_status": "delayed", "language": "fr-CA"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.get_appointment_and_ticket_status()
    assert reply["status"] == "ok"
    assert reply["active_language"] == "fr-CA"
    assert reply["data"]["appointments"][0]["status"] == "delayed"
    assert len(reply["data"]["available_slots"]) == 3
    assert session.state["ticket_state"]


def test_get_appointment_and_ticket_status_without_a_session() -> None:
    assert tool.get_appointment_and_ticket_status()["error"] == "NOT_LOGGED_IN"


def test_get_appointment_and_ticket_status_mock_error(monkeypatch) -> None:
    session = SimpleNamespace(state={**LOGGED_IN, "mock_error": "SYSTEM_DOWN"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    assert tool.get_appointment_and_ticket_status()["error"] == "SYSTEM_UNAVAILABLE"
