from types import SimpleNamespace

import pytest

import cxas_app.tools.send_sms_notification.python_function.python_code as tool
from lib.fakes import ACCOUNTS, SPOKEN_LINES


@pytest.mark.parametrize("purpose", ["outage_updates", "troubleshooting_guide", "slot_available_callback", "registration_link"])
def test_send_sms_notification_texts_number_on_file(monkeypatch, purpose: str) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "phone_last4": "0186"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.send_sms_notification(purpose)
    assert reply["status"] == "ok"
    assert reply["data"]["purpose"] == purpose
    assert reply["data"]["destination_last4"] == "0186"
    assert purpose in session.state["sms_sent"]


@pytest.mark.parametrize("purpose", ["slot_available_callback", "registration_link"])
def test_send_sms_notification_account_purposes_need_an_account(monkeypatch, purpose: str) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    assert tool.send_sms_notification(purpose)["error"] == "NOT_IDENTIFIED"


@pytest.mark.parametrize("lang", ["en-US", "fr-CA"])
def test_outage_updates_without_an_account_text_the_caller_id(monkeypatch, lang: str) -> None:
    # Live calls: the outage offer ("text you when it's restored?") must be kept with no account found.
    session = SimpleNamespace(state={"clid": "5145550123", "language": lang})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.send_sms_notification("outage_updates", language=lang)
    assert reply["status"] == "ok"
    assert reply["data"]["destination_last4"] == "0123"
    assert reply["data"]["destination_source"] == "clid"
    assert reply["data"]["spoken_message"] == SPOKEN_LINES["sms_outage_updates_confirmed"][lang].replace("[last4]", "0123")
    assert "account_id" not in session.state and session.state["sms_sent"] == "outage_updates"


def test_outage_updates_to_a_caller_given_mobile_number(monkeypatch) -> None:
    session = SimpleNamespace(state={"clid": "5145550123"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.send_sms_notification("outage_updates", mobile_number="(438) 555-0177")
    assert reply["data"]["destination_last4"] == "0177" and reply["data"]["destination_source"] == "caller_provided"
    assert reply["data"]["spoken_message"].endswith("ending in 0177 as soon as service is restored.")
    spoken = tool.send_sms_notification("troubleshooting_guide", mobile_number="4 3 8 5 5 5 0 1 7 7")
    assert spoken["data"]["destination_last4"] == "0177"
    assert tool.send_sms_notification("outage_updates", mobile_number=4385550177.0)["data"]["destination_last4"] == "0177"


@pytest.mark.parametrize("bad", ["555-01", "1234567890", "January 1st 1990", "1111111111"])
def test_outage_updates_reject_a_malformed_mobile_number(monkeypatch, bad: str) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.send_sms_notification("outage_updates", mobile_number=bad)
    assert reply["error"] == "INVALID_INPUT" and "sms_sent" not in session.state


def test_outage_updates_without_caller_id_use_the_calling_line(monkeypatch) -> None:
    # Text chats and evaluations have no clid: the simulated calling line, as lookup_account("") does.
    session = SimpleNamespace(state={"clid": "anonymous"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.send_sms_notification("outage_updates")
    assert reply["status"] == "ok" and reply["data"]["destination_source"] == "default_line"
    assert reply["data"]["destination_last4"] == ACCOUNTS[0]["phone"][-4:]


def test_derived_phone_is_not_spoken_when_the_caller_id_is_known(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A123456", "phone_last4": "3456", "phone_derived": True, "clid": "5145550123"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    assert tool.send_sms_notification("outage_updates")["data"]["destination_last4"] == "0123"


def test_send_sms_notification_normalizes_and_rejects_purpose(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "phone_last4": "0186"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    assert tool.send_sms_notification("Troubleshooting Guide")["data"]["purpose"] == "troubleshooting_guide"
    assert tool.send_sms_notification("birthday card")["error"] == "INVALID_INPUT"


def test_send_sms_notification_without_a_session() -> None:
    assert tool.send_sms_notification("registration_link")["error"] == "NOT_IDENTIFIED"
    assert tool.send_sms_notification("outage_updates")["status"] == "ok"


def test_send_sms_notification_mock_error(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "mock_error": "SYSTEM_DOWN"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    assert tool.send_sms_notification("outage_updates")["error"] == "SYSTEM_UNAVAILABLE"
