from types import SimpleNamespace

import cxas_app.tools.manage_appointment.python_function.python_code as tool

LOGGED_IN = {"account_id": "A1001", "phone_last4": "0186", "auth_status": "pass", "logged_in": True}


def test_manage_appointment_reschedule_writes_session_state(monkeypatch) -> None:
    session = SimpleNamespace(state={**LOGGED_IN, "fx_technician_status": "delayed"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.manage_appointment("reschedule", slot_id="SLOT-2")
    assert reply["data"]["rescheduled"] is True
    assert session.state["appt_state"] == "rescheduled"
    assert session.state["appt_slot_id"] == "SLOT-2"


def test_manage_appointment_rejects_unknown_slot(monkeypatch) -> None:
    session = SimpleNamespace(state=dict(LOGGED_IN))
    monkeypatch.setattr(tool, "context", session, raising=False)
    assert tool.manage_appointment("reschedule", slot_id="SLOT-9")["error"] == "INVALID_INPUT"
    assert "appt_state" not in session.state


def test_manage_appointment_same_day_cancel_needs_second_call(monkeypatch) -> None:
    session = SimpleNamespace(state={**LOGGED_IN, "fx_technician_status": "scheduled"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    assert tool.manage_appointment("cancel", confirmed=True)["error"] == "CONFIRMATION_REQUIRED"
    assert tool.manage_appointment("cancel", confirmed=True)["data"]["cancelled"] is True


def test_manage_appointment_without_a_session() -> None:
    assert tool.manage_appointment("cancel")["error"] == "NOT_LOGGED_IN"


def test_manage_appointment_mock_error(monkeypatch) -> None:
    session = SimpleNamespace(state={**LOGGED_IN, "mock_error": "SYSTEM_DOWN"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    assert tool.manage_appointment("cancel")["error"] == "SYSTEM_UNAVAILABLE"
