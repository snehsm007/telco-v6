from typing import Any



def start_number_transfer(
    number_to_transfer: str | int | float = "",
    current_provider: str = "",
    current_account_number: str | int | float = "",
    transfer_pin: str | int | float = "",
    target_line: str = "",
    language: str = "",
) -> dict[str, Any]:
    """Transfers (ports) a phone number in from another provider, onto an existing line or
      a new line. With no number yet it returns required_port_checklist without login.
      Starting the transfer needs login and a valid 10-digit number. Never returns any
      PIN.

    Args:
      number_to_transfer: The 10-digit number to bring over, as said; empty if the
        caller doesn't have it yet.
      current_provider: The provider the number is with now (the one it is leaving).
      current_account_number: The caller's account number with that provider, as said,
        or the phone's 15-digit IMEI when they don't have the account number.
      transfer_pin: Transfer PIN from that provider, if they have one; never repeat it
        back.
      target_line: Where the number goes: new_line (add a line, e.g. a family member),
        existing_line, the number of the line it replaces, or landline_to_mobile.
      language: Active language code (en-US or fr-CA).

    Returns:
      status, data (status submitted or pending_details, transfer_id,
        estimated_completion_display, typical_timeframe_display, number_type, target,
        temporary_number_last4, target_line_last4, sms_updates, missing_details, required_port_checklist,
        keep_old_service_note, fees_note, authorization_note, account_number_alternatives), error_message, tracking_id. Errors add error
        (NOT_LOGGED_IN, INVALID_INPUT) and agent_action.
    """
    ctx = globals().get("context")
    state = getattr(ctx, "state", None) if ctx is not None else None
    if state is None and isinstance(ctx, dict):
        state = ctx
    return start_number_transfer_impl(
        number_to_transfer=number_to_transfer,
        current_provider=current_provider,
        current_account_number=current_account_number,
        transfer_pin=transfer_pin,
        target_line=target_line,
        language=language,
        state=state,
    )


# --- BEGIN GENERATED SHARED BUNDLE (edit lib/, then run `make bundle`) ---
# uses: from lib.sales import start_number_transfer_impl
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
import contextvars
import hashlib
import re
import unicodedata

SALES_IMEI_DIGITS = 15  # pragma: no cover

SALES_LANDLINE_WORDS: tuple[str, ...] = ("landline", "home phone", "house phone", "fixe", "résidentiel", "maison")  # pragma: no cover

SALES_NEW_LINE_WORDS: tuple[str, ...] = ("new", "add", "family", "nouvelle", "ajout", "famille")  # pragma: no cover

SALES_OWN_BRAND_WORDS: tuple[str, ...] = ("telco", "you guys", "chez vous")  # pragma: no cover

def _sales_has(text: str, words: tuple[str, ...] | frozenset[str]) -> bool:  # pragma: no cover
    low = str(text or "").lower()
    return any(w in low for w in words)

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

def resolve_locale(language: str | None) -> str:  # pragma: no cover
    """Normalize a language tag or prefix to a supported locale (en-US or fr-CA)."""
    low = str(language or "").strip().lower().replace("_", "-")
    if low.startswith("fr"):
        return "fr-CA"
    return "en-US"

def spoken_line(key: str, language: str | None = "en-US", **slots: object) -> str:  # pragma: no cover
    """Return the fixed spoken line for `key` and `language`, filling any `[slot]` placeholders."""
    locale = resolve_locale(language)
    table = SPOKEN_LINES.get(key, {})
    template = table.get(locale) or table.get("en-US") or ""
    for slot_name, slot_val in slots.items():
        template = template.replace(f"[{slot_name}]", str(slot_val))
    return template

def login_offer_line(state: dict[str, Any], lang: str) -> str:  # pragma: no cover
    """The login offer for a found account: a 6-digit code to the number on file, or the 4-digit PIN."""
    last4 = str(state.get("caller_provided_phone_last4") or ("" if state.get("phone_derived") else state.get("phone_last4")) or "")
    offer = spoken_line("otp_callback_confirm", lang, last4=last4) if last4 else spoken_line("otp_callback_on_file", lang)
    return offer + " " + spoken_line("pin_alternative", lang)

def _sales_login_offer(state: dict[str, Any], lang: str) -> dict[str, Any]:  # pragma: no cover
    """Not logged in yet: the login offer to use when the caller is ready to start (never improvised)."""
    if state.get("auth_status") == "pass" or not state.get("account_id"):
        return {}
    return {"code_length": 6, "pin_length": 4, "login_offer_line": login_offer_line(state, lang)}

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

def _sales_own_number(state: dict[str, Any], number: str) -> bool:  # pragma: no cover
    """True when the number to transfer is the logged-in account's own phone number."""
    own = {str(state.get(k) or "") for k in ("phone_last4", "caller_provided_phone_last4")} - {""}
    record_phone = normalize_code(account_record(state).get("phone", ""))
    return number == record_phone or number[-4:] in own

SALES_PLACEHOLDERS: frozenset[str] = frozenset(  # pragma: no cover
    {"", "unknown", "external", "none", "n/a", "na", "tbd", "pending", "not sure", "?", "inconnu", "aucun", "other", "autre"}
)

def _sales_placeholder(value: Any) -> bool:  # pragma: no cover
    return str(value if value is not None else "").strip().lower() in SALES_PLACEHOLDERS

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

resolve_copy_locale = resolve_locale  # pragma: no cover

def _sales_text(key: str, lang: str) -> str:  # pragma: no cover
    """Sales copy in the call language only (no sibling-language keys in replies)."""
    table = SALES_COPY.get(key, {})
    return table.get(resolve_copy_locale(lang)) or table.get("en-US", "")

def _sales_port_checklist(lang: str) -> list[str]:  # pragma: no cover
    keys = ("port_check_number", "port_check_provider", "port_check_account", "port_check_pin", "port_check_active")
    return [_sales_text(k, lang) for k in keys]

SALES_PORT_DAYS: dict[str, int] = {"mobile": 0, "landline": 3}  # pragma: no cover

def _sales_business_date(days: int) -> str:  # pragma: no cover
    """ISO date `days` business days from today (0 = today)."""
    current = datetime.now(timezone.utc)
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current.strftime("%Y-%m-%d")

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

def _sales_port_eta(kind: str, lang: str) -> dict[str, str]:  # pragma: no cover
    iso = _sales_business_date(SALES_PORT_DAYS.get(kind, 0))
    return {"date": iso, "display": display_date(iso, lang)}

def _sales_port_facts(lang: str) -> dict[str, Any]:  # pragma: no cover
    """Follow-up facts callers ask before giving details: cost, authorization, no account number (rule 33)."""
    return {
        "fees_note": _sales_text("port_fees", lang),
        "authorization_note": _sales_text("port_authorization", lang),
        "multi_line_note": _sales_text("multi_line_pricing", lang),
        "account_number_alternatives": [_sales_text(k, lang) for k in ("port_account_alt_bill", "port_account_alt_imei")],
    }

SALES_PORT_MAX_DAYS: dict[str, int] = {"mobile": 2, "landline": 5}  # pragma: no cover

def _sales_port_timeframe(kind: str, lang: str) -> str:  # pragma: no cover
    """Typical completion window for a transfer, so "how long does it take?" never waits for the details."""
    low, high = SALES_PORT_DAYS.get(kind, 0), SALES_PORT_MAX_DAYS.get(kind, 0)
    fr = resolve_copy_locale(lang) == "fr-CA"
    if low == 0:
        return f"le jour même, jusqu'à {high} jours ouvrables" if fr else f"the same day, up to {high} business days"
    return f"{low} à {high} jours ouvrables" if fr else f"{low} to {high} business days"

def append_list(state: dict[str, Any], key: str, value: str) -> list[str]:  # pragma: no cover
    """Append to a comma-separated list stored in one STRING session variable."""
    items = [p for p in str(state.get(key) or "").split(",") if p]
    if value not in items:
        items.append(value)
    state[key] = ",".join(items)
    return items

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

def dispatch_sms(state: dict[str, Any], purpose: str) -> dict[str, Any]:  # pragma: no cover
    """Record a text message to the mobile number on file; returns its delivery facts."""
    dest = str(state.get("phone_last4") or account_record(state)["phone"][-4:])
    sent = [p for p in str(state.get("sms_sent") or "").split(",") if p]
    sent.append(purpose)
    state["sms_sent"] = ",".join(sent[-10:])
    return {"sms_sent": True, "destination_last4": dest, "sms_purpose": purpose}

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

DUMMY_NUMBERS: frozenset[str] = frozenset({"1234567890", "0123456789", "9876543210"})  # pragma: no cover

def is_weak_code(digits: str) -> bool:  # pragma: no cover
    """A code made of one repeated digit (e.g. all sevens) is never a valid credential."""
    return bool(digits) and len(set(digits)) == 1

def is_plausible_phone(digits: str) -> bool:  # pragma: no cover
    """A 10-digit number that isn't one repeated digit or an obvious dummy run (Postel: accept generously)."""
    if len(digits) != 10 or not digits.isdigit():
        return False
    return not is_weak_code(digits) and digits not in DUMMY_NUMBERS

def normalize_identifier(raw: object) -> dict[str, str]:  # pragma: no cover
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
    data["spoken_message"] = login_offer_line(state, lang)
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

def start_number_transfer_impl(  # pragma: no cover
    number_to_transfer: str | int | float = "",
    current_provider: str = "",
    current_account_number: str | int | float = "",
    transfer_pin: str | int | float = "",
    target_line: str = "",
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Port a number in from another provider. No number yet = the checklist; starting needs login."""
    state = get_state(state, session_state)
    lang = session_language(state, language)
    err = check_mock_error(state, lang, "start_number_transfer")
    if err:
        return err
    raw_number = re.sub(r"\.0+$", "", str(number_to_transfer if number_to_transfer is not None else "").strip())
    kind_text = f"{target_line or ''} {current_provider or ''}"
    number_type = "landline" if _sales_has(kind_text, SALES_LANDLINE_WORDS) else "mobile"
    if _sales_placeholder(raw_number):
        reference = tracking_id("start_number_transfer", state.get("account_id", ""), "checklist")
        state["last_tracking_id"] = reference
        mobile_eta = _sales_port_eta("mobile", lang)
        landline_eta = _sales_port_eta("landline", lang)
        return ok_reply(
            {
                "status": "pending_details",
                "transfer_started": False,
                "required_port_checklist": _sales_port_checklist(lang),
                "mobile_completion_display": mobile_eta["display"],
                "landline_completion_display": landline_eta["display"],
                "typical_timeframe_display": _sales_port_timeframe(number_type, lang),
                "mobile_typical_timeframe_display": _sales_port_timeframe("mobile", lang),
                "landline_typical_timeframe_display": _sales_port_timeframe("landline", lang),
                "keep_old_service_note": _sales_text("port_keep_active", lang),
                **_sales_port_facts(lang),
                "login_required_to_start": True,
                **_sales_login_offer(state, lang),
            },
            reference,
            language=lang,
        )

    reference = tracking_id("start_number_transfer", state.get("account_id", ""), normalize_code(raw_number))
    ident = normalize_identifier(raw_number)
    if ident["kind"] != "phone" or not is_plausible_phone(ident["value"]):
        return validation_error(
            state,
            "The number to transfer must be a valid 10-digit phone number.",
            "Ask for the 10-digit number to transfer, one digit at a time.",
            reference,
            lang,
        )
    gate = require_login(state, lang, "start_number_transfer")
    if gate:
        return gate
    number = ident["value"]
    account_id = str(state.get("account_id") or "")

    if isinstance(current_account_number, (int, float)) and not isinstance(current_account_number, bool):
        account_number = normalize_code(current_account_number)
    else:
        text = re.sub(r"^(\d+)\.0+$", r"\1", str(current_account_number or "").strip())
        account_number = re.sub(r"[\s\-\.]", "", text)
    if _sales_placeholder(account_number):
        account_number = ""
    if account_number and not re.fullmatch(r"[A-Za-z0-9]{4,20}", account_number):
        return validation_error(
            state,
            "The account number with the current provider looks incomplete.",
            "Ask again for the provider's account number or the phone's IMEI.",
            reference,
            lang,
        )
    pin_given = not _sales_placeholder(transfer_pin)
    pin_digits = normalize_code(transfer_pin) if pin_given else ""
    if pin_given and not (4 <= len(pin_digits) <= 10):
        return validation_error(
            state, "A transfer PIN has 4 to 10 digits.", "Ask for the transfer PIN again; never repeat it back.", reference, lang
        )
    provider = "" if _sales_placeholder(current_provider) else str(current_provider).strip()
    # Number portability: the losing carrier is identified from the number itself,
    # so a caller who doesn't know the provider's name is never blocked on it.
    provider_found_by_lookup = not provider
    if provider_found_by_lookup:
        provider = _sales_text("port_provider_lookup", lang)

    account_identifier = "imei" if re.fullmatch(rf"\d{{{SALES_IMEI_DIGITS}}}", account_number) else "account_number"
    target_given = not _sales_placeholder(target_line)
    target_digits = normalize_code(target_line)
    target_last4 = ""
    if len(target_digits) >= 10:
        target = "existing_line"
        target_last4 = target_digits[-4:]
    elif _sales_has(target_line, SALES_NEW_LINE_WORDS):
        target = "new_line"
    else:
        target = "existing_line"

    # The caller's own Telco number (e.g. their landline onto their mobile) is an internal
    # move: there is no losing provider, so no outside account number is needed.
    internal_move = (
        number_type == "landline"
        and _sales_own_number(state, number)
        and (provider_found_by_lookup or _sales_has(provider, SALES_OWN_BRAND_WORDS))
    )
    if internal_move:
        provider = _sales_text("port_own_account", lang)
    missing = [] if internal_move else [name for name, val in (("current_account_number", account_number),) if not val]
    eta = _sales_port_eta(number_type, lang)
    data: dict[str, Any] = {
        "number_last4": number[-4:],
        "number_type": number_type,
        "current_provider": provider,
        "provider_found_by_lookup": provider_found_by_lookup and not internal_move,
        "internal_move": internal_move,
        "current_account_number_last4": account_number[-4:] if account_number else "",
        "account_identifier_type": account_identifier if account_number else "",
        "transfer_pin_received": bool(pin_digits),
        "target": target,
        "typical_timeframe_display": _sales_port_timeframe(number_type, lang),
        "keep_old_service_note": _sales_text("port_keep_active", lang),
        "fees_note": _sales_text("port_fees", lang),
        "authorization_note": _sales_text("port_authorization", lang),
        "multi_line_note": _sales_text("multi_line_pricing", lang),
    }
    if internal_move:
        data["internal_move_note"] = _sales_text("port_internal_move", lang)
        del data["keep_old_service_note"]
    if target_last4:
        data["target_line_last4"] = target_last4
    if missing:
        state["last_tracking_id"] = reference
        data.update(
            {
                "status": "pending_details",
                "transfer_started": False,
                "missing_details": missing,
                "required_port_checklist": _sales_port_checklist(lang),
                "account_number_alternatives": _sales_port_facts(lang)["account_number_alternatives"],
                # Not asked yet: never present a default the caller didn't choose.
                "target": target if target_given else "not_given",
            }
        )
        reply = ok_reply(data, reference, language=lang)
        reply["agent_action"] = "Ask the caller for the missing_details, then call again."
        return reply

    transfer_id = "PT-" + tracking_id("number_transfer", account_id, number)[1:]
    started = [t for t in str(state.get("sales_transfers") or "").split(",") if t]
    already = transfer_id in started
    data.update(
        {
            "status": "submitted",
            "transfer_started": True,
            "already_submitted": already,
            "transfer_id": transfer_id,
            "estimated_completion_date": eta["date"],
            "estimated_completion_display": eta["display"],
            "line_note": _sales_text("port_temporary_number" if target == "new_line" else "port_existing_line", lang),
            "sms_updates": True,
        }
    )
    if target == "new_line":
        seed = int(normalize_code(tracking_id("temporary_number", account_id, number)) or "0")
        temp = str(seed % 10000).zfill(4)
        if is_weak_code(temp) or temp == number[-4:]:
            temp = str((seed + 1237) % 10000).zfill(4)
        data["temporary_number_last4"] = temp
    if not already:
        append_list(state, "sales_transfers", transfer_id)
        data["sms_destination_last4"] = dispatch_sms(state, "port_updates")["destination_last4"]
    state["last_tracking_id"] = transfer_id
    return ok_reply(data, transfer_id, language=lang)
# --- END GENERATED SHARED BUNDLE ---
