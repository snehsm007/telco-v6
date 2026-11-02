"""Callbacks on every agent: speech hygiene (after model) and the language sheet (before model)."""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from lib.dynamic_prompt import AGENT_VERBATIM_KEYS
from lib.fakes import SPOKEN_LINES

AGENTS = ("router", "billing", "tech_support", "sales_equipment", "account")
HYGIENE = {
    name: importlib.import_module(f"cxas_app.agents.{name}.after_model_callbacks.speech_hygiene.python_code")
    for name in AGENTS
}
LANG_FILTER = {
    name: importlib.import_module(f"cxas_app.agents.{name}.before_model_callbacks.language_prompt_filter.python_code")
    for name in AGENTS
}


@pytest.mark.parametrize("name", AGENTS)
def test_hygiene_prefers_caller_last4_and_strips_markdown(name: str) -> None:
    state = {"phone_last4": "0186", "caller_provided_phone_last4": "0199", "handover_complete": False}
    resp = SimpleNamespace(content=SimpleNamespace(parts=[SimpleNamespace(text="**Your number ending in 0143 is ready.**")]))
    assert HYGIENE[name].after_model_callback(SimpleNamespace(state=state), resp) is resp
    assert resp.content.parts[0].text == "Your number ending in 0199 is ready."


@pytest.mark.parametrize("name", AGENTS)
def test_hygiene_fills_empty_handover_turn_with_handoff_message(name: str) -> None:
    msg = SPOKEN_LINES["live_agent_handoff"]["fr-CA"]
    state = {"handover_complete": True, "handoff_message": msg}
    empty = SimpleNamespace(content=SimpleNamespace(parts=[SimpleNamespace(text="")]))
    assert HYGIENE[name].after_model_callback(SimpleNamespace(state=state), empty) is empty
    assert empty.content.parts[0].text == msg

    tool_only = SimpleNamespace(
        content=SimpleNamespace(parts=[SimpleNamespace(text=None, function_call=SimpleNamespace(name="end_session"))])
    )
    assert HYGIENE[name].after_model_callback(SimpleNamespace(state=state), tool_only) is tool_only
    assert tool_only.content.parts[0].text == msg
    assert tool_only.content.parts[1].function_call.name == "end_session"


@pytest.mark.parametrize("name", AGENTS)
def test_hygiene_leaves_clean_text_and_non_dict_state_alone(name: str) -> None:
    resp = SimpleNamespace(content=SimpleNamespace(parts=[SimpleNamespace(text="All set.")]))
    assert HYGIENE[name].after_model_callback(SimpleNamespace(state={}), resp) is None
    assert HYGIENE[name].after_model_callback(SimpleNamespace(state=None), resp) is None
    assert HYGIENE[name].after_model_callback(SimpleNamespace(state={}), SimpleNamespace(content=None)) is None


@pytest.mark.parametrize("name", AGENTS)
def test_language_filter_uses_its_own_agent_keys(name: str) -> None:
    req = SimpleNamespace(config=SimpleNamespace(system_instruction="Base."), contents=[])
    state = {"language": "fr-CA"}
    assert LANG_FILTER[name].before_model_callback(SimpleNamespace(state=state), req) is None
    sheet = req.config.system_instruction
    assert '<active_language_sheet locale="fr-CA"' in sheet
    for key in AGENT_VERBATIM_KEYS[name]:
        assert SPOKEN_LINES[key]["fr-CA"] in sheet, f"{name} sheet misses {key}"
    assert state == {"language": "fr-CA"}  # read-only callback


def test_turn_one_french_utterance_gives_french_sheet_without_state() -> None:
    req = SimpleNamespace(
        config=SimpleNamespace(system_instruction="Base."),
        contents=[SimpleNamespace(role="user", parts=[SimpleNamespace(text="Bonjour, je veux parler à un représentant")])],
    )
    LANG_FILTER["router"].before_model_callback(SimpleNamespace(state={}), req)
    assert '<active_language_sheet locale="fr-CA"' in req.config.system_instruction
