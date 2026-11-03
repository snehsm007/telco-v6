from typing import Any



def manage_appointment(
    action: str = "",
    appointment_id: str | int | float = "",
    slot_id: str | int | float = "",
    confirmed: bool | str = "",
    note: str = "",
    language: str = "",
) -> dict[str, Any]:
    """Changes a technician visit for a logged-in caller: reschedule or book into one of
      the open slots, cancel (same-day cancel needs a second call with confirmed=true),
      or add a note for the technician. Sends a text confirmation.

    Args:
      action: reschedule, cancel, book or add_note.
      appointment_id: Visit to change; empty = the caller's only active visit.
      slot_id: slot_id from available_slots, for reschedule or book.
      confirmed: true only after the caller confirmed the cancellation.
      note: For add_note: what the technician should know.
      language: Active language code (en-US or fr-CA).

    Returns:
      status, data (appointment_id, new_date_display, new_window_display, cancelled,
        note_added, sms_confirmation_sent, available_slots), error_message, tracking_id.
        Errors add error (CONFIRMATION_REQUIRED, TECHNICIAN_EN_ROUTE, NOT_ELIGIBLE,
        INVALID_INPUT, NOT_FOUND, NOT_LOGGED_IN) and agent_action.
    """
    ctx = globals().get("context")
    state = getattr(ctx, "state", None) if ctx is not None else None
    if state is None and isinstance(ctx, dict):
        state = ctx
    return manage_appointment_impl(
        action=action,
        appointment_id=appointment_id,
        slot_id=slot_id,
        confirmed=confirmed,
        note=note,
        language=language,
        state=state,
    )


# --- BEGIN GENERATED SHARED BUNDLE (edit lib/, then run `make bundle`) ---
# uses: from lib.tech import manage_appointment_impl
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
import hashlib
import re

_TECH_ACTIONS: dict[str, str] = {  # pragma: no cover
    "reschedule": "reschedule", "rebook": "reschedule", "move": "reschedule", "change": "reschedule",
    "cancel": "cancel", "annuler": "cancel",
    "book": "book", "schedule": "book", "new": "book",
    "add_note": "add_note", "note": "add_note", "addnote": "add_note",
}

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

def _tech_add_note(  # pragma: no cover
    state: dict[str, Any], appt: dict[str, Any], note: Any, reference: str, lang: str,
) -> dict[str, Any]:
    text = " ".join(str(note or "").split())[:200]
    if not text:
        return validation_error(
            state, "The note is empty.", "Ask what the caller wants the technician to know.", reference, lang,
        )
    if appt["status"] == "cancelled":
        return error_reply(
            "NOT_ELIGIBLE", "This visit was cancelled.",
            "Offer to book a new visit with action book.", reference, language=lang,
            data={"appointment_id": appt["appointment_id"]},
        )
    state["appt_note"] = text
    return ok_reply(
        {"appointment_id": appt["appointment_id"], "note_added": True, "technician_notified": True},
        reference,
        language=lang,
    )

APPOINTMENT = {  # pragma: no cover
    "appointment_id": "APT-4471",
    "service_type": "internet",
    "visit_type": "installation",
    "days_from_today": 0,
    "window": ("13:00", "17:00"),
    "delay_minutes": 60,
}

TECH_DEFAULT_BOOKING_SERVICE = "repair"  # pragma: no cover

TECH_EN_ROUTE_ETA_MINUTES = 25  # pragma: no cover

_TECH_SERVICE_NAMES: dict[str, dict[str, str]] = {  # pragma: no cover
    "internet": {"en-US": "internet", "fr-CA": "Internet"},
    "tv": {"en-US": "TV", "fr-CA": "télévision"},
    "mobility": {"en-US": "mobile", "fr-CA": "mobile"},
    "homephone": {"en-US": "home phone", "fr-CA": "téléphone résidentiel"},
    "smarthome": {"en-US": "smart home", "fr-CA": "maison intelligente"},
    "repair": {"en-US": "repair", "fr-CA": "réparation"},
}

_TECH_STATUS_NOTES: dict[str, dict[str, str]] = {  # pragma: no cover
    "scheduled": {"en-US": "The visit is confirmed.", "fr-CA": "La visite est confirmée."},
    "en_route": {
        "en-US": "The technician is on the way.",
        "fr-CA": "Le technicien est en route.",
    },
    "delayed": {
        "en-US": "The technician is running late. The visit can be moved to another day.",
        "fr-CA": "Le technicien est en retard. La visite peut être déplacée à un autre jour.",
    },
    "en_route_delayed": {
        "en-US": "The technician is on the way but delayed and running late. The visit can be moved to another day.",
        "fr-CA": "Le technicien est en route, mais il est retardé. La visite peut être déplacée à un autre jour.",
    },
    "cancelled": {"en-US": "The visit is cancelled.", "fr-CA": "La visite est annulée."},
}

_TECH_VISIT_TYPES: dict[str, dict[str, str]] = {  # pragma: no cover
    "installation": {"en-US": "installation", "fr-CA": "installation"},
    "repair": {"en-US": "repair visit", "fr-CA": "visite de réparation"},
}

def resolve_locale(language: str | None) -> str:  # pragma: no cover
    """Normalize a language tag or prefix to a supported locale (en-US or fr-CA)."""
    low = str(language or "").strip().lower().replace("_", "-")
    if low.startswith("fr"):
        return "fr-CA"
    return "en-US"

resolve_copy_locale = resolve_locale  # pragma: no cover

def _tech_text(table: dict[str, str], lang: str) -> str:  # pragma: no cover
    """Pick the caller's language from a {locale: text} table."""
    return table.get(resolve_copy_locale(lang)) or table.get("en-US", "")

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

def display_window(start: str, end: str, lang: str = "en-US") -> str:  # pragma: no cover
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

def _tech_appt_record(  # pragma: no cover
    appt_id: str, service: str, visit: str, iso: str, start: str, end: str,
    status: str, lang: str, today: str,
) -> dict[str, Any]:
    active = status in ("scheduled", "delayed")
    # Running late while on the way: the delay allows moving the visit to another
    # day, but a technician already en route cannot be cancelled (prd.md §13).
    movable = active or status == "en_route_delayed"
    return {
        "appointment_id": appt_id,
        "service_type": service,
        "service_display": _tech_text(_TECH_SERVICE_NAMES.get(service, _TECH_SERVICE_NAMES["repair"]), lang),
        "visit_type_display": _tech_text(_TECH_VISIT_TYPES.get(visit, _TECH_VISIT_TYPES["repair"]), lang),
        "date": iso,
        "date_display": display_date(iso, lang),
        "is_today": iso == today,
        "window_display": display_window(start, end, lang),
        "status": status,
        "status_note": _tech_text(_TECH_STATUS_NOTES[status], lang),
        "technician_eta_display": "",
        "delay_minutes": 0,
        "can_reschedule": movable,
        "can_cancel": active,
        "can_add_note": status != "cancelled",
    }

def _tech_booked_id(state: dict[str, Any]) -> str:  # pragma: no cover
    return "APT-" + tracking_id("book", state.get("account_id", ""))[-4:]

def _tech_hours(hours: int, lang: str) -> str:  # pragma: no cover
    if resolve_copy_locale(lang) == "fr-CA":
        return f"environ {hours} heure" + ("s" if hours > 1 else "")
    return f"about {hours} hour" + ("s" if hours > 1 else "")

def _tech_minutes(minutes: int, lang: str) -> str:  # pragma: no cover
    if minutes % 60 == 0:
        return _tech_hours(minutes // 60, lang)
    if resolve_copy_locale(lang) == "fr-CA":
        return f"environ {minutes} minutes"
    return f"about {minutes} minutes"

def _tech_shift(hhmm: str, minutes: int) -> str:  # pragma: no cover
    h, m = (int(x) for x in hhmm.split(":"))
    total = min(h * 60 + m + minutes, 23 * 60 + 59)
    return f"{total // 60:02d}:{total % 60:02d}"

SLOT_OFFSETS_DAYS: tuple[int, ...] = (1, 2, 4)  # pragma: no cover

SLOT_WINDOWS: tuple[tuple[str, str], ...] = (("08:00", "12:00"), ("12:00", "16:00"), ("16:00", "20:00"))  # pragma: no cover

def relative_date(days: int = 0) -> str:  # pragma: no cover
    """Return an ISO-8601 YYYY-MM-DD date relative to UTC today."""
    return (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%d")

def _tech_slots(lang: str) -> list[dict[str, Any]]:  # pragma: no cover
    """The three bookable slots (rule 34: bundled with the status lookup)."""
    slots = []
    for idx, offset in enumerate(SLOT_OFFSETS_DAYS):
        start, end = SLOT_WINDOWS[idx % len(SLOT_WINDOWS)]
        iso = relative_date(offset)
        slots.append({
            "slot_id": f"SLOT-{idx + 1}",
            "date": iso,
            "date_display": display_date(iso, lang),
            "window_display": display_window(start, end, lang),
            "start": start,
            "end": end,
        })
    return slots

def _tech_slot_by_id(slot_id: str, lang: str) -> dict[str, Any] | None:  # pragma: no cover
    return next((s for s in _tech_slots(lang) if s["slot_id"] == slot_id), None)

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

def _tech_appointments(state: dict[str, Any], lang: str) -> list[dict[str, Any]]:  # pragma: no cover
    """The caller's appointments: backend record + fixture status + changes made on this call."""
    today = relative_date(0)
    base_status = fixture(state, "fx_technician_status")
    if base_status not in ("scheduled", "en_route", "delayed", "en_route_delayed"):
        base_status = "scheduled"
    appt_state = str(state.get("appt_state") or "")
    start, end = APPOINTMENT["window"]
    iso = relative_date(int(APPOINTMENT["days_from_today"]))
    status = base_status
    slot = _tech_slot_by_id(str(state.get("appt_slot_id") or ""), lang) if appt_state == "rescheduled" else None
    if slot:
        iso, start, end, status = slot["date"], slot["start"], slot["end"], "scheduled"
    if appt_state == "cancelled":
        status = "cancelled"
    service = str(APPOINTMENT["service_type"])
    main = _tech_appt_record(
        str(APPOINTMENT["appointment_id"]), service, str(APPOINTMENT["visit_type"]),
        iso, start, end, status, lang, today,
    )
    if status in ("delayed", "en_route_delayed"):
        delay = int(APPOINTMENT["delay_minutes"])
        main["delay_minutes"] = delay
        main["delay_display"] = _tech_minutes(delay, lang)
        revised = display_window(_tech_shift(start, delay), _tech_shift(end, delay), lang)
        main["technician_eta_display"] = revised
        main["revised_window_display"] = revised
    elif status == "en_route":
        main["technician_eta_display"] = (
            f"dans {_tech_minutes(TECH_EN_ROUTE_ETA_MINUTES, lang)}" if resolve_copy_locale(lang) == "fr-CA"
            else f"in {_tech_minutes(TECH_EN_ROUTE_ETA_MINUTES, lang)}"
        )
    if str(state.get("appt_note") or ""):
        main["note_on_file"] = True
    appts = [main]
    booked = _tech_slot_by_id(str(state.get("booked_slot_id") or ""), lang)
    if booked:
        booked_service = str(state.get("lob") or TECH_DEFAULT_BOOKING_SERVICE)
        appts.append(_tech_appt_record(
            _tech_booked_id(state), booked_service, "repair",
            booked["date"], booked["start"], booked["end"], "scheduled", lang, today,
        ))
    return appts

def _tech_public_slots(lang: str) -> list[dict[str, Any]]:  # pragma: no cover
    """Slots as the model sees them (no raw clock times)."""
    return [{k: v for k, v in s.items() if k not in ("start", "end")} for s in _tech_slots(lang)]

def _tech_bad_slot(state: dict[str, Any], reference: str, lang: str) -> dict[str, Any]:  # pragma: no cover
    return validation_error(
        state, "That slot is not one of the open slots.",
        "Offer only the listed slots; if none suit, offer a text when a slot opens.",
        reference, lang, data={"available_slots": _tech_public_slots(lang)},
    )

def _tech_find_slot(raw: Any, lang: str) -> dict[str, Any] | None:  # pragma: no cover
    """Match a slot by id ("SLOT-2"), ordinal ("2", "slot 2", "option 2") or ISO date; None when unknown."""
    text = re.sub(r"\.0+$", "", str(raw or "").strip()).lower()
    if not text:
        return None
    slots = _tech_slots(lang)
    m = re.fullmatch(r"(?:slot|option|créneau|plage)?[\s_#\-]*(\d)", text)
    if m:
        idx = int(m.group(1)) - 1
        return slots[idx] if 0 <= idx < len(slots) else None
    for slot in slots:
        if text == slot["date"]:
            return slot
    return None

def _tech_slot_required(appt_id: str, reference: str, lang: str) -> dict[str, Any]:  # pragma: no cover
    reply = ok_reply(
        {"appointment_id": appt_id, "slot_required": True, "available_slots": _tech_public_slots(lang)},
        reference, language=lang,
    )
    reply["agent_action"] = "Offer these slots and ask which one suits the caller."
    return reply

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

def dispatch_sms(state: dict[str, Any], purpose: str) -> dict[str, Any]:  # pragma: no cover
    """Record a text message to the mobile number on file; returns its delivery facts."""
    dest = str(state.get("phone_last4") or account_record(state)["phone"][-4:])
    sent = [p for p in str(state.get("sms_sent") or "").split(",") if p]
    sent.append(purpose)
    state["sms_sent"] = ",".join(sent[-10:])
    return {"sms_sent": True, "destination_last4": dest, "sms_purpose": purpose}

def _tech_sms_once(state: dict[str, Any], purpose: str) -> dict[str, Any]:  # pragma: no cover
    """Text a confirmation once per purpose (a retried call never sends a second text)."""
    sent = [p for p in str(state.get("sms_sent") or "").split(",") if p]
    if purpose in sent:
        return {"sms_sent": True, "destination_last4": str(state.get("phone_last4") or account_record(state)["phone"][-4:])}
    return dispatch_sms(state, purpose)

def _tech_book(state: dict[str, Any], slot_id: Any, reference: str, lang: str) -> dict[str, Any]:  # pragma: no cover
    new_id = _tech_booked_id(state)
    if not str(slot_id or "").strip():
        return _tech_slot_required(new_id, reference, lang)
    slot = _tech_find_slot(slot_id, lang)
    if slot is None:
        return _tech_bad_slot(state, reference, lang)
    state["booked_slot_id"] = slot["slot_id"]
    sms = _tech_sms_once(state, f"appointment_booked_{slot['slot_id'].lower()}")
    confirmation = tracking_id("book", state.get("account_id", ""), slot["slot_id"])
    state["last_tracking_id"] = confirmation
    service = str(state.get("lob") or TECH_DEFAULT_BOOKING_SERVICE)
    return ok_reply(
        {
            "appointment_id": new_id,
            "booked": True,
            "service_type": service,
            "slot_id": slot["slot_id"],
            "new_date": slot["date"],
            "new_date_display": slot["date_display"],
            "new_window_display": slot["window_display"],
            "confirmation_id": confirmation,
            "sms_confirmation_sent": True,
            "destination_last4": sms["destination_last4"],
        },
        confirmation,
        language=lang,
    )

def _tech_truthy(value: Any) -> bool:  # pragma: no cover
    return str(value).strip().lower() in ("true", "1", "yes", "oui", "y")

def _tech_cancel(  # pragma: no cover
    state: dict[str, Any], appt: dict[str, Any], confirmed: Any, reference: str, lang: str,
) -> dict[str, Any]:
    pending_key = f"cancel:{appt['appointment_id']}"
    is_confirmed = _tech_truthy(confirmed)
    if appt["is_today"]:
        ready = is_confirmed and state.get("pending_confirmation") == pending_key
    else:
        ready = is_confirmed
    if not ready:
        state["pending_confirmation"] = pending_key
        return error_reply(
            "CONFIRMATION_REQUIRED",
            "Same-day cancellation needs a second confirmation." if appt["is_today"] else "Cancellation needs confirmation.",
            "Read back the visit date and window, ask to confirm the cancellation, then call with confirmed=true.",
            reference,
            language=lang,
            data={
                "appointment_id": appt["appointment_id"],
                "same_day": appt["is_today"],
                "date_display": appt["date_display"],
                "window_display": appt["window_display"],
            },
        )
    if appt["appointment_id"] == str(APPOINTMENT["appointment_id"]):
        state["appt_state"] = "cancelled"
    else:
        state["booked_slot_id"] = ""
    state["pending_confirmation"] = ""
    sms = _tech_sms_once(state, f"appointment_cancelled_{appt['appointment_id'].lower()}")
    confirmation = tracking_id("cancel", state.get("account_id", ""), appt["appointment_id"])
    state["last_tracking_id"] = confirmation
    return ok_reply(
        {
            "appointment_id": appt["appointment_id"],
            "cancelled": True,
            "cancellation_id": confirmation,
            "sms_confirmation_sent": True,
            "destination_last4": sms["destination_last4"],
        },
        confirmation,
        language=lang,
    )

def _tech_pick_appt(appts: list[dict[str, Any]], raw_id: Any) -> dict[str, Any] | None:  # pragma: no cover
    wanted = re.sub(r"\.0+$", "", str(raw_id or "").strip()).upper()
    if not wanted:
        live = [a for a in appts if a["status"] != "cancelled"]
        return (live or appts)[0] if len(live) <= 1 else None
    digits = re.sub(r"\D", "", wanted)
    for a in appts:
        if wanted == a["appointment_id"] or (digits and a["appointment_id"].endswith(digits)):
            return a
    return None

def _tech_reschedule(  # pragma: no cover
    state: dict[str, Any], appt: dict[str, Any], slot_id: Any, reference: str, lang: str,
) -> dict[str, Any]:
    if not str(slot_id or "").strip():
        return _tech_slot_required(appt["appointment_id"], reference, lang)
    slot = _tech_find_slot(slot_id, lang)
    if slot is None:
        return _tech_bad_slot(state, reference, lang)
    if appt["appointment_id"] != str(APPOINTMENT["appointment_id"]):
        state["booked_slot_id"] = slot["slot_id"]
    else:
        state["appt_state"] = "rescheduled"
        state["appt_slot_id"] = slot["slot_id"]
    state["pending_confirmation"] = ""
    sms = _tech_sms_once(state, f"appointment_rescheduled_{slot['slot_id'].lower()}")
    confirmation = tracking_id("reschedule", state.get("account_id", ""), appt["appointment_id"], slot["slot_id"])
    state["last_tracking_id"] = confirmation
    return ok_reply(
        {
            "appointment_id": appt["appointment_id"],
            "rescheduled": True,
            "slot_id": slot["slot_id"],
            "new_date": slot["date"],
            "new_date_display": slot["date_display"],
            "new_window_display": slot["window_display"],
            "confirmation_id": confirmation,
            "sms_confirmation_sent": True,
            "destination_last4": sms["destination_last4"],
        },
        confirmation,
        language=lang,
    )

MOCK_ERROR_OFF: frozenset[str] = frozenset({"false", "none", "0", "off", "no", "null"})  # pragma: no cover

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

def manage_appointment_impl(  # pragma: no cover
    action: str = "",
    appointment_id: str | int | float = "",
    slot_id: str | int | float = "",
    confirmed: bool | str = False,
    note: str = "",
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Reschedule, cancel, book or add a note to a technician visit."""
    state = get_state(state, session_state)
    lang = session_language(state, language)
    err = check_mock_error(state, lang, "manage_appointment")
    if err:
        return err
    gate = require_login(state, lang, "manage_appointment")
    if gate:
        return gate
    account_id = str(state.get("account_id") or "")
    act = _TECH_ACTIONS.get(re.sub(r"[\s\-]+", "_", str(action or "").strip().lower()), "")
    reference = tracking_id("manage_appointment", account_id, act, appointment_id, slot_id)
    state["last_tracking_id"] = reference
    if not act:
        return validation_error(
            state, "Unknown appointment action.",
            "Use reschedule, cancel, book or add_note.", reference, lang,
        )
    if act == "book":
        return _tech_book(state, slot_id, reference, lang)
    appts = _tech_appointments(state, lang)
    appt = _tech_pick_appt(appts, appointment_id)
    if appt is None:
        return validation_error(
            state, "That appointment was not found.",
            "Ask which visit they mean, by service type.", reference, lang, code="NOT_FOUND",
            data={"appointments": [{"appointment_id": a["appointment_id"], "service_display": a["service_display"],
                                    "date_display": a["date_display"]} for a in appts]},
        )
    if act == "add_note":
        return _tech_add_note(state, appt, note, reference, lang)
    if appt["status"] == "en_route" or (appt["status"] == "en_route_delayed" and act == "cancel"):
        late = appt["status"] == "en_route_delayed"
        return error_reply(
            "TECHNICIAN_EN_ROUTE",
            "The technician is already on the way, so the visit can't be "
            + ("cancelled; it can be moved to another day." if late else "changed."),
            "Explain the technician is on the way; offer to move the visit to another day or add a note."
            if late else "Explain the technician is on the way and offer to add a note for them.",
            reference,
            language=lang,
            data={"appointment_id": appt["appointment_id"], "technician_eta_display": appt["technician_eta_display"],
                  "can_add_note": True, "can_reschedule": late},
        )
    if appt["status"] == "cancelled" and act == "cancel":
        return ok_reply({"appointment_id": appt["appointment_id"], "cancelled": True, "already_cancelled": True},
                        reference, language=lang)
    if appt["status"] == "cancelled":
        return error_reply(
            "NOT_ELIGIBLE", "This visit was cancelled.",
            "Offer to book a new visit with action book.", reference, language=lang,
            data={"appointment_id": appt["appointment_id"]},
        )
    if act == "cancel":
        return _tech_cancel(state, appt, confirmed, reference, lang)
    return _tech_reschedule(state, appt, slot_id, reference, lang)
# --- END GENERATED SHARED BUNDLE ---
