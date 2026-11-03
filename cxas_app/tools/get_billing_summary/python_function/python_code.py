from typing import Any



def get_billing_summary(
    language: str = "",
) -> dict[str, Any]:
    """Gets the logged-in caller's balance, past-due amount, due date, service status and
      suspension reason, cards and bank on file, autopay status, latest bill line items
      and recent payments. Call it before talking about any amount or charge, and when a
      caller asks about their bill or a suspended service.

    Args:
      language: Active language code (en-US or fr-CA).

    Returns:
      status, data (balance_due_display, past_due_amount_display, due_date_display,
        service_status, suspension_reason, card_on_file_last4, bank_on_file_last4,
        autopay_enrolled, recent_bills[].line_items[] {charge_id, description,
        amount_display, date_display}, recent_payments[], arrangement_offer,
        restore_options, spoken_summary), error_message, tracking_id. Errors add error
        (NOT_LOGGED_IN, PERMISSION_DENIED) and agent_action.
    """
    ctx = globals().get("context")
    state = getattr(ctx, "state", None) if ctx is not None else None
    if state is None and isinstance(ctx, dict):
        state = ctx
    return get_billing_summary_impl(
        language=language,
        state=state,
    )


# --- BEGIN GENERATED SHARED BUNDLE (edit lib/, then run `make bundle`) ---
# uses: from lib.billing import get_billing_summary_impl
from datetime import datetime, timedelta, timezone
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
import contextvars
import hashlib
import re
import unicodedata

BANK_ON_FILE_ENDING = "6083"  # pragma: no cover

BILL_CYCLE_DAYS_AGO = 3  # pragma: no cover

BILL_DUE_IN_DAYS = 18  # pragma: no cover

PAYMENT_POSTING_NOTE = (  # pragma: no cover
    "A payment made with us posts to the account right away, so the balance given already includes it.",
    "Un paiement fait chez nous est porté au compte immédiatement; le solde indiqué en tient donc déjà compte.",
)

SELF_SERVE_ADJUSTMENT_LIMIT = "25.00"  # pragma: no cover

_BILL_SUSPENSION_REASONS = {  # pragma: no cover
    "suspended_nonpayment": "non_payment",
    "suspended_lost_stolen": "lost_stolen",
    "suspended_travel": "travel",
}

_BILL_ZERO = Decimal("0.00")  # pragma: no cover

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

def _bill_amount_text(lang: str, amount: Decimal) -> str:  # pragma: no cover
    """Money as spoken in the call language: '$12.50' / '12.50 $'."""
    shown = display_amount(amount)
    return f"{shown} $" if lang == "fr-CA" else f"${shown}"

ARRANGEMENT_FIRST_DUE_DAYS = 7  # pragma: no cover

ARRANGEMENT_INSTALMENTS = 2  # pragma: no cover

ARRANGEMENT_SECOND_DUE_DAYS = 30  # pragma: no cover

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

_BILL_CENT = Decimal("0.01")  # pragma: no cover

def _bill_q(value: Decimal) -> Decimal:  # pragma: no cover
    return value.quantize(_BILL_CENT, rounding=ROUND_HALF_UP)

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

def _bill_arrangement_offer(balance: Decimal, lang: str, first: Decimal | None = None) -> dict[str, Any]:  # pragma: no cover
    """Two-instalment schedule for the balance (decision A9)."""
    first_amt = _bill_q(first if first is not None else balance / ARRANGEMENT_INSTALMENTS)
    second_amt = _bill_q(balance - first_amt)
    first_due = _bill_date(ARRANGEMENT_FIRST_DUE_DAYS, lang)
    second_due = _bill_date(ARRANGEMENT_FIRST_DUE_DAYS + ARRANGEMENT_SECOND_DUE_DAYS, lang)
    return {
        "instalments": [
            {"number": 1, **money(first_amt), "due_date": first_due["iso"], "due_date_display": first_due["display"]},
            {"number": 2, **money(second_amt), "due_date": second_due["iso"], "due_date_display": second_due["display"]},
        ],
        "instalment_count": ARRANGEMENT_INSTALMENTS,
        **money(balance, "total"),
    }

AUTOPAY_DISCOUNT = "0.00"  # pragma: no cover

AUTOPAY_DISCOUNT_NOTE = (  # pragma: no cover
    "There's no discount or incentive for autopay; it makes sure each bill is paid on time, with no fee.",
    "Le paiement préautorisé ne donne pas de rabais ni d'avantage; il assure que chaque facture est payée à temps, sans frais.",
)

AUTOPAY_WITHDRAWAL_NOTE = (  # pragma: no cover
    "Autopay charges the full statement balance on each bill's due date, [days] days after the bill date.",
    "Le paiement préautorisé prélève le solde total du relevé à la date d'échéance de chaque facture, [days] jours après la date de facturation.",
)

BILL_DATE_CHANGE_NOTE = (  # pragma: no cover
    "The monthly bill date is set by the account's billing cycle and can't be changed; autopay always follows each bill's due date.",
    "La date de facturation mensuelle est fixée par le cycle de facturation du compte et ne peut pas être modifiée; le paiement préautorisé suit toujours la date d'échéance de chaque facture.",
)

def _bill_text(lang: str, en: str, fr: str) -> str:  # pragma: no cover
    """One localized string in the call language (DESIGN_RULES rule 5: no sibling keys)."""
    return fr if lang == "fr-CA" else en

def _bill_autopay_facts(lang: str) -> dict[str, str]:  # pragma: no cover
    """Turn N+1 autopay facts (DESIGN_RULES rule 33): withdrawal day, bill date change, discount."""
    days = BILL_CYCLE_DAYS_AGO + BILL_DUE_IN_DAYS
    return {
        "autopay_withdrawal_note": _bill_text(lang, *AUTOPAY_WITHDRAWAL_NOTE).replace("[days]", str(days)),
        "bill_date_change_note": _bill_text(lang, *BILL_DATE_CHANGE_NOTE),
        "autopay_discount_display": display_amount(AUTOPAY_DISCOUNT),
        "autopay_discount_note": _bill_text(lang, *AUTOPAY_DISCOUNT_NOTE),
    }

DECLINED_CARD_LAST4: frozenset[str] = frozenset({"0000", "9999"})  # pragma: no cover

def _bill_flag(state: dict[str, Any], key: str) -> bool:  # pragma: no cover
    value = state.get(key)
    return value is True or str(value).strip().lower() == "true"

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

def _bill_charges_total(lines: list[dict[str, Any]]) -> Decimal:  # pragma: no cover
    return sum((Decimal(str(line["amount"])) for line in lines), _BILL_ZERO)

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

BILL_EXTRA_LINE_NOTES: dict[str, dict[str, tuple[str, str]]] = {  # pragma: no cover
    "CH-STR-01": {
        "origin": (
            "A purchase made through a connected TV app on the account.",
            "Un achat fait au moyen d'une application télé connectée au compte.",
        ),
        "prevention_tip": (
            "Purchases can be protected with a purchase PIN on the TV service.",
            "Les achats peuvent être protégés par un NIP d'achat sur le service télé.",
        ),
    },
    "CH-LD-01": {
        "origin": (
            "Calls from the mobility line to numbers outside its local calling area.",
            "Des appels faits depuis la ligne mobile vers des numéros hors de sa zone d'appel locale.",
        ),
        "prevention_tip": (
            "A plan that includes long distance calling avoids these per-call charges.",
            "Un forfait qui inclut les appels interurbains évite ces frais par appel.",
        ),
    },
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
                **{key: _bill_text(lang, *pair) for key, pair in BILL_EXTRA_LINE_NOTES.get(extra["charge_id"], {}).items()},
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

PAST_DUE_AMOUNT = "87.65"  # pragma: no cover

def _bill_live(state: dict[str, Any], lang: str) -> dict[str, Decimal]:  # pragma: no cover
    """Balance and past-due amount for this call: session values once a tool changed them, else the backend."""
    past_due = to_decimal(state.get("past_due_amount"))
    if past_due is None:
        past_due = to_decimal(PAST_DUE_AMOUNT) or _BILL_ZERO
    balance = to_decimal(state.get("balance_due"))
    if balance is None:
        balance = past_due + _bill_charges_total(_bill_lines(state, lang))
    return {"balance": _bill_q(max(balance, _BILL_ZERO)), "past_due": _bill_q(max(min(past_due, balance), _BILL_ZERO))}

NEXT_BILL_CYCLE_DAYS = 30  # pragma: no cover

PAST_DUE_FALLBACK_LABEL = ("Unpaid charges from the previous statement", "Frais impayés du relevé précédent")  # pragma: no cover

PAST_DUE_ITEMS: tuple[dict[str, Any], ...] = (  # pragma: no cover
    {"lob": "mobility", "label": ("Mobility monthly service", "Service mobilité mensuel"), "amount": "65.00"},
    {"lob": "mobility", "label": ("Long distance calls", "Appels interurbains"), "amount": "22.65"},
)

PAST_DUE_LATE_FEE = "0.00"  # pragma: no cover

def _bill_past_due_breakdown(state: dict[str, Any], lang: str, past_due: Decimal) -> dict[str, Any]:  # pragma: no cover
    """What the past-due amount is made of: the previous statement's unpaid items (Turn N+1, rule 33)."""
    record = account_record(state)
    lobs = set(record.get("lines_of_business", []))
    statement = _bill_date(-(BILL_CYCLE_DAYS_AGO + NEXT_BILL_CYCLE_DAYS), lang)
    items_total = sum((Decimal(item["amount"]) for item in PAST_DUE_ITEMS), _BILL_ZERO)
    if all(item["lob"] in lobs for item in PAST_DUE_ITEMS) and past_due <= items_total:
        items = [{"description": _bill_text(lang, *item["label"]), **money(item["amount"])} for item in PAST_DUE_ITEMS]
        paid_since = _bill_q(items_total - past_due)
    else:
        items = [{"description": _bill_text(lang, *PAST_DUE_FALLBACK_LABEL), **money(past_due)}]
        paid_since = _BILL_ZERO
    breakdown: dict[str, Any] = {
        "statement_date": statement["iso"],
        "statement_date_display": statement["display"],
        "items": items,
        **money(PAST_DUE_LATE_FEE, "late_fees"),
        **money(past_due, "past_due_amount"),
    }
    if paid_since > _BILL_ZERO:
        breakdown.update(money(paid_since, "paid_since"))
    return breakdown

DUPLICATE_PAYMENT = {"amount": "140.00", "days_ago": 5, "method": "card_on_file"}  # pragma: no cover

LAST_PAYMENT = {"amount": "140.00", "days_ago": 32, "method": "card_on_file"}  # pragma: no cover

RECENT_PAYMENT_DAYS_AGO = 1  # pragma: no cover

def fixture_flag(state: dict[str, Any] | None, name: str) -> bool:  # pragma: no cover
    """Read a true/false fixture."""
    return fixture(state, name) in ("true", "1", "yes")

def _bill_payments(state: dict[str, Any], lang: str, past_due: Decimal) -> list[dict[str, Any]]:  # pragma: no cover
    """Recent payments in the ledger, newest first."""
    payments: list[dict[str, Any]] = []
    paid_now = to_decimal(state.get("last_pmt_amt"))
    if paid_now is not None and paid_now > _BILL_ZERO:
        today = _bill_date(0, lang)
        payments.append({"date": today["iso"], "date_display": today["display"], "status": "posted", "method": str(state.get("last_payment_method") or ""), **money(paid_now)})
    # A posted payment not applied yet is in the payment processor's queue, not the
    # ledger: it shows only once verify_payment_and_restore found and applied it.
    if fixture(state, "fx_recent_payment") == "posted_yesterday" and _bill_flag(state, "recent_payment_applied"):
        when = _bill_date(-RECENT_PAYMENT_DAYS_AGO, lang)
        payments.append({"date": when["iso"], "date_display": when["display"], "status": "posted", "method": "online_banking", **money(PAST_DUE_AMOUNT)})
    if fixture_flag(state, "fx_duplicate_payment"):
        when = _bill_date(-int(DUPLICATE_PAYMENT["days_ago"]), lang)
        refunded = "duplicate_payment" in str(state.get("applied_adjustments") or "").split(",")
        for dup in (False, True):
            payments.append(
                {
                    "date": when["iso"],
                    "date_display": when["display"],
                    "status": "refunded" if (dup and refunded) else "posted",
                    "method": DUPLICATE_PAYMENT["method"],
                    "duplicate": dup,
                    **money(DUPLICATE_PAYMENT["amount"]),
                }
            )
    when = _bill_date(-int(LAST_PAYMENT["days_ago"]), lang)
    payments.append({"date": when["iso"], "date_display": when["display"], "status": "posted", "method": LAST_PAYMENT["method"], **money(LAST_PAYMENT["amount"])})
    return payments

def _bill_public_line(line: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover
    return {k: v for k, v in line.items() if k not in ("keywords", "kind")}

RECONNECT_MINUTES = 15  # pragma: no cover

RECONNECT_NOTE = (  # pragma: no cover
    "Service comes back within [minutes] minutes; if it doesn't, restart the modem or phone.",
    "Le service revient d'ici [minutes] minutes; sinon, redémarrez le modem ou le téléphone.",
)

def _bill_reconnect_note(lang: str) -> str:  # pragma: no cover
    """How soon a restored service comes back and what to do if it doesn't (DESIGN_RULES rule 33)."""
    return _bill_text(lang, *RECONNECT_NOTE).replace("[minutes]", str(RECONNECT_MINUTES))

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
    last4 = str(state.get("caller_provided_phone_last4") or ("" if state.get("phone_derived") else state.get("phone_last4")) or "")
    offer = spoken_line("otp_callback_confirm", lang, last4=last4) if last4 else spoken_line("otp_callback_on_file", lang)
    data["spoken_message"] = offer + " " + spoken_line("pin_alternative", lang)
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

def service_status(state: dict[str, Any]) -> str:  # pragma: no cover
    """Current service status: the value tools wrote this call, else the backend fixture."""
    live = str(state.get("service_status") or "").strip()
    return live or fixture(state, "fx_service_status")

def get_billing_summary_impl(  # pragma: no cover
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Balance, past-due amount, due date, service status, latest bill line items and recent payments."""
    st, lang, err = _bill_start(state, session_state, language, "get_billing_summary")
    if err:
        return err
    live = _bill_live(st, lang)
    status = service_status(st)
    lines = _bill_lines(st, lang)
    card = _bill_card_on_file(st)
    due = _bill_date(BILL_DUE_IN_DAYS, lang)
    autopay = _bill_flag(st, "autopay_enrolled")
    arrangement = _bill_flag(st, "arrangement_active")
    reference = tracking_id("get_billing_summary", st.get("account_id", ""), live["balance"], status)
    data: dict[str, Any] = {
        **money(live["balance"], "balance_due"),
        **money(live["past_due"], "past_due_amount"),
        "due_date": due["iso"],
        "due_date_display": due["display"],
        "service_status": status,
        "suspension_reason": _BILL_SUSPENSION_REASONS.get(status, ""),
        "card_on_file_last4": card["last4"],
        "card_on_file_brand": card["brand"],
        "bank_on_file_last4": BANK_ON_FILE_ENDING,
        "autopay_enrolled": autopay,
        "payment_arrangement_active": arrangement,
        **_bill_autopay_facts(lang),
        "recent_bills": [
            {
                "bill_date": lines[0]["date"] if lines else relative_date(-BILL_CYCLE_DAYS_AGO),
                "bill_date_display": lines[0]["date_display"] if lines else "",
                **money(_bill_charges_total(lines), "new_charges"),
                "line_items": [_bill_public_line(line) for line in lines],
            }
        ],
        "recent_payments": _bill_payments(st, lang, live["past_due"]),
        "self_serve_adjustment_limit_display": display_amount(SELF_SERVE_ADJUSTMENT_LIMIT),
        "posting_note": _bill_text(lang, *PAYMENT_POSTING_NOTE),
    }
    if live["past_due"] > _BILL_ZERO:
        data["past_due_breakdown"] = _bill_past_due_breakdown(st, lang, live["past_due"])
    if status == "suspended_nonpayment":
        data["amount_to_restore_display"] = display_amount(live["past_due"])
        data["restore_options"] = ["pay_past_due", "verify_recent_payment", "payment_arrangement"]
        data["reconnect_note"] = _bill_reconnect_note(lang)
    elif status in ("suspended_lost_stolen", "suspended_travel"):
        data["restore_handled_by"] = "account"
    if live["balance"] > _BILL_ZERO and not arrangement:
        data["arrangement_offer"] = _bill_arrangement_offer(live["balance"], lang)
    summary = _bill_text(
        lang,
        f"Your balance is {_bill_amount_text(lang, live['balance'])}, due {due['display']}.",
        f"Votre solde est de {_bill_amount_text(lang, live['balance'])}, payable le {due['display']}.",
    )
    if live["past_due"] > _BILL_ZERO:
        summary += _bill_text(
            lang,
            f" Of that, {_bill_amount_text(lang, live['past_due'])} is past due.",
            f" De ce montant, {_bill_amount_text(lang, live['past_due'])} est en souffrance.",
        )
    # PRD §7 verbatim, said before any payment step; carried here so the line is grounded.
    data["payment_method_preamble"] = spoken_line("payment_method_preamble", lang)
    data["spoken_summary"] = summary
    reply = ok_reply(data, reference, language=lang)
    if status == "suspended_nonpayment":
        # The suspension is in the data; it is raised only with a caller who asks about it.
        reply["agent_action"] = "Mention the non-payment suspension only if the caller asks about restoring service."
    return _bill_finish(st, reply)
# --- END GENERATED SHARED BUNDLE ---
