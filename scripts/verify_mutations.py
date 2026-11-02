#!/usr/bin/env python3
"""Gate 0 offline mutation and tool-breakage verifier.

Copies the whole repo (minus .git, virtualenvs, caches and run outputs) into a
`tempfile.TemporaryDirectory()` so the working tree is never modified, then:
  0. Runs `pytest` on the UNMUTATED copy. If that baseline fails, nothing below
     means anything (every mutation would look "caught"), so the run stops and
     fails loudly.
  1. Applies each policy mutation in `MUTATIONS` and verifies `pytest` fails.
     A mutation whose file or target string is missing is reported "skipped"
     (domain code not written yet), unless it is marked `required` (foundation
     code), in which case a missing target is an error: the mutation went stale.
     A mutation with `requires` only runs when that file contains that text.
  2. Injects a synthetic `SYSTEM_DOWN` error return into every `<tool>_impl` of
     `lib.services.ALL_TOOLS`, in whichever `lib/*.py` defines it (and in the
     tool's bundled wrapper), and verifies that tool's tests fail. Tools whose
     impl is still a placeholder (raises NotImplementedError) are skipped.

Usage:
  python3 scripts/verify_mutations.py [--root .] [--mutations-only]
  python3 scripts/verify_mutations.py --self-test
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTEST_TIMEOUT_SEC = 600

# Each mutation breaks one rule the agent must keep; the unit tests must notice.
#   file / target / replacement: replace `target` (or the first of `alt_targets`
#     found) with `replacement`; `count: -1` replaces every occurrence.
#   required: the target is foundation code; a missing target is an error.
#   requires: {"file", "contains"}: run only when that file contains that text.
MUTATIONS = [
    {
        "id": "speech_long_numbers_in_full",
        "description": "Stop cutting long numbers to their last 4 digits in lib/speech.py",
        "file": "lib/speech.py",
        "target": "return digits[-4:]",
        "replacement": "return match.group(0)",
        "required": True,
    },
    {
        "id": "core_require_login_always_passes",
        "description": "core.require_login lets every caller through (BR-TV-008)",
        "file": "lib/core.py",
        "target": '    if state.get("auth_status") == "pass" and state.get("logged_in") is not False:\n        return None',
        "replacement": "    return None",
        "required": True,
    },
    {
        "id": "core_validation_errors_never_escalate",
        "description": "validation_error never returns TOO_MANY_ERRORS on the third error (BR-TV-010)",
        "file": "lib/core.py",
        "target": "if count >= MAX_VALIDATION_ERRORS:",
        "replacement": "if False:",
        "required": True,
    },
    {
        "id": "core_language_lock_downgrades",
        "description": "A French call is downgraded to English when the model passes en-US (BR-TV-004)",
        "file": "lib/core.py",
        "target": '    if current and current != "en-US":\n        return current',
        "replacement": (
            '    if arg_lang and isinstance(state, dict):\n'
            '        state["language"] = arg_lang\n'
            '        return arg_lang\n'
            '    if current and current != "en-US":\n'
            '        return current'
        ),
        "required": True,
    },
    {
        "id": "core_mock_error_ignored",
        "description": "check_mock_error ignores the mock_error fault injection (PRD §17)",
        "file": "lib/core.py",
        "target": 'if str(state.get("mock_error") or "").strip():',
        "replacement": "if False:",
        "required": True,
    },
    {
        "id": "login_forget_wrong_codes",
        "description": "Stop counting wrong codes/PINs, so login is never locked, in lib/services.py",
        "file": "lib/services.py",
        "target": "failures = _failures(state) + 1",
        "replacement": "failures = 1",
        "required": True,
    },
    {
        "id": "login_reset_failures_on_account_switch",
        "description": "Switching accounts resets the failed-login counter and the lockout",
        "file": "lib/services.py",
        "target": '        state["step_up_verified"] = False\n',
        "replacement": (
            '        state["step_up_verified"] = False\n'
            '        state["auth_failure_count"] = 0\n'
            '        state["login_attempts"] = 0\n'
            '        state["auth_status"] = "none"\n'
        ),
        "required": True,
    },
    {
        "id": "login_survives_account_switch",
        "description": "Keep a login when the caller switches to another account",
        "file": "lib/services.py",
        "target": (
            '        state["auth_status"] = "none" if state.get("auth_status") != "locked" else "locked"\n'
            '        state["logged_in"] = False\n'
        ),
        "replacement": "        pass\n",
        "required": True,
    },
    {
        "id": "login_accept_any_code",
        "description": "Accept every login code in check_login_code",
        "file": "lib/services.py",
        "target": 'if not _credential_ok(state, digits, "code"):',
        "replacement": "if False:",
        "required": True,
    },
    {
        "id": "login_ignore_credential_on_file",
        "description": "Ignore fx_pin_on_file / fx_otp_on_file and use the ladder (docs/tdd.md §6)",
        "file": "lib/services.py",
        "target": "    if on_file:\n        return digits in on_file",
        "replacement": "    if False:\n        return digits in on_file",
        "required": True,
    },
    {
        "id": "login_accept_weak_codes",
        "description": "Accept codes made of one repeated digit in lib/fakes.py",
        "file": "lib/fakes.py",
        "target": "if digits in ALWAYS_WRONG_LOGIN_CODES or is_weak_code(digits):",
        "replacement": "if digits in ALWAYS_WRONG_LOGIN_CODES:",
        "required": True,
    },
    {
        "id": "lookup_blocked_caller_served",
        "description": "Blocked caller numbers are served like any caller (BR-TV-002)",
        "file": "lib/services.py",
        "target": "if digits in BLOCKED_CALLER_NUMBERS or norm_digits in BLOCKED_CALLER_NUMBERS:",
        "replacement": "if False:",
        "required": True,
    },
    {
        "id": "lookup_business_fixture_ignored",
        "description": "lookup_account ignores fx_business_account (BR-TV-012)",
        "file": "lib/services.py",
        "target": 'business = bool(account.get("business_flag")) or fixture_flag(state, "fx_business_account")',
        "replacement": 'business = bool(account.get("business_flag"))',
        "required": True,
    },
    {
        "id": "handover_fraud_without_empathy",
        "description": "Fraud handover skips the empathy_protocol line (BR-TV-013)",
        "file": "lib/services.py",
        "target": '"fraud_escalation": ("empathy_protocol", "live_agent_handoff"),',
        "replacement": '"fraud_escalation": ("live_agent_handoff",),',
        "required": True,
    },
    {
        "id": "handover_refund_wrong_line",
        "description": "Refund-threshold handover speaks the generic line instead of transfer_to_specialist",
        "file": "lib/services.py",
        "target": '"refund_threshold_exceeded": ("refund_over_limit", "transfer_to_specialist"),',
        "replacement": '"refund_threshold_exceeded": ("refund_over_limit", "live_agent_handoff"),',
        "required": True,
    },
    {
        "id": "handover_no_session_context",
        "description": "handover_to_person stops writing handoff_context (BR-TV-015)",
        "file": "lib/services.py",
        "target": 'state["handoff_context"] = json.dumps(context, ensure_ascii=False)',
        "replacement": 'state["handoff_context"] = ""',
        "required": True,
    },
    # Domain modules: skipped until the builder's code lands.
    *[
        {
            "id": f"{domain}_skips_login",
            "description": f"Every tool in lib/{domain}.py skips core.require_login (BR-TV-008)",
            "file": f"lib/{domain}.py",
            "target": "require_login(",
            "replacement": "(lambda *_a, **_k: None)(",
            "count": -1,
        }
        for domain in ("billing", "tech", "sales", "account")
    ],
    {
        "id": "billing_refund_threshold_dropped",
        "description": "Self-serve adjustments ignore the refund threshold (prd.md §10, decision A1)",
        "file": "lib/fakes.py",
        "target": 'SELF_SERVE_ADJUSTMENT_LIMIT = "25.00"',
        "replacement": 'SELF_SERVE_ADJUSTMENT_LIMIT = "1000000.00"',
        "requires": {"file": "lib/billing.py", "contains": "SELF_SERVE_ADJUSTMENT_LIMIT"},
    },
]

# Copied into the temp workspace: everything except these (top level) and caches.
_SKIP_TOP = {".git", ".venv", "venv", "node_modules", "history", ".claude"}
_SKIP_ANY = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
_SKIP_FILES = {".coverage", "coverage.json"}


def _find_python(repo_root: Path) -> str:
    """Interpreter for the mutated copies: $PYTHON, the repo's .venv, else this interpreter."""
    env_python = os.environ.get("PYTHON", "").strip()
    if env_python:
        # The Makefile may pass a command like "uv run --no-sync python"; only a
        # plain executable path can be used here.
        candidate = Path(env_python)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    venv_python = repo_root / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def _copy_workspace(src_root: Path, dst_root: Path) -> None:
    """Copy the repo (scripts/, bootstrap/, bench/ included: tests import them)."""

    def _ignore(dirpath: str, names: list[str]) -> set[str]:
        here = Path(dirpath).resolve()
        skipped = {n for n in names if n in _SKIP_ANY or n in _SKIP_FILES or n.endswith(".pyc")}
        if here == src_root.resolve():
            skipped |= {n for n in names if n in _SKIP_TOP}
        if here == (src_root / "bench").resolve():
            skipped |= {n for n in names if n == "runs"}
        return skipped

    shutil.copytree(src_root, dst_root, ignore=_ignore, dirs_exist_ok=True, symlinks=True)


def _pytest(python_bin: str, cwd: Path, targets: list[str] | None = None, stop_first: bool = True):
    cmd = [python_bin, "-B", "-m", "pytest", "-q", "-o", "addopts=", "-p", "no:cacheprovider"]
    if stop_first:
        cmd.append("-x")
    cmd.extend(targets or [])
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=PYTEST_TIMEOUT_SEC, check=False)


def patch_function_to_return_error(source_text: str, tool_name: str) -> str:
    """Insert an immediate `SYSTEM_DOWN` error return at the start of `<tool_name>_impl`."""
    func_name = f"{tool_name}_impl"
    pattern = re.compile(
        rf"(^def {re.escape(func_name)}\b[\s\S]*?\)\s*(?:->\s*[^:]+)?:[^\n]*\n(?:\s*\"\"\"[\s\S]*?\"\"\"\n)?)",
        re.MULTILINE,
    )
    match = pattern.search(source_text)
    if not match:
        raise ValueError(f"Could not locate function header for {func_name}")
    injection = (
        '    return {"status": "error", "error": "SYSTEM_DOWN", '
        '"message": "injected breakage", "agent_action": "ESCALATE_SYSTEM_UNAVAILABLE"}\n'
    )
    return source_text[: match.end()] + injection + source_text[match.end() :]


def _resolve_target_str(mut: dict, content: str) -> str | None:
    candidates = [mut["target"]]
    if mut.get("alt_target"):
        candidates.append(mut["alt_target"])
    candidates.extend(mut.get("alt_targets", []))
    for cand in candidates:
        if cand and cand in content:
            return cand
    return None


def _impl_owner(lib_dir: Path, tool_name: str) -> Path | None:
    """The lib/*.py file that defines `<tool>_impl` (services.py or a domain module)."""
    pattern = re.compile(rf"^def {re.escape(tool_name)}_impl\b", re.MULTILINE)
    for path in sorted(lib_dir.glob("*.py")):
        if pattern.search(path.read_text(encoding="utf-8")):
            return path
    return None


_PROBE = r"""
import inspect, json
import lib.services as s
names = list(getattr(s, "ALL_TOOLS", ()) or [n[:-5] for n in dir(s) if n.endswith("_impl")])
out = {}
for n in names:
    fn = getattr(s, n + "_impl", None)
    if fn is None:
        out[n] = "missing"
        continue
    kw = {p.name: "" for p in inspect.signature(fn).parameters.values()
          if p.name not in ("state", "session_state", "language") and p.kind not in (p.VAR_KEYWORD, p.VAR_POSITIONAL)
          and p.default is p.empty}
    try:
        fn(**kw, state={"mock_error": "SYSTEM_DOWN"})
        out[n] = "implemented"
    except NotImplementedError:
        out[n] = "placeholder"
    except Exception as exc:
        out[n] = "implemented"
print(json.dumps(out))
"""


def _probe_tools(python_bin: str, root: Path) -> dict[str, str]:
    """tool -> implemented / placeholder / missing, from lib.services in the copy."""
    if not (root / "lib" / "services.py").exists():
        return {}
    proc = subprocess.run(
        [python_bin, "-B", "-c", _PROBE], cwd=root, capture_output=True, text=True, timeout=120, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(f"could not import lib.services in the copy:\n{proc.stderr[-2000:]}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _apply_mutation(tmp_root: Path, mut: dict) -> tuple[str, str, str | None]:
    """Return (status, reason, original_content). status: apply / skipped / error."""
    req = mut.get("requires")
    if req:
        req_path = tmp_root / req["file"]
        if not req_path.exists() or req["contains"] not in req_path.read_text(encoding="utf-8"):
            return "skipped", f"{req['file']} does not contain {req['contains']!r} yet", None
    target_path = tmp_root / mut["file"]
    if not target_path.exists():
        status = "error" if mut.get("required") else "skipped"
        return status, f"file not found: {mut['file']}", None
    original = target_path.read_text(encoding="utf-8")
    target_str = _resolve_target_str(mut, original)
    if target_str is None:
        status = "error" if mut.get("required") else "skipped"
        return status, f"target not found in {mut['file']}", None
    mutated = original.replace(target_str, mut["replacement"], mut.get("count", 1))
    target_path.write_text(mutated, encoding="utf-8")
    return "apply", "", original


def run_mutations(
    repo_root: Path,
    mutations: list[dict] | None = None,
    include_tool_breakages: bool = True,
) -> dict:
    python_bin = _find_python(repo_root)
    active_mutations = MUTATIONS if mutations is None else mutations
    results: list[dict] = []
    tool_results: list[dict] = []

    with tempfile.TemporaryDirectory(prefix="gecx_mutations_") as tmp:
        tmp_root = Path(tmp)
        _copy_workspace(repo_root, tmp_root)

        baseline = _pytest(python_bin, tmp_root, stop_first=False)
        if baseline.returncode != 0:
            tail = (baseline.stdout + baseline.stderr)[-3000:]
            return {
                "baseline_passed": False,
                "baseline_exit_code": baseline.returncode,
                "baseline_output_tail": tail,
                "all_caught": False,
                "total_mutations": 0,
                "caught_mutations": 0,
                "skipped_mutations": 0,
                "total_tool_breakages": 0,
                "caught_tool_breakages": 0,
                "results": [],
                "tool_breakages": [],
            }

        for mut in active_mutations:
            status, reason, original = _apply_mutation(tmp_root, mut)
            row = {"id": mut["id"], "description": mut.get("description", "")}
            if status != "apply":
                row.update({"status": status, "caught": False, "reason": reason})
                results.append(row)
                continue
            try:
                proc = _pytest(python_bin, tmp_root)
            finally:
                (tmp_root / mut["file"]).write_text(original, encoding="utf-8")
            caught = proc.returncode != 0
            row.update({"status": "caught" if caught else "missed", "caught": caught, "exit_code": proc.returncode})
            results.append(row)

        if include_tool_breakages and (tmp_root / "lib" / "services.py").exists():
            kinds = _probe_tools(python_bin, tmp_root)
            for tool_name, kind in kinds.items():
                if kind != "implemented":
                    tool_results.append({"tool": tool_name, "status": "skipped", "caught": False, "reason": kind})
                    continue
                owner = _impl_owner(tmp_root / "lib", tool_name)
                if owner is None:
                    tool_results.append(
                        {"tool": tool_name, "status": "skipped", "caught": False, "reason": "no `def <tool>_impl` in lib/*.py"}
                    )
                    continue
                candidates = [f"test_{tool_name}.py", f"test_{owner.stem}.py", "test_services.py"]
                test_targets = sorted({f"tests/{c}" for c in candidates if (tmp_root / "tests" / c).exists()})
                if not test_targets:
                    tool_results.append({"tool": tool_name, "status": "missed", "caught": False, "reason": "no test file"})
                    continue
                orig_owner = owner.read_text(encoding="utf-8")
                bundled_path = tmp_root / "cxas_app" / "tools" / tool_name / "python_function" / "python_code.py"
                orig_bundled = bundled_path.read_text(encoding="utf-8") if bundled_path.exists() else None
                try:
                    owner.write_text(patch_function_to_return_error(orig_owner, tool_name), encoding="utf-8")
                    if orig_bundled is not None:
                        try:
                            bundled_path.write_text(
                                patch_function_to_return_error(orig_bundled, tool_name), encoding="utf-8"
                            )
                        except ValueError:
                            pass
                    proc = _pytest(python_bin, tmp_root, test_targets)
                finally:
                    owner.write_text(orig_owner, encoding="utf-8")
                    if orig_bundled is not None:
                        bundled_path.write_text(orig_bundled, encoding="utf-8")
                caught = proc.returncode != 0
                tool_results.append(
                    {
                        "tool": tool_name,
                        "file": str(owner.relative_to(tmp_root)),
                        "status": "caught" if caught else "missed",
                        "caught": caught,
                        "exit_code": proc.returncode,
                        "tests": test_targets,
                    }
                )

    ran = [r for r in results if r["status"] in ("caught", "missed")]
    ran_tools = [r for r in tool_results if r["status"] in ("caught", "missed")]
    failures = [r for r in results + tool_results if r["status"] in ("missed", "error")]
    return {
        "baseline_passed": True,
        "total_mutations": len(ran),
        "caught_mutations": sum(1 for r in ran if r["caught"]),
        "skipped_mutations": sum(1 for r in results if r["status"] == "skipped"),
        "stale_mutations": [r["id"] for r in results if r["status"] == "error"],
        "total_tool_breakages": len(ran_tools),
        "caught_tool_breakages": sum(1 for r in ran_tools if r["caught"]),
        "skipped_tool_breakages": sum(1 for r in tool_results if r["status"] == "skipped"),
        "all_caught": not failures and bool(ran or ran_tools),
        "results": results,
        "tool_breakages": tool_results,
    }


def self_test() -> int:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for sub in ("lib", "tests", "scripts"):
            (root / sub).mkdir()
            (root / sub / "__init__.py").write_text("", encoding="utf-8")
        (root / "tests" / "__init__.py").unlink()
        (root / ".git").mkdir()  # never copied
        (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        (root / "lib" / "wording.py").write_text(
            'GREETING = "Hello, thanks for calling."\nUNUSED = "unused"\n', encoding="utf-8"
        )
        (root / "lib" / "services.py").write_text(
            "from lib.domain import other_tool_impl  # noqa: F401\n"
            'ALL_TOOLS = ("demo_tool", "other_tool", "todo_tool")\n'
            "def demo_tool_impl(x: str = '', state=None) -> dict:\n"
            '    return {"status": "ok", "agent_action": "DONE", "data": {"x": x}}\n'
            "def todo_tool_impl(**kwargs) -> dict:\n"
            "    raise NotImplementedError('todo_tool')\n",
            encoding="utf-8",
        )
        (root / "lib" / "domain.py").write_text(
            "def other_tool_impl(y: str, state=None) -> dict:\n"
            '    return {"status": "ok", "data": {"y": y}}\n',
            encoding="utf-8",
        )
        # A kit script that a test imports: the copy must include scripts/.
        (root / "scripts" / "helper.py").write_text("VALUE = 3\n", encoding="utf-8")
        (root / "tests" / "test_wording.py").write_text(
            "from lib.wording import GREETING\n"
            "from scripts import helper\n"
            "def test_greeting():\n"
            '    assert GREETING == "Hello, thanks for calling." and helper.VALUE == 3\n',
            encoding="utf-8",
        )
        (root / "tests" / "test_services.py").write_text(
            "from lib.services import demo_tool_impl\n"
            "def test_demo():\n"
            '    assert demo_tool_impl("a")["status"] == "ok"\n',
            encoding="utf-8",
        )
        (root / "tests" / "test_domain.py").write_text(
            "from lib.domain import other_tool_impl\n"
            "def test_other():\n"
            '    assert other_tool_impl("b")["status"] == "ok"\n',
            encoding="utf-8",
        )
        good_muts = [
            {"id": "m_caught", "file": "lib/wording.py", "target": '"Hello, thanks for calling."',
             "replacement": '"Hi, thanks for calling."', "required": True},
            {"id": "m_not_yet", "file": "lib/billing.py", "target": "require_login(", "replacement": "x("},
            {"id": "m_gated", "file": "lib/wording.py", "target": '"unused"', "replacement": '"changed"',
             "requires": {"file": "lib/domain.py", "contains": "THRESHOLD"}},
        ]
        summary = run_mutations(root, mutations=good_muts, include_tool_breakages=True)
        assert summary["baseline_passed"] is True, summary
        assert summary["all_caught"] is True, f"Expected all_caught=True, got {summary}"
        assert summary["caught_mutations"] == 1 and summary["skipped_mutations"] == 2, summary
        by_tool = {r["tool"]: r for r in summary["tool_breakages"]}
        assert by_tool["demo_tool"]["status"] == "caught", by_tool
        assert by_tool["other_tool"]["status"] == "caught" and by_tool["other_tool"]["file"] == "lib/domain.py", by_tool
        assert by_tool["todo_tool"]["status"] == "skipped", by_tool

        summary_miss = run_mutations(
            root,
            mutations=[{"id": "m_missed", "file": "lib/wording.py", "target": '"unused"', "replacement": '"changed"'}],
            include_tool_breakages=False,
        )
        assert summary_miss["all_caught"] is False, "Expected uncaught mutation to fail"

        stale = run_mutations(
            root,
            mutations=[{"id": "m_stale", "file": "lib/wording.py", "target": "GONE", "replacement": "x", "required": True}],
            include_tool_breakages=False,
        )
        assert stale["all_caught"] is False and stale["stale_mutations"] == ["m_stale"], stale

        # A failing baseline stops the run instead of counting every mutation as caught.
        (root / "tests" / "test_broken.py").write_text("def test_broken():\n    assert False\n", encoding="utf-8")
        broken = run_mutations(root, mutations=good_muts, include_tool_breakages=True)
        assert broken["baseline_passed"] is False and broken["all_caught"] is False, broken
        assert broken["caught_mutations"] == 0

    print("OK (verify_mutations self-test)")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--root", default=None)
    p.add_argument("--app", default=None, help="Optional path to cxas_app directory")
    p.add_argument("--tests", default=None, help="Optional path to tests directory")
    p.add_argument("--mutations-only", action="store_true")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.root:
        root_dir = Path(args.root).resolve()
    elif args.app:
        root_dir = Path(args.app).resolve().parent
    elif args.tests:
        root_dir = Path(args.tests).resolve().parent
    else:
        root_dir = REPO_ROOT
    summary = run_mutations(
        root_dir,
        include_tool_breakages=not args.mutations_only,
    )
    print(json.dumps(summary, indent=2))
    if not summary.get("baseline_passed", True):
        print(
            "verify_mutations: FAIL - the unmutated test suite does not pass in the copied workspace; "
            "fix it first (every mutation would otherwise look caught).",
            file=sys.stderr,
        )
    elif summary.get("stale_mutations"):
        print(f"verify_mutations: FAIL - stale required mutations: {summary['stale_mutations']}", file=sys.stderr)
    return 0 if summary["all_caught"] else 1


if __name__ == "__main__":
    sys.exit(main())
