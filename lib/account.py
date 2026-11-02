"""Account management tools (docs/tdd.md §4). Placeholder until the account build lands."""

from __future__ import annotations

from typing import Any


def _account_todo(name: str) -> dict[str, Any]:
    raise NotImplementedError(name)


def send_password_reset_link_impl(**kwargs: Any) -> dict[str, Any]:
    return _account_todo("send_password_reset_link")


def manage_mfa_impl(**kwargs: Any) -> dict[str, Any]:
    return _account_todo("manage_mfa")


def execute_suspend_restore_impl(**kwargs: Any) -> dict[str, Any]:
    return _account_todo("execute_suspend_restore")


def cancel_or_port_out_service_impl(**kwargs: Any) -> dict[str, Any]:
    return _account_todo("cancel_or_port_out_service")


def update_contact_profile_impl(**kwargs: Any) -> dict[str, Any]:
    return _account_todo("update_contact_profile")
