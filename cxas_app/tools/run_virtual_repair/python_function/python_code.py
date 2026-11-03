from typing import Any



def run_virtual_repair(
    lob: str = "",
    symptom: str = "",
    tv_sub_type: str = "",
    language: str = "",
) -> dict[str, Any]:
    """Opens a virtual-repair session for a logged-in caller: checks the area outage at the
      address on file, sends a remote reset when possible, and returns troubleshooting
      steps in the caller's language. For TV, tv_sub_type is required.

    Args:
      lob: mobility, internet, tv, homephone or smarthome.
      symptom: The problem in the caller's words, including any error code shown.
      tv_sub_type: For TV only: streaming (receiver box), satellite, or streaming_only
        (app on the caller's own device).
      language: Active language code (en-US or fr-CA).

    Returns:
      status, data (session_id, symptom_category, catalogue_match, remote_reset_sent,
        steps, step_count, sms_recommended, known_issue), error_message, tracking_id.
        Errors add error (NOT_LOGGED_IN, TV_SUB_TYPE_REQUIRED, OUTAGE_ACTIVE,
        INVALID_INPUT) and agent_action.
    """
    ctx = globals().get("context")
    state = getattr(ctx, "state", None) if ctx is not None else None
    if state is None and isinstance(ctx, dict):
        state = ctx
    return run_virtual_repair_impl(
        lob=lob,
        symptom=symptom,
        tv_sub_type=tv_sub_type,
        language=language,
        state=state,
    )


# --- BEGIN GENERATED SHARED BUNDLE (edit lib/, then run `make bundle`) ---
# uses: from lib.tech import run_virtual_repair_impl
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
import hashlib
import re

_TECH_ERROR_CODE_RE = re.compile(r"(?:error|erreur|code)\s*(?:code\s*)?(?:#|no\.?|n°)?\s*(\d{2,4})\b", re.IGNORECASE)  # pragma: no cover

_TECH_KNOWN_ISSUES: dict[str, dict[str, str]] = {  # pragma: no cover
    "satellite_signal_loss": {
        "en-US": "Error codes on a satellite receiver usually mean it lost the satellite signal, often because something blocks the dish.",
        "fr-CA": "Les codes d'erreur sur un récepteur satellite indiquent habituellement une perte du signal satellite, souvent parce que quelque chose bloque l'antenne.",
    },
    "streaming_app_device": {
        "en-US": "The TV app runs on your own device, so no remote reset can be sent to it.",
        "fr-CA": "L'application télé fonctionne sur votre propre appareil, donc aucune réinitialisation à distance ne peut lui être envoyée.",
    },
}

_TECH_LOBS = ("mobility", "internet", "tv", "homephone", "smarthome")  # pragma: no cover

_TECH_REMOTE_RESET_TARGET = {  # pragma: no cover
    "internet": "modem",
    "tv": "receiver",
    "homephone": "line",
    "mobility": "network_registration",
    "smarthome": "hub",
}

_TECH_SUB_TYPES = ("streaming", "satellite", "streaming_only")  # pragma: no cover

ACTIVE_OUTAGES: dict[str, dict[str, Any]] = {  # pragma: no cover
    "Region-A": {"outage_id": "OUT-A-27", "services": ["internet", "tv"], "eta_hours": 4},
}

FIXTURE_OUTAGE = {"outage_id": "OUT-LOCAL-09", "services": ["internet", "tv"], "eta_hours": 3}  # pragma: no cover

FIXTURE_DEFAULTS: dict[str, str] = {  # pragma: no cover
    "fx_pin_on_file": "",
    "fx_otp_on_file": "",
    "fx_card_on_file_status": "valid",
    "fx_service_status": "active",
    "fx_recent_payment": "none",
    "fx_business_account": "false",
    "fx_outage_status": "",
    "fx_technician_status": "scheduled",
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

def _tech_area_outage(state: dict[str, Any], region: str) -> dict[str, Any] | None:  # pragma: no cover
    """The outage affecting a region: fixture override first, else the regional table."""
    status = fixture(state, "fx_outage_status")
    if status == "active":
        return dict(FIXTURE_OUTAGE)
    if status == "none":
        return None
    found = ACTIVE_OUTAGES.get(region)
    return dict(found) if found else None

_TECH_CATEGORIES: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {  # pragma: no cover
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

_TECH_GENERIC_WORDS = (  # pragma: no cover
    "not working", "doesn't work", "does not work", "isn't working", "stopped working",
    "won't work", "broken", "down", "problem", "issue", "trouble",
    "ne fonctionne", "fonctionne pas", "fonctionne plus", "marche pas", "marche plus",
    "en panne", "problème", "brisé", "défectueu",
)

def _tech_has(text: str, words: tuple[str, ...]) -> bool:  # pragma: no cover
    """True when any keyword starts a word in text (prefix match, accents kept)."""
    return any(re.search(r"(?<![\w])" + re.escape(w), text) for w in words)

def _tech_category(lob: str, symptom: str) -> tuple[str, bool]:  # pragma: no cover
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

CURRENT_DATA_GB = 15  # pragma: no cover

CURRENT_DATA_USED_GB = 9  # pragma: no cover

_TECH_DATA_NOTES: dict[str, dict[str, str]] = {  # pragma: no cover
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

def _tech_data_usage(lang: str) -> dict[str, Any]:  # pragma: no cover
    """Mobile data usage facts for a slow-data repair, so a usage question stays in tech support."""
    slowed = CURRENT_DATA_USED_GB >= CURRENT_DATA_GB
    usage = _tech_text(_TECH_DATA_NOTES["usage"], lang).format(
        used=CURRENT_DATA_USED_GB,
        total=CURRENT_DATA_GB,
        state=_tech_text(_TECH_DATA_NOTES["slowed" if slowed else "not_slowed"], lang),
    )
    return {"data_speed_reduced": slowed, "data_usage_note": usage, "throttling_note": _tech_text(_TECH_DATA_NOTES["throttling"], lang)}

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

_TECH_STEPS: dict[str, dict[str, list[str]]] = {  # pragma: no cover
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

def _tech_steps_for(category: str, sub_type: str, lang: str) -> list[str]:  # pragma: no cover
    table = _TECH_STEPS.get(f"{category}:{sub_type}") or _TECH_STEPS.get(category)
    if table is None:  # tv categories without a variant for this sub-type
        table = _TECH_STEPS[f"{category}:streaming"]
    return list(table.get(resolve_copy_locale(lang)) or table["en-US"])

def _tech_sub_type(raw: Any, symptom: str) -> str:  # pragma: no cover
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

def run_virtual_repair_impl(  # pragma: no cover
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
# --- END GENERATED SHARED BUNDLE ---
