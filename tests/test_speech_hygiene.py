from types import SimpleNamespace

import pytest

import importlib

AGENTS = ("router", "billing", "tech_support", "sales_equipment", "account")
CALLBACKS = [
    importlib.import_module(f"cxas_app.agents.{name}.after_model_callbacks.speech_hygiene.python_code")
    for name in AGENTS
]


def make_response(*texts: str) -> SimpleNamespace:
    parts = [SimpleNamespace(text=text) for text in texts]
    parts.append(SimpleNamespace(text=None, function_call=SimpleNamespace(name="end_session")))
    return SimpleNamespace(content=SimpleNamespace(parts=parts))


@pytest.mark.parametrize("callback", CALLBACKS)
def test_cleans_text_parts_and_keeps_tool_calls(callback) -> None:
    response = make_response("**Your number is 2025550186.**", "Anything else?")
    assert callback.after_model_callback(SimpleNamespace(state={}), response) is response
    assert response.content.parts[0].text == "Your number is 0186."
    assert response.content.parts[1].text == "Anything else?"
    assert response.content.parts[2].function_call.name == "end_session"


@pytest.mark.parametrize("callback", CALLBACKS)
def test_injects_handoff_message_when_handover_turn_has_no_spoken_text(callback) -> None:
    msg = "Je vous transfère maintenant à un membre de notre équipe. Merci de votre patience."
    state = {"handover_complete": True, "handoff_message": msg}
    tool_only = SimpleNamespace(
        content=SimpleNamespace(
            parts=[SimpleNamespace(text=None, function_call=SimpleNamespace(name="end_session"))]
        )
    )
    assert callback.after_model_callback(SimpleNamespace(state=state), tool_only) is tool_only
    assert tool_only.content.parts[0].text == msg


@pytest.mark.parametrize("callback", CALLBACKS)
def test_keeps_the_spoken_transfer_line_after_a_handover(callback) -> None:
    msg = "I'm transferring you to a member of our team now. Thank you for your patience."
    state = {"handover_complete": True, "handoff_message": msg}
    step_line = "I'm transferring you to a billing specialist now."
    response = make_response(step_line)
    assert callback.after_model_callback(SimpleNamespace(state=state), response) is None
    assert response.content.parts[0].text == step_line


@pytest.mark.parametrize("callback", CALLBACKS)
def test_returns_none_when_nothing_changes(callback) -> None:
    assert callback.after_model_callback(SimpleNamespace(state={}), make_response("All set.")) is None
    assert callback.after_model_callback(SimpleNamespace(state={}), SimpleNamespace(content=None)) is None


@pytest.mark.parametrize("callback", CALLBACKS)
def test_bundled_callback_keeps_tool_endings_and_fixes_profile_phone(callback) -> None:
    state = {"phone_last4": "0186", "caller_provided_phone_last4": "0199"}
    temp = "Your temporary number ending in 2538 is active."
    assert callback.after_model_callback(SimpleNamespace(state=state), make_response(temp)) is None
    response = make_response("I sent the code to the number ending in 0186.")
    assert callback.after_model_callback(SimpleNamespace(state=state), response) is response
    assert response.content.parts[0].text == "I sent the code to the number ending in 0199."


@pytest.mark.parametrize("callback", CALLBACKS)
def test_bundled_callback_never_speaks_back_a_pin(callback) -> None:
    response = make_response("Thanks, your PIN 7316 is verified.")
    assert callback.after_model_callback(SimpleNamespace(state={}), response) is response
    assert response.content.parts[0].text == "Thanks, your PIN is verified."


def _tool_only(name: str, **args) -> SimpleNamespace:
    call = SimpleNamespace(name=name, args=args)
    return SimpleNamespace(content=SimpleNamespace(parts=[SimpleNamespace(text=None, function_call=call)]))


@pytest.mark.parametrize("callback", CALLBACKS)
@pytest.mark.parametrize(
    ("language", "args", "expected"),
    [
        ("en-US", {"reason": "resolved"}, "Thank you for calling. Have a great day."),
        ("fr-CA", {"reason": "resolved"}, "Merci de votre appel. Bonne journée."),
        ("en-US", {"reason": "malicious_input"}, "I am unable to continue this conversation."),
        ("fr-CA", {"reason": "malicious_input"}, "Je ne peux pas poursuivre cette conversation."),
        ("en-US", {"reason": "blocked_caller"}, "We're unable to help with this call on this line."),
        ("fr-CA", {"reason": "system_unavailable", "session_escalated": True}, "Je vais vous mettre en relation"),
    ],
)
def test_silent_end_session_gets_a_spoken_closing(callback, language, args, expected) -> None:
    # Dead air: the model sometimes called end_session with no words at all.
    response = _tool_only("end_session", **args)
    assert callback.after_model_callback(SimpleNamespace(state={"language": language}), response) is response
    assert response.content.parts[0].text.startswith(expected)
    assert response.content.parts[1].function_call.name == "end_session"


@pytest.mark.parametrize("callback", CALLBACKS)
def test_silent_transfer_without_end_session_stays_silent(callback) -> None:
    response = _tool_only("transfer_to_agent", agent_name="billing")
    assert callback.after_model_callback(SimpleNamespace(state={"language": "en-US"}), response) is None
    assert response.content.parts[0].text is None


@pytest.mark.parametrize("callback", CALLBACKS)
def test_handoff_message_still_wins_on_a_silent_end_session(callback) -> None:
    state = {"handover_complete": True, "handoff_message": "Please hold.", "language": "en-US"}
    response = _tool_only("end_session", reason="user_requested_agent", session_escalated=True)
    assert callback.after_model_callback(SimpleNamespace(state=state), response) is response
    assert response.content.parts[0].text == "Please hold."
