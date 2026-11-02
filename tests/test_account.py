"""lib/account.py: the account management tools (docs/tdd.md §4 Account, PRD §14)."""

from __future__ import annotations

from typing import Any

import pytest

from lib.account import (
    _acct_lob,
    cancel_or_port_out_service_impl,
    execute_suspend_restore_impl,
    manage_mfa_impl,
    send_password_reset_link_impl,
    update_contact_profile_impl,
)
from lib.fakes import (
    ACCT_CONTRACT_TERMS,
    PASSWORD_RESET_VALID_MINUTES,
    SPOKEN_LINES,
    relative_date,
)
from lib.services import (
    check_login_code_impl,
    check_secret_pin_impl,
    lookup_account_impl,
    send_login_code_impl,
)


def _identified(**extra: Any) -> dict[str, Any]:
    state: dict[str, Any] = {}
    lookup_account_impl("613 555 0147", state=state)
    state.update(extra)
    return state


def _logged_in(**extra: Any) -> dict[str, Any]:
    state = _identified()
    assert check_secret_pin_impl("5903", state=state)["status"] == "ok"
    state.update(extra)
    return state


def _walk(obj: Any) -> list[str]:
    """Every key and string value in a reply, for leak checks."""
    out: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append(str(k))
            out.extend(_walk(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_walk(v))
    else:
        out.append(str(obj))
    return out


# --- send_password_reset_link -------------------------------------------------


def test_password_reset_needs_identification_not_login() -> None:
    reply = send_password_reset_link_impl(state={})
    assert reply["error"] == "NOT_IDENTIFIED"
    assert "lookup_account" in reply["agent_action"]
    assert len(reply["agent_action"]) <= 120

    state = _identified()
    assert state.get("auth_status") in (None, "", "none")
    ok = send_password_reset_link_impl(state=state)
    assert ok["status"] == "ok"
    assert ok["data"]["sent"] is True
    assert ok["data"]["destination_last4"] == "0147"
    assert ok["data"]["valid_minutes"] == PASSWORD_RESET_VALID_MINUTES
    assert not any("http" in s or "://" in s for s in _walk(ok))
    assert "password_reset" in state["sms_sent"]


def test_password_reset_goes_to_number_on_file_not_caller_typed() -> None:
    state = {}
    lookup_account_impl("202 555 0186", state=state)
    state["caller_provided_phone_last4"] = "9999"
    reply = send_password_reset_link_impl(state=state)
    assert reply["data"]["destination_last4"] == "0186"


def test_password_reset_requires_pass_identification_status() -> None:
    reply = send_password_reset_link_impl(state={"account_id": "A1001", "identification_status": "Fail"})
    assert reply["error"] == "NOT_IDENTIFIED"


def test_password_reset_resend_ok_when_delivered() -> None:
    state = _identified()
    send_password_reset_link_impl(state=state)
    again = send_password_reset_link_impl(state=state)
    assert again["status"] == "ok"
    assert again["data"]["resend"] is True
    assert state["password_reset_count"] == 2


def test_password_reset_failed_delivery_on_resend() -> None:
    state = _identified(fx_sms_delivery="failed")
    first = send_password_reset_link_impl(state=state)
    assert first["status"] == "ok"
    second = send_password_reset_link_impl(state=state)
    assert second["error"] == "DELIVERY_FAILED"
    assert "sms_delivery_failed" in second["agent_action"]
    assert second["data"]["sent"] is False


def test_password_reset_counter_reads_platform_decimals() -> None:
    state = _identified(password_reset_count=1.0, fx_sms_delivery="failed")
    assert send_password_reset_link_impl(state=state)["error"] == "DELIVERY_FAILED"


def test_password_reset_french_summary() -> None:
    state = _identified(language="fr-CA")
    reply = send_password_reset_link_impl(state=state, language="en-US")
    assert reply["active_language"] == "fr-CA"
    assert "lien de réinitialisation" in reply["data"]["spoken_summary"]
    assert not any(k.endswith(("_en", "_fr")) for k in reply["data"])


def test_password_reset_mock_error() -> None:
    state = _identified(mock_error="SYSTEM_DOWN")
    assert send_password_reset_link_impl(state=state)["error"] == "SYSTEM_UNAVAILABLE"


# --- manage_mfa ---------------------------------------------------------------


def test_mfa_requires_login() -> None:
    assert manage_mfa_impl("enable", state=_identified())["error"] == "NOT_LOGGED_IN"


def test_mfa_enable_from_default_off() -> None:
    state = _logged_in()
    reply = manage_mfa_impl("enable", state=state)
    assert reply["status"] == "ok"
    assert reply["data"]["mfa_enabled"] is True
    assert reply["data"]["method"] == "sms"
    assert reply["data"]["destination_last4"] == "0147"
    assert reply["data"]["effective_date"] == relative_date(0)
    assert state["mfa_state"] == "enabled"
    again = manage_mfa_impl("turn on", state=state)
    assert again["error"] == "ALREADY_APPLIED"
    assert again["data"]["mfa_enabled"] is True


def test_mfa_enable_when_fixture_says_on() -> None:
    state = _logged_in(fx_mfa_enabled="true")
    assert manage_mfa_impl("enable", state=state)["error"] == "ALREADY_APPLIED"


def test_mfa_disable_when_already_off() -> None:
    state = _logged_in()
    reply = manage_mfa_impl("disable", state=state)
    assert reply["error"] == "ALREADY_APPLIED"
    assert reply["data"]["mfa_enabled"] is False


def test_mfa_disable_needs_email_step_up_then_applies_once() -> None:
    state = _logged_in(fx_mfa_enabled="true")
    first = manage_mfa_impl("disable", state=state)
    assert first["error"] == "STEP_UP_REQUIRED"
    assert "email" in first["agent_action"]
    assert len(first["agent_action"]) <= 120
    assert state.get("mfa_state", "") == ""

    sent = send_login_code_impl("email", state=state)
    assert sent["data"]["purpose"] == "step_up"
    checked = check_login_code_impl("372615", state=state)
    assert checked["data"]["step_up_verified"] is True

    done = manage_mfa_impl("disable", state=state)
    assert done["status"] == "ok"
    assert done["data"]["mfa_enabled"] is False
    assert done["data"]["method"] == "none"
    assert state["mfa_state"] == "disabled"
    assert state["step_up_verified"] is False  # single use

    # Turning it back on needs no step-up; turning it off again needs a new one.
    assert manage_mfa_impl("enable", state=state)["status"] == "ok"
    assert manage_mfa_impl("disable", state=state)["error"] == "STEP_UP_REQUIRED"


def test_mfa_login_alone_is_not_a_step_up() -> None:
    state = _logged_in(fx_mfa_enabled="true", step_up_verified=False)
    assert manage_mfa_impl("off", state=state)["error"] == "STEP_UP_REQUIRED"


def test_mfa_invalid_action_counts_validation_error() -> None:
    state = _logged_in()
    reply = manage_mfa_impl("maybe", state=state)
    assert reply["error"] == "INVALID_INPUT"
    assert state["global_err_count"] == 1


def test_mfa_french_summary() -> None:
    state = _logged_in(language="fr-CA")
    reply = manage_mfa_impl("activer", state=state)
    assert reply["status"] == "ok"
    assert "activée" in reply["data"]["spoken_summary"]


def test_mfa_mock_error() -> None:
    assert manage_mfa_impl("enable", state=_logged_in(mock_error="x"))["error"] == "SYSTEM_UNAVAILABLE"


# --- execute_suspend_restore --------------------------------------------------


def test_suspend_requires_login() -> None:
    assert execute_suspend_restore_impl("suspend", "lost_stolen", state=_identified())["error"] == "NOT_LOGGED_IN"


def test_lost_stolen_suspends_immediately_and_confirms_by_email() -> None:
    state = _logged_in()
    reply = execute_suspend_restore_impl("suspend", "my phone was stolen", state=state)
    assert reply["status"] == "ok"
    data = reply["data"]
    assert data["new_state"] == "suspended"
    assert data["reason"] == "lost_stolen"
    assert data["immediate"] is True
    assert data["effective_date"] == relative_date(0)
    assert data["sms_confirmation_sent"] is False
    assert data["email_confirmation_sent"] is True
    assert state["service_status"] == "suspended_lost_stolen"


def test_travel_suspend_then_restore() -> None:
    state = _logged_in()
    reply = execute_suspend_restore_impl("suspend", "travel", state=state)
    assert reply["data"]["sms_confirmation_sent"] is True
    assert state["service_status"] == "suspended_travel"
    again = execute_suspend_restore_impl("suspend", "vacation", state=state)
    assert again["error"] == "ALREADY_APPLIED"
    restored = execute_suspend_restore_impl("restore", "", state=state)
    assert restored["status"] == "ok"
    assert restored["data"]["previous_state"] == "suspended_travel"
    assert restored["data"]["new_state"] == "active"
    assert state["service_status"] == "active"


def test_restore_from_fixture_lost_stolen() -> None:
    state = _logged_in(fx_service_status="suspended_lost_stolen")
    state["service_status"] = ""
    assert execute_suspend_restore_impl("reactivate", state=state)["data"]["new_state"] == "active"


def test_restore_non_payment_goes_to_billing() -> None:
    state = _logged_in(fx_service_status="suspended_nonpayment")
    state["service_status"] = ""
    reply = execute_suspend_restore_impl("restore", "", state=state)
    assert reply["error"] == "NOT_ELIGIBLE"
    assert "router" in reply["agent_action"] and "billing" in reply["agent_action"]
    assert len(reply["agent_action"]) <= 120
    assert state["service_status"] == ""


def test_suspend_over_non_payment_never_masks_it() -> None:
    state = _logged_in()
    state["service_status"] = "suspended_nonpayment"
    reply = execute_suspend_restore_impl("suspend", "lost_stolen", state=state)
    assert reply["error"] == "ALREADY_APPLIED"
    assert "billing" in reply["agent_action"]
    assert state["service_status"] == "suspended_nonpayment"


def test_restore_active_line() -> None:
    assert execute_suspend_restore_impl("restore", state=_logged_in())["error"] == "NOT_SUSPENDED"


@pytest.mark.parametrize("action,reason", [("freeze", "travel"), ("suspend", "")])
def test_suspend_validation(action: str, reason: str) -> None:
    assert execute_suspend_restore_impl(action, reason, state=_logged_in())["error"] == "INVALID_INPUT"


def test_suspend_french_and_mock_error() -> None:
    state = _logged_in(language="fr-CA")
    reply = execute_suspend_restore_impl("suspendre", "perdu", state=state)
    assert "suspendue" in reply["data"]["spoken_summary"]
    assert execute_suspend_restore_impl("suspend", "travel", state=_logged_in(mock_error="x"))["error"] == "SYSTEM_UNAVAILABLE"


# --- cancel_or_port_out_service -----------------------------------------------


def test_cancel_requires_login() -> None:
    assert cancel_or_port_out_service_impl("internet", state=_identified())["error"] == "NOT_LOGGED_IN"


def test_cancel_two_step_confirmation() -> None:
    state = _logged_in()
    quote = cancel_or_port_out_service_impl("internet", "cancel", "moving abroad", False, state=state)
    assert quote["error"] == "CONFIRMATION_REQUIRED"
    assert "contract_cancellation_fee_disclosure" in quote["agent_action"]
    assert len(quote["agent_action"]) <= 120
    data = quote["data"]
    assert data["lob"] == "internet"
    assert data["early_termination_fee_display"] == ACCT_CONTRACT_TERMS["internet"]["early_termination_fee"]
    assert data["final_bill_estimate_display"]
    assert data["effective_date_display"]
    assert data["currency"] == "CAD"
    assert "cancellation_id" not in data
    assert state.get("cancelled_services", "") == ""

    done = cancel_or_port_out_service_impl("home internet", "cancel", "moving abroad", True, state=state)
    assert done["status"] == "ok"
    assert done["data"]["cancellation_id"].startswith("CX")
    assert done["data"]["transfer_authorization_sent_by_sms"] is False
    assert done["data"]["equipment_return_days"] > 0
    assert "internet" not in done["data"]["remaining_lines_of_business"]
    assert state["cancelled_services"] == "internet:cancel"
    assert state["pending_confirmation"] == ""

    again = cancel_or_port_out_service_impl("internet", "cancel", "", True, state=state)
    assert again["status"] == "ok"
    assert again["data"]["already_submitted"] is True
    assert again["data"]["cancellation_id"] == done["data"]["cancellation_id"]
    assert state["cancelled_services"] == "internet:cancel"


def test_confirmed_true_without_a_quote_still_quotes_first() -> None:
    state = _logged_in()
    reply = cancel_or_port_out_service_impl("tv", "cancel", "", "true", state=state)
    assert reply["error"] == "CONFIRMATION_REQUIRED"
    assert cancel_or_port_out_service_impl("tv", "cancel", "", "yes", state=state)["status"] == "ok"


def test_quote_for_one_service_does_not_confirm_another() -> None:
    state = _logged_in()
    cancel_or_port_out_service_impl("tv", state=state)
    assert cancel_or_port_out_service_impl("internet", confirmed=True, state=state)["error"] == "CONFIRMATION_REQUIRED"


def test_cancel_reason_never_triggers_a_hidden_retention_branch() -> None:
    state = _logged_in()
    cancel_or_port_out_service_impl("mobility", "cancel", "I never got my credit, I want to stay elsewhere", state=state)
    done = cancel_or_port_out_service_impl("mobility", "cancel", "I never got my credit", True, state=state)
    assert done["status"] == "ok"
    assert done["data"]["submitted"] is True
    assert "retention" not in " ".join(_walk(done)).lower()
    assert state["cancelled_services"] == "mobility:cancel"


def test_port_out_texts_authorization_and_never_returns_a_pin() -> None:
    state = _logged_in()
    quote = cancel_or_port_out_service_impl("mobile", "port_out", "switching carrier", False, state=state)
    assert quote["error"] == "CONFIRMATION_REQUIRED"
    assert quote["data"]["mode"] == "port_out"
    done = cancel_or_port_out_service_impl("mobility", "port out", "", True, state=state)
    assert done["status"] == "ok"
    assert done["data"]["transfer_authorization_sent_by_sms"] is True
    assert done["data"]["effective_date"] == relative_date(1)
    for reply in (quote, done):
        joined = " ".join(_walk(reply)).lower()
        assert "pin" not in joined.replace("spinning", "")
    assert "port_out_authorization" in state["sms_sent"]


def test_port_out_only_for_phone_numbers() -> None:
    reply = cancel_or_port_out_service_impl("internet", "port_out", state=_logged_in())
    assert reply["error"] == "NOT_ELIGIBLE"


def test_cancel_service_not_on_account() -> None:
    state = {}
    lookup_account_impl("202 555 0198", state=state)  # account without TV
    check_secret_pin_impl("5903", state=state)
    reply = cancel_or_port_out_service_impl("tv", state=state)
    assert reply["error"] == "NOT_ELIGIBLE"
    assert "tv" not in reply["data"]["lines_of_business"]


@pytest.mark.parametrize("lob,mode", [("", "cancel"), ("streaming dog", "cancel"), ("internet", "pause")])
def test_cancel_validation(lob: str, mode: str) -> None:
    state = _logged_in()
    assert cancel_or_port_out_service_impl(lob, mode, state=state)["error"] == "INVALID_INPUT"


def test_cancel_french_and_zero_fee() -> None:
    state = _logged_in(language="fr-CA")
    quote = cancel_or_port_out_service_impl("ligne résidentielle", state=state)
    assert quote["data"]["lob"] == "homephone"
    assert quote["data"]["early_termination_fee_display"] == "0.00"
    assert quote["data"]["final_bill_includes_fee"] is False
    done = cancel_or_port_out_service_impl("homephone", confirmed=True, state=state)
    assert "confirmée" in done["data"]["spoken_summary"]
    assert "contract_cancellation_fee_disclosure" in SPOKEN_LINES


def test_cancel_mock_error() -> None:
    assert cancel_or_port_out_service_impl("tv", state=_logged_in(mock_error="x"))["error"] == "SYSTEM_UNAVAILABLE"


@pytest.mark.parametrize(
    "text,lob",
    [
        ("mobile phone plan", "mobility"),
        ("Fibe TV", "tv"),
        ("téléphone résidentiel", "homephone"),
        ("landline", "homephone"),
        ("home internet", "internet"),
        ("wireless", "mobility"),
        ("", ""),
    ],
)
def test_lob_words(text: str, lob: str) -> None:
    assert _acct_lob(text) == lob


# --- update_contact_profile ---------------------------------------------------


def test_update_requires_login() -> None:
    assert update_contact_profile_impl("email", "x@y.example", state=_identified())["error"] == "NOT_LOGGED_IN"


def test_update_email_masks_value() -> None:
    state = _logged_in()
    reply = update_contact_profile_impl("email", "Sam.Rivera@Example.org", state=state)
    assert reply["status"] == "ok"
    assert reply["data"]["field"] == "email"
    assert reply["data"]["new_value_masked"] == "s***@example.org"
    assert "sam.rivera" not in " ".join(_walk(reply)).lower()
    again = update_contact_profile_impl("courriel", "sam.rivera@example.org", state=state)
    assert again["error"] == "ALREADY_APPLIED"


def test_update_mobile_and_address() -> None:
    state = _logged_in()
    mob = update_contact_profile_impl("phone", "+1 (613) 555-0172", state=state)
    assert mob["data"]["field"] == "mobile_number"
    assert mob["data"]["new_value_masked"] == "***-***-0172"
    addr = update_contact_profile_impl("address", "88 Elm Street, Kingston, ON K7L 3N6", state=state)
    assert addr["data"]["field"] == "mailing_address"
    assert addr["data"]["new_value_masked"] == "***, Kingston, ON K7L 3N6"
    assert "88 Elm" not in str(addr)


def test_update_to_current_value_is_already_applied() -> None:
    state = {}
    lookup_account_impl("202 555 0186", state=state)
    check_secret_pin_impl("5903", state=state)
    assert update_contact_profile_impl("mobile_number", "2025550186", state=state)["error"] == "ALREADY_APPLIED"


@pytest.mark.parametrize(
    "field,value",
    [
        ("email", "not-an-email"),
        ("mobile_number", "12345"),
        ("mailing_address", "nowhere"),
        ("favourite_colour", "blue"),
    ],
)
def test_update_validation(field: str, value: str) -> None:
    assert update_contact_profile_impl(field, value, state=_logged_in())["error"] == "INVALID_INPUT"


def test_update_three_bad_entries_end_in_too_many_errors() -> None:
    state = _logged_in()
    update_contact_profile_impl("email", "bad", state=state)
    update_contact_profile_impl("email", "bad", state=state)
    assert update_contact_profile_impl("email", "bad", state=state)["error"] == "TOO_MANY_ERRORS"


def test_update_french_and_mock_error() -> None:
    state = _logged_in(language="fr-CA")
    reply = update_contact_profile_impl("mobile", "613-555-0163", state=state)
    assert "mis à jour" in reply["data"]["spoken_summary"]
    addr = update_contact_profile_impl("adresse", "12 Rue Laurier Gatineau", state=state)
    assert addr["data"]["new_value_masked"] == "***, Gatineau"
    assert update_contact_profile_impl("email", "a@b.example", state=_logged_in(mock_error="x"))["error"] == "SYSTEM_UNAVAILABLE"


def test_no_shared_default_state_between_calls() -> None:
    first = manage_mfa_impl("enable")
    second = manage_mfa_impl("enable")
    assert first["error"] == second["error"] == "NOT_LOGGED_IN"
    assert send_password_reset_link_impl()["error"] == "NOT_IDENTIFIED"


@pytest.mark.parametrize("lang", ["en-US", "fr-CA"])
def test_cancel_quote_and_confirmation_say_other_services_and_final_bill(lang: str) -> None:
    state = _logged_in(language=lang)
    quote = cancel_or_port_out_service_impl("homephone", "cancel", state=state, language=lang)
    assert quote["error"] == "CONFIRMATION_REQUIRED"
    assert quote["data"]["other_services_note"] and quote["data"]["final_bill_note"]
    done = cancel_or_port_out_service_impl("homephone", "cancel", confirmed=True, state=state, language=lang)
    assert done["data"]["other_services_note"] == quote["data"]["other_services_note"]
    assert done["data"]["final_bill_note"]


def test_mfa_enable_says_what_to_do_if_the_phone_is_lost() -> None:
    on = manage_mfa_impl("enable", state=_logged_in())
    assert "PIN" in on["data"]["lost_phone_note"]
    fr = manage_mfa_impl("enable", state=_logged_in(), language="fr-CA")
    assert "NIP" in fr["data"]["lost_phone_note"]


def test_mfa_step_up_falls_back_to_a_text_when_email_is_unavailable() -> None:
    """Step-up needs a second factor beyond the login; a text to the mobile on file counts."""
    from lib.services import check_login_code_impl, check_secret_pin_impl, lookup_account_impl, send_login_code_impl

    state: dict = {"fx_mfa_enabled": "true"}
    lookup_account_impl("514-555-0199", state=state)
    check_secret_pin_impl("2468", state=state)
    first = manage_mfa_impl(action="disable", state=state)
    assert first["error"] == "STEP_UP_REQUIRED" and first["data"]["step_up_fallback_channel"] == "sms"
    sent = send_login_code_impl(channel="sms", state=state)
    assert sent["data"]["sent"] is True and sent["data"]["purpose"] == "step_up"
    assert check_login_code_impl("482913", state=state)["data"]["step_up_verified"] is True
    assert manage_mfa_impl(action="disable", state=state)["status"] == "ok"
