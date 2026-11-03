from types import SimpleNamespace

import cxas_app.tools.check_login_code.python_function.python_code as tool


def test_check_login_code_logs_the_caller_in(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "auth_status": "code_sent", "auth_failure_count": 0.0})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.check_login_code("271846")
    assert reply["status"] == "ok"
    assert reply["data"]["verified"] is True
    assert session.state["auth_status"] == "pass"


def test_check_login_code_exact_code_on_file_and_lockout(monkeypatch) -> None:
    state = {"account_id": "A1001", "auth_status": "code_sent", "fx_otp_on_file": "804627"}
    monkeypatch.setattr(tool, "context", state, raising=False)
    assert tool.check_login_code(314159)["error"] == "WRONG_CODE"
    assert tool.check_login_code("271846")["error"] == "WRONG_CODE"
    assert tool.check_login_code("111111")["error"] == "TOO_MANY_ATTEMPTS"
    assert state["auth_status"] == "locked"


def test_check_login_code_step_up(monkeypatch) -> None:
    state = {"account_id": "A1001", "auth_status": "pass", "logged_in": True, "code_purpose": "step_up"}
    monkeypatch.setattr(tool, "context", state, raising=False)
    reply = tool.check_login_code(482913.0)
    assert reply["data"]["step_up_verified"] is True and state["step_up_verified"] is True


def test_check_login_code_no_session_and_mock_error(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", None, raising=False)
    assert tool.check_login_code("12")["error"] == "INVALID_INPUT"
    monkeypatch.setattr(tool, "context", SimpleNamespace(state={"mock_error": "x"}), raising=False)
    assert tool.check_login_code("271846")["error"] == "SYSTEM_UNAVAILABLE"


def test_check_login_code_accepts_spoken_codes(monkeypatch) -> None:
    for said in ("two seven one eight four six", "twenty-seven eighteen forty-six", "deux sept un huit quatre six", "the code is 27 18 46"):
        state = {"account_id": "A1001", "auth_status": "code_sent", "fx_otp_on_file": "271846"}
        monkeypatch.setattr(tool, "context", state, raising=False)
        assert tool.check_login_code(said)["status"] == "ok", said


def test_check_login_code_spoken_code_keeps_strict_length(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", {"account_id": "A1001", "auth_status": "code_sent"}, raising=False)
    assert tool.check_login_code("two seven one eight four")["error"] == "INVALID_INPUT"
