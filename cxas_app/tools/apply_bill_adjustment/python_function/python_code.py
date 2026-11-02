from typing import Any



def apply_bill_adjustment(
    adjustment_type: str = "",
    amount: str | int | float = "",
    description: str = "",
    outage_days: str | int | float = "",
    charge_id: str = "",
    language: str = "",
) -> dict[str, Any]:
    """Credits a wrong or unrecognized charge on the latest bill, refunds a duplicate
      payment found in the ledger, credits days of service outage, or opens a dispute
      case when nothing matches. Call it once the caller has said which charge or how
      many outage days. Amounts above the self-serve limit return
      REFUND_THRESHOLD_EXCEEDED.

    Args:
      adjustment_type: unrecognized_charge, incorrect_charge, duplicate_payment or
        outage_credit.
      amount: Amount the caller disputes, as a quoted string; empty when not stated
        (outage credits are computed by the tool).
      description: Short description in the caller's words: the charge, or which service
        was down.
      outage_days: Number of days the service was down, for outage_credit.
      charge_id: charge_id of the line item from get_billing_summary, when known.
      language: Active language code (en-US or fr-CA).

    Returns:
      status, data (approved, credit_id, amount_display, refund_window_business_days,
        refund_confirmation_line, applied_to, balance_due_display; or dispute_ticket_id,
        eta_business_days), error_message, tracking_id. Errors add error
        (REFUND_THRESHOLD_EXCEEDED, ALREADY_APPLIED, INVALID_INPUT, NOT_LOGGED_IN) and
        agent_action.
    """
    ctx = globals().get("context")
    state = getattr(ctx, "state", None) if ctx is not None else None
    if state is None and isinstance(ctx, dict):
        state = ctx
    return apply_bill_adjustment_impl(
        adjustment_type=adjustment_type,
        amount=amount,
        description=description,
        outage_days=outage_days,
        charge_id=charge_id,
        language=language,
        state=state,
    )


# --- BEGIN GENERATED SHARED BUNDLE (edit lib/, then run `make bundle`) ---
# uses: from lib.billing import apply_bill_adjustment_impl
from datetime import datetime, timedelta, timezone
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
import hashlib
import re

DISPUTE_ETA_BUSINESS_DAYS = 10  # pragma: no cover

DUPLICATE_PAYMENT = {"amount": "140.00", "days_ago": 5, "method": "card_on_file"}  # pragma: no cover

REFUND_WINDOW_BUSINESS_DAYS = 2  # pragma: no cover

SELF_SERVE_ADJUSTMENT_LIMIT = "25.00"  # pragma: no cover

SERVICE_PRICES: dict[str, str] = {  # pragma: no cover
    "mobility": "65.00",
    "internet": "85.50",
    "tv": "42.00",
    "homephone": "28.00",
}

_BILL_DUPLICATE_WORDS = ("duplicate", "double", "twice", "two times", "paid two", "deux fois", "en double", "doublon", "trop-perçu", "trop perçu", "trop payé", "overpa")  # pragma: no cover

_BILL_ZERO = Decimal("0.00")  # pragma: no cover

_BILL_ADJUSTMENT_TYPES = ("unrecognized_charge", "incorrect_charge", "duplicate_payment", "outage_credit")  # pragma: no cover

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

def _bill_adjustment_type(adjustment_type: Any, description: str, outage_days: Any) -> str:  # pragma: no cover
    text = str(adjustment_type or "").strip().lower().replace(" ", "_").replace("-", "_")
    if text in _BILL_ADJUSTMENT_TYPES:
        return text
    if "outage" in text or "panne" in text:
        return "outage_credit"
    if "duplic" in text or "double" in text or "twice" in text:
        return "duplicate_payment"
    if "incorrect" in text or "overcharge" in text or "wrong" in text or "error" in text:
        return "incorrect_charge"
    if text:
        return "unrecognized_charge"
    if normalize_code(outage_days):
        return "outage_credit"
    if any(w in description for w in _BILL_DUPLICATE_WORDS):
        return "duplicate_payment"
    return "unrecognized_charge"

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

def mock_mode_on(state: dict[str, Any] | None) -> bool:  # pragma: no cover
    """PRD §17: eval harness flag; tools mark their replies as synthetic when set."""
    return isinstance(state, dict) and str(state.get("mock_mode") or "").strip().lower() == "true"

def _bill_finish(state: dict[str, Any], reply: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover
    """Remember the reference and mark synthetic replies in mock mode (prd.md §17)."""
    state["last_tracking_id"] = reply.get("tracking_id", "")
    if mock_mode_on(state):
        reply["data"]["mock_mode"] = True
    return reply

PAST_DUE_AMOUNT = "87.65"  # pragma: no cover

def _bill_charges_total(lines: list[dict[str, Any]]) -> Decimal:  # pragma: no cover
    return sum((Decimal(str(line["amount"])) for line in lines), _BILL_ZERO)

BILL_CYCLE_DAYS_AGO = 3  # pragma: no cover

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

def _bill_text(lang: str, en: str, fr: str) -> str:  # pragma: no cover
    """One localized string in the call language (DESIGN_RULES rule 5: no sibling keys)."""
    return fr if lang == "fr-CA" else en

CURRENCY = "CAD"  # pragma: no cover

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

def _bill_save(state: dict[str, Any], balance: Decimal, past_due: Decimal) -> None:  # pragma: no cover
    state["balance_due"] = display_amount(max(balance, _BILL_ZERO))
    state["past_due_amount"] = display_amount(max(min(past_due, balance), _BILL_ZERO))

def append_list(state: dict[str, Any], key: str, value: str) -> list[str]:  # pragma: no cover
    """Append to a comma-separated list stored in one STRING session variable."""
    items = [p for p in str(state.get(key) or "").split(",") if p]
    if value not in items:
        items.append(value)
    state[key] = ",".join(items)
    return items

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

OK_STATUS = _StatusStr("ok")  # pragma: no cover

def tracking_id(tool: str, *inputs: object) -> str:  # pragma: no cover
    """Return a reference number built from the tool name and its inputs.

    The same inputs always give the same number, so a retried call can't
    create a second record under a new number.
    """
    raw = "|".join([tool, *(str(value).strip().lower() for value in inputs)])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return "R" + str(int(digest[:8], 16) % 1_000_000).zfill(6)

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
    "otp_callback_confirm": {
        "en-US": "I'll send a 6-digit code to the number ending in [last4]. Ready?",
        "fr-CA": "Je vais envoyer un code à 6 chiffres au numéro se terminant par [last4]. Êtes-vous prêt?",
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

def _bill_credit_reply(  # pragma: no cover
    state: dict[str, Any],
    lang: str,
    kind: str,
    amount: Decimal,
    key: str,
    extra: dict[str, Any],
    to_card: bool = False,
) -> dict[str, Any]:
    """A credit or refund that was applied: the PRD refund_confirmation_pattern facts plus Turn-N+1 fields."""
    account_id = state.get("account_id", "")
    credit_id = tracking_id("CREDIT", account_id, key, amount)
    append_list(state, "applied_adjustments", key)
    live = _bill_live(state, lang)
    balance = live["balance"]
    if not to_card:
        balance = _bill_q(max(balance - amount, _BILL_ZERO))
        _bill_save(state, balance, live["past_due"])
    amount_text = display_amount(amount)
    data = {
        "adjustment_type": kind,
        "approved": True,
        "credit_id": credit_id,
        **money(amount),
        "refund_window_business_days": REFUND_WINDOW_BUSINESS_DAYS,
        "applied_to": "original_payment_method" if to_card else "next_statement",
        "refund_confirmation_line": spoken_line("refund_confirmation_pattern", lang, amount=amount_text, days=REFUND_WINDOW_BUSINESS_DAYS),
        **money(balance, "balance_due"),
        **extra,
    }
    if to_card:
        card = _bill_card_on_file(state)
        data["refund_card_last4"] = card["last4"]
    return _bill_finish(state, ok_reply(data, credit_id, language=lang))

def _bill_match(text: str, keyword: str) -> bool:  # pragma: no cover
    """Whole-word-start match, so 'tv' doesn't hit inside another word but 'mobil' matches 'mobilité'."""
    return re.search(rf"(?<![\w]){re.escape(keyword)}", text) is not None

def _bill_same_amount(line_amount: Decimal, asked: Decimal) -> bool:  # pragma: no cover
    """The caller's amount names this charge: exact, or the whole-dollar figure people say aloud."""
    return asked in (line_amount, line_amount.to_integral_value(rounding=ROUND_DOWN), line_amount.to_integral_value(rounding=ROUND_HALF_UP))

def _bill_find_line(lines: list[dict[str, Any]], charge_id: str, amount: Decimal | None, description: str) -> dict[str, Any] | None:  # pragma: no cover
    """The latest-bill line the caller means: by charge id, else by amount (words break ties), else by words alone.

    A stated amount that matches no line never falls back to words, so a partial
    "overcharge" on a monthly service opens a dispute instead of an automatic credit.
    """
    if charge_id:
        for line in lines:
            if line["charge_id"].lower() == charge_id.lower():
                return line

    def _score(line: dict[str, Any]) -> int:
        hits = sum(1 for kw in line.get("keywords", ()) if _bill_match(description, kw))
        return hits * 2 + (1 if line["kind"] == "extra" and hits else 0)

    if amount is not None:
        same = [line for line in lines if _bill_same_amount(Decimal(str(line["amount"])), amount)]
        return max(same, key=_score) if same else None
    if not description:
        return None
    scored = [(line, _score(line)) for line in lines]
    scored = [pair for pair in scored if pair[1] > 0]
    if not scored:
        return None
    best = max(pair[1] for pair in scored)
    top = [line for line, score in scored if score == best]
    return top[0] if len(top) == 1 else None

def _bill_outage_lob(description: str, state: dict[str, Any]) -> str:  # pragma: no cover
    record = account_record(state)
    lobs = [lob for lob in record.get("lines_of_business", []) if lob in SERVICE_PRICES]
    for lob in lobs:
        if any(_bill_match(description, kw) for kw in SERVICE_KEYWORDS.get(lob, ())):
            return lob
    live = str(state.get("lob") or "").strip().lower()
    if live in lobs:
        return live
    return lobs[0] if len(lobs) == 1 else ""

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

ERROR_STATUS = _StatusStr("error")  # pragma: no cover

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

def require_login(state: dict[str, Any], lang: str, tool_name: str) -> dict[str, Any] | None:  # pragma: no cover
    """BR-TV-008: account reads and changes need a verified caller. Returns an error reply or None."""
    if state.get("auth_status") == "pass" and state.get("logged_in") is not False:
        return None
    ref = tracking_id(tool_name, "not_logged_in", state.get("account_id", ""))
    return error_reply(
        "NOT_LOGGED_IN",
        "The caller has not passed login.",
        "Verify the caller (code or PIN), then call this tool again.",
        ref,
        language=lang,
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

def fixture_flag(state: dict[str, Any] | None, name: str) -> bool:  # pragma: no cover
    """Read a true/false fixture."""
    return fixture(state, name) in ("true", "1", "yes")

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

def apply_bill_adjustment_impl(  # pragma: no cover
    adjustment_type: str = "",
    amount: Any = "",
    description: str = "",
    outage_days: Any = "",
    charge_id: str = "",
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Credit a charge, refund a verified duplicate payment, credit outage days, or open a dispute case."""
    st, lang, err = _bill_start(state, session_state, language, "apply_bill_adjustment")
    if err:
        return err
    account_id = st.get("account_id", "")
    desc = " ".join(str(description or "").lower().split())
    kind = _bill_adjustment_type(adjustment_type, desc, outage_days)
    reference = tracking_id("apply_bill_adjustment", account_id, kind, amount, desc, outage_days, charge_id)
    asked: Decimal | None = None
    if str(amount if amount is not None else "").strip():
        asked = to_decimal(amount)
        if asked is None or asked <= _BILL_ZERO:
            return validation_error(st, "The amount is not a valid positive amount.", "Ask the caller for the amount of the charge.", reference, lang)
    applied = [p for p in str(st.get("applied_adjustments") or "").split(",") if p]
    limit = to_decimal(SELF_SERVE_ADJUSTMENT_LIMIT) or _BILL_ZERO

    def _already(key: str) -> dict[str, Any]:
        return _bill_finish(
            st,
            error_reply(
                "ALREADY_APPLIED",
                "This adjustment was already applied on this account.",
                "Say it was already credited; no second credit.",
                reference,
                language=lang,
                data={"adjustment_key": key, "refund_window_business_days": REFUND_WINDOW_BUSINESS_DAYS},
            ),
        )

    def _over_limit(value: Decimal) -> dict[str, Any]:
        return _bill_finish(
            st,
            error_reply(
                "REFUND_THRESHOLD_EXCEEDED",
                "The amount is above the self-serve adjustment limit.",
                "Hand over with reason refund_threshold_exceeded.",
                reference,
                language=lang,
                data={**money(value), "limit_display": display_amount(limit), "handover_reason": "refund_threshold_exceeded"},
            ),
        )

    # Verified duplicate payment: the caller's own money, refunded in full after the
    # ledger check (decision A1). Only a duplicate that is really in the ledger counts.
    dup_amount = to_decimal(DUPLICATE_PAYMENT["amount"]) or _BILL_ZERO
    dup_claim = kind == "duplicate_payment" or any(w in desc for w in _BILL_DUPLICATE_WORDS)
    if dup_claim and fixture_flag(st, "fx_duplicate_payment") and (asked is None or asked == dup_amount):
        if "duplicate_payment" in applied:
            return _already("duplicate_payment")
        when = _bill_date(-int(DUPLICATE_PAYMENT["days_ago"]), lang)
        return _bill_credit_reply(
            st,
            lang,
            "duplicate_payment",
            dup_amount,
            "duplicate_payment",
            {"duplicate_payment_date": when["iso"], "duplicate_payment_date_display": when["display"]},
            to_card=True,
        )
    # (4) Outage credit: monthly price of the affected service / 30 x days. The credit
    # is always computed here (never the caller's figure) and then checked against the limit.
    if kind == "outage_credit":
        days_text = normalize_code(outage_days)
        days = int(days_text) if days_text else 0
        if not 1 <= days <= 365:
            return validation_error(st, "The number of outage days is missing or invalid.", "Ask how many days the service was down.", reference, lang)
        lob = _bill_outage_lob(desc, st)
        if not lob:
            return validation_error(st, "The affected service is unclear.", "Ask which service was down.", reference, lang, data={"lines_of_business": account_record(st).get("lines_of_business", [])})
        key = f"outage:{lob}"
        if key in applied:
            return _already(key)
        monthly = to_decimal(SERVICE_PRICES[lob]) or _BILL_ZERO
        daily = monthly / Decimal(30)
        credit = _bill_q(daily * days)
        if credit > limit:
            return _over_limit(credit)
        return _bill_credit_reply(
            st,
            lang,
            "outage_credit",
            credit,
            key,
            {"lob": lob, "outage_days": days, **money(monthly, "monthly_price"), "daily_rate_display": display_amount(_bill_q(daily))},
        )
    # (1) Over the self-serve limit: a specialist decides.
    if asked is not None and asked > limit:
        return _over_limit(asked)
    # (2) A line item on the latest bill.
    lines = _bill_lines(st, lang)
    line = _bill_find_line(lines, str(charge_id or "").strip(), asked, desc)
    if line is not None:
        line_amount = Decimal(str(line["amount"]))
        credit = line_amount if asked is None or _bill_same_amount(line_amount, asked) else min(asked, line_amount)
        if credit > limit:
            return _over_limit(credit)
        key = f"charge:{line['charge_id']}"
        if key in applied:
            return _already(key)
        return _bill_credit_reply(
            st,
            lang,
            kind if kind != "duplicate_payment" else "incorrect_charge",
            credit,
            key,
            {"charge_id": line["charge_id"], "charge_description": line["description"], "charge_date_display": line["date_display"]},
        )
    # (5) Nothing matched: open a dispute case for the billing team.
    key = "dispute:" + tracking_id("dispute", kind, asked, desc)
    ticket = tracking_id("DISPUTE", account_id, kind, asked, desc).replace("R", "DSP-", 1)
    if key in applied:
        return _bill_finish(
            st,
            error_reply(
                "ALREADY_APPLIED",
                "A dispute case is already open for this charge.",
                "Give the existing dispute case number.",
                reference,
                language=lang,
                data={"dispute_ticket_id": ticket, "eta_business_days": DISPUTE_ETA_BUSINESS_DAYS},
            ),
        )
    append_list(st, "applied_adjustments", key)
    sms = dispatch_sms(st, "dispute_opened")
    data = {
        "adjustment_type": kind,
        "approved": False,
        "dispute_opened": True,
        "dispute_ticket_id": ticket,
        "eta_business_days": DISPUTE_ETA_BUSINESS_DAYS,
        "sms_confirmation_sent": True,
        "sms_destination_last4": sms["destination_last4"],
        "spoken_summary": _bill_text(
            lang,
            f"I couldn't match that charge on your latest bill, so I opened dispute case {ticket}. The billing team will reply within {DISPUTE_ETA_BUSINESS_DAYS} business days. A confirmation is on its way by text.",
            f"Je n'ai pas trouvé ces frais sur votre dernière facture, j'ai donc ouvert le dossier de contestation {ticket}. L'équipe de facturation répondra d'ici {DISPUTE_ETA_BUSINESS_DAYS} jours ouvrables. Une confirmation vous est envoyée par texto.",
        ),
    }
    if asked is not None:
        data.update(money(asked))
    return _bill_finish(st, ok_reply(data, ticket, language=lang))
# --- END GENERATED SHARED BUNDLE ---
