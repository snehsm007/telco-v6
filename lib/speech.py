"""Speech hygiene for every spoken reply: no markdown symbols, no full long numbers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any

from lib.fakes import spoken_line

# Numbers the PRD wants said in full, such as a support line. Every other
# number with 7 or more digits (a local phone number, a 7- or 8-digit account
# number, a card) is cut to its last 4 digits (BR-TV-009).
SPEAKABLE_NUMBERS: frozenset[str] = frozenset()
MIN_MASKED_DIGITS = 7
# Under 9 digits, an ISO date (2026-10-08) or a plain money amount (12345.67)
# is not personal data and stays as spoken.
SHORT_NUMBER_KEEP_RE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{4}/\d{2}/\d{2}|\d+\.\d{2}")

# Digit groups joined by "-" or ".", or by a space when the next group has 3+
# digits. Phone, card and account numbers match in full; a date and time such
# as "2026-10-08 14:30" stops at 8 digits.
NUMBER_RUN_RE = re.compile(r"\(?\d+\)?(?:[-.]\(?\d+\)?|\s\(?\d{3,}\)?)*")
MARKDOWN_RE = re.compile(r"\*+|`+|^#+[ \t]*", re.MULTILINE)


def mask_long_numbers(text: str, min_digits: int = MIN_MASKED_DIGITS) -> str:
    """Replace every number of `min_digits` or more digits by its last 4 digits."""

    def _mask(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        if len(digits) < min_digits or digits in SPEAKABLE_NUMBERS:
            return match.group(0)
        if len(digits) < 9 and SHORT_NUMBER_KEEP_RE.fullmatch(match.group(0)):
            return match.group(0)
        return digits[-4:]

    return NUMBER_RUN_RE.sub(_mask, text)


# A PIN or login code said right after its name ("PIN 7316", "le code 615203",
# "votre NIP est 7316"). BR-TV-009: PINs and codes are never spoken back.
SECRET_CODE_RE = re.compile(
    r"\b(?P<word>pin|nip|passcode|code)\b(?P<gap>(?:\s+(?:is|was|est|of|de|:)|\s*:)*\s*)"
    r"(?P<digits>\d(?:[\s-]?\d){3,7})(?![\d-])",
    re.IGNORECASE,
)
_SECRET_CODE_SKIP_BEFORE = ("error", "erreur", "area", "régional", "postal")


def mask_secret_codes(text: str) -> str:
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


def strip_markdown(text: str) -> str:
    """Drop the markdown symbols a voice would read out: asterisks, backticks, headings."""
    return MARKDOWN_RE.sub("", text)


_PAYMENT_OR_ACCOUNT_WORDS: tuple[str, ...] = (
    "card", "carte", "visa", "mastercard", "amex", "crédit", "credit", "débit", "debit",
    "bank", "bancaire", "banque", "account", "compte", "chequing", "chèque", "cheque",
)


def clean_speech(text: str) -> str:
    """Everything the speech_hygiene callback does to one piece of reply text."""
    return mask_long_numbers(mask_secret_codes(strip_markdown(text)))


def clean_agent_speech(
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


def enforce_handover_utterance(
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


# Closing line for an end_session turn the model left silent, by end_session reason.
END_SESSION_LINES: dict[str, str] = {
    "malicious_input": "malicious_closing",
    "blocked_caller": "restricted_caller",
}


def _truthy(value: Any) -> bool:
    return value is True or str(value).strip().lower() in ("true", "1", "yes")


def silent_turn_line(
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
