"""lib/services.py: identity, login ladder, handover and SMS (docs/tdd.md §4 Shared, §6, §7)."""

import json

import pytest

import lib.services as services
from lib.fakes import ACCOUNTS, SELF_SERVE_ADJUSTMENT_LIMIT, SPOKEN_LINES, VALID_OTPS, VALID_PINS, read_count
from lib.replies import ERROR_CODES, display_amount
from lib.services import (
    ALL_TOOLS,
    HANDOVER_REASONS,
    MAX_LOGIN_ATTEMPTS,
    check_login_code_impl,
    check_secret_pin_impl,
    handover_to_person_impl,
    lookup_account_impl,
    send_login_code_impl,
    send_sms_notification_impl,
)

KNOWN_PHONE = "202 555 0186"
OTHER_PHONE = "303 555 0188"
OTP = sorted(VALID_OTPS)[0]
PIN = max(VALID_PINS)  # not the 4321 that the exact-PIN tests put on file


def identified(**extra) -> dict:
    state: dict = dict(extra)
    assert lookup_account_impl(KNOWN_PHONE, state=state)["status"] == "ok"
    return state


def logged_in(code: str = OTP, **extra) -> dict:
    state = identified(**extra)
    assert send_login_code_impl(state=state)["status"] == "ok"
    assert check_login_code_impl(code, state=state)["status"] == "ok"
    return state


# --- registry -----------------------------------------------------------------------


def test_all_tools_registry_is_complete_and_unique() -> None:
    assert len(ALL_TOOLS) == len(set(ALL_TOOLS)) == 25
    for name in ALL_TOOLS:
        assert callable(getattr(services, f"{name}_impl")), name
        assert getattr(services, name) is getattr(services, f"{name}_impl")
    assert "submit_request" not in ALL_TOOLS


# --- lookup_account -----------------------------------------------------------------


def test_lookup_known_account_returns_last4_only_and_remembers_it() -> None:
    state: dict = {}
    reply = lookup_account_impl(KNOWN_PHONE, state=state)
    assert reply["status"] == "ok"
    data = reply["data"]
    assert data["identification_status"] == "Pass"
    assert data["phone_last4"] == "0186" and data["caller_provided_phone_last4"] == "0186"
    assert data["business_flag"] is False
    assert "service_status" not in data  # account data: billing reports it after login
    assert data["region"] in ("Region-A", "Region-B", "Region-C")
    assert set(data["lines_of_business"]) >= {"mobility", "internet"}
    assert data["account_id_last4"] == ACCOUNTS[0]["account_id"][-4:]
    assert ACCOUNTS[0]["phone"] not in json.dumps(reply)
    assert state["account_id"] == ACCOUNTS[0]["account_id"] and state["identification_status"] == "Pass"
    assert state["preferred_language"] == "en-US"
    assert "agent_action" not in reply


def test_lookup_accepts_floats_and_account_ids() -> None:
    assert lookup_account_impl(2025550186.0, state={})["data"]["phone_last4"] == "0186"
    by_id = lookup_account_impl(ACCOUNTS[1]["account_id"], state={})
    assert by_id["data"]["caller_provided_phone_last4"] == ""
    assert by_id["data"]["phone_last4"] == ACCOUNTS[1]["phone"][-4:]


def test_lookup_plausible_unknown_number_gets_a_synthetic_record() -> None:
    state: dict = {}
    reply = lookup_account_impl(OTHER_PHONE, state=state)
    assert reply["status"] == "ok"
    assert reply["data"]["phone_last4"] == "0188"
    assert state["account_id"] != ACCOUNTS[0]["account_id"]


@pytest.mark.parametrize("raw", ["1234567890", "5555555555", "12345", "ACC-12", "123"])
def test_lookup_implausible_numbers_are_not_found(raw: str) -> None:
    reply = lookup_account_impl(raw, state={})
    assert reply["status"] == "error" and reply["error"] == "NOT_FOUND"


def test_lookup_validation_errors_end_in_too_many_errors() -> None:
    state: dict = {}
    assert lookup_account_impl("", state=state)["error"] == "INVALID_INPUT"
    assert lookup_account_impl("123", state=state)["error"] == "NOT_FOUND"
    third = lookup_account_impl("1234567890", state=state)
    assert third["error"] == "TOO_MANY_ERRORS"
    assert "too_many_errors" in third["agent_action"]


@pytest.mark.parametrize("raw", ["John Smith", "Miller", "123 Main Street", "Jean-François Côté"])
def test_lookup_by_name_or_address_is_not_a_strike(raw: str) -> None:
    """A name or address is not a malformed number: no strike, the lookup-options line, PIN first."""
    state: dict = {}
    for _ in range(4):
        reply = lookup_account_impl(raw, state=state)
        assert reply["error"] == "NOT_FOUND" and reply["data"]["counted"] is False
    assert read_count(state, "global_err_count") == 0 and "account_id" not in state
    assert reply["data"]["spoken_message"] == SPOKEN_LINES["account_lookup_options"]["en-US"]
    assert "check_secret_pin" in reply["agent_action"] and len(reply["agent_action"]) <= 120
    fr = lookup_account_impl(raw, state={"language": "fr-CA"})
    assert fr["data"]["spoken_message"] == SPOKEN_LINES["account_lookup_options"]["fr-CA"]


@pytest.mark.parametrize("raw", ["123", "ACC-12", "not-an-email@", "555-01"])
def test_lookup_malformed_numbers_still_count(raw: str) -> None:
    state: dict = {}
    reply = lookup_account_impl(raw, state=state)
    assert reply["error"] == "NOT_FOUND" and reply["data"]["global_err_count"] == 1
    assert reply["data"]["spoken_message"] == SPOKEN_LINES["account_lookup_options"]["en-US"]


@pytest.mark.parametrize("raw", ["900-555-0199", "+1 900 555 0199", "19005550199"])
def test_lookup_blocked_caller(raw: str) -> None:
    state: dict = {}
    reply = lookup_account_impl(raw, state=state)
    assert reply["error"] == "PERMISSION_DENIED"
    assert reply["data"]["blocked"] is True
    assert "restricted_caller" in reply["agent_action"]
    assert state["is_blocked"] is True and "account_id" not in state


def test_lookup_business_flag_comes_from_the_fixture() -> None:
    state = {"fx_business_account": "true"}
    reply = lookup_account_impl(KNOWN_PHONE, state=state)
    assert reply["data"]["business_flag"] is True
    assert state["business_flag"] is True
    assert "business_handoff" in reply["agent_action"]


def test_lookup_never_reports_a_suspension_before_login() -> None:
    """The default account is suspended for non-payment (fix 16); identification must not say so,
    so troubleshooting, sales and fraud calls never hear about it."""
    for state in ({}, {"fx_service_status": "suspended_nonpayment"}):
        reply = lookup_account_impl(KNOWN_PHONE, state=state)
        assert "suspen" not in json.dumps(reply)
        assert "service_status" not in state


def test_switching_accounts_clears_the_login_but_keeps_the_failure_count() -> None:
    state = logged_in()
    assert check_login_code_impl("444444", state=state)["status"] == "ok"  # already logged in
    lookup_account_impl(OTHER_PHONE, state=state)
    assert state["auth_status"] == "none" and state["logged_in"] is False
    assert state["step_up_verified"] is False

    state = identified()
    send_login_code_impl(state=state)
    assert check_login_code_impl("444444", state=state)["error"] == "WRONG_CODE"
    assert check_login_code_impl("444444", state=state)["error"] == "WRONG_CODE"
    lookup_account_impl(OTHER_PHONE, state=state)
    # The switch does not grant fresh attempts: the third try still locks.
    assert check_login_code_impl(OTP, state=state)["error"] == "TOO_MANY_ATTEMPTS"


def test_lockout_survives_an_account_switch() -> None:
    state = identified()
    for _ in range(MAX_LOGIN_ATTEMPTS):
        last = check_secret_pin_impl("4444", state=state)
    assert last["error"] == "TOO_MANY_ATTEMPTS" and state["auth_status"] == "locked"
    reply = lookup_account_impl(OTHER_PHONE, state=state)
    assert reply["status"] == "ok"
    assert state["auth_status"] == "locked"
    assert "auth_failure_handoff" in reply["agent_action"]
    assert check_login_code_impl(OTP, state=state)["error"] == "TOO_MANY_ATTEMPTS"
    assert check_secret_pin_impl(PIN, state=state)["error"] == "TOO_MANY_ATTEMPTS"
    assert send_login_code_impl(state=state)["error"] == "TOO_MANY_ATTEMPTS"


# --- send_login_code ----------------------------------------------------------------


def test_send_login_code_by_sms_never_returns_the_code() -> None:
    state = identified()
    reply = send_login_code_impl(state=state)
    assert reply["status"] == "ok"
    data = reply["data"]
    assert data["sent"] is True and data["channel"] == "sms" and data["purpose"] == "login"
    assert data["destination_last4"] == "0186" and data["expires_in_sec"] > 0
    assert state["auth_status"] == "code_sent"
    assert not any(code in json.dumps(reply) for code in VALID_OTPS)


def test_send_login_code_without_lookup_uses_the_default_account() -> None:
    state: dict = {}
    assert send_login_code_impl(state=state)["status"] == "ok"
    assert state["account_id"] == ACCOUNTS[0]["account_id"]


def test_send_login_code_email_and_step_up() -> None:
    state = identified()
    email = send_login_code_impl(channel="email", state=state)
    assert email["data"]["channel"] == "email" and email["data"]["purpose"] == "login"
    assert email["data"]["email_masked"].startswith("m***@")
    assert "destination_last4" not in email["data"]

    state = logged_in()
    already = send_login_code_impl(channel="sms", state=state)
    assert already["data"] == {"sent": False, "already_verified": True}
    step_up = send_login_code_impl(channel="Email", state=state)
    assert step_up["data"]["purpose"] == "step_up"
    assert state["auth_status"] == "pass" and state["code_purpose"] == "step_up"


# --- check_login_code / check_secret_pin (docs/tdd.md §6) ----------------------------


def test_login_ladder_first_try_accepts_any_well_formed_code() -> None:
    state = identified()
    send_login_code_impl(state=state)
    reply = check_login_code_impl("314159", state=state)
    assert reply["status"] == "ok" and reply["logged_in"] is True
    assert state["auth_status"] == "pass" and state["logged_in"] is True


def test_login_ladder_second_try_accepts_only_known_codes_third_always_fails() -> None:
    state = identified()
    first = check_login_code_impl("444444", state=state)  # weak: always fails
    assert first["error"] == "WRONG_CODE" and first["data"]["attempts_remaining"] == 2
    assert check_login_code_impl("314159", state=state)["error"] == "WRONG_CODE"
    third = check_login_code_impl(OTP, state=state)
    assert third["error"] == "TOO_MANY_ATTEMPTS"
    assert third["lockout_triggered"] is True
    assert "auth_failure_handoff" in third["agent_action"]
    assert state["auth_status"] == "locked"

    state = identified()
    check_login_code_impl("444444", state=state)
    ok = check_login_code_impl(OTP, state=state)
    assert ok["status"] == "ok"
    assert state["auth_failure_count"] == 0


@pytest.mark.parametrize("weak_code,weak_pin", [("111111", "1111"), ("000000", "0000"), ("777777", "7777")])
def test_weak_codes_always_fail(weak_code: str, weak_pin: str) -> None:
    assert check_login_code_impl(weak_code, state=identified())["error"] == "WRONG_CODE"
    assert check_secret_pin_impl(weak_pin, state=identified())["error"] == "WRONG_PIN"


def test_exact_otp_on_file_overrides_the_ladder_on_any_attempt() -> None:
    state = identified(fx_otp_on_file="804627")
    assert check_login_code_impl("314159", state=state)["error"] == "WRONG_CODE"
    assert check_login_code_impl(OTP, state=state)["error"] == "WRONG_CODE"  # even a ladder-valid code
    assert check_login_code_impl("804 627", state=state)["status"] == "ok"  # third try, exact value


def test_exact_pin_on_file_overrides_the_ladder() -> None:
    state = identified(fx_pin_on_file="4321")
    wrong = check_secret_pin_impl(PIN, state=state)
    assert wrong["error"] == "WRONG_PIN" and wrong["data"]["attempts_remaining"] == 2
    assert state["pin_failure_count"] == 1
    assert check_secret_pin_impl(4321, state=state)["status"] == "ok"
    assert state["auth_status"] == "pass"


def test_codes_and_pins_share_one_failure_counter() -> None:
    state = identified(fx_pin_on_file="4321")
    assert check_login_code_impl("123456", state=state)["error"] == "WRONG_CODE"
    assert check_secret_pin_impl("1234", state=state)["error"] == "WRONG_PIN"
    assert check_secret_pin_impl("4321", state=state)["status"] == "ok"
    state = identified(fx_pin_on_file="4321")
    check_login_code_impl("123456", state=state)
    check_secret_pin_impl("1234", state=state)
    assert check_secret_pin_impl("5678", state=state)["error"] == "TOO_MANY_ATTEMPTS"


def test_malformed_codes_are_validation_errors_not_login_failures() -> None:
    state = identified()
    reply = check_login_code_impl("12", state=state)
    assert reply["error"] == "INVALID_INPUT"
    assert state.get("auth_failure_count", 0) == 0
    assert check_secret_pin_impl("", state=state)["error"] == "INVALID_INPUT"
    assert check_secret_pin_impl("123456789", state=state)["error"] == "TOO_MANY_ERRORS"


def test_keypad_digits_are_read_when_the_argument_is_empty() -> None:
    state = identified(dtmf_digits="5903", fx_pin_on_file="5903")
    assert check_secret_pin_impl("", state=state)["status"] == "ok"
    state = identified(dtmf_digits="804627.0", fx_otp_on_file="804627")
    assert check_login_code_impl(None, state=state)["status"] == "ok"


def test_already_logged_in_short_circuits() -> None:
    state = logged_in()
    state["logged_in"] = False
    assert check_secret_pin_impl("4444", state=state)["status"] == "ok"
    assert state["logged_in"] is True


def test_step_up_email_code_sets_step_up_verified() -> None:
    state = logged_in("804627", fx_otp_on_file="804627")
    send_login_code_impl(channel="email", state=state)
    wrong = check_login_code_impl("111222", state=state)
    assert wrong["error"] == "WRONG_CODE"
    assert state["auth_status"] == "pass"  # a failed step-up keeps the login
    ok = check_login_code_impl("804627", state=state)
    assert ok["status"] == "ok" and ok["data"]["step_up_verified"] is True
    assert state["step_up_verified"] is True and state["code_purpose"] == "login"


def test_login_tools_mock_error() -> None:
    for fn, arg in ((check_login_code_impl, OTP), (check_secret_pin_impl, PIN), (send_login_code_impl, "sms"), (lookup_account_impl, KNOWN_PHONE)):
        reply = fn(arg, state={"mock_error": "SYSTEM_DOWN"})
        assert reply["error"] == "SYSTEM_UNAVAILABLE"


# --- handover_to_person (docs/tdd.md §7) --------------------------------------------


@pytest.mark.parametrize(
    "raw, code",
    [
        ("fraud_escalation", "fraud_escalation"),
        ("Fraud-Escalation", "fraud_escalation"),
        ("my account was hacked", "fraud_escalation"),
        ("compte piraté", "fraud_escalation"),
        ("business account", "business_handoff"),
        ("compte d'affaires", "business_handoff"),
        ("refund over the threshold", "refund_threshold_exceeded"),
        ("too many errors", "too_many_errors"),
        ("caller locked out of verification", "auth_failure_handoff"),
        ("system down", "system_unavailable"),
        ("silence", "no_input_escalation"),
        ("secondary_language_live_agent", "secondary_language_live_agent"),
        ("talk to a human", "user_requested_agent"),
        ("", "user_requested_agent"),
    ],
)
def test_handover_reason_normalization(raw: str, code: str) -> None:
    reply = handover_to_person_impl(reason=raw, state={}, language="en-US")
    assert reply["data"]["reason"] == code


EXPECTED_LINES = {
    "fraud_escalation": ("empathy_protocol", "live_agent_handoff"),
    "business_handoff": ("business_handoff",),
    "refund_threshold_exceeded": ("refund_over_limit", "transfer_to_specialist"),
}


@pytest.mark.parametrize("lang", ["en-US", "fr-CA"])
@pytest.mark.parametrize("reason", HANDOVER_REASONS)
def test_handover_speaks_the_verbatim_line_for_each_reason(reason: str, lang: str) -> None:
    state: dict = {}
    reply = handover_to_person_impl(reason=reason, summary="s", state=state, language=lang)
    keys = EXPECTED_LINES.get(reason, ("live_agent_handoff",))
    limit = display_amount(SELF_SERVE_ADJUSTMENT_LIMIT)
    expected = " ".join(SPOKEN_LINES[k][lang].replace("[limit]", limit) for k in keys)
    assert reply["status"] == "ok"
    assert reply["data"]["handoff_message"] == expected == reply["handoff_message"]
    assert state["handoff_message"] == expected
    assert state["handover_complete"] is True and state["handoff_reason"] == reason
    assert reply["data"]["language"] == lang and state["language"] == lang


def test_fraud_is_empathy_then_live_agent_and_always_open() -> None:
    reply = handover_to_person_impl(reason="fraud_escalation", state={}, language="en-US")
    msg = reply["data"]["handoff_message"]
    assert msg.startswith(SPOKEN_LINES["empathy_protocol"]["en-US"])
    assert msg.endswith(SPOKEN_LINES["live_agent_handoff"]["en-US"])
    assert reply["data"]["queue"] == "fraud" and reply["data"]["queue_open"] is True
    assert reply["data"]["handoff_status"] == "completed_via_specialist_queue"


@pytest.mark.parametrize("lang", ["en-US", "fr-CA"])
def test_refund_threshold_handover_says_why_then_the_verbatim_transfer_line(lang: str) -> None:
    msg = handover_to_person_impl(reason="refund_threshold_exceeded", state={}, language=lang)["handoff_message"]
    reason_line = SPOKEN_LINES["refund_over_limit"][lang]
    assert "[limit]" in reason_line
    assert msg.startswith(reason_line.replace("[limit]", display_amount(SELF_SERVE_ADJUSTMENT_LIMIT)))
    assert msg.endswith(SPOKEN_LINES["transfer_to_specialist"][lang]) and "[" not in msg


def test_handover_writes_handoff_context_json() -> None:
    state = logged_in(fx_business_account="true")
    state["applied_adjustments"] = "CR-1"
    handover_to_person_impl(reason="business_handoff", summary="  Wants   to pay\n a bill ", state=state)
    ctx = json.loads(state["handoff_context"])
    assert ctx["reason"] == "business_handoff"
    assert ctx["summary"] == "Wants to pay a bill"
    assert ctx["account_id_last4"] == ACCOUNTS[0]["account_id"][-4:]
    assert ctx["identification_status"] == "Pass" and ctx["auth_status"] == "pass"
    assert ctx["business_flag"] is True and ctx["applied_adjustments"] == "CR-1"
    assert ctx["language"] == "en-US" and ctx["last_tracking_id"]
    guest: dict = {}
    handover_to_person_impl(reason="fraud", summary="x" * 500, state=guest)
    gctx = json.loads(guest["handoff_context"])
    assert gctx["identification_status"] == "Fail" and gctx["auth_status"] == "none"
    assert len(gctx["summary"]) == 300


def test_handover_specialist_queue_after_hours_is_a_callback(monkeypatch) -> None:
    monkeypatch.setattr(services, "queue_open", lambda queue: False)
    closed = handover_to_person_impl(reason="refund_threshold_exceeded", state={})
    assert closed["data"]["queue"] == "billing_specialist"
    assert closed["data"]["handoff_status"] == "callback_next_business_day"
    monkeypatch.setattr(services, "queue_open", lambda queue: True)
    assert handover_to_person_impl(reason="refund_threshold_exceeded", state={})["data"]["handoff_status"] == (
        "completed_via_specialist_queue"
    )


def test_handover_language_turn_one_french_and_lock() -> None:
    # Turn 1 in French, before any language is stored: the reason/summary words decide.
    state: dict = {}
    reply = handover_to_person_impl(reason="user_requested_agent", summary="Je veux parler à un représentant", state=state)
    assert reply["data"]["language"] == "fr-CA"
    assert reply["data"]["handoff_message"] == SPOKEN_LINES["live_agent_handoff"]["fr-CA"]
    assert state["language"] == "fr-CA"
    # The caller's own words in state count too.
    st2 = {"utterance": "Bonjour, je veux un agent"}
    assert handover_to_person_impl(reason="agent", state=st2)["data"]["language"] == "fr-CA"
    # A French call stays French even when the model passes en-US.
    st3 = {"language": "fr-CA"}
    assert handover_to_person_impl(reason="agent", language="en-US", state=st3)["data"]["language"] == "fr-CA"
    # An English call with an explicit fr-CA argument switches.
    st4 = {"language": "en-US"}
    assert handover_to_person_impl(reason="agent", language="fr-CA", state=st4)["data"]["language"] == "fr-CA"
    # English call, nothing French: stays English; profile language is the last resort.
    assert handover_to_person_impl(reason="agent", summary="wants a person", state={"language": "en-US"})["data"]["language"] == "en-US"
    assert handover_to_person_impl(reason="agent", summary="wants a person", state={"preferred_language": "fr-CA"})["data"]["language"] == "fr-CA"
    assert handover_to_person_impl(reason="agent", summary="wants a person", state={})["data"]["language"] == "en-US"


def test_handover_mock_error_except_system_unavailable() -> None:
    err = handover_to_person_impl(reason="user_requested_agent", state={"mock_error": "SYSTEM_DOWN"})
    assert err["error"] == "SYSTEM_UNAVAILABLE"
    state = {"mock_error": "SYSTEM_DOWN"}
    ok = handover_to_person_impl(reason="system_unavailable", state=state)
    assert ok["status"] == "ok" and state["handover_complete"] is True


# --- send_sms_notification ----------------------------------------------------------


def test_send_sms_notification() -> None:
    state = identified()
    reply = send_sms_notification_impl("Outage Updates", state=state)
    assert reply["status"] == "ok"
    assert reply["data"]["purpose"] == "outage_updates" and reply["data"]["destination_last4"] == "0186"
    assert reply["data"]["sms_sent"] is True and state["sms_sent"] == "outage_updates"
    assert send_sms_notification_impl("coupon", state=state)["error"] == "INVALID_INPUT"
    assert send_sms_notification_impl("troubleshooting_guide", state={})["error"] == "NOT_IDENTIFIED"
    assert send_sms_notification_impl("outage_updates", state={"mock_error": "x"})["error"] == "SYSTEM_UNAVAILABLE"


def test_every_error_code_used_here_is_documented() -> None:
    src = open(services.__file__, encoding="utf-8").read()
    import re

    for code in set(re.findall(r'"([A-Z][A-Z_]{4,})"', src)):
        if code in ("MAX_LOGIN_ATTEMPTS",):
            continue
        if code.isupper() and "_" in code:
            assert code in ERROR_CODES, code


def test_code_and_pin_formats_are_enforced_and_routed() -> None:
    state: dict = {}
    lookup_account_impl("514-555-0199", state=state)
    bad = check_login_code_impl("12345", state=state)
    assert bad["error"] == "INVALID_INPUT" and read_count(state, "auth_failure_count") == 0
    assert check_secret_pin_impl("123", state=state)["error"] == "INVALID_INPUT"
    # A 4-digit PIN given to the code tool is checked as a PIN.
    assert check_login_code_impl("2468", state=state)["status"] == "ok" and state["auth_status"] == "pass"


def test_texted_code_given_to_the_pin_tool_is_checked_as_a_code() -> None:
    state: dict = {}
    lookup_account_impl("514-555-0199", state=state)
    send_login_code_impl(state=state)
    assert check_secret_pin_impl("482913", state=state)["status"] == "ok"


def test_login_prompts_carry_their_verbatim_lines() -> None:
    """The judge only sees tool replies, so spoken login lines travel in them (cluster C1)."""
    from lib.billing import get_billing_summary_impl

    state: dict = {}
    lookup_account_impl("514-555-0199", state=state)
    gate = get_billing_summary_impl(state=state)
    assert gate["error"] == "NOT_LOGGED_IN"
    assert gate["data"]["spoken_message"].startswith(SPOKEN_LINES["otp_callback_confirm"]["en-US"].split("[")[0])
    assert gate["data"]["pin_prompt_message"] == SPOKEN_LINES["id_verification_pin"]["en-US"]
    sent = send_login_code_impl(state=state)
    assert sent["data"]["spoken_message"] == SPOKEN_LINES["id_verification_otp"]["en-US"]
    fr: dict = {"language": "fr-CA"}
    lookup_account_impl("514-555-0199", state=fr)
    assert send_login_code_impl(state=fr)["data"]["spoken_message"] == SPOKEN_LINES["id_verification_otp"]["fr-CA"]
# --- callers without a number, codes that can't arrive (C2, C3, C10) ------------------


def test_lookup_by_email_identifies_the_default_account() -> None:
    """A caller with no phone or account number gives their email (DESIGN_RULES rules 2, 21)."""
    state: dict = {}
    reply = lookup_account_impl("j.miller_personal@example.com", state=state)
    assert reply["status"] == "ok"
    assert state["account_id"] == ACCOUNTS[0]["account_id"] and state["identification_status"] == "Pass"
    assert reply["data"]["phone_last4"] == ACCOUNTS[0]["phone"][-4:]
    assert reply["data"]["caller_provided_phone_last4"] == ""
    by_email = lookup_account_impl(ACCOUNTS[1]["email"].upper(), state={})
    assert by_email["data"]["account_id_last4"] == ACCOUNTS[1]["account_id"][-4:]
    assert lookup_account_impl("not-an-email@", state={})["error"] == "NOT_FOUND"


def test_texted_code_goes_to_a_number_built_from_the_callers_account_digits() -> None:
    state: dict = {}
    assert lookup_account_impl("882940012", state=state)["data"]["phone_last4"] == "0012"
    assert send_login_code_impl(state=state)["data"]["destination_last4"] == "0012"
    assert lookup_account_impl("ACC-992834", state={})["data"]["phone_last4"] == "2834"


def test_email_login_code_tells_the_agent_what_to_say() -> None:
    """Code Can't Arrive: the login code goes to the email on file when a text can't."""
    state: dict = {}
    reply = send_login_code_impl(channel="email", state=state)
    assert reply["data"]["purpose"] == "login" and reply["data"]["channel"] == "email"
    assert "email" in reply["agent_action"] and "6-digit" in reply["agent_action"]
    assert "agent_action" not in send_login_code_impl(channel="sms", state={})
    assert check_login_code_impl("482913", state=state)["status"] == "ok" and state["auth_status"] == "pass"


@pytest.mark.parametrize("tool", [check_login_code_impl, check_secret_pin_impl])
def test_short_step_up_code_is_a_re_ask_with_a_resend_offer_not_a_strike(tool) -> None:
    state = logged_in()
    send_login_code_impl(channel="email", state=state)
    before = read_count(state, "global_err_count")
    reply = tool("7731", state=state)
    assert reply["error"] == "INVALID_INPUT"
    assert "email" in reply["agent_action"] and "resend" in reply["agent_action"]
    assert read_count(state, "auth_failure_count") == 0 and state["auth_status"] == "pass"
    assert read_count(state, "global_err_count") == before + 1
    assert state["code_purpose"] == "step_up"


def test_suspended_default_leaves_unrelated_journeys_unchanged() -> None:
    """Fix 16: the default account is suspended for non-payment, but only the billing tools
    report it. Troubleshooting, outages, appointments, sales, warranty, porting, MFA,
    password reset, cancellation, contact updates, texts and handovers neither refuse
    nor mention it."""
    calls = [
        lambda st: services.check_regional_outage_impl("K1A 0B1", "internet", state=st),
        lambda st: services.run_virtual_repair_impl("internet", "internet is slow", state=st),
        lambda st: services.run_virtual_repair_impl("mobility", "no service on my phone", state=st),
        lambda st: services.get_appointment_and_ticket_status_impl(state=st),
        lambda st: services.manage_appointment_impl("reschedule", slot_id="SLOT-2", state=st),
        lambda st: services.browse_plans_impl("mobility", "", "more data", state=st),
        lambda st: services.file_warranty_claim_impl("phone", "screen flickers", "no", "no", state=st),
        lambda st: services.start_number_transfer_impl(state=st),
        lambda st: services.manage_mfa_impl("enable", state=st),
        lambda st: services.send_password_reset_link_impl(state=st),
        lambda st: services.cancel_or_port_out_service_impl("tv", "cancel", "moving", False, state=st),
        lambda st: services.update_contact_profile_impl("email", "new.name@mailprovider.example", state=st),
        lambda st: services.send_sms_notification_impl("troubleshooting_guide", state=st),
        lambda st: services.handover_to_person_impl("fraud_escalation", "caller reports a SIM swap", state=st),
    ]
    for call in calls:
        state = logged_in()
        reply = call(state)
        text = json.dumps(reply, ensure_ascii=False).lower()
        assert reply["status"] == "ok" or reply.get("error") == "CONFIRMATION_REQUIRED", reply
        assert not any(w in text for w in ("suspended", "nonpayment", "non_payment", "past due", "past_due")), reply


def test_default_ladder_wrong_then_scenario_pin_on_the_second_try() -> None:
    """Fix 16: without fx_pin_on_file, a wrong first PIN then the scenario-stated PIN logs in."""
    state = identified()
    assert check_secret_pin_impl("9999", state=state)["error"] == "WRONG_PIN"
    assert check_secret_pin_impl("4321", state=state)["status"] == "ok"
    assert state["auth_status"] == "pass"
    other = identified()
    check_secret_pin_impl("9999", state=other)
    assert check_secret_pin_impl("4322", state=other)["error"] == "WRONG_PIN"  # any other PIN still fails
