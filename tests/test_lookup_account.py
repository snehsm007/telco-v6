from types import SimpleNamespace

import cxas_app.tools.lookup_account.python_function.python_code as tool


def test_lookup_account_reads_and_writes_session_state(monkeypatch) -> None:
    session = SimpleNamespace(state={"auth_status": "none", "auth_failure_count": 0.0})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.lookup_account("202 555 0186")
    assert reply["status"] == "ok"
    assert session.state["account_id"] == "A1001"
    assert session.state["caller_provided_phone_last4"] == "0186"


def test_lookup_account_dict_context_and_fixtures(monkeypatch) -> None:
    state = {"fx_business_account": "true"}
    monkeypatch.setattr(tool, "context", state, raising=False)
    reply = tool.lookup_account(2025550186.0, language="fr-CA")
    assert reply["data"]["business_flag"] is True
    assert reply["active_language"] == "fr-CA"
    assert state["business_flag"] is True


def test_lookup_account_without_a_session(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", None, raising=False)
    default = tool.lookup_account("")
    assert default["status"] == "ok" and default["data"]["caller_id_source"] == "default_line"
    assert tool.lookup_account("123 456 7890")["error"] == "NOT_FOUND"
    assert tool.lookup_account("900 555 0199")["error"] == "PERMISSION_DENIED"


def test_lookup_account_mock_error(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "mock_error": "SYSTEM_DOWN"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.lookup_account("202 555 0186")
    assert reply["status"] == "error"
    assert reply["error"] == "SYSTEM_UNAVAILABLE"


def test_lookup_account_uses_the_session_caller_id(monkeypatch) -> None:
    session = SimpleNamespace(state={"clid": "202 555 0186"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.lookup_account("")
    assert reply["status"] == "ok" and reply["data"]["used_caller_id"] is True
    assert session.state["account_id"] == "A1001"
