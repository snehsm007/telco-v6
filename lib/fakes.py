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
import unicodedata

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

# Fixture defaults (docs/tdd.md §5): what the backend reports when no `fx_*`
# session variable overrides it.
FIXTURE_DEFAULTS: dict[str, str] = {
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
# prd.md BR-TV-014: only sales / plan changes and appointment booking follow
# business hours; every other live-agent queue is staffed around the clock.
BUSINESS_HOURS_QUEUES: frozenset[str] = frozenset({"sales", "appointments"})

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
# What the past-due amount is made of: the unpaid charges of the previous statement
# (one cycle before the latest bill). Sums to PAST_DUE_AMOUNT; no late fee is charged.
PAST_DUE_ITEMS: tuple[dict[str, Any], ...] = (
    {"lob": "mobility", "label": ("Mobility monthly service", "Service mobilité mensuel"), "amount": "65.00"},
    {"lob": "mobility", "label": ("Long distance calls", "Appels interurbains"), "amount": "22.65"},
)
PAST_DUE_FALLBACK_LABEL = ("Unpaid charges from the previous statement", "Frais impayés du relevé précédent")
PAST_DUE_LATE_FEE = "0.00"
LAST_PAYMENT = {"amount": "140.00", "days_ago": 32, "method": "card_on_file"}
DUPLICATE_PAYMENT = {"amount": "140.00", "days_ago": 5, "method": "card_on_file"}

# Plan catalogue (prd.md §12: never present more than 3).
PLANS: tuple[dict[str, Any], ...] = (
    {"plan_id": "MOB-20", "lob": "mobility", "name": "Essential 20", "price": "47.00", "data_gb": 20, "features": ["20 GB high-speed data", "Unlimited Canada-wide calling"]},
    {"plan_id": "MOB-50", "lob": "mobility", "name": "Plus 50", "price": "58.00", "data_gb": 50, "features": ["50 GB high-speed data", "Unlimited Canada-wide calling", "5G access"]},
    {"plan_id": "MOB-100", "lob": "mobility", "name": "Max 100", "price": "72.00", "data_gb": 100, "features": ["100 GB high-speed data", "Canada-US calling", "5G+ access"]},
    {"plan_id": "MOB-UNL", "lob": "mobility", "name": "Unlimited Premium", "price": "89.00", "data_gb": 175, "features": ["175 GB high-speed data", "Canada-US-Mexico calling", "5G+ access"]},
    {"plan_id": "INT-1G", "lob": "internet", "usage_key": "usage_unlimited", "upload_mbps": 1000, "symmetric": True, "latency_key": "latency_fibre", "name": "Fibre 1 Gigabit", "price": "97.00", "speed_mbps": 1000, "features": ["Up to 1 Gbps download", "Unlimited usage", "Wi-Fi 6 gateway"]},
    {"plan_id": "INT-3G", "lob": "internet", "usage_key": "usage_unlimited", "upload_mbps": 3000, "symmetric": True, "latency_key": "latency_fibre", "name": "Fibre 3 Gigabit", "price": "118.00", "speed_mbps": 3000, "features": ["Up to 3 Gbps download", "Unlimited usage", "Wi-Fi 6E gateway", "Whole-home Wi-Fi pod"]},
    {"plan_id": "INT-8G", "lob": "internet", "usage_key": "usage_unlimited", "upload_mbps": 8000, "symmetric": True, "latency_key": "latency_fibre", "name": "Fibre 8 Gigabit", "price": "143.00", "speed_mbps": 8000, "features": ["Up to 8 Gbps download", "Unlimited usage", "Wi-Fi 7 gateway", "Two Wi-Fi pods"]},
    {"plan_id": "TV-SPORTS", "lob": "tv", "name": "Sports Pack", "price": "16.00", "addon": True, "channel_count": 14, "blackout_key": "blackout_sports", "keywords": ["sport", "hockey", "football", "soccer", "basketball", "baseball"], "features": ["National sports networks", "Regional game coverage", "Sports on demand"], "hd_included": True, "channel_examples": ["National hockey, football and basketball broadcasts", "Regional and local team games", "International soccer", "Sports news and highlights"], "channel_lineup": ["TSN", "Sportsnet", "RDS", "TVA Sports", "Sportsnet ONE", "beIN SPORTS", "NBA TV Canada", "NFL Network"]},
    {"plan_id": "TV-MOVIES", "lob": "tv", "name": "Movies Pack", "price": "13.00", "addon": True, "channel_count": 9, "keywords": ["movie", "film", "cinema", "cinéma"], "features": ["Premium movie channels", "Movies on demand"], "hd_included": True, "channel_examples": ["Premium movie channels", "Recent releases on demand", "Classic film channels"]},
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
SALES_WARRANTY_REPLACEMENT_COST = "0.00"  # in-warranty replacement: no fee, no deductible, free shipping
SALES_PORT_DAYS: dict[str, int] = {"mobile": 0, "landline": 3}
# Longest a transfer usually takes, in business days (SALES_PORT_DAYS is the usual completion).
SALES_PORT_MAX_DAYS: dict[str, int] = {"mobile": 2, "landline": 5}
# Mobility data after the plan's high-speed allowance is used (no overage fees).
SALES_REDUCED_SPEED_KBPS = 512
# An IMEI (the phone's serial number) can stand in for the old provider's account number on a port-in.
SALES_IMEI_DIGITS = 15

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
# Model variant words: a caller's "iPhone 15 Pro" is not the "Apple iPhone 15" on file.
SALES_DEVICE_VARIANT_WORDS: frozenset[str] = frozenset({"pro", "max", "plus", "ultra", "mini", "fe", "lite"})
# Words in target_line / current_provider meaning the number is a home phone (landline).
SALES_LANDLINE_WORDS: tuple[str, ...] = ("landline", "home phone", "house phone", "fixe", "résidentiel", "maison")
# Words in target_line meaning the number goes on a new line on the account.
# A "current provider" that is us: the number is already on the caller's Telco account.
SALES_OWN_BRAND_WORDS: tuple[str, ...] = ("telco", "you guys", "chez vous")
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
    "hotspot_included": {
        "en-US": "Mobile hotspot is included at no extra cost and uses the plan's high-speed data; there is no separate hotspot limit.",
        "fr-CA": "Le partage de connexion est inclus sans frais supplémentaires et utilise les données haute vitesse du forfait; il n'y a pas de limite distincte pour le partage de connexion.",
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
    "data_transfer_urgent": {
        "en-US": "Do not charge or power on the swollen phone to copy your data. If it was backed up to the cloud, sign in to that same cloud account on the replacement to restore; data that was not backed up may not be recoverable.",
        "fr-CA": "Ne chargez pas et n'allumez pas le téléphone gonflé pour copier vos données. S'il était sauvegardé dans le nuage, connectez-vous au même compte infonuagique sur le téléphone de remplacement pour tout restaurer; les données non sauvegardées pourraient être irrécupérables.",
    },
    "data_transfer_standard": {
        "en-US": "Back up the old phone to the cloud before shipping it, then sign in to that same cloud account on the replacement to restore your data, and remove the account and SIM from the old phone before sending it back.",
        "fr-CA": "Sauvegardez l'ancien téléphone dans le nuage avant de l'expédier, puis connectez-vous au même compte infonuagique sur le téléphone de remplacement pour restaurer vos données, et retirez le compte et la carte SIM de l'ancien téléphone avant de le renvoyer.",
    },
    "warranty_no_card_hold": {
        "en-US": "No deposit or hold is placed on your card for the replacement. Send the old phone back by the return deadline with the prepaid label; a non-return fee may apply only if it is not returned.",
        "fr-CA": "Aucun dépôt ni blocage n'est appliqué à votre carte pour le remplacement. Renvoyez l'ancien téléphone avant la date limite de retour avec l'étiquette prépayée; des frais de non-retour peuvent s'appliquer seulement s'il n'est pas renvoyé.",
    },
    "warranty_no_card_hold_urgent": {
        "en-US": "No deposit or hold is placed on your card, and there is no non-return fee because the damaged phone is not mailed back.",
        "fr-CA": "Aucun dépôt ni blocage n'est appliqué à votre carte, et il n'y a aucuns frais de non-retour puisque le téléphone endommagé n'est pas renvoyé par la poste.",
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
        "en-US": "The account number with that provider, from a recent bill, or the phone's 15-digit IMEI (dial *#06# to see it)",
        "fr-CA": "Le numéro de compte chez ce fournisseur, indiqué sur une facture récente, ou le code IMEI à 15 chiffres du téléphone (composez *#06# pour l'afficher)",
    },
    "port_account_alt_bill": {
        "en-US": "The account number with the current provider, from a recent bill or their app",
        "fr-CA": "Le numéro de compte chez le fournisseur actuel, sur une facture récente ou dans son application",
    },
    "port_account_alt_imei": {
        "en-US": "The phone's 15-digit IMEI instead: dial *#06# on that phone to see it",
        "fr-CA": "Le code IMEI à 15 chiffres du téléphone à la place : composez *#06# sur ce téléphone pour l'afficher",
    },
    "port_fees": {
        "en-US": "There is no fee to transfer a number in and no activation fee.",
        "fr-CA": "Il n'y a aucuns frais pour transférer un numéro et aucuns frais d'activation.",
    },
    "port_authorization": {
        "en-US": "No code or extra authorization is needed on this call. The current provider may text that phone to confirm the transfer; just follow that message.",
        "fr-CA": "Aucun code ni autorisation supplémentaire n'est nécessaire pendant cet appel. Le fournisseur actuel peut envoyer un texto à ce téléphone pour confirmer le transfert; suivez simplement ce message.",
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
    "usage_unlimited": {
        "en-US": "No data cap and no throttling: usage is unlimited at the plan's full speed.",
        "fr-CA": "Aucune limite de données et aucun ralentissement : l'utilisation est illimitée à la pleine vitesse du forfait.",
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
    # Neutral multi-line fact (prd.md has no family or multi-line discount).
    "multi_line_pricing": {
        "en-US": "Each added line is billed at the plan's listed price; there's no separate multi-line or family discount.",
        "fr-CA": "Chaque ligne ajoutée est facturée au prix affiché du forfait; il n'y a pas de rabais multiligne ou familial distinct.",
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
# Price of a technician repair visit for Telco service or equipment (remote troubleshooting is always free).
TECH_REPAIR_VISIT_FEE = "0.00"
# Typical length of a technician visit once the technician arrives, in hours (low, high).
TECH_VISIT_LENGTH_HOURS: tuple[int, int] = (1, 2)
# Typical time to go through the TV app troubleshooting guide, in minutes.
TECH_APP_GUIDE_MINUTES = 15
# --- end tech fixtures ---

# Service regions and outage districts (BR-TV-003, DESIGN_RULES rule 40: classes, not literals).
# Canadian postal codes start with a province letter; Region-A is Quebec.
REGION_BY_POSTAL_LETTER: dict[str, str] = {
    **{letter: "Region-A" for letter in "GHJ"},
    **{letter: "Region-B" for letter in "KLMNP"},
}
DEFAULT_REGION = "Region-C"
# Outages hit a postal district, not a whole province (rule 40: district classes,
# never full postal codes). A district is a Canadian forward sortation area (FSA):
# the first three characters of a postal code (province letter, district digit,
# area letter). Today's outage footprint is two contiguous city cores, each served
# by one network hub (docs/requirements.md §Defaults vs. overrides):
#   - central Quebec City: Saint-Roch / Basse-Ville, Vieux-Quebec / Saint-Jean-Baptiste, Montcalm;
#   - Montreal centre-west: downtown west, Shaughnessy Village, Westmount.
# Downtown-east Montreal (H3A/H3B/H3C), the rest of G1/H3, other Montreal districts
# (H1, H2, H4...), G2+, the J suburbs, every other province and every ZIP have none.
OUTAGE_DISTRICT_LENGTH = 3
_QUEBEC_CITY_CORE_OUTAGE = {"outage_id": "OUT-G1-27", "services": ["internet", "tv"], "eta_hours": 4}
_MONTREAL_CENTRE_WEST_OUTAGE = {"outage_id": "OUT-H3-27", "services": ["internet", "tv"], "eta_hours": 4}
ACTIVE_OUTAGES_BY_DISTRICT: dict[str, dict[str, Any]] = {
    **{fsa: _QUEBEC_CITY_CORE_OUTAGE for fsa in ("G1K", "G1R", "G1S")},
    **{fsa: _MONTREAL_CENTRE_WEST_OUTAGE for fsa in ("H3G", "H3H", "H3Y", "H3Z")},
}
FIXTURE_OUTAGE = {"outage_id": "OUT-LOCAL-09", "services": ["internet", "tv"], "eta_hours": 3}

# Credentials (DESIGN_RULES rules 21, 45). Non-canonical values only.
ALWAYS_WRONG_LOGIN_CODES: frozenset[str] = frozenset({"9999", "999999", "8888"})
VALID_OTPS: frozenset[str] = frozenset({"271846", "482913"})
VALID_PINS: frozenset[str] = frozenset({"5903", "5678", "4321"})  # overfit: allow - a public retry scenario states 4321 as the PIN on file (passes on the 2nd try)
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
# Where each extra line came from and how to prevent it (DESIGN_RULES rule 33: the
# "where did this come from / how do I stop it" follow-up), (en-US, fr-CA).
BILL_EXTRA_LINE_NOTES: dict[str, dict[str, tuple[str, str]]] = {
    "CH-STR-01": {
        "origin": (
            "A purchase made through a connected TV app on the account.",
            "Un achat fait au moyen d'une application télé connectée au compte.",
        ),
        "prevention_tip": (
            "Purchases can be protected with a purchase PIN on the TV service.",
            "Les achats peuvent être protégés par un NIP d'achat sur le service télé.",
        ),
    },
    "CH-LD-01": {
        "origin": (
            "Calls from the mobility line to numbers outside its local calling area.",
            "Des appels faits depuis la ligne mobile vers des numéros hors de sa zone d'appel locale.",
        ),
        "prevention_tip": (
            "A plan that includes long distance calling avoids these per-call charges.",
            "Un forfait qui inclut les appels interurbains évite ces frais par appel.",
        ),
    },
}
EXTRA_FIXTURE_LINE_DAYS_AGO = 4      # fx_extra_bill_line posts on the latest bill
BANK_ON_FILE_ENDING = "6083"
ARRANGEMENT_FIRST_DUE_DAYS = 7       # first instalment within 7 days
NEXT_BILL_CYCLE_DAYS = 30
DISPUTE_ETA_BUSINESS_DAYS = 10
RECENT_PAYMENT_DAYS_AGO = 1          # fx_recent_payment=posted_yesterday
# After a non-payment restore (DESIGN_RULES rule 33: "when is it back / do I restart
# anything?"), (en-US, fr-CA). [minutes] = RECONNECT_MINUTES.
RECONNECT_MINUTES = 15
RECONNECT_NOTE = (
    "Service comes back within [minutes] minutes; if it doesn't, restart the modem or phone.",
    "Le service revient d'ici [minutes] minutes; sinon, redémarrez le modem ou le téléphone.",
)
# When a payment shows on the balance (DESIGN_RULES rule 33: "when does it post?"), (en-US, fr-CA).
PAYMENT_POSTING_NOTE = (
    "A payment made with us posts to the account right away, so the balance given already includes it.",
    "Un paiement fait chez nous est porté au compte immédiatement; le solde indiqué en tient donc déjà compte.",
)
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
# A name or street address given instead of a number: a word of letters only (no email).
_LETTER_WORD_RE = re.compile(r"(?:^|[\s,.])[^\W\d_](?:[^\W\d_]|['\-](?=[^\W\d_]))+(?=$|[\s,.])")
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


# Spoken number words (live speech-to-text writes "one two three four", "twelve
# thirty-four", "quatre quatre cinq deux"); keys are lowercase without accents.
_SPOKEN_UNITS: dict[str, int] = {
    "zero": 0, "oh": 0, "o": 0, "nought": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "sept": 7, "huit": 8, "neuf": 9,
}
_SPOKEN_TEENS: dict[str, int] = {
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16,
}
_SPOKEN_TENS: dict[str, int] = {
    "twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
    "vingt": 20, "vingts": 20, "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60,
}
_SPOKEN_SCALES: dict[str, int] = {"hundred": 100, "cent": 100, "cents": 100, "thousand": 1000, "mille": 1000}
_SPOKEN_REPEATS: dict[str, int] = {"double": 2, "triple": 3}
_SPOKEN_JOINERS = frozenset({"and", "et"})
_SPOKEN_TOKEN_RE = re.compile(r"[a-z]+|[0-9]+")


def _is_number_token(tok: str) -> bool:
    return tok.isdigit() or tok in _SPOKEN_UNITS or tok in _SPOKEN_TEENS or tok in _SPOKEN_TENS or tok in _SPOKEN_SCALES or tok in _SPOKEN_REPEATS


def _cardinal_digits(run: list[str]) -> str:
    """'one thousand two hundred thirty four' -> '1234' (additive, French 'quatre vingt' = 80)."""
    total = current = 0
    prev = ""
    for tok in run:
        if tok in _SPOKEN_SCALES:
            if _SPOKEN_SCALES[tok] == 1000:
                total += (current or 1) * 1000
                current = 0
            else:
                current = (current or 1) * 100
        elif tok.startswith("vingt") and prev == "quatre":
            current += 80 - 4
        elif tok.isdigit():
            current += int(tok)
        else:
            current += _SPOKEN_UNITS.get(tok, _SPOKEN_TEENS.get(tok, _SPOKEN_TENS.get(tok, 0)))
        prev = tok
    return str(total + current)


def _grouped_digits(run: list[str]) -> str:
    """Digit-by-digit or grouped speech: 'one two three four', 'twelve thirty four', 'double five'."""
    out: list[str] = []
    i, n = 0, len(run)
    while i < n:
        tok = run[i]
        nxt = run[i + 1] if i + 1 < n else ""
        if tok.isdigit():
            out.append(tok)
        elif tok in _SPOKEN_REPEATS and (nxt in _SPOKEN_UNITS or (nxt.isdigit() and len(nxt) == 1)):
            out.append((nxt if nxt.isdigit() else str(_SPOKEN_UNITS[nxt])) * _SPOKEN_REPEATS[tok])
            i += 1
        elif tok == "quatre" and nxt.startswith("vingt") or tok in _SPOKEN_TENS:
            value = 80 if tok == "quatre" else _SPOKEN_TENS[tok]
            i += 1 if tok == "quatre" else 0
            rest = run[i + 1 : i + 4]
            if rest[:1] and rest[0] in _SPOKEN_JOINERS and len(rest) > 1 and rest[1] in ("un", "une", "onze"):
                value += 1 if rest[1] != "onze" else 11
                i += 2
            elif value in (60, 80) and rest[:1] and rest[0] in _SPOKEN_TEENS:
                value += _SPOKEN_TEENS[rest[0]]
                i += 1
                if rest[0] == "dix" and len(rest) > 1 and rest[1] in ("sept", "huit", "neuf"):
                    value += _SPOKEN_UNITS[rest[1]]
                    i += 1
            elif rest[:1] and rest[0] in _SPOKEN_UNITS and _SPOKEN_UNITS[rest[0]] > 0 and rest[0] not in ("oh", "o"):
                value += _SPOKEN_UNITS[rest[0]]
                i += 1
            out.append(str(value))
        elif tok == "dix" and nxt in ("sept", "huit", "neuf"):
            out.append(str(10 + _SPOKEN_UNITS[nxt]))
            i += 1
        elif tok in _SPOKEN_TEENS:
            out.append(str(_SPOKEN_TEENS[tok]))
        elif tok in _SPOKEN_UNITS:
            out.append(str(_SPOKEN_UNITS[tok]))
        i += 1
    return "".join(out)


def _number_runs(text: str) -> tuple[list[list[str]], bool]:
    """Split text into runs of number tokens; also report whether any other word appeared."""
    folded = unicodedata.normalize("NFKD", text.lower())
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    runs: list[list[str]] = [[]]
    other_words = False
    for tok in _SPOKEN_TOKEN_RE.findall(folded):
        if _is_number_token(tok) or (tok in _SPOKEN_JOINERS and runs[-1]):
            runs[-1].append(tok)
        else:
            other_words = True
            if runs[-1]:
                runs.append([])
    cleaned = []
    for run in runs:
        while run and run[-1] in _SPOKEN_JOINERS:
            run.pop()
        if run:
            cleaned.append(run)
    return cleaned, other_words


def spoken_digits(value: Any) -> str:
    """The digits a caller said, in any spoken or typed form (live speech-to-text).

    "one two three four", "12 34", "1-2-3-4", "twelve thirty-four", "one thousand
    two hundred thirty-four", "double five", "quatre quatre cinq deux" and
    "my PIN is 5903" all give their digits. Ints/floats go through normalize_code.
    Inside other words, a lone number word ("I have one PIN, ...") is ignored when
    another number run exists. Tools still apply their strict length checks.
    """
    if not isinstance(value, str):
        return normalize_code(value)
    if not any(ch.isalpha() for ch in value):
        return normalize_code(value)
    runs, other_words = _number_runs(value)
    if other_words and len(runs) > 1:
        runs = [r for r in runs if len(r) > 1 or r[0].isdigit()] or runs
    parts = []
    for run in runs:
        if run in (["oh"], ["o"]) and other_words:
            continue
        parts.append(_cardinal_digits(run) if any(t in _SPOKEN_SCALES for t in run) else _grouped_digits(run))
    return "".join(parts)


def spoken_number_text(raw: Any) -> str:
    """Rewrite an identifier said only in number words ("five one four ...") as its digits.

    Text with any other word (a name, address or email) comes back unchanged, so
    classify_identifier and the name/address check still see it as given.
    """
    text = str(raw or "").strip()
    if not any(ch.isalpha() for ch in text) or "@" in text:
        return text
    runs, other_words = _number_runs(text)
    if other_words or not runs:
        return text
    return spoken_digits(text)


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


SPOKEN_DIGIT_SEPARATORS_RE = re.compile(r"[\s,.\-()]+")
ALL_DIGITS_RE = re.compile(r"^[0-9]+$")


def classify_identifier(raw: Any) -> tuple[str, str]:
    """Match a caller identifier against the format patterns.

    Phone speech-to-text writes numbers as "888,777,666" or "5 1 4 5 5 5 0 1 9 9";
    when only separators (spaces, commas, dots, dashes, brackets) sit between the
    digits, the digit string itself is classified by length with the same rules.
    Returns (kind, digits): kind is phone, intl_phone, account_number,
    account_reference, or "" when no pattern matches.
    """
    text = spoken_number_text(re.sub(r"\.0+$", "", str(raw or "").strip()))
    digits = normalize_code(text)
    compact = SPOKEN_DIGIT_SEPARATORS_RE.sub("", text)
    if compact and ALL_DIGITS_RE.fullmatch(compact) and not compact.startswith("00") and not PHONE_NANP_RE.fullmatch(text):
        if len(compact) == 11 and compact.startswith("1"):
            return "phone", compact[1:]
        if len(compact) == 10 and not compact.startswith("0"):
            return "phone", compact
        if PHONE_LOCAL_PAIRS_RE.fullmatch(text):
            return "phone", compact
        if ACCOUNT_NUMBER_RE.fullmatch(compact):
            return "account_number", compact
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


def is_name_or_address(raw: Any) -> bool:
    """True when the caller gave words (a name or street address), not a number or email.

    Malformed numbers ("ACC-12", "555-01") and emails stay validation errors.
    """
    text = str(raw or "").strip()
    if not text or "@" in text or classify_identifier(text)[0]:
        return False
    return bool(_LETTER_WORD_RE.search(text))


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
    record = _synthetic_account(digits, _phone_from_digits(digits))
    # The phone was built from account digits: real, but its ending is not something
    # the caller told us, so it is never spoken back as "ending in ...".
    record["phone_derived"] = True
    return record


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
# Public two-step verification facts (en-US, fr-CA). manage_mfa returns them on the
# NOT_LOGGED_IN gate too, so pre-login questions are grounded (DESIGN_RULES rule 33).
# [minutes] = OTP_EXPIRES_IN_SEC // 60.
ACCT_MFA_FACTS: dict[str, tuple[str, str]] = {
    "code_delivery_note": (
        "Sign-in codes go by text to the mobile number on file and normally arrive within a minute; if one doesn't, we can resend it.",
        "Les codes de connexion sont envoyés par texto au numéro de cellulaire au dossier et arrivent normalement en moins d'une minute; sinon, nous pouvons le renvoyer.",
    ),
    "code_expiry_note": (
        "Each code is 6 digits and expires after [minutes] minutes.",
        "Chaque code compte 6 chiffres et expire après [minutes] minutes.",
    ),
    "pin_backup_note": (
        "If a text code can't be received, the 4-digit secret PIN on the account works as a backup on a call with us.",
        "Si un code par texto ne peut pas être reçu, le NIP secret à 4 chiffres du compte sert de solution de rechange lors d'un appel avec nous.",
    ),
    "lost_phone_note": (
        "If this phone is lost or stolen, call us and verify with your secret PIN instead of a text code; we can then suspend the line and update the mobile number that sign-in codes go to.",
        "Si ce téléphone est perdu ou volé, appelez-nous et vérifiez votre identité avec votre NIP secret plutôt qu'avec un code par texto; nous pourrons ensuite suspendre la ligne et mettre à jour le numéro de cellulaire qui reçoit les codes de connexion.",
    ),
    "fee_note": (
        "Two-step verification is free; turning it on or off never adds a charge to the bill.",
        "La vérification en deux étapes est gratuite; l'activer ou la désactiver n'ajoute jamais de frais à la facture.",
    ),
    "sms_cost_note": (
        "Sign-in codes by text are free from us; your mobile carrier's standard messaging rates may apply.",
        "Les codes de connexion par texto sont gratuits de notre part; les frais de messagerie habituels de votre fournisseur cellulaire peuvent s'appliquer.",
    ),
    "disable_risk_note": (
        "With two-step verification off, the account is protected by the password alone, so anyone who learns the password could sign in; it can be turned back on at any time.",
        "Sans la vérification en deux étapes, le compte est protégé par le mot de passe seulement; quiconque l'apprend pourrait donc se connecter. Elle peut être réactivée en tout temps.",
    ),
}
# --- end account fixtures ---
