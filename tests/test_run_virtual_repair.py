from types import SimpleNamespace

import cxas_app.tools.run_virtual_repair.python_function.python_code as tool

LOGGED_IN = {"account_id": "A1001", "phone_last4": "0186", "auth_status": "pass", "logged_in": True}


def test_run_virtual_repair_reads_and_writes_session_state(monkeypatch) -> None:
    session = SimpleNamespace(state=dict(LOGGED_IN))
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.run_virtual_repair("tv", "error 771 on the screen", "satellite")
    assert reply["status"] == "ok"
    assert reply["data"]["symptom_category"] == "tv_error_code"
    assert session.state["tv_sub_type"] == "satellite"
    assert session.state["vr_session_id"] == reply["data"]["session_id"]


def test_run_virtual_repair_tv_needs_sub_type(monkeypatch) -> None:
    session = SimpleNamespace(state=dict(LOGGED_IN))
    monkeypatch.setattr(tool, "context", session, raising=False)
    assert tool.run_virtual_repair("tv", "no signal")["error"] == "TV_SUB_TYPE_REQUIRED"


def test_run_virtual_repair_without_a_session() -> None:
    assert tool.run_virtual_repair("internet", "down")["error"] == "NOT_LOGGED_IN"


def test_run_virtual_repair_mock_error(monkeypatch) -> None:
    session = SimpleNamespace(state={**LOGGED_IN, "mock_error": "SYSTEM_DOWN"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    assert tool.run_virtual_repair("internet", "down")["error"] == "SYSTEM_UNAVAILABLE"


def test_run_virtual_repair_tv_app_guide_has_cache_faq(monkeypatch) -> None:
    session = SimpleNamespace(state=dict(LOGGED_IN))
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.run_virtual_repair("tv", "TV app freezing on my streaming stick", "streaming_only")
    assert reply["data"]["app_data_note"] and reply["data"]["typical_duration_display"]
