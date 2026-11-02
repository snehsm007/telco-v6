from types import SimpleNamespace

import cxas_app.tools.send_sms_notification.python_function.python_code as tool


def test_send_sms_notification_texts_the_number_on_file(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "phone_last4": "0186"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.send_sms_notification(purpose="troubleshooting_guide")
    assert reply["status"] == "ok"
    assert reply["data"] == {
        "purpose": "troubleshooting_guide",
        "sms_sent": True,
        "destination_last4": "0186",
        "sms_purpose": "troubleshooting_guide",
    }
    assert session.state["sms_sent"] == "troubleshooting_guide"


def test_send_sms_notification_needs_an_identified_account_but_no_login(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", {}, raising=False)
    assert tool.send_sms_notification(purpose="outage_updates")["error"] == "NOT_IDENTIFIED"
    state = {"account_id": "A1001", "auth_status": "none"}
    monkeypatch.setattr(tool, "context", state, raising=False)
    assert tool.send_sms_notification(purpose="coupon")["error"] == "INVALID_INPUT"
    assert tool.send_sms_notification(purpose="slot-available callback")["status"] == "ok"
    assert tool.send_sms_notification(purpose="registration_link")["status"] == "ok"
    assert state["sms_sent"] == "slot_available_callback,registration_link"


def test_send_sms_notification_no_session_and_mock_error(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", None, raising=False)
    assert tool.send_sms_notification(purpose="nope")["error"] == "INVALID_INPUT"
    monkeypatch.setattr(tool, "context", SimpleNamespace(state={"mock_error": "x"}), raising=False)
    assert tool.send_sms_notification(purpose="outage_updates")["error"] == "SYSTEM_UNAVAILABLE"
