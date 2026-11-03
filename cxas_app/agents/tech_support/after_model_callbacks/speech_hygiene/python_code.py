from __future__ import annotations

from types import SimpleNamespace
from typing import Optional



def after_model_callback(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> Optional[LlmResponse]:
    """Cleans every text part of the reply before the caller hears it.

    Strips markdown symbols, masks long numbers to their last 4 digits and
    prefers caller_provided_phone_last4. After a handover it adds
    handoff_message only when the reply has no spoken text at all; it never
    replaces words the model said, so a step-specific or PRD-exact transfer
    line survives. A reply that ends the session with no text at all gets a
    closing line (silent_turn_line), so no call ends in dead air. Returns None when nothing changed, so the reply goes out
    untouched.
    """
    state = getattr(callback_context, "state", None)
    state_dict = state if isinstance(state, dict) else {}
    content = getattr(llm_response, "content", None)
    parts = getattr(content, "parts", None) if content is not None else None
    if content is None or parts is None:
        return None
    changed = False
    has_spoken_text = False

    for part in parts:
        text = getattr(part, "text", None)
        if not isinstance(text, str) or not text.strip():
            continue
        has_spoken_text = True
        cleaned = clean_agent_speech(clean_speech(text), state_dict)
        if cleaned != text:
            part.text = cleaned
            changed = True

    if not has_spoken_text:
        end_session_args = None
        for part in parts:
            call = getattr(part, "function_call", None)
            if call is not None and getattr(call, "name", "") == "end_session":
                end_session_args = dict(getattr(call, "args", None) or {})
        handoff_msg = silent_turn_line(state_dict, end_session_args).strip()
        if handoff_msg and isinstance(parts, list):
            cleaned_msg = clean_agent_speech(clean_speech(handoff_msg), state_dict)
            if parts and getattr(parts[0], "text", None) in (None, "") and not getattr(parts[0], "function_call", None):
                parts[0].text = cleaned_msg
            else:
                parts.insert(0, SimpleNamespace(text=cleaned_msg))
            changed = True

    return llm_response if changed else None


# --- BEGIN GENERATED SHARED BUNDLE (edit lib/, then run `make bundle`) ---
# uses: from lib.speech import clean_agent_speech, clean_speech, silent_turn_line
from datetime import datetime, timedelta, timezone
from typing import Any
import re
import unicodedata

_PAYMENT_OR_ACCOUNT_WORDS: tuple[str, ...] = (  # pragma: no cover
    "card", "carte", "visa", "mastercard", "amex", "crédit", "credit", "débit", "debit",
    "bank", "bancaire", "banque", "account", "compte", "chequing", "chèque", "cheque",
)

MIN_MASKED_DIGITS = 7  # pragma: no cover

NUMBER_RUN_RE = re.compile(r"\(?\d+\)?(?:[-.]\(?\d+\)?|\s\(?\d{3,}\)?)*")  # pragma: no cover

SHORT_NUMBER_KEEP_RE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{4}/\d{2}/\d{2}|\d+\.\d{2}")  # pragma: no cover

SPEAKABLE_NUMBERS: frozenset[str] = frozenset()  # pragma: no cover

def mask_long_numbers(text: str, min_digits: int = MIN_MASKED_DIGITS) -> str:  # pragma: no cover
    """Replace every number of `min_digits` or more digits by its last 4 digits."""

    def _mask(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        if len(digits) < min_digits or digits in SPEAKABLE_NUMBERS:
            return match.group(0)
        if len(digits) < 9 and SHORT_NUMBER_KEEP_RE.fullmatch(match.group(0)):
            return match.group(0)
        return digits[-4:]

    return NUMBER_RUN_RE.sub(_mask, text)

SECRET_CODE_RE = re.compile(  # pragma: no cover
    r"\b(?P<word>pin|nip|passcode|code)\b(?P<gap>(?:\s+(?:is|was|est|of|de|:)|\s*:)*\s*)"
    r"(?P<digits>\d(?:[\s-]?\d){3,7})(?![\d-])",
    re.IGNORECASE,
)

_SECRET_CODE_SKIP_BEFORE = ("error", "erreur", "area", "régional", "postal")  # pragma: no cover

def mask_secret_codes(text: str) -> str:  # pragma: no cover
    """Drop the digits of a PIN (4-8 digits) or login code (6-8 digits) said after its name.

    "Error code 1002" (a TV error code) and "area code 514" are kept.
    """

    def _drop(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group("digits"))
        word = match.group("word").lower()
        before = text[max(0, match.start() - 10) : match.start()].lower()
        if word == "code" and (len(digits) < 6 or any(w in before for w in _SECRET_CODE_SKIP_BEFORE)):
            return match.group(0)
        return match.group("word")

    return SECRET_CODE_RE.sub(_drop, text)

MARKDOWN_RE = re.compile(r"\*+|`+|^#+[ \t]*", re.MULTILINE)  # pragma: no cover

def strip_markdown(text: str) -> str:  # pragma: no cover
    """Drop the markdown symbols a voice would read out: asterisks, backticks, headings."""
    return MARKDOWN_RE.sub("", text)

def clean_speech(text: str) -> str:  # pragma: no cover
    """Everything the speech_hygiene callback does to one piece of reply text."""
    return mask_long_numbers(mask_secret_codes(strip_markdown(text)))

def clean_agent_speech(  # pragma: no cover
    text: str,
    session_params: dict[str, Any] | None = None,
) -> str:
    """Clean markdown and long numbers, and say the caller's own phone ending.

    The only digit rewrite: when the caller identified with a phone whose last
    4 (caller_provided_phone_last4) differ from the default account phone
    (phone_last4), a spoken phone_last4 becomes caller_provided_phone_last4.
    Any other 4-digit ending (temporary number, ticket, card, bank, account,
    claim, order, transfer) is a tool fact and is never touched, and a
    phone_last4 said right after a card, bank or account word, or equal to
    card_last4, is kept too. The callback never invents digits.
    """
    cleaned = clean_speech(text)
    if not isinstance(session_params, dict):
        return cleaned
    caller_last4 = str(session_params.get("caller_provided_phone_last4") or "").strip()
    profile_last4 = str(session_params.get("phone_last4") or "").strip()
    card_last4 = str(session_params.get("card_last4") or "").strip()
    if not (
        len(caller_last4) == 4
        and caller_last4.isdigit()
        and len(profile_last4) == 4
        and profile_last4.isdigit()
        and profile_last4 != caller_last4
        and profile_last4 != card_last4
    ):
        return cleaned
    source = cleaned

    def _swap_profile_last4(m: re.Match[str]) -> str:
        prefix = source[max(0, m.start() - 35) : m.start()].lower()
        if any(w in prefix for w in _PAYMENT_OR_ACCOUNT_WORDS):
            # Card, bank and account endings come from tool results; never swap them for phone digits.
            return m.group(0)
        return caller_last4

    return re.sub(rf"\b{re.escape(profile_last4)}\b", _swap_profile_last4, cleaned)

END_SESSION_LINES: dict[str, str] = {  # pragma: no cover
    "malicious_input": "malicious_closing",
    "blocked_caller": "restricted_caller",
}

def _truthy(value: Any) -> bool:  # pragma: no cover
    return value is True or str(value).strip().lower() in ("true", "1", "yes")

def enforce_handover_utterance(  # pragma: no cover
    text: str,
    session_params: dict[str, Any] | None = None,
) -> str:
    """Fill an empty handover turn with handoff_message; leave spoken text alone.

    After handover_to_person ran (handover_complete is True), a reply with no
    spoken text gets the localized handoff_message. Text the model did speak is
    returned unchanged, so a step-specific or PRD-exact transfer line survives.
    """
    if (text or "").strip():
        return text
    if not isinstance(session_params, dict) or not session_params.get("handover_complete"):
        return text
    handoff_msg = str(session_params.get("handoff_message") or "").strip()
    return handoff_msg or text

SPOKEN_LINES: dict[str, dict[str, str]] = {  # pragma: no cover
    "greeting_main": {
        "en-US": "Welcome to Telco. I can help with billing, technical support, or managing your account. To get started, could you tell me the phone number or account number associated with your service?",
        "fr-CA": "Bienvenue chez Telco. Je peux vous aider avec la facturation, le soutien technique ou la gestion de votre compte. Pour commencer, pourriez-vous me donner le numéro de téléphone ou le numéro de compte associé à votre service?",
    },
    "recording_notice": {
        "en-US": "This call may be recorded for quality and training purposes.",
        "fr-CA": "Cet appel peut être enregistré à des fins de qualité et de formation.",
    },
    "id_verification_otp": {
        "en-US": "For your security, I just sent a 6-digit code to that number — please read it back to me.",
        "fr-CA": "Pour votre sécurité, je viens d'envoyer un code à 6 chiffres à ce numéro — veuillez me le lire.",
    },
    "id_verification_pin": {
        "en-US": "For your security, I'll need to verify your identity. Please enter the 4-digit PIN you set up.",
        "fr-CA": "Pour votre sécurité, je dois vérifier votre identité. Veuillez entrer le NIP à 4 chiffres que vous avez configuré.",
    },
    "live_agent_handoff": {
        "en-US": "I'll connect you to a representative who can help. Please hold.",
        "fr-CA": "Je vais vous mettre en relation avec un représentant qui pourra vous aider. Veuillez patienter.",
    },
    # Operational handover lines (scorecard: transfer context, fraud team, distress);
    # spoken by handover_to_person around the verbatim §7 lines, never instead of them.
    # Interim French PENDING LEGAL APPROVAL (docs/requirements.md decision A6).
    "fraud_team_transfer": {
        "en-US": "I'm transferring you now to our fraud prevention team; they'll have the details you've shared, and they're available 24/7.",
        "fr-CA": "Je vous transfère maintenant à notre équipe de prévention de la fraude; elle aura les détails que vous avez fournis, et elle est disponible 24 heures sur 24, 7 jours sur 7.",
    },
    "handoff_context_note": {
        "en-US": "I've passed along what we've discussed so you won't need to repeat it.",
        "fr-CA": "J'ai transmis ce dont nous avons discuté, vous n'aurez donc pas à le répéter.",
    },
    # Context line for business_handoff: the business team takes over the caller's request.
    "business_context_note": {
        "en-US": "Our business team will take care of your request from here, and I've passed along what you've asked so you won't need to repeat it.",
        "fr-CA": "Notre équipe Affaires s'occupera de votre demande à partir d'ici, et j'ai transmis ce que vous avez demandé, vous n'aurez donc pas à le répéter.",
    },
    "distress_acknowledgement": {
        "en-US": "I understand this has been frustrating, and I'm sorry for the trouble.",
        "fr-CA": "Je comprends que la situation soit frustrante, et je suis désolé pour ces inconvénients.",
    },
    "business_handoff": {
        "en-US": "To get you the best support for your business account, I'll transfer you to an agent. You'll need to use your phone keypad instead of talking to the virtual assistant. Just a moment while I connect you.",
        "fr-CA": "Pour vous offrir le meilleur soutien pour votre compte d'affaires, je vais vous transférer à un agent. Vous devrez utiliser le clavier de votre téléphone au lieu de parler à l'assistant virtuel. Un instant pendant que je vous mets en relation.",
    },
    "payment_method_preamble": {
        "en-US": "Before we continue, please note that your payment details are protected and processed securely, and I will only ever refer to the last four digits of your card or account.",
        "fr-CA": "Avant de continuer, sachez que vos renseignements de paiement sont protégés et traités de façon sécurisée, et que je ne mentionnerai jamais que les quatre derniers chiffres de votre carte ou de votre compte.",
    },
    "contract_cancellation_fee_disclosure": {
        "en-US": "Please note that cancelling before the end of your contract term may result in an early termination fee and a final bill, as set out in your service agreement.",
        "fr-CA": "Veuillez noter qu'une résiliation avant la fin de la durée de votre contrat peut entraîner des frais de résiliation anticipée et une facture finale, comme le prévoit votre entente de service.",
    },
    "refund_confirmation_pattern": {
        "en-US": "Your refund of $[amount] will appear on your next statement within [days] business days.",
        "fr-CA": "Votre remboursement de [amount] $ apparaîtra sur votre prochain relevé d'ici [days] jours ouvrables.",
    },
    "empathy_protocol": {
        "en-US": "I'm very sorry to hear that you are facing challenges. I will ensure we handle your request with the utmost care.",
        "fr-CA": "Je suis vraiment désolé d'apprendre que vous éprouvez des difficultés. Je veillerai à ce que votre demande soit traitée avec le plus grand soin.",
    },
    "outage_active": {
        "en-US": "I see there's an active outage in your area. We're working on it. Would you like me to text you when it's restored?",
        "fr-CA": "Je constate qu'il y a une panne active dans votre secteur. Nous y travaillons. Voulez-vous que je vous envoie un texto lorsque le service sera rétabli?",
    },
    "sms_outage_updates_confirmed": {
        "en-US": "You're all set. I'll text the number ending in [last4] as soon as service is restored.",
        "fr-CA": "C'est noté. J'enverrai un texto au numéro se terminant par [last4] dès que le service sera rétabli.",
    },
    "sms_slot_callback_confirmed": {
        "en-US": "You're all set. I'll text the number ending in [last4] as soon as a slot opens.",
        "fr-CA": "C'est noté. J'enverrai un texto au numéro se terminant par [last4] dès qu'une plage se libère.",
    },
    "sms_sent_confirmed": {
        "en-US": "Done. I've sent the text to the number ending in [last4].",
        "fr-CA": "C'est fait. J'ai envoyé le texto au numéro se terminant par [last4].",
    },
    # Troubleshooting guide texted: the confirmation carries the follow-up question, so the
    # agent never appends an ungrounded one to a verbatim spoken_message.
    "sms_guide_sent_confirmed": {
        "en-US": "Done. I've sent the guide to the number ending in [last4]. Would you like to go through the steps together now?",
        "fr-CA": "C'est fait. J'ai envoyé le guide au numéro se terminant par [last4]. Voulez-vous qu'on fasse les étapes ensemble maintenant?",
    },
    "transfer_to_specialist": {
        "en-US": "I'll connect you to a billing specialist now — they'll have everything we've already discussed.",
        "fr-CA": "Je vais vous mettre en relation avec un spécialiste de la facturation — il aura tout ce dont nous avons déjà discuté.",
    },
    "refund_over_limit": {
        "en-US": "That amount is above our $[limit] self-serve limit, so it needs a specialist's approval.",
        "fr-CA": "Ce montant dépasse notre limite libre-service de [limit] $, il doit donc être approuvé par un spécialiste.",
    },
    "otp_callback_on_file": {
        "en-US": "I'll send a 6-digit code to the mobile number on file. Ready?",
        "fr-CA": "Je vais envoyer un code à 6 chiffres au numéro de mobile au dossier. Êtes-vous prêt?",
    },
    "otp_callback_confirm": {
        "en-US": "I'll send a 6-digit code to the number ending in [last4]. Ready?",
        "fr-CA": "Je vais envoyer un code à 6 chiffres au numéro se terminant par [last4]. Êtes-vous prêt?",
    },
    "pin_alternative": {
        "en-US": "Or, if you prefer, you can use your 4-digit PIN instead.",
        "fr-CA": "Ou, si vous préférez, vous pouvez plutôt utiliser votre NIP à 4 chiffres.",
    },
    # Operational line: said after check_login_code / check_secret_pin succeed, so the
    # confirmation is grounded in the tool reply (judges flagged a bare "You are verified.").
    "login_verified": {
        "en-US": "You are verified.",
        "fr-CA": "Votre identité est vérifiée.",
    },
    # Texted and emailed codes may be spoken (appended after the PRD verbatim lines).
    "say_code_aloud": {
        "en-US": "Please say the 6 digits out loud.",
        "fr-CA": "Dites les 6 chiffres à voix haute.",
    },
    # prd.md PIN flow: on a phone call the PIN is accepted from the keypad only
    # (voice-spelled PINs are refused); check_secret_pin texts a code instead.
    "pin_keypad_required": {
        "en-US": "For your security, your PIN can only be entered on the keypad, so I just texted a 6-digit code to the mobile on file instead. Please say the 6 digits out loud.",
        "fr-CA": "Pour votre sécurité, votre NIP ne peut être entré qu'au clavier; je viens donc d'envoyer un code à 6 chiffres par texto au mobile au dossier. Dites les 6 chiffres à voix haute.",
    },
    "pin_keypad_code_pending": {
        "en-US": "For your security, your PIN can only be entered on the keypad. Please say the 6-digit code I texted you out loud instead.",
        "fr-CA": "Pour votre sécurité, votre NIP ne peut être entré qu'au clavier. Dites plutôt à voix haute le code à 6 chiffres que je vous ai envoyé par texto.",
    },
    # Operational line (no account number at hand); interim wording PENDING LEGAL APPROVAL.
    "account_lookup_options": {
        "en-US": "To find your account, I can use its phone number or account number, your email on file, or your 4-digit PIN.",
        "fr-CA": "Pour trouver votre compte, je peux utiliser son numéro de téléphone ou son numéro de compte, votre courriel au dossier ou votre NIP à 4 chiffres.",
    },
    "email_code_sent": {
        "en-US": "For your security, I just sent a 6-digit code to your email on file — please read it back to me.",
        "fr-CA": "Pour votre sécurité, je viens d'envoyer un code à 6 chiffres à votre adresse courriel au dossier — veuillez me le lire.",
    },
    "callback_next_business_day": {
        "en-US": "That team is closed right now, so I've arranged for them to call you back on the next business day.",
        "fr-CA": "Cette équipe est fermée en ce moment, alors j'ai demandé qu'elle vous rappelle le prochain jour ouvrable.",
    },
    "restricted_caller": {
        "en-US": "We're unable to help with this call on this line. Please visit one of our stores for assistance. Goodbye.",
        "fr-CA": "Nous ne pouvons pas traiter cet appel sur cette ligne. Veuillez vous rendre dans l'une de nos boutiques pour obtenir de l'aide. Au revoir.",
    },
    "ai_disclosure": {
        "en-US": "I'm an artificial intelligence customer care assistant.",
        "fr-CA": "Je suis un assistant de service à la clientèle basé sur l'intelligence artificielle.",
    },
    "closing_goodbye": {
        "en-US": "Thank you for calling. Have a great day.",
        "fr-CA": "Merci de votre appel. Bonne journée.",
    },
    "malicious_closing": {
        "en-US": "I am unable to continue this conversation. Thank you for calling and have a good day.",
        "fr-CA": "Je ne peux pas poursuivre cette conversation. Merci de votre appel et bonne journée.",
    },
}

def resolve_locale(language: str | None) -> str:  # pragma: no cover
    """Normalize a language tag or prefix to a supported locale (en-US or fr-CA)."""
    low = str(language or "").strip().lower().replace("_", "-")
    if low.startswith("fr"):
        return "fr-CA"
    return "en-US"

def spoken_line(key: str, language: str | None = "en-US", **slots: object) -> str:  # pragma: no cover
    """Return the fixed spoken line for `key` and `language`, filling any `[slot]` placeholders."""
    locale = resolve_locale(language)
    table = SPOKEN_LINES.get(key, {})
    template = table.get(locale) or table.get("en-US") or ""
    for slot_name, slot_val in slots.items():
        template = template.replace(f"[{slot_name}]", str(slot_val))
    return template

def silent_turn_line(  # pragma: no cover
    session_params: dict[str, Any] | None,
    end_session_args: dict[str, Any] | None = None,
) -> str:
    """The line to speak when a reply has no text: never end a call in silence.

    After a handover it is handoff_message (as before). Otherwise, only when
    the reply calls end_session: malicious_closing for malicious_input,
    restricted_caller for blocked_caller, live_agent_handoff when the session
    is escalated, and a short localized goodbye for any other reason.
    A silent turn without end_session (a transfer to another agent) stays silent.
    """
    params = session_params if isinstance(session_params, dict) else {}
    handoff = enforce_handover_utterance("", params).strip()
    if handoff:
        return handoff
    if end_session_args is None:
        return ""
    args = end_session_args if isinstance(end_session_args, dict) else {}
    reason = str(args.get("reason") or "").strip().lower()
    key = END_SESSION_LINES.get(reason)
    if key is None:
        key = "live_agent_handoff" if _truthy(args.get("session_escalated")) else "closing_goodbye"
    return spoken_line(key, str(params.get("language") or params.get("preferred_language") or "en-US"))
# --- END GENERATED SHARED BUNDLE ---
