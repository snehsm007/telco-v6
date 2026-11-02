from types import SimpleNamespace

import pytest

import cxas_app.tools.send_sms_notification.python_function.python_code as tool


@pytest.mark.parametrize("purpose", ["outage_updates", "troubleshooting_guide", "slot_available_callback", "registration_link"])
def test_send_sms_notification_texts_number_on_file(monkeypatch, purpose: str) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "phone_last4": "0186"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.send_sms_notification(purpose)
    assert reply["status"] == "ok"
    assert reply["data"]["purpose"] == purpose
    assert reply["data"]["destination_last4"] == "0186"
    assert purpose in session.state["sms_sent"]


def test_send_sms_notification_needs_no_login_but_an_account(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    assert tool.send_sms_notification("outage_updates")["error"] == "NOT_IDENTIFIED"


def test_send_sms_notification_normalizes_and_rejects_purpose(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "phone_last4": "0186"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    assert tool.send_sms_notification("Troubleshooting Guide")["data"]["purpose"] == "troubleshooting_guide"
    assert tool.send_sms_notification("birthday card")["error"] == "INVALID_INPUT"


def test_send_sms_notification_without_a_session() -> None:
    assert tool.send_sms_notification("outage_updates")["error"] == "NOT_IDENTIFIED"


def test_send_sms_notification_mock_error(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "mock_error": "SYSTEM_DOWN"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    assert tool.send_sms_notification("outage_updates")["error"] == "SYSTEM_UNAVAILABLE"
