from types import SimpleNamespace

import cxas_app.tools.setup_autopay.python_function.python_code as tool


def _session(**extra):
    state = {"account_id": "A1001", "phone_last4": "0186", "auth_status": "pass", "logged_in": True}
    state.update(extra)
    return SimpleNamespace(state=state)


def test_setup_autopay_needs_login(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", SimpleNamespace(state={"account_id": "A1001"}), raising=False)
    assert tool.setup_autopay()["error"] == "NOT_LOGGED_IN"


def test_setup_autopay_without_a_session() -> None:
    assert tool.setup_autopay()["error"] == "NOT_LOGGED_IN"


def test_setup_autopay_mock_error(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", _session(mock_error="SYSTEM_DOWN"), raising=False)
    assert tool.setup_autopay()["error"] == "SYSTEM_UNAVAILABLE"


def test_setup_autopay_accepts_a_dict_context(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", _session().state, raising=False)
    assert tool.setup_autopay()["status"] == "ok"


def test_setup_autopay_writes_session_state(monkeypatch) -> None:
    session = _session()
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.setup_autopay(payment_method="new_card", card_number=5105105105105100)
    assert reply["data"]["card_last4"] == "5100"
    assert session.state["autopay_enrolled"] is True
    assert tool.setup_autopay()["error"] == "ALREADY_ENROLLED"
