"""Tech support and appointment tools (lib/tech.py, docs/tdd.md §4)."""

from __future__ import annotations

from typing import Any

import pytest

from lib import tech
from lib.core import display_date
from lib.fakes import APPOINTMENT, FIXTURE_OUTAGE, SLOT_OFFSETS_DAYS, TICKETS, relative_date
from lib.tech import (
    check_regional_outage_impl,
    get_appointment_and_ticket_status_impl,
    manage_appointment_impl,
    run_virtual_repair_impl,
)


def _logged_in(**extra: Any) -> dict[str, Any]:
    state = {"account_id": "A1001", "phone_last4": "0186", "auth_status": "pass", "logged_in": True}
    state.update(extra)
    return state


def _walk_keys(obj: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.append(k)
            keys.extend(_walk_keys(v))
    elif isinstance(obj, list):
        for item in obj:
            keys.extend(_walk_keys(item))
    return keys


# --- check_regional_outage ---------------------------------------------------


@pytest.mark.parametrize("code", ["G2A 3B4", "g2a3b4", "J4K-5L6", "h2x oa9"])
def test_outage_quebec_region_class_is_active_without_login(code: str) -> None:
    state: dict[str, Any] = {}
    reply = check_regional_outage_impl(code, "internet", state=state)
    assert reply["status"] == "ok"
    data = reply["data"]
    assert data["region"] == "Region-A"
    assert data["outage_active"] is True
    assert "internet" in data["affected_services"]
    assert data["restoration_eta_display"]
    assert state["outage_active"] is True
    assert "outage_active" in reply["agent_action"]


def test_outage_other_region_and_zip_have_no_outage() -> None:
    ontario = check_regional_outage_impl("M5V 2T6", state={})["data"]
    assert ontario == {**ontario, "region": "Region-B", "outage_active": False, "affected_services": []}
    zip_reply = check_regional_outage_impl(30301.0, state={})
    assert zip_reply["data"]["region"] == "Region-C"
    assert zip_reply["data"]["outage_active"] is False
    assert "troubleshooting" in zip_reply["agent_action"]


def test_outage_fixture_overrides_regional_table() -> None:
    active = check_regional_outage_impl("M5V 2T6", "tv", state={"fx_outage_status": "active"})["data"]
    assert active["outage_active"] is True
    assert active["outage_id"] == FIXTURE_OUTAGE["outage_id"]
    none = check_regional_outage_impl("G2A 3B4", state={"fx_outage_status": "none"})["data"]
    assert none["outage_active"] is False


def test_outage_lob_not_affected_is_not_active() -> None:
    data = check_regional_outage_impl("G2A 3B4", "mobility", state={})["data"]
    assert data["outage_active"] is False


def test_outage_lob_aliases() -> None:
    assert check_regional_outage_impl("G2A 3B4", "Wi-Fi", state={})["data"]["outage_active"] is True
    assert check_regional_outage_impl("G2A 3B4", "télé", state={})["data"]["outage_active"] is True


def test_outage_empty_code_uses_address_on_file() -> None:
    reply = check_regional_outage_impl("", state={"account_id": "A1001"})
    assert reply["status"] == "ok"
    assert reply["data"]["used_address_on_file"] is True
    assert reply["data"]["region"] == "Region-B"


@pytest.mark.parametrize("bad", ["", "123", "D1A 1A1", "K1A 1A", "ABCDEF", "1234567"])
def test_outage_invalid_codes_are_validation_errors(bad: str) -> None:
    reply = check_regional_outage_impl(bad, state={})
    assert reply["error"] == "INVALID_INPUT"


def test_outage_three_invalid_codes_hand_over() -> None:
    state: dict[str, Any] = {}
    check_regional_outage_impl("x", state=state)
    check_regional_outage_impl("y", state=state)
    assert check_regional_outage_impl("z", state=state)["error"] == "TOO_MANY_ERRORS"


def test_outage_french_display_and_mock_error() -> None:
    fr = check_regional_outage_impl("G2A 3B4", language="fr-CA", state={})
    assert fr["data"]["restoration_eta_display"].startswith("environ")
    err = check_regional_outage_impl("G2A 3B4", state={"mock_error": "SYSTEM_DOWN"})
    assert err["error"] == "SYSTEM_UNAVAILABLE"


def test_outage_without_state_uses_fresh_dict() -> None:
    assert check_regional_outage_impl("M5V 2T6")["status"] == "ok"
    # no shared module-level state: an error count never leaks between calls
    assert check_regional_outage_impl("bad")["data"]["global_err_count"] == 1
    assert check_regional_outage_impl("bad")["data"]["global_err_count"] == 1


# --- run_virtual_repair ------------------------------------------------------


def test_repair_requires_login() -> None:
    reply = run_virtual_repair_impl("internet", "no internet", state={"account_id": "A1001"})
    assert reply["error"] == "NOT_LOGGED_IN"
    assert "sms_sent" not in {"account_id": "A1001"}


def test_repair_tv_needs_sub_type() -> None:
    state = _logged_in()
    reply = run_virtual_repair_impl("tv", "no signal", state=state)
    assert reply["error"] == "TV_SUB_TYPE_REQUIRED"
    assert "global_err_count" not in state  # a business error, not a validation strike


def test_repair_tv_sub_type_from_state_and_explicit_satellite_word() -> None:
    state = _logged_in(tv_sub_type="streaming")
    assert run_virtual_repair_impl("tv", "no signal", state=state)["data"]["tv_sub_type"] == "streaming"
    data = run_virtual_repair_impl("tv", "my satellite box shows nothing", state=_logged_in())["data"]
    assert data["tv_sub_type"] == "satellite"


@pytest.mark.parametrize("raw,expected", [
    ("Satellite", "satellite"), ("streaming only", "streaming_only"), ("app", "streaming_only"),
    ("streaming-app", "streaming_only"), ("Streaming", "streaming"), ("receiver", "streaming"),
    ("satellite dish", "satellite"),
])
def test_repair_sub_type_normalization(raw: str, expected: str) -> None:
    data = run_virtual_repair_impl("tv", "black screen", raw, state=_logged_in())["data"]
    assert data["tv_sub_type"] == expected


@pytest.mark.parametrize("code", ["Error 771", "erreur 6042", "code 88 on screen", "Error #305"])
def test_repair_satellite_error_codes_are_a_class(code: str) -> None:
    data = run_virtual_repair_impl("tv", code, "satellite", state=_logged_in())["data"]
    assert data["symptom_category"] == "tv_error_code"
    assert data["known_issue"]["issue"] == "satellite_signal_loss"
    assert data["error_code"].isdigit()
    assert data["sms_recommended"] is True


def test_repair_streaming_error_code_has_no_satellite_note() -> None:
    data = run_virtual_repair_impl("tv", "error 412", "streaming", state=_logged_in())["data"]
    assert data["symptom_category"] == "tv_error_code"
    assert data["known_issue"] is None
    assert data["remote_reset_sent"] is True
    only = run_virtual_repair_impl("tv", "error 412", "streaming_only", state=_logged_in())["data"]
    assert only["remote_reset_sent"] is False


def test_repair_streaming_app_freezing_is_not_satellite() -> None:
    data = run_virtual_repair_impl("tv", "the streaming app keeps freezing", "streaming_only", state=_logged_in())["data"]
    assert data["symptom_category"] == "tv_app_freezing"
    assert data["tv_sub_type"] == "streaming_only"
    assert data["known_issue"]["issue"] == "streaming_app_device"
    assert data["remote_reset_sent"] is False


@pytest.mark.parametrize("lob,symptom,category", [
    ("internet", "my wifi is not working", "internet_down"),
    ("internet", "internet is slow and keeps dropping", "internet_slow"),
    ("mobility", "no service on my phone", "mobile_no_service"),
    ("mobility", "mon cellulaire n'a plus de réseau", "mobile_no_service"),
    ("mobility", "data is really slow, pages won't load", "mobile_slow_data"),
    ("mobility", "invalid SIM message", "mobile_sim"),
    ("homephone", "no dial tone", "homephone_no_dial_tone"),
    ("homephone", "crackling static on the line", "homephone_noise"),
    ("smarthome", "camera is offline", "smarthome_offline"),
])
def test_repair_symptom_categories(lob: str, symptom: str, category: str) -> None:
    data = run_virtual_repair_impl(lob, symptom, state=_logged_in())["data"]
    assert data["symptom_category"] == category
    assert data["catalogue_match"] is True
    assert data["step_count"] == len(data["steps"])
    assert data["sms_recommended"] is (data["step_count"] > 2)


def test_repair_short_steps_are_verbal() -> None:
    reply = run_virtual_repair_impl("homephone", "static noise", state=_logged_in())
    assert reply["data"]["sms_recommended"] is False
    assert "Walk" in reply["agent_action"]


def test_repair_long_steps_offer_text() -> None:
    reply = run_virtual_repair_impl("internet", "internet down", state=_logged_in())
    assert reply["data"]["sms_recommended"] is True
    assert "troubleshooting_guide" in reply["agent_action"]


def test_repair_infers_lob_from_symptom() -> None:
    assert run_virtual_repair_impl("", "my modem is offline", state=_logged_in())["data"]["lob"] == "internet"
    assert run_virtual_repair_impl("", "no dial tone on my landline", state=_logged_in())["data"]["lob"] == "homephone"
    assert run_virtual_repair_impl("cellular", "no bars", state=_logged_in())["data"]["lob"] == "mobility"


def test_repair_unknown_lob_is_validation_error() -> None:
    assert run_virtual_repair_impl("", "it hums", state=_logged_in())["error"] == "INVALID_INPUT"


def test_repair_french_steps_and_generic_symptom() -> None:
    state = _logged_in(language="fr-CA")
    reply = run_virtual_repair_impl("tv", "ma télé ne fonctionne pas", "satellite", state=state)
    data = reply["data"]
    assert data["catalogue_match"] is True
    assert reply["active_language"] == "fr-CA"
    assert all("é" in s or "à" in s or "e" in s for s in data["steps"])
    assert data["steps"][0].startswith("Vérifiez")


def test_repair_french_symptom_outside_catalogue_hands_over() -> None:
    reply = run_virtual_repair_impl("tv", "la télécommande vocale parle espagnol", "streaming", language="fr-CA", state=_logged_in())
    assert reply["data"]["catalogue_match"] is False
    assert "secondary_language_live_agent" in reply["agent_action"]


def test_repair_english_symptom_outside_catalogue_gets_general_steps() -> None:
    reply = run_virtual_repair_impl("tv", "voice remote answers in spanish", "streaming", state=_logged_in())
    assert reply["data"]["catalogue_match"] is False
    assert reply["data"]["steps"]
    assert "technician" in reply["agent_action"]


def test_repair_blocked_by_active_outage_at_address_on_file() -> None:
    reply = run_virtual_repair_impl("internet", "no internet", state=_logged_in(fx_outage_status="active"))
    assert reply["error"] == "OUTAGE_ACTIVE"
    assert reply["data"]["outage_active"] is True
    ok = run_virtual_repair_impl("mobility", "no service", state=_logged_in(fx_outage_status="active"))
    assert ok["status"] == "ok"


def test_repair_is_idempotent_and_records_session() -> None:
    state = _logged_in()
    first = run_virtual_repair_impl("internet", "slow internet", state=state)
    second = run_virtual_repair_impl("internet", "slow internet", state=state)
    assert first["data"]["session_id"] == second["data"]["session_id"]
    assert state["vr_session_id"] == first["data"]["session_id"]
    assert state["lob"] == "internet"
    assert "sms_sent" not in state  # the tool never texts on its own


def test_repair_mock_error() -> None:
    assert run_virtual_repair_impl("internet", "down", state=_logged_in(mock_error="x"))["error"] == "SYSTEM_UNAVAILABLE"


# --- get_appointment_and_ticket_status --------------------------------------


def test_status_requires_login() -> None:
    assert get_appointment_and_ticket_status_impl(state={})["error"] == "NOT_LOGGED_IN"


@pytest.mark.parametrize("status", ["scheduled", "en_route", "delayed"])
def test_status_follows_fixture(status: str) -> None:
    reply = get_appointment_and_ticket_status_impl(state=_logged_in(fx_technician_status=status))
    appt = reply["data"]["appointments"][0]
    assert appt["status"] == status
    assert appt["appointment_id"] == APPOINTMENT["appointment_id"]
    assert appt["is_today"] is True
    assert appt["date_display"] == display_date(relative_date(0))
    assert appt["can_cancel"] is (status != "en_route")
    assert appt["can_reschedule"] is (status != "en_route")
    if status == "en_route":
        assert appt["technician_eta_display"].startswith("in about")
    if status == "delayed":
        assert appt["delay_minutes"] == APPOINTMENT["delay_minutes"]
        assert appt["revised_window_display"]


def test_status_unknown_fixture_value_falls_back_to_scheduled() -> None:
    reply = get_appointment_and_ticket_status_impl(state=_logged_in(fx_technician_status="teleported"))
    assert reply["data"]["appointments"][0]["status"] == "scheduled"


def test_status_bundles_three_slots_and_tickets() -> None:
    state = _logged_in()
    data = get_appointment_and_ticket_status_impl(state=state)["data"]
    slots = data["available_slots"]
    assert len(slots) == 3 == len(SLOT_OFFSETS_DAYS)
    assert [s["slot_id"] for s in slots] == ["SLOT-1", "SLOT-2", "SLOT-3"]
    assert slots[0]["date"] == relative_date(SLOT_OFFSETS_DAYS[0])
    assert "start" not in slots[0]
    assert len(data["tickets"]) == len(TICKETS)
    assert data["tickets"][0]["status_display"]
    assert state["ticket_state"] == TICKETS[0]["status"]


def test_status_french_is_localized_without_sibling_keys() -> None:
    reply = get_appointment_and_ticket_status_impl(state=_logged_in(language="fr-CA", fx_technician_status="en_route"))
    data = reply["data"]
    assert data["appointments"][0]["technician_eta_display"].startswith("dans environ")
    assert data["available_slots"][0]["window_display"].startswith("entre")
    assert data["tickets"][0]["status_display"] == "en cours de traitement"
    assert not [k for k in _walk_keys(reply) if k.endswith(("_en", "_fr"))]


def test_status_mock_error() -> None:
    assert get_appointment_and_ticket_status_impl(state=_logged_in(mock_error="1"))["error"] == "SYSTEM_UNAVAILABLE"


# --- manage_appointment -------------------------------------------------------


def test_manage_requires_login_and_valid_action() -> None:
    assert manage_appointment_impl("cancel", state={})["error"] == "NOT_LOGGED_IN"
    assert manage_appointment_impl("teleport", state=_logged_in())["error"] == "INVALID_INPUT"
    assert manage_appointment_impl("cancel", state=_logged_in(mock_error="1"))["error"] == "SYSTEM_UNAVAILABLE"


def test_reschedule_delayed_visit_then_status_reflects_it() -> None:
    state = _logged_in(fx_technician_status="delayed")
    reply = manage_appointment_impl("reschedule", slot_id="SLOT-2", state=state)
    data = reply["data"]
    assert data["rescheduled"] is True
    assert data["new_date"] == relative_date(SLOT_OFFSETS_DAYS[1])
    assert data["sms_confirmation_sent"] is True
    assert data["destination_last4"] == "0186"
    appt = get_appointment_and_ticket_status_impl(state=state)["data"]["appointments"][0]
    assert appt["status"] == "scheduled"
    assert appt["date"] == data["new_date"]
    assert appt["is_today"] is False


@pytest.mark.parametrize("slot", ["2", 2, 2.0, "slot 2", "option 2", "slot-2", relative_date(SLOT_OFFSETS_DAYS[1])])
def test_reschedule_accepts_slot_ordinals_and_dates(slot: Any) -> None:
    reply = manage_appointment_impl("reschedule", slot_id=slot, state=_logged_in())
    assert reply["data"]["slot_id"] == "SLOT-2"


@pytest.mark.parametrize("slot", ["SLOT-9", "7", "next tuesday", "2099-01-01"])
def test_reschedule_rejects_unknown_slot(slot: str) -> None:
    state = _logged_in()
    reply = manage_appointment_impl("reschedule", slot_id=slot, state=state)
    assert reply["error"] == "INVALID_INPUT"
    assert len(reply["data"]["available_slots"]) == 3
    assert "appt_state" not in state  # nothing booked silently


def test_reschedule_without_slot_returns_options() -> None:
    reply = manage_appointment_impl("reschedule", state=_logged_in())
    assert reply["status"] == "ok"
    assert reply["data"]["slot_required"] is True
    assert len(reply["data"]["available_slots"]) == 3


def test_reschedule_is_idempotent_and_texts_once() -> None:
    state = _logged_in()
    a = manage_appointment_impl("reschedule", slot_id="SLOT-1", state=state)
    b = manage_appointment_impl("reschedule", slot_id="SLOT-1", state=state)
    assert a["data"]["confirmation_id"] == b["data"]["confirmation_id"]
    assert state["sms_sent"].count("appointment_rescheduled_slot-1") == 1


def test_en_route_cannot_be_cancelled_or_moved_but_note_works() -> None:
    state = _logged_in(fx_technician_status="en_route")
    cancel = manage_appointment_impl("cancel", confirmed=True, state=state)
    assert cancel["error"] == "TECHNICIAN_EN_ROUTE"
    assert cancel["data"]["can_add_note"] is True
    assert manage_appointment_impl("reschedule", slot_id="SLOT-1", state=state)["error"] == "TECHNICIAN_EN_ROUTE"
    note = manage_appointment_impl("add_note", note="  Gate code is on the side door ", state=state)
    assert note["data"]["note_added"] is True
    assert state["appt_note"] == "Gate code is on the side door"
    assert get_appointment_and_ticket_status_impl(state=state)["data"]["appointments"][0]["note_on_file"] is True


def test_default_visit_is_en_route_and_delayed_and_can_be_moved_not_cancelled() -> None:
    """No fixture (fix 16): one status that reads as both "on the way" and "delayed"."""
    state = _logged_in()
    appt = get_appointment_and_ticket_status_impl(state=state)["data"]["appointments"][0]
    assert appt["status"] == "en_route_delayed"
    assert "on the way" in appt["status_note"] and "delayed" in appt["status_note"]
    assert appt["delay_minutes"] == APPOINTMENT["delay_minutes"]
    assert appt["technician_eta_display"] == appt["revised_window_display"] != ""
    assert appt["can_reschedule"] is True and appt["can_cancel"] is False
    cancel = manage_appointment_impl("cancel", confirmed=True, state=state)
    assert cancel["error"] == "TECHNICIAN_EN_ROUTE" and cancel["data"]["can_reschedule"] is True
    moved = manage_appointment_impl("reschedule", slot_id="SLOT-2", state=state)
    assert moved["data"]["rescheduled"] is True
    after = get_appointment_and_ticket_status_impl(state=state)["data"]["appointments"][0]
    assert after["status"] == "scheduled" and after["date"] == relative_date(SLOT_OFFSETS_DAYS[1])
    fr = get_appointment_and_ticket_status_impl(state=_logged_in(language="fr-CA"))["data"]["appointments"][0]
    assert "en route" in fr["status_note"] and "retardé" in fr["status_note"]


def test_add_note_needs_text() -> None:
    assert manage_appointment_impl("add_note", state=_logged_in())["error"] == "INVALID_INPUT"


def test_same_day_cancel_needs_two_calls() -> None:
    state = _logged_in(fx_technician_status="scheduled")
    first = manage_appointment_impl("cancel", confirmed=True, state=state)  # confirmed too early
    assert first["error"] == "CONFIRMATION_REQUIRED"
    assert first["data"]["same_day"] is True
    assert state["pending_confirmation"] == f"cancel:{APPOINTMENT['appointment_id']}"
    second = manage_appointment_impl("cancel", confirmed="true", state=state)
    assert second["data"]["cancelled"] is True
    assert second["data"]["sms_confirmation_sent"] is True
    assert state["appt_state"] == "cancelled"
    again = manage_appointment_impl("cancel", confirmed=True, state=state)
    assert again["data"]["already_cancelled"] is True
    status = get_appointment_and_ticket_status_impl(state=state)["data"]["appointments"][0]
    assert status["status"] == "cancelled"
    assert status["can_reschedule"] is False


def test_same_day_cancel_not_confirmed_stays_pending() -> None:
    state = _logged_in(fx_technician_status="scheduled")
    manage_appointment_impl("cancel", state=state)
    assert manage_appointment_impl("cancel", confirmed=False, state=state)["error"] == "CONFIRMATION_REQUIRED"
    assert state.get("appt_state") is None


def test_future_cancel_needs_one_confirmation() -> None:
    state = _logged_in()
    manage_appointment_impl("reschedule", slot_id="SLOT-3", state=state)
    ask = manage_appointment_impl("cancel", state=state)
    assert ask["error"] == "CONFIRMATION_REQUIRED"
    assert ask["data"]["same_day"] is False
    done = manage_appointment_impl("cancel", confirmed="yes", state=state)
    assert done["data"]["cancelled"] is True


def test_cancelled_visit_cannot_be_rescheduled_or_noted() -> None:
    state = _logged_in(appt_state="cancelled")
    assert manage_appointment_impl("reschedule", slot_id="SLOT-1", state=state)["error"] == "NOT_ELIGIBLE"
    assert manage_appointment_impl("add_note", note="hi", state=state)["error"] == "NOT_ELIGIBLE"


def test_book_new_visit_flow() -> None:
    state = _logged_in(lob="tv")
    options = manage_appointment_impl("book", state=state)
    assert options["data"]["slot_required"] is True
    assert manage_appointment_impl("book", slot_id="SLOT-8", state=state)["error"] == "INVALID_INPUT"
    booked = manage_appointment_impl("book", slot_id="SLOT-3", state=state)
    assert booked["data"]["booked"] is True
    assert booked["data"]["service_type"] == "tv"
    appts = get_appointment_and_ticket_status_impl(state=state)["data"]["appointments"]
    assert len(appts) == 2
    new_id = booked["data"]["appointment_id"]
    # two live visits: an unnamed change must ask which one
    assert manage_appointment_impl("cancel", state=state)["error"] == "NOT_FOUND"
    moved = manage_appointment_impl("reschedule", appointment_id=new_id, slot_id="SLOT-1", state=state)
    assert moved["data"]["slot_id"] == "SLOT-1"
    manage_appointment_impl("cancel", appointment_id=new_id, state=state)
    gone = manage_appointment_impl("cancel", appointment_id=new_id, confirmed=True, state=state)
    assert gone["data"]["cancelled"] is True
    assert state["booked_slot_id"] == ""


def test_appointment_id_by_suffix_and_unknown() -> None:
    state = _logged_in()
    digits = APPOINTMENT["appointment_id"].split("-")[-1]
    assert manage_appointment_impl("reschedule", appointment_id=digits, slot_id="1", state=state)["status"] == "ok"
    assert manage_appointment_impl("reschedule", appointment_id="APT-0000", slot_id="1", state=state)["error"] == "NOT_FOUND"


def test_helpers() -> None:
    assert tech._tech_shift("23:30", 60) == "23:59"
    assert tech._tech_minutes(25, "fr-CA") == "environ 25 minutes"
    assert tech._tech_minutes(120, "en-US") == "about 2 hours"
    assert tech._tech_parse_postal("k1a0b1") == ("postal", "K1A 0B1")
    assert tech._tech_find_slot("", "en-US") is None
    assert tech._tech_truthy("oui") is True


def test_repair_returns_first_step_in_call_language() -> None:
    for lang in ("en-US", "fr-CA"):
        data = run_virtual_repair_impl("tv", "app keeps freezing", "streaming_only", state=_logged_in(), language=lang)["data"]
        assert data["first_step"] == data["steps"][0]


def test_repair_slow_mobile_data_carries_usage_and_throttling_facts() -> None:
    data = run_virtual_repair_impl("mobility", "data is very slow", state=_logged_in())["data"]
    assert data["symptom_category"] == "mobile_slow_data"
    assert data["data_speed_reduced"] is False
    assert data["data_usage_note"] and data["throttling_note"]
    fr = run_virtual_repair_impl("mobility", "données lentes", state=_logged_in(), language="fr-CA")["data"]
    assert "Go" in fr["data_usage_note"] and fr["throttling_note"] != data["throttling_note"]
    assert "data_usage_note" not in run_virtual_repair_impl("internet", "slow", state=_logged_in())["data"]


def test_data_usage_reports_reduced_speed_over_allowance(monkeypatch) -> None:
    monkeypatch.setattr(tech, "CURRENT_DATA_USED_GB", tech.CURRENT_DATA_GB)
    assert tech._tech_data_usage("en-US")["data_speed_reduced"] is True
