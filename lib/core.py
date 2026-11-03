"""Shared helpers for every tool (docs/tdd.md §2). No tools live here.

Every tool impl starts with:
    state = get_state(state, session_state)
    lang = session_language(state, language)
    err = check_mock_error(state, lang, "<tool>")
and account tools then call require_login(state, lang, "<tool>").
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from lib.fakes import (
    ACCOUNTS,
    ALWAYS_OPEN_QUEUES,
    CURRENCY,
    FIXTURE_DEFAULTS,
    QUEUE_HOURS,
    BUSINESS_HOURS_QUEUES,
    read_count,
    relative_date,
    resolve_copy_locale,
    spoken_line,
)
from lib.replies import display_amount, error_reply, set_mock_mode_active, tracking_id

MAX_VALIDATION_ERRORS = 3

# No account found yet (require_login, lookup_account): a PIN already given beats asking again.
NO_ACCOUNT_ACTION = "If the caller already gave a 4-digit PIN, call check_secret_pin now; else say spoken_message."

SYSTEM_ERROR_CODES: frozenset[str] = frozenset(
    {"SYSTEM_UNAVAILABLE", "SYSTEM_DOWN", "INTERNAL_ERROR", "AUTH_SERVICE_UNAVAILABLE"}
)

MOCK_ERROR_OFF: frozenset[str] = frozenset({"false", "none", "0", "off", "no", "null"})

_FR_MONTHS = (
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)
_FR_DAYS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
_EN_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
_EN_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def get_state(
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the session state dict. A missing state gets a fresh dict, never a shared one.

    Also switches the PRD §17 mock_mode marker on or off for the replies of this call.
    """
    resolved = state if state is not None else (session_state if session_state is not None else {})
    set_mock_mode_active(mock_mode_on(resolved))
    return resolved


def session_language(state: dict[str, Any] | None, language: Any = "") -> str:
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


def fixture(state: dict[str, Any] | None, name: str) -> str:
    """Read a backend fixture (`fx_*`): the session override when set, else FIXTURE_DEFAULTS."""
    raw = ""
    if isinstance(state, dict):
        raw = str(state.get(name) or "").strip()
    if not raw:
        raw = FIXTURE_DEFAULTS.get(name, "")
    return raw.strip().lower() if name not in ("fx_pin_on_file", "fx_otp_on_file", "fx_extra_bill_line") else raw.strip()


def fixture_flag(state: dict[str, Any] | None, name: str) -> bool:
    """Read a true/false fixture."""
    return fixture(state, name) in ("true", "1", "yes")


def mock_mode_on(state: dict[str, Any] | None) -> bool:
    """PRD §17 eval-harness flag (scenario variableOverrides mock_mode="True").

    Every tool here already runs on the fake backend in lib/fakes.py, so mock mode
    changes no tool outcome; fixtures (fx_*) still apply and login is never mocked.
    """
    return isinstance(state, dict) and str(state.get("mock_mode") or "").strip().lower() == "true"


def check_mock_error(state: dict[str, Any], lang: str = "en-US", tool_name: str = "tool") -> dict[str, Any] | None:
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


def require_login(state: dict[str, Any], lang: str, tool_name: str) -> dict[str, Any] | None:
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


def validation_error(
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


def to_decimal(value: Any) -> Decimal | None:
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


def money(value: Any, prefix: str = "amount") -> dict[str, Any]:
    """Money as a number plus a 2-decimal display string (DESIGN_RULES rule 27)."""
    amount = to_decimal(value) or Decimal("0.00")
    return {prefix: float(amount), f"{prefix}_display": display_amount(amount), "currency": CURRENCY}


def display_date(iso_date: str, lang: str = "en-US") -> str:
    """Spoken date for an ISO date: 'Tuesday, March 4' / 'mardi 4 mars'."""
    try:
        d = datetime.strptime(str(iso_date)[:10], "%Y-%m-%d")
    except ValueError:
        return str(iso_date)
    if resolve_copy_locale(lang) == "fr-CA":
        return f"{_FR_DAYS[d.weekday()]} {d.day} {_FR_MONTHS[d.month - 1]}"
    return f"{_EN_DAYS[d.weekday()]}, {_EN_MONTHS[d.month - 1]} {d.day}"


def display_window(start: str, end: str, lang: str = "en-US") -> str:
    """Spoken time window: '1 PM to 5 PM' / 'entre 13 h et 17 h'."""
    def _en(t: str) -> str:
        h, m = (int(x) for x in t.split(":"))
        suffix = "AM" if h < 12 else "PM"
        h12 = h % 12 or 12
        return f"{h12} {suffix}" if m == 0 else f"{h12}:{m:02d} {suffix}"

    def _fr(t: str) -> str:
        h, m = (int(x) for x in t.split(":"))
        return f"{h} h" if m == 0 else f"{h} h {m:02d}"

    if resolve_copy_locale(lang) == "fr-CA":
        return f"entre {_fr(start)} et {_fr(end)}"
    return f"{_en(start)} to {_en(end)}"


def date_in(days: int, lang: str = "en-US") -> dict[str, str]:
    """An ISO date `days` from today plus its spoken form."""
    iso = relative_date(days)
    return {"date": iso, "date_display": display_date(iso, lang)}


def account_record(state: dict[str, Any]) -> dict[str, Any]:
    """The active account record, falling back to the default account."""
    account_id = str(state.get("account_id") or "")
    for record in ACCOUNTS:
        if record["account_id"] == account_id:
            return dict(record)
    base = dict(ACCOUNTS[0])
    if account_id:
        base["account_id"] = account_id
    return base


def ensure_account(state: dict[str, Any]) -> str:
    """Make sure an account is active (login tools fill the default; DESIGN_RULES rule 21)."""
    if not state.get("account_id"):
        state["account_id"] = ACCOUNTS[0]["account_id"]
        state["phone_last4"] = ACCOUNTS[0]["phone"][-4:]
        state["identification_status"] = "Pass"
    return str(state["account_id"])


def service_status(state: dict[str, Any]) -> str:
    """Current service status: the value tools wrote this call, else the backend fixture."""
    live = str(state.get("service_status") or "").strip()
    return live or fixture(state, "fx_service_status")


def dispatch_sms(state: dict[str, Any], purpose: str) -> dict[str, Any]:
    """Record a text message to the mobile number on file; returns its delivery facts."""
    dest = str(state.get("phone_last4") or account_record(state)["phone"][-4:])
    sent = [p for p in str(state.get("sms_sent") or "").split(",") if p]
    sent.append(purpose)
    state["sms_sent"] = ",".join(sent[-10:])
    return {"sms_sent": True, "destination_last4": dest, "sms_purpose": purpose}


def queue_open(queue: str, now: datetime | None = None) -> bool:
    """BR-TV-014: only sales and appointment queues follow QUEUE_HOURS (ET); all others are 24/7."""
    if queue in ALWAYS_OPEN_QUEUES or queue not in BUSINESS_HOURS_QUEUES:
        return True
    current = now or (datetime.now(timezone.utc) - timedelta(hours=5))
    day = "saturday" if current.weekday() == 5 else "sunday" if current.weekday() == 6 else "weekday"
    hours = QUEUE_HOURS.get(day, {}).get("specialist")
    if not hours:
        return False
    return hours[0] <= current.hour < hours[1]


def append_list(state: dict[str, Any], key: str, value: str) -> list[str]:
    """Append to a comma-separated list stored in one STRING session variable."""
    items = [p for p in str(state.get(key) or "").split(",") if p]
    if value not in items:
        items.append(value)
    state[key] = ",".join(items)
    return items
