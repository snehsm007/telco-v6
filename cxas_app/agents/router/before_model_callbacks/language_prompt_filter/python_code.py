from __future__ import annotations

from typing import Optional



def before_model_callback(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> Optional[LlmResponse]:
    """Inject active language rules and verbatim lines before model invocation."""
    apply_language_prompt_filter(
        callback_context,
        llm_request,
        agent_name="router",
    )
    return None


# --- BEGIN GENERATED SHARED BUNDLE (edit lib/, then run `make bundle`) ---
# uses: from lib.dynamic_prompt import apply_language_prompt_filter
from datetime import datetime, timedelta, timezone
from typing import Any
import re

LANGUAGE_SHEET_SENTINEL = "<!-- ACTIVE_LANGUAGE_SHEET -->"  # pragma: no cover

AGENT_VERBATIM_KEYS: dict[str, tuple[str, ...]] = {  # pragma: no cover
    "router": ("greeting", "handover", "ai_disclosure", "malicious_closing", "recording_notice"),
    "specialist": ("code_sent", "handover", "ai_disclosure", "malicious_closing", "recording_notice"),
}

WORLD_LANGUAGE_NAMES: dict[str, str] = {  # pragma: no cover
    "en-US": "English",
    "fr-CA": "French (Canada)",
    "es-US": "Spanish",
}

def resolve_locale(language: str | None) -> str:  # pragma: no cover
    """Normalize a language tag or prefix to a supported BCP-47 locale code."""
    raw = str(language or "").strip()
    if not raw:
        return "en-US"
    low = raw.lower().replace("_", "-")
    if low.startswith("fr"):
        return "fr-CA"
    if low.startswith("es"):
        return "es-US"
    if low.startswith("en"):
        return "en-US"
    return "en-US"

SPOKEN_LINES: dict[str, dict[str, str]] = {  # pragma: no cover
    "greeting": {
        "en-US": "Hello, thanks for calling. Which phone number or account number can I look up for you?",
        "fr-CA": "Bonjour, merci de votre appel. Quel numéro de téléphone ou numéro de compte puis-je rechercher pour vous?",
        "es-US": "Hola, gracias por su llamada. ¿Qué número de teléfono o número de cuenta puedo buscar para usted?",
    },
    "code_sent": {
        "en-US": "I've sent a login code to the phone number ending in [destination_last4]. Please read it to me when it arrives.",
        "fr-CA": "J'ai envoyé un code de connexion au numéro se terminant par [destination_last4]. Lisez-le-moi dès que vous le recevez.",
        "es-US": "Envié un código de acceso al número que termina en [destination_last4]. Léamelo cuando lo reciba.",
    },
    "handover": {
        "en-US": "I'm transferring you to a member of our team now. Thank you for your patience.",
        "fr-CA": "Je vous transfère maintenant à un membre de notre équipe. Merci de votre patience.",
        "es-US": "Le transfiero ahora con un miembro de nuestro equipo. Gracias por su paciencia.",
    },
    "account_found": {
        "en-US": "Account found for [first_name].",
        "fr-CA": "Compte trouvé pour [first_name].",
        "es-US": "Cuenta encontrada para [first_name].",
    },
    "code_verified": {
        "en-US": "Login verified successfully.",
        "fr-CA": "Connexion vérifiée avec succès.",
        "es-US": "Inicio de sesión verificado con éxito.",
    },
    "already_verified": {
        "en-US": "Account is already verified.",
        "fr-CA": "Le compte est déjà vérifié.",
        "es-US": "La cuenta ya está verificada.",
    },
    "pin_verified": {
        "en-US": "Secret PIN verified successfully.",
        "fr-CA": "NIP secret vérifié avec succès.",
        "es-US": "PIN secreto verificado con éxito.",
    },
    "request_submitted": {
        "en-US": "Your request has been submitted successfully.",
        "fr-CA": "Votre demande a été soumise avec succès.",
        "es-US": "Su solicitud ha sido enviada con éxito.",
    },
    "restricted_caller": {
        "en-US": "This number is not authorized for telephone service. Please visit our website or a retail store for assistance.",
        "fr-CA": "Ce numéro n'est pas autorisé pour le service téléphonique. Veuillez visiter notre site Web ou un magasin pour obtenir de l'aide.",
        "es-US": "Este número no está autorizado para el servicio telefónico. Visite nuestro sitio web o una tienda para obtener ayuda.",
    },
    "ai_disclosure": {
        "en-US": "I'm an artificial intelligence customer care assistant.",
        "fr-CA": "Je suis un assistant de service à la clientèle basé sur l'intelligence artificielle.",
        "es-US": "Soy un asistente de atención al cliente con inteligencia artificial.",
    },
    "malicious_closing": {
        "en-US": "I am unable to continue this conversation. Thank you for calling and have a good day.",
        "fr-CA": "Je ne peux pas poursuivre cette conversation. Merci de votre appel et bonne journée.",
        "es-US": "No puedo continuar con esta conversación. Gracias por llamar y que tenga un buen día.",
    },
    "recording_notice": {
        "en-US": "This call may be monitored or recorded for quality and training purposes.",
        "fr-CA": "Cet appel peut être surveillé ou enregistré à des fins de qualité et de formation.",
        "es-US": "Esta llamada puede ser monitoreada o grabada con fines de calidad y capacitación.",
    },
    "card_declined": {
        "en-US": "That card was declined. Would you like to try another card or a different payment method?",
        "fr-CA": "Cette carte a été refusée. Souhaitez-vous essayer une autre carte ou un autre mode de paiement?",
        "es-US": "Esa tarjeta fue rechazada. ¿Desea probar con otra tarjeta o un método de pago diferente?",
    },
}

def spoken_line(key: str, language: str | None = "en-US", **slots: object) -> str:  # pragma: no cover
    """Return the fixed spoken line for `key` and `language`, filling any `[slot]` placeholders."""
    locale = resolve_locale(language)
    table = SPOKEN_LINES.get(key, {})
    template = table.get(locale) or table.get("en-US") or ""
    for slot_name, slot_val in slots.items():
        template = template.replace(f"[{slot_name}]", str(slot_val))
    return template

def build_language_sheet(locale: str, agent_name: str = "router") -> str:  # pragma: no cover
    """Generate dynamic language sheet containing localized rules and verbatim lines."""
    loc = resolve_locale(locale)
    lang_name = WORLD_LANGUAGE_NAMES.get(loc, loc)
    keys = AGENT_VERBATIM_KEYS.get(agent_name, AGENT_VERBATIM_KEYS.get("router", ("greeting", "handover")))

    lines = [
        LANGUAGE_SHEET_SENTINEL,
        f'<active_language_sheet locale="{loc}" language="{lang_name}">',
    ]

    if loc in ("en-US", "fr-CA", "es-US"):
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
    return "\\n".join(lines)

_DP_EXPLICIT_SWITCH_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (  # pragma: no cover
    ("fr-CA", ("en français", "en francais", "parlez-vous français", "parlez vous francais", "in french", "speak french", "french please", "switch to french")),
    ("es-US", ("en español", "en espanol", "habla español", "habla espanol", "in spanish", "speak spanish", "spanish please", "switch to spanish")),
    ("en-US", ("in english", "speak english", "english please", "switch to english")),
    ("de-DE", ("auf deutsch", "sprechen sie deutsch", "in german", "speak german", "german please", "switch to german")),
    ("it-IT", ("in italiano", "parla italiano", "in italian", "speak italian", "italian please", "switch to italian")),
    ("pt-BR", ("em português", "em portugues", "fala português", "fala portugues", "in portuguese", "speak portuguese", "portuguese please", "switch to portuguese")),
)

_DP_NEGATED_SWITCH_PREFIX_RE = re.compile(  # pragma: no cover
    r"(?:"
    r"\b(?:don't|do\s+not|dont|cannot|can't|cant|not|unable to|not able to)\s+"
    r"(?:want\s+to\s+|know\s+how\s+to\s+)?(?:speak\s+|talk\s+|switch\s+to\s+)?"
    r"|\b(?:pas|jamais)\s+(?:parler\s+|continuer\s+)?"
    r"|\bno\s+(?:hablo|habla|hablas|hablamos|puedo|podemos|quiero)\s+(?:hablar\s+)?"
    r")\s*$",
    re.IGNORECASE,
)

def _dp_match_explicit_switch(low: str) -> str:  # pragma: no cover
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

_RE_RELAY_ACTIVE_LANG = re.compile(  # pragma: no cover
    r"""['"]active_language['"]\s*:\s*['"]([a-zA-Z]{2}(?:-[a-zA-Z]{2})?)['"]"""
)

def _extract_relayed_active_language(llm_request: Any) -> str:  # pragma: no cover
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

_ENGLISH_MARKERS: frozenset[str] = frozenset({  # pragma: no cover
    "hello", "hi", "thanks", "thank", "yes", "yeah", "account", "bill",
    "pay", "service", "help", "need", "representative", "agent", "speak",
    "code", "received", "please", "support",
})

_FRENCH_MARKERS: frozenset[str] = frozenset({  # pragma: no cover
    "bonjour", "merci", "oui", "non", "svp", "compte", "facture", "payer",
    "service", "aide", "besoin", "agent", "parler", "code", "reçu", "francais",
    "français", "salut", "allo", "allô", "s'il", "vous", "plaît", "plait",
})

_SPANISH_MARKERS: frozenset[str] = frozenset({  # pragma: no cover
    "hola", "gracias", "si", "sí", "cuenta", "factura", "pagar", "servicio",
    "ayuda", "necesito", "agente", "hablar", "codigo", "código", "espanol",
    "español", "buenas", "tardes", "días", "favor", "por",
})

def detect_utterance_language(utterance: str, current_language: str = "en-US") -> str:  # pragma: no cover
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

_RE_QUOTED_AGENT_BLOCK = re.compile(  # pragma: no cover
    r"<<<BEGIN_QUOTED_AGENT_CONTENT>>>[\s\S]*?<<<END_QUOTED_AGENT_CONTENT>>>"
)

_RE_RELAY_PREFIX = re.compile(  # pragma: no cover
    r"^(?:For context|\s*\[[^\]]+\]\s*(?:said:|thought:|called tool |`[^`]*` tool returned result:))",
    re.IGNORECASE,
)

def _is_relay_or_quoted_part(txt: str) -> bool:  # pragma: no cover
    """Return True if txt is an ADK relay part, agent event, or quoted content block."""
    s = txt.strip()
    if not s:
        return True
    if _RE_RELAY_PREFIX.match(s):
        return True
    cleaned = _RE_QUOTED_AGENT_BLOCK.sub("", s).strip()
    if not cleaned:
        return True
    if _RE_RELAY_PREFIX.match(cleaned):
        return True
    return False

def extract_user_utterances(llm_request: Any) -> list[str]:  # pragma: no cover
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
                            utterances.append(txt.strip())
            elif isinstance(getattr(item, "text", None), str):
                t = item.text.strip()
                if t and not _is_relay_or_quoted_part(t):
                    utterances.append(t)
    return utterances

def detect_active_call_language(state_dict: Any, llm_request: Any) -> str:  # pragma: no cover
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
    for utt in user_utterances:
        if current != "en-US":
            switch = _dp_match_explicit_switch(utt.lower())
            if switch:
                current = switch
        else:
            current = detect_utterance_language(utt, current_language=current)

    return current

def apply_language_prompt_filter(  # pragma: no cover
    callback_context: Any,
    llm_request: Any,
    agent_name: str = "router",
) -> None:
    """Inject language rules and verbatim lines into system instruction in-place without touching state."""
    state = getattr(callback_context, "state", None)
    state_dict = state if callable(getattr(state, "get", None)) else {}
    locale = detect_active_call_language(state_dict, llm_request)
    sheet = build_language_sheet(locale, agent_name=agent_name)

    config = getattr(llm_request, "config", None)
    if config is None:
        return None
    sys_inst = getattr(config, "system_instruction", None)
    if sys_inst is None:
        return None

    def _update_text(text: str) -> str:
        if LANGUAGE_SHEET_SENTINEL in text:
            text = text.split(LANGUAGE_SHEET_SENTINEL, 1)[0].rstrip()
        return f"{text}\\n\\n{sheet}"

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
# --- END GENERATED SHARED BUNDLE ---
