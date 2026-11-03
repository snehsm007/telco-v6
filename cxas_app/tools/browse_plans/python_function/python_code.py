from typing import Any



def browse_plans(
    lob: str = "",
    budget: str | int | float = "",
    need: str = "",
    language: str = "",
) -> dict[str, Any]:
    """Lists at most three plans or add-ons for one line of business, filtered by the
      caller's monthly budget and ranked by what they need, with coverage at the service
      address. No login needed. Call it when the caller wants to upgrade, compare plans
      or add a TV pack. Returns current_plan, price differences, new monthly totals,
      contract_terms and activation timing.

    Args:
      lob: mobility, internet or tv (homephone also accepted).
      budget: Highest monthly price the caller will pay, as said; empty when none was
        given.
      need: What the caller wants in a few words, e.g. more data, faster speed, sports
        channels, lower price.
      language: Active language code (en-US or fr-CA).

    Returns:
      status, data (lob, plans[] {plan_id, name, price_display, key_features,
        data_display or speed_display, price_difference_display, price_change,
        new_monthly_total_display, new_account_monthly_total_display}, current_plan,
        coverage_checked, coverage_available, max_speed_display, contract_terms,
        activation_display, effective_date_display, no_plan_within_budget),
        error_message, tracking_id. Errors add error (INVALID_INPUT) and agent_action.
    """
    ctx = globals().get("context")
    state = getattr(ctx, "state", None) if ctx is not None else None
    if state is None and isinstance(ctx, dict):
        state = ctx
    return browse_plans_impl(
        lob=lob,
        budget=budget,
        need=need,
        language=language,
        state=state,
    )


# --- BEGIN GENERATED SHARED BUNDLE (edit lib/, then run `make bundle`) ---
# uses: from lib.sales import browse_plans_impl
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
import contextvars
import hashlib
import re

DEFAULT_REGION = "Region-C"  # pragma: no cover

PLANS: tuple[dict[str, Any], ...] = (  # pragma: no cover
    {"plan_id": "MOB-20", "lob": "mobility", "name": "Essential 20", "price": "47.00", "data_gb": 20, "features": ["20 GB high-speed data", "Unlimited Canada-wide calling"]},
    {"plan_id": "MOB-50", "lob": "mobility", "name": "Plus 50", "price": "58.00", "data_gb": 50, "features": ["50 GB high-speed data", "Unlimited Canada-wide calling", "5G access"]},
    {"plan_id": "MOB-100", "lob": "mobility", "name": "Max 100", "price": "72.00", "data_gb": 100, "features": ["100 GB high-speed data", "Canada-US calling", "5G+ access"]},
    {"plan_id": "MOB-UNL", "lob": "mobility", "name": "Unlimited Premium", "price": "89.00", "data_gb": 175, "features": ["175 GB high-speed data", "Canada-US-Mexico calling", "5G+ access"]},
    {"plan_id": "INT-1G", "lob": "internet", "upload_mbps": 1000, "symmetric": True, "latency_key": "latency_fibre", "name": "Fibre 1 Gigabit", "price": "97.00", "speed_mbps": 1000, "features": ["Up to 1 Gbps download", "Unlimited usage", "Wi-Fi 6 gateway"]},
    {"plan_id": "INT-3G", "lob": "internet", "upload_mbps": 3000, "symmetric": True, "latency_key": "latency_fibre", "name": "Fibre 3 Gigabit", "price": "118.00", "speed_mbps": 3000, "features": ["Up to 3 Gbps download", "Unlimited usage", "Wi-Fi 6E gateway", "Whole-home Wi-Fi pod"]},
    {"plan_id": "INT-8G", "lob": "internet", "upload_mbps": 8000, "symmetric": True, "latency_key": "latency_fibre", "name": "Fibre 8 Gigabit", "price": "143.00", "speed_mbps": 8000, "features": ["Up to 8 Gbps download", "Unlimited usage", "Wi-Fi 7 gateway", "Two Wi-Fi pods"]},
    {"plan_id": "TV-SPORTS", "lob": "tv", "name": "Sports Pack", "price": "16.00", "addon": True, "channel_count": 14, "blackout_key": "blackout_sports", "keywords": ["sport", "hockey", "football", "soccer", "basketball", "baseball"], "features": ["National sports networks", "Regional game coverage", "Sports on demand"], "hd_included": True, "channel_examples": ["National hockey, football and basketball broadcasts", "Regional and local team games", "International soccer", "Sports news and highlights"]},
    {"plan_id": "TV-MOVIES", "lob": "tv", "name": "Movies Pack", "price": "13.00", "addon": True, "channel_count": 9, "keywords": ["movie", "film", "cinema", "cinéma"], "features": ["Premium movie channels", "Movies on demand"], "hd_included": True, "channel_examples": ["Premium movie channels", "Recent releases on demand", "Classic film channels"]},
    {"plan_id": "TV-PLUS", "lob": "tv", "name": "TV Plus Package", "price": "61.00", "addon": False, "keywords": ["package", "channels", "upgrade"], "features": ["Over 150 channels", "Cloud PVR"], "hd_included": True, "channel_examples": ["National news and lifestyle channels", "Kids and family channels", "Specialty entertainment channels"]},
)

SALES_COVERAGE_MAX_MBPS: dict[str, int] = {"Region-A": 3000, "Region-B": 8000, "Region-C": 1000}  # pragma: no cover

SALES_EQUIPMENT_DELIVERY_DAYS = 3  # pragma: no cover

_SALES_MAX_OPTIONS = 3  # pragma: no cover

SALES_ACTIVATION_DAYS: dict[str, int] = {"mobility": 0, "internet": 1, "tv": 0, "homephone": 1}  # pragma: no cover

def _sales_business_date(days: int) -> str:  # pragma: no cover
    """ISO date `days` business days from today (0 = today)."""
    current = datetime.now(timezone.utc)
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current.strftime("%Y-%m-%d")

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
    "warranty_fees": {
        "en-US": "An in-warranty replacement costs nothing: no fee or deductible, free shipping of the replacement, and a prepaid return label for the old phone.",
        "fr-CA": "Un remplacement sous garantie ne coûte rien : aucuns frais ni franchise, livraison gratuite du téléphone de remplacement et étiquette de retour prépayée pour l'ancien téléphone.",
    },
    "warranty_fees_urgent": {
        "en-US": "This safety replacement costs nothing: no fee or deductible, and free expedited shipping. The damaged phone is not mailed back.",
        "fr-CA": "Ce remplacement pour raison de sécurité ne coûte rien : aucuns frais ni franchise, et livraison accélérée gratuite. Le téléphone endommagé n'est pas renvoyé par la poste.",
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
    "port_provider_lookup": {
        "en-US": "the current provider on record for that number (found by number lookup)",
        "fr-CA": "le fournisseur actuel inscrit pour ce numéro (trouvé par recherche de numéro)",
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
    "full_channel_list": {
        "en-US": "The full channel list for this pack is on the TV packs page of the Telco website and in the receiver's channel guide once the pack is added.",
        "fr-CA": "La liste complète des chaînes de ce forfait se trouve sur la page des forfaits télé du site Web de Telco et dans le guide des chaînes du récepteur une fois le forfait ajouté.",
    },
    "blackout_sports": {
        "en-US": "Some local and regional games can be blacked out when a local broadcaster holds the rights in your area; those games air on that broadcaster's channel instead. Blackouts depend on the league and the service address.",
        "fr-CA": "Certains matchs locaux et régionaux peuvent être interdits de diffusion quand un diffuseur local détient les droits dans votre région; ces matchs sont alors présentés sur la chaîne de ce diffuseur. Les interdictions dépendent de la ligue et de l'adresse de service.",
    },
    "port_own_account": {
        "en-US": "your own Telco account",
        "fr-CA": "votre propre compte Telco",
    },
    "port_internal_move": {
        "en-US": "This number is already on your Telco account, so it moves between your own lines: no account number or transfer PIN from another provider is needed.",
        "fr-CA": "Ce numéro est déjà à votre compte Telco, donc il passe d'une de vos lignes à l'autre : aucun numéro de compte ni NIP de transfert d'un autre fournisseur n'est requis.",
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

def _sales_activation(lob: str, lang: str) -> dict[str, str]:  # pragma: no cover
    days = SALES_ACTIVATION_DAYS.get(lob, 0)
    iso = _sales_business_date(days)
    return {
        "effective_date": iso,
        "effective_date_display": display_date(iso, lang),
        "activation_display": _sales_text("activation_today" if days == 0 else "activation_next_day", lang),
    }

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

def _sales_budget(budget: Any) -> Decimal | None:  # pragma: no cover
    match = re.search(r"\d+(?:[.,]\d{1,2})?", str(budget if budget is not None else ""))
    return to_decimal(match.group(0)) if match else None

def _sales_capacity(plan: dict[str, Any]) -> int:  # pragma: no cover
    return int(plan.get("data_gb") or plan.get("speed_mbps") or 0)

CURRENT_DATA_GB = 15  # pragma: no cover

CURRENT_PLANS: dict[str, str] = {"mobility": "Plus 50 Legacy", "internet": "Fibre 500", "tv": "TV Basic", "homephone": "Home Phone Lite"}  # pragma: no cover

CURRENT_SPEED_MBPS = 500  # pragma: no cover

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

def _sales_account_lobs(state: dict[str, Any]) -> list[str]:  # pragma: no cover
    return list(account_record(state).get("lines_of_business") or [])

def _sales_data_display(gb: int, lang: str) -> str:  # pragma: no cover
    return f"{gb} Go" if resolve_copy_locale(lang) == "fr-CA" else f"{gb} GB"

def _sales_speed_display(mbps: int, lang: str) -> str:  # pragma: no cover
    fr = resolve_copy_locale(lang) == "fr-CA"
    if mbps >= 1000 and mbps % 1000 == 0:
        return f"{mbps // 1000} Gbit/s" if fr else f"{mbps // 1000} Gbps"
    return f"{mbps} Mbit/s" if fr else f"{mbps} Mbps"

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

def money(value: Any, prefix: str = "amount") -> dict[str, Any]:  # pragma: no cover
    """Money as a number plus a 2-decimal display string (DESIGN_RULES rule 27)."""
    amount = to_decimal(value) or Decimal("0.00")
    return {prefix: float(amount), f"{prefix}_display": display_amount(amount), "currency": CURRENCY}

def _sales_current(state: dict[str, Any], lob: str, lang: str) -> dict[str, Any] | None:  # pragma: no cover
    """The plan the identified account has today for `lob` (None when it has no such service)."""
    if not state.get("account_id") or lob not in _sales_account_lobs(state) or lob not in CURRENT_PLANS:
        return None
    current: dict[str, Any] = {"name": CURRENT_PLANS[lob], **money(SERVICE_PRICES.get(lob, "0"), "price")}
    if lob == "mobility":
        current["data_gb"] = CURRENT_DATA_GB
        current["data_display"] = _sales_data_display(CURRENT_DATA_GB, lang)
    elif lob == "internet":
        current["speed_mbps"] = CURRENT_SPEED_MBPS
        current["speed_display"] = _sales_speed_display(CURRENT_SPEED_MBPS, lang)
    return current

def _sales_has(text: str, words: tuple[str, ...] | frozenset[str]) -> bool:  # pragma: no cover
    low = str(text or "").lower()
    return any(w in low for w in words)

_SALES_LOB_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (  # pragma: no cover
    ("tv", ("tv", "télé", "tele", "television", "channel", "chaîne", "sport", "movie", "film")),
    ("internet", ("internet", "wifi", "wi-fi", "fibre", "fiber", "broadband", "connexion", "connection")),
    ("homephone", ("home phone", "homephone", "landline", "ligne fixe", "téléphone fixe")),
    ("mobility", ("mobil", "mobile", "cell", "wireless", "phone", "data", "données", "forfait")),
)

def _sales_lob(lob: Any, need: Any = "") -> str:  # pragma: no cover
    """Map the model's line-of-business words onto mobility / internet / tv / homephone."""
    for text in (lob, need):
        low = str(text or "").strip().lower()
        if not low:
            continue
        for key, words in _SALES_LOB_WORDS:
            if low == key or any(w in low for w in words):
                return key
    return ""

SALES_PLACEHOLDERS: frozenset[str] = frozenset(  # pragma: no cover
    {"", "unknown", "external", "none", "n/a", "na", "tbd", "pending", "not sure", "?", "inconnu", "aucun", "other", "autre"}
)

def _sales_placeholder(value: Any) -> bool:  # pragma: no cover
    return str(value if value is not None else "").strip().lower() in SALES_PLACEHOLDERS

SALES_FEATURES_FR: dict[str, str] = {  # pragma: no cover
    "20 GB high-speed data": "20 Go de données haute vitesse",
    "50 GB high-speed data": "50 Go de données haute vitesse",
    "100 GB high-speed data": "100 Go de données haute vitesse",
    "175 GB high-speed data": "175 Go de données haute vitesse",
    "Unlimited Canada-wide calling": "Appels illimités partout au Canada",
    "Canada-US calling": "Appels Canada–États-Unis",
    "Canada-US-Mexico calling": "Appels Canada–États-Unis–Mexique",
    "5G access": "Accès 5G",
    "5G+ access": "Accès 5G+",
    "Up to 1 Gbps download": "Téléchargement jusqu'à 1 Gbit/s",
    "Up to 3 Gbps download": "Téléchargement jusqu'à 3 Gbit/s",
    "Up to 8 Gbps download": "Téléchargement jusqu'à 8 Gbit/s",
    "Unlimited usage": "Utilisation illimitée",
    "Wi-Fi 6 gateway": "Passerelle Wi-Fi 6",
    "Wi-Fi 6E gateway": "Passerelle Wi-Fi 6E",
    "Wi-Fi 7 gateway": "Passerelle Wi-Fi 7",
    "Whole-home Wi-Fi pod": "Module Wi-Fi pour toute la maison",
    "Two Wi-Fi pods": "Deux modules Wi-Fi",
    "National sports networks": "Réseaux de sports nationaux",
    "Regional game coverage": "Couverture des matchs régionaux",
    "Sports on demand": "Sports sur demande",
    "Premium movie channels": "Chaînes de films haut de gamme",
    "Movies on demand": "Films sur demande",
    "Over 150 channels": "Plus de 150 chaînes",
    "Cloud PVR": "Enregistreur numérique infonuagique",
    "National hockey, football and basketball broadcasts": "Matchs nationaux de hockey, de football et de basketball",
    "Regional and local team games": "Matchs des équipes régionales et locales",
    "International soccer": "Soccer international",
    "Sports news and highlights": "Nouvelles et faits saillants sportifs",
    "Recent releases on demand": "Films récents sur demande",
    "Classic film channels": "Chaînes de films classiques",
    "National news and lifestyle channels": "Chaînes nationales de nouvelles et de style de vie",
    "Kids and family channels": "Chaînes pour enfants et la famille",
    "Specialty entertainment channels": "Chaînes spécialisées de divertissement",
}

def _sales_feature(text: str, lang: str) -> str:  # pragma: no cover
    return SALES_FEATURES_FR.get(text, text) if resolve_copy_locale(lang) == "fr-CA" else text

def _sales_account_total(state: dict[str, Any]) -> Decimal:  # pragma: no cover
    return sum(
        (to_decimal(SERVICE_PRICES.get(lob, "0")) or Decimal("0") for lob in _sales_account_lobs(state)),
        Decimal("0.00"),
    )

def _sales_pricing(state: dict[str, Any], plan: dict[str, Any], current: dict[str, Any] | None) -> dict[str, Any]:  # pragma: no cover
    """Price difference against today's plan and the new monthly totals (service and account).

    Without a current plan (caller not identified, or a new service) only the plan's own
    price is the new service total and no difference is reported.
    """
    price = to_decimal(plan["price"]) or Decimal("0")
    if current is None:
        out: dict[str, Any] = {**money(price, "new_monthly_total"), "price_change": "new_service"}
        if state.get("account_id"):
            out.update(money(_sales_account_total(state) + price, "new_account_monthly_total"))
        return out
    old = to_decimal(current["price"]) or Decimal("0")
    delta = price if plan.get("addon") else price - old
    out = {
        "price_difference": float(abs(delta)),
        "price_difference_display": display_amount(abs(delta)),
        "price_change": "increase" if delta > 0 else "decrease" if delta < 0 else "none",
        **money(old + delta, "new_monthly_total"),
        **money(_sales_account_total(state) + delta, "new_account_monthly_total"),
    }
    return out

def _sales_plan_view(state: dict[str, Any], plan: dict[str, Any], current: dict[str, Any] | None, lang: str) -> dict[str, Any]:  # pragma: no cover
    view: dict[str, Any] = {
        "plan_id": plan["plan_id"],
        "name": plan["name"],
        "lob": plan["lob"],
        "is_addon": bool(plan.get("addon")),
        **money(plan["price"], "price"),
        "key_features": [_sales_feature(f, lang) for f in plan.get("features", [])[:3]],
    }
    if plan.get("data_gb"):
        view["data_display"] = _sales_data_display(int(plan["data_gb"]), lang)
    if plan.get("speed_mbps"):
        view["speed_display"] = _sales_speed_display(int(plan["speed_mbps"]), lang)
    if plan.get("upload_mbps"):  # follow-up facts: upload, symmetry, latency (DESIGN_RULES rule 33)
        view["upload_speed_display"] = _sales_speed_display(int(plan["upload_mbps"]), lang)
        view["symmetric"] = bool(plan.get("symmetric"))
        view["latency_note"] = _sales_text(str(plan.get("latency_key") or ""), lang)
    if plan.get("channel_examples"):
        view["channel_examples"] = [_sales_feature(c, lang) for c in plan["channel_examples"]]
        view["hd_included"] = bool(plan.get("hd_included"))
        # Follow-up facts for a TV pack: size, where the full lineup is, blackouts (rule 33).
        if plan.get("channel_count"):
            view["channel_count"] = int(plan["channel_count"])
        view["full_channel_list_note"] = _sales_text("full_channel_list", lang)
        if plan.get("blackout_key"):
            view["blackout_note"] = _sales_text(str(plan["blackout_key"]), lang)
    view.update(_sales_pricing(state, plan, current))
    return view

SALES_CAPACITY_WORDS: tuple[str, ...] = (  # pragma: no cover
    "data", "données", "higher tier", "unlimited", "heavy", "gaming", "stream", "fast", "speed",
    "work from home", "working from home", "remote work", "reliable", "bandwidth", "upload",
    "video call", "plus de données", "illimit", "vitesse", "rapide", "télétravail", "fiable",
    "bande passante",
)

SALES_PRICE_WORDS: tuple[str, ...] = (  # pragma: no cover
    "budget", "cheap", "afford", "save", "lower price", "lowest", "moins cher", "économ", "abordable",
)

def _sales_rank(plans: list[dict[str, Any]], need: str) -> list[dict[str, Any]]:  # pragma: no cover
    """Pick at most 3: capacity needs keep the biggest tiers, otherwise the lowest prices; shown by price."""
    by_price = sorted(plans, key=lambda p: to_decimal(p["price"]) or Decimal("0"))
    if _sales_has(need, SALES_CAPACITY_WORDS) and not _sales_has(need, SALES_PRICE_WORDS):
        top = sorted(plans, key=_sales_capacity, reverse=True)[:_SALES_MAX_OPTIONS]
        return [p for p in by_price if p in top]
    return by_price[:_SALES_MAX_OPTIONS]

REGION_BY_POSTAL_LETTER: dict[str, str] = {  # pragma: no cover
    **{letter: "Region-A" for letter in "GHJ"},
    **{letter: "Region-B" for letter in "KLMNP"},
}

def _sales_region(state: dict[str, Any]) -> str:  # pragma: no cover
    """Region class of the identified account's service address ("" when not identified)."""
    if not state.get("account_id"):
        return ""
    region = str(state.get("region") or "").strip()
    if region:
        return region
    postal = str(account_record(state).get("postal_code") or "")
    return REGION_BY_POSTAL_LETTER.get(postal[:1].upper(), DEFAULT_REGION)

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

def browse_plans_impl(  # pragma: no cover
    lob: str = "",
    budget: str | int | float = "",
    need: str = "",
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Up to 3 plans or add-ons for a line of business, with coverage and Turn-N+1 facts. No login."""
    state = get_state(state, session_state)
    lang = session_language(state, language)
    err = check_mock_error(state, lang, "browse_plans")
    if err:
        return err
    lob_key = _sales_lob(lob, need)
    need_text = str(need or "")
    reference = tracking_id("browse_plans", state.get("account_id", ""), lob_key, budget, need_text)
    if not lob_key:
        return validation_error(
            state, "Unknown line of business.", "Ask if the caller means mobile, internet or TV.", reference, lang
        )
    budget_amt = _sales_budget(budget) if not _sales_placeholder(budget) else None
    if budget_amt is not None and budget_amt <= 0:
        return validation_error(state, "The budget must be above zero.", "Ask for the monthly budget again.", reference, lang)
    state["lob"] = lob_key
    state["last_tracking_id"] = reference

    region = _sales_region(state)
    max_mbps = SALES_COVERAGE_MAX_MBPS.get(region, SALES_COVERAGE_MAX_MBPS[DEFAULT_REGION]) if region else 0
    current = _sales_current(state, lob_key, lang)
    catalogue = [p for p in PLANS if p["lob"] == lob_key]

    if lob_key == "tv":
        wanted = [p for p in catalogue if _sales_has(need_text, tuple(p.get("keywords", [])))]
        others = [p for p in catalogue if p not in wanted]
        candidates = wanted + others
    else:
        candidates = list(catalogue)
        if current:
            floor = int(current.get("data_gb") or current.get("speed_mbps") or 0)
            candidates = [p for p in candidates if _sales_capacity(p) > floor]
        if lob_key == "internet" and max_mbps:
            candidates = [p for p in candidates if int(p.get("speed_mbps") or 0) <= max_mbps]

    over_budget: list[dict[str, Any]] = []
    if budget_amt is not None:
        over_budget = [p for p in candidates if (to_decimal(p["price"]) or Decimal("0")) > budget_amt]
        candidates = [p for p in candidates if p not in over_budget]

    chosen = candidates[:_SALES_MAX_OPTIONS] if lob_key == "tv" else _sales_rank(candidates, need_text)
    data: dict[str, Any] = {
        "lob": lob_key,
        "plans": [_sales_plan_view(state, p, current, lang) for p in chosen],
        "plan_count": len(chosen),
        "coverage_checked": bool(region),
        "coverage_available": True if region else None,
        "has_current_service": current is not None,
        "current_plan": current,
        "contract_terms": _sales_text("contract_terms", lang),
        "proration_note": _sales_text("proration", lang),
        "prices_exclude_tax": True,
        **_sales_activation(lob_key, lang),
    }
    if not region:
        data["coverage_note"] = _sales_text("coverage_unchecked", lang)
    if lob_key == "internet":
        if max_mbps:
            data["max_speed_display"] = _sales_speed_display(max_mbps, lang)
        delivery = _sales_business_date(SALES_EQUIPMENT_DELIVERY_DAYS)
        data["gateway_delivery_eta_display"] = display_date(delivery, lang)
    if lob_key == "mobility":
        data["after_data_cap"] = _sales_text("after_data_cap", lang)
    if budget_amt is not None:
        data.update(money(budget_amt, "budget"))
        data["no_plan_within_budget"] = not chosen
        if over_budget and not chosen:
            cheapest = min(over_budget, key=lambda p: to_decimal(p["price"]) or Decimal("0"))
            data.update(money(cheapest["price"], "lowest_available_price"))
    if lob_key == "tv" and current is None and state.get("account_id"):
        data["tv_service_required_for_addons"] = True
    return ok_reply(data, reference, language=lang)
# --- END GENERATED SHARED BUNDLE ---
