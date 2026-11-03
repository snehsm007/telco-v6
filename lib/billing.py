"""Billing tools (docs/tdd.md §4 Billing): bill summary, payments, autopay,
adjustments (credits, refunds, disputes), payment arrangements, and restoring
service suspended for non-payment.

Live billing facts for the call (balance, past-due amount, service status,
autopay, arrangement) are kept in session state so every billing tool sees the
same numbers. Empty values mean "not touched yet on this call": the fake
backend (lib/fakes.py) supplies them. Restore after non-payment happens only
when the past-due amount is covered by a payment, a verified posted payment, or
an accepted payment arrangement (docs/requirements.md decision A9).
"""

from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
import re
from typing import Any

from lib.core import (
    account_record,
    append_list,
    check_mock_error,
    display_date,
    dispatch_sms,
    fixture,
    fixture_flag,
    get_state,
    mock_mode_on,
    money,
    require_login,
    service_status,
    session_language,
    to_decimal,
    validation_error,
)
from lib.fakes import (
    ARRANGEMENT_FIRST_DUE_DAYS,
    ARRANGEMENT_INSTALMENTS,
    ARRANGEMENT_SECOND_DUE_DAYS,
    AUTOPAY_DISCOUNT,
    AUTOPAY_DISCOUNT_NOTE,
    AUTOPAY_WITHDRAWAL_NOTE,
    BANK_ON_FILE_ENDING,
    BILL_DATE_CHANGE_NOTE,
    BILL_CYCLE_DAYS_AGO,
    BILL_DUE_IN_DAYS,
    BILL_EXTRA_LINE_FR,
    BILL_EXTRA_LINE_KEYWORDS,
    BILL_EXTRA_LINE_NOTES,
    BILL_EXTRA_LINES,
    CARD_BRANDS_BY_PREFIX,
    DECLINED_CARD_LAST4,
    DISPUTE_ETA_BUSINESS_DAYS,
    DUPLICATE_PAYMENT,
    EXTRA_FIXTURE_LINE_DAYS_AGO,
    LAST_PAYMENT,
    NEXT_BILL_CYCLE_DAYS,
    PAST_DUE_AMOUNT,
    RECENT_PAYMENT_DAYS_AGO,
    RECONNECT_MINUTES,
    RECONNECT_NOTE,
    REFUND_WINDOW_BUSINESS_DAYS,
    SELF_SERVE_ADJUSTMENT_LIMIT,
    SERVICE_KEYWORDS,
    SERVICE_LINE_LABELS,
    SERVICE_PRICES,
    normalize_code,
    read_count,
    relative_date,
    spoken_line,
)
from lib.replies import display_amount, error_reply, ok_reply, tracking_id

_BILL_ZERO = Decimal("0.00")
_BILL_CENT = Decimal("0.01")
_BILL_FULL_WORDS = ("full", "all", "balance", "total", "entire", "everything", "solde", "tout", "complet", "totalit")
_BILL_PAST_DUE_WORDS = ("past", "overdue", "late", "arrears", "retard", "souffrance", "arriéré", "arriere", "échu", "echu")
_BILL_BANK_WORDS = ("bank", "chequ", "check", "saving", "debit", "bancaire", "banque", "chèque", "cheque", "épargne", "prélèvement", "prelevement")
_BILL_NEW_WORDS = ("new", "other", "another", "different", "second", "nouvelle", "nouveau", "autre", "différente", "deuxième")
_BILL_FILE_WORDS = ("file", "saved", "stored", "dossier", "enregistr", "existing", "same", "même")
_BILL_CARD_WORDS = ("card", "carte", "visa", "mastercard", "amex", "credit", "crédit")
_BILL_DUPLICATE_WORDS = ("duplicate", "double", "twice", "two times", "paid two", "deux fois", "en double", "doublon", "trop-perçu", "trop perçu", "trop payé", "overpa")
_BILL_ADJUSTMENT_TYPES = ("unrecognized_charge", "incorrect_charge", "duplicate_payment", "outage_credit")
_BILL_SUSPENSION_REASONS = {
    "suspended_nonpayment": "non_payment",
    "suspended_lost_stolen": "lost_stolen",
    "suspended_travel": "travel",
}


# ---------------------------------------------------------------------------
# Shared billing helpers
# ---------------------------------------------------------------------------


def _bill_text(lang: str, en: str, fr: str) -> str:
    """One localized string in the call language (DESIGN_RULES rule 5: no sibling keys)."""
    return fr if lang == "fr-CA" else en


def _bill_amount_text(lang: str, amount: Decimal) -> str:
    """Money as spoken in the call language: '$12.50' / '12.50 $'."""
    shown = display_amount(amount)
    return f"{shown} $" if lang == "fr-CA" else f"${shown}"


def _bill_q(value: Decimal) -> Decimal:
    return value.quantize(_BILL_CENT, rounding=ROUND_HALF_UP)


def _bill_to_amount(value: Any) -> Decimal | None:
    """A caller amount with words around it ("85.50 dollars", "85,50 $") as Decimal; None when there is no number."""
    if isinstance(value, bool):
        return None
    direct = to_decimal(value)
    if direct is not None:
        return direct
    match = re.search(r"\d[\d\s,]*(?:\.\d+)?", str(value or ""))
    return to_decimal(match.group(0)) if match else None


def _bill_date(days: int, lang: str) -> dict[str, str]:
    iso = relative_date(days)
    return {"iso": iso, "display": display_date(iso, lang)}


def _bill_start(
    state: dict[str, Any] | None,
    session_state: dict[str, Any] | None,
    language: str,
    tool: str,
) -> tuple[dict[str, Any], str, dict[str, Any] | None]:
    """Common opening of every billing tool: state, language, fault injection, business guard, login."""
    st = get_state(state, session_state)
    lang = session_language(st, language)
    err = check_mock_error(st, lang, tool)
    if err:
        return st, lang, err
    if st.get("business_flag") is True or str(st.get("business_flag")).strip().lower() == "true":
        return st, lang, error_reply(
            "PERMISSION_DENIED",
            "Business accounts are served by the business team.",
            "Business account: hand over with reason business_handoff.",
            tracking_id(tool, "business", st.get("account_id", "")),
            language=lang,
        )
    login_err = require_login(st, lang, tool)
    if login_err:
        return st, lang, login_err
    return st, lang, None


def _bill_finish(state: dict[str, Any], reply: dict[str, Any]) -> dict[str, Any]:
    """Remember the reference and mark synthetic replies in mock mode (prd.md §17)."""
    state["last_tracking_id"] = reply.get("tracking_id", "")
    if mock_mode_on(state):
        reply["data"]["mock_mode"] = True
    return reply


def _bill_match(text: str, keyword: str) -> bool:
    """Whole-word-start match, so 'tv' doesn't hit inside another word but 'mobil' matches 'mobilité'."""
    return re.search(rf"(?<![\w]){re.escape(keyword)}", text) is not None


def _bill_lines(state: dict[str, Any], lang: str) -> list[dict[str, Any]]:
    """Line items on the latest bill: monthly services, extra charges, and the fx_extra_bill_line fixture."""
    record = account_record(state)
    lobs = [lob for lob in record.get("lines_of_business", []) if lob in SERVICE_PRICES]
    cycle = _bill_date(-BILL_CYCLE_DAYS_AGO, lang)
    lines: list[dict[str, Any]] = []
    for lob in lobs:
        en, fr = SERVICE_LINE_LABELS[lob]
        lines.append(
            {
                "charge_id": f"CH-SVC-{lob.upper()}",
                "description": _bill_text(lang, en, fr),
                "lob": lob,
                "kind": "service",
                "date": cycle["iso"],
                "date_display": cycle["display"],
                "keywords": SERVICE_KEYWORDS.get(lob, ()),
                **money(SERVICE_PRICES[lob]),
            }
        )
    for extra in BILL_EXTRA_LINES:
        if extra["lob"] not in lobs:
            continue
        when = _bill_date(-int(extra["days_ago"]), lang)
        lines.append(
            {
                "charge_id": extra["charge_id"],
                "description": _bill_text(lang, extra["description"], BILL_EXTRA_LINE_FR.get(extra["charge_id"], extra["description"])),
                "lob": extra["lob"],
                "kind": "extra",
                "date": when["iso"],
                "date_display": when["display"],
                "keywords": BILL_EXTRA_LINE_KEYWORDS.get(extra["charge_id"], ()),
                **money(extra["amount"]),
                **{key: _bill_text(lang, *pair) for key, pair in BILL_EXTRA_LINE_NOTES.get(extra["charge_id"], {}).items()},
            }
        )
    raw = fixture(state, "fx_extra_bill_line")
    parts = [p.strip() for p in raw.split("|")] if raw else []
    if len(parts) >= 2 and parts[0] and to_decimal(parts[1]) is not None and to_decimal(parts[1]) > _BILL_ZERO:
        lob = parts[2].lower() if len(parts) > 2 and parts[2] else ""
        when = _bill_date(-EXTRA_FIXTURE_LINE_DAYS_AGO, lang)
        words = tuple(w for w in re.findall(r"[\w'-]+", parts[0].lower()) if len(w) > 3)
        lines.append(
            {
                "charge_id": "CH-EXT-01",
                "description": parts[0],
                "lob": lob,
                "kind": "extra",
                "date": when["iso"],
                "date_display": when["display"],
                "keywords": words + SERVICE_KEYWORDS.get(lob, ()),
                **money(parts[1]),
            }
        )
    return lines


def _bill_public_line(line: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in line.items() if k not in ("keywords", "kind")}


def _bill_charges_total(lines: list[dict[str, Any]]) -> Decimal:
    return sum((Decimal(str(line["amount"])) for line in lines), _BILL_ZERO)


def _bill_live(state: dict[str, Any], lang: str) -> dict[str, Decimal]:
    """Balance and past-due amount for this call: session values once a tool changed them, else the backend."""
    past_due = to_decimal(state.get("past_due_amount"))
    if past_due is None:
        past_due = to_decimal(PAST_DUE_AMOUNT) or _BILL_ZERO
    balance = to_decimal(state.get("balance_due"))
    if balance is None:
        balance = past_due + _bill_charges_total(_bill_lines(state, lang))
    return {"balance": _bill_q(max(balance, _BILL_ZERO)), "past_due": _bill_q(max(min(past_due, balance), _BILL_ZERO))}


def _bill_save(state: dict[str, Any], balance: Decimal, past_due: Decimal) -> None:
    state["balance_due"] = display_amount(max(balance, _BILL_ZERO))
    state["past_due_amount"] = display_amount(max(min(past_due, balance), _BILL_ZERO))


def _bill_flag(state: dict[str, Any], key: str) -> bool:
    value = state.get(key)
    return value is True or str(value).strip().lower() == "true"


def _bill_reconnect_note(lang: str) -> str:
    """How soon a restored service comes back and what to do if it doesn't (DESIGN_RULES rule 33)."""
    return _bill_text(lang, *RECONNECT_NOTE).replace("[minutes]", str(RECONNECT_MINUTES))


def _bill_restore(state: dict[str, Any], lang: str) -> dict[str, Any]:
    """Lift a non-payment suspension and text the confirmation."""
    state["service_status"] = "active"
    sms = dispatch_sms(state, "service_restored")
    return {
        "service_restored": True,
        "new_service_status": "active",
        "restore_sms_sent": True,
        "sms_destination_last4": sms["destination_last4"],
        "reconnect_note": _bill_reconnect_note(lang),
    }


def _bill_card_on_file(state: dict[str, Any]) -> dict[str, str]:
    """The usable card on file this call: {last4, brand, status} (status valid/declined/expired/none)."""
    record = account_record(state)
    original = str(record.get("card_last4") or "")
    live = str(state.get("card_last4") or "").strip()
    if live:
        status = fixture(state, "fx_card_on_file_status") if live == original else "valid"
        if live in DECLINED_CARD_LAST4:
            status = "declined"
        brand = str(record.get("card_brand") or "") if live == original else str(state.get("card_brand") or "")
        return {"last4": live, "brand": brand, "status": status or "valid"}
    if _bill_flag(state, "payment_declined_once") and str(state.get("declined_card_last4") or "") == original:
        return {"last4": "", "brand": "", "status": "none"}
    return {"last4": original, "brand": str(record.get("card_brand") or ""), "status": fixture(state, "fx_card_on_file_status") or "valid"}


def _bill_autopay_facts(lang: str) -> dict[str, str]:
    """Turn N+1 autopay facts (DESIGN_RULES rule 33): withdrawal day, bill date change, discount."""
    days = BILL_CYCLE_DAYS_AGO + BILL_DUE_IN_DAYS
    return {
        "autopay_withdrawal_note": _bill_text(lang, *AUTOPAY_WITHDRAWAL_NOTE).replace("[days]", str(days)),
        "bill_date_change_note": _bill_text(lang, *BILL_DATE_CHANGE_NOTE),
        "autopay_discount_display": display_amount(AUTOPAY_DISCOUNT),
        "autopay_discount_note": _bill_text(lang, *AUTOPAY_DISCOUNT_NOTE),
    }


def _bill_brand(digits: str) -> str:
    return CARD_BRANDS_BY_PREFIX.get(digits[:1], "Card")


def _bill_method(payment_method: Any, digits: str, state: dict[str, Any]) -> str:
    """Normalize the payment method to card_on_file / new_card / bank_account ('' when unknown)."""
    text = str(payment_method or "").strip().lower().replace("-", "_")
    if text in ("card_on_file", "new_card", "bank_account"):
        method = text
    elif any(w in text for w in _BILL_BANK_WORDS) and not any(w in text for w in ("card", "carte")):
        method = "bank_account"
    elif any(w in text for w in _BILL_NEW_WORDS):
        method = "new_card"
    elif not text or any(w in text for w in _BILL_FILE_WORDS) or any(w in text for w in _BILL_CARD_WORDS):
        method = "new_card" if len(digits) >= 13 else "card_on_file"
    else:
        return ""
    if method == "card_on_file" and len(digits) >= 13:
        method = "new_card"
    if len(digits) == 4 and method in ("card_on_file", "new_card"):
        card_last4 = _bill_card_on_file(state)["last4"]
        if digits == BANK_ON_FILE_ENDING and digits != card_last4:
            # The caller named the bank account on file by its ending (get_billing_summary bank_on_file_last4).
            return "bank_account"
        method = "card_on_file" if digits == card_last4 else "new_card"
    return method


def _bill_digits(card_number: Any, dtmf_digits: Any, state: dict[str, Any]) -> str:
    """Card or bank digits from the argument, the keypad argument, or keypad entry in session state."""
    for source in (card_number, dtmf_digits):
        digits = normalize_code(source)
        if digits:
            return digits
    keyed = normalize_code(state.get("dtmf_digits"))
    return keyed if 13 <= len(keyed) <= 19 else ""


def _bill_decline(state: dict[str, Any], last4: str, code: str, lang: str, reference: str, tool: str) -> dict[str, Any]:
    """DESIGN_RULES rule 24: a decline clears card_last4 and keeps declined_card_last4."""
    failures = read_count(state, "payment_failure_count") + 1
    state["payment_failure_count"] = failures
    state["card_last4"] = ""
    state["declined_card_last4"] = last4
    state["payment_declined_once"] = True
    message = "The card was declined." if code == "CARD_DECLINED" else "The card has expired."
    return _bill_finish(
        state,
        error_reply(
            code,
            message,
            "Say the card was declined and ask for another card or a bank account.",
            reference,
            language=lang,
            data={
                "declined_card_last4": last4,
                "card_last4": "",
                "payment_failure_count": failures,
                "other_methods": ["new_card", "bank_account"],
            },
        ),
    )


def _bill_resolve_method(
    state: dict[str, Any],
    lang: str,
    tool: str,
    payment_method: Any,
    card_number: Any,
    dtmf_digits: Any,
    reference: str,
) -> tuple[dict[str, str] | None, dict[str, Any] | None]:
    """Resolve and check the payment method. Returns ({method, last4, brand}, None) or (None, error reply)."""
    digits = _bill_digits(card_number, dtmf_digits, state)
    method = _bill_method(payment_method, digits, state)
    if not method:
        return None, validation_error(
            state,
            "Unknown payment method.",
            "Ask: card on file, a new card, or a bank account?",
            reference,
            lang,
        )
    if method == "card_on_file":
        card = _bill_card_on_file(state)
        if card["status"] == "none":
            return None, _bill_finish(
                state,
                error_reply(
                    "CARD_DECLINED",
                    "The card on file was declined earlier on this call.",
                    "Ask for another card or a bank account.",
                    reference,
                    language=lang,
                    data={"declined_card_last4": state.get("declined_card_last4", ""), "other_methods": ["new_card", "bank_account"]},
                ),
            )
        if card["status"] in ("declined", "expired"):
            return None, _bill_decline(state, card["last4"], "CARD_DECLINED" if card["status"] == "declined" else "CARD_EXPIRED", lang, reference, tool)
        return {"method": method, "last4": card["last4"], "brand": card["brand"]}, None
    if method == "new_card":
        if not digits:
            # No card named yet. Incomplete, not malformed: not counted towards too_many_errors.
            return None, _bill_finish(
                state,
                error_reply(
                    "INVALID_INPUT",
                    "No card was given.",
                    "Ask which card to use by its last four digits, or to key the card number on the keypad.",
                    reference,
                    language=lang,
                    data={"needs_card": True},
                ),
            )
        if len(digits) == 4:
            # A card the caller names by its ending is one they already hold on file or keyed
            # upstream (prd.md §10: card digits are tokenized upstream, never spoken in full).
            if digits in DECLINED_CARD_LAST4 or digits == str(state.get("declined_card_last4") or ""):
                return None, _bill_decline(state, digits, "CARD_DECLINED", lang, reference, tool)
            return {"method": method, "last4": digits, "brand": ""}, None
        if not 13 <= len(digits) <= 19:
            return None, validation_error(
                state,
                "A card number has 13 to 19 digits.",
                "Ask the caller to enter the full card number.",
                reference,
                lang,
                data={"needs_full_card_number": True},
            )
        last4 = digits[-4:]
        if last4 in DECLINED_CARD_LAST4:
            return None, _bill_decline(state, last4, "CARD_DECLINED", lang, reference, tool)
        return {"method": method, "last4": last4, "brand": _bill_brand(digits)}, None
    if len(digits) == 4:
        # A bank account named by its ending: the one on file (bank_on_file_last4), or one the caller
        # holds and keyed upstream (tokenized, like a card ending; prd.md §10 never full numbers aloud).
        return {"method": method, "last4": digits, "brand": ""}, None
    if digits and not 5 <= len(digits) <= 17:
        return None, validation_error(
            state,
            "A bank account is named by its last 4 digits or keyed in full (5 to 17 digits).",
            "Ask the caller for the bank account's last four digits again; never switch payment method without asking.",
            reference,
            lang,
            data={"payment_method": method, "bank_on_file_last4": BANK_ON_FILE_ENDING},
        )
    return {"method": method, "last4": digits[-4:] if digits else BANK_ON_FILE_ENDING, "brand": ""}, None


_BILL_REFERENCE_NAMES: dict[str, tuple[str, str]] = {
    "payment": ("payment", "de paiement"),
    "autopay": ("autopay", "de paiement préautorisé"),
    "arrangement": ("arrangement", "d'entente"),
}


def _bill_reference_text(lang: str, kind: str, reference: str) -> str:
    """Trailing sentence with the record's reference number, so the summary carries what the agent reads."""
    en, fr = _BILL_REFERENCE_NAMES[kind]
    return _bill_text(lang, f" Your {en} reference number is {reference}.", f" Votre numéro de référence {fr} est le {reference}.")


def _bill_method_text(lang: str, method: dict[str, str]) -> str:
    if method["method"] == "bank_account":
        return _bill_text(lang, f"bank account ending in {method['last4']}", f"compte bancaire se terminant par {method['last4']}")
    return _bill_text(lang, f"card ending in {method['last4']}", f"carte se terminant par {method['last4']}")


# ---------------------------------------------------------------------------
# get_billing_summary
# ---------------------------------------------------------------------------


def _bill_arrangement_offer(balance: Decimal, lang: str, first: Decimal | None = None) -> dict[str, Any]:
    """Two-instalment schedule for the balance (decision A9)."""
    first_amt = _bill_q(first if first is not None else balance / ARRANGEMENT_INSTALMENTS)
    second_amt = _bill_q(balance - first_amt)
    first_due = _bill_date(ARRANGEMENT_FIRST_DUE_DAYS, lang)
    second_due = _bill_date(ARRANGEMENT_FIRST_DUE_DAYS + ARRANGEMENT_SECOND_DUE_DAYS, lang)
    return {
        "instalments": [
            {"number": 1, **money(first_amt), "due_date": first_due["iso"], "due_date_display": first_due["display"]},
            {"number": 2, **money(second_amt), "due_date": second_due["iso"], "due_date_display": second_due["display"]},
        ],
        "instalment_count": ARRANGEMENT_INSTALMENTS,
        **money(balance, "total"),
    }


def _bill_payments(state: dict[str, Any], lang: str, past_due: Decimal) -> list[dict[str, Any]]:
    """Recent payments in the ledger, newest first."""
    payments: list[dict[str, Any]] = []
    paid_now = to_decimal(state.get("last_pmt_amt"))
    if paid_now is not None and paid_now > _BILL_ZERO:
        today = _bill_date(0, lang)
        payments.append({"date": today["iso"], "date_display": today["display"], "status": "posted", "method": str(state.get("last_payment_method") or ""), **money(paid_now)})
    # A posted payment not applied yet is in the payment processor's queue, not the
    # ledger: it shows only once verify_payment_and_restore found and applied it.
    if fixture(state, "fx_recent_payment") == "posted_yesterday" and _bill_flag(state, "recent_payment_applied"):
        when = _bill_date(-RECENT_PAYMENT_DAYS_AGO, lang)
        payments.append({"date": when["iso"], "date_display": when["display"], "status": "posted", "method": "online_banking", **money(PAST_DUE_AMOUNT)})
    if fixture_flag(state, "fx_duplicate_payment"):
        when = _bill_date(-int(DUPLICATE_PAYMENT["days_ago"]), lang)
        refunded = "duplicate_payment" in str(state.get("applied_adjustments") or "").split(",")
        for dup in (False, True):
            payments.append(
                {
                    "date": when["iso"],
                    "date_display": when["display"],
                    "status": "refunded" if (dup and refunded) else "posted",
                    "method": DUPLICATE_PAYMENT["method"],
                    "duplicate": dup,
                    **money(DUPLICATE_PAYMENT["amount"]),
                }
            )
    when = _bill_date(-int(LAST_PAYMENT["days_ago"]), lang)
    payments.append({"date": when["iso"], "date_display": when["display"], "status": "posted", "method": LAST_PAYMENT["method"], **money(LAST_PAYMENT["amount"])})
    return payments


def get_billing_summary_impl(
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Balance, past-due amount, due date, service status, latest bill line items and recent payments."""
    st, lang, err = _bill_start(state, session_state, language, "get_billing_summary")
    if err:
        return err
    live = _bill_live(st, lang)
    status = service_status(st)
    lines = _bill_lines(st, lang)
    card = _bill_card_on_file(st)
    due = _bill_date(BILL_DUE_IN_DAYS, lang)
    autopay = _bill_flag(st, "autopay_enrolled")
    arrangement = _bill_flag(st, "arrangement_active")
    reference = tracking_id("get_billing_summary", st.get("account_id", ""), live["balance"], status)
    data: dict[str, Any] = {
        **money(live["balance"], "balance_due"),
        **money(live["past_due"], "past_due_amount"),
        "due_date": due["iso"],
        "due_date_display": due["display"],
        "service_status": status,
        "suspension_reason": _BILL_SUSPENSION_REASONS.get(status, ""),
        "card_on_file_last4": card["last4"],
        "card_on_file_brand": card["brand"],
        "bank_on_file_last4": BANK_ON_FILE_ENDING,
        "autopay_enrolled": autopay,
        "payment_arrangement_active": arrangement,
        **_bill_autopay_facts(lang),
        "recent_bills": [
            {
                "bill_date": lines[0]["date"] if lines else relative_date(-BILL_CYCLE_DAYS_AGO),
                "bill_date_display": lines[0]["date_display"] if lines else "",
                **money(_bill_charges_total(lines), "new_charges"),
                "line_items": [_bill_public_line(line) for line in lines],
            }
        ],
        "recent_payments": _bill_payments(st, lang, live["past_due"]),
        "self_serve_adjustment_limit_display": display_amount(SELF_SERVE_ADJUSTMENT_LIMIT),
    }
    if status == "suspended_nonpayment":
        data["amount_to_restore_display"] = display_amount(live["past_due"])
        data["restore_options"] = ["pay_past_due", "verify_recent_payment", "payment_arrangement"]
        data["reconnect_note"] = _bill_reconnect_note(lang)
    elif status in ("suspended_lost_stolen", "suspended_travel"):
        data["restore_handled_by"] = "account"
    if live["balance"] > _BILL_ZERO and not arrangement:
        data["arrangement_offer"] = _bill_arrangement_offer(live["balance"], lang)
    summary = _bill_text(
        lang,
        f"Your balance is {_bill_amount_text(lang, live['balance'])}, due {due['display']}.",
        f"Votre solde est de {_bill_amount_text(lang, live['balance'])}, payable le {due['display']}.",
    )
    if live["past_due"] > _BILL_ZERO:
        summary += _bill_text(
            lang,
            f" Of that, {_bill_amount_text(lang, live['past_due'])} is past due.",
            f" De ce montant, {_bill_amount_text(lang, live['past_due'])} est en souffrance.",
        )
    data["spoken_summary"] = summary
    reply = ok_reply(data, reference, language=lang)
    if status == "suspended_nonpayment":
        # The suspension is in the data; it is raised only with a caller who asks about it.
        reply["agent_action"] = "Mention the non-payment suspension only if the caller asks about restoring service."
    return _bill_finish(st, reply)


# ---------------------------------------------------------------------------
# process_bill_payment
# ---------------------------------------------------------------------------


def _bill_payment_amount(amount: Any, live: dict[str, Decimal]) -> Decimal | None:
    text = str(amount if amount is not None else "").strip().lower()
    if isinstance(amount, bool):
        return None
    if not text or any(w in text for w in _BILL_FULL_WORDS) and not any(w in text for w in _BILL_PAST_DUE_WORDS):
        return live["balance"]
    if any(w in text for w in _BILL_PAST_DUE_WORDS):
        return live["past_due"]
    return _bill_to_amount(amount)


def process_bill_payment_impl(
    amount: Any = "",
    payment_method: str = "card_on_file",
    card_number: Any = "",
    dtmf_digits: Any = "",
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Pay all or part of the balance; restores a non-payment suspension once the past-due amount is covered."""
    st, lang, err = _bill_start(state, session_state, language, "process_bill_payment")
    if err:
        return err
    account_id = st.get("account_id", "")
    live = _bill_live(st, lang)
    reference = tracking_id("process_bill_payment", account_id, amount, payment_method, live["balance"])
    if live["balance"] <= _BILL_ZERO:
        return _bill_finish(
            st,
            error_reply(
                "NOT_ELIGIBLE",
                "There is no balance to pay.",
                "Say the balance is already paid in full.",
                reference,
                language=lang,
                data={**money(live["balance"], "balance_due"), "service_status": service_status(st)},
            ),
        )
    pay = _bill_payment_amount(amount, live)
    if pay is None or pay <= _BILL_ZERO or pay > live["balance"]:
        return validation_error(
            st,
            "The amount must be more than zero and no more than the balance.",
            "Read back the balance and ask how much to pay.",
            reference,
            lang,
            data=money(live["balance"], "balance_due"),
        )
    method, method_err = _bill_resolve_method(st, lang, "process_bill_payment", payment_method, card_number, dtmf_digits, reference)
    if method_err:
        return method_err
    assert method is not None
    status_before = service_status(st)
    new_balance = _bill_q(live["balance"] - pay)
    new_past_due = _bill_q(max(live["past_due"] - pay, _BILL_ZERO))
    _bill_save(st, new_balance, new_past_due)
    payment_count = read_count(st, "bill_payment_count") + 1
    st["bill_payment_count"] = payment_count
    st["last_payment_method"] = method["method"]
    st["last_pmt_amt"] = display_amount(pay)
    st["payment_failure_count"] = 0
    if method["method"] != "bank_account":
        st["card_last4"] = method["last4"]
        st["card_brand"] = method["brand"]
    payment_id = tracking_id("PAY", account_id, pay, method["method"], method["last4"], payment_count)
    receipt = dispatch_sms(st, "payment_receipt")
    due = _bill_date(BILL_DUE_IN_DAYS if new_balance > _BILL_ZERO else BILL_DUE_IN_DAYS + NEXT_BILL_CYCLE_DAYS, lang)
    data: dict[str, Any] = {
        "payment_id": payment_id,
        **money(pay, "amount_paid"),
        "payment_method": method["method"],
        "card_last4": method["last4"] if method["method"] != "bank_account" else "",
        "card_brand": method["brand"],
        "bank_last4": method["last4"] if method["method"] == "bank_account" else "",
        **money(new_balance, "remaining_balance"),
        **money(new_past_due, "remaining_past_due"),
        "paid_in_full": new_balance == _BILL_ZERO,
        "next_due_date": due["iso"],
        "next_due_date_display": due["display"],
        "receipt_sms_sent": receipt["sms_sent"],
        "sms_destination_last4": receipt["destination_last4"],
        "autopay_enrolled": _bill_flag(st, "autopay_enrolled"),
        "service_restored": False,
        "service_status": status_before,
    }
    summary = _bill_text(
        lang,
        f"Your payment of {_bill_amount_text(lang, pay)} with the {_bill_method_text(lang, method)} went through. "
        f"Your remaining balance is {_bill_amount_text(lang, new_balance)}.",
        f"Votre paiement de {_bill_amount_text(lang, pay)} avec la {_bill_method_text(lang, method)} est accepté. "
        f"Votre solde restant est de {_bill_amount_text(lang, new_balance)}.",
    ).replace("avec la compte", "avec le compte")
    # Wording fits both a caller restoring a suspended line and one paying to avoid a
    # cut-off (the default account is suspended; docs/tdd.md §5): no unprompted
    # "suspended", and "fully active" confirms a restore.
    if status_before == "suspended_nonpayment" and new_past_due == _BILL_ZERO:
        data.update(_bill_restore(st, lang))
        data["service_status"] = "active"
        data["suspension_risk_cleared"] = True
        summary += _bill_text(
            lang,
            " Your account is no longer past due, and your service is fully active.",
            " Votre compte n'est plus en souffrance et votre service est entièrement actif.",
        )
    elif status_before == "suspended_nonpayment":
        data["restore_requires_display"] = display_amount(new_past_due)
        summary += _bill_text(
            lang,
            f" The remaining past-due amount of {_bill_amount_text(lang, new_past_due)} still needs to be paid to make your service fully active.",
            f" Le montant en souffrance restant de {_bill_amount_text(lang, new_past_due)} doit encore être payé pour que votre service soit entièrement actif.",
        )
    elif live["past_due"] > _BILL_ZERO and new_past_due == _BILL_ZERO:
        data["suspension_risk_cleared"] = True
        summary += _bill_text(lang, " Your account is no longer past due.", " Votre compte n'est plus en souffrance.")
    if receipt["sms_sent"]:
        summary += _bill_text(lang, " A receipt is on its way by text.", " Un reçu vous est envoyé par texto.")
    summary += _bill_reference_text(lang, "payment", payment_id)
    data["spoken_summary"] = summary
    return _bill_finish(st, ok_reply(data, payment_id, language=lang))


# ---------------------------------------------------------------------------
# setup_autopay
# ---------------------------------------------------------------------------


def setup_autopay_impl(
    payment_method: str = "card_on_file",
    card_number: Any = "",
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Enrol the account in automatic monthly payments of the statement balance."""
    st, lang, err = _bill_start(state, session_state, language, "setup_autopay")
    if err:
        return err
    account_id = st.get("account_id", "")
    reference = tracking_id("setup_autopay", account_id, payment_method, normalize_code(card_number)[-4:])
    if _bill_flag(st, "autopay_enrolled"):
        return _bill_finish(
            st,
            error_reply(
                "ALREADY_ENROLLED",
                "Autopay is already on for this account.",
                "Say autopay is already set up.",
                reference,
                language=lang,
                data={"autopay_enrolled": True, "method": st.get("autopay_method", "")},
            ),
        )
    method, method_err = _bill_resolve_method(st, lang, "setup_autopay", payment_method, card_number, "", reference)
    if method_err:
        return method_err
    assert method is not None
    live = _bill_live(st, lang)
    # The current bill is charged on its due date; once it's paid, autopay starts with the next bill.
    first = _bill_date(BILL_DUE_IN_DAYS if live["balance"] > _BILL_ZERO else BILL_DUE_IN_DAYS + NEXT_BILL_CYCLE_DAYS, lang)
    st["autopay_enrolled"] = True
    st["autopay_method"] = method["method"]
    if method["method"] != "bank_account":
        st["card_last4"] = method["last4"]
        st["card_brand"] = method["brand"]
    sms = dispatch_sms(st, "autopay_confirmation")
    autopay_id = tracking_id("AUTOPAY", account_id, method["method"], method["last4"])
    data = {
        "autopay_enrolled": True,
        "autopay_id": autopay_id,
        "method": method["method"],
        "card_last4": method["last4"] if method["method"] != "bank_account" else "",
        "card_brand": method["brand"],
        "bank_last4": method["last4"] if method["method"] == "bank_account" else "",
        "first_charge_date": first["iso"],
        "first_charge_date_display": first["display"],
        "charges": "full_statement_balance_on_due_date",
        **_bill_autopay_facts(lang),
        "current_balance_included": live["balance"] > _BILL_ZERO,
        **money(live["balance"], "balance_due"),
        "confirmation_sms_sent": sms["sms_sent"],
        "sms_destination_last4": sms["destination_last4"],
        "spoken_summary": _bill_text(
            lang,
            f"Autopay is set up with the {_bill_method_text(lang, method)}. The first automatic payment is on {first['display']}."
            + (" A confirmation is on its way by text." if sms["sms_sent"] else ""),
            f"Les paiements préautorisés sont configurés avec la {_bill_method_text(lang, method)}. Le premier paiement automatique aura lieu le {first['display']}."
            + (" Une confirmation vous est envoyée par texto." if sms["sms_sent"] else ""),
        ).replace("avec la compte", "avec le compte") + _bill_reference_text(lang, "autopay", autopay_id),
    }
    return _bill_finish(st, ok_reply(data, autopay_id, language=lang))


# ---------------------------------------------------------------------------
# apply_bill_adjustment
# ---------------------------------------------------------------------------


def _bill_adjustment_type(adjustment_type: Any, description: str, outage_days: Any) -> str:
    text = str(adjustment_type or "").strip().lower().replace(" ", "_").replace("-", "_")
    if text in _BILL_ADJUSTMENT_TYPES:
        return text
    if "outage" in text or "panne" in text:
        return "outage_credit"
    if "duplic" in text or "double" in text or "twice" in text:
        return "duplicate_payment"
    if "incorrect" in text or "overcharge" in text or "wrong" in text or "error" in text:
        return "incorrect_charge"
    if text:
        return "unrecognized_charge"
    if normalize_code(outage_days):
        return "outage_credit"
    if any(w in description for w in _BILL_DUPLICATE_WORDS):
        return "duplicate_payment"
    return "unrecognized_charge"


def _bill_same_amount(line_amount: Decimal, asked: Decimal) -> bool:
    """The caller's amount names this charge: exact, or the whole-dollar figure people say aloud."""
    return asked in (line_amount, line_amount.to_integral_value(rounding=ROUND_DOWN), line_amount.to_integral_value(rounding=ROUND_HALF_UP))


def _bill_find_line(lines: list[dict[str, Any]], charge_id: str, amount: Decimal | None, description: str) -> dict[str, Any] | None:
    """The latest-bill line the caller means: by charge id, else by amount (words break ties), else by words alone.

    A stated amount that matches no line never falls back to words, so a partial
    "overcharge" on a monthly service opens a dispute instead of an automatic credit.
    """
    if charge_id:
        for line in lines:
            if line["charge_id"].lower() == charge_id.lower():
                return line

    def _score(line: dict[str, Any]) -> int:
        hits = sum(1 for kw in line.get("keywords", ()) if _bill_match(description, kw))
        return hits * 2 + (1 if line["kind"] == "extra" and hits else 0)

    if amount is not None:
        same = [line for line in lines if _bill_same_amount(Decimal(str(line["amount"])), amount)]
        return max(same, key=_score) if same else None
    if not description:
        return None
    scored = [(line, _score(line)) for line in lines]
    scored = [pair for pair in scored if pair[1] > 0]
    if not scored:
        return None
    best = max(pair[1] for pair in scored)
    top = [line for line, score in scored if score == best]
    return top[0] if len(top) == 1 else None


def _bill_named_service_line(lines: list[dict[str, Any]], description: str) -> dict[str, Any] | None:
    """The one monthly service line the caller's words name (e.g. "my internet bill"), else None."""
    named = [
        line for line in lines
        if line["kind"] == "service" and any(_bill_match(description, kw) for kw in line.get("keywords", ()))
    ]
    return named[0] if len(named) == 1 else None


def _bill_outage_lob(description: str, state: dict[str, Any]) -> str:
    record = account_record(state)
    lobs = [lob for lob in record.get("lines_of_business", []) if lob in SERVICE_PRICES]
    for lob in lobs:
        if any(_bill_match(description, kw) for kw in SERVICE_KEYWORDS.get(lob, ())):
            return lob
    live = str(state.get("lob") or "").strip().lower()
    if live in lobs:
        return live
    return lobs[0] if len(lobs) == 1 else ""


def _bill_credit_reply(
    state: dict[str, Any],
    lang: str,
    kind: str,
    amount: Decimal,
    key: str,
    extra: dict[str, Any],
    to_card: bool = False,
) -> dict[str, Any]:
    """A credit or refund that was applied: the PRD refund_confirmation_pattern facts plus Turn-N+1 fields."""
    account_id = state.get("account_id", "")
    credit_id = tracking_id("CREDIT", account_id, key, amount)
    append_list(state, "applied_adjustments", key)
    live = _bill_live(state, lang)
    balance = live["balance"]
    if not to_card:
        balance = _bill_q(max(balance - amount, _BILL_ZERO))
        _bill_save(state, balance, live["past_due"])
    amount_text = display_amount(amount)
    data = {
        "adjustment_type": kind,
        "approved": True,
        "credit_id": credit_id,
        **money(amount),
        "refund_window_business_days": REFUND_WINDOW_BUSINESS_DAYS,
        "applied_to": "original_payment_method" if to_card else "next_statement",
        "refund_confirmation_line": spoken_line("refund_confirmation_pattern", lang, amount=amount_text, days=REFUND_WINDOW_BUSINESS_DAYS),
        **money(balance, "balance_due"),
        **extra,
    }
    if to_card:
        card = _bill_card_on_file(state)
        data["refund_card_last4"] = card["last4"]
    return _bill_finish(state, ok_reply(data, credit_id, language=lang))


def apply_bill_adjustment_impl(
    adjustment_type: str = "",
    amount: Any = "",
    description: str = "",
    outage_days: Any = "",
    charge_id: str = "",
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Credit a charge, refund a verified duplicate payment, credit outage days, or open a dispute case."""
    st, lang, err = _bill_start(state, session_state, language, "apply_bill_adjustment")
    if err:
        return err
    account_id = st.get("account_id", "")
    desc = " ".join(str(description or "").lower().split())
    kind = _bill_adjustment_type(adjustment_type, desc, outage_days)
    reference = tracking_id("apply_bill_adjustment", account_id, kind, amount, desc, outage_days, charge_id)
    asked: Decimal | None = None
    if str(amount if amount is not None else "").strip():
        asked = _bill_to_amount(amount)
        if asked is None or asked <= _BILL_ZERO:
            return validation_error(st, "The amount is not a valid positive amount.", "Ask the caller for the amount of the charge.", reference, lang)
    applied = [p for p in str(st.get("applied_adjustments") or "").split(",") if p]
    limit = to_decimal(SELF_SERVE_ADJUSTMENT_LIMIT) or _BILL_ZERO

    def _already(key: str) -> dict[str, Any]:
        return _bill_finish(
            st,
            error_reply(
                "ALREADY_APPLIED",
                "This adjustment was already applied on this account.",
                "Say it was already credited; no second credit.",
                reference,
                language=lang,
                data={"adjustment_key": key, "refund_window_business_days": REFUND_WINDOW_BUSINESS_DAYS},
            ),
        )

    def _over_limit(value: Decimal) -> dict[str, Any]:
        # The agent speaks in the same turn as handover_to_person, before it returns, so
        # this reply carries the full transfer sentence: why (the limit) + the verbatim line.
        limit_text = display_amount(limit)
        spoken = spoken_line("refund_over_limit", lang, limit=limit_text) + " " + spoken_line("transfer_to_specialist", lang)
        return _bill_finish(
            st,
            error_reply(
                "REFUND_THRESHOLD_EXCEEDED",
                "The amount is above the self-serve adjustment limit.",
                "Hand over with reason refund_threshold_exceeded.",
                reference,
                language=lang,
                data={
                    **money(value),
                    "limit_display": limit_text,
                    "handover_reason": "refund_threshold_exceeded",
                    "spoken_message": spoken,
                },
            ),
        )

    # Verified duplicate payment: the caller's own money, refunded in full after the
    # ledger check (decision A1). Only a duplicate that is really in the ledger counts.
    dup_amount = to_decimal(DUPLICATE_PAYMENT["amount"]) or _BILL_ZERO
    dup_claim = kind == "duplicate_payment" or any(w in desc for w in _BILL_DUPLICATE_WORDS)
    if dup_claim and fixture_flag(st, "fx_duplicate_payment") and (asked is None or asked == dup_amount):
        if "duplicate_payment" in applied:
            return _already("duplicate_payment")
        when = _bill_date(-int(DUPLICATE_PAYMENT["days_ago"]), lang)
        return _bill_credit_reply(
            st,
            lang,
            "duplicate_payment",
            dup_amount,
            "duplicate_payment",
            {"duplicate_payment_date": when["iso"], "duplicate_payment_date_display": when["display"]},
            to_card=True,
        )
    # (4) Outage credit: monthly price of the affected service / 30 x days. The credit
    # is always computed here (never the caller's figure) and then checked against the limit.
    if kind == "outage_credit":
        days_text = normalize_code(outage_days)
        days = int(days_text) if days_text else 0
        if not 1 <= days <= 365:
            return validation_error(st, "The number of outage days is missing or invalid.", "Ask how many days the service was down.", reference, lang)
        lob = _bill_outage_lob(desc, st)
        if not lob:
            return validation_error(st, "The affected service is unclear.", "Ask which service was down.", reference, lang, data={"lines_of_business": account_record(st).get("lines_of_business", [])})
        key = f"outage:{lob}"
        if key in applied:
            return _already(key)
        monthly = to_decimal(SERVICE_PRICES[lob]) or _BILL_ZERO
        daily = monthly / Decimal(30)
        credit = _bill_q(daily * days)
        if credit > limit:
            return _over_limit(credit)
        return _bill_credit_reply(
            st,
            lang,
            "outage_credit",
            credit,
            key,
            {"lob": lob, "outage_days": days, **money(monthly, "monthly_price"), "daily_rate_display": display_amount(_bill_q(daily))},
        )
    # (1) Over the self-serve limit: a specialist decides.
    if asked is not None and asked > limit:
        return _over_limit(asked)
    # (2) A line item on the latest bill.
    lines = _bill_lines(st, lang)
    line = _bill_find_line(lines, str(charge_id or "").strip(), asked, desc)
    if line is not None:
        line_amount = Decimal(str(line["amount"]))
        credit = line_amount if asked is None or _bill_same_amount(line_amount, asked) else min(asked, line_amount)
        if credit > limit:
            return _over_limit(credit)
        key = f"charge:{line['charge_id']}"
        if key in applied:
            return _already(key)
        return _bill_credit_reply(
            st,
            lang,
            kind if kind != "duplicate_payment" else "incorrect_charge",
            credit,
            key,
            {
                "charge_id": line["charge_id"],
                "charge_description": line["description"],
                "charge_date_display": line["date_display"],
                # Turn N+1 "how did this get on my bill / how do I stop it" (DESIGN_RULES rule 33).
                **{f"charge_{key}": line[key] for key in ("origin", "prevention_tip") if line.get(key)},
            },
        )
    # (5) Nothing matched: open a dispute case for the billing team.
    key = "dispute:" + tracking_id("dispute", kind, asked, desc)
    ticket = tracking_id("DISPUTE", account_id, kind, asked, desc).replace("R", "DSP-", 1)
    # (5a) An overcharge of a stated amount within the self-serve limit on a service the
    # caller names (one monthly service line on the bill, at least that amount) gets a
    # provisional credit now, with the case kept open for the billing team to review
    # (prd.md §10: self-serve adjustments up to the limit). Never for a duplicate-payment
    # claim: those need the ledger match above.
    service_line = _bill_named_service_line(lines, desc) if asked is not None and not dup_claim else None
    if service_line is not None and asked is not None and asked <= Decimal(str(service_line["amount"])):
        prov_key = f"provisional:{service_line['charge_id']}"
        if prov_key in applied:
            return _already(prov_key)
        append_list(st, "applied_adjustments", key)
        dispatch_sms(st, "dispute_opened")
        return _bill_credit_reply(
            st,
            lang,
            kind,
            asked,
            prov_key,
            {
                "provisional": True,
                "charge_id": service_line["charge_id"],
                "charge_description": service_line["description"],
                "charge_date_display": service_line["date_display"],
                "dispute_ticket_id": ticket,
                "review_eta_business_days": DISPUTE_ETA_BUSINESS_DAYS,
            },
        )
    if key in applied:
        return _bill_finish(
            st,
            error_reply(
                "ALREADY_APPLIED",
                "A dispute case is already open for this charge.",
                "Give the existing dispute case number.",
                reference,
                language=lang,
                data={"dispute_ticket_id": ticket, "eta_business_days": DISPUTE_ETA_BUSINESS_DAYS},
            ),
        )
    append_list(st, "applied_adjustments", key)
    sms = dispatch_sms(st, "dispute_opened")
    data = {
        "adjustment_type": kind,
        "approved": False,
        "dispute_opened": True,
        "dispute_ticket_id": ticket,
        "eta_business_days": DISPUTE_ETA_BUSINESS_DAYS,
        "sms_confirmation_sent": True,
        "sms_destination_last4": sms["destination_last4"],
        "spoken_summary": _bill_text(
            lang,
            f"I couldn't match that charge on your latest bill, so I opened dispute case {ticket}. The billing team will reply within {DISPUTE_ETA_BUSINESS_DAYS} business days. A confirmation is on its way by text.",
            f"Je n'ai pas trouvé ces frais sur votre dernière facture, j'ai donc ouvert le dossier de contestation {ticket}. L'équipe de facturation répondra d'ici {DISPUTE_ETA_BUSINESS_DAYS} jours ouvrables. Une confirmation vous est envoyée par texto.",
        ),
    }
    if asked is not None:
        data.update(money(asked))
    return _bill_finish(st, ok_reply(data, ticket, language=lang))


# ---------------------------------------------------------------------------
# setup_payment_arrangement
# ---------------------------------------------------------------------------


def setup_payment_arrangement_impl(
    first_payment_amount: Any = "",
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Split the balance into two instalments and restore a non-payment suspension."""
    st, lang, err = _bill_start(state, session_state, language, "setup_payment_arrangement")
    if err:
        return err
    account_id = st.get("account_id", "")
    live = _bill_live(st, lang)
    reference = tracking_id("setup_payment_arrangement", account_id, first_payment_amount, live["balance"])
    if _bill_flag(st, "arrangement_active"):
        return _bill_finish(
            st,
            error_reply(
                "NOT_ELIGIBLE",
                "Only one payment arrangement is allowed every 12 months.",
                "Say an arrangement is already in place; offer a payment instead.",
                reference,
                language=lang,
                data={"arrangement_active": True},
            ),
        )
    if live["balance"] <= _BILL_ZERO:
        return _bill_finish(
            st,
            error_reply(
                "NOT_ELIGIBLE",
                "There is no balance to arrange.",
                "Say the balance is already paid.",
                reference,
                language=lang,
                data=money(live["balance"], "balance_due"),
            ),
        )
    first: Decimal | None = None
    if str(first_payment_amount if first_payment_amount is not None else "").strip():
        first = _bill_to_amount(first_payment_amount)
        if first is None or first <= _BILL_ZERO or first >= live["balance"]:
            return validation_error(
                st,
                "The first instalment must be more than zero and less than the balance.",
                "Offer the standard split from the tool or ask for another first amount.",
                reference,
                lang,
                data=money(live["balance"], "balance_due"),
            )
    plan = _bill_arrangement_offer(live["balance"], lang, first)
    st["arrangement_active"] = True
    status_before = service_status(st)
    arrangement_id = tracking_id("ARRANGEMENT", account_id, live["balance"], plan["instalments"][0]["amount"])
    sms = dispatch_sms(st, "arrangement_confirmation")
    data: dict[str, Any] = {
        "arrangement_id": arrangement_id,
        **plan,
        "balance_unchanged": True,
        "confirmation_sms_sent": sms["sms_sent"],
        "sms_destination_last4": sms["destination_last4"],
        "service_restored": False,
        "service_status": status_before,
        "next_arrangement_allowed": "in_12_months",
    }
    one, two = plan["instalments"]
    summary = _bill_text(
        lang,
        f"Your arrangement is set: {_bill_amount_text(lang, Decimal(str(one['amount'])))} by {one['due_date_display']}, "
        f"then {_bill_amount_text(lang, Decimal(str(two['amount'])))} by {two['due_date_display']}.",
        f"Votre entente est en place : {_bill_amount_text(lang, Decimal(str(one['amount'])))} d'ici le {one['due_date_display']}, "
        f"puis {_bill_amount_text(lang, Decimal(str(two['amount'])))} d'ici le {two['due_date_display']}.",
    )
    if status_before == "suspended_nonpayment":
        data.update(_bill_restore(st, lang))
        data["service_status"] = "active"
        summary += _bill_text(lang, " Your service is restored.", " Votre service est rétabli.")
    if sms["sms_sent"]:
        summary += _bill_text(lang, " A confirmation text is on its way.", " Une confirmation vous est envoyée par texto.")
    summary += _bill_reference_text(lang, "arrangement", arrangement_id)
    data["spoken_summary"] = summary
    return _bill_finish(st, ok_reply(data, arrangement_id, language=lang))


# ---------------------------------------------------------------------------
# verify_payment_and_restore
# ---------------------------------------------------------------------------


def verify_payment_and_restore_impl(
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """For "I already paid": find a posted payment that covers the past-due amount, then restore."""
    st, lang, err = _bill_start(state, session_state, language, "verify_payment_and_restore")
    if err:
        return err
    account_id = st.get("account_id", "")
    status = service_status(st)
    live = _bill_live(st, lang)
    reference = tracking_id("verify_payment_and_restore", account_id, status, live["past_due"])
    if status in ("suspended_lost_stolen", "suspended_travel"):
        return _bill_finish(
            st,
            error_reply(
                "NOT_ELIGIBLE",
                "This suspension is not for non-payment.",
                "Transfer to the router agent so the account team can restore it.",
                reference,
                language=lang,
                data={"service_status": status, "suspension_reason": _BILL_SUSPENSION_REASONS[status]},
            ),
        )
    if status != "suspended_nonpayment":
        return _bill_finish(
            st,
            error_reply(
                "NOT_SUSPENDED",
                "The service is not suspended.",
                "Say the service is active.",
                reference,
                language=lang,
                data={"service_status": status, **money(live["balance"], "balance_due")},
            ),
        )
    recent = fixture(st, "fx_recent_payment")
    posted = (to_decimal(PAST_DUE_AMOUNT) or _BILL_ZERO) if recent == "posted_yesterday" and not _bill_flag(st, "recent_payment_applied") else _BILL_ZERO
    if posted <= _BILL_ZERO or posted < live["past_due"]:
        return _bill_finish(
            st,
            error_reply(
                "NO_PAYMENT_FOUND",
                "No posted payment covers the past-due amount.",
                "Say no payment has posted; offer to pay now or set up an arrangement.",
                reference,
                language=lang,
                data={
                    **money(live["past_due"], "past_due_amount"),
                    **money(live["balance"], "balance_due"),
                    "options": ["pay_past_due", "payment_arrangement"],
                },
            ),
        )
    when = _bill_date(-RECENT_PAYMENT_DAYS_AGO, lang)
    st["recent_payment_applied"] = True
    new_balance = _bill_q(max(live["balance"] - posted, _BILL_ZERO))
    _bill_save(st, new_balance, _BILL_ZERO)
    restored = _bill_restore(st, lang)
    data = {
        "payment_verified": True,
        "verified_payment_date": when["iso"],
        "verified_payment_date_display": when["display"],
        **money(posted, "verified_payment_amount"),
        **money(new_balance, "remaining_balance"),
        **restored,
        "spoken_summary": _bill_text(
            lang,
            f"I found your payment of {_bill_amount_text(lang, posted)} from {when['display']}. Your service is restored and a confirmation text is on its way.",
            f"J'ai trouvé votre paiement de {_bill_amount_text(lang, posted)} du {when['display']}. Votre service est rétabli et une confirmation vous est envoyée par texto.",
        ),
    }
    return _bill_finish(st, ok_reply(data, tracking_id("RESTORE", account_id, when["iso"]), language=lang))
