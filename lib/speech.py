"""Speech hygiene for every spoken reply: no markdown symbols, no full long numbers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any

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


def strip_markdown(text: str) -> str:
    """Drop the markdown symbols a voice would read out: asterisks, backticks, headings."""
    return MARKDOWN_RE.sub("", text)


_PAYMENT_OR_ACCOUNT_WORDS: tuple[str, ...] = (
    "card", "carte", "visa", "mastercard", "amex", "crédit", "credit", "débit", "debit",
    "bank", "bancaire", "banque", "account", "compte", "chequing", "chèque", "cheque",
)


def clean_speech(text: str) -> str:
    """Everything the speech_hygiene callback does to one piece of reply text."""
    return mask_long_numbers(strip_markdown(text))


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
