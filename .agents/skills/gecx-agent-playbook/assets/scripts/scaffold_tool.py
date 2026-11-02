#!/usr/bin/env python3
"""Write a tool's JSON and thin python wrapper from a small JSON spec.

The wrapper reads the session state from the platform `context`, passes every
argument through to `<name>_impl` (from lib/<module>.py, bundled by `make bundle`),
and follows DESIGN_RULES rule 32: union types on numeric/code args and no
`from __future__ import annotations`.

Spec (JSON file or stdin):
{
  "name": "process_bill_payment",
  "module": "billing",
  "description": "What it does and when to call it (one or two sentences).",
  "params": [
    {"name": "amount", "type": "str | int | float", "default": "", "doc": "Amount to pay; empty = full balance."},
    {"name": "payment_method", "type": "str", "default": "card_on_file", "doc": "card_on_file, new_card or bank_account."}
  ],
  "returns": "status, data (...), error_message, tracking_id. Errors add error and agent_action."
}
`language` is appended automatically as the last parameter.

Usage: python scripts/scaffold_tool.py spec.json [--app-dir cxas_app]
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path


def _wrap(text: str, indent: str, width: int = 88) -> str:
    return "\n".join(textwrap.wrap(text, width=width, initial_indent=indent, subsequent_indent=indent + "  "))


def render_wrapper(spec: dict) -> str:
    name = spec["name"]
    params = list(spec.get("params", []))
    params.append({"name": "language", "type": "str", "default": "", "doc": "Active language code (en-US or fr-CA)."})
    sig_lines = []
    for p in params:
        default = p.get("default", None)
        if default is None:
            sig_lines.append(f"    {p['name']}: {p['type']},")
        else:
            sig_lines.append(f"    {p['name']}: {p['type']} = {json.dumps(default)},")
    doc_args = "\n".join(_wrap(f"{p['name']}: {p['doc']}", "      ") for p in params)
    call_args = "\n".join(f"        {p['name']}={p['name']}," for p in params)
    desc = _wrap(spec["description"], "    ").lstrip()
    returns = _wrap(spec.get("returns", "status, data, error_message and tracking_id."), "      ")
    return (
        "from typing import Any\n\n\n\n"
        f"def {name}(\n" + "\n".join(sig_lines) + "\n) -> dict[str, Any]:\n"
        f'    """{desc}\n\n'
        "    Args:\n"
        f"{doc_args}\n\n"
        "    Returns:\n"
        f"{returns}\n"
        '    """\n'
        '    ctx = globals().get("context")\n'
        '    state = getattr(ctx, "state", None) if ctx is not None else None\n'
        "    if state is None and isinstance(ctx, dict):\n"
        "        state = ctx\n"
        f"    return {name}_impl(\n"
        f"{call_args}\n"
        "        state=state,\n"
        "    )\n\n\n"
        "# --- BEGIN GENERATED SHARED BUNDLE (edit lib/, then run `make bundle`) ---\n"
        f"# uses: from lib.{spec.get('module', 'services')} import {name}_impl\n"
        "# --- END GENERATED SHARED BUNDLE ---\n"
    )


def render_json(spec: dict) -> str:
    name = spec["name"]
    return json.dumps(
        {
            "name": name,
            "displayName": name,
            "executionType": "SYNCHRONOUS",
            "pythonFunction": {
                "name": name,
                "description": spec["description"],
                "pythonCode": f"tools/{name}/python_function/python_code.py",
            },
        },
        indent=2,
        ensure_ascii=False,
    ) + "\n"


def write_tool(spec: dict, app_dir: Path) -> Path:
    tool_dir = app_dir / "tools" / spec["name"]
    (tool_dir / "python_function").mkdir(parents=True, exist_ok=True)
    (tool_dir / f"{spec['name']}.json").write_text(render_json(spec), encoding="utf-8")
    (tool_dir / "python_function" / "python_code.py").write_text(render_wrapper(spec), encoding="utf-8")
    return tool_dir


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("spec", nargs="?", help="Spec JSON file (default: stdin). A JSON list writes several tools.")
    ap.add_argument("--app-dir", default="cxas_app")
    args = ap.parse_args()
    raw = Path(args.spec).read_text(encoding="utf-8") if args.spec else sys.stdin.read()
    specs = json.loads(raw)
    for spec in specs if isinstance(specs, list) else [specs]:
        print(write_tool(spec, Path(args.app_dir)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
