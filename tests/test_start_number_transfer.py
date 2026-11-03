from types import SimpleNamespace

import cxas_app.tools.start_number_transfer.python_function.python_code as tool


def _logged_in() -> SimpleNamespace:
    return SimpleNamespace(
        state={"account_id": "A1001", "phone_last4": "0186", "auth_status": "pass", "logged_in": True}
    )


def test_start_number_transfer_submits(monkeypatch) -> None:
    session = _logged_in()
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.start_number_transfer(
        number_to_transfer="416 555 0123",
        current_provider="Other Mobile",
        current_account_number="77001234",
        transfer_pin="2468",
        target_line="new_line",
    )
    assert reply["status"] == "ok"
    assert reply["data"]["transfer_id"].startswith("PT-")
    assert reply["data"]["temporary_number_last4"]
    assert "2468" not in str(reply)
    assert session.state["sales_transfers"] == reply["data"]["transfer_id"]


def test_start_number_transfer_checklist_without_a_session() -> None:
    reply = tool.start_number_transfer()
    assert reply["status"] == "ok"
    assert reply["data"]["required_port_checklist"]
    assert reply["data"]["transfer_started"] is False


def test_start_number_transfer_needs_login(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", SimpleNamespace(state={"account_id": "A1001"}), raising=False)
    assert tool.start_number_transfer(number_to_transfer="4165550123")["error"] == "NOT_LOGGED_IN"


def test_start_number_transfer_rejects_malformed_number(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", _logged_in(), raising=False)
    assert tool.start_number_transfer(number_to_transfer="12345")["error"] == "INVALID_INPUT"


def test_start_number_transfer_pending_still_gives_timeframe(monkeypatch) -> None:
    session = _logged_in()
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.start_number_transfer(number_to_transfer="416 555 0123", current_provider="Other Mobile", target_line="new_line")
    assert reply["data"]["status"] == "pending_details"
    assert reply["data"]["typical_timeframe_display"]
