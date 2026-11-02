from lib.fakes import (
    ACCOUNTS,
    ALWAYS_WRONG_LOGIN_CODES,
    SPOKEN_LINES,
    SUPPORTED_LOCALES,
    VALID_OTPS,
    VALID_PINS,
    find_account,
    is_plausible_phone,
    is_weak_code,
    login_code_accepted,
    normalize_code,
    normalize_identifier,
    only_digits,
    read_count,
    relative_date,
    resolve_locale,
    secret_pin_accepted,
    spoken_line,
)


def test_only_digits_and_normalize_code() -> None:
    assert only_digits("(202) 555-0186") == "2025550186"
    assert only_digits("") == ""
    assert normalize_code(5903.0) == "5903"
    assert normalize_code(-5903) == "5903"
    assert normalize_code("5903.0") == "5903"
    assert normalize_code(59.5) == "595"
    assert normalize_code("59-03") == "5903"
    assert normalize_code(271846) == "271846"
    assert normalize_code(None) == ""
    assert normalize_code(True) == ""


def test_read_count_and_locales() -> None:
    assert read_count({"a": 2.0}, "a") == 2
    assert read_count({"a": "x"}, "a") == 0
    assert read_count(None, "a") == 0
    assert SUPPORTED_LOCALES == ("en-US", "fr-CA")
    assert resolve_locale("fr") == "fr-CA"
    assert resolve_locale("fr_FR") == "fr-CA"
    assert resolve_locale("es-MX") == "en-US"
    assert resolve_locale("en-GB") == "en-US"
    assert resolve_locale("") == "en-US"
    assert resolve_locale(None) == "en-US"


def test_spoken_line_fills_slots_and_falls_back() -> None:
    assert "0186" in spoken_line("otp_callback_confirm", "en-US", last4="0186")
    assert "0186" in spoken_line("otp_callback_confirm", "fr-CA", last4="0186")
    assert spoken_line("refund_confirmation_pattern", "en-US", amount="12.50", days=2) == (
        "Your refund of $12.50 will appear on your next statement within 2 business days."
    )
    assert spoken_line("live_agent_handoff", "es-US") == SPOKEN_LINES["live_agent_handoff"]["en-US"]
    assert spoken_line("no_such_key") == ""


def test_normalize_identifier() -> None:
    assert normalize_identifier("2025550186") == {"kind": "phone", "value": "2025550186"}
    assert normalize_identifier("+1 (202) 555-0186") == {"kind": "phone", "value": "2025550186"}
    assert normalize_identifier("1-202-555-0186") == {"kind": "phone", "value": "2025550186"}
    assert normalize_identifier("+44 20 7946 0958") == {"kind": "international_phone", "value": "+442079460958"}
    assert normalize_identifier("0044 20 7946 0958") == {"kind": "international_phone", "value": "+442079460958"}
    assert normalize_identifier("12345") == {"kind": "account", "value": "12345"}
    assert normalize_identifier("REF-12345") == {"kind": "reference", "value": "REF-12345"}
    assert normalize_identifier("12345-REF") == {"kind": "reference", "value": "12345-REF"}
    assert normalize_identifier("unknown-word") == {"kind": "unknown", "value": "unknown-word"}
    assert normalize_identifier("") == {"kind": "unknown", "value": ""}


def test_relative_date() -> None:
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert relative_date(0) == today
    assert len(relative_date(3)) == 10


def test_known_account_by_phone_or_account_number() -> None:
    by_phone = find_account("202-555-0186")
    assert by_phone is not None and by_phone["account_id"] == ACCOUNTS[0]["account_id"]
    by_id = find_account(ACCOUNTS[0]["account_id"].lower())
    assert by_id is not None and by_id["phone"] == ACCOUNTS[0]["phone"]
    second = find_account(ACCOUNTS[1]["phone"])
    assert second is not None and second["preferred_language"] == "fr-CA"


def test_plausible_unknown_numbers_get_a_synthetic_record() -> None:
    record = find_account("303 555 0188")
    assert record is not None
    assert record["phone"] == "3035550188" and record["first_name"] == ""
    assert record["account_id"] != ACCOUNTS[0]["account_id"]
    nine_digit = find_account("303555019")
    assert nine_digit is not None and nine_digit["first_name"] == ""
    intl = find_account("+44 20 7946 0958")
    assert intl is not None and intl["phone"] == "2079460958"
    by_ref = find_account("A-123456")
    assert by_ref is not None and by_ref["account_id"] == "A123456"


def test_implausible_numbers_are_not_found() -> None:
    assert find_account("12345") is None
    assert find_account("ACC-12") is None
    assert find_account("") is None
    assert find_account("5555555555") is None  # one repeated digit
    assert find_account("1234567890") is None
    assert find_account("111111111") is None  # weak 9-digit account number


def test_generous_formats_resolve() -> None:
    """Fact-less callers invent numbers in many shapes (DESIGN_RULES rule 43)."""
    for raw in ("555-012-3456", "06 12 34 56 78", "8827-4091-332", "MOB-773421", "ACCT-9988-XJ", "88293041", "ABC982736451", "1235550188"):
        assert find_account(raw) is not None, raw


def test_phone_and_weak_code_helpers() -> None:
    assert is_plausible_phone("3035550188")
    assert is_plausible_phone("5550123456")
    assert not is_plausible_phone("303555018")
    assert not is_plausible_phone("9876543210")
    assert is_weak_code("7777") and is_weak_code("000000")
    assert not is_weak_code("") and not is_weak_code("5903")


def test_login_ladder_for_codes_and_secret_pins() -> None:
    otp = sorted(VALID_OTPS)[0]
    pin = sorted(VALID_PINS)[0]
    assert login_code_accepted("314159", attempts=0)  # first try: any well-formed code
    assert not login_code_accepted("314159", attempts=1)  # second try: only known codes
    assert login_code_accepted(otp, attempts=1)
    assert not login_code_accepted(otp, attempts=2)  # last try: always wrong (lockout)
    assert login_code_accepted(otp, attempts=2, max_attempts=5)
    assert secret_pin_accepted(pin, attempts=1)
    assert not secret_pin_accepted(pin, attempts=2)
    assert not login_code_accepted("12")
    assert not login_code_accepted("123456789")
    assert not login_code_accepted("4444")  # weak
    assert all(not login_code_accepted(code) for code in ALWAYS_WRONG_LOGIN_CODES)


import pytest  # noqa: E402

from lib.fakes import OTP_RE, PIN_RE, classify_identifier  # noqa: E402


@pytest.mark.parametrize(
    "raw,kind",
    [
        ("514-555-0199", "phone"),
        ("(514) 555-0199", "phone"),
        ("514.555.0199", "phone"),
        ("+1 514 555 0199", "phone"),
        ("1-514-555-0199", "phone"),
        ("06 12 34 56 78", "phone"),
        ("+44 20 7946 0958", "intl_phone"),
        ("0044 20 7946 0958", "intl_phone"),
        ("883726152", "account_number"),
        ("8827-4091-332", "account_number"),
        ("MOB-773421", "account_reference"),
        ("ACCT-9988-XJ", "account_reference"),
    ],
)
def test_identifier_formats_accepted(raw: str, kind: str) -> None:
    assert classify_identifier(raw)[0] == kind


@pytest.mark.parametrize("raw", ["", "abc", "12-34", "12345", "+12", "514--555", "ABC-12", "#5145550199"])
def test_identifier_formats_rejected(raw: str) -> None:
    assert classify_identifier(raw)[0] == ""
    assert find_account(raw) is None


def test_credential_formats() -> None:
    assert OTP_RE.fullmatch("482913") and not OTP_RE.fullmatch("48291") and not OTP_RE.fullmatch("4829130")
    assert PIN_RE.fullmatch("5903") and not PIN_RE.fullmatch("590") and not PIN_RE.fullmatch("59031")
    assert not login_code_accepted("59031", attempts=0)  # neither a PIN nor a code
