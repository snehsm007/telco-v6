"""Fake backend for local tests and cloud evals: the Telco Voice Central world.

Only this file holds fake records (AGENTS.md Hard Rule 16). Tools read it through
lib/services.py and the domain modules, never directly from prompts.

Design (docs/tdd.md §5-6, DESIGN_RULES rules 21-22, 40, 44, 45):
  - Fact-less simulated callers give numbers this world doesn't know, so any
    structurally valid 9- or 10-digit number resolves to a synthetic record.
  - Per-customer backend facts (card status, suspension, technician status, ...)
    have defaults in FIXTURE_DEFAULTS and can be seeded per conversation through
    `fx_*` session variables (an eval scenario's variableOverrides).
  - Login follows the ladder in login_code_accepted unless a fixture names the
    exact credential on file.
  - Dates are relative to UTC today (relative_date); never literal calendar dates.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any

SUPPORTED_LOCALES: tuple[str, ...] = ("en-US", "fr-CA")

# Verbatim copy library (prd.md §7) plus operational lines. French lines and the
# two Legal placeholders (payment_method_preamble,
# contract_cancellation_fee_disclosure) are interim wording PENDING LEGAL APPROVAL
# (docs/requirements.md decision A6).
SPOKEN_LINES: dict[str, dict[str, str]] = {
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

# Fixture defaults (docs/tdd.md §5): what the backend reports when no `fx_*`
# session variable overrides it.
FIXTURE_DEFAULTS: dict[str, str] = {
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

CURRENCY = "CAD"
SELF_SERVE_ADJUSTMENT_LIMIT = "25.00"
REFUND_WINDOW_BUSINESS_DAYS = 2
PASSWORD_RESET_VALID_MINUTES = 30
OTP_EXPIRES_IN_SEC = 300

# Specialist queue hours (decision A8), Eastern Time. Outage and fraud are 24/7.
QUEUE_HOURS: dict[str, dict[str, tuple[int, int]]] = {
    "weekday": {"specialist": (8, 20)},
    "saturday": {"specialist": (9, 17)},
    "sunday": {},
}
ALWAYS_OPEN_QUEUES: frozenset[str] = frozenset({"fraud", "outage", "general"})

ACCOUNTS: tuple[dict[str, Any], ...] = (
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

# Monthly service prices on the default account (used for bills and outage credits).
SERVICE_PRICES: dict[str, str] = {
    "mobility": "65.00",
    "internet": "85.50",
    "tv": "42.00",
    "homephone": "28.00",
}

# Latest bill line items, beyond the monthly service charges above. The streaming
# purchase matches the brief's sample dispute transcript (prd.md §10).
BILL_EXTRA_LINES: tuple[dict[str, Any], ...] = (
    {"charge_id": "CH-STR-01", "description": "AppleStreaming purchase", "amount": "12.50", "lob": "tv", "days_ago": 7},
    {"charge_id": "CH-LD-01", "description": "Long distance calls", "amount": "18.40", "lob": "mobility", "days_ago": 12},
)
BILL_CYCLE_DAYS_AGO = 3      # latest bill issued 3 days ago
BILL_DUE_IN_DAYS = 18        # due 18 days from today
PAST_DUE_AMOUNT = "87.65"    # unpaid from the previous cycle
LAST_PAYMENT = {"amount": "140.00", "days_ago": 32, "method": "card_on_file"}
DUPLICATE_PAYMENT = {"amount": "140.00", "days_ago": 5, "method": "card_on_file"}

# Plan catalogue (prd.md §12: never present more than 3).
PLANS: tuple[dict[str, Any], ...] = (
    {"plan_id": "MOB-20", "lob": "mobility", "name": "Essential 20", "price": "47.00", "data_gb": 20, "features": ["20 GB high-speed data", "Unlimited Canada-wide calling"]},
    {"plan_id": "MOB-50", "lob": "mobility", "name": "Plus 50", "price": "58.00", "data_gb": 50, "features": ["50 GB high-speed data", "Unlimited Canada-wide calling", "5G access"]},
    {"plan_id": "MOB-100", "lob": "mobility", "name": "Max 100", "price": "72.00", "data_gb": 100, "features": ["100 GB high-speed data", "Canada-US calling", "5G+ access"]},
    {"plan_id": "MOB-UNL", "lob": "mobility", "name": "Unlimited Premium", "price": "89.00", "data_gb": 175, "features": ["175 GB high-speed data", "Canada-US-Mexico calling", "5G+ access"]},
    {"plan_id": "INT-1G", "lob": "internet", "name": "Fibre 1 Gigabit", "price": "97.00", "speed_mbps": 1000, "features": ["Up to 1 Gbps download", "Unlimited usage", "Wi-Fi 6 gateway"]},
    {"plan_id": "INT-3G", "lob": "internet", "name": "Fibre 3 Gigabit", "price": "118.00", "speed_mbps": 3000, "features": ["Up to 3 Gbps download", "Unlimited usage", "Wi-Fi 6E gateway", "Whole-home Wi-Fi pod"]},
    {"plan_id": "INT-8G", "lob": "internet", "name": "Fibre 8 Gigabit", "price": "143.00", "speed_mbps": 8000, "features": ["Up to 8 Gbps download", "Unlimited usage", "Wi-Fi 7 gateway", "Two Wi-Fi pods"]},
    {"plan_id": "TV-SPORTS", "lob": "tv", "name": "Sports Pack", "price": "16.00", "addon": True, "keywords": ["sport", "hockey", "football", "soccer", "basketball", "baseball"], "features": ["National sports networks", "Regional game coverage", "Sports on demand"]},
    {"plan_id": "TV-MOVIES", "lob": "tv", "name": "Movies Pack", "price": "13.00", "addon": True, "keywords": ["movie", "film", "cinema", "cinéma"], "features": ["Premium movie channels", "Movies on demand"]},
    {"plan_id": "TV-PLUS", "lob": "tv", "name": "TV Plus Package", "price": "61.00", "addon": False, "keywords": ["package", "channels", "upgrade"], "features": ["Over 150 channels", "Cloud PVR"]},
)
CURRENT_PLANS: dict[str, str] = {"mobility": "Plus 50 Legacy", "internet": "Fibre 500", "tv": "TV Basic", "homephone": "Home Phone Lite"}
CURRENT_SPEED_MBPS = 500
CURRENT_DATA_GB = 15

# Devices on the account (prd.md §12 warranty). Purchase dates relative to today.
DEVICES_ON_FILE: tuple[dict[str, Any], ...] = (
    {"device_id": "DEV-01", "model": "Apple iPhone 15", "keywords": ["iphone", "apple"], "purchased_days_ago": 160},
    {"device_id": "DEV-02", "model": "Samsung Galaxy S24", "keywords": ["samsung", "galaxy"], "purchased_days_ago": 210},
    {"device_id": "DEV-03", "model": "Google Pixel 8", "keywords": ["pixel", "google"], "purchased_days_ago": 120},
)
DEVICE_WARRANTY_DAYS = 365

# Appointments and tickets (prd.md §13).
APPOINTMENT = {
    "appointment_id": "APT-4471",
    "service_type": "internet",
    "visit_type": "installation",
    "days_from_today": 0,
    "window": ("13:00", "17:00"),
    "delay_minutes": 60,
}
TICKETS: tuple[dict[str, Any], ...] = (
    {"ticket_id": "TKT-3318", "lob": "tv", "issue": "tv_no_picture", "status": "in_progress", "updated_days_ago": 1, "next_step": "technician_review"},
    {"ticket_id": "TKT-3342", "lob": "internet", "issue": "network_intermittent", "status": "open", "updated_days_ago": 0, "next_step": "network_team_investigating"},
)
SLOT_OFFSETS_DAYS: tuple[int, ...] = (1, 2, 4)
SLOT_WINDOWS: tuple[tuple[str, str], ...] = (("08:00", "12:00"), ("12:00", "16:00"), ("16:00", "20:00"))
# --- tech fixtures ---
# Minutes until an en-route technician arrives (fx_technician_status=en_route).
TECH_EN_ROUTE_ETA_MINUTES = 25
# Service type of a visit booked on this call when the repair line is unknown.
TECH_DEFAULT_BOOKING_SERVICE = "repair"
# --- end tech fixtures ---

# Outage regions (BR-TV-003, DESIGN_RULES rule 40: classes, not literals).
# Canadian postal codes start with a province letter; Region-A is Quebec.
REGION_BY_POSTAL_LETTER: dict[str, str] = {
    **{letter: "Region-A" for letter in "GHJ"},
    **{letter: "Region-B" for letter in "KLMNP"},
}
DEFAULT_REGION = "Region-C"
ACTIVE_OUTAGES: dict[str, dict[str, Any]] = {
    "Region-A": {"outage_id": "OUT-A-27", "services": ["internet", "tv"], "eta_hours": 4},
}
FIXTURE_OUTAGE = {"outage_id": "OUT-LOCAL-09", "services": ["internet", "tv"], "eta_hours": 3}

# Credentials (DESIGN_RULES rules 21, 45). Non-canonical values only.
ALWAYS_WRONG_LOGIN_CODES: frozenset[str] = frozenset({"9999", "999999", "8888"})
VALID_OTPS: frozenset[str] = frozenset({"271846", "482913"})
VALID_PINS: frozenset[str] = frozenset({"5903", "5678"})
VALID_LOGIN_CODES: frozenset[str] = VALID_OTPS | VALID_PINS
DECLINED_CARD_LAST4: frozenset[str] = frozenset({"0000", "9999"})  # overfit: allow
BLOCKED_CALLER_NUMBERS: frozenset[str] = frozenset({"9005550199"})
ARRANGEMENT_INSTALMENTS = 2
ARRANGEMENT_SECOND_DUE_DAYS = 30


def resolve_locale(language: str | None) -> str:
    """Normalize a language tag or prefix to a supported locale (en-US or fr-CA)."""
    low = str(language or "").strip().lower().replace("_", "-")
    if low.startswith("fr"):
        return "fr-CA"
    return "en-US"


resolve_copy_locale = resolve_locale


def relative_date(days: int = 0) -> str:
    """Return an ISO-8601 YYYY-MM-DD date relative to UTC today."""
    return (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%d")


def spoken_line(key: str, language: str | None = "en-US", **slots: object) -> str:
    """Return the fixed spoken line for `key` and `language`, filling any `[slot]` placeholders."""
    locale = resolve_locale(language)
    table = SPOKEN_LINES.get(key, {})
    template = table.get(locale) or table.get("en-US") or ""
    for slot_name, slot_val in slots.items():
        template = template.replace(f"[{slot_name}]", str(slot_val))
    return template


def normalize_code(value: Any) -> str:
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


def only_digits(text: Any) -> str:
    """Keep the digits of what the caller said ("(202) 555-0143" -> "2025550143")."""
    return normalize_code(text)


def read_count(state: dict[str, Any] | None, key: str) -> int:
    """Read a whole-number variable; the platform hands them to tools as decimals (5 -> 5.0)."""
    if not isinstance(state, dict):
        return 0
    try:
        return int(float(state.get(key) or 0))
    except (TypeError, ValueError):
        return 0


def is_weak_code(digits: str) -> bool:
    """A code made of one repeated digit (e.g. all sevens) is never a valid credential."""
    return bool(digits) and len(set(digits)) == 1


def is_plausible_phone(digits: str) -> bool:
    """North American number plan check: area code and exchange start with 2-9, not one repeated digit."""
    if len(digits) != 10 or not digits.isdigit():
        return False
    if digits[0] in "01" or digits[3] in "01":
        return False
    if is_weak_code(digits) or digits in ("1234567890", "0123456789", "9876543210"):
        return False
    return True


def normalize_identifier(raw: object) -> dict[str, str]:
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


def _synthetic_account(account_number: str, phone: str) -> dict[str, Any]:
    """A record for a well-formed number this world doesn't know (fact-less simulated callers)."""
    base = dict(ACCOUNTS[0])
    base["account_id"] = "A" + account_number[-6:]
    base["phone"] = phone
    base["first_name"] = ""
    return base


def find_account(identifier: Any) -> dict[str, Any] | None:
    """Find an account by phone number or account number; None when the number is malformed."""
    raw_str = re.sub(r"\.0+$", "", str(identifier or "").strip())
    raw = raw_str.upper()
    if not raw:
        return None
    has_alpha = any(c.isalpha() for c in raw_str)
    digits = normalize_code(raw_str)
    for record in ACCOUNTS:
        if raw == record["account_id"] or (not has_alpha and digits and digits == record["phone"]):
            return dict(record)
    norm = normalize_identifier(raw_str)
    if norm["kind"] == "phone":
        if not is_plausible_phone(norm["value"]):
            return None
        return _synthetic_account(norm["value"], norm["value"])
    if norm["kind"] == "international_phone":
        tail = norm["value"].lstrip("+")[-10:]
        return _synthetic_account(tail, tail) if len(tail) == 10 else None
    if not has_alpha and len(digits) == 9 and not is_weak_code(digits):
        return _synthetic_account(digits, ACCOUNTS[0]["phone"])
    if norm["kind"] == "reference" and re.fullmatch(r"A\d{4,8}", norm["value"].replace("-", "")):
        return _synthetic_account(normalize_code(norm["value"]), ACCOUNTS[0]["phone"])
    return None


def login_code_accepted(code_digits: Any, attempts: int = 0, max_attempts: int = 3) -> bool:
    """Whether the fake login service accepts a code on this try (the login ladder).

    `attempts` is the number of wrong tries so far on this call:
      - weak codes (one repeated digit) and ALWAYS_WRONG_LOGIN_CODES never pass;
      - first try (attempts == 0): any 4- to 8-digit code;
      - second try: only VALID_LOGIN_CODES;
      - the last try (attempts == max_attempts - 1): always wrong.
    Lookups with a credential on file (fx_pin_on_file / fx_otp_on_file) bypass
    the ladder in lib/services.py and compare exactly.
    """
    digits = normalize_code(code_digits)
    if not (4 <= len(digits) <= 8):
        return False
    if digits in ALWAYS_WRONG_LOGIN_CODES or is_weak_code(digits):
        return False
    if attempts >= max(max_attempts - 1, 1):
        return False
    if attempts >= 1:
        return digits in VALID_LOGIN_CODES
    return True


def secret_pin_accepted(pin_digits: Any, attempts: int = 0, max_attempts: int = 3) -> bool:
    """Whether the fake login service accepts a secret PIN (the same ladder as login codes)."""
    return login_code_accepted(pin_digits, attempts=attempts, max_attempts=max_attempts)
