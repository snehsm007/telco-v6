from typing import Any



def lookup_account(
    phone_or_account: str | int | float,
    language: str = "",
) -> dict[str, Any]:
    """Finds the caller's account from the phone number or account number they gave (or
      their email address when they have no number) and remembers it for the call. Call
      it as soon as the caller gives a number. Returns business_flag and service_status;
      a blocked number returns error PERMISSION_DENIED.

    Args:
      phone_or_account: The phone number or account number exactly as the caller said or
        keyed it, as a quoted string, or the email address they gave.
      language: Active language code (en-US or fr-CA).

    Returns:
      status, data (identification_status, account_id_last4, phone_last4, business_flag,
        customer_type, lines_of_business, region, service_status), error_message,
        tracking_id. Errors add error (NOT_FOUND, PERMISSION_DENIED, TOO_MANY_ERRORS)
        and agent_action.
    """
    ctx = globals().get("context")
    state = getattr(ctx, "state", None) if ctx is not None else None
    if state is None and isinstance(ctx, dict):
        state = ctx
    return lookup_account_impl(
        phone_or_account=phone_or_account,
        language=language,
        state=state,
    )


# --- BEGIN GENERATED SHARED BUNDLE (edit lib/, then run `make bundle`) ---
# uses: from lib.services import lookup_account_impl
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
import contextvars
import hashlib
import json
import re

BLOCKED_CALLER_NUMBERS: frozenset[str] = frozenset({"9005550199"})  # pragma: no cover

CALLER_ID_REQUESTS: frozenset[str] = frozenset({"", "clid"})  # pragma: no cover

NO_ACCOUNT_ACTION = "If the caller already gave a 4-digit PIN, call check_secret_pin now; else say spoken_message."  # pragma: no cover

ACCOUNT_NUMBER_RE = re.compile(r"^[0-9](?:[\s\-]?[0-9]){5,14}$")  # pragma: no cover

ACCOUNT_REFERENCE_RE = re.compile(  # pragma: no cover
    r"^(?=(?:[^0-9]*[0-9]){4})(?=.*[A-Za-z])[A-Za-z0-9](?:[A-Za-z0-9]|[\s\-](?=[A-Za-z0-9])){3,24}$"
)

ALL_DIGITS_RE = re.compile(r"^[0-9]+$")  # pragma: no cover

PHONE_INTL_RE = re.compile(r"^(?:\+|00)[1-9](?:[\s.\-]?[0-9]){9,14}$")  # pragma: no cover

PHONE_LOCAL_PAIRS_RE = re.compile(r"^0[1-9](?:[\s.\-]?[0-9]{2}){4}$")  # pragma: no cover

PHONE_NANP_RE = re.compile(r"^(?:\+?1[\s.\-]?)?\(?[0-9]{3}\)?[\s.\-]?[0-9]{3}[\s.\-]?[0-9]{4}$")  # pragma: no cover

SPOKEN_DIGIT_SEPARATORS_RE = re.compile(r"[\s,.\-()]+")  # pragma: no cover

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

def classify_identifier(raw: Any) -> tuple[str, str]:  # pragma: no cover
    """Match a caller identifier against the format patterns.

    Phone speech-to-text writes numbers as "888,777,666" or "5 1 4 5 5 5 0 1 9 9";
    when only separators (spaces, commas, dots, dashes, brackets) sit between the
    digits, the digit string itself is classified by length with the same rules.
    Returns (kind, digits): kind is phone, intl_phone, account_number,
    account_reference, or "" when no pattern matches.
    """
    text = re.sub(r"\.0+$", "", str(raw or "").strip())
    digits = normalize_code(text)
    compact = SPOKEN_DIGIT_SEPARATORS_RE.sub("", text)
    if compact and ALL_DIGITS_RE.fullmatch(compact) and not compact.startswith("00") and not PHONE_NANP_RE.fullmatch(text):
        if len(compact) == 11 and compact.startswith("1"):
            return "phone", compact[1:]
        if len(compact) == 10 and not compact.startswith("0"):
            return "phone", compact
        if PHONE_LOCAL_PAIRS_RE.fullmatch(text):
            return "phone", compact
        if ACCOUNT_NUMBER_RE.fullmatch(compact):
            return "account_number", compact
    if PHONE_NANP_RE.fullmatch(text):
        return "phone", digits[-10:]
    if PHONE_LOCAL_PAIRS_RE.fullmatch(text):
        return "phone", digits
    if PHONE_INTL_RE.fullmatch(text):
        return "intl_phone", digits
    if ACCOUNT_NUMBER_RE.fullmatch(text):
        return "account_number", digits
    if ACCOUNT_REFERENCE_RE.fullmatch(text):
        return "account_reference", digits
    return "", digits

DUMMY_NUMBERS: frozenset[str] = frozenset({"1234567890", "0123456789", "9876543210"})  # pragma: no cover

def is_weak_code(digits: str) -> bool:  # pragma: no cover
    """A code made of one repeated digit (e.g. all sevens) is never a valid credential."""
    return bool(digits) and len(set(digits)) == 1

def is_plausible_phone(digits: str) -> bool:  # pragma: no cover
    """A 10-digit number that isn't one repeated digit or an obvious dummy run (Postel: accept generously)."""
    if len(digits) != 10 or not digits.isdigit():
        return False
    return not is_weak_code(digits) and digits not in DUMMY_NUMBERS

def _caller_id_phone(state: dict[str, Any]) -> str:  # pragma: no cover
    """The caller ID (`clid`, prd.md §5) when it is a valid 10-digit phone number, else ""."""
    kind, digits = classify_identifier(state.get("clid"))
    return digits if kind == "phone" and is_plausible_phone(digits) else ""

DEFAULT_REGION = "Region-C"  # pragma: no cover

REGION_BY_POSTAL_LETTER: dict[str, str] = {  # pragma: no cover
    **{letter: "Region-A" for letter in "GHJ"},
    **{letter: "Region-B" for letter in "KLMNP"},
}

def _region_for_postal(postal_code: str) -> str:  # pragma: no cover
    """Region class from a Canadian postal code's first letter (DESIGN_RULES rule 40)."""
    first = str(postal_code or "").strip()[:1].upper()
    return REGION_BY_POSTAL_LETTER.get(first, DEFAULT_REGION)

MOCK_ERROR_OFF: frozenset[str] = frozenset({"false", "none", "0", "off", "no", "null"})  # pragma: no cover

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

ERROR_MESSAGES_FR: dict[str, str] = {  # pragma: no cover
    "INVALID_INPUT": "Les renseignements fournis ne sont pas valides.",
    "NOT_FOUND": "Aucun dossier correspondant n'a été trouvé.",
    "NOT_IDENTIFIED": "Le compte de l'appelant n'a pas encore été trouvé.",
    "NOT_LOGGED_IN": "L'identité de l'appelant n'a pas encore été vérifiée.",
    "CODE_NOT_SENT": "Aucun code de connexion n'a été envoyé pendant cet appel.",
    "WRONG_CODE": "Le code ne correspond pas.",
    "WRONG_PIN": "Le NIP ne correspond pas.",
    "TOO_MANY_ATTEMPTS": "Trop de codes erronés pendant cet appel.",
    "LOCKED_OUT": "L'accès est verrouillé après trop de tentatives infructueuses.",
    "CARD_DECLINED": "La carte a été refusée.",
    "PAYMENT_DECLINED": "Le mode de paiement a été refusé.",
    "INELIGIBLE": "Le compte n'est pas admissible à cette demande.",
    "NOT_ELIGIBLE": "Le compte n'est pas admissible à cette option.",
    "ALREADY_PROCESSED": "Cette demande a déjà été traitée.",
    "ALREADY_APPLIED": "Ce crédit ou cet ajustement a déjà été appliqué.",
    "ALREADY_ENROLLED": "Le compte est déjà inscrit à cette fonction.",
    "OUT_OF_WINDOW": "La demande est hors du délai permis.",
    "OUTAGE_ACTIVE": "Une panne de service touche actuellement ce secteur.",
    "LIMIT_EXCEEDED": "Le montant ou le nombre demandé dépasse la limite permise.",
    "INTERNAL_ERROR": "Une erreur interne est survenue pendant le traitement de la demande.",
    "SERVICE_UNAVAILABLE": "Le service est actuellement indisponible.",
    "SYSTEM_UNAVAILABLE": "Le service est temporairement indisponible.",
    "SYSTEM_DOWN": "Le service est temporairement indisponible.",
    "PERMISSION_DENIED": "Accès refusé.",
    "TOO_MANY_ERRORS": "Trop d'entrées non valides pendant cet appel.",
    "MALFORMED_REQUEST": "La demande est mal formée.",
    "AUTH_SERVICE_UNAVAILABLE": "Le service de connexion est indisponible.",
    "INSUFFICIENT_FUNDS": "Le mode de paiement n'a pas les fonds suffisants.",
    "REFUND_THRESHOLD_EXCEEDED": "Le montant dépasse la limite libre-service.",
    "TECHNICIAN_EN_ROUTE": "Le technicien est déjà en route.",
    "NO_AVAILABILITY": "Aucune plage horaire n'est disponible dans cette période.",
    "STEP_UP_REQUIRED": "Cette modification exige une étape de vérification supplémentaire.",
    "NO_PAYMENT_FOUND": "Aucun paiement enregistré ne couvre le montant en souffrance.",
    "CONFIRMATION_REQUIRED": "L'appelant doit confirmer avant que ce soit appliqué.",
    "TV_SUB_TYPE_REQUIRED": "Le type de service télé est requis d'abord.",
    "CARD_EXPIRED": "La carte au dossier est expirée.",
    "NOT_SUSPENDED": "Le service n'est pas suspendu.",
    "DELIVERY_FAILED": "Le texto n'a pas pu être livré.",
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

_MOCK_MODE_ACTIVE: contextvars.ContextVar[bool] = contextvars.ContextVar("mock_mode_active", default=False)  # pragma: no cover

def _stamp_mock(reply: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover
    """Add the mock_mode marker to a reply and its data when the call runs in mock mode."""
    if _MOCK_MODE_ACTIVE.get():
        reply["mock_mode"] = True
        if isinstance(reply.get("data"), dict):
            reply["data"]["mock_mode"] = True
    return reply

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
    if str(language or "").strip().lower().startswith("fr"):
        # fr-CA call: tools pass English detail, so the French default wins.
        msg = ERROR_MESSAGES_FR.get(code) or msg
    payload = dict(data or {})
    reply: dict[str, Any] = {
        "status": ERROR_STATUS,
        "error": code,
        "data": payload,
        "error_message": msg,
        "message": msg,
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
    return _stamp_mock(reply)

def check_mock_error(state: dict[str, Any], lang: str = "en-US", tool_name: str = "tool") -> dict[str, Any] | None:  # pragma: no cover
    """Fault injection: `mock_error` set in session state makes every tool return a system error.

    "false", "none", "0", "off", "no" and "null" mean no fault, like an empty value.
    """
    if str(state.get("mock_error") or "").strip():
        if str(state.get("mock_error")).strip().lower() in MOCK_ERROR_OFF:
            return None
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

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")  # pragma: no cover

def _phone_from_digits(digits: str) -> str:  # pragma: no cover
    """A deterministic 10-digit phone ending in the caller's own digits.

    Synthetic records from an account number or reference get this phone, so the
    texted-code destination ("ending in ...") echoes digits the caller gave instead
    of the default account's phone.
    """
    if len(digits) >= 10:
        return digits[-10:]
    return ACCOUNTS[0]["phone"][: 10 - len(digits)] + digits

def _synthetic_account(account_number: str, phone: str) -> dict[str, Any]:  # pragma: no cover
    """A record for a well-formed number this world doesn't know (fact-less simulated callers)."""
    base = dict(ACCOUNTS[0])
    base["account_id"] = "A" + account_number[-6:]
    base["phone"] = phone
    base["first_name"] = ""
    return base

def find_account(identifier: Any) -> dict[str, Any] | None:  # pragma: no cover
    """Find an account by phone number, account number, account reference or email.

    The identifier must match one of the format patterns above. An email address
    (EMAIL_RE) finds the account with that email, else the default account
    (fact-less callers without a number give their email instead). Within those
    formats this accepts generously (DESIGN_RULES rule 43): fact-less callers
    invent numbers, so a well-formed unknown identifier resolves to a synthetic
    record. One repeated digit and dummy runs are never accounts.
    """
    raw_str = re.sub(r"\.0+$", "", str(identifier or "").strip())
    if not raw_str:
        return None
    raw = raw_str.upper()
    digits = normalize_code(raw_str)
    for record in ACCOUNTS:
        if raw == record["account_id"] or (digits and digits == record["phone"] and not any(c.isalpha() for c in raw_str)):
            return dict(record)
    if EMAIL_RE.fullmatch(raw_str):
        by_email = [r for r in ACCOUNTS if str(r.get("email", "")).lower() == raw_str.lower()]
        return dict(by_email[0] if by_email else ACCOUNTS[0])
    kind, digits = classify_identifier(raw_str)
    if not kind or is_weak_code(digits) or digits in DUMMY_NUMBERS:
        return None
    if kind == "phone":
        return _synthetic_account(digits, digits) if is_plausible_phone(digits) else None
    if kind == "intl_phone":
        return _synthetic_account(digits, digits[-10:])
    return _synthetic_account(digits, _phone_from_digits(digits))

FIXTURE_DEFAULTS: dict[str, str] = {  # pragma: no cover
    "fx_pin_on_file": "",
    "fx_otp_on_file": "",
    "fx_card_on_file_status": "valid",
    # The default account is past due and suspended for non-payment. Only the billing
    # tools report it (lookup_account does not, before login), and their spoken lines
    # never raise it unprompted, so unrelated journeys are unaffected (docs/tdd.md §5).
    "fx_service_status": "suspended_nonpayment",
    # A payment covering the past-due amount posted yesterday but not applied yet:
    # it sits in the payment processor's queue, so get_billing_summary does not list it
    # and only verify_payment_and_restore (the caller says they already paid) finds it.
    "fx_recent_payment": "posted_yesterday",
    "fx_business_account": "false",
    "fx_outage_status": "",
    # Default visit: technician on the way but running late (reads as both "en route"
    # and "delayed"); it can be moved to another day, not cancelled (en route).
    "fx_technician_status": "en_route_delayed",
    "fx_duplicate_payment": "true",  # the ledger holds a duplicate payment; refunded only when a caller claims it
    "fx_extra_bill_line": "",
    "fx_device_warranty": "in_warranty",
    # "" = no MFA record for a synthetic caller: the account is in the state opposite
    # to the caller's request (manage_mfa), then fixed for the rest of the call.
    "fx_mfa_enabled": "",
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

def fixture_flag(state: dict[str, Any] | None, name: str) -> bool:  # pragma: no cover
    """Read a true/false fixture."""
    return fixture(state, name) in ("true", "1", "yes")

def mock_mode_on(state: dict[str, Any] | None) -> bool:  # pragma: no cover
    """PRD §17 eval-harness flag (scenario variableOverrides mock_mode="True").

    Every tool here already runs on the fake backend in lib/fakes.py, so mock mode
    changes no tool outcome; fixtures (fx_*) still apply and login is never mocked.
    """
    return isinstance(state, dict) and str(state.get("mock_mode") or "").strip().lower() == "true"

def set_mock_mode_active(active: bool) -> None:  # pragma: no cover
    """Mark replies built from now on in this call as mock_mode payloads (PRD §17)."""
    _MOCK_MODE_ACTIVE.set(bool(active))

def get_state(  # pragma: no cover
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the session state dict. A missing state gets a fresh dict, never a shared one.

    Also switches the PRD §17 mock_mode marker on or off for the replies of this call.
    """
    resolved = state if state is not None else (session_state if session_state is not None else {})
    set_mock_mode_active(mock_mode_on(resolved))
    return resolved

_LETTER_WORD_RE = re.compile(r"(?:^|[\s,.])[^\W\d_](?:[^\W\d_]|['\-](?=[^\W\d_]))+(?=$|[\s,.])")  # pragma: no cover

def is_name_or_address(raw: Any) -> bool:  # pragma: no cover
    """True when the caller gave words (a name or street address), not a number or email.

    Malformed numbers ("ACC-12", "555-01") and emails stay validation errors.
    """
    text = str(raw or "").strip()
    if not text or "@" in text or classify_identifier(text)[0]:
        return False
    return bool(_LETTER_WORD_RE.search(text))

def normalize_identifier(raw: object) -> dict[str, str]:  # pragma: no cover
    """Postel normalizer for caller-provided identifiers (DESIGN_RULES rule 43).

    10 digits or +1+10 = phone; +/00 + 10-15 digits = international_phone;
    4-9 digits = account; letters+digits = reference; anything else = unknown.
    """
    s = str(raw or "").strip()
    if not s:
        return {"kind": "unknown", "value": ""}
    compact = re.sub(r"[\s\-\(\)\.]+", "", s)
    if compact.startswith("+1") and len(compact) == 12 and compact[2:].isdigit():
        return {"kind": "phone", "value": compact[2:]}
    if compact.startswith("1") and len(compact) == 11 and compact[1:].isdigit():
        return {"kind": "phone", "value": compact[1:]}
    if compact.isdigit() and len(compact) == 10:
        return {"kind": "phone", "value": compact}
    if compact.startswith("+"):
        digits = compact[1:]
        if digits.isdigit() and 10 <= len(digits) <= 15:
            return {"kind": "international_phone", "value": "+" + digits}
    if compact.startswith("00"):
        digits = compact[2:]
        if digits.isdigit() and 10 <= len(digits) <= 15:
            return {"kind": "international_phone", "value": "+" + digits}
    ref_match1 = re.fullmatch(r"([A-Za-z]{1,4})-?(\d{4,8})", s)
    if ref_match1:
        prefix, digits = ref_match1.groups()
        return {"kind": "reference", "value": f"{prefix.upper()}-{digits}"}
    ref_match2 = re.fullmatch(r"(\d{4,9})-?([A-Za-z]{1,4})", s)
    if ref_match2:
        digits, suffix = ref_match2.groups()
        return {"kind": "reference", "value": f"{digits}-{suffix.upper()}"}
    if compact.isdigit() and 4 <= len(compact) <= 9:
        return {"kind": "account", "value": compact}
    return {"kind": "unknown", "value": s}

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
    return _stamp_mock(reply)

def only_digits(text: Any) -> str:  # pragma: no cover
    """Keep the digits of what the caller said ("(202) 555-0143" -> "2025550143")."""
    return normalize_code(text)

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
    "transfer_to_specialist": {
        "en-US": "I'll connect you to a billing specialist now — they'll have everything we've already discussed.",
        "fr-CA": "Je vais vous mettre en relation avec un spécialiste de la facturation — il aura tout ce dont nous avons déjà discuté.",
    },
    "refund_over_limit": {
        "en-US": "That amount is above our $[limit] self-serve limit, so it needs a specialist's approval.",
        "fr-CA": "Ce montant dépasse notre limite libre-service de [limit] $, il doit donc être approuvé par un spécialiste.",
    },
    "otp_callback_confirm": {
        "en-US": "I'll send a 6-digit code to the number ending in [last4]. Ready?",
        "fr-CA": "Je vais envoyer un code à 6 chiffres au numéro se terminant par [last4]. Êtes-vous prêt?",
    },
    "pin_alternative": {
        "en-US": "Or, if you prefer, you can use your 4-digit PIN instead.",
        "fr-CA": "Ou, si vous préférez, vous pouvez plutôt utiliser votre NIP à 4 chiffres.",
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

def spoken_line(key: str, language: str | None = "en-US", **slots: object) -> str:  # pragma: no cover
    """Return the fixed spoken line for `key` and `language`, filling any `[slot]` placeholders."""
    locale = resolve_locale(language)
    table = SPOKEN_LINES.get(key, {})
    template = table.get(locale) or table.get("en-US") or ""
    for slot_name, slot_val in slots.items():
        template = template.replace(f"[{slot_name}]", str(slot_val))
    return template

MAX_VALIDATION_ERRORS = 3  # pragma: no cover

def read_count(state: dict[str, Any] | None, key: str) -> int:  # pragma: no cover
    """Read a whole-number variable; the platform hands them to tools as decimals (5 -> 5.0)."""
    if not isinstance(state, dict):
        return 0
    try:
        return int(float(state.get(key) or 0))
    except (TypeError, ValueError):
        return 0

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

def lookup_account_impl(  # pragma: no cover
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
    raw = re.sub(r"\.0+$", "", raw)
    used_caller_id = False
    if raw.lower() in CALLER_ID_REQUESTS:
        # No number given ("use the number I'm calling from"): try the caller ID once.
        raw = _caller_id_phone(state)
        used_caller_id = bool(raw)
    reference = tracking_id("lookup_account", raw)
    if not raw:
        # No number and no usable caller ID: not a wrong entry, so no strike (BR-TV-010).
        state["last_tracking_id"] = reference
        return error_reply(
            "INVALID_INPUT",
            "No phone number or account number was given, and no caller ID is available.",
            NO_ACCOUNT_ACTION,
            reference,
            language=lang,
            data={
                "spoken_message": spoken_line("account_lookup_options", lang),
                "pin_length": 4,
                "counted": False,
                "caller_id_available": False,
            },
        )
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
    ident = normalize_identifier(raw)
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
        "phone_last4": account["phone"][-4:],
        "caller_provided_phone_last4": state["caller_provided_phone_last4"],
        "business_flag": business,
        "customer_type": state["customer_type"],
        "lines_of_business": list(account.get("lines_of_business", [])),
        "region": state["region"],
        "used_caller_id": used_caller_id,
    }
    reply = ok_reply(data, reference, language=lang)
    if business:
        reply["agent_action"] = "Business account: hand over with reason business_handoff."
    elif state.get("auth_status") == "locked":
        reply["agent_action"] = "Login is locked on this call: hand over with reason auth_failure_handoff."
    return reply
# --- END GENERATED SHARED BUNDLE ---
