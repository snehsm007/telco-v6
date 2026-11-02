"""Every locale in lib.fakes.SUPPORTED_LOCALES is complete, and tool replies follow the call language."""

from __future__ import annotations

import re
from typing import Any

import pytest

from lib.fakes import SPOKEN_LINES, SUPPORTED_LOCALES
from lib.services import (
    ALL_TOOLS,
    check_login_code_impl,
    check_secret_pin_impl,
    handover_to_person_impl,
    lookup_account_impl,
    send_login_code_impl,
    send_sms_notification_impl,
)
from tests.tool_registry import call, is_implemented

SIBLING_KEY_RE = re.compile(r"_(?:en|fr|es|de|pt|it)(?:[-_][a-z0-9]{2,4})?$", re.IGNORECASE)
LOCALE_TEXT_RE = re.compile(r"\[translate:|TODO|FIXME", re.IGNORECASE)


def _sibling_keys(obj: Any, path: str = "") -> list[str]:
    findings: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{path}.{k}" if path else str(k)
            if isinstance(k, str) and SIBLING_KEY_RE.search(k.lower()):
                findings.append(here)
            findings.extend(_sibling_keys(v, here))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            findings.extend(_sibling_keys(item, f"{path}[{i}]"))
    return findings


def test_supported_locales_are_english_and_canadian_french() -> None:
    assert SUPPORTED_LOCALES == ("en-US", "fr-CA")


def test_spoken_lines_all_supported_locales_present() -> None:
    for key, table in SPOKEN_LINES.items():
        for loc in SUPPORTED_LOCALES:
            assert loc in table, f"Missing locale {loc} in SPOKEN_LINES[{key}]"
            assert table[loc].strip(), f"Empty line in SPOKEN_LINES[{key}][{loc}]"
            assert not LOCALE_TEXT_RE.search(table[loc]), f"Untranslated line in SPOKEN_LINES[{key}][{loc}]"
        assert set(table) <= set(SUPPORTED_LOCALES), f"SPOKEN_LINES[{key}] has an unsupported locale"


@pytest.mark.parametrize("locale", SUPPORTED_LOCALES)
def test_shared_tools_reply_in_the_call_language(locale: str) -> None:
    base: dict[str, Any] = {"account_id": "A1001", "phone_last4": "0186", "language": locale}
    calls = [
        (lookup_account_impl, {"phone_or_account": "2025550186"}, {}),
        (send_login_code_impl, {}, {"auth_status": "none"}),
        (check_login_code_impl, {"code": "271846"}, {"auth_status": "code_sent"}),
        (check_secret_pin_impl, {"pin": "5903"}, {"auth_status": "none"}),
        (send_sms_notification_impl, {"purpose": "outage_updates"}, {}),
        (handover_to_person_impl, {"reason": "user_requested_agent"}, {}),
    ]
    for fn, kwargs, extra in calls:
        state = {**base, **extra}
        reply = fn(**kwargs, state=state, language=locale)
        assert reply["status"] == "ok", f"{fn.__name__}: {reply}"
        assert reply["active_language"] == locale, fn.__name__
        assert not _sibling_keys(reply), f"{fn.__name__} has localized sibling keys"
        assert state["language"] == locale
    assert state["handoff_message"] == SPOKEN_LINES["live_agent_handoff"][locale]


@pytest.mark.parametrize("locale", SUPPORTED_LOCALES)
def test_error_replies_contract(locale: str) -> None:
    state: dict[str, Any] = {"language": locale}
    err = lookup_account_impl(phone_or_account="000", state=state, language=locale)
    assert err["status"] == "error" and err["active_language"] == locale
    assert 0 < len(err["agent_action"]) <= 120
    assert not _sibling_keys(err)
    # The error text follows the call language too (VE-15: English error_message failed "strictly French").
    assert (err["error_message"] == "Aucun dossier correspondant n'a été trouvé.") is (locale == "fr-CA")


@pytest.mark.parametrize("locale", SUPPORTED_LOCALES)
@pytest.mark.parametrize("name", ALL_TOOLS)
def test_every_tool_keeps_the_locked_call_language(name: str, locale: str) -> None:
    if not is_implemented(name):
        pytest.skip(f"{name} is still a placeholder")
    state = {"account_id": "A1001", "phone_last4": "0186", "auth_status": "pass", "logged_in": True, "language": locale}
    reason = {"reason": "user_requested_agent"} if name == "handover_to_person" else {}
    # The model passing en-US must never downgrade a French call (asymmetric lock).
    reply = call(name, state, "en-US", **reason)
    assert reply.get("active_language", locale) == locale, f"{name}: {reply.get('active_language')}"
    assert state["language"] == locale
    assert not _sibling_keys(reply), f"{name} reply has localized sibling keys"
    if reply.get("agent_action"):
        assert len(reply["agent_action"]) <= 120
