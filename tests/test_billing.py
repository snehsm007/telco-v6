"""Billing tools (docs/tdd.md §4 Billing): balance, payments, autopay, adjustments, arrangements, restore."""

from decimal import Decimal

import pytest

from lib import billing
from lib.billing import (
    apply_bill_adjustment_impl,
    get_billing_summary_impl,
    process_bill_payment_impl,
    setup_autopay_impl,
    setup_payment_arrangement_impl,
    verify_payment_and_restore_impl,
)
from lib.fakes import (
    ACCOUNTS,
    AUTOPAY_DISCOUNT,
    AUTOPAY_DISCOUNT_NOTE,
    AUTOPAY_WITHDRAWAL_NOTE,
    BILL_CYCLE_DAYS_AGO,
    BILL_DATE_CHANGE_NOTE,
    BILL_DUE_IN_DAYS,
    BILL_EXTRA_LINES,
    DUPLICATE_PAYMENT,
    PAST_DUE_AMOUNT,
    REFUND_WINDOW_BUSINESS_DAYS,
    SELF_SERVE_ADJUSTMENT_LIMIT,
    SERVICE_PRICES,
)

DEFAULT = ACCOUNTS[0]
STREAMING = next(line for line in BILL_EXTRA_LINES if line["charge_id"] == "CH-STR-01")
LONG_DISTANCE = next(line for line in BILL_EXTRA_LINES if line["charge_id"] == "CH-LD-01")
NEW_CARD = "5105105105105100"


def logged_in(**extra):
    state = {"account_id": DEFAULT["account_id"], "phone_last4": DEFAULT["phone"][-4:], "auth_status": "pass", "logged_in": True}
    state.update(extra)
    return state


def expected_balance(extra=Decimal("0")):
    charges = sum(Decimal(SERVICE_PRICES[lob]) for lob in DEFAULT["lines_of_business"])
    charges += sum(Decimal(line["amount"]) for line in BILL_EXTRA_LINES)
    return charges + Decimal(PAST_DUE_AMOUNT) + extra


ALL_TOOLS = (
    lambda s: get_billing_summary_impl(state=s),
    lambda s: process_bill_payment_impl("", "card_on_file", state=s),
    lambda s: setup_autopay_impl("card_on_file", state=s),
    lambda s: apply_bill_adjustment_impl("unrecognized_charge", "", "streaming", state=s),
    lambda s: setup_payment_arrangement_impl(state=s),
    lambda s: verify_payment_and_restore_impl(state=s),
)


# --- gates shared by every billing tool -------------------------------------


@pytest.mark.parametrize("call", ALL_TOOLS)
def test_every_tool_needs_login(call):
    reply = call({"account_id": DEFAULT["account_id"], "auth_status": "code_sent"})
    assert reply["error"] == "NOT_LOGGED_IN"


@pytest.mark.parametrize("call", ALL_TOOLS)
def test_every_tool_honours_mock_error(call):
    reply = call(logged_in(mock_error="SYSTEM_DOWN"))
    assert reply["error"] == "SYSTEM_UNAVAILABLE"
    assert "system_unavailable" in reply["agent_action"]


@pytest.mark.parametrize("call", ALL_TOOLS)
def test_business_accounts_are_handed_over(call):
    reply = call(logged_in(business_flag=True))
    assert reply["error"] == "PERMISSION_DENIED"
    assert "business_handoff" in reply["agent_action"]


def test_no_shared_default_state_between_calls():
    first = process_bill_payment_impl("", "card_on_file", session_state=logged_in())
    assert first["status"] == "ok"
    assert get_billing_summary_impl()["error"] == "NOT_LOGGED_IN"


def test_mock_mode_marks_replies():
    reply = get_billing_summary_impl(state=logged_in(mock_mode="true"))
    assert reply["data"]["mock_mode"] is True


# --- get_billing_summary -----------------------------------------------------


def test_summary_has_balance_lines_and_payments():
    reply = get_billing_summary_impl(state=logged_in())
    data = reply["data"]
    assert reply["status"] == "ok"
    assert data["balance_due_display"] == str(expected_balance())
    assert data["past_due_amount_display"] == PAST_DUE_AMOUNT
    assert data["currency"] == "CAD"
    assert data["card_on_file_last4"] == DEFAULT["card_last4"]
    assert data["autopay_enrolled"] is False
    items = data["recent_bills"][0]["line_items"]
    assert {"charge_id", "description", "amount", "amount_display", "lob", "date", "date_display"} <= set(items[0])
    assert any(i["charge_id"] == STREAMING["charge_id"] for i in items)
    assert all("keywords" not in i for i in items)
    assert data["recent_payments"]
    assert data["arrangement_offer"]["instalment_count"] == 2
    assert data["service_status"] == "active"
    assert "restore_options" not in data
    assert data["balance_due_display"] in data["spoken_summary"]


def test_summary_in_french():
    reply = get_billing_summary_impl(state=logged_in(), language="fr-CA")
    assert reply["active_language"] == "fr-CA"
    assert "Votre solde" in reply["data"]["spoken_summary"]
    assert any(i["description"] == "Appels interurbains" for i in reply["data"]["recent_bills"][0]["line_items"])


def test_summary_suspended_nonpayment_offers_restore_paths():
    data = get_billing_summary_impl(state=logged_in(fx_service_status="suspended_nonpayment"))["data"]
    assert data["suspension_reason"] == "non_payment"
    assert data["amount_to_restore_display"] == PAST_DUE_AMOUNT
    assert data["restore_options"] == ["pay_past_due", "verify_recent_payment", "payment_arrangement"]
    assert "suspended" in data["spoken_summary"]


def test_summary_lost_stolen_points_to_account():
    data = get_billing_summary_impl(state=logged_in(fx_service_status="suspended_lost_stolen"))["data"]
    assert data["restore_handled_by"] == "account"


def test_summary_extra_bill_line_fixture():
    state = logged_in(fx_extra_bill_line="Equipment rental adjustment|9.75|internet")
    data = get_billing_summary_impl(state=state)["data"]
    assert data["balance_due_display"] == str(expected_balance(Decimal("9.75")))
    assert any(i["charge_id"] == "CH-EXT-01" and i["amount_display"] == "9.75" for i in data["recent_bills"][0]["line_items"])


def test_summary_ignores_malformed_extra_line():
    data = get_billing_summary_impl(state=logged_in(fx_extra_bill_line="no amount here"))["data"]
    assert data["balance_due_display"] == str(expected_balance())


def test_summary_shows_duplicate_and_posted_payments():
    state = logged_in(fx_duplicate_payment="true", fx_recent_payment="posted_yesterday")
    payments = get_billing_summary_impl(state=state)["data"]["recent_payments"]
    assert sum(1 for p in payments if p.get("duplicate")) == 1
    assert any(p["status"] == "posted_not_applied" for p in payments)


def test_summary_account_without_extra_lob_lines():
    state = logged_in(account_id=ACCOUNTS[1]["account_id"])
    items = get_billing_summary_impl(state=state)["data"]["recent_bills"][0]["line_items"]
    assert {i["lob"] for i in items} <= set(ACCOUNTS[1]["lines_of_business"])
    assert all(i["charge_id"] != STREAMING["charge_id"] for i in items)


# --- process_bill_payment ------------------------------------------------------


def test_full_payment_with_card_on_file():
    state = logged_in()
    reply = process_bill_payment_impl("full", "card_on_file", state=state)
    data = reply["data"]
    assert reply["status"] == "ok"
    assert data["amount_paid_display"] == str(expected_balance())
    assert data["card_last4"] == DEFAULT["card_last4"]
    assert data["remaining_balance_display"] == "0.00"
    assert data["paid_in_full"] is True
    assert data["receipt_sms_sent"] is True
    assert data["suspension_risk_cleared"] is True
    assert data["next_due_date_display"]
    assert state["balance_due"] == "0.00"
    assert state["last_payment_method"] == "card_on_file"
    assert "payment_receipt" in state["sms_sent"]
    summary = get_billing_summary_impl(state=state)["data"]
    assert summary["balance_due_display"] == "0.00"
    assert any(p["date"] == data["next_due_date"] or p["status"] == "posted" for p in summary["recent_payments"])
    again = process_bill_payment_impl("", "card_on_file", state=state)
    assert again["error"] == "NOT_ELIGIBLE"


def test_partial_payment_never_zeroes_or_restores():
    state = logged_in(fx_service_status="suspended_nonpayment")
    reply = process_bill_payment_impl("50", "card_on_file", state=state)
    data = reply["data"]
    assert reply["status"] == "ok"
    assert data["service_restored"] is False
    assert data["service_status"] == "suspended_nonpayment"
    assert data["remaining_past_due_display"] == str(Decimal(PAST_DUE_AMOUNT) - 50)
    assert data["remaining_balance_display"] == str(expected_balance() - 50)
    assert data["restore_requires_display"] == data["remaining_past_due_display"]
    assert state.get("service_status") in (None, "", "suspended_nonpayment")
    assert verify_payment_and_restore_impl(state=state)["error"] == "NO_PAYMENT_FOUND"


def test_past_due_payment_restores_in_the_same_call():
    state = logged_in(fx_service_status="suspended_nonpayment")
    reply = process_bill_payment_impl("past due", "card_on_file", state=state)
    data = reply["data"]
    assert data["amount_paid_display"] == PAST_DUE_AMOUNT
    assert data["service_restored"] is True
    assert data["new_service_status"] == "active"
    assert data["restore_sms_sent"] is True
    assert state["service_status"] == "active"
    assert data["remaining_balance_display"] == str(expected_balance() - Decimal(PAST_DUE_AMOUNT))
    assert "restored" in data["spoken_summary"]


def test_payment_in_french_with_bank_on_file():
    state = logged_in()
    reply = process_bill_payment_impl("20,00", "compte bancaire", state=state, language="fr-CA")
    data = reply["data"]
    assert data["payment_method"] == "bank_account"
    assert data["bank_last4"] and data["card_last4"] == ""
    assert "compte bancaire" in data["spoken_summary"]
    assert "Votre paiement" in data["spoken_summary"]
    assert state["last_payment_method"] == "bank_account"


def test_payment_with_bank_digits_and_bad_bank_digits():
    state = logged_in()
    ok = process_bill_payment_impl("10", "bank_account", "00123456789", state=state)
    assert ok["data"]["bank_last4"] == "6789"
    bad = process_bill_payment_impl("10", "bank_account", "123", state=logged_in())
    assert bad["error"] == "INVALID_INPUT"


def test_declined_card_on_file_then_new_card():
    state = logged_in(fx_card_on_file_status="declined")
    declined = process_bill_payment_impl("", "card_on_file", state=state)
    assert declined["error"] == "CARD_DECLINED"
    assert state["card_last4"] == ""
    assert state["declined_card_last4"] == DEFAULT["card_last4"]
    assert state["payment_declined_once"] is True
    assert declined["data"]["other_methods"] == ["new_card", "bank_account"]
    again = process_bill_payment_impl("", "card_on_file", state=state)
    assert again["error"] == "CARD_DECLINED"
    summary = get_billing_summary_impl(state=state)["data"]
    assert summary["card_on_file_last4"] == ""
    paid = process_bill_payment_impl("", "new_card", NEW_CARD, state=state)
    assert paid["status"] == "ok"
    assert paid["data"]["card_last4"] == NEW_CARD[-4:]
    assert paid["data"]["card_brand"] == "Mastercard"
    assert state["card_last4"] == NEW_CARD[-4:]
    assert state["payment_failure_count"] == 0
    assert state["last_payment_method"] == "new_card"


def test_expired_card_on_file():
    state = logged_in(fx_card_on_file_status="expired")
    assert process_bill_payment_impl("", "card_on_file", state=state)["error"] == "CARD_EXPIRED"
    assert state["card_last4"] == ""


def test_new_card_from_keypad_state():
    state = logged_in(dtmf_digits="4111 2222 3333 4448")
    reply = process_bill_payment_impl("", "new_card", state=state)
    assert reply["data"]["card_last4"] == "4448"
    assert reply["data"]["card_brand"] == "Visa"


def test_new_card_from_dtmf_argument():
    reply = process_bill_payment_impl("", "new card", "", "3782 822463 10005", state=logged_in())
    assert reply["data"]["card_last4"] == "0005"


def test_keypad_pin_is_not_taken_as_a_card():
    reply = process_bill_payment_impl("", "new_card", state=logged_in(dtmf_digits="5903"))
    assert reply["error"] == "INVALID_INPUT"
    assert reply["data"]["needs_card"] is True


def test_last4_of_card_on_file_means_card_on_file():
    reply = process_bill_payment_impl("", "new_card", DEFAULT["card_last4"], state=logged_in())
    assert reply["data"]["payment_method"] == "card_on_file"


def test_caller_named_card_ending_is_charged_and_read_back_as_last4():
    state = logged_in()
    reply = process_bill_payment_impl("", "card_on_file", "6150", state=state)
    assert reply["status"] == "ok"
    assert reply["data"]["card_last4"] == "6150"
    assert "ending in 6150" in reply["data"]["spoken_summary"]
    assert state["card_last4"] == "6150"


def test_declined_card_on_file_then_same_ending_declines_and_another_ending_pays():
    state = logged_in(fx_card_on_file_status="declined")
    assert process_bill_payment_impl("", "card_on_file", state=state)["error"] == "CARD_DECLINED"
    assert process_bill_payment_impl("", "card_on_file", DEFAULT["card_last4"], state=state)["error"] == "CARD_DECLINED"
    assert process_bill_payment_impl("", "new_card", "0000", state=state)["error"] == "CARD_DECLINED"
    paid = process_bill_payment_impl("", "new_card", "6150", state=state)
    assert paid["status"] == "ok"
    assert paid["data"]["card_last4"] == "6150"


def test_missing_card_does_not_count_as_a_hard_error():
    state = logged_in()
    for _ in range(3):
        assert process_bill_payment_impl("", "new_card", "", state=state)["error"] == "INVALID_INPUT"
    assert not state.get("global_err_count")
    short = process_bill_payment_impl("", "new_card", "51051051", state=state)
    assert short["error"] == "INVALID_INPUT"
    assert state["global_err_count"] == 1


def test_full_number_with_card_on_file_wording_is_a_new_card():
    reply = process_bill_payment_impl("", "credit card", NEW_CARD, state=logged_in())
    assert reply["data"]["payment_method"] == "new_card"


def test_new_card_on_decline_list():
    state = logged_in()
    reply = process_bill_payment_impl("", "new_card", "4000000000000000", state=state)
    assert reply["error"] == "CARD_DECLINED"
    assert state["declined_card_last4"] == "0000"


def test_payment_validation_errors_count_to_too_many():
    state = logged_in()
    assert process_bill_payment_impl("-5", "card_on_file", state=state)["error"] == "INVALID_INPUT"
    assert process_bill_payment_impl("100000", "card_on_file", state=state)["error"] == "INVALID_INPUT"
    third = process_bill_payment_impl("", "bitcoin", state=state)
    assert third["error"] == "TOO_MANY_ERRORS"


def test_payment_amount_not_a_number():
    assert process_bill_payment_impl("abc", "card_on_file", state=logged_in())["error"] == "INVALID_INPUT"
    assert process_bill_payment_impl(True, "card_on_file", state=logged_in())["error"] == "INVALID_INPUT"


def test_amounts_with_words_around_them():
    reply = process_bill_payment_impl("20.50 dollars", "card_on_file", state=logged_in())
    assert reply["data"]["amount_paid_display"] == "20.50"
    french = process_bill_payment_impl("20,50 $", "carte au dossier", state=logged_in(), language="fr-CA")
    assert french["data"]["amount_paid_display"] == "20.50"
    assert billing._bill_to_amount(True) is None


def test_payment_id_is_unique_per_payment():
    state = logged_in()
    first = process_bill_payment_impl("10", "card_on_file", state=state)
    second = process_bill_payment_impl("10", "card_on_file", state=state)
    assert first["data"]["payment_id"] != second["data"]["payment_id"]


# --- setup_autopay ------------------------------------------------------------


def test_autopay_card_on_file_then_already_enrolled():
    state = logged_in()
    reply = setup_autopay_impl("card_on_file", state=state)
    data = reply["data"]
    assert data["autopay_enrolled"] is True
    assert data["card_last4"] == DEFAULT["card_last4"]
    assert data["first_charge_date_display"]
    assert data["current_balance_included"] is True
    assert state["autopay_enrolled"] is True
    assert get_billing_summary_impl(state=state)["data"]["autopay_enrolled"] is True
    assert setup_autopay_impl("card_on_file", state=state)["error"] == "ALREADY_ENROLLED"


def test_autopay_after_paying_starts_next_cycle():
    state = logged_in()
    paid = process_bill_payment_impl("", "card_on_file", state=state)
    auto = setup_autopay_impl("card_on_file", state=state)
    assert auto["status"] == "ok"
    assert auto["data"]["current_balance_included"] is False
    assert auto["data"]["first_charge_date"] == paid["data"]["next_due_date"]


def test_autopay_new_card_and_bank_in_french():
    state = logged_in()
    reply = setup_autopay_impl("new_card", NEW_CARD, state=state, language="fr-CA")
    assert reply["data"]["card_last4"] == NEW_CARD[-4:]
    assert "paiements préautorisés" in reply["data"]["spoken_summary"]
    bank = setup_autopay_impl("bank_account", state=logged_in(), language="fr-CA")
    assert bank["data"]["method"] == "bank_account"
    assert "avec le compte bancaire" in bank["data"]["spoken_summary"]


def test_autopay_with_caller_named_card_ending():
    state = logged_in()
    reply = setup_autopay_impl("new_card", "6150", state=state)
    assert reply["data"]["card_last4"] == "6150"
    assert state["card_last4"] == "6150"


def test_autopay_follow_up_facts_localized_in_summary_and_setup():
    days = str(BILL_CYCLE_DAYS_AGO + BILL_DUE_IN_DAYS)
    summary = get_billing_summary_impl(state=logged_in())["data"]
    assert days in summary["autopay_withdrawal_note"]
    assert summary["bill_date_change_note"] == BILL_DATE_CHANGE_NOTE[0]
    assert summary["autopay_discount_display"] == AUTOPAY_DISCOUNT
    fr = setup_autopay_impl("card_on_file", state=logged_in(), language="fr-CA")["data"]
    assert fr["autopay_discount_note"] == AUTOPAY_DISCOUNT_NOTE[1]
    assert fr["autopay_withdrawal_note"] == AUTOPAY_WITHDRAWAL_NOTE[1].replace("[days]", days)
    assert not any(key.endswith(("_en", "_fr")) for key in fr)


def test_autopay_with_declined_card_on_file():
    state = logged_in(fx_card_on_file_status="declined")
    assert setup_autopay_impl("card_on_file", state=state)["error"] == "CARD_DECLINED"
    assert state.get("autopay_enrolled") is None


# --- apply_bill_adjustment -----------------------------------------------------


def test_unrecognized_charge_is_credited_with_refund_pattern():
    state = logged_in()
    reply = apply_bill_adjustment_impl("unrecognized_charge", STREAMING["amount"], "streaming purchase", state=state)
    data = reply["data"]
    assert reply["status"] == "ok"
    assert data["approved"] is True
    assert data["amount_display"] == STREAMING["amount"]
    assert data["refund_window_business_days"] == REFUND_WINDOW_BUSINESS_DAYS
    assert data["charge_id"] == STREAMING["charge_id"]
    assert data["credit_id"]
    assert STREAMING["amount"] in data["refund_confirmation_line"]
    assert data["balance_due_display"] == str(expected_balance() - Decimal(STREAMING["amount"]))
    again = apply_bill_adjustment_impl("unrecognized_charge", STREAMING["amount"], "streaming purchase", state=state)
    assert again["error"] == "ALREADY_APPLIED"


def test_charge_found_by_whole_dollar_amount():
    reply = apply_bill_adjustment_impl("unrecognized_charge", str(int(Decimal(STREAMING["amount"]))), "", state=logged_in())
    assert reply["data"]["charge_id"] == STREAMING["charge_id"]
    assert reply["data"]["amount_display"] == STREAMING["amount"]


def test_charge_found_by_charge_id():
    reply = apply_bill_adjustment_impl("incorrect_charge", "", "", charge_id=LONG_DISTANCE["charge_id"], state=logged_in())
    assert reply["data"]["amount_display"] == LONG_DISTANCE["amount"]


def test_charge_found_by_french_words():
    reply = apply_bill_adjustment_impl("incorrect_charge", "", "appels interurbains que je n'ai jamais faits", state=logged_in(), language="fr-CA")
    data = reply["data"]
    assert data["charge_id"] == LONG_DISTANCE["charge_id"]
    assert data["refund_confirmation_line"].startswith("Votre remboursement de")


def test_fixture_extra_line_is_matched_by_amount():
    state = logged_in(fx_extra_bill_line="Internet service overcharge|15.00|internet")
    reply = apply_bill_adjustment_impl("incorrect_charge", "15", "internet overcharge", state=state)
    assert reply["data"]["charge_id"] == "CH-EXT-01"
    assert reply["data"]["amount_display"] == "15.00"


def test_partial_overcharge_on_a_service_opens_a_dispute():
    state = logged_in()
    reply = apply_bill_adjustment_impl("incorrect_charge", "15", "internet overcharge", state=state)
    data = reply["data"]
    assert data["approved"] is False
    assert data["dispute_opened"] is True
    assert data["dispute_ticket_id"].startswith("DSP-")
    assert data["eta_business_days"] > 0
    assert data["amount_display"] == "15.00"
    again = apply_bill_adjustment_impl("incorrect_charge", "15", "internet overcharge", state=state)
    assert again["error"] == "ALREADY_APPLIED"
    assert again["data"]["dispute_ticket_id"] == data["dispute_ticket_id"]


def test_unmatched_description_opens_dispute_in_french():
    reply = apply_bill_adjustment_impl("", "", "frais inconnus", state=logged_in(), language="fr-CA")
    assert reply["data"]["dispute_opened"] is True
    assert "contestation" in reply["data"]["spoken_summary"]


def test_ambiguous_words_open_a_dispute():
    reply = apply_bill_adjustment_impl("unrecognized_charge", "", "monthly service", state=logged_in())
    assert reply["data"]["dispute_opened"] is True


def test_partial_amount_with_charge_id_credits_part():
    reply = apply_bill_adjustment_impl("incorrect_charge", "5", "", charge_id=LONG_DISTANCE["charge_id"], state=logged_in())
    assert reply["data"]["amount_display"] == "5.00"


def test_over_limit_amount_goes_to_specialist():
    state = logged_in()
    reply = apply_bill_adjustment_impl("incorrect_charge", "150.00", "modem already returned", state=state)
    assert reply["error"] == "REFUND_THRESHOLD_EXCEEDED"
    assert reply["agent_action"] == "Hand over with reason refund_threshold_exceeded."
    assert reply["data"]["limit_display"] == SELF_SERVE_ADJUSTMENT_LIMIT
    assert not state.get("applied_adjustments")


def test_whole_service_line_over_limit_goes_to_specialist():
    reply = apply_bill_adjustment_impl("incorrect_charge", "", "", charge_id="CH-SVC-INTERNET", state=logged_in())
    assert reply["error"] == "REFUND_THRESHOLD_EXCEEDED"


def test_outage_credit_is_prorated():
    state = logged_in()
    reply = apply_bill_adjustment_impl("outage_credit", "", "internet was down", 3, state=state)
    data = reply["data"]
    expected = (Decimal(SERVICE_PRICES["internet"]) / 30 * 3).quantize(Decimal("0.01"))
    assert data["amount_display"] == str(expected)
    assert data["lob"] == "internet"
    assert data["outage_days"] == 3
    assert data["daily_rate_display"]
    again = apply_bill_adjustment_impl("outage_credit", "", "internet was down", 2, state=state)
    assert again["error"] == "ALREADY_APPLIED"


def test_outage_credit_ignores_the_callers_monthly_amount():
    reply = apply_bill_adjustment_impl("outage_credit", SERVICE_PRICES["internet"], "internet", "3", state=logged_in())
    assert reply["status"] == "ok"


def test_long_outage_is_capped_by_the_limit():
    reply = apply_bill_adjustment_impl("outage_credit", "", "internet", 365, state=logged_in())
    assert reply["error"] == "REFUND_THRESHOLD_EXCEEDED"


def test_outage_validation():
    assert apply_bill_adjustment_impl("outage_credit", "", "internet", "", state=logged_in())["error"] == "INVALID_INPUT"
    assert apply_bill_adjustment_impl("outage_credit", "", "internet", 400, state=logged_in())["error"] == "INVALID_INPUT"
    reply = apply_bill_adjustment_impl("outage_credit", "", "it was down", 2, state=logged_in())
    assert reply["error"] == "INVALID_INPUT"


def test_outage_service_from_session_lob_or_single_lob():
    reply = apply_bill_adjustment_impl("outage", "", "it was down", 2, state=logged_in(lob="tv"))
    assert reply["data"]["lob"] == "tv"
    single = logged_in(account_id=ACCOUNTS[1]["account_id"])
    single_reply = apply_bill_adjustment_impl("", "", "down", 2, state=single)
    assert single_reply["error"] == "INVALID_INPUT"  # two services on that account: ask which


def test_verified_duplicate_payment_is_refunded_in_full():
    state = logged_in(fx_duplicate_payment="true")
    reply = apply_bill_adjustment_impl("duplicate_payment", "", "payé deux fois", state=state, language="fr-CA")
    data = reply["data"]
    assert data["amount_display"] == DUPLICATE_PAYMENT["amount"]
    assert data["applied_to"] == "original_payment_method"
    assert data["refund_card_last4"] == DEFAULT["card_last4"]
    assert data["refund_confirmation_line"].startswith("Votre remboursement de")
    assert apply_bill_adjustment_impl("duplicate_payment", "", "", state=state)["error"] == "ALREADY_APPLIED"
    payments = get_billing_summary_impl(state=state)["data"]["recent_payments"]
    assert any(p.get("duplicate") and p["status"] == "refunded" for p in payments)


def test_duplicate_found_from_description_when_type_differs():
    state = logged_in(fx_duplicate_payment="true")
    reply = apply_bill_adjustment_impl("incorrect_charge", DUPLICATE_PAYMENT["amount"], "I paid my bill twice", state=state)
    assert reply["data"]["adjustment_type"] == "duplicate_payment"


def test_duplicate_claim_without_ledger_proof_is_not_refunded():
    no_dup = {"fx_duplicate_payment": "false"}
    reply = apply_bill_adjustment_impl("duplicate_payment", DUPLICATE_PAYMENT["amount"], "paid twice", state=logged_in(**no_dup))
    assert reply["error"] == "REFUND_THRESHOLD_EXCEEDED"
    small = apply_bill_adjustment_impl("duplicate_payment", "", "paid twice", state=logged_in(**no_dup))
    assert small["data"]["dispute_opened"] is True


def test_default_ledger_holds_a_duplicate_refunded_only_on_a_claim():
    # Default world (no fx_* overrides): the duplicate is in the ledger, so a caller who
    # says they paid twice gets it back; nobody else is refunded anything.
    state = logged_in()
    payments = get_billing_summary_impl(state=state)["data"]["recent_payments"]
    assert sum(1 for p in payments if p.get("duplicate")) == 1
    assert state.get("applied_adjustments", "") == ""
    reply = apply_bill_adjustment_impl("duplicate_payment", "", "j'ai payé deux fois", state=state, language="fr-CA")
    assert reply["data"]["amount_display"] == DUPLICATE_PAYMENT["amount"]
    assert reply["data"]["applied_to"] == "original_payment_method"
    # A different amount than the ledger's duplicate is not a verified duplicate.
    other = apply_bill_adjustment_impl("duplicate_payment", "60.00", "paid twice", state=logged_in())
    assert other["error"] == "REFUND_THRESHOLD_EXCEEDED"


def test_adjustment_amount_validation():
    assert apply_bill_adjustment_impl("incorrect_charge", "-3", "x", state=logged_in())["error"] == "INVALID_INPUT"
    assert apply_bill_adjustment_impl("incorrect_charge", "abc", "x", state=logged_in())["error"] == "INVALID_INPUT"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("outage_credit", "outage_credit"),
        ("panne", "outage_credit"),
        ("double payment", "duplicate_payment"),
        ("overcharge", "incorrect_charge"),
        ("something", "unrecognized_charge"),
    ],
)
def test_adjustment_type_normalization(raw, expected):
    assert billing._bill_adjustment_type(raw, "", "") == expected


def test_adjustment_type_inferred_from_context():
    assert billing._bill_adjustment_type("", "", "3") == "outage_credit"
    assert billing._bill_adjustment_type("", "paid twice", "") == "duplicate_payment"
    assert billing._bill_adjustment_type("", "", "") == "unrecognized_charge"


# --- setup_payment_arrangement -------------------------------------------------


def test_arrangement_restores_and_is_once_only():
    state = logged_in(fx_service_status="suspended_nonpayment")
    reply = setup_payment_arrangement_impl(state=state)
    data = reply["data"]
    first, second = data["instalments"]
    assert Decimal(first["amount_display"]) + Decimal(second["amount_display"]) == expected_balance()
    assert first["due_date_display"] and second["due_date_display"]
    assert data["service_restored"] is True
    assert state["service_status"] == "active"
    assert state["arrangement_active"] is True
    assert data["balance_unchanged"] is True
    again = setup_payment_arrangement_impl(state=state)
    assert again["error"] == "NOT_ELIGIBLE"
    assert "arrangement_offer" not in get_billing_summary_impl(state=state)["data"]


def test_arrangement_on_active_account_with_chosen_first_amount_in_french():
    reply = setup_payment_arrangement_impl("100", state=logged_in(), language="fr-CA")
    data = reply["data"]
    assert data["instalments"][0]["amount_display"] == "100.00"
    assert data["service_restored"] is False
    assert "entente" in data["spoken_summary"]


def test_arrangement_validation_and_nothing_owed():
    state = logged_in()
    assert setup_payment_arrangement_impl("0", state=state)["error"] == "INVALID_INPUT"
    paid = logged_in()
    process_bill_payment_impl("", "card_on_file", state=paid)
    assert setup_payment_arrangement_impl(state=paid)["error"] == "NOT_ELIGIBLE"


# --- verify_payment_and_restore ------------------------------------------------


def test_verified_posted_payment_restores():
    state = logged_in(fx_service_status="suspended_nonpayment", fx_recent_payment="posted_yesterday")
    reply = verify_payment_and_restore_impl(state=state, language="fr-CA")
    data = reply["data"]
    assert data["payment_verified"] is True
    assert data["verified_payment_amount_display"] == PAST_DUE_AMOUNT
    assert data["verified_payment_date_display"]
    assert data["service_restored"] is True
    assert data["restore_sms_sent"] is True
    assert state["service_status"] == "active"
    assert state["past_due_amount"] == "0.00"
    assert "rétabli" in data["spoken_summary"]
    assert verify_payment_and_restore_impl(state=state)["error"] == "NOT_SUSPENDED"


def test_no_posted_payment_never_restores_on_the_callers_word():
    state = logged_in(fx_service_status="suspended_nonpayment")
    reply = verify_payment_and_restore_impl(state=state)
    assert reply["error"] == "NO_PAYMENT_FOUND"
    assert reply["data"]["past_due_amount_display"] == PAST_DUE_AMOUNT
    assert reply["data"]["options"] == ["pay_past_due", "payment_arrangement"]
    assert state.get("service_status") != "active"


def test_verify_on_active_and_other_suspensions():
    assert verify_payment_and_restore_impl(state=logged_in())["error"] == "NOT_SUSPENDED"
    travel = verify_payment_and_restore_impl(state=logged_in(fx_service_status="suspended_travel"))
    assert travel["error"] == "NOT_ELIGIBLE"
    assert "router" in travel["agent_action"]


def test_agent_actions_stay_short():
    replies = [
        apply_bill_adjustment_impl("incorrect_charge", "150", "x", state=logged_in()),
        process_bill_payment_impl("", "card_on_file", state=logged_in(fx_card_on_file_status="declined")),
        verify_payment_and_restore_impl(state=logged_in(fx_service_status="suspended_nonpayment")),
    ]
    assert all(len(r["agent_action"]) <= 120 for r in replies)
