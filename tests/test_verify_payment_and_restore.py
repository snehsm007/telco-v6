from types import SimpleNamespace

import cxas_app.tools.verify_payment_and_restore.python_function.python_code as tool


def _session(**extra):
    state = {"account_id": "A1001", "phone_last4": "0186", "auth_status": "pass", "logged_in": True}
    state.update(extra)
    return SimpleNamespace(state=state)


def test_verify_payment_and_restore_needs_login(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", SimpleNamespace(state={"account_id": "A1001"}), raising=False)
    assert tool.verify_payment_and_restore()["error"] == "NOT_LOGGED_IN"


def test_verify_payment_and_restore_without_a_session() -> None:
    assert tool.verify_payment_and_restore()["error"] == "NOT_LOGGED_IN"


def test_verify_payment_and_restore_mock_error(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", _session(mock_error="SYSTEM_DOWN"), raising=False)
    assert tool.verify_payment_and_restore()["error"] == "SYSTEM_UNAVAILABLE"


def test_verify_payment_and_restore_accepts_a_dict_context(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", _session(fx_service_status="active").state, raising=False)
    assert tool.verify_payment_and_restore()["error"] == "NOT_SUSPENDED"


def test_verify_payment_and_restore_with_posted_payment(monkeypatch) -> None:
    session = _session(fx_service_status="suspended_nonpayment", fx_recent_payment="posted_yesterday")
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.verify_payment_and_restore()
    assert reply["data"]["service_restored"] is True
    assert session.state["service_status"] == "active"


def test_verify_payment_and_restore_without_payment(monkeypatch) -> None:
    session = _session(fx_service_status="suspended_nonpayment", fx_recent_payment="none")
    monkeypatch.setattr(tool, "context", session, raising=False)
    assert tool.verify_payment_and_restore()["error"] == "NO_PAYMENT_FOUND"
