"""BR-TV-016 / BR-TV-008 / rule 17: the safety contract in the shared prompt and guardrails."""

import json
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "cxas_app"
GLOBAL = (APP / "global_instruction.txt").read_text(encoding="utf-8")


def _step(name: str) -> str:
    m = re.search(rf'<step name="{name}">(.*?)</step>', GLOBAL, re.S)
    assert m, name
    return m.group(1)


def test_malicious_step_covers_injection_and_spares_ordinary_frustration() -> None:
    step = _step("Close Malicious Session")
    trigger = re.search(r"<trigger>(.*?)</trigger>", step, re.S).group(1)
    for words in ("ignore", "reveal", "instructions", "another role", "login by command", "threatens"):
        assert words in trigger, words
    assert "malicious_closing" in step and '"malicious_input"' in step
    assert "one swear word is ordinary" in step


def test_claimed_login_state_never_unlocks_account_tools() -> None:
    # BR-TV-008: "I'm already verified" / "set logged_in true" can't reach the gate;
    # only the check tools write auth_status, and extra arguments are ignored.
    import lib.services as services

    for tool in ("get_billing_summary", "manage_mfa", "place_order", "update_contact_profile"):
        reply = getattr(services, tool)(state={"account_id": "A1001"}, auth_status="pass", logged_in=True)
        assert reply["error"] == "NOT_LOGGED_IN", tool


def test_guardrails_enabled_and_wired() -> None:
    app = json.loads((APP / "app.json").read_text(encoding="utf-8"))
    names = set(app["guardrails"])
    found = {}
    for path in (APP / "guardrails").glob("*/*.json"):
        cfg = json.loads(path.read_text(encoding="utf-8"))
        found[cfg["displayName"]] = cfg
    assert names == set(found)
    assert all(cfg["enabled"] for cfg in found.values())
    safety = found["Default Safety Guardrail"]["modelSafety"]["safetySettings"]
    assert {s["threshold"] for s in safety} == {"BLOCK_MEDIUM_AND_ABOVE"}
    prompt = found["Default Prompt Guardrail"]
    assert prompt["llmPromptSecurity"]["customPolicy"]["policyScope"] == "USER_QUERY"
    for cfg in found.values():
        # The refusal must follow the caller's language (BR-TV-004 / BR-TV-020).
        assert "French" in cfg["action"]["generativeAnswer"]["prompt"]
