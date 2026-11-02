"""lib/core.py: shared helpers every tool uses (docs/tdd.md §2)."""

from datetime import datetime
from decimal import Decimal

from lib import core
from lib.fakes import ACCOUNTS, FIXTURE_DEFAULTS, SPOKEN_LINES


def test_get_state_prefers_state_then_session_state_then_fresh_dict() -> None:
    a, b = {"x": 1}, {"y": 2}
    assert core.get_state(a, b) is a
    assert core.get_state(None, b) is b
    first, second = core.get_state(), core.get_state()
    assert first == {} and first is not second


def test_session_language_asymmetric_lock() -> None:
    state: dict = {}
    assert core.session_language(state, "") == "en-US"
    assert "language" not in state
    assert core.session_language(state, "en") == "en-US" and state["language"] == "en-US"
    # French upgrades an English call and locks it ...
    assert core.session_language(state, "fr") == "fr-CA" and state["language"] == "fr-CA"
    # ... and later English or empty values from the model never downgrade it.
    assert core.session_language(state, "en-US") == "fr-CA"
    assert core.session_language(state, "") == "fr-CA"
    assert state["language"] == "fr-CA"
    # An English call stays English when no language is passed.
    assert core.session_language({"language": "en-US"}, "") == "en-US"
    # Unsupported languages fall back to English; non-dict state is tolerated.
    assert core.session_language({}, "es-US") == "en-US"
    assert core.session_language(None, "fr-CA") == "fr-CA"
    assert core.session_language(None) == "en-US"


def test_fixture_reads_override_else_default() -> None:
    assert core.fixture({}, "fx_card_on_file_status") == FIXTURE_DEFAULTS["fx_card_on_file_status"]
    assert core.fixture(None, "fx_service_status") == "active"
    assert core.fixture({"fx_service_status": " Suspended_NonPayment "}, "fx_service_status") == "suspended_nonpayment"
    assert core.fixture({"fx_service_status": ""}, "fx_service_status") == "active"
    # Credentials and free-text fixtures keep their case.
    assert core.fixture({"fx_extra_bill_line": "Internet Overcharge|15.00|internet"}, "fx_extra_bill_line") == (
        "Internet Overcharge|15.00|internet"
    )
    assert core.fixture({"fx_pin_on_file": " 4321 "}, "fx_pin_on_file") == "4321"
    assert core.fixture({}, "fx_unknown") == ""
    assert core.fixture_flag({"fx_business_account": "TRUE"}, "fx_business_account") is True
    assert core.fixture_flag({"fx_business_account": "yes"}, "fx_business_account") is True
    assert core.fixture_flag({}, "fx_business_account") is False


def test_mock_mode_and_mock_error() -> None:
    assert core.mock_mode_on({"mock_mode": "True"}) is True
    assert core.mock_mode_on({"mock_mode": ""}) is False
    assert core.mock_mode_on(None) is False
    assert core.check_mock_error({}, "en-US", "x") is None
    state = {"mock_error": "SYSTEM_DOWN", "account_id": "A1001"}
    err = core.check_mock_error(state, "fr-CA", "lookup_account")
    assert err is not None
    assert err["error"] == "SYSTEM_UNAVAILABLE"
    assert err["agent_action"] == "Hand over with reason system_unavailable."
    assert err["active_language"] == "fr-CA"
    assert state["last_tracking_id"] == err["tracking_id"]
    assert "SYSTEM_UNAVAILABLE" in core.SYSTEM_ERROR_CODES


def test_require_login() -> None:
    assert core.require_login({"auth_status": "pass"}, "en-US", "t") is None
    assert core.require_login({"auth_status": "pass", "logged_in": True}, "en-US", "t") is None
    for state in ({}, {"auth_status": "code_sent"}, {"auth_status": "pass", "logged_in": False}, {"auth_status": "locked"}):
        err = core.require_login(state, "en-US", "get_billing_summary")
        assert err is not None and err["error"] == "NOT_LOGGED_IN"
        assert len(err["agent_action"]) <= 120


def test_require_login_without_an_account_says_how_to_find_it() -> None:
    """No number yet: a verbatim line (never an improvised method) and a PIN already given comes first."""
    for lang in ("en-US", "fr-CA"):
        err = core.require_login({}, lang, "start_number_transfer")
        assert err["data"]["spoken_message"] == SPOKEN_LINES["account_lookup_options"][lang]
        assert err["data"]["pin_length"] == 4 and "pin_prompt_message" not in err["data"]
        assert err["agent_action"].startswith("If the caller already gave a 4-digit PIN, call check_secret_pin")
    found = core.require_login({"account_id": ACCOUNTS[0]["account_id"], "phone_last4": "0186"}, "en-US", "t")
    assert "0186" in found["data"]["spoken_message"] and "pin_prompt_message" in found["data"]


def test_validation_error_third_one_is_too_many_errors() -> None:
    state: dict = {}
    first = core.validation_error(state, "bad", "Ask again.", "R1", "en-US", data={"field": "amount"})
    assert first["error"] == "INVALID_INPUT"
    assert first["data"] == {"field": "amount", "global_err_count": 1}
    second = core.validation_error(state, "bad", "Ask again.", "R1", "en-US", code="NOT_FOUND")
    assert second["error"] == "NOT_FOUND" and second["data"]["global_err_count"] == 2
    third = core.validation_error(state, "bad", "Ask again.", "R1", "en-US")
    assert third["error"] == "TOO_MANY_ERRORS"
    assert third["agent_action"] == "Hand over with reason too_many_errors."
    assert state["global_err_count"] == 3
    # The platform hands counters back as decimals.
    assert core.validation_error({"global_err_count": 2.0}, "x", "y", "R", "en-US")["error"] == "TOO_MANY_ERRORS"


def test_to_decimal_and_money() -> None:
    assert core.to_decimal("$85.5") == Decimal("85.50")
    assert core.to_decimal("85,50") == Decimal("85.50")
    assert core.to_decimal("1,085.50") == Decimal("1085.50")
    assert core.to_decimal("12 CAD") == Decimal("12.00")
    assert core.to_decimal(2.675) == Decimal("2.68")
    for bad in (None, True, "", "abc", "nan", "inf"):
        assert core.to_decimal(bad) is None
    assert core.money("15") == {"amount": 15.0, "amount_display": "15.00", "currency": "CAD"}
    assert core.money("junk", prefix="balance") == {"balance": 0.0, "balance_display": "0.00", "currency": "CAD"}


def test_display_date_and_window_in_both_languages() -> None:
    assert core.display_date("2026-03-03", "en-US") == "Tuesday, March 3"
    assert core.display_date("2026-03-03", "fr-CA") == "mardi 3 mars"
    assert core.display_date("2026-03-03T10:00:00", "fr") == "mardi 3 mars"
    assert core.display_date("not a date") == "not a date"
    assert core.display_window("13:00", "17:00") == "1 PM to 5 PM"
    assert core.display_window("08:30", "12:00", "en-US") == "8:30 AM to 12 PM"
    assert core.display_window("00:00", "12:15", "en-US") == "12 AM to 12:15 PM"
    assert core.display_window("13:00", "17:30", "fr-CA") == "entre 13 h et 17 h 30"
    d = core.date_in(2, "en-US")
    assert len(d["date"]) == 10 and d["date_display"] == core.display_date(d["date"], "en-US")


def test_account_record_ensure_account_and_service_status() -> None:
    assert core.account_record({"account_id": ACCOUNTS[1]["account_id"]})["phone"] == ACCOUNTS[1]["phone"]
    synthetic = core.account_record({"account_id": "A303555"})
    assert synthetic["account_id"] == "A303555" and synthetic["phone"] == ACCOUNTS[0]["phone"]
    assert core.account_record({})["account_id"] == ACCOUNTS[0]["account_id"]
    state: dict = {}
    assert core.ensure_account(state) == ACCOUNTS[0]["account_id"]
    assert state["phone_last4"] == ACCOUNTS[0]["phone"][-4:] and state["identification_status"] == "Pass"
    assert core.ensure_account({"account_id": "A2"}) == "A2"
    assert core.service_status({}) == "active"
    assert core.service_status({"fx_service_status": "suspended_nonpayment"}) == "suspended_nonpayment"
    assert core.service_status({"service_status": "active", "fx_service_status": "suspended_nonpayment"}) == "active"


def test_dispatch_sms_and_append_list() -> None:
    state = {"phone_last4": "0199"}
    out = core.dispatch_sms(state, "outage_updates")
    assert out == {"sms_sent": True, "destination_last4": "0199", "sms_purpose": "outage_updates"}
    for i in range(12):
        core.dispatch_sms(state, f"p{i}")
    assert len(state["sms_sent"].split(",")) == 10
    assert core.dispatch_sms({}, "x")["destination_last4"] == ACCOUNTS[0]["phone"][-4:]
    st: dict = {}
    assert core.append_list(st, "applied_adjustments", "a") == ["a"]
    assert core.append_list(st, "applied_adjustments", "a") == ["a"]
    assert core.append_list(st, "applied_adjustments", "b") == ["a", "b"]
    assert st["applied_adjustments"] == "a,b"


def test_queue_open_follows_queue_hours() -> None:
    monday_10 = datetime(2026, 3, 2, 10, 0)
    monday_21 = datetime(2026, 3, 2, 21, 0)
    saturday_10 = datetime(2026, 3, 7, 10, 0)
    saturday_18 = datetime(2026, 3, 7, 18, 0)
    sunday_12 = datetime(2026, 3, 8, 12, 0)
    assert core.queue_open("billing_specialist", monday_10) is True
    assert core.queue_open("billing_specialist", monday_21) is False
    assert core.queue_open("sales", saturday_10) is True
    assert core.queue_open("sales", saturday_18) is False
    assert core.queue_open("appointments", sunday_12) is False
    for queue in ("fraud", "outage", "general"):
        assert core.queue_open(queue, sunday_12) is True
    assert isinstance(core.queue_open("sales"), bool)
