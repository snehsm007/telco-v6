from typing import Any



def check_login_code(
    code: str | int | float = "",
    language: str = "",
) -> dict[str, Any]:
    """Checks the verification code the caller read back or keyed in. Use it for the texted
      login code and for the emailed step-up code. Three wrong codes or PINs on a call
      lock the caller out.

    Args:
      code: The digits exactly as the caller gave them, as a quoted string.
      language: Active language code (en-US or fr-CA).

    Returns:
      status, data (verified, logged_in, step_up_verified), error_message, tracking_id.
        Errors add error (WRONG_CODE, TOO_MANY_ATTEMPTS, INVALID_INPUT) and
        agent_action.
    """
    ctx = globals().get("context")
    state = getattr(ctx, "state", None) if ctx is not None else None
    if state is None and isinstance(ctx, dict):
        state = ctx
    return check_login_code_impl(
        code=code,
        language=language,
        state=state,
    )


# --- BEGIN GENERATED SHARED BUNDLE (edit lib/, then run `make bundle`) ---
# uses: from lib.services import check_login_code_impl
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
import hashlib
import json
import re

MAX_LOGIN_ATTEMPTS = 3  # pragma: no cover

OTP_RE = re.compile(r"^[0-9]{6}$")  # pragma: no cover

PIN_RE = re.compile(r"^[0-9]{4}$")  # pragma: no cover

def read_count(state: dict[str, Any] | None, key: str) -> int:  # pragma: no cover
    """Read a whole-number variable; the platform hands them to tools as decimals (5 -> 5.0)."""
    if not isinstance(state, dict):
        return 0
    try:
        return int(float(state.get(key) or 0))
    except (TypeError, ValueError):
        return 0

def _failures(state: dict[str, Any]) -> int:  # pragma: no cover
    """The call's shared failed-login count (codes and PINs)."""
    return max(read_count(state, "auth_failure_count"), read_count(state, "login_attempts"))

FIXTURE_DEFAULTS: dict[str, str] = {  # pragma: no cover
    "fx_pin_on_file": "",
    "fx_otp_on_file": "",
    "fx_card_on_file_status": "valid",
    "fx_service_status": "active",
    "fx_recent_payment": "none",
    "fx_business_account": "false",
    "fx_outage_status": "",
    "fx_technician_status": "scheduled",
    "fx_duplicate_payment": "false",
    "fx_extra_bill_line": "",
    "fx_device_warranty": "in_warranty",
    "fx_mfa_enabled": "false",
    "fx_sms_delivery": "delivered",
}

def fixture(state: dict[str, Any] | None, name: str) -> str:  # pragma: no cover
    """Read a backend fixture (`fx_*`): the session override when set, else FIXTURE_DEFAULTS."""
    raw = ""
    if isinstance(state, dict):
        raw = str(state.get(name) or "").strip()
    if not raw:
        raw = FIXTURE_DEFAULTS.get(name, "")
    return raw.strip().lower() if name not in ("fx_pin_on_file", "fx_otp_on_file", "fx_extra_bill_line") else raw.strip()

ALWAYS_WRONG_LOGIN_CODES: frozenset[str] = frozenset({"9999", "999999", "8888"})  # pragma: no cover

VALID_OTPS: frozenset[str] = frozenset({"271846", "482913"})  # pragma: no cover

VALID_PINS: frozenset[str] = frozenset({"5903", "5678"})  # pragma: no cover

VALID_LOGIN_CODES: frozenset[str] = VALID_OTPS | VALID_PINS  # pragma: no cover

def is_weak_code(digits: str) -> bool:  # pragma: no cover
    """A code made of one repeated digit (e.g. all sevens) is never a valid credential."""
    return bool(digits) and len(set(digits)) == 1

def normalize_code(value: Any) -> str:  # pragma: no cover
    """Coerce ints, floats (e.g. 5903.0), and formatted strings into a clean digit string."""
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return str(abs(value))
    if isinstance(value, float):
        if value.is_integer():
            return str(int(abs(value)))
        return re.sub(r"\D", "", str(value))
    text = str(value).strip()
    if re.fullmatch(r"[+-]?\d+\.0+", text):
        text = text.split(".", 1)[0]
    return "".join(ch for ch in text if ch.isdigit())

def login_code_accepted(code_digits: Any, attempts: int = 0, max_attempts: int = 3) -> bool:  # pragma: no cover
    """Whether the fake login service accepts a code on this try (the login ladder).

    `attempts` is the number of wrong tries so far on this call:
      - weak codes (one repeated digit) and ALWAYS_WRONG_LOGIN_CODES never pass;
      - first try (attempts == 0): any 4-digit PIN or 6-digit code;
      - second try: only VALID_LOGIN_CODES;
      - the last try (attempts == max_attempts - 1): always wrong.
    Lookups with a credential on file (fx_pin_on_file / fx_otp_on_file) bypass
    the ladder in lib/services.py and compare exactly.
    """
    digits = normalize_code(code_digits)
    if not (PIN_RE.fullmatch(digits) or OTP_RE.fullmatch(digits)):
        return False
    if digits in ALWAYS_WRONG_LOGIN_CODES or is_weak_code(digits):
        return False
    if attempts >= max(max_attempts - 1, 1):
        return False
    if attempts >= 1:
        return digits in VALID_LOGIN_CODES
    return True

def _credential_ok(state: dict[str, Any], digits: str, kind: str) -> bool:  # pragma: no cover
    """Exact match when a credential is on file (fx_pin_on_file / fx_otp_on_file), else the login ladder."""
    on_file = {normalize_code(fixture(state, "fx_pin_on_file")), normalize_code(fixture(state, "fx_otp_on_file"))} - {""}
    if on_file:
        return digits in on_file
    return login_code_accepted(digits, attempts=_failures(state), max_attempts=MAX_LOGIN_ATTEMPTS)

ERROR_CODES = (  # pragma: no cover
    "INVALID_INPUT",
    "NOT_FOUND",
    "NOT_IDENTIFIED",
    "NOT_LOGGED_IN",
    "CODE_NOT_SENT",
    "WRONG_CODE",
    "WRONG_PIN",
    "TOO_MANY_ATTEMPTS",
    "LOCKED_OUT",
    "CARD_DECLINED",
    "PAYMENT_DECLINED",
    "INELIGIBLE",
    "NOT_ELIGIBLE",
    "ALREADY_PROCESSED",
    "ALREADY_APPLIED",
    "ALREADY_ENROLLED",
    "OUT_OF_WINDOW",
    "OUTAGE_ACTIVE",
    "LIMIT_EXCEEDED",
    "INTERNAL_ERROR",
    "SERVICE_UNAVAILABLE",
    "SYSTEM_UNAVAILABLE",
    "SYSTEM_DOWN",
    "PERMISSION_DENIED",
    "TOO_MANY_ERRORS",
    "MALFORMED_REQUEST",
    "AUTH_SERVICE_UNAVAILABLE",
    "INSUFFICIENT_FUNDS",
    "REFUND_THRESHOLD_EXCEEDED",
    "TECHNICIAN_EN_ROUTE",
    "NO_AVAILABILITY",
    "STEP_UP_REQUIRED",
    "NO_PAYMENT_FOUND",
    "CONFIRMATION_REQUIRED",
    "TV_SUB_TYPE_REQUIRED",
    "CARD_EXPIRED",
    "NOT_SUSPENDED",
    "DELIVERY_FAILED",
)

ERROR_CODE_DEFAULTS: dict[str, tuple[str, str]] = {  # pragma: no cover
    "INVALID_INPUT": (
        "The provided input is invalid.",
        "Ask the caller to repeat the information clearly.",
    ),
    "NOT_FOUND": (
        "No matching record was found.",
        "Ask the caller to repeat the identifier one digit at a time.",
    ),
    "NOT_IDENTIFIED": (
        "The caller's account has not been found yet.",
        "Call lookup_account or use the active session account.",
    ),
    "NOT_LOGGED_IN": (
        "The caller has not passed login.",
        "Log the caller in with send_login_code and check_login_code, then retry.",
    ),
    "CODE_NOT_SENT": (
        "No login code has been sent on this call.",
        "Call send_login_code or verify the code the caller provided.",
    ),
    "WRONG_CODE": (
        "The code does not match.",
        "Tell the caller the code didn't match and ask them to try again.",
    ),
    "WRONG_PIN": (
        "The secret PIN does not match.",
        "Tell the caller the PIN didn't match and ask them to try again.",
    ),
    "TOO_MANY_ATTEMPTS": (
        "Too many wrong login codes on this call.",
        "Call handover_to_person, speak handoff_message, and call end_session.",
    ),
    "LOCKED_OUT": (
        "The caller is locked out after too many failed attempts.",
        "Call handover_to_person, speak handoff_message, and call end_session.",
    ),
    "CARD_DECLINED": (
        "The card was declined.",
        "Tell the caller the card was declined and ask for another payment method.",
    ),
    "PAYMENT_DECLINED": (
        "The payment method was declined.",
        "Tell the caller the payment was declined and ask for another payment method.",
    ),
    "INELIGIBLE": (
        "The account is not eligible for this request.",
        "Explain that the account is not eligible and offer to transfer to a person.",
    ),
    "NOT_ELIGIBLE": (
        "The account is not eligible for this option.",
        "Explain that the account is not eligible and offer an available alternative.",
    ),
    "ALREADY_PROCESSED": (
        "This request has already been processed.",
        "Let the caller know the request was already completed.",
    ),
    "ALREADY_APPLIED": (
        "This credit or adjustment has already been applied.",
        "Let the caller know the adjustment was already applied.",
    ),
    "ALREADY_ENROLLED": (
        "The account is already enrolled in this feature.",
        "Let the caller know the account is already enrolled.",
    ),
    "OUT_OF_WINDOW": (
        "The request is outside the allowed time window.",
        "Explain the policy window and offer to transfer to a person.",
    ),
    "OUTAGE_ACTIVE": (
        "An active service outage affects this area.",
        "Share the outage status and estimated restoration details with the caller.",
    ),
    "LIMIT_EXCEEDED": (
        "The requested amount or count exceeds the allowed limit.",
        "Explain the limit and offer to transfer to a person.",
    ),
    "INTERNAL_ERROR": (
        "An internal error occurred while processing the request.",
        "Apologize for the issue and hand the caller over to a person.",
    ),
    "SERVICE_UNAVAILABLE": (
        "The upstream service is currently unavailable.",
        "Hand over with reason system_unavailable.",
    ),
    "SYSTEM_DOWN": (
        "The service is temporarily unavailable.",
        "Hand over with reason system_unavailable.",
    ),
    "SYSTEM_UNAVAILABLE": (
        "The service is temporarily unavailable.",
        "Hand over with reason system_unavailable.",
    ),
    "PERMISSION_DENIED": (
        "Permission denied.",
        "Explain the restriction and hand the caller over to a person.",
    ),
    "TOO_MANY_ERRORS": (
        "Too many invalid entries on this call.",
        "Hand over with reason too_many_errors.",
    ),
    "MALFORMED_REQUEST": (
        "The request was malformed.",
        "Ask the caller to repeat the details.",
    ),
    "AUTH_SERVICE_UNAVAILABLE": (
        "The login service is unavailable.",
        "Hand over with reason system_unavailable.",
    ),
    "INSUFFICIENT_FUNDS": (
        "The payment method has insufficient funds.",
        "Tell the caller and ask for another payment method.",
    ),
    "REFUND_THRESHOLD_EXCEEDED": (
        "The amount is above the self-serve limit.",
        "Hand over with reason refund_threshold_exceeded.",
    ),
    "TECHNICIAN_EN_ROUTE": (
        "The technician is already on the way.",
        "Explain it can't be cancelled and offer to add a note.",
    ),
    "NO_AVAILABILITY": (
        "No slots are available in that window.",
        "Offer a text when a slot opens.",
    ),
    "STEP_UP_REQUIRED": (
        "This change needs an extra verification step.",
        "Send an email code with send_login_code channel=email.",
    ),
    "NO_PAYMENT_FOUND": (
        "No posted payment covers the past-due amount.",
        "Offer to take a payment or set up an arrangement.",
    ),
    "CONFIRMATION_REQUIRED": (
        "The caller must confirm before this is applied.",
        "Read back the details and ask the caller to confirm.",
    ),
    "TV_SUB_TYPE_REQUIRED": (
        "The TV service type is needed first.",
        "Ask if the TV is streaming, satellite or streaming only.",
    ),
    "CARD_EXPIRED": (
        "The card on file has expired.",
        "Tell the caller and ask for another payment method.",
    ),
    "NOT_SUSPENDED": (
        "The service is not suspended.",
        "Tell the caller the service is active.",
    ),
    "DELIVERY_FAILED": (
        "The text message could not be delivered.",
        "Apologize and offer a transfer to a representative.",
    ),
}

class _StatusStr(str):  # pragma: no cover
    """String status value that compares equal case-insensitively ('ok' == 'OK')."""

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.lower() == other.lower()
        return super().__eq__(other)

    def __ne__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.lower() != other.lower()
        return super().__ne__(other)

    def __hash__(self) -> int:
        return super().__hash__()

ERROR_STATUS = _StatusStr("error")  # pragma: no cover

def tracking_id(tool: str, *inputs: object) -> str:  # pragma: no cover
    """Return a reference number built from the tool name and its inputs.

    The same inputs always give the same number, so a retried call can't
    create a second record under a new number.
    """
    raw = "|".join([tool, *(str(value).strip().lower() for value in inputs)])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return "R" + str(int(digest[:8], 16) % 1_000_000).zfill(6)

def error_reply(  # pragma: no cover
    code: str,
    message: str = "",
    agent_action: str = "",
    reference: str | None = None,
    data: dict[str, Any] | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    """Build an error reply; `code` must be one of ERROR_CODES."""
    if code not in ERROR_CODES:
        raise ValueError(f"unknown error code {code!r}; add it to ERROR_CODES first")
    default_msg, default_action = ERROR_CODE_DEFAULTS.get(
        code,
        ("The request could not be completed.", "Explain the issue to the caller."),
    )
    msg = message or default_msg
    action = agent_action or default_action
    if reference is None:
        reference = tracking_id("error", code, msg)
    payload = dict(data or {})
    reply: dict[str, Any] = {
        "status": ERROR_STATUS,
        "error": code,
        "data": payload,
        "error_message": msg,
        "agent_action": action,
        "tracking_id": reference,
    }
    if language is not None:
        reply["active_language"] = str(language)
    if "lockout_triggered" in payload:
        reply["lockout_triggered"] = payload["lockout_triggered"]
    for key in (
        "logged_in",
        "handoff_message",
        "spoken_message",
        "spoken_summary",
        "handoff_status",
        "action_fulfilled",
        "task_completed",
        "user_goal_fulfilled",
    ):
        if key in payload:
            reply[key] = payload[key]
    return reply

def _locked_reply(state: dict[str, Any], reference: str, lang: str) -> dict[str, Any]:  # pragma: no cover
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

def _record_failure(state: dict[str, Any], reference: str, lang: str, kind: str) -> dict[str, Any]:  # pragma: no cover
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

def check_mock_error(state: dict[str, Any], lang: str = "en-US", tool_name: str = "tool") -> dict[str, Any] | None:  # pragma: no cover
    """Fault injection: `mock_error` set in session state makes every tool return a system error."""
    if str(state.get("mock_error") or "").strip():
        ref = tracking_id(tool_name, "mock_error", state.get("account_id", ""))
        state["last_tracking_id"] = ref
        return error_reply(
            "SYSTEM_UNAVAILABLE",
            agent_action="Hand over with reason system_unavailable.",
            reference=ref,
            language=lang,
        )
    return None

ACCOUNTS: tuple[dict[str, Any], ...] = (  # pragma: no cover
    {
        "account_id": "A1001",
        "phone": "2025550186",
        "first_name": "Morgan",
        "email": "m.okafor@mailprovider.example",
        "status": "active",
        "preferred_language": "en-US",
        "card_last4": "7742",
        "card_brand": "Visa",
        "customer_type": "Existing",
        "postal_code": "K2P 1L4",
        "service_address_last_line": "Ottawa, ON K2P 1L4",
        "lines_of_business": ["mobility", "internet", "tv", "homephone"],
        "business_flag": False,
    },
    {
        "account_id": "A1002",
        "phone": "2025550198",
        "first_name": "Taylor",
        "email": "taylor.r@mailprovider.example",
        "status": "active",
        "preferred_language": "fr-CA",
        "card_last4": "8853",
        "card_brand": "Mastercard",
        "customer_type": "Existing",
        "postal_code": "K1A 0B1",
        "service_address_last_line": "Ottawa, ON K1A 0B1",
        "lines_of_business": ["mobility", "internet"],
        "business_flag": False,
    },
)

def ensure_account(state: dict[str, Any]) -> str:  # pragma: no cover
    """Make sure an account is active (login tools fill the default; DESIGN_RULES rule 21)."""
    if not state.get("account_id"):
        state["account_id"] = ACCOUNTS[0]["account_id"]
        state["phone_last4"] = ACCOUNTS[0]["phone"][-4:]
        state["identification_status"] = "Pass"
    return str(state["account_id"])

def get_state(  # pragma: no cover
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the session state dict. A missing state gets a fresh dict, never a shared one."""
    if state is not None:
        return state
    if session_state is not None:
        return session_state
    return {}

OK_STATUS = _StatusStr("ok")  # pragma: no cover

def ok_reply(  # pragma: no cover
    data: dict[str, Any] | None = None,
    reference: str | None = None,
    language: str | None = None,
    spoken_summary: str | None = None,
) -> dict[str, Any]:
    """Build a success reply."""
    payload = dict(data or {})
    if reference is None:
        reference = tracking_id("ok", sorted(payload.keys()))
    reply: dict[str, Any] = {
        "status": OK_STATUS,
        "data": payload,
        "error_message": "",
        "tracking_id": reference,
    }
    if language is not None:
        reply["active_language"] = str(language)
    if spoken_summary is not None:
        reply["spoken_summary"] = str(spoken_summary)
    for key in (
        "logged_in",
        "handoff_message",
        "spoken_message",
        "spoken_summary",
        "handoff_status",
        "action_fulfilled",
        "task_completed",
        "user_goal_fulfilled",
    ):
        if key in payload:
            reply[key] = payload[key]
    return reply

def resolve_locale(language: str | None) -> str:  # pragma: no cover
    """Normalize a language tag or prefix to a supported locale (en-US or fr-CA)."""
    low = str(language or "").strip().lower().replace("_", "-")
    if low.startswith("fr"):
        return "fr-CA"
    return "en-US"

resolve_copy_locale = resolve_locale  # pragma: no cover

def session_language(state: dict[str, Any] | None, language: Any = "") -> str:  # pragma: no cover
    """Resolve the call language with an asymmetric lock (DESIGN_RULES rule 41).

    A non-English language locks the call; a later en-US or empty value from the
    model never downgrades it. An empty state takes the model's language.
    """
    current = ""
    if isinstance(state, dict):
        existing = state.get("language")
        if existing and str(existing).strip():
            current = resolve_copy_locale(str(existing))
    arg_lang = resolve_copy_locale(str(language)) if language and str(language).strip() else ""
    if current and current != "en-US":
        return current
    if arg_lang and arg_lang != "en-US":
        if isinstance(state, dict):
            state["language"] = arg_lang
        return arg_lang
    if current:
        return current
    if arg_lang and isinstance(state, dict):
        state["language"] = arg_lang
        return arg_lang
    return "en-US"

MAX_VALIDATION_ERRORS = 3  # pragma: no cover

def validation_error(  # pragma: no cover
    state: dict[str, Any],
    message: str,
    agent_action: str,
    reference: str,
    lang: str,
    code: str = "INVALID_INPUT",
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """BR-TV-010: count validation errors; the third on a call ends in TOO_MANY_ERRORS."""
    count = read_count(state, "global_err_count") + 1
    state["global_err_count"] = count
    if count >= MAX_VALIDATION_ERRORS:
        return error_reply(
            "TOO_MANY_ERRORS",
            "Too many invalid entries on this call.",
            "Hand over with reason too_many_errors.",
            reference,
            language=lang,
            data={"global_err_count": count},
        )
    payload = dict(data or {})
    payload["global_err_count"] = count
    return error_reply(code, message, agent_action, reference, language=lang, data=payload)

def check_secret_pin_impl(  # pragma: no cover
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
    reference = tracking_id("check_secret_pin", account_id, normalize_code(pin))
    state["last_tracking_id"] = reference
    if state.get("code_purpose") == "step_up" and state.get("auth_status") == "pass":
        # A step-up code is pending: digits given here are the emailed code.
        return check_login_code_impl(pin, state=state, language=lang)
    if state.get("auth_status") == "pass":
        state["logged_in"] = True
        return ok_reply({"verified": True, "logged_in": True}, reference, language=lang)
    if state.get("auth_status") == "locked" or _failures(state) >= MAX_LOGIN_ATTEMPTS:
        return _locked_reply(state, reference, lang)
    digits = normalize_code(pin) or normalize_code(state.get("dtmf_digits"))
    if OTP_RE.fullmatch(digits) and state.get("login_code_sent"):
        # The caller read back the 6-digit texted code.
        return check_login_code_impl(digits, state=state, language=lang)
    if not PIN_RE.fullmatch(digits):
        return validation_error(state, "A PIN has 4 digits.", "Ask the caller to key in their 4-digit PIN again.", reference, lang)
    if not _credential_ok(state, digits, "pin"):
        return _record_failure(state, reference, lang, "pin")
    state["auth_status"] = "pass"
    state["logged_in"] = True
    state["auth_failure_count"] = 0
    state["login_attempts"] = 0
    return ok_reply({"verified": True, "logged_in": True}, reference, language=lang)

def check_login_code_impl(  # pragma: no cover
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
    reference = tracking_id("check_login_code", account_id, normalize_code(code))
    state["last_tracking_id"] = reference
    step_up = state.get("code_purpose") == "step_up" and state.get("auth_status") == "pass"
    if state.get("auth_status") == "pass" and not step_up:
        state["logged_in"] = True
        return ok_reply({"verified": True, "logged_in": True}, reference, language=lang)
    if state.get("auth_status") == "locked" or _failures(state) >= MAX_LOGIN_ATTEMPTS:
        return _locked_reply(state, reference, lang)
    digits = normalize_code(code) or normalize_code(state.get("dtmf_digits"))
    if PIN_RE.fullmatch(digits) and not step_up:
        # The caller gave their 4-digit PIN instead of the texted code.
        return check_secret_pin_impl(digits, state=state, language=lang)
    if not OTP_RE.fullmatch(digits):
        return validation_error(state, "A verification code has 6 digits.", "Ask the caller to say or key in the 6-digit code again.", reference, lang)
    if not _credential_ok(state, digits, "code"):
        return _record_failure(state, reference, lang, "code")
    state["auth_failure_count"] = 0
    state["login_attempts"] = 0
    if step_up:
        state["step_up_verified"] = True
        state["code_purpose"] = "login"
        return ok_reply({"verified": True, "step_up_verified": True, "logged_in": True}, reference, language=lang)
    state["auth_status"] = "pass"
    state["logged_in"] = True
    return ok_reply({"verified": True, "logged_in": True}, reference, language=lang)
# --- END GENERATED SHARED BUNDLE ---
