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

# Verbatim copy library (prd.md §7) plus operational lines. French lines, the
# two Legal placeholders (payment_method_preamble,
# contract_cancellation_fee_disclosure) and refund_over_limit are interim wording
# PENDING LEGAL APPROVAL (docs/requirements.md decision A6).
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
    {"plan_id": "INT-1G", "lob": "internet", "upload_mbps": 1000, "symmetric": True, "latency_key": "latency_fibre", "name": "Fibre 1 Gigabit", "price": "97.00", "speed_mbps": 1000, "features": ["Up to 1 Gbps download", "Unlimited usage", "Wi-Fi 6 gateway"]},
    {"plan_id": "INT-3G", "lob": "internet", "upload_mbps": 3000, "symmetric": True, "latency_key": "latency_fibre", "name": "Fibre 3 Gigabit", "price": "118.00", "speed_mbps": 3000, "features": ["Up to 3 Gbps download", "Unlimited usage", "Wi-Fi 6E gateway", "Whole-home Wi-Fi pod"]},
    {"plan_id": "INT-8G", "lob": "internet", "upload_mbps": 8000, "symmetric": True, "latency_key": "latency_fibre", "name": "Fibre 8 Gigabit", "price": "143.00", "speed_mbps": 8000, "features": ["Up to 8 Gbps download", "Unlimited usage", "Wi-Fi 7 gateway", "Two Wi-Fi pods"]},
    {"plan_id": "TV-SPORTS", "lob": "tv", "name": "Sports Pack", "price": "16.00", "addon": True, "keywords": ["sport", "hockey", "football", "soccer", "basketball", "baseball"], "features": ["National sports networks", "Regional game coverage", "Sports on demand"], "hd_included": True, "channel_examples": ["National hockey, football and basketball broadcasts", "Regional and local team games", "International soccer", "Sports news and highlights"]},
    {"plan_id": "TV-MOVIES", "lob": "tv", "name": "Movies Pack", "price": "13.00", "addon": True, "keywords": ["movie", "film", "cinema", "cinéma"], "features": ["Premium movie channels", "Movies on demand"], "hd_included": True, "channel_examples": ["Premium movie channels", "Recent releases on demand", "Classic film channels"]},
    {"plan_id": "TV-PLUS", "lob": "tv", "name": "TV Plus Package", "price": "61.00", "addon": False, "keywords": ["package", "channels", "upgrade"], "features": ["Over 150 channels", "Cloud PVR"], "hd_included": True, "channel_examples": ["National news and lifestyle channels", "Kids and family channels", "Specialty entertainment channels"]},
)
CURRENT_PLANS: dict[str, str] = {"mobility": "Plus 50 Legacy", "internet": "Fibre 500", "tv": "TV Basic", "homephone": "Home Phone Lite"}
CURRENT_SPEED_MBPS = 500
CURRENT_DATA_GB = 15
CURRENT_DATA_USED_GB = 9     # high-speed data used this cycle (below the plan's allowance: not slowed)

# Devices on the account (prd.md §12 warranty). Purchase dates relative to today.
DEVICES_ON_FILE: tuple[dict[str, Any], ...] = (
    {"device_id": "DEV-01", "model": "Apple iPhone 15", "keywords": ["iphone", "apple"], "purchased_days_ago": 160},
    {"device_id": "DEV-02", "model": "Samsung Galaxy S24", "keywords": ["samsung", "galaxy"], "purchased_days_ago": 210},
    {"device_id": "DEV-03", "model": "Google Pixel 8", "keywords": ["pixel", "google"], "purchased_days_ago": 120},
)
DEVICE_WARRANTY_DAYS = 365

# --- sales fixtures ---
# Sales & equipment backend facts (docs/tdd.md §4), read by lib/sales.py only.
# Dates are day offsets from today; copy has one entry per locale and the tool
# returns only the call language's text.
SALES_COVERAGE_MAX_MBPS: dict[str, int] = {"Region-A": 3000, "Region-B": 8000, "Region-C": 1000}
SALES_ACTIVATION_DAYS: dict[str, int] = {"mobility": 0, "internet": 1, "tv": 0, "homephone": 1}
SALES_EQUIPMENT_DELIVERY_DAYS = 3        # a new gateway ships with an internet plan change
SALES_WARRANTY_SHIP_DAYS = 3             # standard warranty replacement
SALES_URGENT_SHIP_DAYS = 1               # expedited safety replacement
SALES_RETURN_WINDOW_DAYS = 15
SALES_OUT_OF_WARRANTY_AGE_DAYS = 430     # device age reported when fx_device_warranty=out_of_warranty
SALES_REPAIR_FEE = "139.00"
SALES_PORT_DAYS: dict[str, int] = {"mobile": 0, "landline": 3}

# French wording of the plan features in PLANS (English is the catalogue text).
SALES_FEATURES_FR: dict[str, str] = {
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

# Need words that rank plans (browse_plans `need`): capacity first or price first.
SALES_CAPACITY_WORDS: tuple[str, ...] = (
    "data", "données", "higher tier", "unlimited", "heavy", "gaming", "stream", "fast", "speed",
    "work from home", "working from home", "remote work", "reliable", "bandwidth", "upload",
    "video call", "plus de données", "illimit", "vitesse", "rapide", "télétravail", "fiable",
    "bande passante",
)
SALES_PRICE_WORDS: tuple[str, ...] = (
    "budget", "cheap", "afford", "save", "lower price", "lowest", "moins cher", "économ", "abordable",
)
# Words in a warranty description that mean a battery or heat safety hazard.
SALES_SAFETY_WORDS: tuple[str, ...] = (
    "swollen", "swelling", "bulging", "bulge", "puffy", "expanding", "smoke", "smoking", "overheat",
    "too hot", "burning", "fire", "melt", "gonfl", "bombé", "fumée", "surchauff", "brûl",
)
# Words that name no particular device ("my phone"): warranty falls back to the newest device.
SALES_GENERIC_DEVICE_WORDS: frozenset[str] = frozenset({
    "my", "the", "a", "an", "this", "it", "old", "new", "current", "phone", "cell", "cellphone", "smartphone",
    "mobile", "device", "handset", "mon", "ma", "le", "la", "un", "une", "ce", "téléphone", "telephone",
    "cellulaire", "appareil", "portable", "intelligent",
})
# Words in target_line / current_provider meaning the number is a home phone (landline).
SALES_LANDLINE_WORDS: tuple[str, ...] = ("landline", "home phone", "house phone", "fixe", "résidentiel", "maison")
# Words in target_line meaning the number goes on a new line on the account.
SALES_NEW_LINE_WORDS: tuple[str, ...] = ("new", "add", "family", "nouvelle", "ajout", "famille")
# Answers that mean "not provided yet".
SALES_PLACEHOLDERS: frozenset[str] = frozenset(
    {"", "unknown", "external", "none", "n/a", "na", "tbd", "pending", "not sure", "?", "inconnu", "aucun", "other", "autre"}
)

SALES_COPY: dict[str, dict[str, str]] = {
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
    "new_line_pricing": {
        "en-US": "Added as an additional line, the plan adds its own price to the account and the current line keeps its plan; as a plan change, it replaces the current mobile plan.",
        "fr-CA": "Ajouté comme ligne supplémentaire, le forfait ajoute son propre prix au compte et la ligne actuelle garde son forfait; comme changement de forfait, il remplace le forfait mobile actuel.",
    },
}
# --- end sales fixtures ---

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

# --- billing fixtures ---
# Labels of the monthly service lines on a bill (en-US, fr-CA) and the words a
# caller uses for each service. Keyword matching is by service class, never by
# a test sentence.
SERVICE_LINE_LABELS: dict[str, tuple[str, str]] = {
    "mobility": ("Mobility monthly service", "Service mobilité mensuel"),
    "internet": ("Home internet monthly service", "Service Internet résidentiel mensuel"),
    "tv": ("TV monthly service", "Service télé mensuel"),
    "homephone": ("Home phone monthly service", "Service de téléphone résidentiel mensuel"),
}
SERVICE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "mobility": ("mobil", "cell", "wireless", "smartphone", "data", "données", "sans fil"),
    "internet": ("internet", "wi-fi", "wifi", "modem", "router", "routeur", "broadband", "fibre", "fiber"),
    "tv": ("tv", "télé", "tele", "television", "télévision", "cable", "câble", "satellite", "channel", "chaîne"),
    "homephone": ("home phone", "landline", "ligne fixe", "téléphone résidentiel", "telephone residentiel"),
}
# French labels and caller words for the extra lines in BILL_EXTRA_LINES.
BILL_EXTRA_LINE_FR: dict[str, str] = {
    "CH-STR-01": "Achat AppleStreaming",
    "CH-LD-01": "Appels interurbains",
}
BILL_EXTRA_LINE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "CH-STR-01": ("stream", "apple", "diffusion", "en continu", "purchase", "achat", "subscription", "abonnement"),
    "CH-LD-01": ("long distance", "long-distance", "longue distance", "interurbain", "international", "calls", "appels"),
}
EXTRA_FIXTURE_LINE_DAYS_AGO = 4      # fx_extra_bill_line posts on the latest bill
BANK_ON_FILE_ENDING = "6083"
ARRANGEMENT_FIRST_DUE_DAYS = 7       # first instalment within 7 days
NEXT_BILL_CYCLE_DAYS = 30
DISPUTE_ETA_BUSINESS_DAYS = 10
RECENT_PAYMENT_DAYS_AGO = 1          # fx_recent_payment=posted_yesterday
CARD_BRANDS_BY_PREFIX: dict[str, str] = {"4": "Visa", "5": "Mastercard", "2": "Mastercard", "3": "American Express"}
# Autopay follow-up facts (DESIGN_RULES rule 33), (en-US, fr-CA). [days] = bill date to due date.
AUTOPAY_WITHDRAWAL_NOTE = (
    "Autopay charges the full statement balance on each bill's due date, [days] days after the bill date.",
    "Le paiement préautorisé prélève le solde total du relevé à la date d'échéance de chaque facture, [days] jours après la date de facturation.",
)
BILL_DATE_CHANGE_NOTE = (
    "The monthly bill date is set by the account's billing cycle and can't be changed; autopay always follows each bill's due date.",
    "La date de facturation mensuelle est fixée par le cycle de facturation du compte et ne peut pas être modifiée; le paiement préautorisé suit toujours la date d'échéance de chaque facture.",
)
AUTOPAY_DISCOUNT = "0.00"
AUTOPAY_DISCOUNT_NOTE = (
    "There's no discount or incentive for autopay; it makes sure each bill is paid on time, with no fee.",
    "Le paiement préautorisé ne donne pas de rabais ni d'avantage; il assure que chaque facture est payée à temps, sans frais.",
)
# --- end billing fixtures ---


# Input formats (prd.md §9, docs/tdd.md §6). Tools check these before acting; anything
# else is a validation error ("please repeat"), never a login strike.
PHONE_NANP_RE = re.compile(r"^(?:\+?1[\s.\-]?)?\(?[0-9]{3}\)?[\s.\-]?[0-9]{3}[\s.\-]?[0-9]{4}$")
PHONE_INTL_RE = re.compile(r"^(?:\+|00)[1-9](?:[\s.\-]?[0-9]){9,14}$")
PHONE_LOCAL_PAIRS_RE = re.compile(r"^0[1-9](?:[\s.\-]?[0-9]{2}){4}$")
ACCOUNT_NUMBER_RE = re.compile(r"^[0-9](?:[\s\-]?[0-9]){5,14}$")
ACCOUNT_REFERENCE_RE = re.compile(
    r"^(?=(?:[^0-9]*[0-9]){4})(?=.*[A-Za-z])[A-Za-z0-9](?:[A-Za-z0-9]|[\s\-](?=[A-Za-z0-9])){3,24}$"
)
OTP_RE = re.compile(r"^[0-9]{6}$")
PIN_RE = re.compile(r"^[0-9]{4}$")
# An email address the caller gives instead of a number (no phone or account number at hand).
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")
DUMMY_NUMBERS: frozenset[str] = frozenset({"1234567890", "0123456789", "9876543210"})


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
    """A 10-digit number that isn't one repeated digit or an obvious dummy run (Postel: accept generously)."""
    if len(digits) != 10 or not digits.isdigit():
        return False
    return not is_weak_code(digits) and digits not in DUMMY_NUMBERS


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


def _phone_from_digits(digits: str) -> str:
    """A deterministic 10-digit phone ending in the caller's own digits.

    Synthetic records from an account number or reference get this phone, so the
    texted-code destination ("ending in ...") echoes digits the caller gave instead
    of the default account's phone.
    """
    if len(digits) >= 10:
        return digits[-10:]
    return ACCOUNTS[0]["phone"][: 10 - len(digits)] + digits


def _synthetic_account(account_number: str, phone: str) -> dict[str, Any]:
    """A record for a well-formed number this world doesn't know (fact-less simulated callers)."""
    base = dict(ACCOUNTS[0])
    base["account_id"] = "A" + account_number[-6:]
    base["phone"] = phone
    base["first_name"] = ""
    return base


def classify_identifier(raw: Any) -> tuple[str, str]:
    """Match a caller identifier against the format patterns.

    Returns (kind, digits): kind is phone, intl_phone, account_number,
    account_reference, or "" when no pattern matches.
    """
    text = re.sub(r"\.0+$", "", str(raw or "").strip())
    digits = normalize_code(text)
    if PHONE_NANP_RE.fullmatch(text):
        return "phone", digits[-10:]
    if PHONE_LOCAL_PAIRS_RE.fullmatch(text):
        return "phone", digits
    if PHONE_INTL_RE.fullmatch(text):
        return "intl_phone", digits
    if ACCOUNT_NUMBER_RE.fullmatch(text):
        return "account_number", digits
    if ACCOUNT_REFERENCE_RE.fullmatch(text):
        return "account_reference", digits
    return "", digits


def find_account(identifier: Any) -> dict[str, Any] | None:
    """Find an account by phone number, account number, account reference or email.

    The identifier must match one of the format patterns above. An email address
    (EMAIL_RE) finds the account with that email, else the default account
    (fact-less callers without a number give their email instead). Within those
    formats this accepts generously (DESIGN_RULES rule 43): fact-less callers
    invent numbers, so a well-formed unknown identifier resolves to a synthetic
    record. One repeated digit and dummy runs are never accounts.
    """
    raw_str = re.sub(r"\.0+$", "", str(identifier or "").strip())
    if not raw_str:
        return None
    raw = raw_str.upper()
    digits = normalize_code(raw_str)
    for record in ACCOUNTS:
        if raw == record["account_id"] or (digits and digits == record["phone"] and not any(c.isalpha() for c in raw_str)):
            return dict(record)
    if EMAIL_RE.fullmatch(raw_str):
        by_email = [r for r in ACCOUNTS if str(r.get("email", "")).lower() == raw_str.lower()]
        return dict(by_email[0] if by_email else ACCOUNTS[0])
    kind, digits = classify_identifier(raw_str)
    if not kind or is_weak_code(digits) or digits in DUMMY_NUMBERS:
        return None
    if kind == "phone":
        return _synthetic_account(digits, digits) if is_plausible_phone(digits) else None
    if kind == "intl_phone":
        return _synthetic_account(digits, digits[-10:])
    return _synthetic_account(digits, _phone_from_digits(digits))


def login_code_accepted(code_digits: Any, attempts: int = 0, max_attempts: int = 3) -> bool:
    """Whether the fake login service accepts a code on this try (the login ladder).

    `attempts` is the number of wrong tries so far on this call:
      - weak codes (one repeated digit) and ALWAYS_WRONG_LOGIN_CODES never pass;
      - first try (attempts == 0): any 4-digit PIN or 6-digit code;
      - second try: only VALID_LOGIN_CODES;
      - the last try (attempts == max_attempts - 1): always wrong.
    Lookups with a credential on file (fx_pin_on_file / fx_otp_on_file) bypass
    the ladder in lib/services.py and compare exactly.
    """
    digits = normalize_code(code_digits)
    if not (PIN_RE.fullmatch(digits) or OTP_RE.fullmatch(digits)):
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


# --- account fixtures ---
# Account management (docs/tdd.md §4 Account). Relative dates only; amounts are
# non-canonical fake values.
ACCT_LINES_OF_BUSINESS: tuple[str, ...] = ("mobility", "internet", "tv", "homephone")
ACCT_PORTABLE_LINES: tuple[str, ...] = ("mobility", "homephone")
# Early termination fee and months left on the contract, per line of business.
ACCT_CONTRACT_TERMS: dict[str, dict[str, Any]] = {
    "mobility": {"early_termination_fee": "96.40", "months_remaining": 7},
    "internet": {"early_termination_fee": "42.75", "months_remaining": 5},
    "tv": {"early_termination_fee": "0.00", "months_remaining": 0},
    "homephone": {"early_termination_fee": "0.00", "months_remaining": 0},
}
ACCT_BILLING_CYCLE_DAYS = 30
ACCT_PORT_OUT_COMPLETION_DAYS = 1      # the new carrier completes the port the next day
ACCT_EQUIPMENT_RETURN_DAYS = 30        # rented modem or TV receiver return window
ACCT_MFA_METHOD = "sms"
# --- end account fixtures ---
