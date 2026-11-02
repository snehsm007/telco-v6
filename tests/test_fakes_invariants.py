import re

from lib.fakes import (
    ACCOUNTS,
    ALWAYS_WRONG_LOGIN_CODES,
    BLOCKED_CALLER_NUMBERS,
    DECLINED_CARD_LAST4,
    FIXTURE_DEFAULTS,
    SPOKEN_LINES,
    SUPPORTED_LOCALES,
    VALID_LOGIN_CODES,
    VALID_OTPS,
    VALID_PINS,
    find_account,
    is_plausible_phone,
    is_weak_code,
    normalize_code,
)

# prd.md §7 verbatim library plus the operational lines the agents speak.
BRIEF_KEYS = {
    "greeting_main",
    "recording_notice",
    "id_verification_otp",
    "id_verification_pin",
    "live_agent_handoff",
    "business_handoff",
    "payment_method_preamble",
    "contract_cancellation_fee_disclosure",
    "refund_confirmation_pattern",
    "empathy_protocol",
    "outage_active",
    "transfer_to_specialist",
    "otp_callback_confirm",
}
FIXTURES = {
    "fx_pin_on_file",
    "fx_otp_on_file",
    "fx_card_on_file_status",
    "fx_service_status",
    "fx_recent_payment",
    "fx_business_account",
    "fx_outage_status",
    "fx_technician_status",
    "fx_duplicate_payment",
    "fx_extra_bill_line",
    "fx_device_warranty",
    "fx_mfa_enabled",
    "fx_sms_delivery",
}


def test_spoken_lines_cover_the_brief_in_every_locale() -> None:
    assert BRIEF_KEYS <= set(SPOKEN_LINES)
    for key, table in SPOKEN_LINES.items():
        assert set(table) == set(SUPPORTED_LOCALES), key
        for loc, line in table.items():
            assert len(line) > 30, (key, loc)
            assert table["fr-CA"] != table["en-US"], key
    # Slots survive translation.
    for key, table in SPOKEN_LINES.items():
        slots = {s: sorted(re.findall(r"\[(\w+)\]", line)) for s, line in table.items()}
        assert slots["en-US"] == slots["fr-CA"], key


def test_brief_lines_are_verbatim() -> None:
    assert SPOKEN_LINES["recording_notice"]["en-US"] == "This call may be recorded for quality and training purposes."
    assert SPOKEN_LINES["live_agent_handoff"]["en-US"] == "I'll connect you to a representative who can help. Please hold."
    assert SPOKEN_LINES["transfer_to_specialist"]["en-US"].startswith("I'll connect you to a billing specialist now")
    assert SPOKEN_LINES["empathy_protocol"]["en-US"].startswith("I'm very sorry to hear")


def test_fixture_defaults_are_complete_strings() -> None:
    assert set(FIXTURE_DEFAULTS) == FIXTURES
    assert all(isinstance(v, str) for v in FIXTURE_DEFAULTS.values())
    assert FIXTURE_DEFAULTS["fx_pin_on_file"] == "" and FIXTURE_DEFAULTS["fx_otp_on_file"] == ""
    assert FIXTURE_DEFAULTS["fx_business_account"] == "false"


def test_credential_invariants() -> None:
    assert {"9999", "999999", "8888"} <= ALWAYS_WRONG_LOGIN_CODES
    assert VALID_OTPS and VALID_PINS and VALID_LOGIN_CODES == (VALID_OTPS | VALID_PINS)
    assert not ALWAYS_WRONG_LOGIN_CODES & VALID_LOGIN_CODES  # DESIGN_RULES rule 23
    assert all(len(p) == 4 for p in VALID_PINS) and all(len(o) == 6 for o in VALID_OTPS)
    assert not any(is_weak_code(c) for c in VALID_LOGIN_CODES)
    assert {"0000", "9999"} <= DECLINED_CARD_LAST4


def test_account_invariants() -> None:
    assert len(ACCOUNTS) >= 2
    ids = [a["account_id"] for a in ACCOUNTS]
    assert len(ids) == len(set(ids))
    for account in ACCOUNTS:
        assert is_plausible_phone(account["phone"])
        assert account["phone"][-4:] not in ALWAYS_WRONG_LOGIN_CODES
        assert normalize_code(account["account_id"])[-4:] not in ALWAYS_WRONG_LOGIN_CODES
        assert account["phone"] not in BLOCKED_CALLER_NUMBERS
        assert account["preferred_language"] in SUPPORTED_LOCALES
        assert account["business_flag"] is False  # business is a per-scenario fixture
    for blocked in BLOCKED_CALLER_NUMBERS:
        assert len(blocked) == 10


def test_fakes_helper_invariants() -> None:
    assert find_account("202555019") is not None
    assert find_account("12345") is None
    assert find_account("ACC-12") is None
