from types import SimpleNamespace

import cxas_app.tools.browse_plans.python_function.python_code as tool


def test_browse_plans_reads_session_state(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "region": "Region-B", "language": ""})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.browse_plans(lob="internet", need="faster speed")
    assert reply["status"] == "ok"
    assert 1 <= len(reply["data"]["plans"]) <= 3
    assert reply["data"]["current_plan"]["name"]
    assert session.state["lob"] == "internet"


def test_browse_plans_without_a_session_needs_no_login() -> None:
    reply = tool.browse_plans(lob="mobility", budget="60")
    assert reply["status"] == "ok"
    assert all(p["price"] <= 60 for p in reply["data"]["plans"])
    assert reply["data"]["coverage_checked"] is False


def test_browse_plans_unknown_lob(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", SimpleNamespace(state={}), raising=False)
    assert tool.browse_plans(lob="spaceship")["error"] == "INVALID_INPUT"


def test_browse_plans_mock_error(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", SimpleNamespace(state={"mock_error": "SYSTEM_DOWN"}), raising=False)
    assert tool.browse_plans(lob="tv")["error"] == "SYSTEM_UNAVAILABLE"
