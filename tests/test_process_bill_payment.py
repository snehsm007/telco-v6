from types import SimpleNamespace

import cxas_app.tools.process_bill_payment.python_function.python_code as tool


def _session(**extra):
    state = {"account_id": "A1001", "phone_last4": "0186", "auth_status": "pass", "logged_in": True}
    state.update(extra)
    return SimpleNamespace(state=state)


def test_process_bill_payment_needs_login(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", SimpleNamespace(state={"account_id": "A1001"}), raising=False)
    assert tool.process_bill_payment()["error"] == "NOT_LOGGED_IN"


def test_process_bill_payment_without_a_session() -> None:
    assert tool.process_bill_payment()["error"] == "NOT_LOGGED_IN"


def test_process_bill_payment_mock_error(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", _session(mock_error="SYSTEM_DOWN"), raising=False)
    assert tool.process_bill_payment()["error"] == "SYSTEM_UNAVAILABLE"


def test_process_bill_payment_accepts_a_dict_context(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", _session().state, raising=False)
    assert tool.process_bill_payment(amount="10")["status"] == "ok"


def test_process_bill_payment_writes_session_state(monkeypatch) -> None:
    session = _session(fx_service_status="suspended_nonpayment")
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.process_bill_payment(amount="past due", payment_method="card_on_file")
    assert reply["data"]["service_restored"] is True
    assert "restart the modem" in reply["data"]["reconnect_note"]
    assert session.state["service_status"] == "active"
    assert session.state["last_payment_method"] == "card_on_file"


def test_process_bill_payment_numeric_amount_and_keypad(monkeypatch) -> None:
    session = _session()
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.process_bill_payment(amount=25.5, payment_method="new_card", dtmf_digits=5105105105105100)
    assert reply["data"]["amount_paid_display"] == "25.50"
    assert reply["data"]["card_last4"] == "5100"


def test_process_bill_payment_decline(monkeypatch) -> None:
    session = _session(fx_card_on_file_status="declined")
    monkeypatch.setattr(tool, "context", session, raising=False)
    assert tool.process_bill_payment()["error"] == "CARD_DECLINED"
    assert session.state["card_last4"] == ""
