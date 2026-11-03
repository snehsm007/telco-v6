from types import SimpleNamespace
from typing import Any
import pytest

import importlib

AGENT_CALLBACKS = [
    (name, importlib.import_module(f"cxas_app.agents.{name}.before_model_callbacks.language_prompt_filter.python_code"))
    for name in ("router", "billing", "tech_support", "sales_equipment", "account")
]


@pytest.mark.parametrize("agent_name, callback_mod", AGENT_CALLBACKS)
def test_language_prompt_filter_injects_sentinel_and_zero_state_writes(
    agent_name: str, callback_mod: Any
) -> None:
    initial_state = {
        "account_id": "A1001",
        "phone_last4": "0186",
        "language": "fr-CA",
        "auth_status": "pass",
    }
    state_copy = dict(initial_state)
    context = SimpleNamespace(state=state_copy)

    initial_instruction = f"Base prompt for {agent_name}."
    req = SimpleNamespace(
        config=SimpleNamespace(system_instruction=initial_instruction),
        contents=[
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text="Bonjour j'ai une question")],
            )
        ],
    )

    result = callback_mod.before_model_callback(context, req)

    assert result is None
    assert "<!-- ACTIVE_LANGUAGE_SHEET -->" in req.config.system_instruction
    assert '<active_language_sheet locale="fr-CA"' in req.config.system_instruction
    assert state_copy == initial_state


@pytest.mark.parametrize("agent_name, callback_mod", AGENT_CALLBACKS)
def test_language_prompt_filter_english_default_and_parts_structure(
    agent_name: str, callback_mod: Any
) -> None:
    state = {"language": "en-US"}
    part = SimpleNamespace(text="System instructions here.")
    req = SimpleNamespace(
        config=SimpleNamespace(system_instruction=SimpleNamespace(parts=[part])),
        contents=[],
    )

    result = callback_mod.before_model_callback(SimpleNamespace(state=state), req)
    assert result is None
    assert "<!-- ACTIVE_LANGUAGE_SHEET -->" in part.text
    assert 'locale="en-US"' in part.text


@pytest.mark.parametrize("agent_name, callback_mod", AGENT_CALLBACKS)
def test_language_prompt_filter_mappingproxy_and_adk_state_with_digits(
    agent_name: str, callback_mod: Any
) -> None:
    from types import MappingProxyType

    class MockAdkState:
        def __init__(self, data: dict[str, Any]) -> None:
            self._data = dict(data)

        def get(self, key: str, default: Any = None) -> Any:
            return self._data.get(key, default)

        def __getitem__(self, key: str) -> Any:
            return self._data[key]

    raw_state = {"language": "fr-CA"}
    for st in (MappingProxyType(raw_state), MockAdkState(raw_state)):
        req = SimpleNamespace(
            config=SimpleNamespace(system_instruction="Base prompt."),
            contents=[
                SimpleNamespace(
                    role="user",
                    parts=[SimpleNamespace(text="5903")],
                )
            ],
        )
        res = callback_mod.before_model_callback(SimpleNamespace(state=st), req)
        assert res is None
        assert '<active_language_sheet locale="fr-CA"' in req.config.system_instruction


def _req(*turns: tuple[str, str]) -> SimpleNamespace:
    return SimpleNamespace(
        config=SimpleNamespace(system_instruction="Base."),
        contents=[SimpleNamespace(role=role, parts=[SimpleNamespace(text=text)]) for role, text in turns],
    )


@pytest.mark.parametrize("agent_name, callback_mod", AGENT_CALLBACKS)
def test_language_prompt_filter_captures_dtmf_and_resets_it(agent_name: str, callback_mod: Any) -> None:
    """prd.md §6.1: keypad digits land in dtmf_digits on their turn and clear on the next turn."""
    state: dict = {}
    keyed = _req(("user", "<event>session start</event>"), ("model", "Welcome."), ("user", "<context>user pressed 1234 on keypad.</context>"))
    callback_mod.before_model_callback(SimpleNamespace(state=state), keyed)
    assert state["dtmf_digits"] == "1234" and state["call_channel"] == "voice"
    spoken = _req(("user", "<event>session start</event>"), ("user", "<context>user pressed 1234 on keypad.</context>"), ("model", "Verified."), ("user", "What's my balance?"))
    callback_mod.before_model_callback(SimpleNamespace(state=state), spoken)
    assert state["dtmf_digits"] == "" and state["call_channel"] == "voice"


def test_dtmf_capture_prefers_the_current_user_content_and_native_parts() -> None:
    callback_mod = AGENT_CALLBACKS[0][1]
    state: dict = {}
    ctx = SimpleNamespace(state=state, user_content=SimpleNamespace(parts=[SimpleNamespace(text=None, dtmf="5 9 2 1#")]))
    callback_mod.before_model_callback(ctx, _req(("user", "My PIN?")))
    assert state == {"dtmf_digits": "5921", "call_channel": "voice"}


def test_text_chat_never_marks_a_phone_call() -> None:
    callback_mod = AGENT_CALLBACKS[0][1]
    state: dict = {"dtmf_digits": "4829"}
    callback_mod.before_model_callback(SimpleNamespace(state=state), _req(("user", "My PIN is 4829")))
    assert state == {"dtmf_digits": ""}
