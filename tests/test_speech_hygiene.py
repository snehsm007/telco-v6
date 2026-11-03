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
