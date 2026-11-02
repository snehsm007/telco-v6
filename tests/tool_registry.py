"""Helpers for tests that iterate over lib.services.ALL_TOOLS.

Domain tools start as placeholders that raise NotImplementedError. `implemented_tools()`
probes each impl once (with mock_error set, so a real impl returns at its first line)
and skips placeholders, so these tests cover every domain tool automatically once
its builder lands.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable

import lib.services as services

INTERNAL_PARAMS = ("state", "session_state", "language")

# docs/tdd.md §4: account-reading and account-mutating tools (need auth_status=pass).
LOGIN_REQUIRED = frozenset(
    {
        "get_billing_summary",
        "process_bill_payment",
        "setup_autopay",
        "apply_bill_adjustment",
        "setup_payment_arrangement",
        "verify_payment_and_restore",
        "run_virtual_repair",
        "get_appointment_and_ticket_status",
        "manage_appointment",
        "place_order",
        "file_warranty_claim",
        "manage_mfa",
        "execute_suspend_restore",
        "cancel_or_port_out_service",
        "update_contact_profile",
    }
)


def impl(name: str) -> Callable[..., dict[str, Any]]:
    return getattr(services, f"{name}_impl")


def tool_params(name: str) -> list[str]:
    """The tool's own parameters (what the wrapper exposes besides `language`)."""
    sig = inspect.signature(impl(name))
    return [
        p.name
        for p in sig.parameters.values()
        if p.name not in INTERNAL_PARAMS and p.kind not in (p.VAR_KEYWORD, p.VAR_POSITIONAL)
    ]


def call(name: str, state: dict[str, Any], language: str = "", **args: Any) -> dict[str, Any]:
    """Call an impl with every tool parameter defaulting to an empty string."""
    kwargs = {p: "" for p in tool_params(name)}
    kwargs.update(args)
    return impl(name)(**kwargs, state=state, language=language)


def is_implemented(name: str) -> bool:
    try:
        call(name, {"mock_error": "SYSTEM_DOWN"})
    except NotImplementedError:
        return False
    return True


def implemented_tools() -> list[str]:
    return [name for name in services.ALL_TOOLS if is_implemented(name)]
