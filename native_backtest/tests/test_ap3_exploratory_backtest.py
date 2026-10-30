"""The completed Causal RAG exploratory development backtest.

Genuine qwen3:4b agent outputs now cover all 95 agent months, and the 46 development months have been carried
through signal encoding, walk-forward calibration and the native allocation. None of that makes them validated:
both pre-registered reliability gates still fail, and every output has to keep saying so.
"""
import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "native_backtest/out/ap3/qwen3_runs"
EV = RUN / "evaluation"
SUMMARY = json.loads((RUN / "summary.json").read_text())
EVAL = json.loads((EV / "evaluation.json").read_text())
DEV = ("2019-03", "2022-12")


def test_the_agent_replay_is_complete_and_genuine():
    assert SUMMARY["n_months"] == SUMMARY["target_months"] == 95
    assert SUMMARY["protocol"] == {"version": "1.1", "fingerprint": "983e4b398c4a09ac"}
    assert SUMMARY["cost_usd"] == 0.0
    assert min(SUMMARY["months_complete"]) == "2015-02" and max(SUMMARY["months_complete"]) == "2022-12"
    for f in sorted((RUN / "months").glob("*.json")):
        j = json.loads(f.read_text())
        assert j["engineering_mock"] is False, f.name
        assert j["model"] == "qwen3:4b@359d7dd4bcda", f.name


def test_the_gates_still_fail_with_their_real_values():
    g = SUMMARY["gates"]
    assert g["G3a"]["pass"] is False and g["G3b"]["pass"] is False
    assert g["G3b"]["checks"]["accuracy"]["value"] == pytest.approx(0.5666666666666667)
    assert g["G3b"]["checks"]["opposite_direction_errors"]["value"] == 2
    assert g["G3a"]["checks"]["schema_valid_call_rate"]["value"] == pytest.approx(0.9770642201834863)
    assert SUMMARY["exploratory"]["label"] == "EXPLORATORY — RELIABILITY GATES FAILED"


def test_the_evaluation_is_labelled_and_never_claims_validation():
    assert EVAL["exploratory"]["label"] == "EXPLORATORY — RELIABILITY GATES FAILED"
    assert "not validated" in EVAL["status"] and "not evidence" in EVAL["status"]
    recs = [json.loads(l) for l in (ROOT / "native_backtest/out/decisions/AP3_qwen3_reduced_evidence.jsonl").read_text().splitlines()]
    assert len(recs) == 46
    for r in recs:
        assert r["generation"]["exploratory"] is True and r["generation"]["validated"] is False
        assert sorted(r["generation"]["gates_failed"]) == ["G3a", "G3b"]
        assert r["generation"]["model"] == "qwen3:4b@359d7dd4bcda"


def test_only_development_months_were_scored():
    sim = pd.read_csv(EV / "AP3_common_matched_dev.csv", dtype={"decision_month": str})
    assert sim["decision_month"].min() == DEV[0] and sim["decision_month"].max() == DEV[1]
    assert len(sim) == 46
    assert sim["exit_date"].max() < "2023-03-01", "nothing settles beyond the final development month"
    pred = pd.read_csv(EV / "predictions.csv", dtype={"decision_month": str})
    assert pred["decision_month"].max() <= DEV[1]


def test_coverage_is_disclosed_rather_than_filled_in():
    c = EVAL["coverage"]
    assert c["agent_months_present"] == c["agent_months_expected"] == 95
    assert c["scored_months_present"] == c["scored_months_expected"] == 46
    # one month produced no hypothesis: it must be disclosed, and still have a real decision
    assert c["scored_months_with_at_least_one_hypothesis"] == 45
    assert c["scored_months_without_hypotheses"] == ["2021-08"]
    w = json.loads((EV / "weights.json").read_text())
    assert "2021-08" in w and abs(sum(w["2021-08"].values()) - 1) < 1e-8
    assert c["n_months_with_agent_failure"] == 0
    assert c["status_counts"]["Insufficient"] > 0, "Insufficient is recorded, never silently dropped"


def test_no_contrast_is_statistically_clear():
    for name, v in EVAL["primary_contrasts_development"].items():
        assert v["ci95"][0] <= 0 <= v["ci95"][1], f"{name} interval excludes zero"
        assert v["p_two_sided_bootstrap"] > 0.05, name
    own = EVAL["vs_own_benchmark"]
    assert own["ci95"][0] <= 0 <= own["ci95"][1] and own["p_two_sided_bootstrap"] > 0.05


def test_the_calibration_diagnostics_are_kept_visible():
    """The placebo and calibration numbers are the reason this result must not be read as forecast skill."""
    cal = EVAL["calibration"]
    assert cal["g4c_checks"]["intercept_only_share"] > 0.5, "most months fall back to the intercept"
    assert cal["g4c_checks"]["calibration_slope"] < 1.0, "forecasts are more confident than outcomes justify"
    p = cal["placebo"]
    assert p["n"] >= 100 and "percentile" in p and "actual_improvement" in p


def test_the_weights_are_the_native_allocation():
    w = json.loads((EV / "weights.json").read_text())
    cfg = json.loads((ROOT / "native_backtest/config/framework_config_v1.json").read_text())
    lo, up = {"SPY": 0.20, "IEF": 0.15, "LQD": 0.10}, {"SPY": 0.70, "IEF": 0.60, "LQD": 0.40}
    assert set(w) == {str(m) for m in pd.period_range(DEV[0], DEV[1], freq="M")}
    for m, v in w.items():
        assert set(v) == set(cfg["systems"]["AP3"]["native_neutral_weights"]), m
        assert abs(sum(v.values()) - 1) < 1e-8, m
        for a, x in v.items():
            assert lo[a] - 1e-9 <= x <= up[a] + 1e-9, (m, a, x)
