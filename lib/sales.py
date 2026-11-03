"""Sales and equipment tools (docs/tdd.md §4, prd.md §12).

browse_plans          catalogue + coverage, no login (Turn-N+1 fields: current plan,
                      price difference, contract terms, activation timing).
place_order           login, two-step: quote (CONFIRMATION_REQUIRED) then order.
file_warranty_claim   login, device on file, damage/warranty rules, urgent safety path;
                      two-step: claim terms (CONFIRMATION_REQUIRED) then filed.
start_number_transfer port-in. Empty number = public checklist (decision A3);
                      starting a transfer needs login. Never returns any PIN.

Tools return data, never sentences; descriptive notes come from SALES_COPY in the
call language only. Every session key used here is declared in cxas_app/app.json.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import re
from typing import Any

from lib.core import (
    account_record,
    append_list,
    check_mock_error,
    dispatch_sms,
    display_date,
    fixture,
    get_state,
    money,
    require_login,
    session_language,
    to_decimal,
    validation_error,
)
from lib.fakes import (
    CURRENT_DATA_GB,
    CURRENT_PLANS,
    CURRENT_SPEED_MBPS,
    DEFAULT_REGION,
    DEVICE_WARRANTY_DAYS,
    DEVICES_ON_FILE,
    PLANS,
    REGION_BY_POSTAL_LETTER,
    SALES_ACTIVATION_DAYS,
    SALES_CAPACITY_WORDS,
    SALES_COPY,
    SALES_COVERAGE_MAX_MBPS,
    SALES_DEVICE_VARIANT_WORDS,
    SALES_EQUIPMENT_DELIVERY_DAYS,
    SALES_FEATURES_FR,
    SALES_GENERIC_DEVICE_WORDS,
    SALES_IMEI_DIGITS,
    SALES_LANDLINE_WORDS,
    SALES_NEW_LINE_WORDS,
    SALES_OWN_BRAND_WORDS,
    SALES_OUT_OF_WARRANTY_AGE_DAYS,
    SALES_PLACEHOLDERS,
    SALES_PORT_DAYS,
    SALES_PORT_MAX_DAYS,
    SALES_PRICE_WORDS,
    SALES_REDUCED_SPEED_KBPS,
    SALES_REPAIR_FEE,
    SALES_RETURN_WINDOW_DAYS,
    SALES_SAFETY_WORDS,
    SALES_URGENT_SHIP_DAYS,
    SALES_WARRANTY_REPLACEMENT_COST,
    SALES_WARRANTY_SHIP_DAYS,
    SERVICE_PRICES,
    is_plausible_phone,
    is_weak_code,
    normalize_code,
    normalize_identifier,
    relative_date,
    resolve_copy_locale,
)
from lib.replies import display_amount, error_reply, ok_reply, tracking_id

_SALES_MAX_OPTIONS = 3  # prd.md §12: never more than 3 options

_SALES_LOB_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("tv", ("tv", "télé", "tele", "television", "channel", "chaîne", "sport", "movie", "film")),
    ("internet", ("internet", "wifi", "wi-fi", "fibre", "fiber", "broadband", "connexion", "connection")),
    ("homephone", ("home phone", "homephone", "landline", "ligne fixe", "téléphone fixe")),
    ("mobility", ("mobil", "mobile", "cell", "wireless", "phone", "data", "données", "forfait")),
)


# ----------------------------------------------------------------------------- helpers


def _sales_text(key: str, lang: str) -> str:
    """Sales copy in the call language only (no sibling-language keys in replies)."""
    table = SALES_COPY.get(key, {})
    return table.get(resolve_copy_locale(lang)) or table.get("en-US", "")


def _sales_has(text: str, words: tuple[str, ...] | frozenset[str]) -> bool:
    low = str(text or "").lower()
    return any(w in low for w in words)


def _sales_placeholder(value: Any) -> bool:
    return str(value if value is not None else "").strip().lower() in SALES_PLACEHOLDERS


def _sales_bool(value: Any) -> bool | None:
    """Caller yes/no answers: True, False, or None when not answered yet."""
    if isinstance(value, bool):
        return value
    low = str(value if value is not None else "").strip().lower()
    if low in ("true", "yes", "y", "1", "oui", "1.0"):
        return True
    if low in ("false", "no", "n", "0", "non", "none", "0.0", "aucun"):
        return False
    return None


def _sales_business_date(days: int) -> str:
    """ISO date `days` business days from today (0 = today)."""
    current = datetime.now(timezone.utc)
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current.strftime("%Y-%m-%d")


def _sales_data_display(gb: int, lang: str) -> str:
    return f"{gb} Go" if resolve_copy_locale(lang) == "fr-CA" else f"{gb} GB"


def _sales_speed_display(mbps: int, lang: str) -> str:
    fr = resolve_copy_locale(lang) == "fr-CA"
    if mbps >= 1000 and mbps % 1000 == 0:
        return f"{mbps // 1000} Gbit/s" if fr else f"{mbps // 1000} Gbps"
    return f"{mbps} Mbit/s" if fr else f"{mbps} Mbps"


def _sales_kbps_display(kbps: int, lang: str) -> str:
    return f"{kbps} kbit/s" if resolve_copy_locale(lang) == "fr-CA" else f"{kbps} kbps"


def _sales_feature(text: str, lang: str) -> str:
    return SALES_FEATURES_FR.get(text, text) if resolve_copy_locale(lang) == "fr-CA" else text


def _sales_lob(lob: Any, need: Any = "") -> str:
    """Map the model's line-of-business words onto mobility / internet / tv / homephone."""
    for text in (lob, need):
        low = str(text or "").strip().lower()
        if not low:
            continue
        for key, words in _SALES_LOB_WORDS:
            if low == key or any(w in low for w in words):
                return key
    return ""


def _sales_capacity(plan: dict[str, Any]) -> int:
    return int(plan.get("data_gb") or plan.get("speed_mbps") or 0)


def _sales_region(state: dict[str, Any]) -> str:
    """Region class of the identified account's service address ("" when not identified)."""
    if not state.get("account_id"):
        return ""
    region = str(state.get("region") or "").strip()
    if region:
        return region
    postal = str(account_record(state).get("postal_code") or "")
    return REGION_BY_POSTAL_LETTER.get(postal[:1].upper(), DEFAULT_REGION)


def _sales_account_lobs(state: dict[str, Any]) -> list[str]:
    return list(account_record(state).get("lines_of_business") or [])


def _sales_current(state: dict[str, Any], lob: str, lang: str) -> dict[str, Any] | None:
    """The plan the identified account has today for `lob` (None when it has no such service)."""
    if not state.get("account_id") or lob not in _sales_account_lobs(state) or lob not in CURRENT_PLANS:
        return None
    current: dict[str, Any] = {"name": CURRENT_PLANS[lob], **money(SERVICE_PRICES.get(lob, "0"), "price")}
    if lob == "mobility":
        current["data_gb"] = CURRENT_DATA_GB
        current["data_display"] = _sales_data_display(CURRENT_DATA_GB, lang)
    elif lob == "internet":
        current["speed_mbps"] = CURRENT_SPEED_MBPS
        current["speed_display"] = _sales_speed_display(CURRENT_SPEED_MBPS, lang)
    return current


def _sales_account_total(state: dict[str, Any]) -> Decimal:
    return sum(
        (to_decimal(SERVICE_PRICES.get(lob, "0")) or Decimal("0") for lob in _sales_account_lobs(state)),
        Decimal("0.00"),
    )


def _sales_pricing(state: dict[str, Any], plan: dict[str, Any], current: dict[str, Any] | None) -> dict[str, Any]:
    """Price difference against today's plan and the new monthly totals (service and account).

    Without a current plan (caller not identified, or a new service) only the plan's own
    price is the new service total and no difference is reported.
    """
    price = to_decimal(plan["price"]) or Decimal("0")
    if current is None:
        out: dict[str, Any] = {**money(price, "new_monthly_total"), "price_change": "new_service"}
        if state.get("account_id"):
            out.update(money(_sales_account_total(state) + price, "new_account_monthly_total"))
        return out
    old = to_decimal(current["price"]) or Decimal("0")
    delta = price if plan.get("addon") else price - old
    out = {
        "price_difference": float(abs(delta)),
        "price_difference_display": display_amount(abs(delta)),
        "price_change": "increase" if delta > 0 else "decrease" if delta < 0 else "none",
        **money(old + delta, "new_monthly_total"),
        **money(_sales_account_total(state) + delta, "new_account_monthly_total"),
    }
    return out


def _sales_activation(lob: str, lang: str) -> dict[str, str]:
    days = SALES_ACTIVATION_DAYS.get(lob, 0)
    iso = _sales_business_date(days)
    return {
        "effective_date": iso,
        "effective_date_display": display_date(iso, lang),
        "activation_display": _sales_text("activation_today" if days == 0 else "activation_next_day", lang),
    }


def _sales_plan_view(state: dict[str, Any], plan: dict[str, Any], current: dict[str, Any] | None, lang: str) -> dict[str, Any]:
    view: dict[str, Any] = {
        "plan_id": plan["plan_id"],
        "name": plan["name"],
        "lob": plan["lob"],
        "is_addon": bool(plan.get("addon")),
        **money(plan["price"], "price"),
        "key_features": [_sales_feature(f, lang) for f in plan.get("features", [])[:3]],
    }
    if plan.get("data_gb"):
        view["data_display"] = _sales_data_display(int(plan["data_gb"]), lang)
    if plan.get("speed_mbps"):
        view["speed_display"] = _sales_speed_display(int(plan["speed_mbps"]), lang)
    if plan["lob"] == "mobility":  # follow-up facts: speed after the allowance, hotspot (rule 33)
        view["reduced_speed_display"] = _sales_kbps_display(SALES_REDUCED_SPEED_KBPS, lang)
        view["hotspot_note"] = _sales_text("hotspot_included", lang)
    if plan.get("upload_mbps"):  # follow-up facts: upload, symmetry, latency (DESIGN_RULES rule 33)
        view["upload_speed_display"] = _sales_speed_display(int(plan["upload_mbps"]), lang)
        view["symmetric"] = bool(plan.get("symmetric"))
        view["latency_note"] = _sales_text(str(plan.get("latency_key") or ""), lang)
    if plan.get("usage_key"):  # follow-up fact: data cap / throttling (rule 33)
        view["usage_note"] = _sales_text(str(plan["usage_key"]), lang)
    if plan.get("channel_examples"):
        view["channel_examples"] = [_sales_feature(c, lang) for c in plan["channel_examples"]]
        view["hd_included"] = bool(plan.get("hd_included"))
        # Follow-up facts for a TV pack: size, where the full lineup is, blackouts (rule 33).
        if plan.get("channel_count"):
            view["channel_count"] = int(plan["channel_count"])
        if plan.get("channel_lineup"):  # named channels, for "which channels exactly?" (rule 33)
            view["channel_lineup"] = list(plan["channel_lineup"])
        view["full_channel_list_note"] = _sales_text("full_channel_list", lang)
        if plan.get("blackout_key"):
            view["blackout_note"] = _sales_text(str(plan["blackout_key"]), lang)
    view.update(_sales_pricing(state, plan, current))
    return view


def _sales_find_plan(plan_id: Any) -> dict[str, Any] | None:
    """Find a plan by id ("MOB-50", "mob 50") or exact name ("Plus 50")."""
    raw = str(plan_id or "").strip().lower()
    if not raw:
        return None
    compact = re.sub(r"[\s_\-]+", "", raw)
    for plan in PLANS:
        if compact == re.sub(r"[\s_\-]+", "", plan["plan_id"].lower()) or raw == plan["name"].lower():
            return plan
    return None


def _sales_budget(budget: Any) -> Decimal | None:
    match = re.search(r"\d+(?:[.,]\d{1,2})?", str(budget if budget is not None else ""))
    return to_decimal(match.group(0)) if match else None


def _sales_rank(plans: list[dict[str, Any]], need: str) -> list[dict[str, Any]]:
    """Pick at most 3: capacity needs keep the biggest tiers, otherwise the lowest prices; shown by price."""
    by_price = sorted(plans, key=lambda p: to_decimal(p["price"]) or Decimal("0"))
    if _sales_has(need, SALES_CAPACITY_WORDS) and not _sales_has(need, SALES_PRICE_WORDS):
        top = sorted(plans, key=_sales_capacity, reverse=True)[:_SALES_MAX_OPTIONS]
        return [p for p in by_price if p in top]
    return by_price[:_SALES_MAX_OPTIONS]


def _sales_model_tokens(text: Any) -> set[str]:
    """Model-number tokens the caller named: letters+digits ("s22", "8a") or a short number ("13").

    Storage sizes ("128gb") and long numbers (years, codes) are not model numbers.
    """
    tokens = re.findall(r"[^\W_]+", str(text or "").lower())
    return {
        t for t in tokens
        if re.search(r"\d", t) and len(t) <= 6
        and not re.fullmatch(r"\d+(?:gb|go|tb|to|g)", t)
        and not (t.isdigit() and len(t) > 2)
    }


def _sales_device(device: Any, issue: Any) -> tuple[dict[str, Any], bool]:
    """Match the caller's words to a device on file.

    A model the caller names that isn't on file gets a record of its own (same default
    purchase age as the newest device), so a claim is never filed for a phone they don't
    own; only a generic "my phone" falls back to the most recent purchase.
    """
    text = f"{device or ''} {issue or ''}".lower()
    named_tokens = _sales_model_tokens(device)
    named_variants = set(re.findall(r"[^\W_]+", str(device or "").lower())) & SALES_DEVICE_VARIANT_WORDS
    for dev in DEVICES_ON_FILE:
        if not (any(k in text for k in dev.get("keywords", [])) or str(dev["model"]).lower() in text):
            continue
        # Same brand, different model ("Galaxy S22" vs the S24 on file): not this device.
        if named_tokens - _sales_model_tokens(dev["model"]):
            continue
        # Same model number, other variant ("iPhone 15 Pro" vs the iPhone 15 on file): not this device.
        if named_variants - set(re.findall(r"[^\W_]+", str(dev["model"]).lower())):
            continue
        return dev, True
    newest = min(DEVICES_ON_FILE, key=lambda d: int(d["purchased_days_ago"]))
    named = " ".join(str(device or "").split())[:60]
    words = re.findall(r"[^\W_]+", named.lower())
    if _sales_placeholder(named) or all(w in SALES_GENERIC_DEVICE_WORDS for w in words):
        return newest, False
    device_id = "DEV-" + normalize_code(tracking_id("caller_device", named.lower()))
    return {"device_id": device_id, "model": named, "purchased_days_ago": newest["purchased_days_ago"]}, False


# ----------------------------------------------------------------------------- browse_plans


def browse_plans_impl(
    lob: str = "",
    budget: str | int | float = "",
    need: str = "",
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Up to 3 plans or add-ons for a line of business, with coverage and Turn-N+1 facts. No login."""
    state = get_state(state, session_state)
    lang = session_language(state, language)
    err = check_mock_error(state, lang, "browse_plans")
    if err:
        return err
    lob_key = _sales_lob(lob, need)
    need_text = str(need or "")
    reference = tracking_id("browse_plans", state.get("account_id", ""), lob_key, budget, need_text)
    if not lob_key:
        return validation_error(
            state, "Unknown line of business.", "Ask if the caller means mobile, internet or TV.", reference, lang
        )
    budget_amt = _sales_budget(budget) if not _sales_placeholder(budget) else None
    if budget_amt is not None and budget_amt <= 0:
        return validation_error(state, "The budget must be above zero.", "Ask for the monthly budget again.", reference, lang)
    state["lob"] = lob_key
    state["last_tracking_id"] = reference

    region = _sales_region(state)
    max_mbps = SALES_COVERAGE_MAX_MBPS.get(region, SALES_COVERAGE_MAX_MBPS[DEFAULT_REGION]) if region else 0
    current = _sales_current(state, lob_key, lang)
    catalogue = [p for p in PLANS if p["lob"] == lob_key]

    if lob_key == "tv":
        wanted = [p for p in catalogue if _sales_has(need_text, tuple(p.get("keywords", [])))]
        others = [p for p in catalogue if p not in wanted]
        candidates = wanted + others
    else:
        candidates = list(catalogue)
        if current:
            floor = int(current.get("data_gb") or current.get("speed_mbps") or 0)
            candidates = [p for p in candidates if _sales_capacity(p) > floor]
        if lob_key == "internet" and max_mbps:
            candidates = [p for p in candidates if int(p.get("speed_mbps") or 0) <= max_mbps]

    over_budget: list[dict[str, Any]] = []
    if budget_amt is not None:
        over_budget = [p for p in candidates if (to_decimal(p["price"]) or Decimal("0")) > budget_amt]
        candidates = [p for p in candidates if p not in over_budget]

    chosen = candidates[:_SALES_MAX_OPTIONS] if lob_key == "tv" else _sales_rank(candidates, need_text)
    data: dict[str, Any] = {
        "lob": lob_key,
        "plans": [_sales_plan_view(state, p, current, lang) for p in chosen],
        "plan_count": len(chosen),
        "coverage_checked": bool(region),
        "coverage_available": True if region else None,
        "has_current_service": current is not None,
        "current_plan": current,
        "contract_terms": _sales_text("contract_terms", lang),
        "proration_note": _sales_text("proration", lang),
        "prices_exclude_tax": True,
        **_sales_activation(lob_key, lang),
    }
    if not region:
        data["coverage_note"] = _sales_text("coverage_unchecked", lang)
    if lob_key == "internet":
        if max_mbps:
            data["max_speed_display"] = _sales_speed_display(max_mbps, lang)
        delivery = _sales_business_date(SALES_EQUIPMENT_DELIVERY_DAYS)
        data["gateway_delivery_eta_display"] = display_date(delivery, lang)
    if lob_key == "mobility":
        data["after_data_cap"] = _sales_text("after_data_cap", lang)
        data["multi_line_note"] = _sales_text("multi_line_pricing", lang)
    if budget_amt is not None:
        data.update(money(budget_amt, "budget"))
        data["no_plan_within_budget"] = not chosen
        if over_budget and not chosen:
            cheapest = min(over_budget, key=lambda p: to_decimal(p["price"]) or Decimal("0"))
            data.update(money(cheapest["price"], "lowest_available_price"))
    if lob_key == "tv" and current is None and state.get("account_id"):
        data["tv_service_required_for_addons"] = True
    return ok_reply(data, reference, language=lang)


# ----------------------------------------------------------------------------- place_order


def place_order_impl(
    plan_id: str = "",
    confirmed: str | bool = "",
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Quote (confirmed=false) then place (confirmed=true) a plan change or add-on. Needs login."""
    state = get_state(state, session_state)
    lang = session_language(state, language)
    err = check_mock_error(state, lang, "place_order")
    if err:
        return err
    gate = require_login(state, lang, "place_order")
    if gate:
        return gate
    account_id = str(state.get("account_id") or "")
    plan = _sales_find_plan(plan_id)
    reference = tracking_id("place_order", account_id, str(plan_id or "").strip().lower())
    if plan is None:
        return validation_error(
            state,
            "Unknown plan id.",
            "Use a plan_id from browse_plans; call browse_plans again if needed.",
            reference,
            lang,
            data={"valid_plan_ids": [p["plan_id"] for p in PLANS]},
        )
    lob = plan["lob"]
    current = _sales_current(state, lob, lang)
    if plan.get("addon") and current is None:
        return error_reply(
            "NOT_ELIGIBLE",
            "Add-ons need that service on the account.",
            "Explain the add-on needs that service; offer the base package instead.",
            reference,
            language=lang,
            data={"plan_id": plan["plan_id"], "required_service": lob},
        )
    region = _sales_region(state)
    max_mbps = SALES_COVERAGE_MAX_MBPS.get(region, SALES_COVERAGE_MAX_MBPS[DEFAULT_REGION])
    if lob == "internet" and int(plan.get("speed_mbps") or 0) > max_mbps:
        return error_reply(
            "NOT_ELIGIBLE",
            "That speed is not available at the service address.",
            "Say the speed isn't available there; offer a plan up to max_speed_display.",
            reference,
            language=lang,
            data={"plan_id": plan["plan_id"], "max_speed_display": _sales_speed_display(max_mbps, lang)},
        )

    quote: dict[str, Any] = {
        **_sales_plan_view(state, plan, current, lang),
        "current_plan": current,
        "contract_terms": _sales_text("contract_terms", lang),
        "proration_note": _sales_text("proration", lang),
        **_sales_activation(lob, lang),
    }
    if lob == "internet":
        delivery = _sales_business_date(SALES_EQUIPMENT_DELIVERY_DAYS)
        quote["delivery_eta_date"] = delivery
        quote["delivery_eta_display"] = display_date(delivery, lang)
    if lob == "mobility":
        quote["after_data_cap"] = _sales_text("after_data_cap", lang)
        if current is not None:  # an extra line adds the plan price; new_monthly_total is the plan-change view
            quote.update(money(plan["price"], "new_line_monthly_price"))
            quote.update(money(_sales_account_total(state) + (to_decimal(plan["price"]) or Decimal("0")), "new_line_account_monthly_total"))
            quote["new_line_pricing_note"] = _sales_text("new_line_pricing", lang)
            quote["multi_line_note"] = _sales_text("multi_line_pricing", lang)

    order_id = "ORD-" + tracking_id("place_order", account_id, plan["plan_id"])[1:]
    pending_key = f"place_order:{plan['plan_id']}"
    already = plan["plan_id"] in [p for p in str(state.get("sales_orders") or "").split(",") if p]
    if already:
        state["last_tracking_id"] = order_id
        return ok_reply(
            {**quote, "order_id": order_id, "order_placed": True, "already_placed": True, "sms_receipt_sent": True},
            order_id,
            language=lang,
        )
    if _sales_bool(confirmed) is not True or state.get("pending_confirmation") != pending_key:
        state["pending_confirmation"] = pending_key
        state["last_tracking_id"] = reference
        return error_reply(
            "CONFIRMATION_REQUIRED",
            "Read the quote and get the caller's yes before ordering.",
            "Read name, price, new_monthly_total and effective date; ask to confirm; then confirmed=true.",
            reference,
            language=lang,
            data={**quote, "order_placed": False},
        )

    append_list(state, "sales_orders", plan["plan_id"])
    state["pending_confirmation"] = ""
    state["last_tracking_id"] = order_id
    sms = dispatch_sms(state, "order_receipt")
    return ok_reply(
        {
            **quote,
            "order_id": order_id,
            "order_placed": True,
            "already_placed": False,
            "sms_receipt_sent": True,
            "sms_destination_last4": sms["destination_last4"],
        },
        order_id,
        language=lang,
    )


# ----------------------------------------------------------------------------- file_warranty_claim


def file_warranty_claim_impl(
    device: str = "",
    issue: str = "",
    physical_damage: str | bool = "",
    water_damage: str | bool = "",
    confirmed: str | bool = "",
    state: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
    language: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Check coverage, read the claim terms (confirmed=false), then file (confirmed=true). Needs login."""
    state = get_state(state, session_state)
    lang = session_language(state, language)
    err = check_mock_error(state, lang, "file_warranty_claim")
    if err:
        return err
    urgent = _sales_has(f"{device or ''} {issue or ''}", SALES_SAFETY_WORDS)
    gate = require_login(state, lang, "file_warranty_claim")
    if gate:
        if urgent:
            gate["data"].update(
                {"urgent": True, "safety_advice_key": "battery_safety", "safety_advice": _sales_text("battery_safety", lang)}
            )
            gate["agent_action"] = "Say safety_advice now, then verify the caller and call again."
        return gate

    account_id = str(state.get("account_id") or "")
    dev, matched = _sales_device(device, issue)
    age = int(dev["purchased_days_ago"])
    if fixture(state, "fx_device_warranty") == "out_of_warranty":
        age = SALES_OUT_OF_WARRANTY_AGE_DAYS
    purchase_iso = relative_date(-age)
    end_iso = relative_date(DEVICE_WARRANTY_DAYS - age)
    in_warranty = age <= DEVICE_WARRANTY_DAYS
    reference = tracking_id("file_warranty_claim", account_id, dev["device_id"])
    state["last_tracking_id"] = reference
    base: dict[str, Any] = {
        "device_model": dev["model"],
        "device_matched": matched,
        "purchase_date": purchase_iso,
        "purchase_date_display": display_date(purchase_iso, lang),
        "warranty_end_date": end_iso,
        "warranty_end_display": display_date(end_iso, lang),
        "in_warranty": in_warranty,
        "urgent": urgent,
    }
    # What the replacement costs, for the fee question callers ask before agreeing (rule 33).
    fees: dict[str, Any] = {
        **money(SALES_WARRANTY_REPLACEMENT_COST, "replacement_cost"),
        "replacement_shipping_free": True,
        "return_shipping_prepaid": not urgent,
        "fees_note": _sales_text("warranty_fees_urgent" if urgent else "warranty_fees", lang),
        "card_hold": False,
        "card_hold_note": _sales_text("warranty_no_card_hold_urgent" if urgent else "warranty_no_card_hold", lang),
    }
    if urgent:
        base["safety_advice_key"] = "battery_safety"
        base["safety_advice"] = _sales_text("battery_safety", lang)

    physical = _sales_bool(physical_damage)
    water = _sales_bool(water_damage)
    repair = {
        "repair_options": [_sales_text(k, lang) for k in ("repair_paid", "repair_protection", "repair_trade_in")],
        **money(SALES_REPAIR_FEE, "repair_fee"),
    }
    if not urgent and (physical or water):
        return error_reply(
            "NOT_ELIGIBLE",
            "Physical or water damage is not covered by the warranty.",
            "Explain damage isn't covered and offer the repair_options.",
            reference,
            language=lang,
            data={**base, "not_covered_reason": "water_damage" if water else "physical_damage", **repair},
        )
    if not urgent and not in_warranty:
        return error_reply(
            "NOT_ELIGIBLE",
            "The device is out of warranty.",
            "Say the warranty ended on warranty_end_display and offer the repair_options.",
            reference,
            language=lang,
            data={**base, "not_covered_reason": "out_of_warranty", **repair},
        )
    if not urgent and (physical is None or water is None):
        missing = [name for name, val in (("physical_damage", physical), ("water_damage", water)) if val is None]
        check = {
            **base,
            "claim_filed": False,
            "damage_check_needed": True,
            "missing": missing,
            **fees,
        }
        reply = ok_reply(check, reference, language=lang)
        reply["agent_action"] = "Confirm the device model, ask about cracks or water damage, then call again."
        return reply
    if not urgent and not str(issue or "").strip():
        return validation_error(state, "No fault described.", "Ask what is wrong with the device.", reference, lang)

    claim_id = "WC-" + tracking_id("warranty_claim", account_id, dev["device_id"])[1:]
    ship_days = SALES_URGENT_SHIP_DAYS if urgent else SALES_WARRANTY_SHIP_DAYS
    eta_iso = _sales_business_date(ship_days)
    terms: dict[str, Any] = {
        **base,
        **fees,
        "shipping": "expedited" if urgent else "standard",
        "replacement_eta_date": eta_iso,
        "replacement_eta_display": display_date(eta_iso, lang),
        "return_instructions": _sales_text("return_urgent" if urgent else "return_standard", lang),
        "data_transfer_note": _sales_text("data_transfer_urgent" if urgent else "data_transfer_standard", lang),
    }
    if not urgent:
        return_by = relative_date(SALES_RETURN_WINDOW_DAYS + ship_days)
        terms["return_by_display"] = display_date(return_by, lang)
    claims = [c for c in str(state.get("sales_claims") or "").split(",") if c]
    already = claim_id in claims
    pending_key = f"file_warranty_claim:{dev['device_id']}"
    if not already and (_sales_bool(confirmed) is not True or state.get("pending_confirmation") != pending_key):
        # Two-step like a cancellation: the caller hears the terms and agrees before anything is filed.
        state["pending_confirmation"] = pending_key
        return error_reply(
            "CONFIRMATION_REQUIRED",
            "Read the claim terms and get the caller's yes before filing.",
            "Say safety_advice if urgent, then the replacement terms and fees_note; ask to file; then confirmed=true.",
            reference,
            language=lang,
            data={**terms, "claim_filed": False},
        )
    data: dict[str, Any] = {
        **terms,
        "claim_id": claim_id,
        "claim_filed": True,
        "already_filed": already,
    }
    if not already:
        append_list(state, "sales_claims", claim_id)
        state["pending_confirmation"] = ""
        data["sms_confirmation_sent"] = dispatch_sms(state, "warranty_claim")["sms_sent"]
    else:
        data["sms_confirmation_sent"] = True
    state["last_tracking_id"] = claim_id
    return ok_reply(data, claim_id, language=lang)


# ----------------------------------------------------------------------------- start_number_transfer


def _sales_port_checklist(lang: str) -> list[str]:
    keys = ("port_check_number", "port_check_provider", "port_check_account", "port_check_pin", "port_check_active")
    return [_sales_text(k, lang) for k in keys]


def _sales_port_facts(lang: str) -> dict[str, Any]:
    """Follow-up facts callers ask before giving details: cost, authorization, no account number (rule 33)."""
    return {
        "fees_note": _sales_text("port_fees", lang),
        "authorization_note": _sales_text("port_authorization", lang),
        "multi_line_note": _sales_text("multi_line_pricing", lang),
        "account_number_alternatives": [_sales_text(k, lang) for k in ("port_account_alt_bill", "port_account_alt_imei")],
    }


def _sales_port_eta(kind: str, lang: str) -> dict[str, str]:
    iso = _sales_business_date(SALES_PORT_DAYS.get(kind, 0))
    return {"date": iso, "display": display_date(iso, lang)}


def _sales_port_timeframe(kind: str, lang: str) -> str:
    """Typical completion window for a transfer, so "how long does it take?" never waits for the details."""
    low, high = SALES_PORT_DAYS.get(kind, 0), SALES_PORT_MAX_DAYS.get(kind, 0)
    fr = resolve_copy_locale(lang) == "fr-CA"
    if low == 0:
        return f"le jour même, jusqu'à {high} jours ouvrables" if fr else f"the same day, up to {high} business days"
    return f"{low} à {high} jours ouvrables" if fr else f"{low} to {high} business days"


def _sales_own_number(state: dict[str, Any], number: str) -> bool:
    """True when the number to transfer is the logged-in account's own phone number."""
    own = {str(state.get(k) or "") for k in ("phone_last4", "caller_provided_phone_last4")} - {""}
    record_phone = normalize_code(account_record(state).get("phone", ""))
    return number == record_phone or number[-4:] in own


def start_number_transfer_impl(
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
