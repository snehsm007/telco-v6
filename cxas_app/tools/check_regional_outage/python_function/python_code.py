from typing import Any



def check_regional_outage(
    postal_code: str | int | float = "",
    lob: str = "",
    language: str = "",
) -> dict[str, Any]:
    """Checks for an active service outage in an area by Canadian postal code or US ZIP
      code. Needs no login. Empty postal_code uses the service address of the account
      found on this call. Call it before any troubleshooting when the caller reports a
      service down or asks about an outage.

    Args:
      postal_code: Postal code as the caller said it (A1A 1A1, spaces optional) or a
        5-digit ZIP; empty = address on file.
      lob: Service with the problem: mobility, internet, tv, homephone or smarthome;
        empty = any.
      language: Active language code (en-US or fr-CA).

    Returns:
      status, data (region, outage_active, affected_services, restoration_eta_display,
        outage_id, next_step), error_message, tracking_id. Errors add error
        (INVALID_INPUT, TOO_MANY_ERRORS) and agent_action.
    """
    ctx = globals().get("context")
    state = getattr(ctx, "state", None) if ctx is not None else None
    if state is None and isinstance(ctx, dict):
        state = ctx
    return check_regional_outage_impl(
        postal_code=postal_code,
        lob=lob,
        language=language,
        state=state,
    )


# --- BEGIN GENERATED SHARED BUNDLE (edit lib/, then run `make bundle`) ---
# uses: from lib.tech import check_regional_outage_impl
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
import contextvars
import hashlib
import re
import unicodedata

_MONTREAL_CENTRE_WEST_OUTAGE = {"outage_id": "OUT-H3-27", "services": ["internet", "tv"], "eta_hours": 4}  # pragma: no cover

_QUEBEC_CITY_CORE_OUTAGE = {"outage_id": "OUT-G1-27", "services": ["internet", "tv"], "eta_hours": 4}  # pragma: no cover

ACTIVE_OUTAGES_BY_DISTRICT: dict[str, dict[str, Any]] = {  # pragma: no cover
    **{fsa: _QUEBEC_CITY_CORE_OUTAGE for fsa in ("G1K", "G1R", "G1S")},
    **{fsa: _MONTREAL_CENTRE_WEST_OUTAGE for fsa in ("H3G", "H3H", "H3Y", "H3Z")},
}

FIXTURE_OUTAGE = {"outage_id": "OUT-LOCAL-09", "services": ["internet", "tv"], "eta_hours": 3}  # pragma: no cover

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

def _tech_area_outage(state: dict[str, Any], district: str) -> dict[str, Any] | None:  # pragma: no cover
    """The outage affecting a postal district: fixture override first, else the district table."""
    status = fixture(state, "fx_outage_status")
    if status == "active":
        return dict(FIXTURE_OUTAGE)
    if status == "none":
        return None
    found = ACTIVE_OUTAGES_BY_DISTRICT.get(district)
    return dict(found) if found else None

OUTAGE_DISTRICT_LENGTH = 3  # pragma: no cover

def _tech_district(kind: str, code: str) -> str:  # pragma: no cover
    """Postal district (FSA: the first three characters) of a Canadian postal code; "" for a ZIP."""
    return code[:OUTAGE_DISTRICT_LENGTH] if kind == "postal" else ""

def resolve_locale(language: str | None) -> str:  # pragma: no cover
    """Normalize a language tag or prefix to a supported locale (en-US or fr-CA)."""
    low = str(language or "").strip().lower().replace("_", "-")
    if low.startswith("fr"):
        return "fr-CA"
    return "en-US"

resolve_copy_locale = resolve_locale  # pragma: no cover

def _tech_hours(hours: int, lang: str) -> str:  # pragma: no cover
    if resolve_copy_locale(lang) == "fr-CA":
        return f"environ {hours} heure" + ("s" if hours > 1 else "")
    return f"about {hours} hour" + ("s" if hours > 1 else "")

_TECH_LOB_ALIASES: dict[str, str] = {  # pragma: no cover
    "mobile": "mobility", "mobility": "mobility", "cell": "mobility", "cellular": "mobility",
    "wireless": "mobility", "phone": "mobility", "mobilite": "mobility", "mobilité": "mobility",
    "cellulaire": "mobility", "portable": "mobility",
    "internet": "internet", "wifi": "internet", "wi-fi": "internet", "wi_fi": "internet",
    "home_internet": "internet", "broadband": "internet", "fibre": "internet",
    "tv": "tv", "television": "tv", "télévision": "tv", "tele": "tv", "télé": "tv",
    "homephone": "homephone", "home_phone": "homephone", "landline": "homephone",
    "home phone": "homephone", "telephone_residentiel": "homephone",
    "smarthome": "smarthome", "smart_home": "smarthome", "smart home": "smarthome",
}

_TECH_LOB_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (  # pragma: no cover
    ("homephone", ("home phone", "landline", "dial tone", "tonalité", "ligne fixe", "téléphone résidentiel")),
    ("tv", ("tv", "télé", "television", "télévision", "receiver", "récepteur", "channel", "chaîne", "satellite")),
    ("smarthome", ("smart home", "camera", "caméra", "sensor", "capteur", "alarm", "maison intelligente")),
    ("mobility", ("cell", "mobile", "portable", "cellulaire", "sim", "5g", "lte", "données mobiles", "mobile data")),
    ("internet", ("internet", "wifi", "wi-fi", "modem", "router", "routeur")),
)

def _tech_has(text: str, words: tuple[str, ...]) -> bool:  # pragma: no cover
    """True when any keyword starts a word in text (prefix match, accents kept)."""
    return any(re.search(r"(?<![\w])" + re.escape(w), text) for w in words)

def _tech_lob(raw: Any, symptom: str = "") -> str:  # pragma: no cover
    """Normalize a line of business; infer it from the symptom when missing."""
    clean = str(raw or "").strip().lower()
    key = re.sub(r"[\s\-]+", "_", clean)
    lob = _TECH_LOB_ALIASES.get(clean) or _TECH_LOB_ALIASES.get(key) or ""
    if lob:
        return lob
    for hint_lob, words in _TECH_LOB_HINTS:
        if _tech_has(symptom, words):
            return hint_lob
    return ""

_TECH_DIGIT_FIXES = {"O": "0", "I": "1", "L": "1"}  # pragma: no cover

_TECH_CA_FIRST = "ABCEGHJKLMNPRSTVXY"  # pragma: no cover

_TECH_CA_LETTER = "ABCEGHJKLMNPRSTVWXYZ"  # pragma: no cover

_TECH_POSTAL_RE = re.compile(  # pragma: no cover
    rf"[{_TECH_CA_FIRST}]\d[{_TECH_CA_LETTER}]\d[{_TECH_CA_LETTER}]\d"
)

def _tech_parse_postal(raw: Any) -> tuple[str, str]:  # pragma: no cover
    """Return (kind, normalized) for a Canadian postal code or US ZIP; kind "" when invalid."""
    text = re.sub(r"\.0+$", "", str(raw or "").strip())
    compact = re.sub(r"[\s\-\.]+", "", text).upper()
    if re.fullmatch(r"\d{5}", compact):
        return "zip", compact
    if len(compact) == 6:
        chars = list(compact)
        for pos in (1, 3, 5):  # spoken "oh" for zero in digit slots
            chars[pos] = _TECH_DIGIT_FIXES.get(chars[pos], chars[pos])
        fixed = "".join(chars)
        if _TECH_POSTAL_RE.fullmatch(fixed):
            return "postal", f"{fixed[:3]} {fixed[3:]}"
    return "", compact

DEFAULT_REGION = "Region-C"  # pragma: no cover

REGION_BY_POSTAL_LETTER: dict[str, str] = {  # pragma: no cover
    **{letter: "Region-A" for letter in "GHJ"},
    **{letter: "Region-B" for letter in "KLMNP"},
}

def _tech_region(kind: str, code: str) -> str:  # pragma: no cover
    if kind == "postal":
        return REGION_BY_POSTAL_LETTER.get(code[:1], DEFAULT_REGION)
    return DEFAULT_REGION

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

def account_record(state: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover
    """The active account record, falling back to the default account."""
    account_id = str(state.get("account_id") or "")
    for record in ACCOUNTS:
        if record["account_id"] == account_id:
            return dict(record)
    base = dict(ACCOUNTS[0])
    if account_id:
        base["account_id"] = account_id
    return base

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
    "PIN_KEYPAD_REQUIRED",
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
    "PIN_KEYPAD_REQUIRED": (
        "On a phone call the PIN can only be keyed in.",
        "Say spoken_message word for word, then check the 6-digit code the caller says.",
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
    "PIN_KEYPAD_REQUIRED": "Au téléphone, le NIP ne peut être entré qu'au clavier.",
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

def check_regional_outage_impl(  # pragma: no cover
    postal_code: str | int | float = "",
    lob: str = "",
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Area outage status by postal code or ZIP (public; no login needed)."""
    state = get_state(state, session_state)
    lang = session_language(state, language)
    err = check_mock_error(state, lang, "check_regional_outage")
    if err:
        return err
    raw = str(postal_code or "").strip()
    used_address_on_file = False
    if not raw and state.get("account_id"):
        raw = str(account_record(state).get("postal_code") or "")
        used_address_on_file = True
    kind, code = _tech_parse_postal(raw)
    reference = tracking_id("check_regional_outage", code, lob)
    state["last_tracking_id"] = reference
    if not kind:
        return validation_error(
            state,
            "A postal code looks like A1A 1A1 (or a 5-digit ZIP code).",
            "Ask for the postal code again, one character at a time.",
            reference,
            lang,
        )
    region = _tech_region(kind, code)
    service = _tech_lob(lob)
    outage = _tech_area_outage(state, _tech_district(kind, code))
    affected = list(outage["services"]) if outage else []
    active = bool(outage) and (not service or service in affected)
    state["region"] = region
    state["outage_active"] = active
    data: dict[str, Any] = {
        "region": region,
        "outage_active": active,
        "affected_services": affected if active else [],
        "restoration_eta_display": _tech_hours(int(outage["eta_hours"]), lang) if active else "",
        "outage_id": outage["outage_id"] if active else "",
        "used_address_on_file": used_address_on_file,
        "next_step": "say_outage_active_and_offer_text_updates" if active else "offer_troubleshooting",
    }
    if active:
        data["spoken_message"] = spoken_line("outage_active", lang)
    reply = ok_reply(data, reference, language=lang)
    if active:
        reply["agent_action"] = "Say spoken_message (the outage_active line) word for word; on yes, text outage_updates."
    else:
        reply["agent_action"] = "Say there is no outage in the area; offer troubleshooting."
    return reply
# --- END GENERATED SHARED BUNDLE ---
