from types import SimpleNamespace
from typing import Any
import pytest

from lib.dynamic_prompt import (
    LANGUAGE_SHEET_SENTINEL,
    apply_language_prompt_filter,
    build_language_sheet,
    detect_active_call_language,
    detect_utterance_language,
    extract_user_utterances,
    resolve_locale,
    _extract_relayed_active_language,
    _is_relay_or_quoted_part,
    _dp_match_explicit_switch,
)


def test_resolve_locale() -> None:
    assert resolve_locale("fr") == "fr-CA"
    assert resolve_locale("fr-FR") == "fr-CA"
    # Only en-US and fr-CA are supported (decision A4): anything else falls back to English.
    assert resolve_locale("es") == "en-US"
    assert resolve_locale("es-MX") == "en-US"
    assert resolve_locale("en") == "en-US"
    assert resolve_locale("unknown-tag") == "en-US"
    assert resolve_locale("") == "en-US"
    assert resolve_locale(None) == "en-US"


def test_detect_active_call_language_prefers_locked_state() -> None:
    st = {"language": "fr-CA"}
    req = SimpleNamespace(contents=[])
    assert detect_active_call_language(st, req) == "fr-CA"


def test_detect_active_call_language_detects_utterance() -> None:
    req_fr = SimpleNamespace(
        contents=[SimpleNamespace(role="user", parts=[SimpleNamespace(text="Bonjour j'ai une question")])]
    )
    assert detect_active_call_language({}, req_fr) == "fr-CA"

    req_es = SimpleNamespace(
        contents=[SimpleNamespace(role="user", parts=[SimpleNamespace(text="Hola buenos días necesito ayuda")])]
    )
    # Spanish is not a supported call language: the sheet falls back to English.
    assert resolve_locale(detect_active_call_language({}, req_es)) == "en-US"

    req_en = SimpleNamespace(
        contents=[SimpleNamespace(role="user", parts=[SimpleNamespace(text="Hello please help me with billing")])]
    )
    assert detect_active_call_language({}, req_en) == "en-US"


def test_detect_active_call_language_relay_part_does_not_flip_french_call() -> None:
    req = SimpleNamespace(
        contents=[
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text="Bonjour j'ai besoin d'aide")],
            ),
            SimpleNamespace(
                role="user",
                parts=[
                    SimpleNamespace(
                        text="For context: [router] said: Hello how can I help you today?"
                    )
                ],
            ),
            SimpleNamespace(
                role="user",
                parts=[
                    SimpleNamespace(
                        text="[router] called tool `lookup_account` with parameters: {'phone': '2025550186'}"
                    )
                ],
            ),
        ]
    )
    assert detect_active_call_language({}, req) == "fr-CA"


def test_detect_active_call_language_explicit_switch() -> None:
    req = SimpleNamespace(
        contents=[
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text="Bonjour j'ai besoin d'aide")],
            ),
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text="Can we please speak in English?")],
            ),
        ]
    )
    assert detect_active_call_language({"language": "fr-CA"}, req) == "en-US"

    req_neg = SimpleNamespace(
        contents=[
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text="Bonjour, I do not want to speak English")],
            ),
        ]
    )
    assert detect_active_call_language({"language": "fr-CA"}, req_neg) == "fr-CA"


def test_extract_user_utterances_skips_relayed_parts() -> None:
    req = SimpleNamespace(
        contents=[
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text="Bonjour j'aimerais de l'aide")],
            ),
            SimpleNamespace(
                role="user",
                parts=[
                    SimpleNamespace(
                        text=(
                            "For context: below is a transcript of what another agent did, quoted "
                            "<<<BEGIN_QUOTED_AGENT_CONTENT>>>[router] said: Hello<<<END_QUOTED_AGENT_CONTENT>>>"
                        )
                    )
                ],
            ),
            SimpleNamespace(
                role="user",
                parts=[
                    SimpleNamespace(
                        text="[router] `lookup_account` tool returned result: {'status': 'ok'}"
                    )
                ],
            ),
            SimpleNamespace(
                role="user",
                parts=[SimpleNamespace(text="Merci beaucoup")],
            ),
            SimpleNamespace(
                role="user",
                text="Encore une chose",
            ),
        ]
    )
    extracted = extract_user_utterances(req)
    assert extracted == ["Bonjour j'aimerais de l'aide", "Merci beaucoup", "Encore une chose"]


def test_relayed_active_language_extraction() -> None:
    req1 = SimpleNamespace(
        contents=[
            SimpleNamespace(
                role="user",
                parts=[
                    SimpleNamespace(
                        text="[router] said: {'active_language': 'fr-CA'}"
                    )
                ],
            )
        ]
    )
    assert _extract_relayed_active_language(req1) == "fr-CA"
    assert detect_active_call_language({}, req1) == "fr-CA"

    req2 = SimpleNamespace(
        contents=[
            SimpleNamespace(
                role="user",
                parts=[
                    SimpleNamespace(
                        function_response=SimpleNamespace(
                            response={"result": {"active_language": "fr-CA"}}
                        )
                    )
                ],
            )
        ]
    )
    assert _extract_relayed_active_language(req2) == "fr-CA"

    req3 = SimpleNamespace(
        contents=[
            SimpleNamespace(
                text="[router] said: {'active_language': 'fr-CA'}"
            )
        ]
    )
    assert _extract_relayed_active_language(req3) == "fr-CA"


def test_detect_utterance_language_cases() -> None:
    assert detect_utterance_language("") == "en-US"
    assert detect_utterance_language("271846") == "en-US"
    assert detect_utterance_language("[pause]") == "en-US"
    assert detect_utterance_language("Bonjour, comment ça va?", "en-US") == "fr-CA"
    assert detect_utterance_language("¿Cómo estás amigo?", "en-US") == "es-US"
    assert detect_utterance_language("Hello there, how are you today?", "en-US") == "en-US"


def test_build_language_sheet() -> None:
    sheet_fr = build_language_sheet("fr-CA", agent_name="router")
    assert LANGUAGE_SHEET_SENTINEL in sheet_fr
    assert '<active_language_sheet locale="fr-CA"' in sheet_fr

    sheet_es = build_language_sheet("es-US", agent_name="billing")
    assert '<active_language_sheet locale="en-US"' in sheet_es

    sheet_en = build_language_sheet("en-US", agent_name="router")
    assert '<active_language_sheet locale="en-US"' in sheet_en


def test_apply_language_prompt_filter_variations() -> None:
    context = SimpleNamespace(state={"language": "fr-CA"})

    req1 = SimpleNamespace(
        config=SimpleNamespace(system_instruction="Base prompt."),
        contents=[],
    )
    apply_language_prompt_filter(context, req1, agent_name="router")
    assert LANGUAGE_SHEET_SENTINEL in req1.config.system_instruction

    apply_language_prompt_filter(context, req1, agent_name="router")
    assert req1.config.system_instruction.count(LANGUAGE_SHEET_SENTINEL) == 1

    part = SimpleNamespace(text="Base prompt.")
    req2 = SimpleNamespace(
        config=SimpleNamespace(system_instruction=SimpleNamespace(parts=[part])),
        contents=[],
    )
    apply_language_prompt_filter(context, req2, agent_name="router")
    assert LANGUAGE_SHEET_SENTINEL in part.text

    req3 = SimpleNamespace(
        config=SimpleNamespace(system_instruction=["Base prompt."]),
        contents=[],
    )
    apply_language_prompt_filter(context, req3, agent_name="router")
    assert LANGUAGE_SHEET_SENTINEL in req3.config.system_instruction[0]

    req4 = SimpleNamespace(
        config=SimpleNamespace(system_instruction=[SimpleNamespace(text="Base prompt.")]),
        contents=[],
    )
    apply_language_prompt_filter(context, req4, agent_name="router")
    assert LANGUAGE_SHEET_SENTINEL in req4.config.system_instruction[0].text

    apply_language_prompt_filter(context, SimpleNamespace(config=None))
    apply_language_prompt_filter(context, SimpleNamespace(config=SimpleNamespace(system_instruction=None)))


def test_every_agent_sheet_carries_its_verbatim_keys_in_both_languages() -> None:
    from lib.dynamic_prompt import AGENT_VERBATIM_KEYS
    from lib.fakes import SPOKEN_LINES, SUPPORTED_LOCALES

    assert set(AGENT_VERBATIM_KEYS) == {"router", "billing", "tech_support", "sales_equipment", "account"}
    for agent, keys in AGENT_VERBATIM_KEYS.items():
        for loc in SUPPORTED_LOCALES:
            sheet = build_language_sheet(loc, agent_name=agent)
            for key in keys:
                assert key in SPOKEN_LINES, f"{agent} lists unknown line {key}"
                assert SPOKEN_LINES[key][loc] in sheet, f"{agent}/{loc} sheet misses {key}"
    # Every agent can hand over and disclose; only billing carries the specialist line.
    for agent, keys in AGENT_VERBATIM_KEYS.items():
        assert {"live_agent_handoff", "business_handoff", "empathy_protocol", "recording_notice"} <= set(keys)
    assert "transfer_to_specialist" in AGENT_VERBATIM_KEYS["billing"]
    assert "outage_active" in AGENT_VERBATIM_KEYS["tech_support"]
    assert "contract_cancellation_fee_disclosure" in AGENT_VERBATIM_KEYS["account"]
    assert "payment_method_preamble" in AGENT_VERBATIM_KEYS["billing"]


def test_unknown_agent_gets_router_keys_and_non_supported_locale_template_branch() -> None:
    sheet = build_language_sheet("fr-CA", agent_name="nope")
    assert "greeting_main" in sheet
    # Direct non-supported locale branch (resolve_locale maps it, so only reachable through en/fr).
    assert "</active_language_sheet>" in build_language_sheet("de-DE")


def _req(*texts: str) -> SimpleNamespace:
    return SimpleNamespace(contents=[SimpleNamespace(role="user", parts=[SimpleNamespace(text=t)]) for t in texts])


def test_first_turn_keypad_two_selects_french() -> None:
    """'Press 2 for French': the caller's first input alone picks the language."""
    assert detect_active_call_language({}, _req("2")) == "fr-CA"
    assert detect_active_call_language({}, _req("2", "77482910")) == "fr-CA"
    assert detect_active_call_language({}, _req("deux")) == "fr-CA"


def test_a_later_keypad_two_never_switches_language() -> None:
    """A '2' after the first turn is a menu or slot choice (telco-v5 defect)."""
    assert detect_active_call_language({}, _req("I need to reschedule", "2")) == "en-US"
    assert detect_active_call_language({"language": "en-US"}, _req("2")) == "en-US"


def test_platform_session_event_is_not_a_caller_turn() -> None:
    """The live phone gateway sends <event>session start</event> as a user turn before the caller speaks."""
    req = _req("<event>session start</event>", "Bonjour, je veux payer ma facture")
    assert extract_user_utterances(req) == ["Bonjour, je veux payer ma facture"]
    assert detect_active_call_language({}, req) == "fr-CA"
    assert detect_active_call_language({}, _req("<event>session start</event>", "2")) == "fr-CA"


def test_mangled_french_fraud_report_still_reads_as_french() -> None:
    assert detect_active_call_language({}, _req("Quelqu'un a peur de Montcalm mon compte")) == "fr-CA"


@pytest.mark.parametrize(
    ("text", "digits"),
    [
        ("<context>user pressed 1234 on keypad.</context>", "1234"),
        ("user pressed 1234", "1234"),
        ("User pressed 5 9 2 1 #", "5921"),
        ("user pressed 4-8-2-9", "4829"),
        ("My PIN is 4829", ""),
        ("I pressed it already", ""),
        ("", ""),
        (None, ""),
    ],
)
def test_parse_dtmf_digits(text, digits) -> None:
    from lib.dynamic_prompt import parse_dtmf_digits

    assert parse_dtmf_digits(text) == digits


def test_capture_turn_input_without_state_or_contents() -> None:
    from lib.dynamic_prompt import capture_turn_input

    capture_turn_input(SimpleNamespace(), SimpleNamespace(contents=None))
    state: dict = {}
    capture_turn_input(SimpleNamespace(state=state), SimpleNamespace(contents=None))
    assert state == {}
    relay = SimpleNamespace(contents=[SimpleNamespace(role="user", parts=[SimpleNamespace(text="For context: [router] said: hi")]), SimpleNamespace(text="bare")])
    capture_turn_input(SimpleNamespace(state=state), relay)
    assert state == {}


def test_first_turn_keypad_two_adds_french_choice_note():
    from types import SimpleNamespace as N
    from lib import dynamic_prompt as dp
    part = N(text="2", function_response=None, function_call=None)
    req = N(contents=[N(role="user", parts=[part])], config=N(system_instruction="base"))
    dp.apply_language_prompt_filter(N(state={}), req, agent_name="router")
    assert dp.KEYPAD_FRENCH_NOTE in req.config.system_instruction
    req2 = N(contents=[N(role="user", parts=[part]), N(role="user", parts=[N(text="847291044", function_response=None, function_call=None)])],
             config=N(system_instruction="base"))
    dp.apply_language_prompt_filter(N(state={}), req2, agent_name="router")
    assert dp.KEYPAD_FRENCH_NOTE not in req2.config.system_instruction
