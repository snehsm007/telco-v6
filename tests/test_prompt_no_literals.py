from pathlib import Path
import re

from lib.fakes import ACCOUNTS

APP_DIR = Path(__file__).resolve().parent.parent / "cxas_app"
FORBIDDEN_NAMES = (
    *(acc.get("first_name", "") for acc in ACCOUNTS if acc.get("first_name")),
    "Jordan",
    "Alex",
    "Marie",
    "Carlos",
    "Smith",
    "Rivera",
)
FORBIDDEN_IDS = (
    *(acc.get("account_id", "") for acc in ACCOUNTS if acc.get("account_id")),
    "A1001",
    "A1002",
    "ACC-1001",
    "ACC-1002",
)
_ALLOWED_PROMPT_PATTERNS = (
    re.compile(r"<[^>]+>"),
    re.compile(r"\{[^}]+\}"),
    re.compile(r"\b\d+-digit\b", re.IGNORECASE),
    re.compile(r"\b(?:\w+_)?last[ -]?4(?:\s+digits)?\b", re.IGNORECASE),
    re.compile(r"\b2FA\b", re.IGNORECASE),
    re.compile(r"\b[a-z]{2}-[A-Z]{2}(?:-[A-Za-z0-9]+)?\b"),
    re.compile(r"\b[a-z]{2}-419\b", re.IGNORECASE),
    re.compile(r"\bstep[_\s-]*\d+\b", re.IGNORECASE),
    re.compile(r"\bM\d+\b"),
    re.compile(r"\b1-800-[0-9-]+\b"),
    re.compile(r"\b24/7\b"),
    re.compile(r"\b24\b"),
    re.compile(r"\b[1-4]\b"),
    re.compile(r"(?m)^\s*\d+\.\s"),
    # Inline ordered lists ("...: 1. safety; 2. fraud; ... 10. closing") are ranks, not facts.
    re.compile(r"(?:(?<=[:;])\s|(?<=:)\s?)\d+\.\s"),
)


def _strip_allowed(text: str, prd_digits: set[str] | None = None) -> str:
    cleaned = text
    for pat in _ALLOWED_PROMPT_PATTERNS:
        cleaned = pat.sub(" ", cleaned)
    for num in prd_digits or ():
        cleaned = re.sub(rf"\b{re.escape(str(num))}\b", " ", cleaned)
    return cleaned


def test_prompts_contain_no_literals_or_defect_ids() -> None:
    prompt_files = [
        APP_DIR / "global_instruction.txt",
        *sorted((APP_DIR / "agents").rglob("instruction.txt")),
    ]
    assert len(prompt_files) >= 3
    for path in prompt_files:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\b\d{4,}\b", text), f"{path} contains a 4+ digit number"
        assert not re.findall(r"\b\d+\b", _strip_allowed(text)), f"{path} contains unallowed digits"
        assert not re.search(r"\b(?:DEF|VE|HE|BUG)-\d+\b", text), f"{path} contains a tracker ID"
        for name in FORBIDDEN_NAMES:
            assert not re.search(rf"\b{re.escape(name)}\b", text), f"{path} contains fake name {name}"
        for acc_id in FORBIDDEN_IDS:
            assert acc_id not in text, f"{path} contains fake account ID {acc_id}"


AGENTS = ("router", "billing", "tech_support", "sales_equipment", "account")


def _is_placeholder(text: str) -> bool:
    """Domain prompts start as a 3-line placeholder until their builder lands."""
    return "Placeholder for the" in text and "<taskflow>" not in text


def test_every_agent_has_a_prompt_and_router_is_m1_only() -> None:
    for name in AGENTS:
        assert (APP_DIR / "agents" / name / "instruction.txt").is_file(), f"missing prompt for {name}"
    router_txt = (APP_DIR / "agents" / "router" / "instruction.txt").read_text(encoding="utf-8")
    router_subtasks = re.findall(r'<subtask name="([^"]+)">', router_txt)
    assert router_subtasks and all(name.startswith("M1 ") for name in router_subtasks)
    assert "first_name" not in router_txt
    assert "{@TOOL: lookup_account}" in router_txt
    assert "restricted_caller" in router_txt


def test_handover_pairing_in_global_and_every_written_agent_prompt() -> None:
    global_txt = (APP_DIR / "global_instruction.txt").read_text(encoding="utf-8")
    texts = {"global_instruction": global_txt}
    for name in AGENTS:
        txt = (APP_DIR / "agents" / name / "instruction.txt").read_text(encoding="utf-8")
        if not _is_placeholder(txt):
            texts[name] = txt
    assert "router" in texts
    for label, txt in texts.items():
        assert "{@TOOL: end_session}" in txt, f"{label} never ends the session"
        if label in ("global_instruction", "router"):
            assert "{@TOOL: handover_to_person}" in txt, f"{label} has no handover"
            assert "handoff_message" in txt, f"{label} does not speak handoff_message"
        if "{@TOOL: handover_to_person}" in txt:
            assert "handoff_message" in txt, f"{label} hands over without speaking handoff_message"
    # Removed scaffold names must not come back.
    for label, txt in texts.items():
        assert "submit_request" not in txt, label
        assert "specialist}" not in txt and "@AGENT: specialist" not in txt, label


def test_login_recovery_steps_never_dead_end() -> None:
    """Callers without a number or a reachable phone get a way to verify (DESIGN_RULES rules 2, 21)."""
    global_txt = (APP_DIR / "global_instruction.txt").read_text(encoding="utf-8")
    router_txt = (APP_DIR / "agents" / "router" / "instruction.txt").read_text(encoding="utf-8")
    cant_arrive = re.search(r'<step name="Code Can\'t Arrive">(.*?)</step>', global_txt, re.S)
    assert cant_arrive and 'channel "email"' in cant_arrive.group(1) and "TOO_MANY_ATTEMPTS" in cant_arrive.group(1)
    need_account = re.search(r'<step name="Need Account">(.*?)</step>', global_txt, re.S)
    assert need_account and "no number" in need_account.group(1)
    assert "check_secret_pin" in need_account.group(1) and "spoken_message" in need_account.group(1)
    no_number = re.search(r'<step name="No Number">(.*?)</step>', router_txt, re.S)
    assert no_number and "email" in no_number.group(1) and "silently" in no_number.group(1)


def test_router_uses_caller_id_when_the_caller_gives_a_non_number() -> None:
    """Live call: a date of birth instead of a number must not get the same question again."""
    router_txt = (APP_DIR / "agents" / "router" / "instruction.txt").read_text(encoding="utf-8")
    step = re.search(r'<step name="Not A Number">(.*?)</step>', router_txt, re.S)
    assert step, "router has no Not A Number step"
    body = step.group(1)
    assert "date of birth" in body and "Never ask the same question again" in body
    assert '{@TOOL: lookup_account} with phone_or_account set to ""' in body and "once per call" in body.lower()
    assert "- en-US:" in body and "- fr-CA:" in body
    assert "not_a_number line said together with {@TOOL: lookup_account}" in router_txt


def test_router_reads_stt_mangled_french_cancellation_as_account() -> None:
    """Phone STT renders "annuler mon forfait" as "un autre mois forfait"; that is a cancellation, not sales."""
    router_txt = (APP_DIR / "agents" / "router" / "instruction.txt").read_text(encoding="utf-8")
    easy = router_txt.split("Easy to mix up:", 1)[1].split("</taxonomy>", 1)[0]
    hint = next(line for line in easy.splitlines() if "un autre mois" in line)
    assert "annuler mon" in hint and "annulé mon" in hint and "(account)" in hint and "cancelling" in hint


def test_tech_support_keeps_the_outage_text_promise_without_an_account() -> None:
    tech_txt = (APP_DIR / "agents" / "tech_support" / "instruction.txt").read_text(encoding="utf-8")
    send = re.search(r'<step name="Send Text">(.*?)</step>', tech_txt, re.S)
    sent = re.search(r'<step name="Text Sent">(.*?)</step>', tech_txt, re.S)
    assert send and "mobile_number" in send.group(1) and "need no account" in send.group(1)
    assert sent and "spoken_message" in sent.group(1) and "word for word" in sent.group(1)
