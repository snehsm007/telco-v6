"""lib/sales.py: browse_plans, place_order, file_warranty_claim, start_number_transfer (docs/tdd.md §4)."""

from __future__ import annotations

import ast
from pathlib import Path
import re
from typing import Any

import pytest

from lib import sales
from lib.fakes import DEVICE_WARRANTY_DAYS, DEVICES_ON_FILE, PLANS, SALES_COPY, SERVICE_PRICES
from lib.sales import (
    _sales_bool,
    _sales_business_date,
    _sales_find_plan,
    _sales_lob,
    _sales_speed_display,
    browse_plans_impl,
    file_warranty_claim_impl,
    place_order_impl,
    start_number_transfer_impl,
)

SIBLING = re.compile(r"_(en|fr)$")


def _identified(**extra: Any) -> dict[str, Any]:
    state: dict[str, Any] = {"account_id": "A1001", "phone_last4": "0186", "region": "Region-B"}
    state.update(extra)
    return state


def _logged_in(**extra: Any) -> dict[str, Any]:
    return _identified(auth_status="pass", logged_in=True, **extra)


def _keys(obj: Any) -> list[str]:
    out: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append(str(k))
            out.extend(_keys(v))
    elif isinstance(obj, list):
        for item in obj:
            out.extend(_keys(item))
    return out


# ----------------------------------------------------------------------------- helpers


def test_helpers() -> None:
    assert _sales_lob("Mobile plan") == "mobility"
    assert _sales_lob("", "faster home internet") == "internet"
    assert _sales_lob("télé") == "tv"
    assert _sales_lob("home phone") == "homephone"
    assert _sales_lob("") == ""
    assert _sales_bool(True) is True
    assert _sales_bool("oui") is True
    assert _sales_bool("non") is False
    assert _sales_bool("") is None
    assert _sales_find_plan("mob 50")["plan_id"] == "MOB-50"
    assert _sales_find_plan("Plus 50")["plan_id"] == "MOB-50"
    assert _sales_find_plan("") is None
    assert _sales_speed_display(500, "fr-CA") == "500 Mbit/s"
    assert _sales_speed_display(3000, "en-US") == "3 Gbps"
    assert _sales_business_date(0) <= _sales_business_date(3)


def test_sales_copy_has_both_locales() -> None:
    for key, table in SALES_COPY.items():
        assert set(table) == {"en-US", "fr-CA"}, key


def test_no_module_level_mutable_state_or_eval_literals() -> None:
    """Defect (5) in telco-v5: shared module state. lib/sales.py keeps state only in the session dict."""
    tree = ast.parse(Path(sales.__file__).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            assert not isinstance(value, (ast.Dict, ast.List, ast.Set)), ast.dump(node)[:80]


# ----------------------------------------------------------------------------- browse_plans


def test_browse_needs_no_login_and_caps_at_three() -> None:
    reply = browse_plans_impl("mobility", state={})
    assert reply["status"] == "ok"
    assert len(reply["data"]["plans"]) == 3
    assert reply["data"]["coverage_checked"] is False
    assert reply["data"]["coverage_note"]
    assert reply["data"]["plans"][0]["price_change"] == "new_service"


def test_browse_budget_is_inclusive_and_shows_difference() -> None:
    reply = browse_plans_impl("mobile", budget="$58 a month", need="budget", state=_identified())
    plans = reply["data"]["plans"]
    assert plans and all(p["price"] <= 58 for p in plans)
    assert "MOB-50" in [p["plan_id"] for p in plans]
    current = reply["data"]["current_plan"]
    assert current["price_display"] == SERVICE_PRICES["mobility"]
    assert all(p["price_difference_display"] for p in plans)
    assert reply["data"]["budget_display"] == "58.00"
    assert reply["data"]["no_plan_within_budget"] is False


def test_browse_capacity_need_keeps_bigger_tiers_sorted_by_price() -> None:
    reply = browse_plans_impl("mobility", need="more high-speed data", state=_identified())
    prices = [p["price"] for p in reply["data"]["plans"]]
    assert prices == sorted(prices)
    assert reply["data"]["plans"][-1]["plan_id"] == "MOB-UNL"
    assert reply["data"]["after_data_cap"]


def test_browse_budget_with_no_match() -> None:
    reply = browse_plans_impl("internet", budget=20, state=_identified())
    assert reply["data"]["plans"] == []
    assert reply["data"]["no_plan_within_budget"] is True
    assert reply["data"]["lowest_available_price_display"]


def test_browse_internet_upgrades_only_and_respects_coverage() -> None:
    reply = browse_plans_impl("internet", need="work from home", state=_identified(region="Region-A"), language="fr-CA")
    ids = [p["plan_id"] for p in reply["data"]["plans"]]
    assert "INT-8G" not in ids and ids
    assert reply["data"]["max_speed_display"] == "3 Gbit/s"
    assert "Téléchargement" in reply["data"]["plans"][0]["key_features"][0]
    assert reply["data"]["gateway_delivery_eta_display"]
    assert reply["active_language"] == "fr-CA"


def test_browse_tv_puts_requested_pack_first_with_combined_total() -> None:
    reply = browse_plans_impl("tv", need="sports", state=_identified())
    first = reply["data"]["plans"][0]
    assert first["plan_id"] == "TV-SPORTS" and first["is_addon"] is True
    sports = next(p for p in PLANS if p["plan_id"] == "TV-SPORTS")
    expected = float(SERVICE_PRICES["tv"]) + float(sports["price"])
    assert first["new_monthly_total"] == pytest.approx(expected)


def test_browse_tv_without_tv_service() -> None:
    reply = browse_plans_impl("tv", need="sports", state=_identified(account_id="A1002"))
    assert reply["data"]["tv_service_required_for_addons"] is True


def test_browse_region_from_account_when_state_has_none() -> None:
    state = {"account_id": "A1001"}
    reply = browse_plans_impl("internet", state=state)
    assert reply["data"]["coverage_checked"] is True


def test_browse_validation_and_mock_error() -> None:
    state: dict[str, Any] = {}
    assert browse_plans_impl("boats", state=state)["error"] == "INVALID_INPUT"
    assert browse_plans_impl("mobility", budget="0", state=state)["error"] == "INVALID_INPUT"
    assert browse_plans_impl("mobility", state={"mock_error": "x"})["error"] == "SYSTEM_UNAVAILABLE"


def test_browse_reply_has_no_sibling_language_keys() -> None:
    reply = browse_plans_impl("mobility", state=_identified(), language="fr-CA")
    assert not [k for k in _keys(reply) if SIBLING.search(k)]


# ----------------------------------------------------------------------------- place_order


def test_place_order_two_step_and_idempotent() -> None:
    state = _logged_in()
    direct = place_order_impl("MOB-100", True, state=state)
    assert direct["error"] == "CONFIRMATION_REQUIRED", "a yes without a read quote still gets the quote"
    assert direct["data"]["effective_date_display"]
    assert len(direct["agent_action"]) <= 120
    placed = place_order_impl("MOB-100", "true", state=state)
    assert placed["status"] == "ok"
    data = placed["data"]
    assert data["order_id"].startswith("ORD-")
    assert data["new_monthly_total_display"] == "72.00"
    assert data["sms_receipt_sent"] is True and data["sms_destination_last4"] == "0186"
    assert state["pending_confirmation"] == ""
    again = place_order_impl("MOB-100", True, state=state)
    assert again["data"]["order_id"] == data["order_id"]
    assert again["data"]["already_placed"] is True
    assert state["sms_sent"].count("order_receipt") == 1


def test_place_order_internet_has_delivery_eta() -> None:
    state = _logged_in()
    quote = place_order_impl("INT-1G", False, state=state)
    assert quote["data"]["delivery_eta_display"]
    assert quote["data"]["order_placed"] is False


def test_place_order_rules() -> None:
    assert place_order_impl("MOB-50", True, state=_identified())["error"] == "NOT_LOGGED_IN"
    bad = place_order_impl("GOLD-1", state=_logged_in())
    assert bad["error"] == "INVALID_INPUT" and "MOB-50" in bad["data"]["valid_plan_ids"]
    addon = place_order_impl("TV-SPORTS", state=_logged_in(account_id="A1002"))
    assert addon["error"] == "NOT_ELIGIBLE"
    too_fast = place_order_impl("INT-8G", state=_logged_in(region="Region-C"))
    assert too_fast["error"] == "NOT_ELIGIBLE" and too_fast["data"]["max_speed_display"]
    assert place_order_impl("MOB-50", state={"mock_error": "x"})["error"] == "SYSTEM_UNAVAILABLE"


def test_place_order_three_bad_ids_hand_over() -> None:
    state = _logged_in()
    for _ in range(2):
        place_order_impl("NOPE", state=state)
    assert place_order_impl("NOPE", state=state)["error"] == "TOO_MANY_ERRORS"


# ----------------------------------------------------------------------------- file_warranty_claim


def test_warranty_matches_device_and_reports_dates() -> None:
    state = _logged_in()
    check = file_warranty_claim_impl("Samsung", "ne charge plus", state=state, language="fr-CA")
    data = check["data"]
    assert data["device_model"].startswith("Samsung") and data["device_matched"] is True
    assert data["in_warranty"] is True and data["claim_filed"] is False
    assert data["missing"] == ["physical_damage", "water_damage"]
    assert re.search(r"[a-zé]+ \d+ [a-zéû]+", data["warranty_end_display"])
    assert len(check["agent_action"]) <= 120


def test_warranty_falls_back_to_most_recent_device() -> None:
    reply = file_warranty_claim_impl("my phone", "screen flickers", False, False, state=_logged_in())
    newest = min(DEVICES_ON_FILE, key=lambda d: d["purchased_days_ago"])
    assert reply["data"]["device_model"] == newest["model"]
    assert reply["data"]["device_matched"] is False
    assert reply["data"]["claim_filed"] is True


def test_warranty_claim_filed_once() -> None:
    state = _logged_in()
    first = file_warranty_claim_impl("iPhone", "screen flickering", "no", "no", state=state)
    data = first["data"]
    assert data["claim_id"].startswith("WC-") and data["shipping"] == "standard"
    assert data["shipping_address_last_line"]
    assert data["return_instructions"] and data["return_by_display"]
    second = file_warranty_claim_impl("iPhone", "screen flickering", "no", "no", state=state)
    assert second["data"]["claim_id"] == data["claim_id"] and second["data"]["already_filed"] is True
    assert state["sms_sent"].count("warranty_claim") == 1


def test_warranty_damage_and_out_of_warranty_not_eligible() -> None:
    physical = file_warranty_claim_impl("Pixel", "cracked", True, False, state=_logged_in())
    assert physical["error"] == "NOT_ELIGIBLE" and physical["data"]["not_covered_reason"] == "physical_damage"
    assert physical["data"]["repair_fee_display"]
    old = file_warranty_claim_impl("Pixel", "mic dead", state=_logged_in(fx_device_warranty="out_of_warranty"))
    assert old["error"] == "NOT_ELIGIBLE" and old["data"]["in_warranty"] is False
    assert old["data"]["not_covered_reason"] == "out_of_warranty"
    assert DEVICE_WARRANTY_DAYS < 10_000


def test_warranty_needs_fault_and_login() -> None:
    assert file_warranty_claim_impl("Pixel", "", False, False, state=_logged_in())["error"] == "INVALID_INPUT"
    assert file_warranty_claim_impl("Pixel", "mic", state=_identified())["error"] == "NOT_LOGGED_IN"
    assert file_warranty_claim_impl("Pixel", "mic", state={"mock_error": "x"})["error"] == "SYSTEM_UNAVAILABLE"


def test_swollen_battery_requires_login_then_files_urgent_claim() -> None:
    """Defect (1) in telco-v5: the safety path skipped login. Here it gives advice, then still verifies."""
    guest = file_warranty_claim_impl("", "la batterie est gonflée", state={"language": "fr-CA"})
    assert guest["error"] == "NOT_LOGGED_IN"
    assert guest["data"]["urgent"] is True and "claim_id" not in guest["data"]
    assert guest["data"]["safety_advice"] == SALES_COPY["battery_safety"]["fr-CA"]
    state = _logged_in(language="fr-CA")
    claim = file_warranty_claim_impl("", "la batterie est gonflée", state=state)
    data = claim["data"]
    assert claim["status"] == "ok" and data["urgent"] is True and data["shipping"] == "expedited"
    assert data["safety_advice_key"] == "battery_safety"
    assert data["return_instructions"] == SALES_COPY["return_urgent"]["fr-CA"]
    assert "return_by_display" not in data


def test_urgent_claim_ignores_damage_answers() -> None:
    reply = file_warranty_claim_impl("iPhone", "phone is smoking", True, True, state=_logged_in())
    assert reply["status"] == "ok" and reply["data"]["urgent"] is True


# ----------------------------------------------------------------------------- start_number_transfer


@pytest.mark.parametrize("placeholder", ["", "unknown", "external", None])
def test_transfer_checklist_without_login(placeholder: Any) -> None:
    """Rule 34 / decision A3: the checklist is public and carries no account data or PIN."""
    reply = start_number_transfer_impl(placeholder, state={})
    data = reply["data"]
    assert reply["status"] == "ok" and data["status"] == "pending_details"
    assert len(data["required_port_checklist"]) == 5
    assert not [k for k in _keys(reply) if "pin" in k.lower() and k != "required_port_checklist"]
    assert "contract_disclosure" not in str(reply)


def test_transfer_pending_until_provider_account_given() -> None:
    state = _logged_in()
    pending = start_number_transfer_impl("(416) 555-0123", "Bell", "", "", "new line", state=state)
    data = pending["data"]
    assert data["status"] == "pending_details" and data["missing_details"] == ["current_account_number"]
    assert data["current_provider"] == "Bell", "a provider name never means port-out"
    assert "transfer_id" not in data
    assert len(pending["agent_action"]) <= 120


def test_transfer_new_line_submitted_once_without_pin_echo() -> None:
    state = _logged_in()
    reply = start_number_transfer_impl("416.555.0123", "Other Mobile", "AC-55120", "73519", "add my daughter", state=state)
    data = reply["data"]
    assert data["status"] == "submitted" and data["target"] == "new_line"
    assert data["transfer_id"].startswith("PT-") and data["sms_updates"] is True
    assert re.fullmatch(r"\d{4}", data["temporary_number_last4"]) and data["temporary_number_last4"] != "0123"
    assert data["current_account_number_last4"] == "5120"
    assert data["transfer_pin_received"] is True
    assert "73519" not in str(reply)
    again = start_number_transfer_impl("4165550123", "Other Mobile", "AC-55120", "73519", "new_line", state=state)
    assert again["data"]["transfer_id"] == data["transfer_id"] and again["data"]["already_submitted"] is True


def test_transfer_onto_existing_line_number() -> None:
    reply = start_number_transfer_impl("5145550142", "Old Carrier", 991122334.0, "", "613-555-0177", state=_logged_in())
    data = reply["data"]
    assert data["target"] == "existing_line" and data["target_line_last4"] == "0177"
    assert data["current_account_number_last4"] == "2334"
    assert "temporary_number_last4" not in data


def test_transfer_landline_to_mobile_takes_longer_in_french() -> None:
    reply = start_number_transfer_impl(
        "819 555 0166", "Fournisseur local", "445566", "", "ligne fixe vers mobile", state=_logged_in(), language="fr-CA"
    )
    data = reply["data"]
    assert data["number_type"] == "landline" and data["target"] == "existing_line"
    assert data["estimated_completion_date"] >= _sales_business_date(0)
    assert data["line_note"] == SALES_COPY["port_existing_line"]["fr-CA"]


def test_transfer_validation() -> None:
    state = _logged_in()
    assert start_number_transfer_impl("555-0123", state=state)["error"] == "INVALID_INPUT"
    assert start_number_transfer_impl("4165550123", "X", "12", state={**_logged_in()})["error"] == "INVALID_INPUT"
    assert start_number_transfer_impl("4165550123", "X", "123456", "12", state=_logged_in())["error"] == "INVALID_INPUT"
    assert start_number_transfer_impl("4165550123", state=_identified())["error"] == "NOT_LOGGED_IN"
    assert start_number_transfer_impl("4165550123", state={"mock_error": "x"})["error"] == "SYSTEM_UNAVAILABLE"


# ----------------------------------------------------------------------------- follow-up facts (DEF C5 / C11)


@pytest.mark.parametrize("lang", ["en-US", "fr-CA"])
def test_browse_internet_plans_carry_upload_symmetry_and_latency(lang: str) -> None:
    reply = browse_plans_impl("internet", need="work from home video calls", state=_identified(), language=lang)
    plans = reply["data"]["plans"]
    assert plans
    for plan in plans:
        assert plan["upload_speed_display"] == plan["speed_display"]
        assert plan["symmetric"] is True
        assert plan["latency_note"]
    assert ("Gbit/s" in plans[0]["upload_speed_display"]) == (lang == "fr-CA")
    assert not [k for k in _keys(reply) if SIBLING.search(k)]


def test_browse_tv_addons_carry_channel_examples_and_hd() -> None:
    en = browse_plans_impl("tv", need="sports", state=_identified())["data"]["plans"][0]
    fr = browse_plans_impl("tv", need="sports", state=_identified(), language="fr-CA")["data"]["plans"][0]
    assert en["plan_id"] == "TV-SPORTS" and en["hd_included"] is True
    assert len(en["channel_examples"]) >= 3
    assert len(fr["channel_examples"]) == len(en["channel_examples"]) and fr["channel_examples"] != en["channel_examples"]


def test_place_order_mobility_quote_has_unambiguous_new_line_price() -> None:
    quote = place_order_impl("MOB-20", False, state=_logged_in())["data"]
    plan_price = float(next(p for p in PLANS if p["plan_id"] == "MOB-20")["price"])
    account_total = sum(float(v) for v in SERVICE_PRICES.values())
    assert quote["new_line_monthly_price"] == pytest.approx(plan_price)
    assert quote["new_line_account_monthly_total"] == pytest.approx(account_total + plan_price)
    assert quote["new_line_pricing_note"]
    assert "new_line_monthly_price" not in place_order_impl("INT-1G", False, state=_logged_in())["data"]


def test_warranty_unknown_named_model_is_not_swapped_for_a_device_on_file() -> None:
    state = _logged_in()
    reply = file_warranty_claim_impl("Orbit Z9 Max", "screen flickers", False, False, state=state)
    data = reply["data"]
    assert data["device_model"] == "Orbit Z9 Max"
    assert data["device_matched"] is False
    assert data["in_warranty"] is True and data["claim_filed"] is True
    assert all(d["model"] not in str(reply) for d in DEVICES_ON_FILE)
    old = file_warranty_claim_impl("Orbit Z9 Max", "mic dead", state=_logged_in(fx_device_warranty="out_of_warranty"))
    assert old["error"] == "NOT_ELIGIBLE" and old["data"]["device_model"] == "Orbit Z9 Max"
    assert file_warranty_claim_impl("mon téléphone", "écran", False, False, state=_logged_in())["data"]["device_matched"] is False
