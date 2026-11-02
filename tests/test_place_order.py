from types import SimpleNamespace

import cxas_app.tools.place_order.python_function.python_code as tool


def _logged_in() -> SimpleNamespace:
    return SimpleNamespace(
        state={"account_id": "A1001", "phone_last4": "0186", "auth_status": "pass", "logged_in": True}
    )


def test_place_order_quotes_then_orders(monkeypatch) -> None:
    session = _logged_in()
    monkeypatch.setattr(tool, "context", session, raising=False)
    quote = tool.place_order(plan_id="MOB-50", confirmed=False)
    assert quote["error"] == "CONFIRMATION_REQUIRED"
    assert quote["data"]["new_monthly_total_display"]
    order = tool.place_order(plan_id="MOB-50", confirmed=True)
    assert order["status"] == "ok"
    assert order["data"]["order_id"].startswith("ORD-")
    assert order["data"]["sms_receipt_sent"] is True
    assert session.state["sales_orders"] == "MOB-50"


def test_place_order_needs_login(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", SimpleNamespace(state={"account_id": "A1001"}), raising=False)
    assert tool.place_order(plan_id="MOB-50", confirmed=True)["error"] == "NOT_LOGGED_IN"


def test_place_order_without_a_session() -> None:
    assert tool.place_order(plan_id="MOB-50")["error"] == "NOT_LOGGED_IN"


def test_place_order_unknown_plan(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", _logged_in(), raising=False)
    assert tool.place_order(plan_id="NOPE-1")["error"] == "INVALID_INPUT"
