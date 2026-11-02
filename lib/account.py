"""Account management tools (docs/tdd.md §4 Account, PRD §14).

Password reset (identified only), two-step verification (MFA) with an email
step-up for disabling, lost/stolen and travel suspensions, cancellation and
port-out with a two-step confirmation, and contact-detail updates.

Every tool returns data plus one `spoken_summary` in the call language; the
prompt owns the conversation. Private helpers are prefixed `_acct_` so names
stay unique across lib/*.py (the bundler inlines them into one file).
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from lib.core import (
    account_record,
    append_list,
    check_mock_error,
    date_in,
    dispatch_sms,
    fixture,
    fixture_flag,
    get_state,
    money,
    require_login,
    service_status,
    session_language,
    validation_error,
)
from lib.fakes import (
    ACCT_BILLING_CYCLE_DAYS,
    ACCT_CONTRACT_TERMS,
    ACCT_EQUIPMENT_RETURN_DAYS,
    ACCT_LINES_OF_BUSINESS,
    ACCT_MFA_METHOD,
    ACCT_PORT_OUT_COMPLETION_DAYS,
    ACCT_PORTABLE_LINES,
    BILL_CYCLE_DAYS_AGO,
    PASSWORD_RESET_VALID_MINUTES,
    SERVICE_PRICES,
    is_plausible_phone,
    only_digits,
    read_count,
)
from lib.replies import error_reply, ok_reply, tracking_id

_ACCT_TRUE = ("true", "1", "yes", "y", "oui", "confirmed", "confirm")

_ACCT_LOB_ALIASES: dict[str, str] = {
    "mobility": "mobility", "mobile": "mobility", "wireless": "mobility", "cell": "mobility",
    "cellular": "mobility", "phone_plan": "mobility", "cellulaire": "mobility", "mobilite": "mobility",
    "internet": "internet", "home_internet": "internet", "wifi": "internet", "fibre": "internet",
    "fiber": "internet",
    "tv": "tv", "television": "tv", "tele": "tv", "fibe_tv": "tv",
    "homephone": "homephone", "home_phone": "homephone", "landline": "homephone",
    "residential_phone": "homephone", "ligne_residentielle": "homephone", "home_line": "homephone",
}

# Keyword fallback, checked in this order (home phone before mobile, "telephone" is not TV).
_ACCT_LOB_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("homephone", r"\b(?:home ?phone|landline|land line|home line|residenti\w*|fixe)\b"),
    ("mobility", r"\b(?:mobile|mobility|wireless|cell ?phone|cellular|cellulaire|mobilite)\b"),
    ("internet", r"\b(?:internet|wi ?fi|modem)\b"),
    ("tv", r"\b(?:tv|television|tele|cable)\b"),
)

_ACCT_LOB_NAMES: dict[str, dict[str, str]] = {
    "mobility": {"en-US": "mobile service", "fr-CA": "service mobile"},
    "internet": {"en-US": "internet service", "fr-CA": "service Internet"},
    "tv": {"en-US": "TV service", "fr-CA": "service de télé"},
    "homephone": {"en-US": "home phone service", "fr-CA": "service de téléphonie résidentielle"},
}

_ACCT_FIELD_ALIASES: dict[str, str] = {
    "email": "email", "e_mail": "email", "email_address": "email", "courriel": "email",
    "mobile_number": "mobile_number", "mobile": "mobile_number", "phone": "mobile_number",
    "phone_number": "mobile_number", "cell": "mobile_number", "contact_number": "mobile_number",
    "mailing_address": "mailing_address", "address": "mailing_address", "billing_address": "mailing_address",
    "postal_address": "mailing_address", "adresse": "mailing_address",
}

_ACCT_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")


def _acct_text(lang: str, en: str, fr: str) -> str:
    """One string in the call language (never both; DESIGN_RULES rule 5)."""
    return fr if lang == "fr-CA" else en


def _acct_flag(value: Any) -> bool:
    """Read a true/false argument the model may send as bool, number or text."""
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in _ACCT_TRUE


def _acct_key(value: Any) -> str:
    """Lower-case, accent-light, underscore-joined form of a free-text enum argument."""
    text = str(value or "").strip().lower()
    for src, dst in (("é", "e"), ("è", "e"), ("ê", "e"), ("à", "a"), ("ç", "c"), ("ô", "o")):
        text = text.replace(src, dst)
    return re.sub(r"[\s\-/]+", "_", text)


def _acct_lob(value: Any) -> str:
    """Map the caller's words for a service onto mobility / internet / tv / homephone ("" if unknown)."""
    key = _acct_key(value)
    if key in _ACCT_LOB_ALIASES:
        return _ACCT_LOB_ALIASES[key]
    spaced = " " + key.replace("_", " ") + " "
    for lob, pattern in _ACCT_LOB_KEYWORDS:
        if re.search(pattern, spaced):
            return lob
    return ""


def _acct_mfa_on(state: dict[str, Any]) -> bool:
    """MFA state: what a tool set this call, else the backend fixture."""
    live = str(state.get("mfa_state") or "").strip().lower()
    if live in ("enabled", "disabled"):
        return live == "enabled"
    return fixture_flag(state, "fx_mfa_enabled")


def send_password_reset_link_impl(
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Text a password reset link to the mobile number on file (identified callers; no login needed)."""
    state = get_state(state, session_state)
    lang = session_language(state, language)
    err = check_mock_error(state, lang, "send_password_reset_link")
    if err:
        return err
    account_id = str(state.get("account_id") or "")
    if not account_id or str(state.get("identification_status") or "") != "Pass":
        reference = tracking_id("send_password_reset_link", "not_identified")
        state["last_tracking_id"] = reference
        return error_reply(
            "NOT_IDENTIFIED",
            "The caller's account has not been found yet.",
            "Ask for the phone or account number, call lookup_account, then retry.",
            reference,
            language=lang,
        )
    count = read_count(state, "password_reset_count") + 1
    state["password_reset_count"] = count
    reference = tracking_id("send_password_reset_link", account_id, count)
    state["last_tracking_id"] = reference
    dest = str(state.get("phone_last4") or account_record(state)["phone"][-4:])
    if count >= 2 and fixture(state, "fx_sms_delivery") == "failed":
        return error_reply(
            "DELIVERY_FAILED",
            "The reset text could not be delivered to the mobile number on file.",
            "Apologize, then hand over with reason sms_delivery_failed.",
            reference,
            language=lang,
            data={"sent": False, "delivery_failed": True, "destination_last4": dest},
        )
    dispatch_sms(state, "password_reset")
    summary = _acct_text(
        lang,
        f"I've texted a password reset link to your mobile number ending in {dest}. "
        f"It's valid for {PASSWORD_RESET_VALID_MINUTES} minutes.",
        f"Je vous ai envoyé par texto un lien de réinitialisation au numéro de cellulaire se terminant par {dest}. "
        f"Il est valide pendant {PASSWORD_RESET_VALID_MINUTES} minutes.",
    )
    return ok_reply(
        {
            "sent": True,
            "channel": "sms",
            "destination_last4": dest,
            "valid_minutes": PASSWORD_RESET_VALID_MINUTES,
            "resend": count > 1,
            "send_count": count,
            "spoken_summary": summary,
        },
        reference,
        language=lang,
    )


def manage_mfa_impl(
    action: str = "",
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Turn two-step verification on or off; turning it off needs an email step-up code first."""
    state = get_state(state, session_state)
    lang = session_language(state, language)
    err = check_mock_error(state, lang, "manage_mfa")
    if err:
        return err
    gate = require_login(state, lang, "manage_mfa")
    if gate:
        return gate
    account_id = str(state.get("account_id") or "")
    key = _acct_key(action)
    act = "enable" if key in ("enable", "on", "turn_on", "activate", "activer") else (
        "disable" if key in ("disable", "off", "turn_off", "deactivate", "remove", "desactiver") else ""
    )
    reference = tracking_id("manage_mfa", account_id, act or key)
    state["last_tracking_id"] = reference
    if not act:
        return validation_error(
            state,
            "The action must be enable or disable.",
            "Ask whether the caller wants two-step verification turned on or off.",
            reference,
            lang,
        )
    currently_on = _acct_mfa_on(state)
    if currently_on == (act == "enable"):
        return error_reply(
            "ALREADY_APPLIED",
            "Two-step verification is already in the requested state.",
            "Tell the caller it is already " + ("on." if currently_on else "off."),
            reference,
            language=lang,
            data={"mfa_enabled": currently_on, "already_in_state": True},
        )
    if act == "disable" and not _acct_flag(state.get("step_up_verified")):
        # Step-up = a second factor beyond the login: the emailed code, or a text to
        # the mobile on file when the caller can't get email.
        state["step_up_pending"] = True
        return error_reply(
            "STEP_UP_REQUIRED",
            "Turning off two-step verification needs a second verification code first.",
            "Send a code by email (send_login_code channel email); if no email access, by text (channel sms).",
            reference,
            language=lang,
            data={"step_up_channel": "email", "step_up_fallback_channel": "sms", "mfa_enabled": currently_on},
        )
    now_on = act == "enable"
    state["mfa_state"] = "enabled" if now_on else "disabled"
    if not now_on:
        state["step_up_verified"] = False  # a step-up code authorizes one change only
    record = account_record(state)
    dest = str(state.get("phone_last4") or record["phone"][-4:])
    today = date_in(0, lang)
    summary = _acct_text(
        lang,
        f"Two-step verification is now on. Sign-in codes will go by text to your mobile number ending in {dest}."
        if now_on
        else "Two-step verification is now off. You'll sign in with your password only.",
        f"La vérification en deux étapes est maintenant activée. Les codes de connexion seront envoyés par texto au numéro se terminant par {dest}."
        if now_on
        else "La vérification en deux étapes est maintenant désactivée. Vous vous connecterez avec votre mot de passe seulement.",
    )
    return ok_reply(
        {
            "mfa_enabled": now_on,
            "method": ACCT_MFA_METHOD if now_on else "none",
            "destination_last4": dest if now_on else "",
            "effective_date": today["date"],
            "effective_display": _acct_text(lang, "effective immediately", "en vigueur immédiatement"),
            "confirmation_sms_sent": dispatch_sms(state, "mfa_" + act)["sms_sent"],
            "spoken_summary": summary,
            "lost_phone_note": _acct_text(
                lang,
                "If this phone is lost or stolen, call us and verify with your secret PIN instead of a text code; we can then suspend the line and update the mobile number that sign-in codes go to.",
                "Si ce téléphone est perdu ou volé, appelez-nous et vérifiez votre identité avec votre NIP secret plutôt qu'avec un code par texto; nous pourrons ensuite suspendre la ligne et mettre à jour le numéro de cellulaire qui reçoit les codes de connexion.",
            ) if now_on else "",
        },
        reference,
        language=lang,
    )


def execute_suspend_restore_impl(
    action: str = "",
    reason: str = "",
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Suspend a line (lost/stolen right away, or travel) or restore a lost/stolen or travel suspension."""
    state = get_state(state, session_state)
    lang = session_language(state, language)
    err = check_mock_error(state, lang, "execute_suspend_restore")
    if err:
        return err
    gate = require_login(state, lang, "execute_suspend_restore")
    if gate:
        return gate
    account_id = str(state.get("account_id") or "")
    act_key = _acct_key(action)
    act = "suspend" if act_key in ("suspend", "suspendre", "pause") else (
        "restore" if act_key in ("restore", "reactivate", "resume", "unsuspend", "retablir") else ""
    )
    why_key = _acct_key(reason)
    why = ""
    if any(w in why_key for w in ("lost", "stolen", "theft", "perdu", "vol")):
        why = "lost_stolen"
    elif any(w in why_key for w in ("travel", "trip", "vacation", "voyage", "vacances", "abroad")):
        why = "travel"
    reference = tracking_id("execute_suspend_restore", account_id, act or act_key, why)
    state["last_tracking_id"] = reference
    if not act:
        return validation_error(
            state,
            "The action must be suspend or restore.",
            "Ask whether the caller wants to suspend or restore the line.",
            reference,
            lang,
        )
    current = service_status(state)
    today = date_in(0, lang)
    if act == "restore":
        if current == "suspended_nonpayment":
            return error_reply(
                "NOT_ELIGIBLE",
                "A non-payment suspension is restored by clearing the balance.",
                "Explain billing restores it, then transfer silently to router for billing.",
                reference,
                language=lang,
                data={"service_status": current, "route_to": "billing"},
            )
        if not current.startswith("suspended"):
            return error_reply(
                "NOT_SUSPENDED",
                "The service is not suspended.",
                "Tell the caller the service is already active.",
                reference,
                language=lang,
                data={"service_status": current},
            )
        state["service_status"] = "active"
        summary = _acct_text(
            lang,
            "Your service is restored and working again as of today.",
            "Votre service est rétabli et fonctionne de nouveau dès aujourd'hui.",
        )
        return ok_reply(
            {
                "action": "restore",
                "previous_state": current,
                "new_state": "active",
                "effective_date": today["date"],
                "effective_display": today["date_display"],
                "sms_confirmation_sent": dispatch_sms(state, "service_restored")["sms_sent"],
                "spoken_summary": summary,
            },
            reference,
            language=lang,
        )
    if not why:
        return validation_error(
            state,
            "The suspension reason must be lost_stolen or travel.",
            "Ask if the phone was lost or stolen, or if the caller is travelling.",
            reference,
            lang,
        )
    if current.startswith("suspended"):
        return error_reply(
            "ALREADY_APPLIED",
            "The line is already suspended.",
            "Tell the caller the line is already suspended."
            if current != "suspended_nonpayment"
            else "Line is suspended for non-payment; offer billing via router.",
            reference,
            language=lang,
            data={"service_status": current, "already_suspended": True},
        )
    new_status = "suspended_" + why
    state["service_status"] = new_status
    if why == "lost_stolen":
        # The phone is gone: confirm by email, never by text to the lost device.
        sms_sent = False
        summary = _acct_text(
            lang,
            "Your line is suspended as of right now, so no one can make calls or use data on it. "
            "A confirmation is going to the email on file.",
            "Votre ligne est suspendue dès maintenant; personne ne peut faire d'appels ni utiliser de données avec celle-ci. "
            "Une confirmation est envoyée au courriel au dossier.",
        )
    else:
        sms_sent = dispatch_sms(state, "service_suspended")["sms_sent"]
        summary = _acct_text(
            lang,
            "Your line is suspended for your travel as of today. Call us when you're back and we'll restore it.",
            "Votre ligne est suspendue pour votre voyage dès aujourd'hui. Appelez-nous à votre retour et nous la rétablirons.",
        )
    return ok_reply(
        {
            "action": "suspend",
            "reason": why,
            "previous_state": current,
            "new_state": "suspended",
            "service_status": new_status,
            "immediate": why == "lost_stolen",
            "effective_date": today["date"],
            "effective_display": today["date_display"],
            "sms_confirmation_sent": sms_sent,
            "email_confirmation_sent": not sms_sent,
            "spoken_summary": summary,
        },
        reference,
        language=lang,
    )


def _acct_cancel_quote(lob: str, mode: str, lang: str) -> dict[str, Any]:
    """Fee, final bill estimate and effective date for cancelling or porting out one service."""
    terms = ACCT_CONTRACT_TERMS.get(lob, {"early_termination_fee": "0.00", "months_remaining": 0})
    fee = Decimal(str(terms["early_termination_fee"]))
    if mode == "port_out":
        days_to_effective = ACCT_PORT_OUT_COMPLETION_DAYS
    else:
        days_to_effective = max(ACCT_BILLING_CYCLE_DAYS - BILL_CYCLE_DAYS_AGO, 1)
    days_used = min(BILL_CYCLE_DAYS_AGO + days_to_effective, ACCT_BILLING_CYCLE_DAYS)
    price = Decimal(str(SERVICE_PRICES.get(lob, "0.00")))
    usage = (price * days_used / ACCT_BILLING_CYCLE_DAYS).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    final_bill = fee + usage
    effective = date_in(days_to_effective, lang)
    fee_money = money(fee, "early_termination_fee")
    bill_money = money(final_bill, "final_bill_estimate")
    return {
        "lob": lob,
        "mode": mode,
        "service_name": _ACCT_LOB_NAMES[lob][lang if lang in ("en-US", "fr-CA") else "en-US"],
        **fee_money,
        "contract_months_remaining": int(terms["months_remaining"]),
        **bill_money,
        "final_bill_includes_fee": fee > 0,
        "effective_date": effective["date"],
        "effective_date_display": effective["date_display"],
        # Turn N+1 facts (DESIGN_RULES rule 33): other services and what the final bill covers.
        "other_services_note": _acct_text(
            lang,
            "Your other services on the account stay active, and their plans and prices don't change.",
            "Vos autres services au compte restent actifs, et leurs forfaits et leurs prix ne changent pas.",
        ),
        "final_bill_note": _acct_text(
            lang,
            "The final bill covers this service up to the effective date, plus any early termination fee; nothing more is billed for it after that.",
            "La facture finale couvre ce service jusqu'à la date d'effet, plus les frais de résiliation anticipée s'il y a lieu; rien d'autre n'est facturé pour ce service par la suite.",
        ),
    }


def cancel_or_port_out_service_impl(
    lob: str = "",
    mode: str = "cancel",
    reason: str = "",
    confirmed: bool | str | int = False,
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Cancel a service or port its number out: confirmed=false quotes the terms, confirmed=true submits."""
    state = get_state(state, session_state)
    lang = session_language(state, language)
    err = check_mock_error(state, lang, "cancel_or_port_out_service")
    if err:
        return err
    gate = require_login(state, lang, "cancel_or_port_out_service")
    if gate:
        return gate
    account_id = str(state.get("account_id") or "")
    mode_key = _acct_key(mode)
    clean_mode = "port_out" if mode_key.startswith("port") else ("cancel" if mode_key in ("", "cancel", "cancellation", "annuler", "resilier") else "")
    clean_lob = _acct_lob(lob)
    reference = tracking_id("cancel_or_port_out_service", account_id, clean_lob or _acct_key(lob), clean_mode or mode_key)
    state["last_tracking_id"] = reference
    if not clean_mode:
        return validation_error(
            state,
            "The mode must be cancel or port_out.",
            "Ask if the caller wants to cancel the service or move the number to another provider.",
            reference,
            lang,
        )
    if not clean_lob:
        return validation_error(
            state,
            "The service must be mobility, internet, tv or homephone.",
            "Ask which service: mobile, internet, TV or home phone.",
            reference,
            lang,
        )
    record = account_record(state)
    on_account = list(record.get("lines_of_business", ACCT_LINES_OF_BUSINESS))
    if clean_lob not in on_account:
        return error_reply(
            "NOT_ELIGIBLE",
            "That service is not on this account.",
            "Tell the caller that service isn't on the account; ask which one they mean.",
            reference,
            language=lang,
            data={"lines_of_business": on_account},
        )
    if clean_mode == "port_out" and clean_lob not in ACCT_PORTABLE_LINES:
        return error_reply(
            "NOT_ELIGIBLE",
            "Only a phone number can be ported out.",
            "Explain only mobile or home phone numbers port out; offer to cancel instead.",
            reference,
            language=lang,
            data={"portable_lines": list(ACCT_PORTABLE_LINES)},
        )
    state["lob"] = clean_lob
    done_key = f"{clean_lob}:{clean_mode}"
    quote = _acct_cancel_quote(clean_lob, clean_mode, lang)
    cancellation_id = "CX" + reference[1:]
    remaining = [x for x in on_account if x != clean_lob]
    if done_key in str(state.get("cancelled_services") or "").split(","):
        return ok_reply(
            {**quote, "cancellation_id": cancellation_id, "already_submitted": True, "submitted": True,
             "transfer_authorization_sent_by_sms": clean_mode == "port_out",
             "remaining_lines_of_business": remaining},
            reference,
            language=lang,
        )
    pending_key = "quote:" + done_key
    if not _acct_flag(confirmed) or str(state.get("pending_confirmation") or "") != pending_key:
        # Two-step confirmation (PRD §14): the terms are always quoted before anything is submitted.
        state["pending_confirmation"] = pending_key
        return error_reply(
            "CONFIRMATION_REQUIRED",
            "The caller must hear the terms and confirm before the request is submitted.",
            "Say contract_cancellation_fee_disclosure, the fee, final bill and date; ask to confirm.",
            reference,
            language=lang,
            data={**quote, "disclosure_key": "contract_cancellation_fee_disclosure",
                  "remaining_lines_of_business": remaining},
        )
    state["pending_confirmation"] = ""
    append_list(state, "cancelled_services", done_key)
    sms = dispatch_sms(state, "port_out_authorization" if clean_mode == "port_out" else "cancellation_confirmation")
    data: dict[str, Any] = {
        **quote,
        "submitted": True,
        "already_submitted": False,
        "cancellation_id": cancellation_id,
        "reason_recorded": " ".join(str(reason or "").split())[:120],
        "confirmation_sms_sent": sms["sms_sent"],
        "destination_last4": sms["destination_last4"],
        "remaining_lines_of_business": remaining,
        "other_services_unchanged": True,
    }
    if clean_mode == "port_out":
        data["transfer_authorization_sent_by_sms"] = True
        data["spoken_summary"] = _acct_text(
            lang,
            f"Your port-out request is submitted. Your transfer authorization is on its way by text to the number ending in {sms['destination_last4']}; "
            f"give it to your new provider. The line closes once the transfer completes, by {quote['effective_date_display']}.",
            f"Votre demande de transfert est soumise. Votre autorisation de transfert vous est envoyée par texto au numéro se terminant par {sms['destination_last4']}; "
            f"donnez-la à votre nouveau fournisseur. La ligne sera fermée une fois le transfert terminé, d'ici le {quote['effective_date_display']}.",
        )
    else:
        data["transfer_authorization_sent_by_sms"] = False
        if clean_lob in ("internet", "tv"):
            data["equipment_return_days"] = ACCT_EQUIPMENT_RETURN_DAYS
            data["equipment_return_note"] = _acct_text(
                lang,
                f"Please return any rented equipment within {ACCT_EQUIPMENT_RETURN_DAYS} days.",
                f"Veuillez retourner l'équipement loué d'ici {ACCT_EQUIPMENT_RETURN_DAYS} jours.",
            )
        data["spoken_summary"] = _acct_text(
            lang,
            f"Your {quote['service_name']} cancellation is confirmed, effective {quote['effective_date_display']}.",
            f"L'annulation de votre {quote['service_name']} est confirmée, en vigueur le {quote['effective_date_display']}.",
        )
    return ok_reply(data, reference, language=lang)


def _acct_mask_email(email: str) -> str:
    user, _, domain = email.partition("@")
    return f"{user[:1]}***@{domain}"


def _acct_clean_address(value: str) -> str:
    return " ".join(str(value or "").replace("\n", ", ").split())


def update_contact_profile_impl(
    field: str = "",
    value: str | int | float = "",
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Change the email, mobile number or mailing address on file; returns only a masked new value."""
    state = get_state(state, session_state)
    lang = session_language(state, language)
    err = check_mock_error(state, lang, "update_contact_profile")
    if err:
        return err
    gate = require_login(state, lang, "update_contact_profile")
    if gate:
        return gate
    account_id = str(state.get("account_id") or "")
    clean_field = _ACCT_FIELD_ALIASES.get(_acct_key(field), "")
    raw = str(value if value is not None else "").strip()
    reference = tracking_id("update_contact_profile", account_id, clean_field or _acct_key(field), raw.lower())
    state["last_tracking_id"] = reference
    if not clean_field:
        return validation_error(
            state,
            "The field must be email, mobile_number or mailing_address.",
            "Ask whether to update the email, mobile number or mailing address.",
            reference,
            lang,
        )
    record = account_record(state)
    if clean_field == "email":
        new_value = raw.lower()
        if not _ACCT_EMAIL_RE.match(new_value):
            return validation_error(state, "That is not a valid email address.", "Ask the caller to spell the email address again.", reference, lang)
        masked = _acct_mask_email(new_value)
        spoken_tail = _acct_text(lang, "at ", "au domaine ") + new_value.partition("@")[2]
        current = str(record.get("email", "")).lower()
    elif clean_field == "mobile_number":
        digits = only_digits(re.sub(r"\.0+$", "", raw))
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]
        if not is_plausible_phone(digits):
            return validation_error(state, "A mobile number has 10 digits.", "Ask for the 10-digit mobile number again.", reference, lang)
        new_value = digits
        masked = "***-***-" + digits[-4:]
        spoken_tail = _acct_text(lang, "ending in ", "se terminant par ") + digits[-4:]
        current = str(record.get("phone", ""))
    else:
        new_value = _acct_clean_address(raw)
        if len(new_value) < 10 or not re.search(r"\d", new_value) or not re.search(r"[A-Za-zÀ-ÿ]{2,}", new_value):
            return validation_error(state, "The address needs a street number, street and city.", "Ask for the full mailing address with street number, city and postal code.", reference, lang)
        parts = [p.strip() for p in new_value.split(",") if p.strip()]
        tail = ", ".join(parts[-2:]) if len(parts) > 1 else new_value.split()[-1]
        masked = "***, " + tail
        spoken_tail = _acct_text(lang, "ending in ", "se terminant par ") + tail
        current = ""
    done = f"{clean_field}:{reference}"
    if new_value == current or done in str(state.get("contact_updates") or "").split(","):
        return error_reply(
            "ALREADY_APPLIED",
            "That is already the value on file.",
            "Tell the caller that detail is already up to date.",
            reference,
            language=lang,
            data={"field": clean_field, "new_value_masked": masked},
        )
    append_list(state, "contact_updates", done)
    notice = dispatch_sms(state, "contact_updated")
    names = {
        "email": _acct_text(lang, "email address", "adresse courriel"),
        "mobile_number": _acct_text(lang, "mobile number", "numéro de cellulaire"),
        "mailing_address": _acct_text(lang, "mailing address", "adresse postale"),
    }
    summary = _acct_text(
        lang,
        f"Your {names[clean_field]} is updated: the new one is {spoken_tail}.",
        f"Votre {names[clean_field]} est {'mis' if clean_field == 'mobile_number' else 'mise'} à jour, {spoken_tail}.",
    )
    return ok_reply(
        {
            "field": clean_field,
            "updated": True,
            "new_value_masked": masked,
            "effective_display": _acct_text(lang, "effective immediately", "en vigueur immédiatement"),
            "security_notice_sent": notice["sms_sent"],
            "spoken_summary": summary,
        },
        reference,
        language=lang,
    )

