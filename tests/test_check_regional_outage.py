from types import SimpleNamespace

import cxas_app.tools.check_regional_outage.python_function.python_code as tool


def test_check_regional_outage_reads_and_writes_session_state(monkeypatch) -> None:
    session = SimpleNamespace(state={"fx_outage_status": "active"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.check_regional_outage("m5v 2t6", "internet")
    assert reply["status"] == "ok"
    assert reply["data"]["outage_active"] is True
    assert session.state["outage_active"] is True
    assert session.state["region"] == "Region-B"


def test_check_regional_outage_accepts_numeric_zip(monkeypatch) -> None:
    session = SimpleNamespace(state={})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.check_regional_outage(30301.0)
    assert reply["data"]["region"] == "Region-C"


def test_check_regional_outage_without_a_session() -> None:
    assert tool.check_regional_outage("")["error"] == "INVALID_INPUT"


def test_check_regional_outage_mock_error(monkeypatch) -> None:
    session = SimpleNamespace(state={"mock_error": "SYSTEM_DOWN"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    assert tool.check_regional_outage("M5V 2T6")["error"] == "SYSTEM_UNAVAILABLE"
