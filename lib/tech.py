"""Tech support and appointment tools (docs/tdd.md §4, prd.md §11, §13, §15).

Tools return data, never sentences. Step text, issue text and status notes are
data in the caller's locked language (en-US / fr-CA), never sibling keys.
Appointment changes made on a call live in session state (appt_state,
appt_slot_id, appt_note, booked_slot_id, pending_confirmation) so every call
starts from the backend facts in lib/fakes.py and the fx_* fixtures.
"""

from __future__ import annotations

import re
from typing import Any

from lib.core import (
    account_record,
    check_mock_error,
    dispatch_sms,
    display_date,
    display_window,
    fixture,
    get_state,
    require_login,
    session_language,
    validation_error,
)
from lib.fakes import (
    ACTIVE_OUTAGES,
    APPOINTMENT,
    CURRENT_DATA_GB,
    CURRENT_DATA_USED_GB,
    DEFAULT_REGION,
    FIXTURE_OUTAGE,
    REGION_BY_POSTAL_LETTER,
    SLOT_OFFSETS_DAYS,
    SLOT_WINDOWS,
    TECH_DEFAULT_BOOKING_SERVICE,
    TECH_EN_ROUTE_ETA_MINUTES,
    TICKETS,
    relative_date,
    resolve_copy_locale,
    spoken_line,
)
from lib.replies import error_reply, ok_reply, tracking_id

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_TECH_LOBS = ("mobility", "internet", "tv", "homephone", "smarthome")
_TECH_LOB_ALIASES: dict[str, str] = {
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
# Lob inferred from the symptom when the model passes none (order matters).
_TECH_LOB_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("homephone", ("home phone", "landline", "dial tone", "tonalité", "ligne fixe", "téléphone résidentiel")),
    ("tv", ("tv", "télé", "television", "télévision", "receiver", "récepteur", "channel", "chaîne", "satellite")),
    ("smarthome", ("smart home", "camera", "caméra", "sensor", "capteur", "alarm", "maison intelligente")),
    ("mobility", ("cell", "mobile", "portable", "cellulaire", "sim", "5g", "lte", "données mobiles", "mobile data")),
    ("internet", ("internet", "wifi", "wi-fi", "modem", "router", "routeur")),
)


def _tech_text(table: dict[str, str], lang: str) -> str:
    """Pick the caller's language from a {locale: text} table."""
    return table.get(resolve_copy_locale(lang)) or table.get("en-US", "")


def _tech_has(text: str, words: tuple[str, ...]) -> bool:
    """True when any keyword starts a word in text (prefix match, accents kept)."""
    return any(re.search(r"(?<![\w])" + re.escape(w), text) for w in words)


def _tech_lob(raw: Any, symptom: str = "") -> str:
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


def _tech_hours(hours: int, lang: str) -> str:
    if resolve_copy_locale(lang) == "fr-CA":
        return f"environ {hours} heure" + ("s" if hours > 1 else "")
    return f"about {hours} hour" + ("s" if hours > 1 else "")


def _tech_minutes(minutes: int, lang: str) -> str:
    if minutes % 60 == 0:
        return _tech_hours(minutes // 60, lang)
    if resolve_copy_locale(lang) == "fr-CA":
        return f"environ {minutes} minutes"
    return f"about {minutes} minutes"


def _tech_shift(hhmm: str, minutes: int) -> str:
    h, m = (int(x) for x in hhmm.split(":"))
    total = min(h * 60 + m + minutes, 23 * 60 + 59)
    return f"{total // 60:02d}:{total % 60:02d}"


# ---------------------------------------------------------------------------
# check_regional_outage
# ---------------------------------------------------------------------------

_TECH_CA_FIRST = "ABCEGHJKLMNPRSTVXY"
_TECH_CA_LETTER = "ABCEGHJKLMNPRSTVWXYZ"
_TECH_POSTAL_RE = re.compile(
    rf"[{_TECH_CA_FIRST}]\d[{_TECH_CA_LETTER}]\d[{_TECH_CA_LETTER}]\d"
)
_TECH_DIGIT_FIXES = {"O": "0", "I": "1", "L": "1"}


def _tech_parse_postal(raw: Any) -> tuple[str, str]:
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


def _tech_region(kind: str, code: str) -> str:
    if kind == "postal":
        return REGION_BY_POSTAL_LETTER.get(code[:1], DEFAULT_REGION)
    return DEFAULT_REGION


def _tech_area_outage(state: dict[str, Any], region: str) -> dict[str, Any] | None:
    """The outage affecting a region: fixture override first, else the regional table."""
    status = fixture(state, "fx_outage_status")
    if status == "active":
        return dict(FIXTURE_OUTAGE)
    if status == "none":
        return None
    found = ACTIVE_OUTAGES.get(region)
    return dict(found) if found else None


def check_regional_outage_impl(
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
    outage = _tech_area_outage(state, region)
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


# ---------------------------------------------------------------------------
# run_virtual_repair: troubleshooting catalogue (data, not speech)
# ---------------------------------------------------------------------------

_TECH_GENERIC_WORDS = (
    "not working", "doesn't work", "does not work", "isn't working", "stopped working",
    "won't work", "broken", "down", "problem", "issue", "trouble",
    "ne fonctionne", "fonctionne pas", "fonctionne plus", "marche pas", "marche plus",
    "en panne", "problème", "brisé", "défectueu",
)
_TECH_ERROR_CODE_RE = re.compile(r"(?:error|erreur|code)\s*(?:code\s*)?(?:#|no\.?|n°)?\s*(\d{2,4})\b", re.IGNORECASE)

# Each step list is {locale: [steps]}. Keys are category ids; "variants" key by tv_sub_type.
_TECH_STEPS: dict[str, dict[str, list[str]]] = {
    "internet_down": {
        "en-US": [
            "Check that the modem's power cable is plugged into a working outlet.",
            "Unplug the modem for thirty seconds, then plug it back in.",
            "Wait about five minutes until the internet light is solid white or blue.",
            "Reconnect your device to Wi-Fi and open a website.",
        ],
        "fr-CA": [
            "Vérifiez que le câble d'alimentation du modem est branché dans une prise qui fonctionne.",
            "Débranchez le modem pendant trente secondes, puis rebranchez-le.",
            "Attendez environ cinq minutes que le voyant Internet soit blanc ou bleu fixe.",
            "Reconnectez votre appareil au Wi-Fi et ouvrez un site Web.",
        ],
    },
    "internet_slow": {
        "en-US": [
            "Restart the modem: unplug it for thirty seconds, then plug it back in.",
            "Move closer to the modem or remove anything blocking it.",
            "Disconnect devices you are not using from the Wi-Fi.",
            "Run a speed test on a device connected by cable to compare.",
        ],
        "fr-CA": [
            "Redémarrez le modem : débranchez-le trente secondes, puis rebranchez-le.",
            "Rapprochez-vous du modem ou retirez ce qui l'obstrue.",
            "Déconnectez du Wi-Fi les appareils que vous n'utilisez pas.",
            "Faites un test de vitesse sur un appareil branché par câble pour comparer.",
        ],
    },
    "mobile_no_service": {
        "en-US": [
            "Turn airplane mode on for fifteen seconds, then turn it off.",
            "Restart your phone.",
            "In network settings, set network selection to automatic.",
            "Check that the SIM card is seated properly, then restart again.",
        ],
        "fr-CA": [
            "Activez le mode avion pendant quinze secondes, puis désactivez-le.",
            "Redémarrez votre téléphone.",
            "Dans les réglages réseau, choisissez la sélection automatique du réseau.",
            "Vérifiez que la carte SIM est bien insérée, puis redémarrez de nouveau.",
        ],
    },
    "mobile_slow_data": {
        "en-US": [
            "Check that mobile data is on and you are not over your data limit.",
            "Turn airplane mode on for fifteen seconds, then turn it off.",
            "Reset the network settings on your phone.",
            "Restart your phone and try loading a page again.",
        ],
        "fr-CA": [
            "Vérifiez que les données cellulaires sont activées et que votre limite n'est pas atteinte.",
            "Activez le mode avion pendant quinze secondes, puis désactivez-le.",
            "Réinitialisez les réglages réseau de votre téléphone.",
            "Redémarrez votre téléphone et essayez de charger une page de nouveau.",
        ],
    },
    "mobile_sim": {
        "en-US": [
            "Turn the phone off, take out the SIM card and put it back in firmly.",
            "Turn the phone back on and wait for the network to appear.",
        ],
        "fr-CA": [
            "Éteignez le téléphone, retirez la carte SIM et réinsérez-la bien.",
            "Rallumez le téléphone et attendez que le réseau s'affiche.",
        ],
    },
    "tv_no_signal:streaming": {
        "en-US": [
            "Check that the HDMI cable is firmly connected at the TV and the receiver.",
            "Use the TV remote to select the input the receiver is connected to.",
            "Unplug the receiver for thirty seconds, then plug it back in.",
            "Check that the modem is online, since the receiver needs the internet.",
        ],
        "fr-CA": [
            "Vérifiez que le câble HDMI est bien branché au téléviseur et au récepteur.",
            "Avec la télécommande du téléviseur, choisissez l'entrée où le récepteur est branché.",
            "Débranchez le récepteur pendant trente secondes, puis rebranchez-le.",
            "Vérifiez que le modem est en ligne, car le récepteur a besoin d'Internet.",
        ],
    },
    "tv_no_signal:satellite": {
        "en-US": [
            "Check that the HDMI cable and the coaxial cable are tight on the receiver.",
            "Use the TV remote to select the input the receiver is connected to.",
            "Unplug the receiver for thirty seconds, then plug it back in.",
            "Check that nothing like snow, ice or branches blocks the dish.",
        ],
        "fr-CA": [
            "Vérifiez que le câble HDMI et le câble coaxial sont bien serrés sur le récepteur.",
            "Avec la télécommande du téléviseur, choisissez l'entrée où le récepteur est branché.",
            "Débranchez le récepteur pendant trente secondes, puis rebranchez-le.",
            "Vérifiez que rien, comme de la neige, de la glace ou des branches, ne bloque l'antenne.",
        ],
    },
    "tv_no_signal:streaming_only": {
        "en-US": [
            "Check that your streaming device is connected to the internet.",
            "Close the TV app completely and open it again.",
            "Restart your streaming device.",
        ],
        "fr-CA": [
            "Vérifiez que votre appareil de diffusion est connecté à Internet.",
            "Fermez complètement l'application télé et rouvrez-la.",
            "Redémarrez votre appareil de diffusion.",
        ],
    },
    "tv_error_code:satellite": {
        "en-US": [
            "Check that the dish has a clear view of the sky, with no snow, ice or branches in the way.",
            "Check that the coaxial cable is hand-tight on the back of the receiver.",
            "Unplug the receiver for fifteen seconds, then plug it back in.",
            "Allow up to ten minutes for the receiver to find the signal and reload the guide.",
        ],
        "fr-CA": [
            "Vérifiez que l'antenne voit bien le ciel, sans neige, glace ni branches devant.",
            "Vérifiez que le câble coaxial est bien serré à la main à l'arrière du récepteur.",
            "Débranchez le récepteur pendant quinze secondes, puis rebranchez-le.",
            "Attendez jusqu'à dix minutes que le récepteur capte le signal et recharge le guide.",
        ],
    },
    "tv_error_code:streaming": {
        "en-US": [
            "Unplug the receiver for thirty seconds, then plug it back in.",
            "Check that the modem is online and its internet light is solid.",
            "If the error comes back, note the code shown on the screen.",
        ],
        "fr-CA": [
            "Débranchez le récepteur pendant trente secondes, puis rebranchez-le.",
            "Vérifiez que le modem est en ligne et que son voyant Internet est fixe.",
            "Si l'erreur revient, notez le code affiché à l'écran.",
        ],
    },
    "tv_error_code:streaming_only": {
        "en-US": [
            "Sign out of the TV app, then sign back in.",
            "Update the TV app to the latest version.",
            "Restart your streaming device.",
        ],
        "fr-CA": [
            "Déconnectez-vous de l'application télé, puis reconnectez-vous.",
            "Mettez l'application télé à jour avec la dernière version.",
            "Redémarrez votre appareil de diffusion.",
        ],
    },
    "tv_app_freezing": {
        "en-US": [
            "Close the TV app completely, then open it again.",
            "Clear the app's cache in your device settings, or uninstall and reinstall the app.",
            "Restart your streaming device.",
            "Check your internet speed, or move the device closer to the modem.",
        ],
        "fr-CA": [
            "Fermez complètement l'application télé, puis rouvrez-la.",
            "Videz le cache de l'application dans les réglages de l'appareil, ou désinstallez et réinstallez l'application.",
            "Redémarrez votre appareil de diffusion.",
            "Vérifiez votre vitesse Internet ou rapprochez l'appareil du modem.",
        ],
    },
    "homephone_no_dial_tone": {
        "en-US": [
            "Check that the phone cord is firmly plugged into the wall jack or modem.",
            "Try another phone or another jack to see if the line works.",
            "Unplug the phone base for thirty seconds, then plug it back in.",
            "If your home phone runs through the modem, restart the modem.",
        ],
        "fr-CA": [
            "Vérifiez que le cordon du téléphone est bien branché dans la prise murale ou le modem.",
            "Essayez un autre téléphone ou une autre prise pour voir si la ligne fonctionne.",
            "Débranchez la base du téléphone pendant trente secondes, puis rebranchez-la.",
            "Si votre téléphone résidentiel passe par le modem, redémarrez le modem.",
        ],
    },
    "homephone_noise": {
        "en-US": [
            "Try a different phone cord, and unplug other devices sharing the line.",
            "Move the cordless phone base away from other electronics.",
        ],
        "fr-CA": [
            "Essayez un autre cordon et débranchez les autres appareils sur la ligne.",
            "Éloignez la base du téléphone sans fil des autres appareils électroniques.",
        ],
    },
    "smarthome_offline": {
        "en-US": [
            "Check that the smart home hub is plugged in and online.",
            "Unplug the hub for thirty seconds, then plug it back in.",
            "In the app, remove the device and pair it again.",
        ],
        "fr-CA": [
            "Vérifiez que le concentrateur de maison intelligente est branché et en ligne.",
            "Débranchez le concentrateur pendant trente secondes, puis rebranchez-le.",
            "Dans l'application, retirez l'appareil et jumelez-le de nouveau.",
        ],
    },
}

# Symptom categories per lob, checked in order; the first entry is the lob's default.
_TECH_CATEGORIES: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "internet": (
        ("internet_down", ("no internet", "offline", "no connection", "can't connect", "cannot connect",
                           "disconnected", "pas d'internet", "hors ligne", "aucune connexion", "connexion",
                           "wifi", "wi-fi", "internet")),
        ("internet_slow", ("slow", "lent", "lag", "buffer", "intermittent", "drop", "cuts out", "keeps cutting",
                           "coupe", "instable", "speed", "vitesse", "déconnect")),
    ),
    "mobility": (
        ("mobile_no_service", ("no service", "no signal", "no network", "no bars", "sos", "emergency only",
                               "can't make calls", "cannot make calls", "aucun service", "pas de service",
                               "pas de réseau", "plus de réseau", "aucun réseau", "pas de signal",
                               "aucun signal", "réseau", "network", "signal", "appel", "calls")),
        ("mobile_slow_data", ("data", "données", "slow", "lent", "pages", "load", "browsing", "navigation", "internet", "web",
                              "5g", "lte", "4g")),
        ("mobile_sim", ("sim", "puk")),
    ),
    "tv": (
        ("tv_no_signal", ("no signal", "aucun signal", "pas de signal", "black screen", "écran noir",
                          "no picture", "pas d'image", "aucune image", "blank screen", "signal")),
        ("tv_error_code", ()),  # matched by _TECH_ERROR_CODE_RE
        ("tv_app_freezing", ("freez", "frozen", "buffer", "gel", "fige", "figé", "plante", "crash", "stutter",
                             "saccad", "lag", "keeps stopping", "app", "application")),
    ),
    "homephone": (
        ("homephone_no_dial_tone", ("dial tone", "tonalité", "dead line", "ligne morte", "no sound",
                                    "can't call", "cannot call", "aucun son")),
        ("homephone_noise", ("static", "crackl", "noise", "bruit", "grésill", "echo", "écho")),
    ),
    "smarthome": (
        ("smarthome_offline", ("offline", "hors ligne", "camera", "caméra", "sensor", "capteur", "alarm",
                               "alarme", "not responding", "ne répond", "disconnected", "déconnect")),
    ),
}

_TECH_SUB_TYPES = ("streaming", "satellite", "streaming_only")
_TECH_REMOTE_RESET_TARGET = {
    "internet": "modem",
    "tv": "receiver",
    "homephone": "line",
    "mobility": "network_registration",
    "smarthome": "hub",
}
_TECH_KNOWN_ISSUES: dict[str, dict[str, str]] = {
    "satellite_signal_loss": {
        "en-US": "Error codes on a satellite receiver usually mean it lost the satellite signal, often because something blocks the dish.",
        "fr-CA": "Les codes d'erreur sur un récepteur satellite indiquent habituellement une perte du signal satellite, souvent parce que quelque chose bloque l'antenne.",
    },
    "streaming_app_device": {
        "en-US": "The TV app runs on your own device, so no remote reset can be sent to it.",
        "fr-CA": "L'application télé fonctionne sur votre propre appareil, donc aucune réinitialisation à distance ne peut lui être envoyée.",
    },
}


_TECH_DATA_NOTES: dict[str, dict[str, str]] = {
    "usage": {
        "en-US": "This cycle you've used {used} GB of your {total} GB of high-speed data, so your speed is {state}.",
        "fr-CA": "Pendant ce cycle, vous avez utilisé {used} Go de vos {total} Go de données haute vitesse; votre vitesse {state}.",
    },
    "not_slowed": {"en-US": "not being reduced", "fr-CA": "n'est donc pas réduite"},
    "slowed": {"en-US": "reduced until the next cycle", "fr-CA": "est donc réduite jusqu'au prochain cycle"},
    "throttling": {
        "en-US": "After the high-speed data is used, data continues at a reduced speed with no overage fees; a plan with more data restores full speed.",
        "fr-CA": "Une fois les données haute vitesse utilisées, les données continuent à vitesse réduite, sans frais d'excédent; un forfait avec plus de données rétablit la pleine vitesse.",
    },
}


def _tech_data_usage(lang: str) -> dict[str, Any]:
    """Mobile data usage facts for a slow-data repair, so a usage question stays in tech support."""
    slowed = CURRENT_DATA_USED_GB >= CURRENT_DATA_GB
    usage = _tech_text(_TECH_DATA_NOTES["usage"], lang).format(
        used=CURRENT_DATA_USED_GB,
        total=CURRENT_DATA_GB,
        state=_tech_text(_TECH_DATA_NOTES["slowed" if slowed else "not_slowed"], lang),
    )
    return {"data_speed_reduced": slowed, "data_usage_note": usage, "throttling_note": _tech_text(_TECH_DATA_NOTES["throttling"], lang)}


def _tech_sub_type(raw: Any, symptom: str) -> str:
    """Normalize the TV sub-type; only an explicit satellite mention is inferred from the symptom."""
    clean = re.sub(r"[\s\-]+", "_", str(raw or "").strip().lower())
    if clean in _TECH_SUB_TYPES:
        return clean
    if "satellite" in clean or "satell" in clean:
        return "satellite"
    if clean in ("app", "app_only", "streaming_app", "streaming_device", "application", "own_device"):
        return "streaming_only"
    if clean.startswith("stream") and "only" in clean:
        return "streaming_only"
    if clean.startswith("stream") or clean in ("iptv", "fibre", "receiver", "box"):
        return "streaming"
    if _tech_has(symptom, ("satellite", "parabol", "dish")):
        return "satellite"
    return ""


def _tech_category(lob: str, symptom: str) -> tuple[str, bool]:
    """(category id, matched). Unmatched symptoms fall back to the lob's default with matched=False."""
    categories = _TECH_CATEGORIES[lob]
    default = categories[0][0]
    if lob == "tv" and _TECH_ERROR_CODE_RE.search(symptom):
        return "tv_error_code", True
    ordered = list(categories)
    if lob == "internet":
        ordered = [categories[1], categories[0]]  # "slow" wins over generic connection words
    for cat_id, words in ordered:
        if words and _tech_has(symptom, words):
            return cat_id, True
    if not symptom.strip() or _tech_has(symptom, _TECH_GENERIC_WORDS):
        return default, True
    return default, False


def _tech_steps_for(category: str, sub_type: str, lang: str) -> list[str]:
    table = _TECH_STEPS.get(f"{category}:{sub_type}") or _TECH_STEPS.get(category)
    if table is None:  # tv categories without a variant for this sub-type
        table = _TECH_STEPS[f"{category}:streaming"]
    return list(table.get(resolve_copy_locale(lang)) or table["en-US"])


def run_virtual_repair_impl(
    lob: str = "",
    symptom: str = "",
    tv_sub_type: str = "",
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Open a virtual-repair session: area outage check, remote reset, localized steps."""
    state = get_state(state, session_state)
    lang = session_language(state, language)
    err = check_mock_error(state, lang, "run_virtual_repair")
    if err:
        return err
    gate = require_login(state, lang, "run_virtual_repair")
    if gate:
        return gate
    text = " ".join(str(symptom or "").lower().split())
    service = _tech_lob(lob, text) or _tech_lob(state.get("lob"), text)
    account_id = str(state.get("account_id") or "")
    reference = tracking_id("run_virtual_repair", account_id, service, text)
    state["last_tracking_id"] = reference
    if service not in _TECH_LOBS:
        return validation_error(
            state,
            "The service with the problem is not clear.",
            "Ask which service has the problem: mobile, internet, TV, home phone or smart home.",
            reference,
            lang,
        )
    state["lob"] = service
    sub_type = ""
    if service == "tv":
        sub_type = _tech_sub_type(tv_sub_type, text) or _tech_sub_type(state.get("tv_sub_type"), "")
        if not sub_type:
            return error_reply(
                "TV_SUB_TYPE_REQUIRED",
                "The TV service type is needed first.",
                "Ask if their TV is through a receiver (streaming), satellite, or the app only.",
                reference,
                language=lang,
                data={"lob": "tv", "allowed_sub_types": list(_TECH_SUB_TYPES)},
            )
        state["tv_sub_type"] = sub_type
    region = _tech_region(*_tech_parse_postal(account_record(state).get("postal_code", "")))
    outage = _tech_area_outage(state, region)
    if outage and service in outage["services"]:
        state["outage_active"] = True
        return error_reply(
            "OUTAGE_ACTIVE",
            "An active outage affects this service at the address on file.",
            "Say spoken_message (the outage_active line) word for word; on yes, text outage_updates.",
            reference,
            language=lang,
            data={
                "spoken_message": spoken_line("outage_active", lang),
                "outage_active": True,
                "affected_services": list(outage["services"]),
                "restoration_eta_display": _tech_hours(int(outage["eta_hours"]), lang),
                "outage_id": outage["outage_id"],
            },
        )
    category, matched = _tech_category(service, text)
    steps = _tech_steps_for(category, sub_type, lang)
    remote_reset = not (service == "tv" and sub_type == "streaming_only")
    known_issue = None
    error_code = ""
    if category == "tv_error_code":
        found = _TECH_ERROR_CODE_RE.search(text)
        error_code = found.group(1) if found else ""
        if sub_type == "satellite":
            known_issue = {"issue": "satellite_signal_loss", "note": _tech_text(_TECH_KNOWN_ISSUES["satellite_signal_loss"], lang)}
    if not remote_reset:
        known_issue = known_issue or {"issue": "streaming_app_device", "note": _tech_text(_TECH_KNOWN_ISSUES["streaming_app_device"], lang)}
    session_id = "VR-" + reference[1:]
    state["vr_session_id"] = session_id
    state["vr_task_count"] = len(steps)
    data: dict[str, Any] = {
        "session_id": session_id,
        "lob": service,
        "tv_sub_type": sub_type,
        "symptom_category": category,
        "catalogue_match": matched,
        "error_code": error_code,
        "area_outage_checked": True,
        "remote_reset_sent": remote_reset,
        "remote_reset_target": _TECH_REMOTE_RESET_TARGET[service] if remote_reset else "",
        "steps": steps,
        "first_step": steps[0] if steps else "",
        "step_count": len(steps),
        "sms_recommended": len(steps) > 2,
        "known_issue": known_issue,
        "if_unresolved": ["technician_visit", "live_agent"],
    }
    if category == "mobile_slow_data":
        data.update(_tech_data_usage(lang))
    reply = ok_reply(data, reference, language=lang)
    if not matched and resolve_copy_locale(lang) == "fr-CA":
        reply["agent_action"] = "Not in the French repair catalogue: hand over with reason secondary_language_live_agent."
    elif not matched:
        reply["agent_action"] = "Symptom not in the catalogue: offer these general steps, then a technician visit."
    elif len(steps) > 2:
        reply["agent_action"] = "Offer to text these steps (troubleshooting_guide) before reading them."
    else:
        reply["agent_action"] = "Walk the caller through these steps briefly."
    return reply


# ---------------------------------------------------------------------------
# Appointments and tickets
# ---------------------------------------------------------------------------

_TECH_TICKET_ISSUES: dict[str, dict[str, str]] = {
    "tv_no_picture": {"en-US": "TV has no picture", "fr-CA": "Aucune image à la télévision"},
    "network_intermittent": {"en-US": "Internet connection drops on and off", "fr-CA": "Connexion Internet intermittente"},
}
_TECH_TICKET_STATUS: dict[str, dict[str, str]] = {
    "open": {"en-US": "open", "fr-CA": "ouvert"},
    "in_progress": {"en-US": "in progress", "fr-CA": "en cours de traitement"},
    "closed": {"en-US": "closed", "fr-CA": "fermé"},
}
_TECH_TICKET_NEXT: dict[str, dict[str, str]] = {
    "technician_review": {
        "en-US": "A technician is reviewing it; you'll get a text with the next update.",
        "fr-CA": "Un technicien l'examine; vous recevrez un texto avec la prochaine mise à jour.",
    },
    "network_team_investigating": {
        "en-US": "Our network team is investigating; you'll get a text when it's fixed.",
        "fr-CA": "Notre équipe réseau enquête; vous recevrez un texto une fois le problème réglé.",
    },
}
_TECH_STATUS_NOTES: dict[str, dict[str, str]] = {
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
_TECH_SERVICE_NAMES: dict[str, dict[str, str]] = {
    "internet": {"en-US": "internet", "fr-CA": "Internet"},
    "tv": {"en-US": "TV", "fr-CA": "télévision"},
    "mobility": {"en-US": "mobile", "fr-CA": "mobile"},
    "homephone": {"en-US": "home phone", "fr-CA": "téléphone résidentiel"},
    "smarthome": {"en-US": "smart home", "fr-CA": "maison intelligente"},
    "repair": {"en-US": "repair", "fr-CA": "réparation"},
}
_TECH_VISIT_TYPES: dict[str, dict[str, str]] = {
    "installation": {"en-US": "installation", "fr-CA": "installation"},
    "repair": {"en-US": "repair visit", "fr-CA": "visite de réparation"},
}


def _tech_slots(lang: str) -> list[dict[str, Any]]:
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


def _tech_public_slots(lang: str) -> list[dict[str, Any]]:
    """Slots as the model sees them (no raw clock times)."""
    return [{k: v for k, v in s.items() if k not in ("start", "end")} for s in _tech_slots(lang)]


def _tech_find_slot(raw: Any, lang: str) -> dict[str, Any] | None:
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


def _tech_slot_by_id(slot_id: str, lang: str) -> dict[str, Any] | None:
    return next((s for s in _tech_slots(lang) if s["slot_id"] == slot_id), None)


def _tech_appointments(state: dict[str, Any], lang: str) -> list[dict[str, Any]]:
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


def _tech_booked_id(state: dict[str, Any]) -> str:
    return "APT-" + tracking_id("book", state.get("account_id", ""))[-4:]


def _tech_appt_record(
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


def _tech_tickets(lang: str) -> list[dict[str, Any]]:
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


def get_appointment_and_ticket_status_impl(
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
    }
    return ok_reply(data, reference, language=lang)


# ---------------------------------------------------------------------------
# manage_appointment
# ---------------------------------------------------------------------------

_TECH_ACTIONS: dict[str, str] = {
    "reschedule": "reschedule", "rebook": "reschedule", "move": "reschedule", "change": "reschedule",
    "cancel": "cancel", "annuler": "cancel",
    "book": "book", "schedule": "book", "new": "book",
    "add_note": "add_note", "note": "add_note", "addnote": "add_note",
}


def _tech_truthy(value: Any) -> bool:
    return str(value).strip().lower() in ("true", "1", "yes", "oui", "y")


def _tech_pick_appt(appts: list[dict[str, Any]], raw_id: Any) -> dict[str, Any] | None:
    wanted = re.sub(r"\.0+$", "", str(raw_id or "").strip()).upper()
    if not wanted:
        live = [a for a in appts if a["status"] != "cancelled"]
        return (live or appts)[0] if len(live) <= 1 else None
    digits = re.sub(r"\D", "", wanted)
    for a in appts:
        if wanted == a["appointment_id"] or (digits and a["appointment_id"].endswith(digits)):
            return a
    return None


def _tech_sms_once(state: dict[str, Any], purpose: str) -> dict[str, Any]:
    """Text a confirmation once per purpose (a retried call never sends a second text)."""
    sent = [p for p in str(state.get("sms_sent") or "").split(",") if p]
    if purpose in sent:
        return {"sms_sent": True, "destination_last4": str(state.get("phone_last4") or account_record(state)["phone"][-4:])}
    return dispatch_sms(state, purpose)


def manage_appointment_impl(
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


def _tech_slot_required(appt_id: str, reference: str, lang: str) -> dict[str, Any]:
    reply = ok_reply(
        {"appointment_id": appt_id, "slot_required": True, "available_slots": _tech_public_slots(lang)},
        reference, language=lang,
    )
    reply["agent_action"] = "Offer these slots and ask which one suits the caller."
    return reply


def _tech_bad_slot(state: dict[str, Any], reference: str, lang: str) -> dict[str, Any]:
    return validation_error(
        state, "That slot is not one of the open slots.",
        "Offer only the listed slots; if none suit, offer a text when a slot opens.",
        reference, lang, data={"available_slots": _tech_public_slots(lang)},
    )


def _tech_reschedule(
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


def _tech_cancel(
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


def _tech_book(state: dict[str, Any], slot_id: Any, reference: str, lang: str) -> dict[str, Any]:
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


def _tech_add_note(
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
