from typing import Any



def file_warranty_claim(
    device: str = "",
    issue: str = "",
    physical_damage: str | bool = "",
    water_damage: str | bool = "",
    language: str = "",
) -> dict[str, Any]:
    """Checks warranty coverage for the caller's device on file and files a replacement
      claim. Needs login. Call with the damage answers empty to check coverage; call
      again with both damage answers to file. A swollen battery, smoke or overheating
      files an urgent expedited claim and returns safety_advice.

    Args:
      device: The device as the caller named it (brand or model); empty if not said.
      issue: The fault in the caller's words.
      physical_damage: true or false once the caller answered whether it is cracked or
        dropped; empty if not asked yet.
      water_damage: true or false once the caller answered whether it got wet; empty if
        not asked yet.
      language: Active language code (en-US or fr-CA).

    Returns:
      status, data (device_model, device_matched, purchase_date_display,
        warranty_end_display, in_warranty, claim_filed, damage_check_needed, claim_id,
        replacement_eta_display, shipping_address_last_line, return_instructions,
        urgent, safety_advice), error_message, tracking_id. Errors add error
        (NOT_LOGGED_IN, NOT_ELIGIBLE with repair_options, INVALID_INPUT) and
        agent_action.
    """
    ctx = globals().get("context")
    state = getattr(ctx, "state", None) if ctx is not None else None
    if state is None and isinstance(ctx, dict):
        state = ctx
    return file_warranty_claim_impl(
        device=device,
        issue=issue,
        physical_damage=physical_damage,
        water_damage=water_damage,
        language=language,
        state=state,
    )


# --- BEGIN GENERATED SHARED BUNDLE (edit lib/, then run `make bundle`) ---
# uses: from lib.sales import file_warranty_claim_impl
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
import hashlib
import re

DEVICE_WARRANTY_DAYS = 365  # pragma: no cover

SALES_OUT_OF_WARRANTY_AGE_DAYS = 430  # pragma: no cover

SALES_REPAIR_FEE = "139.00"  # pragma: no cover

SALES_RETURN_WINDOW_DAYS = 15  # pragma: no cover

SALES_SAFETY_WORDS: tuple[str, ...] = (  # pragma: no cover
    "swollen", "swelling", "bulging", "bulge", "puffy", "expanding", "smoke", "smoking", "overheat",
    "too hot", "burning", "fire", "melt", "gonfl", "bombé", "fumée", "surchauff", "brûl",
)

SALES_URGENT_SHIP_DAYS = 1  # pragma: no cover

SALES_WARRANTY_SHIP_DAYS = 3  # pragma: no cover

def _sales_bool(value: Any) -> bool | None:  # pragma: no cover
    """Caller yes/no answers: True, False, or None when not answered yet."""
    if isinstance(value, bool):
        return value
    low = str(value if value is not None else "").strip().lower()
    if low in ("true", "yes", "y", "1", "oui", "1.0"):
        return True
    if low in ("false", "no", "n", "0", "non", "none", "0.0", "aucun"):
        return False
    return None

def _sales_business_date(days: int) -> str:  # pragma: no cover
    """ISO date `days` business days from today (0 = today)."""
    current = datetime.now(timezone.utc)
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current.strftime("%Y-%m-%d")

DEVICES_ON_FILE: tuple[dict[str, Any], ...] = (  # pragma: no cover
    {"device_id": "DEV-01", "model": "Apple iPhone 15", "keywords": ["iphone", "apple"], "purchased_days_ago": 160},
    {"device_id": "DEV-02", "model": "Samsung Galaxy S24", "keywords": ["samsung", "galaxy"], "purchased_days_ago": 210},
    {"device_id": "DEV-03", "model": "Google Pixel 8", "keywords": ["pixel", "google"], "purchased_days_ago": 120},
)

SALES_GENERIC_DEVICE_WORDS: frozenset[str] = frozenset({  # pragma: no cover
    "my", "the", "a", "an", "this", "it", "old", "new", "current", "phone", "cell", "cellphone", "smartphone",
    "mobile", "device", "handset", "mon", "ma", "le", "la", "un", "une", "ce", "téléphone", "telephone",
    "cellulaire", "appareil", "portable", "intelligent",
})

SALES_PLACEHOLDERS: frozenset[str] = frozenset(  # pragma: no cover
    {"", "unknown", "external", "none", "n/a", "na", "tbd", "pending", "not sure", "?", "inconnu", "aucun", "other", "autre"}
)

def _sales_placeholder(value: Any) -> bool:  # pragma: no cover
    return str(value if value is not None else "").strip().lower() in SALES_PLACEHOLDERS

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

def tracking_id(tool: str, *inputs: object) -> str:  # pragma: no cover
    """Return a reference number built from the tool name and its inputs.

    The same inputs always give the same number, so a retried call can't
    create a second record under a new number.
    """
    raw = "|".join([tool, *(str(value).strip().lower() for value in inputs)])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return "R" + str(int(digest[:8], 16) % 1_000_000).zfill(6)

def _sales_device(device: Any, issue: Any) -> tuple[dict[str, Any], bool]:  # pragma: no cover
    """Match the caller's words to a device on file.

    A model the caller names that isn't on file gets a record of its own (same default
    purchase age as the newest device), so a claim is never filed for a phone they don't
    own; only a generic "my phone" falls back to the most recent purchase.
    """
    text = f"{device or ''} {issue or ''}".lower()
    for dev in DEVICES_ON_FILE:
        if any(k in text for k in dev.get("keywords", [])) or str(dev["model"]).lower() in text:
            return dev, True
    newest = min(DEVICES_ON_FILE, key=lambda d: int(d["purchased_days_ago"]))
    named = " ".join(str(device or "").split())[:60]
    words = re.findall(r"[^\W_]+", named.lower())
    if _sales_placeholder(named) or all(w in SALES_GENERIC_DEVICE_WORDS for w in words):
        return newest, False
    device_id = "DEV-" + normalize_code(tracking_id("caller_device", named.lower()))
    return {"device_id": device_id, "model": named, "purchased_days_ago": newest["purchased_days_ago"]}, False

def _sales_has(text: str, words: tuple[str, ...] | frozenset[str]) -> bool:  # pragma: no cover
    low = str(text or "").lower()
    return any(w in low for w in words)

SALES_COPY: dict[str, dict[str, str]] = {  # pragma: no cover
    "contract_terms": {
        "en-US": "Month-to-month, no term contract and no activation fee. Prices are before tax.",
        "fr-CA": "Au mois, sans contrat à terme et sans frais d'activation. Les prix sont avant taxes.",
    },
    "activation_today": {
        "en-US": "Takes effect today, with no service interruption.",
        "fr-CA": "Prend effet aujourd'hui, sans interruption de service.",
    },
    "activation_next_day": {
        "en-US": "Takes effect the next business day; no technician visit is needed.",
        "fr-CA": "Prend effet le jour ouvrable suivant; aucune visite de technicien n'est requise.",
    },
    "after_data_cap": {
        "en-US": "After the high-speed data is used, data continues at a reduced speed with no overage fees.",
        "fr-CA": "Une fois les données haute vitesse utilisées, les données continuent à vitesse réduite, sans frais d'excédent.",
    },
    "proration": {
        "en-US": "This month's bill is prorated for the days on each plan.",
        "fr-CA": "La facture de ce mois-ci est calculée au prorata des jours passés sur chaque forfait.",
    },
    "coverage_unchecked": {
        "en-US": "Coverage at the service address is confirmed once the account is identified.",
        "fr-CA": "La couverture à l'adresse de service est confirmée une fois le compte identifié.",
    },
    "battery_safety": {
        "en-US": "For your safety, power the phone off now, unplug it, stop charging it, and keep it on a hard surface away from anything flammable. Don't press on the battery or mail the phone.",
        "fr-CA": "Pour votre sécurité, éteignez le téléphone maintenant, débranchez-le, cessez de le charger et posez-le sur une surface dure, loin de tout objet inflammable. N'appuyez pas sur la batterie et n'envoyez pas le téléphone par la poste.",
    },
    "return_standard": {
        "en-US": "The replacement comes with a prepaid return label. Back up the old phone, then send it back in the same box before the return deadline.",
        "fr-CA": "Le téléphone de remplacement arrive avec une étiquette de retour prépayée. Sauvegardez l'ancien téléphone, puis renvoyez-le dans la même boîte avant la date limite de retour.",
    },
    "return_urgent": {
        "en-US": "Do not ship the damaged phone. Bring it to a Telco store or a certified battery recycling drop-off; no return label is needed.",
        "fr-CA": "N'expédiez pas le téléphone endommagé. Apportez-le dans une boutique Telco ou à un point de dépôt certifié pour le recyclage des batteries; aucune étiquette de retour n'est nécessaire.",
    },
    "repair_paid": {
        "en-US": "Paid repair at a Telco repair centre",
        "fr-CA": "Réparation payante dans un centre de réparation Telco",
    },
    "repair_protection": {
        "en-US": "A claim with your device protection plan, if you have one",
        "fr-CA": "Une réclamation auprès de votre plan de protection d'appareil, si vous en avez un",
    },
    "repair_trade_in": {
        "en-US": "Trade-in credit toward a new phone",
        "fr-CA": "Un crédit d'échange applicable à un nouveau téléphone",
    },
    "port_keep_active": {
        "en-US": "Keep the service with the current provider active until the transfer is done; it closes automatically when the number moves.",
        "fr-CA": "Gardez le service actif chez le fournisseur actuel jusqu'à la fin du transfert; il se ferme automatiquement quand le numéro est transféré.",
    },
    "port_check_number": {
        "en-US": "The phone number you want to bring over",
        "fr-CA": "Le numéro de téléphone que vous voulez transférer",
    },
    "port_check_provider": {
        "en-US": "The name of the current provider",
        "fr-CA": "Le nom du fournisseur actuel",
    },
    "port_check_account": {
        "en-US": "The account number with that provider, from a recent bill",
        "fr-CA": "Le numéro de compte chez ce fournisseur, indiqué sur une facture récente",
    },
    "port_check_pin": {
        "en-US": "A transfer PIN, if that provider uses one",
        "fr-CA": "Un NIP de transfert, si ce fournisseur en utilise un",
    },
    "port_check_active": {
        "en-US": "Keep that service active; don't cancel it before the transfer",
        "fr-CA": "Gardez ce service actif; ne l'annulez pas avant le transfert",
    },
    "port_temporary_number": {
        "en-US": "The new line works right away on a temporary number until the transfer completes.",
        "fr-CA": "La nouvelle ligne fonctionne tout de suite avec un numéro temporaire jusqu'à la fin du transfert.",
    },
    "port_existing_line": {
        "en-US": "The transferred number replaces the current number on that line when the transfer completes.",
        "fr-CA": "Le numéro transféré remplacera le numéro actuel de cette ligne à la fin du transfert.",
    },
    "latency_fibre": {
        "en-US": "Fibre has low latency, typically under 10 milliseconds on a wired connection, well suited to video calls.",
        "fr-CA": "La fibre a une faible latence, habituellement moins de 10 millisecondes sur une connexion câblée, idéale pour les appels vidéo.",
    },
    "new_line_pricing": {
        "en-US": "Added as an additional line, the plan adds its own price to the account and the current line keeps its plan; as a plan change, it replaces the current mobile plan.",
        "fr-CA": "Ajouté comme ligne supplémentaire, le forfait ajoute son propre prix au compte et la ligne actuelle garde son forfait; comme changement de forfait, il remplace le forfait mobile actuel.",
    },
}

def resolve_locale(language: str | None) -> str:  # pragma: no cover
    """Normalize a language tag or prefix to a supported locale (en-US or fr-CA)."""
    low = str(language or "").strip().lower().replace("_", "-")
    if low.startswith("fr"):
        return "fr-CA"
    return "en-US"

resolve_copy_locale = resolve_locale  # pragma: no cover

def _sales_text(key: str, lang: str) -> str:  # pragma: no cover
    """Sales copy in the call language only (no sibling-language keys in replies)."""
    table = SALES_COPY.get(key, {})
    return table.get(resolve_copy_locale(lang)) or table.get("en-US", "")

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

def append_list(state: dict[str, Any], key: str, value: str) -> list[str]:  # pragma: no cover
    """Append to a comma-separated list stored in one STRING session variable."""
    items = [p for p in str(state.get(key) or "").split(",") if p]
    if value not in items:
        items.append(value)
    state[key] = ",".join(items)
    return items

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

def dispatch_sms(state: dict[str, Any], purpose: str) -> dict[str, Any]:  # pragma: no cover
    """Record a text message to the mobile number on file; returns its delivery facts."""
    dest = str(state.get("phone_last4") or account_record(state)["phone"][-4:])
    sent = [p for p in str(state.get("sms_sent") or "").split(",") if p]
    sent.append(purpose)
    state["sms_sent"] = ",".join(sent[-10:])
    return {"sms_sent": True, "destination_last4": dest, "sms_purpose": purpose}

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

def display_date(iso_date: str, lang: str = "en-US") -> str:  # pragma: no cover
    """Spoken date for an ISO date: 'Tuesday, March 4' / 'mardi 4 mars'."""
    try:
        d = datetime.strptime(str(iso_date)[:10], "%Y-%m-%d")
    except ValueError:
        return str(iso_date)
    if resolve_copy_locale(lang) == "fr-CA":
        return f"{_FR_DAYS[d.weekday()]} {d.day} {_FR_MONTHS[d.month - 1]}"
    return f"{_EN_DAYS[d.weekday()]}, {_EN_MONTHS[d.month - 1]} {d.day}"

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

def relative_date(days: int = 0) -> str:  # pragma: no cover
    """Return an ISO-8601 YYYY-MM-DD date relative to UTC today."""
    return (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%d")

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

def file_warranty_claim_impl(  # pragma: no cover
    device: str = "",
    issue: str = "",
    physical_damage: str | bool = "",
    water_damage: str | bool = "",
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Check warranty coverage for a device on file and file a replacement claim. Needs login."""
    state = get_state(state, session_state)
    lang = session_language(state, language)
    err = check_mock_error(state, lang, "file_warranty_claim")
    if err:
        return err
    urgent = _sales_has(f"{device or ''} {issue or ''}", SALES_SAFETY_WORDS)
    gate = require_login(state, lang, "file_warranty_claim")
    if gate:
        if urgent:
            gate["data"].update(
                {"urgent": True, "safety_advice_key": "battery_safety", "safety_advice": _sales_text("battery_safety", lang)}
            )
            gate["agent_action"] = "Say safety_advice now, then verify the caller and call again."
        return gate

    account_id = str(state.get("account_id") or "")
    dev, matched = _sales_device(device, issue)
    age = int(dev["purchased_days_ago"])
    if fixture(state, "fx_device_warranty") == "out_of_warranty":
        age = SALES_OUT_OF_WARRANTY_AGE_DAYS
    purchase_iso = relative_date(-age)
    end_iso = relative_date(DEVICE_WARRANTY_DAYS - age)
    in_warranty = age <= DEVICE_WARRANTY_DAYS
    reference = tracking_id("file_warranty_claim", account_id, dev["device_id"])
    state["last_tracking_id"] = reference
    base: dict[str, Any] = {
        "device_model": dev["model"],
        "device_matched": matched,
        "purchase_date": purchase_iso,
        "purchase_date_display": display_date(purchase_iso, lang),
        "warranty_end_date": end_iso,
        "warranty_end_display": display_date(end_iso, lang),
        "in_warranty": in_warranty,
        "urgent": urgent,
    }
    if urgent:
        base["safety_advice_key"] = "battery_safety"
        base["safety_advice"] = _sales_text("battery_safety", lang)

    physical = _sales_bool(physical_damage)
    water = _sales_bool(water_damage)
    repair = {
        "repair_options": [_sales_text(k, lang) for k in ("repair_paid", "repair_protection", "repair_trade_in")],
        **money(SALES_REPAIR_FEE, "repair_fee"),
    }
    if not urgent and (physical or water):
        return error_reply(
            "NOT_ELIGIBLE",
            "Physical or water damage is not covered by the warranty.",
            "Explain damage isn't covered and offer the repair_options.",
            reference,
            language=lang,
            data={**base, "not_covered_reason": "water_damage" if water else "physical_damage", **repair},
        )
    if not urgent and not in_warranty:
        return error_reply(
            "NOT_ELIGIBLE",
            "The device is out of warranty.",
            "Say the warranty ended on warranty_end_display and offer the repair_options.",
            reference,
            language=lang,
            data={**base, "not_covered_reason": "out_of_warranty", **repair},
        )
    if not urgent and (physical is None or water is None):
        missing = [name for name, val in (("physical_damage", physical), ("water_damage", water)) if val is None]
        reply = ok_reply({**base, "claim_filed": False, "damage_check_needed": True, "missing": missing}, reference, language=lang)
        reply["agent_action"] = "Confirm the device model and ask about physical or water damage, then call again."
        return reply
    if not urgent and not str(issue or "").strip():
        return validation_error(state, "No fault described.", "Ask what is wrong with the device.", reference, lang)

    claim_id = "WC-" + tracking_id("warranty_claim", account_id, dev["device_id"])[1:]
    ship_days = SALES_URGENT_SHIP_DAYS if urgent else SALES_WARRANTY_SHIP_DAYS
    eta_iso = _sales_business_date(ship_days)
    data: dict[str, Any] = {
        **base,
        "claim_id": claim_id,
        "claim_filed": True,
        "shipping": "expedited" if urgent else "standard",
        "replacement_eta_date": eta_iso,
        "replacement_eta_display": display_date(eta_iso, lang),
        "shipping_address_last_line": account_record(state).get("service_address_last_line", ""),
        "return_instructions": _sales_text("return_urgent" if urgent else "return_standard", lang),
    }
    if not urgent:
        return_by = relative_date(SALES_RETURN_WINDOW_DAYS + ship_days)
        data["return_by_display"] = display_date(return_by, lang)
    claims = [c for c in str(state.get("sales_claims") or "").split(",") if c]
    data["already_filed"] = claim_id in claims
    if not data["already_filed"]:
        append_list(state, "sales_claims", claim_id)
        data["sms_confirmation_sent"] = dispatch_sms(state, "warranty_claim")["sms_sent"]
    else:
        data["sms_confirmation_sent"] = True
    state["last_tracking_id"] = claim_id
    return ok_reply(data, claim_id, language=lang)
# --- END GENERATED SHARED BUNDLE ---
