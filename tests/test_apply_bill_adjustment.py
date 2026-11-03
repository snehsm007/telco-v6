from types import SimpleNamespace

import cxas_app.tools.apply_bill_adjustment.python_function.python_code as tool


def _session(**extra):
    state = {"account_id": "A1001", "phone_last4": "0186", "auth_status": "pass", "logged_in": True}
    state.update(extra)
    return SimpleNamespace(state=state)


def test_apply_bill_adjustment_needs_login(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", SimpleNamespace(state={"account_id": "A1001"}), raising=False)
    assert tool.apply_bill_adjustment(adjustment_type="unrecognized_charge")["error"] == "NOT_LOGGED_IN"


def test_apply_bill_adjustment_without_a_session() -> None:
    assert tool.apply_bill_adjustment(adjustment_type="unrecognized_charge")["error"] == "NOT_LOGGED_IN"


def test_apply_bill_adjustment_mock_error(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", _session(mock_error="SYSTEM_DOWN"), raising=False)
    assert tool.apply_bill_adjustment(adjustment_type="unrecognized_charge")["error"] == "SYSTEM_UNAVAILABLE"


def test_apply_bill_adjustment_accepts_a_dict_context(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", _session().state, raising=False)
    assert tool.apply_bill_adjustment(adjustment_type="outage_credit", description="internet", outage_days=3)["status"] == "ok"


def test_apply_bill_adjustment_numeric_days_and_idempotency(monkeypatch) -> None:
    session = _session()
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.apply_bill_adjustment(adjustment_type="outage_credit", description="internet down", outage_days=3.0)
    assert reply["data"]["approved"] is True
    assert "outage:internet" in session.state["applied_adjustments"]
    again = tool.apply_bill_adjustment(adjustment_type="outage_credit", description="internet down", outage_days=3)
    assert again["error"] == "ALREADY_APPLIED"


def test_apply_bill_adjustment_over_limit(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", _session(), raising=False)
    reply = tool.apply_bill_adjustment(adjustment_type="incorrect_charge", amount=150, description="modem")
    assert reply["error"] == "REFUND_THRESHOLD_EXCEEDED"
    assert reply["spoken_message"].startswith("That amount is above our $25.00 self-serve limit")
    assert reply["spoken_message"].endswith("they'll have everything we've already discussed.")
