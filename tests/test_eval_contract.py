"""Unit tests for scripts/eval_contract.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.eval_contract import (
    _is_uncustomized_starter_fakes,
    _load_fakes_module,
    check_eval_contract,
    extract_eval_facts,
    main,
)
from scripts.kickstart import kickstart

REPO_ROOT = Path(__file__).resolve().parents[1]


FAKES_TEMPLATE = """\
ACCOUNTS = {
    "ACC-1001": {
        "account_id": "ACC-1001",
        "phone": "2025550143",
        "first_name": "Jordan",
    },
    "ACC-1002": {
        "account_id": "ACC-1002",
        "phone": "2025550198",
        "first_name": "Taylor",
    },
}

VALID_PINS = frozenset({"7391", "5678"})
VALID_OTPS = frozenset({"604213", "654321"})
ALWAYS_WRONG_LOGIN_CODES = frozenset({"0000", "000000", "9999", "999999"})


def normalize_code(code: str) -> str:
    return "".join(ch for ch in str(code or "") if ch.isdigit())


def login_code_accepted(code: str, attempts: int = 0) -> bool:
    digits = normalize_code(code)
    if digits in ALWAYS_WRONG_LOGIN_CODES or len(digits) < 4:
        return False
    if attempts >= 1:
        return digits in (VALID_PINS | VALID_OTPS)
    return True
"""


def _write_eval(evals_dir: Path, name: str, payload: dict) -> Path:
    path = evals_dir / name / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_matching_fakes_and_evals_pass(tmp_path: Path) -> None:
    fakes = tmp_path / "fakes.py"
    fakes.write_text(FAKES_TEMPLATE, encoding="utf-8")
    evals_dir = tmp_path / "bench" / "dev" / "evaluations"

    _write_eval(
        evals_dir,
        "sim_first_try",
        {
            "displayName": "sim_first_try",
            "scenario": {
                "task": "Check balance. Provide OTP code 604213 when asked.",
                "userFacts": ["Phone: 202-555-0143", "Account ID: ACC-1001"],
            },
        },
    )
    _write_eval(
        evals_dir,
        "sim_retry_pin",
        {
            "displayName": "sim_retry_pin",
            "scenario": {
                "task": (
                    "If asked for a PIN, first enter '9999' (which is incorrect); "
                    "when prompted to retry, enter the correct PIN '5678'."
                ),
                "userFacts": ["Account ID: ACC-1002"],
            },
        },
    )

    assert check_eval_contract(evals_dir, fakes) == []
    assert main(["--evals-dir", str(evals_dir), "--fakes", str(fakes)]) == 0


def test_first_try_code_in_always_wrong_fails(tmp_path: Path) -> None:
    fakes = tmp_path / "fakes.py"
    fakes.write_text(FAKES_TEMPLATE, encoding="utf-8")
    evals_dir = tmp_path / "bench" / "dev" / "evaluations"

    _write_eval(
        evals_dir,
        "sim_bad_first_try",
        {
            "displayName": "sim_bad_first_try",
            "scenario": {
                "task": "Verify account using login code 000000.",
                "userFacts": ["Account ID: ACC-1001"],
            },
        },
    )

    violations = check_eval_contract(evals_dir, fakes)
    assert len(violations) == 1
    assert violations[0]["kind"] == "FIRST_TRY_CODE_REJECTED"
    assert violations[0]["value"] == "000000"
    assert main(["--evals-dir", str(evals_dir), "--fakes", str(fakes)]) == 1


def test_retry_code_missing_from_valid_sets_fails(tmp_path: Path) -> None:
    fakes = tmp_path / "fakes.py"
    fakes.write_text(FAKES_TEMPLATE, encoding="utf-8")
    evals_dir = tmp_path / "bench" / "dev" / "evaluations"

    _write_eval(
        evals_dir,
        "sim_unlisted_retry_pin",
        {
            "displayName": "sim_unlisted_retry_pin",
            "scenario": {
                "task": (
                    "If asked for a PIN, first enter '0000' (incorrect); "
                    "when prompted to retry, enter PIN '2468'."
                ),
                "userFacts": ["Account ID: ACC-1001"],
            },
        },
    )

    violations = check_eval_contract(evals_dir, fakes)
    assert any(v["kind"] == "RETRY_CODE_REJECTED" and v["value"] == "2468" for v in violations)


def test_wrong_code_not_rejected_by_fakes_fails(tmp_path: Path) -> None:
    fakes = tmp_path / "fakes.py"
    fakes.write_text(FAKES_TEMPLATE, encoding="utf-8")
    evals_dir = tmp_path / "bench" / "dev" / "evaluations"

    _write_eval(
        evals_dir,
        "sim_wrong_code_accepted",
        {
            "displayName": "sim_wrong_code_accepted",
            "scenario": {
                "task": (
                    "If asked for a verification code, first enter '777777' (which is wrong); "
                    "on retry enter code '604213'."
                ),
                "userFacts": ["Account ID: ACC-1001"],
            },
        },
    )

    violations = check_eval_contract(evals_dir, fakes)
    assert any(v["kind"] == "WRONG_CODE_ACCEPTED" and v["value"] == "777777" for v in violations)


def test_unknown_account_or_phone_in_user_facts_fails(tmp_path: Path) -> None:
    fakes = tmp_path / "fakes.py"
    fakes.write_text(FAKES_TEMPLATE, encoding="utf-8")
    evals_dir = tmp_path / "bench" / "dev" / "evaluations"

    _write_eval(
        evals_dir,
        "sim_unknown_account",
        {
            "displayName": "sim_unknown_account",
            "scenario": {
                "task": "Look up caller account.",
                "userFacts": ["Account ID: ACC-9999", "Phone: 202-555-0999"],
            },
        },
    )

    violations = check_eval_contract(evals_dir, fakes)
    unknown_values = {v["value"] for v in violations if v["kind"] == "UNKNOWN_IDENTIFIER"}
    assert "ACC-9999" in unknown_values
    assert "202-555-0999" in unknown_values


def test_holdout_path_is_refused(tmp_path: Path) -> None:
    fakes = tmp_path / "fakes.py"
    fakes.write_text(FAKES_TEMPLATE, encoding="utf-8")
    holdout_dir = tmp_path / "bench-holdout" / "evaluations"
    holdout_dir.mkdir(parents=True)

    with pytest.raises(ValueError, match="holdout"):
        check_eval_contract(holdout_dir, fakes)

    assert main(["--evals-dir", str(holdout_dir), "--fakes", str(fakes)]) == 2


def test_missing_dirs_graceful_noop(tmp_path: Path) -> None:
    missing_evals = tmp_path / "no_such_evals"
    missing_fakes = tmp_path / "no_such_fakes.py"
    assert check_eval_contract(missing_evals, missing_fakes) == []
    assert main(["--evals-dir", str(missing_evals), "--fakes", str(missing_fakes)]) == 0


def test_extract_eval_facts_handles_dict_user_facts_and_turns() -> None:
    facts = extract_eval_facts(
        {
            "scenario": {
                "user_facts": {
                    "account_id": "ACC-1001",
                    "wrong_pin": "0000 (incorrect)",
                    "retry_pin": "on retry use 5678",
                }
            },
            "golden": {
                "turns": [
                    {"user": "My phone is 202-555-0143"},
                ]
            },
        }
    )
    assert "0000" in facts["wrong_codes"]
    assert "5678" in facts["retry_codes"]
    assert "ACC-1001" in facts["user_fact_identifiers"]
    assert "202-555-0143" in facts["identifiers"]


def _fresh_kickstart_fakes(tmp_path: Path) -> Path:
    """Scaffold an untouched agent with kickstart.py and return its lib/fakes.py."""
    kickstart(
        target_dir=tmp_path / "agent",
        agent_name="contract-check",
        project_id="test-proj",
        location="us",
        languages=["en-US", "fr-CA", "es-US"],
    )
    return tmp_path / "agent" / "lib" / "fakes.py"


def test_fresh_kickstart_fakes_are_recognized_as_the_starter(tmp_path: Path) -> None:
    # _STARTER_DEFAULT_PINS / _STARTER_DEFAULT_OTPS must track the kickstart template:
    # an untouched scaffold gets the lenient retry rule, a customized fake world the strict one.
    fakes_mod = _load_fakes_module(_fresh_kickstart_fakes(tmp_path))
    valid_pins = {str(x) for x in fakes_mod.VALID_PINS}
    valid_otps = {str(x) for x in fakes_mod.VALID_OTPS}

    assert _is_uncustomized_starter_fakes(fakes_mod, valid_pins, valid_otps) is True
    assert _is_uncustomized_starter_fakes(fakes_mod, valid_pins | {"8642"}, valid_otps) is False


def test_fresh_kickstart_passes_the_shipped_sample_bench(tmp_path: Path) -> None:
    # What `make ci` runs right after `make kickstart`: the sample bench's retry PINs are
    # arbitrary, so the untouched starter must pass without editing lib/fakes.py.
    sample_bench = REPO_ROOT / "bench" / "dev" / "evaluations"
    if not sample_bench.is_dir():
        pytest.skip("the kit's sample bench/dev/evaluations is not present")

    assert check_eval_contract(sample_bench, _fresh_kickstart_fakes(tmp_path)) == []


def test_retry_code_equal_to_credential_on_file_is_valid(tmp_path: Path) -> None:
    fakes = tmp_path / "fakes.py"
    fakes.write_text(FAKES_TEMPLATE, encoding="utf-8")
    evals_dir = tmp_path / "bench" / "dev" / "evaluations"
    task = "When prompted for your PIN enter '9999' (incorrect). When prompted to retry, enter the PIN '4321'."
    _write_eval(
        evals_dir,
        "sim_pin_on_file",
        {
            "displayName": "sim_pin_on_file",
            "scenario": {
                "task": task,
                "variableOverrides": {"fx_pin_on_file": "4321", "fx_extra_bill_line": "x|15.00|internet"},
            },
        },
    )
    assert check_eval_contract(evals_dir, fakes) == []
    # Without the override the same scenario breaks the strict retry rule.
    _write_eval(evals_dir, "sim_no_override", {"displayName": "sim_no_override", "scenario": {"task": task}})
    kinds = {(v["eval_id"], v["kind"]) for v in check_eval_contract(evals_dir, fakes)}
    assert kinds == {("sim_no_override", "RETRY_CODE_REJECTED")}


def test_credential_on_file_rejects_every_other_code(tmp_path: Path) -> None:
    fakes = tmp_path / "fakes.py"
    fakes.write_text(FAKES_TEMPLATE, encoding="utf-8")
    evals_dir = tmp_path / "bench" / "dev" / "evaluations"
    _write_eval(
        evals_dir,
        "sim_otp_on_file",
        {
            "displayName": "sim_otp_on_file",
            "scenario": {
                # 604213 is a ladder-valid OTP, but this caller's account has 804627 on file.
                "task": "Provide OTP code 604213 when asked. Then give the wrong code 804627.",
                "variableOverrides": {"fx_otp_on_file": "804627"},
            },
        },
    )
    kinds = {(v["kind"], v["value"]) for v in check_eval_contract(evals_dir, fakes)}
    # With a wrong code present, the other code counts as the retry code.
    assert ("RETRY_CODE_REJECTED", "604213") in kinds
    assert ("WRONG_CODE_ACCEPTED", "804627") in kinds


def test_malformed_credential_on_file_is_reported(tmp_path: Path) -> None:
    from scripts.eval_contract import credentials_on_file, extract_variable_overrides

    fakes = tmp_path / "fakes.py"
    fakes.write_text(FAKES_TEMPLATE, encoding="utf-8")
    evals_dir = tmp_path / "bench" / "dev" / "evaluations"
    _write_eval(
        evals_dir,
        "sim_bad_pin",
        {"displayName": "sim_bad_pin", "scenario": {"task": "Ask to disable MFA.", "variableOverrides": {"fx_pin_on_file": "77777"}}},
    )
    assert [v["kind"] for v in check_eval_contract(evals_dir, fakes)] == ["BAD_CREDENTIAL_ON_FILE"]
    golden = {"golden": {"turns": [{"steps": [{"userInput": {"variables": {"fx_otp_on_file": "80 46 27"}}}]}]}}
    assert credentials_on_file(extract_variable_overrides(golden)) == {"fx_otp_on_file": "804627"}
    empty = {"scenario": {"variableOverrides": {"fx_pin_on_file": ""}}}
    assert credentials_on_file(extract_variable_overrides(empty)) == {}


def test_shipped_bench_passes_with_strict_retry() -> None:
    evals = REPO_ROOT / "bench" / "dev" / "evaluations"
    if not evals.is_dir():
        pytest.skip("no bench/dev/evaluations")
    assert check_eval_contract(evals, REPO_ROOT / "lib" / "fakes.py", strict_retry=True) == []
