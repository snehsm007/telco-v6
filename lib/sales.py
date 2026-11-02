"""Sales and equipment tools (docs/tdd.md §4). Placeholder until the sales build lands."""

from __future__ import annotations

from typing import Any


def _sales_todo(name: str) -> dict[str, Any]:
    raise NotImplementedError(name)


def browse_plans_impl(**kwargs: Any) -> dict[str, Any]:
    return _sales_todo("browse_plans")


def place_order_impl(**kwargs: Any) -> dict[str, Any]:
    return _sales_todo("place_order")


def file_warranty_claim_impl(**kwargs: Any) -> dict[str, Any]:
    return _sales_todo("file_warranty_claim")


def start_number_transfer_impl(**kwargs: Any) -> dict[str, Any]:
    return _sales_todo("start_number_transfer")
