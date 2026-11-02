from types import SimpleNamespace

import cxas_app.tools.cancel_or_port_out_service.python_function.python_code as tool


def test_cancel_or_port_out_service_reads_and_writes_session_state(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "phone_last4": "0186", "identification_status": "Pass", "auth_status": "pass", "logged_in": True})
    monkeypatch.setattr(tool, "context", session, raising=False)
    quote = tool.cancel_or_port_out_service("mobility", "port_out")
    assert quote["error"] == "CONFIRMATION_REQUIRED"
    assert quote["data"]["early_termination_fee_display"]
    done = tool.cancel_or_port_out_service("mobility", "port_out", "", True)
    assert done["status"] == "ok"
    assert done["data"]["transfer_authorization_sent_by_sms"] is True
    assert "pin" not in " ".join(done["data"]).lower()
    assert session.state["cancelled_services"] == "mobility:port_out"


def test_cancel_or_port_out_service_without_a_session() -> None:
    assert tool.cancel_or_port_out_service("internet")["error"] == "NOT_LOGGED_IN"


def test_cancel_or_port_out_service_mock_error(monkeypatch) -> None:
    session = SimpleNamespace(state={"mock_error": "SYSTEM_DOWN"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    assert tool.cancel_or_port_out_service("internet")["error"] == "SYSTEM_UNAVAILABLE"
