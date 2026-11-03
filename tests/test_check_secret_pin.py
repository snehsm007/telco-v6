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


def test_check_secret_pin_accepts_spoken_pins(monkeypatch) -> None:
    for said in ("one two three four", "twelve thirty four", "one thousand two hundred thirty-four", "quatre quatre cinq deux", "my PIN is 5 9 0 3"):
        state = {"account_id": "A1001", "auth_status": "none"}
        monkeypatch.setattr(tool, "context", state, raising=False)
        assert tool.check_secret_pin(said)["status"] == "ok", said
    state = {"account_id": "A1001", "fx_pin_on_file": "4452"}
    monkeypatch.setattr(tool, "context", state, raising=False)
    assert tool.check_secret_pin("quatre quatre cinq deux")["status"] == "ok"


def test_check_secret_pin_spoken_pin_keeps_strict_length(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", {"account_id": "A1001"}, raising=False)
    assert tool.check_secret_pin("one two three")["error"] == "INVALID_INPUT"
    assert tool.check_secret_pin("one two three four five")["error"] == "INVALID_INPUT"


def test_phone_call_accepts_the_keypad_pin(monkeypatch) -> None:
    state = {"account_id": "A1001", "call_channel": "voice", "dtmf_digits": "4829", "fx_pin_on_file": "4829"}
    monkeypatch.setattr(tool, "context", state, raising=False)
    assert tool.check_secret_pin("4829")["status"] == "ok"
    state = {"account_id": "A1001", "call_channel": "voice", "dtmf_digits": "4829", "fx_pin_on_file": "4829"}
    monkeypatch.setattr(tool, "context", state, raising=False)
    assert tool.check_secret_pin("")["status"] == "ok"


def test_phone_call_refuses_a_spoken_pin_and_texts_a_code(monkeypatch) -> None:
    """prd.md PIN flow: voice-spelled PINs are refused; a code is texted in the same turn, no strike."""
    state = {"account_id": "A1001", "call_channel": "voice", "dtmf_digits": ""}
    monkeypatch.setattr(tool, "context", state, raising=False)
    reply = tool.check_secret_pin("one two three four")
    assert reply["error"] == "PIN_KEYPAD_REQUIRED" and reply["data"]["sent"] is True
    assert "keypad" in reply["data"]["spoken_message"] and "6" in reply["data"]["spoken_message"]
    assert state["login_code_sent"] is True and state["auth_status"] == "code_sent"
    assert not state.get("auth_failure_count") and not state.get("global_err_count")
    again = tool.check_secret_pin("")
    assert again["error"] == "PIN_KEYPAD_REQUIRED" and again["data"]["sent"] is False
    fr = {"account_id": "A1001", "call_channel": "voice", "language": "fr-CA"}
    monkeypatch.setattr(tool, "context", fr, raising=False)
    assert "clavier" in tool.check_secret_pin("1234", language="fr-CA")["data"]["spoken_message"]


def test_phone_call_spoken_code_still_checks_the_code(monkeypatch) -> None:
    state = {"account_id": "A1001", "call_channel": "voice", "fx_otp_on_file": "271846"}
    monkeypatch.setattr(tool, "context", state, raising=False)
    assert tool.check_secret_pin("5903")["error"] == "PIN_KEYPAD_REQUIRED"
    assert tool.check_secret_pin("two seven one eight four six")["status"] == "ok"


def test_phone_call_refusal_when_locked(monkeypatch) -> None:
    state = {"account_id": "A1001", "call_channel": "voice", "auth_failure_count": 3}
    monkeypatch.setattr(tool, "context", state, raising=False)
    assert tool.check_secret_pin("5903")["error"] == "TOO_MANY_ATTEMPTS"


def test_text_chat_accepts_a_typed_pin(monkeypatch) -> None:
    state = {"account_id": "A1001", "fx_pin_on_file": "4829"}
    monkeypatch.setattr(tool, "context", state, raising=False)
    assert tool.check_secret_pin("My PIN is 4829")["status"] == "ok"
