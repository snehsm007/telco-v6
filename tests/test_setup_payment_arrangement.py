from types import SimpleNamespace

import cxas_app.tools.setup_payment_arrangement.python_function.python_code as tool


def _session(**extra):
    state = {"account_id": "A1001", "phone_last4": "0186", "auth_status": "pass", "logged_in": True}
    state.update(extra)
    return SimpleNamespace(state=state)


def test_setup_payment_arrangement_needs_login(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", SimpleNamespace(state={"account_id": "A1001"}), raising=False)
    assert tool.setup_payment_arrangement()["error"] == "NOT_LOGGED_IN"


def test_setup_payment_arrangement_without_a_session() -> None:
    assert tool.setup_payment_arrangement()["error"] == "NOT_LOGGED_IN"


def test_setup_payment_arrangement_mock_error(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", _session(mock_error="SYSTEM_DOWN"), raising=False)
    assert tool.setup_payment_arrangement()["error"] == "SYSTEM_UNAVAILABLE"


def test_setup_payment_arrangement_accepts_a_dict_context(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", _session().state, raising=False)
    assert tool.setup_payment_arrangement()["status"] == "ok"


def test_setup_payment_arrangement_restores(monkeypatch) -> None:
    session = _session(fx_service_status="suspended_nonpayment")
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.setup_payment_arrangement(first_payment_amount=100)
    assert reply["data"]["instalments"][0]["amount_display"] == "100.00"
    assert session.state["service_status"] == "active"
