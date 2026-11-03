"""Shared tools (M1 identity, M2 login, handover, SMS) and the tool registry.

Each `<tool>_impl` backs the thin wrapper in cxas_app/tools/<tool>/. Domain tools
live in lib/billing.py, lib/tech.py, lib/sales.py and lib/account.py and are
re-exported here so suite/tool_tests.py finds every tool through ALL_TOOLS.
Every session key used here is declared in cxas_app/app.json (lint rule V100).
"""

from __future__ import annotations

import json
import re
from typing import Any

from lib.account import (  # noqa: F401
    cancel_or_port_out_service_impl,
    execute_suspend_restore_impl,
    manage_mfa_impl,
    send_password_reset_link_impl,
    update_contact_profile_impl,
)
from lib.billing import (  # noqa: F401
    apply_bill_adjustment_impl,
    get_billing_summary_impl,
    process_bill_payment_impl,
    setup_autopay_impl,
    setup_payment_arrangement_impl,
    verify_payment_and_restore_impl,
)
from lib.core import (
    account_record,
    check_mock_error,
    ensure_account,
    fixture,
    fixture_flag,
    get_state,
    queue_open,
    service_status,
    NO_ACCOUNT_ACTION,
    session_language,
    validation_error,
)
from lib.fakes import (
    ACCOUNTS,
    BLOCKED_CALLER_NUMBERS,
    OTP_EXPIRES_IN_SEC,
    REGION_BY_POSTAL_LETTER,
    SELF_SERVE_ADJUSTMENT_LIMIT,
    DEFAULT_REGION,
    OTP_RE,
    PIN_RE,
    classify_identifier,
    find_account,
    is_name_or_address,
    is_plausible_phone,
    login_code_accepted,
    normalize_code,
    spoken_digits,
    spoken_number_text,
    normalize_identifier,
    only_digits,
    read_count,
    resolve_copy_locale,
    spoken_line,
)
from lib.replies import ERROR_CODES, display_amount, error_reply, ok_reply, tracking_id  # noqa: F401
from lib.sales import (  # noqa: F401
    browse_plans_impl,
    file_warranty_claim_impl,
    place_order_impl,
    start_number_transfer_impl,
)
from lib.speech import redact_pii
from lib.tech import (  # noqa: F401
    check_regional_outage_impl,
    get_appointment_and_ticket_status_impl,
    manage_appointment_impl,
    run_virtual_repair_impl,
)

ALL_TOOLS = (
    "lookup_account",
    "send_login_code",
    "check_login_code",
    "check_secret_pin",
    "handover_to_person",
    "send_sms_notification",
    "get_billing_summary",
    "process_bill_payment",
    "setup_autopay",
    "apply_bill_adjustment",
    "setup_payment_arrangement",
    "verify_payment_and_restore",
    "check_regional_outage",
    "run_virtual_repair",
    "get_appointment_and_ticket_status",
    "manage_appointment",
    "browse_plans",
    "place_order",
    "file_warranty_claim",
    "start_number_transfer",
    "send_password_reset_link",
    "manage_mfa",
    "execute_suspend_restore",
    "cancel_or_port_out_service",
    "update_contact_profile",
)

# Login tries allowed on one call (prd.md §9: third failure escalates).
MAX_LOGIN_ATTEMPTS = 3
SMS_PURPOSES = ("outage_updates", "troubleshooting_guide", "slot_available_callback", "registration_link")

# prd.md §7 / docs/tdd.md §7: which line(s) each handover reason speaks. Verbatim
# §7 lines are spoken unaltered; the scorecard's "next steps & transfer context"
# adds handoff_context_note after them (transfer_to_specialist already says it).
# refund_threshold_exceeded first says why (over the self-serve limit, needs a
# specialist's approval; prd.md §10), then the verbatim transfer line, last.
# Fraud: verbatim empathy_protocol first (BR-TV-013), then the fraud-team transfer.
HANDOVER_LINES: dict[str, tuple[str, ...]] = {
    "business_handoff": ("business_handoff", "handoff_context_note"),
    "fraud_escalation": ("empathy_protocol", "fraud_team_transfer"),
    "refund_threshold_exceeded": ("refund_over_limit", "transfer_to_specialist"),
}
DEFAULT_HANDOVER_LINES: tuple[str, ...] = ("live_agent_handoff", "handoff_context_note")
# Scorecard "acknowledge distress": a frustrated or worried caller hears one short
# acknowledgement before the transfer (fraud already opens with empathy_protocol).
_DISTRESS_RE = re.compile(
    r"frustrat|angry|upset|annoy|furious|mad at|fed up|sick of|tired of|ridiculous|"
    r"in circles|going around|worried|stress|anxious|disconnect|cut off|"
    r"fâch|fach|en col[eè]re|tann[eé]|écœur|ecoeur|en rond|inqui[eè]t|énerv|enerv",
    re.IGNORECASE,
)
HANDOVER_QUEUES: dict[str, str] = {
    "fraud_escalation": "fraud",
    "business_handoff": "business",
    "refund_threshold_exceeded": "billing_specialist",
    "secondary_language_live_agent": "french_support",
    "sales_specialist": "sales",
    "appointment_booking": "appointments",
}
HANDOVER_REASONS: tuple[str, ...] = (
    "user_requested_agent",
    "auth_failure_handoff",
    "no_input_escalation",
    "disambig_max_attempts",
    "system_unavailable",
    "too_many_errors",
    "secondary_language_live_agent",
    "sms_delivery_failed",
    "business_handoff",
    "fraud_escalation",
    "refund_threshold_exceeded",
    "sales_specialist",
    "appointment_booking",
)
_REASON_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("fraud_escalation", ("fraud", "hack", "pirat", "scam", "phish", "sim swap", "stolen number", "unauthori")),
    ("business_handoff", ("business", "affaires", "entreprise")),
    ("refund_threshold_exceeded", ("threshold", "refund", "rembours", "over limit", "exceed")),
    ("auth_failure_handoff", ("auth", "lock", "verification", "verrouill")),
    ("system_unavailable", ("system", "unavailable", "outage of tool")),
    ("no_input_escalation", ("no input", "silence", "no_input")),
)
_HANDOVER_FR_WORDS = re.compile(
    r"\b(?:bonjour|merci|compte|facture|facturation|paiement|transf[eé]rer|repr[eé]sentant|"
    r"humain|personne|aide|svp|oui|num[eé]ro|t[eé]l[eé]phone|fran[cç]ais|parler|quelqu|"
    r"besoin|[eé]quipe|pirat[eé]|annuler|t[eé]l[eé]|panne|je|veux|mon|ma)\b"
)


def _region_for_postal(postal_code: str) -> str:
    """Region class from a Canadian postal code's first letter (DESIGN_RULES rule 40)."""
    first = str(postal_code or "").strip()[:1].upper()
    return REGION_BY_POSTAL_LETTER.get(first, DEFAULT_REGION)


# What the model passes when the caller asks to use the number they are calling from (prd.md §5 `clid`).
CALLER_ID_REQUESTS: frozenset[str] = frozenset({"", "clid"})


def _caller_id_phone(state: dict[str, Any]) -> str:
    """The caller ID (`clid`, prd.md §5) when it is a valid 10-digit phone number, else ""."""
    kind, digits = classify_identifier(state.get("clid"))
    return digits if kind == "phone" and is_plausible_phone(digits) else ""


def lookup_account_impl(
    phone_or_account: str | int | float,
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Find the caller's account (Guest -> Identified) and remember it for the call."""
    state = get_state(state, session_state)
    lang = session_language(state, language)
    err = check_mock_error(state, lang, "lookup_account")
    if err:
        return err
    raw = str(phone_or_account or "").strip()
    raw = spoken_number_text(re.sub(r"\.0+$", "", raw))
    used_caller_id = False
    caller_id_source = ""
    if raw.lower() in CALLER_ID_REQUESTS:
        # No number given ("use the number I'm calling from"): try the caller ID once.
        raw = _caller_id_phone(state)
        used_caller_id = True
        caller_id_source = "clid"
        if not raw:
            # No usable caller ID (text chats, evaluations): simulate the line, as an unknown
            # email resolves the default account (find_account). An account already identified
            # on this call is kept. Identification only: login is still required.
            raw = str(state.get("account_id") or "")
            caller_id_source = "session_account" if raw else "default_line"
            raw = raw or ACCOUNTS[0]["account_id"]
    reference = tracking_id("lookup_account", raw)
    digits = only_digits(raw)
    norm_digits = digits[1:] if (len(digits) == 11 and digits.startswith("1")) else digits
    if digits in BLOCKED_CALLER_NUMBERS or norm_digits in BLOCKED_CALLER_NUMBERS:
        state["is_blocked"] = True
        state["last_tracking_id"] = reference
        return error_reply(
            "PERMISSION_DENIED",
            "This number is on the restricted list.",
            "Say the restricted_caller line and end the session with reason blocked_caller.",
            reference,
            language=lang,
            data={"blocked": True},
        )
    account = find_account(raw)
    options = {"spoken_message": spoken_line("account_lookup_options", lang), "pin_length": 4}
    if account is None and is_name_or_address(raw):
        # A name or address is not a wrong entry: no strike (BR-TV-010 counts malformed numbers only).
        state["last_tracking_id"] = reference
        return error_reply(
            "NOT_FOUND",
            "Accounts are found by number, email or PIN, not by name or address.",
            NO_ACCOUNT_ACTION,
            reference,
            language=lang,
            data={**options, "counted": False},
        )
    if account is None:
        return validation_error(
            state,
            "No account matches that number.",
            "Say you couldn't find that account and ask for the number again.",
            reference,
            lang,
            code="NOT_FOUND",
            data=options,
        )
    if state.get("account_id") and state.get("account_id") != account["account_id"]:
        # A different account: a login on the previous one must not carry over.
        # The call's failed-login count is kept, so switching accounts never resets a lockout.
        state["auth_status"] = "none" if state.get("auth_status") != "locked" else "locked"
        state["logged_in"] = False
        state["login_code_sent"] = False
        state["step_up_verified"] = False
    business = bool(account.get("business_flag")) or fixture_flag(state, "fx_business_account")
    state["account_id"] = account["account_id"]
    state["phone_last4"] = account["phone"][-4:]
    if caller_id_source != "session_account":
        state["phone_derived"] = bool(account.get("phone_derived"))
    ident = normalize_identifier(raw)
    if caller_id_source != "session_account":
        state["caller_provided_phone_last4"] = (
            only_digits(ident["value"])[-4:] if ident["kind"] in ("phone", "international_phone") else ""
        )
    state["identification_status"] = "Pass"
    state["business_flag"] = business
    state["customer_type"] = account.get("customer_type", "Existing")
    state["region"] = _region_for_postal(account.get("postal_code", ""))
    if account.get("preferred_language") and not state.get("preferred_language"):
        state["preferred_language"] = account["preferred_language"]
    state["last_tracking_id"] = reference
    data = {
        "identification_status": "Pass",
        "account_id_last4": normalize_code(account["account_id"])[-4:] or account["account_id"][-4:],
        "phone_last4": "" if state.get("phone_derived") else str(state.get("phone_last4") or ""),
        "mobile_on_file": bool(account.get("phone")),
        "caller_provided_phone_last4": str(state.get("caller_provided_phone_last4") or ""),
        "business_flag": business,
        "customer_type": state["customer_type"],
        "lines_of_business": list(account.get("lines_of_business", [])),
        "region": state["region"],
        "used_caller_id": used_caller_id,
        "caller_id_source": caller_id_source,
    }
    reply = ok_reply(data, reference, language=lang)
    if business:
        reply["agent_action"] = "Business account: hand over with reason business_handoff."
    elif state.get("auth_status") == "locked":
        reply["agent_action"] = "Login is locked on this call: hand over with reason auth_failure_handoff."
    return reply


def _failures(state: dict[str, Any]) -> int:
    """The call's shared failed-login count (codes and PINs)."""
    return max(read_count(state, "auth_failure_count"), read_count(state, "login_attempts"))


def _locked_reply(state: dict[str, Any], reference: str, lang: str) -> dict[str, Any]:
    """Reply once the caller has used up their login attempts (prd.md §9 step 6)."""
    state["auth_status"] = "locked"
    state["logged_in"] = False
    return error_reply(
        "TOO_MANY_ATTEMPTS",
        "Too many wrong codes on this call.",
        "Hand over with reason auth_failure_handoff.",
        reference,
        language=lang,
        data={"attempts_remaining": 0, "lockout_triggered": True, "auth_status": "locked"},
    )


def _record_failure(state: dict[str, Any], reference: str, lang: str, kind: str) -> dict[str, Any]:
    """Count one wrong code or PIN; the third locks the caller out."""
    failures = _failures(state) + 1
    state["auth_failure_count"] = failures
    state["login_attempts"] = failures
    if kind == "pin":
        state["pin_failure_count"] = read_count(state, "pin_failure_count") + 1
    if failures >= MAX_LOGIN_ATTEMPTS:
        return _locked_reply(state, reference, lang)
    remaining = MAX_LOGIN_ATTEMPTS - failures
    return error_reply(
        "WRONG_CODE" if kind == "code" else "WRONG_PIN",
        "That code does not match." if kind == "code" else "That PIN does not match.",
        "Say it didn't match and ask the caller to try again.",
        reference,
        language=lang,
        data={"attempts_remaining": remaining, "lockout_triggered": False},
    )


def _credential_ok(state: dict[str, Any], digits: str, kind: str) -> bool:
    """Exact match when a credential is on file (fx_pin_on_file / fx_otp_on_file), else the login ladder."""
    on_file = {normalize_code(fixture(state, "fx_pin_on_file")), normalize_code(fixture(state, "fx_otp_on_file"))} - {""}
    if on_file:
        return digits in on_file
    return login_code_accepted(digits, attempts=_failures(state), max_attempts=MAX_LOGIN_ATTEMPTS)


def send_login_code_impl(
    channel: str = "sms",
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Send a 6-digit code by text (login) or to the email on file (MFA step-up). Never returns the code."""
    state = get_state(state, session_state)
    lang = session_language(state, language)
    err = check_mock_error(state, lang, "send_login_code")
    if err:
        return err
    account_id = ensure_account(state)
    chan = "email" if str(channel or "").strip().lower().startswith("e") else "sms"
    reference = tracking_id("send_login_code", account_id, chan)
    state["last_tracking_id"] = reference
    if state.get("auth_status") == "locked" or _failures(state) >= MAX_LOGIN_ATTEMPTS:
        return _locked_reply(state, reference, lang)
    logged_in = state.get("auth_status") == "pass"
    purpose = "step_up" if logged_in and (chan == "email" or state.get("step_up_pending")) else "login"
    if logged_in and purpose == "login":
        return ok_reply({"sent": False, "already_verified": True}, reference, language=lang)
    if not logged_in:
        state["auth_status"] = "code_sent"
    state["login_code_sent"] = True
    state["login_channel"] = chan
    state["code_purpose"] = purpose
    record = account_record(state)
    data: dict[str, Any] = {
        "sent": True,
        "channel": chan,
        "purpose": purpose,
        "code_length": 6,
        "expires_in_sec": OTP_EXPIRES_IN_SEC,
    }
    if chan == "email":
        email = str(record.get("email", ""))
        user, _, domain = email.partition("@")
        data["email_masked"] = (user[:1] + "***@" + domain) if domain else "on file"
        data["spoken_message"] = spoken_line("email_code_sent", lang) + " " + spoken_line("say_code_aloud", lang)
    else:
        data["destination_last4"] = str(
            state.get("caller_provided_phone_last4")
            or ("" if state.get("phone_derived") else (state.get("phone_last4") or record["phone"][-4:]))
        )
        data["spoken_message"] = spoken_line("id_verification_otp", lang) + " " + spoken_line("say_code_aloud", lang)
    reply = ok_reply(data, reference, language=lang)
    if chan == "email" and purpose == "login":
        # The login code went to the email on file (the caller can't get a text).
        reply["agent_action"] = "Say a 6-digit code was sent to the email on file and ask the caller to read it back."
    return reply


def check_login_code_impl(
    code: str | int | float = "",
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Check the code the caller read back or keyed in (login or step-up)."""
    state = get_state(state, session_state)
    lang = session_language(state, language)
    err = check_mock_error(state, lang, "check_login_code")
    if err:
        return err
    account_id = ensure_account(state)
    reference = tracking_id("check_login_code", account_id, spoken_digits(code))
    state["last_tracking_id"] = reference
    step_up = state.get("code_purpose") == "step_up" and state.get("auth_status") == "pass"
    if state.get("auth_status") == "pass" and not step_up:
        state["logged_in"] = True
        return ok_reply({"verified": True, "logged_in": True}, reference, language=lang)
    if state.get("auth_status") == "locked" or _failures(state) >= MAX_LOGIN_ATTEMPTS:
        return _locked_reply(state, reference, lang)
    digits = spoken_digits(code) or normalize_code(state.get("dtmf_digits"))
    if PIN_RE.fullmatch(digits) and not step_up:
        # The caller gave their 4-digit PIN instead of the texted code.
        return check_secret_pin_impl(digits, state=state, language=lang)
    if not OTP_RE.fullmatch(digits):
        # A re-ask, never a strike (docs/tdd.md §6); it still counts toward global_err_count.
        if step_up:
            return validation_error(
                state,
                "The emailed code has 6 digits.",
                "Say the code sent to their email has 6 digits, ask them to say all of them out loud, and offer to resend it by email.",
                reference,
                lang,
            )
        return validation_error(state, "A verification code has 6 digits.", "Ask the caller to say the 6-digit code out loud again.", reference, lang)
    if not _credential_ok(state, digits, "code"):
        return _record_failure(state, reference, lang, "code")
    state["auth_failure_count"] = 0
    state["login_attempts"] = 0
    if step_up:
        state["step_up_verified"] = True
        state["step_up_pending"] = False
        state["code_purpose"] = "login"
        return ok_reply({"verified": True, "step_up_verified": True, "logged_in": True}, reference, language=lang)
    state["auth_status"] = "pass"
    state["logged_in"] = True
    return ok_reply({"verified": True, "logged_in": True}, reference, language=lang)


def is_voice_call(state: dict[str, Any]) -> bool:
    """True on a live phone call (the before-model callback sets call_channel; text chats stay "")."""
    return str(state.get("call_channel") or "").strip().lower() == "voice"


def _pin_keypad_required(state: dict[str, Any], reference: str, lang: str) -> dict[str, Any]:
    """Refuse a spoken PIN on a phone call and text a login code instead (one agent turn)."""
    data: dict[str, Any] = {"keypad_only": True, "code_length": 6}
    if state.get("login_code_sent") and state.get("login_channel") == "sms":
        data["sent"] = False
        data["spoken_message"] = spoken_line("pin_keypad_code_pending", lang)
    else:
        sent = send_login_code_impl("sms", state=state, language=lang)
        if sent.get("status") != "ok":
            return sent
        data["sent"] = True
        data["destination_last4"] = sent["data"].get("destination_last4", "")
        data["spoken_message"] = spoken_line("pin_keypad_required", lang)
    state["last_tracking_id"] = reference
    return error_reply(
        "PIN_KEYPAD_REQUIRED",
        "On a phone call the PIN can only be keyed in; a login code was texted instead.",
        "Say spoken_message word for word, then check the 6-digit code the caller says. Never ask for the PIN again.",
        reference,
        language=lang,
        data=data,
    )


def check_secret_pin_impl(
    pin: str | int | float = "",
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Check the caller's 4-digit PIN (keyed in on the phone keypad; typed digits in chat)."""
    state = get_state(state, session_state)
    lang = session_language(state, language)
    err = check_mock_error(state, lang, "check_secret_pin")
    if err:
        return err
    account_id = ensure_account(state)
    reference = tracking_id("check_secret_pin", account_id, spoken_digits(pin))
    state["last_tracking_id"] = reference
    if state.get("code_purpose") == "step_up" and state.get("auth_status") == "pass":
        # A step-up code is pending: digits given here are the emailed code.
        return check_login_code_impl(pin, state=state, language=lang)
    if state.get("auth_status") == "pass":
        state["logged_in"] = True
        return ok_reply({"verified": True, "logged_in": True}, reference, language=lang)
    if state.get("auth_status") == "locked" or _failures(state) >= MAX_LOGIN_ATTEMPTS:
        return _locked_reply(state, reference, lang)
    keyed = normalize_code(state.get("dtmf_digits"))
    digits = spoken_digits(pin) or keyed
    if OTP_RE.fullmatch(digits) and state.get("login_code_sent"):
        # The caller read back the 6-digit texted code.
        return check_login_code_impl(digits, state=state, language=lang)
    if is_voice_call(state):
        # prd.md PIN flow: on a phone call only keypad digits count; a voice-spelled
        # PIN is refused (never a strike) and a texted code is offered in the same turn.
        if not PIN_RE.fullmatch(keyed):
            return _pin_keypad_required(state, reference, lang)
        digits = keyed
    if not PIN_RE.fullmatch(digits):
        return validation_error(state, "A PIN has 4 digits.", "Ask the caller to key in their 4-digit PIN again.", reference, lang)
    if not _credential_ok(state, digits, "pin"):
        return _record_failure(state, reference, lang, "pin")
    state["auth_status"] = "pass"
    state["logged_in"] = True
    state["auth_failure_count"] = 0
    state["login_attempts"] = 0
    return ok_reply({"verified": True, "logged_in": True}, reference, language=lang)


def _normalize_reason(reason: str) -> str:
    """Map the model's reason text onto a PRD reason code."""
    clean = re.sub(r"[\s\-]+", "_", str(reason or "").strip().lower())
    if clean in HANDOVER_REASONS:
        return clean
    spaced = clean.replace("_", " ")
    for code, words in _REASON_KEYWORDS:
        if any(w in spaced for w in words):
            return code
    return "user_requested_agent"


def _handover_language(state: dict[str, Any], language: str, texts: tuple[str, ...]) -> str:
    """DESIGN_RULES rule 25: explicit arg, then call language, then French words, then profile."""
    active = str(state.get("language") or "").strip()
    if active and resolve_copy_locale(active) != "en-US":
        return resolve_copy_locale(active)
    if language and str(language).strip():
        return session_language(state, language)
    if active:
        return resolve_copy_locale(active)
    combined = " ".join(str(t or "") for t in texts).lower()
    if _HANDOVER_FR_WORDS.search(combined):
        return session_language(state, "fr-CA")
    pref = str(state.get("preferred_language") or "")
    return resolve_copy_locale(pref) if pref else "en-US"


def handover_to_person_impl(
    reason: str = "user_requested_agent",
    summary: str = "",
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Hand the caller to a live agent with session context; returns the verbatim handoff_message."""
    state = get_state(state, session_state)
    code = _normalize_reason(reason)
    lang = _handover_language(state, str(language or ""), (reason, summary, state.get("utterance")))
    err = check_mock_error(state, lang, "handover_to_person")
    if err and code != "system_unavailable":
        return err
    keys = HANDOVER_LINES.get(code, DEFAULT_HANDOVER_LINES)
    queue = HANDOVER_QUEUES.get(code, "general")
    open_now = queue_open(queue)
    if not open_now:
        # The queue is closed (BR-TV-014): say the callback, never "please hold".
        keys = ("callback_next_business_day", "handoff_context_note")
    distressed = code != "fraud_escalation" and bool(
        _DISTRESS_RE.search(" ".join(str(t or "") for t in (reason, summary, state.get("utterance"))))
    )
    if distressed:
        keys = ("distress_acknowledgement", *keys)
    limit = display_amount(SELF_SERVE_ADJUSTMENT_LIMIT)
    message = " ".join(spoken_line(k, lang, limit=limit) for k in keys)
    context = {
        "reason": code,
        "summary": redact_pii(" ".join(str(summary or "").split()))[:300],
        "language": lang,
        "account_id_last4": normalize_code(state.get("account_id", ""))[-4:],
        "identification_status": state.get("identification_status") or "Fail",
        "auth_status": state.get("auth_status") or "none",
        "business_flag": bool(state.get("business_flag")),
        "service_status": state.get("service_status") or "",
        "last_tracking_id": state.get("last_tracking_id") or "",
        "applied_adjustments": state.get("applied_adjustments") or "",
        "phone_last4": str(state.get("caller_provided_phone_last4") or state.get("phone_last4") or "")[-4:],
        "customer_type": state.get("customer_type") or "",
        "region": state.get("region") or "",
        "lob": state.get("lob") or "",
        "route": state.get("route") or "",
        "global_err_count": read_count(state, "global_err_count"),
        "auth_failure_count": read_count(state, "auth_failure_count"),
        "queue": queue,
        "queue_open": open_now,
    }
    reference = tracking_id("handover_to_person", state.get("account_id", ""), code, lang)
    state["language"] = lang
    state["handoff_reason"] = code
    state["handoff_context"] = json.dumps(context, ensure_ascii=False)
    state["handover_complete"] = True
    state["handoff_message"] = message
    state["handoff_status"] = "completed_via_specialist_queue" if open_now else "callback_next_business_day"
    state["last_tracking_id"] = reference
    return ok_reply(
        {
            "handoff_status": state["handoff_status"],
            "reason": code,
            "queue": queue,
            "queue_open": open_now,
            "language": lang,
            "handover_id": reference,
            "handoff_message": message,
            "session_context_attached": True,
            "distress_acknowledged": distressed,
            "action_fulfilled": True,
            "task_completed": True,
            "user_goal_fulfilled": True,
        },
        reference,
        language=lang,
    )


# Texts about public information need no account: they go to the caller's own line.
PUBLIC_SMS_PURPOSES: frozenset[str] = frozenset({"outage_updates", "troubleshooting_guide"})
SMS_CONFIRMATION_LINES: dict[str, str] = {
    "outage_updates": "sms_outage_updates_confirmed",
    "slot_available_callback": "sms_slot_callback_confirmed",
}


def _sms_line_number(raw: Any) -> str:
    """A caller-given mobile number (PHONE_* formats, 10 plausible digits), else ""."""
    kind, digits = classify_identifier(raw)
    return digits if kind == "phone" and is_plausible_phone(digits) else ""


def _sms_destination(state: dict[str, Any], mobile_number: str) -> tuple[str, str]:
    """(last4, source) of the number to text: the number the caller gave, the number on file,
    the caller ID (`clid`), or the simulated calling line (like lookup_account's default_line)."""
    given = _sms_line_number(mobile_number)
    if given:
        return given[-4:], "caller_provided"
    clid = _caller_id_phone(state)
    on_file = str(state.get("phone_last4") or account_record(state)["phone"][-4:])
    if state.get("account_id") and not (clid and state.get("phone_derived")):
        # A phone synthesized from account digits is never spoken when the caller ID is known.
        return on_file, "on_file"
    if clid:
        return clid[-4:], "clid"
    return ACCOUNTS[0]["phone"][-4:], "default_line"


def send_sms_notification_impl(
    purpose: str = "outage_updates",
    mobile_number: str | int | float = "",
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Text the caller (outage updates, troubleshooting guide, slot callback, registration link).

    Outage updates and the troubleshooting guide are public: with no account found they go
    to the number the caller gave, else the caller ID, else the calling line.
    """
    state = get_state(state, session_state)
    lang = session_language(state, language)
    err = check_mock_error(state, lang, "send_sms_notification")
    if err:
        return err
    clean = re.sub(r"[\s\-]+", "_", str(purpose or "").strip().lower())
    raw_number = re.sub(r"\.0+$", "", str(mobile_number or "").strip())
    reference = tracking_id("send_sms_notification", state.get("account_id", ""), clean, raw_number)
    if clean not in SMS_PURPOSES:
        return validation_error(
            state,
            "Unknown text message purpose.",
            "Use outage_updates, troubleshooting_guide, slot_available_callback or registration_link.",
            reference,
            lang,
        )
    if raw_number and not _sms_line_number(raw_number):
        return validation_error(
            state,
            "That is not a 10-digit mobile number.",
            "Ask for the 10-digit mobile number to text, then retry with mobile_number.",
            reference,
            lang,
        )
    if not state.get("account_id") and not raw_number and clean not in PUBLIC_SMS_PURPOSES:
        return error_reply(
            "NOT_IDENTIFIED",
            "No mobile number on file yet.",
            "Ask which phone number to text, call lookup_account, then retry.",
            reference,
            language=lang,
        )
    last4, source = _sms_destination(state, raw_number)
    sent = [p for p in str(state.get("sms_sent") or "").split(",") if p]
    sent.append(clean)
    state["sms_sent"] = ",".join(sent[-10:])
    state["last_tracking_id"] = reference
    line = SMS_CONFIRMATION_LINES.get(clean, "sms_sent_confirmed")
    data = {
        "purpose": clean,
        "sms_sent": True,
        "destination_last4": last4,
        "destination_source": source,
        "sms_purpose": clean,
        "spoken_message": spoken_line(line, lang, last4=last4),
    }
    reply = ok_reply(data, reference, language=lang)
    reply["agent_action"] = "Say spoken_message word for word."
    return reply

lookup_account = lookup_account_impl
send_login_code = send_login_code_impl
check_login_code = check_login_code_impl
check_secret_pin = check_secret_pin_impl
handover_to_person = handover_to_person_impl
send_sms_notification = send_sms_notification_impl
get_billing_summary = get_billing_summary_impl
process_bill_payment = process_bill_payment_impl
setup_autopay = setup_autopay_impl
apply_bill_adjustment = apply_bill_adjustment_impl
setup_payment_arrangement = setup_payment_arrangement_impl
verify_payment_and_restore = verify_payment_and_restore_impl
check_regional_outage = check_regional_outage_impl
run_virtual_repair = run_virtual_repair_impl
get_appointment_and_ticket_status = get_appointment_and_ticket_status_impl
manage_appointment = manage_appointment_impl
browse_plans = browse_plans_impl
place_order = place_order_impl
file_warranty_claim = file_warranty_claim_impl
start_number_transfer = start_number_transfer_impl
send_password_reset_link = send_password_reset_link_impl
manage_mfa = manage_mfa_impl
execute_suspend_restore = execute_suspend_restore_impl
cancel_or_port_out_service = cancel_or_port_out_service_impl
update_contact_profile = update_contact_profile_impl
