"""Unit tests for scripts/run_bench.py: the daily full-run cap comes from gate_thresholds.json."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from scripts import run_bench

REPO_ROOT = Path(__file__).resolve().parents[1]
APP = "projects/test-proj/locations/us/apps/a1"


def _thresholds(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "gate_thresholds.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _full_runs_today(runs_dir: Path, count: int) -> None:
    runs_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(UTC).strftime("%Y%m%d")
    for n in range(count):
        (runs_dir / f"run_{today}T00000{n}Z.json").write_text(json.dumps({"is_full_run": True}), encoding="utf-8")


def test_cap_comes_from_the_thresholds_file_when_no_flag_is_given(tmp_path: Path) -> None:
    thresholds = _thresholds(tmp_path, {"promotion": {"daily_full_run_cap": 6}})
    assert run_bench.resolve_max_full_runs(None, thresholds) == 6


def test_explicit_flag_wins_over_the_thresholds_file(tmp_path: Path) -> None:
    thresholds = _thresholds(tmp_path, {"promotion": {"daily_full_run_cap": 6}})
    assert run_bench.resolve_max_full_runs(3, thresholds) == 3


@pytest.mark.parametrize("payload", [{}, {"promotion": {}}, {"promotion": {"daily_full_run_cap": "many"}}, []])
def test_missing_or_unusable_key_falls_back_to_the_builtin_default(tmp_path: Path, payload: object) -> None:
    assert run_bench.resolve_max_full_runs(None, _thresholds(tmp_path, payload)) == run_bench.DEFAULT_MAX_FULL_RUNS


def test_missing_file_falls_back_to_the_builtin_default(tmp_path: Path) -> None:
    assert run_bench.resolve_max_full_runs(None, tmp_path / "missing.json") == run_bench.DEFAULT_MAX_FULL_RUNS


def test_the_kit_thresholds_file_is_the_default_source() -> None:
    # One source of truth: the cap the kit ships in gate_thresholds.json is what run_bench enforces.
    shipped = json.loads((REPO_ROOT / "gate_thresholds.json").read_text(encoding="utf-8"))
    assert run_bench.resolve_max_full_runs(None) == shipped["promotion"]["daily_full_run_cap"]


def test_env_override_still_wins_in_check_daily_full_run_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs_dir = tmp_path / "runs"
    _full_runs_today(runs_dir, 6)
    cap = run_bench.resolve_max_full_runs(None, _thresholds(tmp_path, {"promotion": {"daily_full_run_cap": 6}}))

    monkeypatch.delenv("MAX_FULL_RUNS", raising=False)
    assert run_bench.check_daily_full_run_cap(runs_dir, max_full_runs=cap) == (False, 6)
    monkeypatch.setenv("MAX_FULL_RUNS", "7")
    assert run_bench.check_daily_full_run_cap(runs_dir, max_full_runs=cap) == (True, 6)


def test_main_refuses_a_full_run_at_the_thresholds_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The real wiring: a full run with no --max-full-runs stops at daily_full_run_cap (before
    any cloud call), and an explicit --max-full-runs above the count is honoured instead."""
    bench_dir = tmp_path / "bench"
    _full_runs_today(bench_dir / "runs", 6)
    thresholds = _thresholds(tmp_path, {"promotion": {"daily_full_run_cap": 6}})
    monkeypatch.delenv("MAX_FULL_RUNS", raising=False)

    code = run_bench.main(["--app", APP, "--bench-dir", str(bench_dir), "--thresholds", str(thresholds)])
    assert code == 1
    assert "daily full-run cap reached (6/6" in capsys.readouterr().err

    # 7 > 6 full runs today: the cap no longer stops the run, so main gets past the cap check
    # and reaches the cloud client, which the unit test replaces with a sentinel error.
    def _no_cloud(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("no cloud in unit tests")

    monkeypatch.setattr(run_bench, "_make_cloud", _no_cloud)
    with pytest.raises((RuntimeError, ImportError)):
        run_bench.main([
            "--app", APP, "--bench-dir", str(bench_dir), "--thresholds", str(thresholds), "--max-full-runs", "7",
        ])


# ----------------------------------------------------------------------------- Gate 1 / Gate 3 exit codes


def _smoke_rec(slot: int, passed: bool) -> dict:
    exps = [{"prompt": "says the line", "outcome": 1}, {"prompt": "does the task", "outcome": 1 if passed else 2}]
    return {
        "round": 0, "evaluation_run": "r", "slot": slot, "evaluation": "ev/x",
        "classification": "PASS" if passed else "FAIL", "tool_calls": [],
        "raw": {"scenario_result": {"evaluation_expectation_results": exps}},
    }


def test_smoke_gate_needs_the_whole_eval_not_one_expectation() -> None:
    recs = [_smoke_rec(1, True), _smoke_rec(2, False), _smoke_rec(3, False)]
    gate = run_bench.compute_smoke_gate(recs, [{"ve_id": "VE-01", "evaluation_name": "ev/x", "total_runs": 3, "pass_runs": 1}])
    assert gate["per_eval"]["VE-01"]["expectations"]["says the line"] == "3/3"
    assert gate["per_eval"]["VE-01"]["eval_go"] is False
    assert gate["gate_verdict"] == "stop"
    assert run_bench.smoke_exit_code({"smoke_gate": gate}) == 4


def test_run_evals_appends_records_and_returns_4_on_a_gate_1_stop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import run_evals

    bench_dir = tmp_path / "bench"

    def _fake_bench_main(argv: list[str]) -> int:
        label = argv[argv.index("--report-name") + 1]
        (bench_dir / "runs").mkdir(parents=True, exist_ok=True)
        report = {"results": [{"display_name": "golden_x", "pass_runs": 1, "fail_runs": 2, "total_runs": 3}],
                  "smoke_gate": {"gate_verdict": "stop"}}
        (bench_dir / "runs" / f"{label}.json").write_text(json.dumps(report), encoding="utf-8")
        return 4

    monkeypatch.setattr(run_bench, "main", _fake_bench_main)
    records = tmp_path / "runs.jsonl"
    code = run_evals.main([
        "--app", APP, "--smoke", "--targets", "golden_x", "--bench-dir", str(bench_dir),
        "--eval-dir", str(REPO_ROOT / "evals"), "--records", str(records), "--label", "smoke-test",
        "--thresholds", str(REPO_ROOT / "gate_thresholds.json"),
    ])
    assert code == 4
    assert records.read_text(encoding="utf-8").strip(), "smoke records must still be appended on a stop"


def _make(target: str, tmp_path: Path, **overrides: str) -> "subprocess.CompletedProcess[str]":
    import shutil
    import subprocess

    if not shutil.which("make"):
        pytest.skip("make is not installed")
    args = ["make", "--no-print-directory", "-C", str(REPO_ROOT), target, "SKIP_PREFLIGHT=1",
            "APP=projects/p/locations/l/apps/a", "SHA7=abc1234", f"BENCH_DIR={tmp_path / 'bench'}"]
    args += [f"{k}={v}" for k, v in overrides.items()]
    return subprocess.run(args, capture_output=True, text=True, timeout=120, check=False)


def _stub(tmp_path: Path, name: str, body: str) -> str:
    path = tmp_path / name
    path.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
    path.chmod(0o755)
    return str(path)


def test_make_bench_full_fails_when_gate_3_fails(tmp_path: Path) -> None:
    # PYTHON stub: every helper succeeds except the Gate 3 verdict.
    py = _stub(tmp_path, "py", 'case "$*" in *--gate3*) echo "Gate 3 FAIL"; exit 1;; esac; exit 0')
    proc = _make("bench-full", tmp_path, PYTHON=py, RUN_EVALS="true", IMPACT="true")
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "does not pass Gate 3" in proc.stderr
    ok_py = _stub(tmp_path, "py_ok", "exit 0")
    assert _make("bench-full", tmp_path, PYTHON=ok_py, RUN_EVALS="true", IMPACT="true").returncode == 0


def test_make_smoke_targets_fail_on_a_gate_1_stop_but_still_record(tmp_path: Path) -> None:
    marker = tmp_path / "recorded"
    impact = _stub(tmp_path, "impact", f'case "$*" in *--smoke-plan*) echo VE-01;; *--record-smoke*) touch {marker};; esac; exit 0')
    stop = _stub(tmp_path, "run_evals_stop", "exit 4")
    proc = _make("smoke-impact", tmp_path, IMPACT=impact, RUN_EVALS=stop)
    assert proc.returncode != 0 and marker.exists(), proc.stdout + proc.stderr
    assert _make("bench-smoke", tmp_path, RUN_EVALS=stop, TARGETS="VE-01").returncode != 0
    go = _stub(tmp_path, "run_evals_go", "exit 0")
    marker.unlink()
    assert _make("smoke-impact", tmp_path, IMPACT=impact, RUN_EVALS=go).returncode == 0 and marker.exists()
    broken = _stub(tmp_path, "run_evals_err", "exit 1")
    marker.unlink()
    assert _make("smoke-impact", tmp_path, IMPACT=impact, RUN_EVALS=broken).returncode != 0 and not marker.exists()
