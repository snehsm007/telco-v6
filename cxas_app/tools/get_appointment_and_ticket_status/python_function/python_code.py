from typing import Any



def get_appointment_and_ticket_status(
    language: str = "",
) -> dict[str, Any]:
    """Returns a logged-in caller's technician visits (date, window, status, technician ETA
      or delay), open repair tickets, and three open slots for a reschedule or a new
      visit.

    Args:
      language: Active language code (en-US or fr-CA).

    Returns:
      status, data (appointments, tickets, available_slots, visit_prep,
        visit_length_display), error_message, tracking_id.
        Errors add error (NOT_LOGGED_IN) and agent_action.
    """
    ctx = globals().get("context")
    state = getattr(ctx, "state", None) if ctx is not None else None
    if state is None and isinstance(ctx, dict):
        state = ctx
    return get_appointment_and_ticket_status_impl(
        language=language,
        state=state,
    )


# --- BEGIN GENERATED SHARED BUNDLE (edit lib/, then run `make bundle`) ---
# uses: from lib.tech import get_appointment_and_ticket_status_impl
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
import contextvars
import hashlib
import re
import unicodedata

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

def tracking_id(tool: str, *inputs: object) -> str:  # pragma: no cover
    """Return a reference number built from the tool name and its inputs.

    The same inputs always give the same number, so a retried call can't
    create a second record under a new number.
    """
    raw = "|".join([tool, *(str(value).strip().lower() for value in inputs)])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return "R" + str(int(digest[:8], 16) % 1_000_000).zfill(6)

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

TICKETS: tuple[dict[str, Any], ...] = (  # pragma: no cover
    {"ticket_id": "TKT-3318", "lob": "tv", "issue": "tv_no_picture", "status": "in_progress", "updated_days_ago": 1, "next_step": "technician_review"},
    {"ticket_id": "TKT-3342", "lob": "internet", "issue": "network_intermittent", "status": "open", "updated_days_ago": 0, "next_step": "network_team_investigating"},
)

_TECH_TICKET_ISSUES: dict[str, dict[str, str]] = {  # pragma: no cover
    "tv_no_picture": {"en-US": "TV has no picture", "fr-CA": "Aucune image à la télévision"},
    "network_intermittent": {"en-US": "Internet connection drops on and off", "fr-CA": "Connexion Internet intermittente"},
}

_TECH_TICKET_NEXT: dict[str, dict[str, str]] = {  # pragma: no cover
    "technician_review": {
        "en-US": "A technician is reviewing it; you'll get a text with the next update.",
        "fr-CA": "Un technicien l'examine; vous recevrez un texto avec la prochaine mise à jour.",
    },
    "network_team_investigating": {
        "en-US": "Our network team is investigating; you'll get a text when it's fixed.",
        "fr-CA": "Notre équipe réseau enquête; vous recevrez un texto une fois le problème réglé.",
    },
}

_TECH_TICKET_STATUS: dict[str, dict[str, str]] = {  # pragma: no cover
    "open": {"en-US": "open", "fr-CA": "ouvert"},
    "in_progress": {"en-US": "in progress", "fr-CA": "en cours de traitement"},
    "closed": {"en-US": "closed", "fr-CA": "fermé"},
}

def _tech_tickets(lang: str) -> list[dict[str, Any]]:  # pragma: no cover
    tickets = []
    for t in TICKETS:
        tickets.append({
            "ticket_id": t["ticket_id"],
            "lob": t["lob"],
            "issue": _tech_text(_TECH_TICKET_ISSUES.get(t["issue"], {"en-US": t["issue"]}), lang),
            "status": t["status"],
            "status_display": _tech_text(_TECH_TICKET_STATUS.get(t["status"], {"en-US": t["status"]}), lang),
            "last_update_display": display_date(relative_date(-int(t["updated_days_ago"])), lang),
            "next_step": _tech_text(_TECH_TICKET_NEXT.get(t["next_step"], {"en-US": ""}), lang),
        })
    return tickets

TECH_VISIT_LENGTH_HOURS: tuple[int, int] = (1, 2)  # pragma: no cover

_TECH_VISIT_PREP: dict[str, tuple[str, ...]] = {  # pragma: no cover
    "en-US": (
        "An adult needs to be home for the whole arrival window.",
        "Keep clear access to the equipment: the modem, receiver or phone jack, and the satellite dish for satellite TV.",
        "No documents or paperwork are needed.",
        "You'll get a text when the technician is on the way.",
    ),
    "fr-CA": (
        "Un adulte doit être à la maison pendant toute la plage d'arrivée.",
        "Gardez un accès dégagé à l'équipement : le modem, le récepteur ou la prise téléphonique, et l'antenne parabolique pour la télé par satellite.",
        "Aucun document n'est requis.",
        "Vous recevrez un texto quand le technicien sera en route.",
    ),
}

def _tech_visit_facts(lang: str) -> dict[str, Any]:  # pragma: no cover
    """What to prepare and how long a visit takes, so a booking follow-up stays grounded."""
    low, high = TECH_VISIT_LENGTH_HOURS
    if resolve_copy_locale(lang) == "fr-CA":
        length = f"environ {low} à {high} heures"
    else:
        length = f"about {low} to {high} hours"
    prep = _TECH_VISIT_PREP.get(resolve_copy_locale(lang)) or _TECH_VISIT_PREP["en-US"]
    return {"visit_prep": list(prep), "visit_length_display": length, "documents_needed": False}

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

def get_appointment_and_ticket_status_impl(  # pragma: no cover
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Technician visits, repair tickets and three open slots in one call."""
    state = get_state(state, session_state)
    lang = session_language(state, language)
    err = check_mock_error(state, lang, "get_appointment_and_ticket_status")
    if err:
        return err
    gate = require_login(state, lang, "get_appointment_and_ticket_status")
    if gate:
        return gate
    appts = _tech_appointments(state, lang)
    tickets = _tech_tickets(lang)
    reference = tracking_id(
        "get_appointment_and_ticket_status", state.get("account_id", ""),
        ",".join(f"{a['appointment_id']}:{a['status']}:{a['date']}" for a in appts),
    )
    state["last_tracking_id"] = reference
    if tickets:
        state["ticket_state"] = tickets[0]["status"]
    data = {
        "appointments": appts,
        "appointment_count": len(appts),
        "tickets": tickets,
        "ticket_count": len(tickets),
        "available_slots": _tech_public_slots(lang),
        **_tech_visit_facts(lang),
    }
    return ok_reply(data, reference, language=lang)
# --- END GENERATED SHARED BUNDLE ---
