from types import SimpleNamespace

import cxas_app.tools.check_secret_pin.python_function.python_code as tool


def test_check_secret_pin_logs_the_caller_in(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "auth_status": "none", "pin_failure_count": 0.0})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.check_secret_pin("5903")
    assert reply["status"] == "ok"
    assert reply["data"]["verified"] is True
    assert session.state["auth_status"] == "pass"


def test_check_secret_pin_exact_pin_on_file_and_keypad(monkeypatch) -> None:
    state = {"account_id": "A1001", "fx_pin_on_file": "4321"}
    monkeypatch.setattr(tool, "context", state, raising=False)
    wrong = tool.check_secret_pin("5903")
    assert wrong["error"] == "WRONG_PIN" and wrong["data"]["attempts_remaining"] == 2
    state["dtmf_digits"] = "4321"
    assert tool.check_secret_pin("")["status"] == "ok"


def test_check_secret_pin_weak_and_mock_error(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", None, raising=False)
    assert tool.check_secret_pin("7777")["error"] == "WRONG_PIN"
    monkeypatch.setattr(tool, "context", SimpleNamespace(state={"mock_error": "x"}), raising=False)
    assert tool.check_secret_pin("5903")["error"] == "SYSTEM_UNAVAILABLE"
