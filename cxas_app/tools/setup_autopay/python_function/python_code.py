from typing import Any



def setup_autopay(
    payment_method: str = "card_on_file",
    card_number: str | int | float = "",
    language: str = "",
) -> dict[str, Any]:
    """Enrols the logged-in caller in automatic monthly payments with the card on file, a
      new card or a bank account. Call it once the caller has chosen the method. Returns
      the first automatic charge date.

    Args:
      payment_method: card_on_file, new_card or bank_account.
      card_number: The last 4 digits of the card the caller named, or a keyed card
        number (or bank account number), exactly as given; empty for card_on_file.
      language: Active language code (en-US or fr-CA).

    Returns:
      status, data (autopay_enrolled, method, card_last4, bank_last4,
        first_charge_date_display, confirmation_sms_sent, spoken_summary),
        error_message, tracking_id. Errors add error (ALREADY_ENROLLED, CARD_DECLINED,
        CARD_EXPIRED, INVALID_INPUT, NOT_LOGGED_IN) and agent_action.
    """
    ctx = globals().get("context")
    state = getattr(ctx, "state", None) if ctx is not None else None
    if state is None and isinstance(ctx, dict):
        state = ctx
    return setup_autopay_impl(
        payment_method=payment_method,
        card_number=card_number,
        language=language,
        state=state,
    )


# --- BEGIN GENERATED SHARED BUNDLE (edit lib/, then run `make bundle`) ---
# uses: from lib.billing import setup_autopay_impl
from datetime import datetime, timedelta, timezone
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
import hashlib
import re

BILL_DUE_IN_DAYS = 18  # pragma: no cover

NEXT_BILL_CYCLE_DAYS = 30  # pragma: no cover

_BILL_ZERO = Decimal("0.00")  # pragma: no cover

AUTOPAY_DISCOUNT = "0.00"  # pragma: no cover

AUTOPAY_DISCOUNT_NOTE = (  # pragma: no cover
    "There's no discount or incentive for autopay; it makes sure each bill is paid on time, with no fee.",
    "Le paiement préautorisé ne donne pas de rabais ni d'avantage; il assure que chaque facture est payée à temps, sans frais.",
)

AUTOPAY_WITHDRAWAL_NOTE = (  # pragma: no cover
    "Autopay charges the full statement balance on each bill's due date, [days] days after the bill date.",
    "Le paiement préautorisé prélève le solde total du relevé à la date d'échéance de chaque facture, [days] jours après la date de facturation.",
)

BILL_CYCLE_DAYS_AGO = 3  # pragma: no cover

BILL_DATE_CHANGE_NOTE = (  # pragma: no cover
    "The monthly bill date is set by the account's billing cycle and can't be changed; autopay always follows each bill's due date.",
    "La date de facturation mensuelle est fixée par le cycle de facturation du compte et ne peut pas être modifiée; le paiement préautorisé suit toujours la date d'échéance de chaque facture.",
)

def _bill_text(lang: str, en: str, fr: str) -> str:  # pragma: no cover
    """One localized string in the call language (DESIGN_RULES rule 5: no sibling keys)."""
    return fr if lang == "fr-CA" else en

def display_amount(value: Any) -> str:  # pragma: no cover
    """Format money for the agent to say: 85.5 -> "85.50" (two decimals, half-up rounding).

    Return it next to the number, never instead of it:
    {"amount": 85.5, "amount_display": "85.50", "currency": "CAD"}.
    """
    if isinstance(value, bool) or value is None:
        raise ValueError(f"not an amount: {value!r}")
    try:
        amount = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"not an amount: {value!r}") from exc
    if not amount.is_finite():
        raise ValueError(f"not an amount: {value!r}")
    return str(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

def _bill_autopay_facts(lang: str) -> dict[str, str]:  # pragma: no cover
    """Turn N+1 autopay facts (DESIGN_RULES rule 33): withdrawal day, bill date change, discount."""
    days = BILL_CYCLE_DAYS_AGO + BILL_DUE_IN_DAYS
    return {
        "autopay_withdrawal_note": _bill_text(lang, *AUTOPAY_WITHDRAWAL_NOTE).replace("[days]", str(days)),
        "bill_date_change_note": _bill_text(lang, *BILL_DATE_CHANGE_NOTE),
        "autopay_discount_display": display_amount(AUTOPAY_DISCOUNT),
        "autopay_discount_note": _bill_text(lang, *AUTOPAY_DISCOUNT_NOTE),
    }

_EN_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")  # pragma: no cover

_EN_MONTHS = (  # pragma: no cover
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

_FR_DAYS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")  # pragma: no cover

_FR_MONTHS = (  # pragma: no cover
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)

def resolve_locale(language: str | None) -> str:  # pragma: no cover
    """Normalize a language tag or prefix to a supported locale (en-US or fr-CA)."""
    low = str(language or "").strip().lower().replace("_", "-")
    if low.startswith("fr"):
        return "fr-CA"
    return "en-US"

resolve_copy_locale = resolve_locale  # pragma: no cover

def display_date(iso_date: str, lang: str = "en-US") -> str:  # pragma: no cover
    """Spoken date for an ISO date: 'Tuesday, March 4' / 'mardi 4 mars'."""
    try:
        d = datetime.strptime(str(iso_date)[:10], "%Y-%m-%d")
    except ValueError:
        return str(iso_date)
    if resolve_copy_locale(lang) == "fr-CA":
        return f"{_FR_DAYS[d.weekday()]} {d.day} {_FR_MONTHS[d.month - 1]}"
    return f"{_EN_DAYS[d.weekday()]}, {_EN_MONTHS[d.month - 1]} {d.day}"

def relative_date(days: int = 0) -> str:  # pragma: no cover
    """Return an ISO-8601 YYYY-MM-DD date relative to UTC today."""
    return (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%d")

def _bill_date(days: int, lang: str) -> dict[str, str]:  # pragma: no cover
    iso = relative_date(days)
    return {"iso": iso, "display": display_date(iso, lang)}

def mock_mode_on(state: dict[str, Any] | None) -> bool:  # pragma: no cover
    """PRD §17 eval-harness flag (scenario variableOverrides mock_mode="True").

    Every tool here already runs on the fake backend in lib/fakes.py, so mock mode
    changes no tool outcome; fixtures (fx_*) still apply and login is never mocked.
    """
    return isinstance(state, dict) and str(state.get("mock_mode") or "").strip().lower() == "true"

def _bill_finish(state: dict[str, Any], reply: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover
    """Remember the reference and mark synthetic replies in mock mode (prd.md §17)."""
    state["last_tracking_id"] = reply.get("tracking_id", "")
    if mock_mode_on(state):
        reply["data"]["mock_mode"] = True
    return reply

def _bill_flag(state: dict[str, Any], key: str) -> bool:  # pragma: no cover
    value = state.get(key)
    return value is True or str(value).strip().lower() == "true"

PAST_DUE_AMOUNT = "87.65"  # pragma: no cover

def _bill_charges_total(lines: list[dict[str, Any]]) -> Decimal:  # pragma: no cover
    return sum((Decimal(str(line["amount"])) for line in lines), _BILL_ZERO)

BILL_EXTRA_LINES: tuple[dict[str, Any], ...] = (  # pragma: no cover
    {"charge_id": "CH-STR-01", "description": "AppleStreaming purchase", "amount": "12.50", "lob": "tv", "days_ago": 7},
    {"charge_id": "CH-LD-01", "description": "Long distance calls", "amount": "18.40", "lob": "mobility", "days_ago": 12},
)

BILL_EXTRA_LINE_FR: dict[str, str] = {  # pragma: no cover
    "CH-STR-01": "Achat AppleStreaming",
    "CH-LD-01": "Appels interurbains",
}

BILL_EXTRA_LINE_KEYWORDS: dict[str, tuple[str, ...]] = {  # pragma: no cover
    "CH-STR-01": ("stream", "apple", "diffusion", "en continu", "purchase", "achat", "subscription", "abonnement"),
    "CH-LD-01": ("long distance", "long-distance", "longue distance", "interurbain", "international", "calls", "appels"),
}

EXTRA_FIXTURE_LINE_DAYS_AGO = 4  # pragma: no cover

SERVICE_KEYWORDS: dict[str, tuple[str, ...]] = {  # pragma: no cover
    "mobility": ("mobil", "cell", "wireless", "smartphone", "data", "données", "sans fil"),
    "internet": ("internet", "wi-fi", "wifi", "modem", "router", "routeur", "broadband", "fibre", "fiber"),
    "tv": ("tv", "télé", "tele", "television", "télévision", "cable", "câble", "satellite", "channel", "chaîne"),
    "homephone": ("home phone", "landline", "ligne fixe", "téléphone résidentiel", "telephone residentiel"),
}

SERVICE_LINE_LABELS: dict[str, tuple[str, str]] = {  # pragma: no cover
    "mobility": ("Mobility monthly service", "Service mobilité mensuel"),
    "internet": ("Home internet monthly service", "Service Internet résidentiel mensuel"),
    "tv": ("TV monthly service", "Service télé mensuel"),
    "homephone": ("Home phone monthly service", "Service de téléphone résidentiel mensuel"),
}

SERVICE_PRICES: dict[str, str] = {  # pragma: no cover
    "mobility": "65.00",
    "internet": "85.50",
    "tv": "42.00",
    "homephone": "28.00",
}

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

CURRENCY = "CAD"  # pragma: no cover

def to_decimal(value: Any) -> Decimal | None:  # pragma: no cover
    """Parse a caller or model amount ("$85.50", 85.5, "85,50") into Decimal; None when not a number."""
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace("$", "").replace("CAD", "").replace(" ", "")
    if not text:
        return None
    if text.count(",") == 1 and "." not in text:
        text = text.replace(",", ".")
    text = text.replace(",", "")
    try:
        amount = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite():
        return None
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def money(value: Any, prefix: str = "amount") -> dict[str, Any]:  # pragma: no cover
    """Money as a number plus a 2-decimal display string (DESIGN_RULES rule 27)."""
    amount = to_decimal(value) or Decimal("0.00")
    return {prefix: float(amount), f"{prefix}_display": display_amount(amount), "currency": CURRENCY}

def _bill_lines(state: dict[str, Any], lang: str) -> list[dict[str, Any]]:  # pragma: no cover
    """Line items on the latest bill: monthly services, extra charges, and the fx_extra_bill_line fixture."""
    record = account_record(state)
    lobs = [lob for lob in record.get("lines_of_business", []) if lob in SERVICE_PRICES]
    cycle = _bill_date(-BILL_CYCLE_DAYS_AGO, lang)
    lines: list[dict[str, Any]] = []
    for lob in lobs:
        en, fr = SERVICE_LINE_LABELS[lob]
        lines.append(
            {
                "charge_id": f"CH-SVC-{lob.upper()}",
                "description": _bill_text(lang, en, fr),
                "lob": lob,
                "kind": "service",
                "date": cycle["iso"],
                "date_display": cycle["display"],
                "keywords": SERVICE_KEYWORDS.get(lob, ()),
                **money(SERVICE_PRICES[lob]),
            }
        )
    for extra in BILL_EXTRA_LINES:
        if extra["lob"] not in lobs:
            continue
        when = _bill_date(-int(extra["days_ago"]), lang)
        lines.append(
            {
                "charge_id": extra["charge_id"],
                "description": _bill_text(lang, extra["description"], BILL_EXTRA_LINE_FR.get(extra["charge_id"], extra["description"])),
                "lob": extra["lob"],
                "kind": "extra",
                "date": when["iso"],
                "date_display": when["display"],
                "keywords": BILL_EXTRA_LINE_KEYWORDS.get(extra["charge_id"], ()),
                **money(extra["amount"]),
            }
        )
    raw = fixture(state, "fx_extra_bill_line")
    parts = [p.strip() for p in raw.split("|")] if raw else []
    if len(parts) >= 2 and parts[0] and to_decimal(parts[1]) is not None and to_decimal(parts[1]) > _BILL_ZERO:
        lob = parts[2].lower() if len(parts) > 2 and parts[2] else ""
        when = _bill_date(-EXTRA_FIXTURE_LINE_DAYS_AGO, lang)
        words = tuple(w for w in re.findall(r"[\w'-]+", parts[0].lower()) if len(w) > 3)
        lines.append(
            {
                "charge_id": "CH-EXT-01",
                "description": parts[0],
                "lob": lob,
                "kind": "extra",
                "date": when["iso"],
                "date_display": when["display"],
                "keywords": words + SERVICE_KEYWORDS.get(lob, ()),
                **money(parts[1]),
            }
        )
    return lines

_BILL_CENT = Decimal("0.01")  # pragma: no cover

def _bill_q(value: Decimal) -> Decimal:  # pragma: no cover
    return value.quantize(_BILL_CENT, rounding=ROUND_HALF_UP)

def _bill_live(state: dict[str, Any], lang: str) -> dict[str, Decimal]:  # pragma: no cover
    """Balance and past-due amount for this call: session values once a tool changed them, else the backend."""
    past_due = to_decimal(state.get("past_due_amount"))
    if past_due is None:
        past_due = to_decimal(PAST_DUE_AMOUNT) or _BILL_ZERO
    balance = to_decimal(state.get("balance_due"))
    if balance is None:
        balance = past_due + _bill_charges_total(_bill_lines(state, lang))
    return {"balance": _bill_q(max(balance, _BILL_ZERO)), "past_due": _bill_q(max(min(past_due, balance), _BILL_ZERO))}

def _bill_method_text(lang: str, method: dict[str, str]) -> str:  # pragma: no cover
    if method["method"] == "bank_account":
        return _bill_text(lang, f"bank account ending in {method['last4']}", f"compte bancaire se terminant par {method['last4']}")
    return _bill_text(lang, f"card ending in {method['last4']}", f"carte se terminant par {method['last4']}")

BANK_ON_FILE_ENDING = "6083"  # pragma: no cover

DECLINED_CARD_LAST4: frozenset[str] = frozenset({"0000", "9999"})  # pragma: no cover

CARD_BRANDS_BY_PREFIX: dict[str, str] = {"4": "Visa", "5": "Mastercard", "2": "Mastercard", "3": "American Express"}  # pragma: no cover

def _bill_brand(digits: str) -> str:  # pragma: no cover
    return CARD_BRANDS_BY_PREFIX.get(digits[:1], "Card")

def _bill_card_on_file(state: dict[str, Any]) -> dict[str, str]:  # pragma: no cover
    """The usable card on file this call: {last4, brand, status} (status valid/declined/expired/none)."""
    record = account_record(state)
    original = str(record.get("card_last4") or "")
    live = str(state.get("card_last4") or "").strip()
    if live:
        status = fixture(state, "fx_card_on_file_status") if live == original else "valid"
        if live in DECLINED_CARD_LAST4:
            status = "declined"
        brand = str(record.get("card_brand") or "") if live == original else str(state.get("card_brand") or "")
        return {"last4": live, "brand": brand, "status": status or "valid"}
    if _bill_flag(state, "payment_declined_once") and str(state.get("declined_card_last4") or "") == original:
        return {"last4": "", "brand": "", "status": "none"}
    return {"last4": original, "brand": str(record.get("card_brand") or ""), "status": fixture(state, "fx_card_on_file_status") or "valid"}

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

def read_count(state: dict[str, Any] | None, key: str) -> int:  # pragma: no cover
    """Read a whole-number variable; the platform hands them to tools as decimals (5 -> 5.0)."""
    if not isinstance(state, dict):
        return 0
    try:
        return int(float(state.get(key) or 0))
    except (TypeError, ValueError):
        return 0

def _bill_decline(state: dict[str, Any], last4: str, code: str, lang: str, reference: str, tool: str) -> dict[str, Any]:  # pragma: no cover
    """DESIGN_RULES rule 24: a decline clears card_last4 and keeps declined_card_last4."""
    failures = read_count(state, "payment_failure_count") + 1
    state["payment_failure_count"] = failures
    state["card_last4"] = ""
    state["declined_card_last4"] = last4
    state["payment_declined_once"] = True
    message = "The card was declined." if code == "CARD_DECLINED" else "The card has expired."
    return _bill_finish(
        state,
        error_reply(
            code,
            message,
            "Say the card was declined and ask for another card or a bank account.",
            reference,
            language=lang,
            data={
                "declined_card_last4": last4,
                "card_last4": "",
                "payment_failure_count": failures,
                "other_methods": ["new_card", "bank_account"],
            },
        ),
    )

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

def _bill_digits(card_number: Any, dtmf_digits: Any, state: dict[str, Any]) -> str:  # pragma: no cover
    """Card or bank digits from the argument, the keypad argument, or keypad entry in session state."""
    for source in (card_number, dtmf_digits):
        digits = normalize_code(source)
        if digits:
            return digits
    keyed = normalize_code(state.get("dtmf_digits"))
    return keyed if 13 <= len(keyed) <= 19 else ""

_BILL_BANK_WORDS = ("bank", "chequ", "check", "saving", "debit", "bancaire", "banque", "chèque", "cheque", "épargne", "prélèvement", "prelevement")  # pragma: no cover

_BILL_CARD_WORDS = ("card", "carte", "visa", "mastercard", "amex", "credit", "crédit")  # pragma: no cover

_BILL_FILE_WORDS = ("file", "saved", "stored", "dossier", "enregistr", "existing", "same", "même")  # pragma: no cover

_BILL_NEW_WORDS = ("new", "other", "another", "different", "second", "nouvelle", "nouveau", "autre", "différente", "deuxième")  # pragma: no cover

def _bill_method(payment_method: Any, digits: str, state: dict[str, Any]) -> str:  # pragma: no cover
    """Normalize the payment method to card_on_file / new_card / bank_account ('' when unknown)."""
    text = str(payment_method or "").strip().lower().replace("-", "_")
    if text in ("card_on_file", "new_card", "bank_account"):
        method = text
    elif any(w in text for w in _BILL_BANK_WORDS) and not any(w in text for w in ("card", "carte")):
        method = "bank_account"
    elif any(w in text for w in _BILL_NEW_WORDS):
        method = "new_card"
    elif not text or any(w in text for w in _BILL_FILE_WORDS) or any(w in text for w in _BILL_CARD_WORDS):
        method = "new_card" if len(digits) >= 13 else "card_on_file"
    else:
        return ""
    if method == "card_on_file" and len(digits) >= 13:
        method = "new_card"
    if len(digits) == 4 and method in ("card_on_file", "new_card"):
        method = "card_on_file" if digits == _bill_card_on_file(state)["last4"] else "new_card"
    return method

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

def _bill_resolve_method(  # pragma: no cover
    state: dict[str, Any],
    lang: str,
    tool: str,
    payment_method: Any,
    card_number: Any,
    dtmf_digits: Any,
    reference: str,
) -> tuple[dict[str, str] | None, dict[str, Any] | None]:
    """Resolve and check the payment method. Returns ({method, last4, brand}, None) or (None, error reply)."""
    digits = _bill_digits(card_number, dtmf_digits, state)
    method = _bill_method(payment_method, digits, state)
    if not method:
        return None, validation_error(
            state,
            "Unknown payment method.",
            "Ask: card on file, a new card, or a bank account?",
            reference,
            lang,
        )
    if method == "card_on_file":
        card = _bill_card_on_file(state)
        if card["status"] == "none":
            return None, _bill_finish(
                state,
                error_reply(
                    "CARD_DECLINED",
                    "The card on file was declined earlier on this call.",
                    "Ask for another card or a bank account.",
                    reference,
                    language=lang,
                    data={"declined_card_last4": state.get("declined_card_last4", ""), "other_methods": ["new_card", "bank_account"]},
                ),
            )
        if card["status"] in ("declined", "expired"):
            return None, _bill_decline(state, card["last4"], "CARD_DECLINED" if card["status"] == "declined" else "CARD_EXPIRED", lang, reference, tool)
        return {"method": method, "last4": card["last4"], "brand": card["brand"]}, None
    if method == "new_card":
        if not digits:
            # No card named yet. Incomplete, not malformed: not counted towards too_many_errors.
            return None, _bill_finish(
                state,
                error_reply(
                    "INVALID_INPUT",
                    "No card was given.",
                    "Ask which card to use by its last four digits, or to key the card number on the keypad.",
                    reference,
                    language=lang,
                    data={"needs_card": True},
                ),
            )
        if len(digits) == 4:
            # A card the caller names by its ending is one they already hold on file or keyed
            # upstream (prd.md §10: card digits are tokenized upstream, never spoken in full).
            if digits in DECLINED_CARD_LAST4 or digits == str(state.get("declined_card_last4") or ""):
                return None, _bill_decline(state, digits, "CARD_DECLINED", lang, reference, tool)
            return {"method": method, "last4": digits, "brand": ""}, None
        if not 13 <= len(digits) <= 19:
            return None, validation_error(
                state,
                "A card number has 13 to 19 digits.",
                "Ask the caller to enter the full card number.",
                reference,
                lang,
                data={"needs_full_card_number": True},
            )
        last4 = digits[-4:]
        if last4 in DECLINED_CARD_LAST4:
            return None, _bill_decline(state, last4, "CARD_DECLINED", lang, reference, tool)
        return {"method": method, "last4": last4, "brand": _bill_brand(digits)}, None
    if digits and not 5 <= len(digits) <= 17:
        return None, validation_error(
            state,
            "A bank account number has 5 to 17 digits.",
            "Ask the caller to repeat the bank account number.",
            reference,
            lang,
        )
    return {"method": method, "last4": digits[-4:] if digits else BANK_ON_FILE_ENDING, "brand": ""}, None

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

NO_ACCOUNT_ACTION = "If the caller already gave a 4-digit PIN, call check_secret_pin now; else say spoken_message."  # pragma: no cover

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
    "restricted_caller": {
        "en-US": "We're unable to help with this call on this line. Please visit one of our stores for assistance. Goodbye.",
        "fr-CA": "Nous ne pouvons pas traiter cet appel sur cette ligne. Veuillez vous rendre dans l'une de nos boutiques pour obtenir de l'aide. Au revoir.",
    },
    "ai_disclosure": {
        "en-US": "I'm an artificial intelligence customer care assistant.",
        "fr-CA": "Je suis un assistant de service à la clientèle basé sur l'intelligence artificielle.",
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

def require_login(state: dict[str, Any], lang: str, tool_name: str) -> dict[str, Any] | None:  # pragma: no cover
    """BR-TV-008: account reads and changes need a verified caller. Returns an error reply or None."""
    if state.get("auth_status") == "pass" and state.get("logged_in") is not False:
        return None
    ref = tracking_id(tool_name, "not_logged_in", state.get("account_id", ""))
    data: dict[str, Any] = {"code_length": 6, "pin_length": 4}
    if not state.get("account_id"):
        # No number found yet: say what can find the account, never an improvised method.
        data["spoken_message"] = spoken_line("account_lookup_options", lang)
        return error_reply(
            "NOT_LOGGED_IN",
            "The caller has not passed login and no account is found yet.",
            NO_ACCOUNT_ACTION,
            ref,
            language=lang,
            data=data,
        )
    last4 = str(state.get("caller_provided_phone_last4") or state.get("phone_last4") or "")
    data["spoken_message"] = (
        spoken_line("otp_callback_confirm", lang, last4=last4) + " " + spoken_line("pin_alternative", lang)
    )
    data["pin_prompt_message"] = spoken_line("id_verification_pin", lang)
    return error_reply(
        "NOT_LOGGED_IN",
        "The caller has not passed login.",
        "Say spoken_message; send a code if they agree, or check the PIN they give.",
        ref,
        language=lang,
        data=data,
    )

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

def _bill_start(  # pragma: no cover
    state: dict[str, Any] | None,
    session_state: dict[str, Any] | None,
    language: str,
    tool: str,
) -> tuple[dict[str, Any], str, dict[str, Any] | None]:
    """Common opening of every billing tool: state, language, fault injection, business guard, login."""
    st = get_state(state, session_state)
    lang = session_language(st, language)
    err = check_mock_error(st, lang, tool)
    if err:
        return st, lang, err
    if st.get("business_flag") is True or str(st.get("business_flag")).strip().lower() == "true":
        return st, lang, error_reply(
            "PERMISSION_DENIED",
            "Business accounts are served by the business team.",
            "Business account: hand over with reason business_handoff.",
            tracking_id(tool, "business", st.get("account_id", "")),
            language=lang,
        )
    login_err = require_login(st, lang, tool)
    if login_err:
        return st, lang, login_err
    return st, lang, None

def dispatch_sms(state: dict[str, Any], purpose: str) -> dict[str, Any]:  # pragma: no cover
    """Record a text message to the mobile number on file; returns its delivery facts."""
    dest = str(state.get("phone_last4") or account_record(state)["phone"][-4:])
    sent = [p for p in str(state.get("sms_sent") or "").split(",") if p]
    sent.append(purpose)
    state["sms_sent"] = ",".join(sent[-10:])
    return {"sms_sent": True, "destination_last4": dest, "sms_purpose": purpose}

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

def setup_autopay_impl(  # pragma: no cover
    payment_method: str = "card_on_file",
    card_number: Any = "",
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Enrol the account in automatic monthly payments of the statement balance."""
    st, lang, err = _bill_start(state, session_state, language, "setup_autopay")
    if err:
        return err
    account_id = st.get("account_id", "")
    reference = tracking_id("setup_autopay", account_id, payment_method, normalize_code(card_number)[-4:])
    if _bill_flag(st, "autopay_enrolled"):
        return _bill_finish(
            st,
            error_reply(
                "ALREADY_ENROLLED",
                "Autopay is already on for this account.",
                "Say autopay is already set up.",
                reference,
                language=lang,
                data={"autopay_enrolled": True, "method": st.get("autopay_method", "")},
            ),
        )
    method, method_err = _bill_resolve_method(st, lang, "setup_autopay", payment_method, card_number, "", reference)
    if method_err:
        return method_err
    assert method is not None
    live = _bill_live(st, lang)
    # The current bill is charged on its due date; once it's paid, autopay starts with the next bill.
    first = _bill_date(BILL_DUE_IN_DAYS if live["balance"] > _BILL_ZERO else BILL_DUE_IN_DAYS + NEXT_BILL_CYCLE_DAYS, lang)
    st["autopay_enrolled"] = True
    st["autopay_method"] = method["method"]
    if method["method"] != "bank_account":
        st["card_last4"] = method["last4"]
        st["card_brand"] = method["brand"]
    sms = dispatch_sms(st, "autopay_confirmation")
    autopay_id = tracking_id("AUTOPAY", account_id, method["method"], method["last4"])
    data = {
        "autopay_enrolled": True,
        "autopay_id": autopay_id,
        "method": method["method"],
        "card_last4": method["last4"] if method["method"] != "bank_account" else "",
        "card_brand": method["brand"],
        "bank_last4": method["last4"] if method["method"] == "bank_account" else "",
        "first_charge_date": first["iso"],
        "first_charge_date_display": first["display"],
        "charges": "full_statement_balance_on_due_date",
        **_bill_autopay_facts(lang),
        "current_balance_included": live["balance"] > _BILL_ZERO,
        **money(live["balance"], "balance_due"),
        "confirmation_sms_sent": True,
        "sms_destination_last4": sms["destination_last4"],
        "spoken_summary": _bill_text(
            lang,
            f"Autopay is set up with the {_bill_method_text(lang, method)}. The first automatic payment is on {first['display']}. A confirmation is on its way by text.",
            f"Les paiements préautorisés sont configurés avec la {_bill_method_text(lang, method)}. Le premier paiement automatique aura lieu le {first['display']}. Une confirmation vous est envoyée par texto.",
        ).replace("avec la compte", "avec le compte"),
    }
    return _bill_finish(st, ok_reply(data, autopay_id, language=lang))
# --- END GENERATED SHARED BUNDLE ---
