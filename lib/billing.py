"""Billing tools (docs/tdd.md §4 Billing). Placeholder until the billing build lands."""

from __future__ import annotations

from typing import Any


def _billing_todo(name: str) -> dict[str, Any]:
    raise NotImplementedError(name)


def get_billing_summary_impl(**kwargs: Any) -> dict[str, Any]:
    return _billing_todo("get_billing_summary")


def process_bill_payment_impl(**kwargs: Any) -> dict[str, Any]:
    return _billing_todo("process_bill_payment")


def setup_autopay_impl(**kwargs: Any) -> dict[str, Any]:
    return _billing_todo("setup_autopay")


def apply_bill_adjustment_impl(**kwargs: Any) -> dict[str, Any]:
    return _billing_todo("apply_bill_adjustment")


def setup_payment_arrangement_impl(**kwargs: Any) -> dict[str, Any]:
    return _billing_todo("setup_payment_arrangement")


def verify_payment_and_restore_impl(**kwargs: Any) -> dict[str, Any]:
    return _billing_todo("verify_payment_and_restore")
