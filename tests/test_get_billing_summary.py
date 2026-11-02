from types import SimpleNamespace

import cxas_app.tools.get_billing_summary.python_function.python_code as tool


def _session(**extra):
    state = {"account_id": "A1001", "phone_last4": "0186", "auth_status": "pass", "logged_in": True}
    state.update(extra)
    return SimpleNamespace(state=state)


def test_get_billing_summary_needs_login(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", SimpleNamespace(state={"account_id": "A1001"}), raising=False)
    assert tool.get_billing_summary()["error"] == "NOT_LOGGED_IN"


def test_get_billing_summary_without_a_session() -> None:
    assert tool.get_billing_summary()["error"] == "NOT_LOGGED_IN"


def test_get_billing_summary_mock_error(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", _session(mock_error="SYSTEM_DOWN"), raising=False)
    assert tool.get_billing_summary()["error"] == "SYSTEM_UNAVAILABLE"


def test_get_billing_summary_accepts_a_dict_context(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", _session().state, raising=False)
    assert tool.get_billing_summary()["status"] == "ok"


def test_get_billing_summary_reads_session_state(monkeypatch) -> None:
    session = _session(balance_due="12.00", past_due_amount="0.00")
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.get_billing_summary(language="fr-CA")
    assert reply["data"]["balance_due_display"] == "12.00"
    assert reply["active_language"] == "fr-CA"
