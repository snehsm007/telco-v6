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


def test_get_billing_summary_line_items_carry_origin_and_prevention_tip(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", _session(), raising=False)
    items = tool.get_billing_summary()["data"]["recent_bills"][0]["line_items"]
    streaming = next(i for i in items if i["charge_id"] == "CH-STR-01")
    assert "connected TV app" in streaming["origin"]
    assert "purchase PIN" in streaming["prevention_tip"]


def test_get_billing_summary_breaks_down_the_past_due_amount(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", _session(), raising=False)
    breakdown = tool.get_billing_summary()["data"]["past_due_breakdown"]
    assert breakdown["past_due_amount_display"] == "87.65"
    assert [i["amount_display"] for i in breakdown["items"]] == ["65.00", "22.65"]
    assert breakdown["late_fees_display"] == "0.00"
