\
"""Dynamic multilingual prompt injection via read-only before_model_callback.

Detects active conversation language (filtering out ADK relay/agent event parts)
and injects a localized language sheet containing verbatim spoken lines and rules
into the system instruction before model execution.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any

from lib.fakes import SPOKEN_LINES, resolve_locale, spoken_line

LANGUAGE_SHEET_SENTINEL = "<!-- ACTIVE_LANGUAGE_SHEET -->"

WORLD_LANGUAGE_NAMES: dict[str, str] = {
    "en-US": "English",
    "fr-CA": "French (Canada)",
    "es-US": "Spanish",
}

AGENT_VERBATIM_KEYS: dict[str, tuple[str, ...]] = {
    "router": ("greeting_main", "restricted_caller", "live_agent_handoff", "business_handoff", "empathy_protocol", "recording_notice", "ai_disclosure", "malicious_closing"),
    "billing": ("id_verification_otp", "id_verification_pin", "otp_callback_confirm", "payment_method_preamble", "refund_confirmation_pattern", "transfer_to_specialist", "live_agent_handoff", "business_handoff", "empathy_protocol", "recording_notice", "ai_disclosure", "malicious_closing"),
    "tech_support": ("id_verification_otp", "id_verification_pin", "otp_callback_confirm", "outage_active", "live_agent_handoff", "business_handoff", "empathy_protocol", "recording_notice", "ai_disclosure", "malicious_closing"),
    "sales_equipment": ("id_verification_otp", "id_verification_pin", "otp_callback_confirm", "live_agent_handoff", "business_handoff", "empathy_protocol", "recording_notice", "ai_disclosure", "malicious_closing"),
    "account": ("id_verification_otp", "id_verification_pin", "otp_callback_confirm", "contract_cancellation_fee_disclosure", "live_agent_handoff", "business_handoff", "empathy_protocol", "recording_notice", "ai_disclosure", "malicious_closing"),
}

_FRENCH_MARKERS: frozenset[str] = frozenset({
    "quelqu'un", "quelqu", "piraté", "pirate",
    "bonjour", "merci", "oui", "non", "svp", "compte", "facture", "payer",
    "service", "aide", "besoin", "agent", "parler", "code", "reçu", "francais",
    "français", "salut", "allo", "allô", "s'il", "vous", "plaît", "plait",
})

_SPANISH_MARKERS: frozenset[str] = frozenset({
    "hola", "gracias", "si", "sí", "cuenta", "factura", "pagar", "servicio",
    "ayuda", "necesito", "agente", "hablar", "codigo", "código", "espanol",
    "español", "buenas", "tardes", "días", "favor", "por",
})

_ENGLISH_MARKERS: frozenset[str] = frozenset({
    "hello", "hi", "thanks", "thank", "yes", "yeah", "account", "bill",
    "pay", "service", "help", "need", "representative", "agent", "speak",
    "code", "received", "please", "support",
})

_DP_GERMAN_MARKERS: frozenset[str] = frozenset({
    "hallo", "guten", "tag", "danke", "ja", "nein", "bitte", "hilfe",
    "rechnung", "konto", "sprechen", "deutsch",
})

_DP_PORTUGUESE_MARKERS: frozenset[str] = frozenset({
    "olá", "ola", "obrigado", "obrigada", "sim", "não", "nao", "por",
    "favor", "ajuda", "conta", "falar", "português", "portugues",
})

_DP_ITALIAN_MARKERS: frozenset[str] = frozenset({
    "ciao", "buongiorno", "grazie", "sì", "si", "per", "favore", "aiuto",
    "conto", "parlare", "italiano",
})

_DP_EXPLICIT_SWITCH_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("fr-CA", ("en français", "en francais", "parlez-vous français", "parlez vous francais", "in french", "speak french", "french please", "switch to french")),
    ("es-US", ("en español", "en espanol", "habla español", "habla espanol", "in spanish", "speak spanish", "spanish please", "switch to spanish")),
    ("en-US", ("in english", "speak english", "english please", "switch to english")),
    ("de-DE", ("auf deutsch", "sprechen sie deutsch", "in german", "speak german", "german please", "switch to german")),
    ("it-IT", ("in italiano", "parla italiano", "in italian", "speak italian", "italian please", "switch to italian")),
    ("pt-BR", ("em português", "em portugues", "fala português", "fala portugues", "in portuguese", "speak portuguese", "portuguese please", "switch to portuguese")),
)

_DP_NEGATED_SWITCH_PREFIX_RE = re.compile(
    r"(?:"
    r"\b(?:don't|do\s+not|dont|cannot|can't|cant|not|unable to|not able to)\s+"
    r"(?:want\s+to\s+|know\s+how\s+to\s+)?(?:speak\s+|talk\s+|switch\s+to\s+)?"
    r"|\b(?:pas|jamais)\s+(?:parler\s+|continuer\s+)?"
    r"|\bno\s+(?:hablo|habla|hablas|hablamos|puedo|podemos|quiero)\s+(?:hablar\s+)?"
    r")\s*$",
    re.IGNORECASE,
)

_RE_RELAY_PREFIX = re.compile(
    r"^(?:For context|\s*\[[^\]]+\]\s*(?:said:|thought:|called tool |`[^`]*` tool returned result:))",
    re.IGNORECASE,
)
_RE_QUOTED_AGENT_BLOCK = re.compile(
    r"<<<BEGIN_QUOTED_AGENT_CONTENT>>>[\s\S]*?<<<END_QUOTED_AGENT_CONTENT>>>"
)
# Platform events delivered as "user" text, e.g. the live phone gateway's
# <event>session start</event> before the caller speaks. Never a caller turn.
_RE_PLATFORM_EVENT = re.compile(r"<event\b[^>]*>[\s\S]*?</event>|<state_update\b[^>]*>[\s\S]*?</state_update>", re.IGNORECASE)
_RE_RELAY_ACTIVE_LANG = re.compile(
    r"""['"]active_language['"]\s*:\s*['"]([a-zA-Z]{2}(?:-[a-zA-Z]{2})?)['"]"""
)


def _is_relay_or_quoted_part(txt: str) -> bool:
    """Return True if txt is an ADK relay part, agent event, or quoted content block."""
    s = txt.strip()
    if not s:
        return True
    if _RE_RELAY_PREFIX.match(s):
        return True
    cleaned = _RE_PLATFORM_EVENT.sub("", _RE_QUOTED_AGENT_BLOCK.sub("", s)).strip()
    if not cleaned:
        return True
    if _RE_RELAY_PREFIX.match(cleaned):
        return True
    return False


def _extract_relayed_active_language(llm_request: Any) -> str:
    """Extract the most recent active_language from relayed tool results in contents."""
    contents = getattr(llm_request, "contents", None)
    if not contents or not isinstance(contents, (list, tuple)):
        return ""
    last_lang = ""
    for item in contents:
        parts = getattr(item, "parts", None)
        if parts and isinstance(parts, (list, tuple)):
            for part in parts:
                txt = getattr(part, "text", None)
                if txt and isinstance(txt, str):
                    matches = _RE_RELAY_ACTIVE_LANG.findall(txt)
                    if matches:
                        last_lang = matches[-1]
                fn_resp = getattr(part, "function_response", None)
                if fn_resp:
                    resp = getattr(fn_resp, "response", None)
                    if isinstance(resp, dict):
                        al = resp.get("active_language")
                        if not al and isinstance(resp.get("result"), dict):
                            al = resp["result"].get("active_language")
                        if al and isinstance(al, str):
                            last_lang = al
        elif isinstance(getattr(item, "text", None), str):
            matches = _RE_RELAY_ACTIVE_LANG.findall(item.text)
            if matches:
                last_lang = matches[-1]
    if last_lang:
        return resolve_locale(last_lang)
    return ""


def extract_user_utterances(llm_request: Any) -> list[str]:
    """Safely extract genuine user utterance strings from LLM request contents, skipping relay parts."""
    utterances: list[str] = []
    contents = getattr(llm_request, "contents", None)
    if not contents or not isinstance(contents, (list, tuple)):
        return utterances
    for item in contents:
        if getattr(item, "role", "") == "user":
            parts = getattr(item, "parts", None)
            if parts and isinstance(parts, (list, tuple)):
                for part in parts:
                    txt = getattr(part, "text", None)
                    if txt and isinstance(txt, str) and txt.strip():
                        if not _is_relay_or_quoted_part(txt):
                            utterances.append(_RE_PLATFORM_EVENT.sub("", txt).strip())
            elif isinstance(getattr(item, "text", None), str):
                t = item.text.strip()
                if t and not _is_relay_or_quoted_part(t):
                    utterances.append(_RE_PLATFORM_EVENT.sub("", t).strip())
    return utterances


def _dp_match_explicit_switch(low: str) -> str:
    """Return target locale for the last non-negated explicit switch term in low."""
    best_end = -1
    best_locale = ""
    for target_locale, terms in _DP_EXPLICIT_SWITCH_TERMS:
        for term in terms:
            for m in re.finditer(rf"(?<!\w){re.escape(term)}(?!\w)", low):
                if _DP_NEGATED_SWITCH_PREFIX_RE.search(low[: m.start()]):
                    continue
                if m.end() > best_end:
                    best_end = m.end()
                    best_locale = target_locale
    return best_locale


def detect_utterance_language(utterance: str, current_language: str = "en-US") -> str:
    """Detect language from an utterance with contextual inertia on silence and numbers."""
    cleaned = re.sub(r"\\[(?:pause|silence)\\]", " ", str(utterance or ""), flags=re.IGNORECASE)
    cleaned = re.sub(r"[0-9\W_]+", " ", cleaned).strip()
    if not cleaned:
        return resolve_locale(current_language)

    low = str(utterance or "").lower()

    explicit_switch = _dp_match_explicit_switch(low)
    if explicit_switch:
        return explicit_switch

    words = [w.lower() for w in cleaned.split()]

    if words == ["merci"] and resolve_locale(current_language) == "en-US":
        return "en-US"
    if words == ["gracias"] and resolve_locale(current_language) == "en-US":
        return "en-US"

    french_words = sum(1 for w in words if w in _FRENCH_MARKERS)
    has_french_accents = bool(re.search(r"[éèêëàâùûîïôçœ]", low))
    french_score = french_words + (1 if has_french_accents else 0)

    spanish_words = sum(1 for w in words if w in _SPANISH_MARKERS)
    has_spanish_punct = bool(re.search(r"[¿¡ñ]", low))
    spanish_score = spanish_words + (1 if has_spanish_punct else 0)

    english_words = sum(1 for w in words if w in _ENGLISH_MARKERS)

    if french_score > 0 and french_score >= spanish_score and french_score >= english_words:
        return "fr-CA"
    if spanish_score > 0 and spanish_score > french_score and spanish_score >= english_words:
        return "es-US"
    if english_words >= 3 and french_score == 0 and spanish_score == 0:
        return "en-US"

    return resolve_locale(current_language)


KEYPAD_FRENCH_CHOICES: frozenset[str] = frozenset({"2", "deux"})
KEYPAD_FRENCH_NOTE = (
    "The caller pressed 2 on the keypad to choose French. It is a language choice, not an account "
    "number: do not call any tool for it; reply in French with your greeting."
)


def _dp_is_keypad_french_choice(utterance: str) -> bool:
    """True when the caller's first input is the keypad language choice for French."""
    cleaned = re.sub(r"[\s.!,#*]+", "", str(utterance or "").strip().lower())
    cleaned = re.sub(r"^(?:pressed|keyed|appuie|touche)", "", cleaned)
    return cleaned in KEYPAD_FRENCH_CHOICES


def detect_active_call_language(state_dict: Any, llm_request: Any) -> str:
    """Determine the active conversation language from state and user turns."""
    user_utterances = extract_user_utterances(llm_request)
    locked = (
        str(state_dict.get("language") or "").strip()
        if callable(getattr(state_dict, "get", None))
        else ""
    )
    if locked:
        locked = resolve_locale(locked)
    else:
        relayed = _extract_relayed_active_language(llm_request)
        if relayed:
            locked = relayed

    if locked and locked != "en-US":
        current = locked
        for utt in user_utterances:
            switch = _dp_match_explicit_switch(utt.lower())
            if switch:
                current = switch
        return current

    current = resolve_locale(locked) if locked else "en-US"
    if not locked and user_utterances and _dp_is_keypad_french_choice(user_utterances[0]):
        # "Press 2 for French": only the caller's very first input selects the
        # language this way; a "2" later in the call (a menu or slot choice) never does.
        current = "fr-CA"
        user_utterances = user_utterances[1:]
    for utt in user_utterances:
        if current != "en-US":
            switch = _dp_match_explicit_switch(utt.lower())
            if switch:
                current = switch
        else:
            current = detect_utterance_language(utt, current_language=current)

    return current


def build_language_sheet(locale: str, agent_name: str = "router") -> str:
    """Generate dynamic language sheet containing localized rules and verbatim lines."""
    loc = resolve_locale(locale)
    lang_name = WORLD_LANGUAGE_NAMES.get(loc, loc)
    keys = AGENT_VERBATIM_KEYS.get(agent_name, AGENT_VERBATIM_KEYS["router"])

    lines = [
        LANGUAGE_SHEET_SENTINEL,
        f'<active_language_sheet locale="{loc}" language="{lang_name}">',
    ]

    if loc in ("en-US", "fr-CA"):
        lines.append("### Required Disclosures & Spoken Lines (Emit Exact Wording):")
        for k in keys:
            line_text = spoken_line(k, loc)
            if line_text:
                lines.append(f'- {k}: "{line_text}"')
        lines.append("")
        lines.append("### Mandatory Conversational Rules:")
        lines.append(
            f"1. Speak 100% in {lang_name} ({loc}). Never mix languages or repeat lines in another language."
        )
        lines.append(
            f'2. Always pass language="{loc}" when calling tools (and write any free-text reason/summary in {lang_name} while keeping structural enum values unchanged).'
        )
        lines.append(
            "3. Emit the verbatim lines above word-for-word whenever their trigger fires, filling slots from tool output only."
        )
    else:
        lines.append("### Canonical Templates:")
        for k in keys:
            line_text = spoken_line(k, "en-US")
            if line_text:
                lines.append(f'- {k}: "{line_text}"')
        lines.append("")
        lines.append("### Mandatory Conversational Rules:")
        lines.append(
            f"1. Speak 100% natively and fluently in {lang_name} ({loc}), translating disclosures faithfully into {lang_name} with zero English mixing."
        )
        lines.append(
            f'2. Pass language="{loc}" to tools; if a request cannot be completed accurately without language degradation, politely offer to connect a specialist via handover_to_person(reason="secondary_language_live_agent", language="{loc}").'
        )

    lines.append("</active_language_sheet>")
    return "\n".join(lines)


# prd.md §6.1 DTMF capture: keypad input reaches the model as user text such as
# "<context>user pressed 1234 on keypad.</context>" or "user pressed 1234".
_RE_DTMF_PRESSED = re.compile(r"\buser\s+pressed\s+([0-9*#](?:[\s,.\-]*[0-9*#])*)", re.IGNORECASE)
# The live phone gateway opens every call with this platform event; text chats never send it.
_RE_PHONE_SESSION_START = re.compile(r"<event\b[^>]*>\s*session\s+start\s*</event>", re.IGNORECASE)


def _content_texts(content: Any) -> list[str]:
    """Text of every part of one request content (or a bare text content)."""
    texts: list[str] = []
    parts = getattr(content, "parts", None)
    if isinstance(parts, (list, tuple)):
        for part in parts:
            txt = getattr(part, "text", None)
            if isinstance(txt, str) and txt.strip():
                texts.append(txt)
            native = getattr(part, "dtmf", None)
            if isinstance(native, str) and native.strip():
                texts.append(f"user pressed {native}")
    elif isinstance(getattr(content, "text", None), str):
        texts.append(content.text)
    return texts


def _latest_user_texts(callback_context: Any, llm_request: Any) -> list[str]:
    """The caller's latest turn: callback_context.user_content, else the last user text in the request."""
    current = [t for t in _content_texts(getattr(callback_context, "user_content", None)) if not _RE_RELAY_PREFIX.match(t.strip())]
    if current:
        return current
    contents = getattr(llm_request, "contents", None)
    if not isinstance(contents, (list, tuple)):
        return []
    for item in reversed(contents):
        if getattr(item, "role", "") != "user":
            continue
        texts = [t for t in _content_texts(item) if not _is_relay_or_quoted_part(t) or _RE_DTMF_PRESSED.search(t)]
        if texts:
            return texts
    return []


def parse_dtmf_digits(text: Any) -> str:
    """Keypad digits from 'user pressed 1234' text ('' when the turn has none); * and # are dropped."""
    found = _RE_DTMF_PRESSED.findall(str(text or ""))
    return "".join(ch for ch in "".join(found) if ch.isdigit())


def _is_phone_session(llm_request: Any) -> bool:
    contents = getattr(llm_request, "contents", None)
    if not isinstance(contents, (list, tuple)):
        return False
    return any(_RE_PHONE_SESSION_START.search(t) for item in contents if getattr(item, "role", "") == "user" for t in _content_texts(item))


def capture_turn_input(callback_context: Any, llm_request: Any) -> None:
    """prd.md §6.1: write this turn's keypad digits to dtmf_digits ("" without DTMF) and mark phone calls.

    Writes only dtmf_digits and call_channel ("voice" once the phone gateway's
    session-start event or keypad input is seen; never cleared), and only when
    the value changes.
    """
    state = getattr(callback_context, "state", None)
    if state is None or not callable(getattr(state, "get", None)):
        return
    digits = parse_dtmf_digits(" ".join(_latest_user_texts(callback_context, llm_request)))
    try:
        if str(state.get("dtmf_digits") or "") != digits:
            state["dtmf_digits"] = digits
        if state.get("call_channel") != "voice" and (digits or _is_phone_session(llm_request)):
            state["call_channel"] = "voice"
    except (TypeError, AttributeError):  # pragma: no cover - read-only state objects
        return


def apply_language_prompt_filter(
    callback_context: Any,
    llm_request: Any,
    agent_name: str = "router",
) -> None:
    """Capture keypad digits (capture_turn_input), then inject language rules and verbatim lines in place."""
    capture_turn_input(callback_context, llm_request)
    state = getattr(callback_context, "state", None)
    state_dict = state if callable(getattr(state, "get", None)) else {}
    locale = detect_active_call_language(state_dict, llm_request)
    sheet = build_language_sheet(locale, agent_name=agent_name)
    utterances = extract_user_utterances(llm_request)
    if len(utterances) == 1 and _dp_is_keypad_french_choice(utterances[0]) and locale == "fr-CA":
        # The caller's only input so far is the keypad language choice ("2" = French):
        # it is not an account number, so greet in French instead of looking it up.
        sheet += "\n" + KEYPAD_FRENCH_NOTE

    config = getattr(llm_request, "config", None)
    if config is None:
        return None
    sys_inst = getattr(config, "system_instruction", None)
    if sys_inst is None:
        return None

    def _update_text(text: str) -> str:
        if LANGUAGE_SHEET_SENTINEL in text:
            text = text.split(LANGUAGE_SHEET_SENTINEL, 1)[0].rstrip()
        return f"{text}\n\n{sheet}"

    if isinstance(sys_inst, str):
        config.system_instruction = _update_text(sys_inst)
    elif hasattr(sys_inst, "parts"):
        parts = getattr(sys_inst, "parts", None)
        if parts and len(parts) > 0:
            first = parts[0]
            if hasattr(first, "text") and isinstance(first.text, str):
                first.text = _update_text(first.text)
    elif isinstance(sys_inst, list) and len(sys_inst) > 0:
        if isinstance(sys_inst[0], str):
            sys_inst[0] = _update_text(sys_inst[0])
        elif hasattr(sys_inst[0], "text") and isinstance(sys_inst[0].text, str):
            sys_inst[0].text = _update_text(sys_inst[0].text)
