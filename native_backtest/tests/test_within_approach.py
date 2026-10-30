"""Within-approach experiments completed on 2026-10-29: pre-registration, reproduction, statistics and safeguards."""
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from native_backtest.framework import metrics as M
from native_backtest.framework.market import load_config
from native_backtest.scripts import within_approach_experiments as W

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "native_backtest/out/within_approach/within_approach_v1.json"
PREREG = ROOT / "native_backtest/config/within_approach_preregistration_v1.json"


@pytest.fixture(scope="module")
def res():
    return json.loads(RES.read_text())


@pytest.fixture(scope="module")
def prereg():
    return json.loads(PREREG.read_text())


def test_results_follow_the_preregistration_that_was_written_first(res, prereg):
    """The report must cite the pre-registration actually in the repository, and use its settings."""
    assert res["preregistration_sha256"] == hashlib.sha256(PREREG.read_bytes()).hexdigest()
    cfg = load_config()
    m = cfg["metrics"]
    assert res["bootstrap"] == {"block_months": m["bootstrap_block_months"], "replications": m["bootstrap_reps"],
                                "seed": m["bootstrap_seed"], "cer_delta": m["cer_delta"]}
    assert (m["bootstrap_block_months"], m["bootstrap_reps"], m["bootstrap_seed"]) == (6, 5000, 20261027)
    assert res["months"] == ["2019-03", "2022-12", 46]
    assert prereg["AP1_financial_signals"]["confirmatory"].startswith("B-All vs A")
    assert res["safeguards"]["protected_window_scored"] is False and res["safeguards"]["model_calls"] == 0


def test_stage2_rerun_reproduces_the_archived_run(res):
    rep = res["AP1_financial_signals"]["reproduction"]
    assert rep["all_identical"] and rep["scorer_own_check_vs_saved_summary"] == "MATCH" and rep["scorer_check_differences"] == 0
    for f, v in rep["files"].items():
        assert v["identical"], f
    # the archived run's own files are untouched
    arch = ROOT / "stage2/results/dev_rerun_v4_portfolio_2026-10-27"
    new = ROOT / "stage2/results/dev_rerun_v5_within_approach_2026-10-29"
    for f in W.SHARED:
        if not f.endswith(".json"):
            assert hashlib.sha256((arch / f).read_bytes()).hexdigest() == hashlib.sha256((new / f).read_bytes()).hexdigest(), f


def test_bootstrap_reproduces_the_frozen_scorer_exactly(res):
    """The bootstrap used for the new statistics is the scorer's own: it must return its published numbers."""
    assert res["AP1_financial_signals"]["max_abs_difference_vs_scorer"] == 0.0
    saved = json.loads((ROOT / "stage2/results/dev_rerun_v5_within_approach_2026-10-29/stage2_result_summary.json").read_text())
    ref = saved["primary_contrast_BAll_vs_A"]
    series = pd.Series({k: float(v) for k, v in ref["monthly_improvement"].items()}).sort_index().to_numpy()
    P = {"block": 6, "reps": 5000, "seed": 20261027}
    mine = W.boot_summary(series, P)
    assert mine["point"] == pytest.approx(ref["normalized_pooled_se_improvement"], abs=1e-15)
    assert mine["ci90"] == pytest.approx(ref["ci90"], abs=1e-15) and mine["ci95"] == pytest.approx(ref["ci95"], abs=1e-15)
    assert mine["bootstrap_prob_le_zero"] == pytest.approx(ref["bootstrap_prob_le_zero"], abs=1e-15)
    assert 0.0 <= mine["p_two_sided"] <= 1.0


def test_no_financial_signal_is_reported_as_a_robust_improvement(res):
    """The pre-registered robustness rule: significant, same sign in both halves, at least 2 of 3 assets."""
    sysres = res["AP1_financial_signals"]["systems"]
    assert set(sysres) == {"B1", "B2", "B3", "B4", "B5", "B-All"}
    for s, v in sysres.items():
        f, rb = v["forecast"], v["robust"]
        assert rb["significant_overall"] == (f["p_two_sided"] < 0.05)
        signs = {np.sign(h["improvement"]) for h in f["halves"].values()}
        assert 0.0 not in signs                                     # sign is well defined in both halves
        assert rb["same_sign_in_both_halves"] == (len(signs) == 1)
        assert rb["assets_improved_at_least_2_of_3"] == (f["assets_improved"] >= 2)
        assert rb["robust_improvement"] == (rb["significant_overall"] and rb["same_sign_in_both_halves"]
                                            and rb["assets_improved_at_least_2_of_3"] and f["normalized_pooled_se_improvement"] > 0)
        assert rb["robust_improvement"] is False                    # the actual finding on this sample
        assert sum(h["months"] for h in f["halves"].values()) == 46
    assert sysres["B-All"]["role"] == "confirmatory" and sysres["B-All"]["forecast"]["normalized_pooled_se_improvement"] < 0
    for s in ("B1", "B2", "B3", "B4", "B5"):
        h = sysres[s]["holm_within_component_family"]
        assert h["holm_adjusted_p"] >= sysres[s]["forecast"]["p_two_sided"] and not h["reject_at_alpha"]


def test_every_signal_is_fully_covered_so_no_result_is_a_data_gap(res):
    for s, v in res["AP1_financial_signals"]["systems"].items():
        for feat, c in v["coverage"].items():
            assert c["asset_months_available"] == c["of"] == 138 and c["share"] == 1.0, (s, feat)


def test_committee_plus_jev_is_a_valid_parameter_free_combination(res):
    c = res["AP2_committee_plus_jev"]
    for k, v in c["validity_checks"].items():
        assert v["all_pass"] and v["months_passing"] == v["of"] == 46, k
    assert "equal-weight average" in c["rule"]
    recs = [json.loads(l) for l in (ROOT / "native_backtest/out/decisions/AP2_COMBO.jsonl").read_text().splitlines()]
    a = {r["decision_month"]: r for r in (json.loads(l) for l in (ROOT / "native_backtest/out/decisions/AP2A.jsonl").read_text().splitlines())}
    b = {r["decision_month"]: r for r in (json.loads(l) for l in (ROOT / "native_backtest/out/decisions/AP2B.jsonl").read_text().splitlines())}
    assert len(recs) == 46
    for r in recs:
        m = r["decision_month"]
        assert r["generation"]["parameters"] == 0 and list(r["universe"]) == ["SPY", "TLT"]
        assert r["target_weights"]["SPY"] == pytest.approx(0.5 * (a[m]["target_weights"]["SPY"] + b[m]["target_weights"]["SPY"]), abs=1e-15)
        assert sum(r["target_weights"].values()) == pytest.approx(1.0, abs=1e-12)
        assert pd.Timestamp(r["info_cutoff"]) <= pd.Timestamp(r["decision_time"])          # no look-ahead
    # the combination lies between its components, as averaging weights must
    cer = {k: v["cer_delta_2_5"] for k, v in c["metrics"].items()}
    assert min(cer["jev"], cer["com"]) <= cer["combo"] <= max(cer["jev"], cer["com"])
    for k, v in c["comparisons"].items():
        assert v["statistically_clear_at_5pct"] is False, k
        assert v["ci95"][0] <= v["net_cer_difference"] <= v["ci95"][1]


def test_committee_plus_jev_does_not_touch_its_components(res):
    """The existing JEV-only and Committee-only decisions and results are preserved exactly."""
    rep = json.loads((ROOT / "native_backtest/out/development/development_evaluation_report.json").read_text())
    rows = {x["system"]: x for x in rep["common_evaluation_matched_dev"]}
    c = res["AP2_committee_plus_jev"]["metrics"]
    assert c["jev"]["cer_delta_2_5"] == pytest.approx(rows["AP2B"]["absolute"]["cer_delta_2_5"], abs=1e-12)
    assert c["com"]["cer_delta_2_5"] == pytest.approx(rows["AP2A"]["absolute"]["cer_delta_2_5"], abs=1e-12)


def test_regimes_are_known_at_the_decision_time_and_diagnostic_only(res):
    g = res["REG_market_regimes"]
    lab = pd.read_csv(ROOT / "native_backtest/out/within_approach/regime_labels_v1.csv", dtype={"decision_month": str})
    assert len(lab) == 46
    for r in lab.itertuples():                                   # the VIX close used is on or before the decision date
        assert pd.Timestamp(r.vix_close_date) <= pd.Timestamp(r.decision_date)
        assert r.R2_volatility == ("stressed (VIX >= 20)" if r.vix_close >= 20 else "calm (VIX < 20)")
    assert sum(g["months_by_regime"]["R1_date"].values()) == 46 and sum(g["months_by_regime"]["R2_volatility"].values()) == 46
    assert "diagnostic only" in g["definitions"]["status"]
    for key, splits in g["systems"].items():
        for split, groups in splits.items():
            assert sum(v["months"] for v in groups.values()) == 46, (key, split)


def test_statuses_changed_only_for_experiments_that_actually_ran():
    cfg = load_config()
    st = {v["id"]: v["status"] for g in cfg["research_design"]["within_approach_experiments"]["groups"] for v in g["variants"]}
    assert st["AP1+B1..B5"] == st["AP1+B-All"] == st["REG"] == st["AP2-COMBO"] == "tested"
    # the completed qwen3:4b run moves AP3-RE to "exploratory" - it ran, and its gates failed. It must never
    # become "tested", and nothing else in the Causal RAG group moves with it.
    assert st["AP3-RE"] in ("awaiting_validation", "exploratory") and st["AP3-RE"] != "tested"
    assert st["AP3-RE-PROXY"] == "awaiting_validation" and st["AP3-HD"] == "blocked"
    for k in ("AP3-RE-vs-HD", "AP3-STD", "AP3-NR/RG/PERM/MED", "AP3-VAR"):
        assert st[k] == "planned", k                              # no Causal RAG experiment is called tested
    assert cfg["version"] == cfg["change_log"][-1]["version"], "every version bump is logged"
    assert cfg["version"] in ("1.8", "1.9")
    assert "no experiment definition changed" in cfg["change_log"][-1]["change"]
    # the frozen scientific settings are untouched
    assert cfg["windows"]["protected"] == ["2023-01", "2026-08"] and cfg["costs"]["cost_per_dollar_traded"] == 0.0005
    assert cfg["metrics"]["cer_delta"] == 2.5 and cfg["primary_contrasts"] == [["AP2B", "AP1"], ["AP3", "AP1"], ["AP3", "AP2B"]]


def test_paired_cer_on_a_subset_matches_the_shared_implementation():
    """paired_cer is used for regime subsets; on the full sample it must equal the framework's own contrast."""
    rng = np.random.default_rng(7)
    a, b = rng.normal(0.01, 0.03, 46), rng.normal(0.008, 0.03, 46)
    P = {"delta": 2.5, "block": 6, "reps": 5000, "seed": 20261027}
    mine = W.paired_cer(a, b, P)
    fa = pd.DataFrame({"decision_month": [f"20{19 + i // 12}-{i % 12 + 1:02d}" for i in range(46)], "net_excess_return": a})
    fb = fa.assign(net_excess_return=b)
    ref = M.paired_cer_contrast(fa, fb)
    assert mine["net_cer_difference"] == pytest.approx(ref["cer_difference"], abs=1e-12)
    assert mine["ci95"] == pytest.approx(ref["ci95"], abs=1e-12)
    assert mine["p_two_sided_bootstrap"] == pytest.approx(ref["p_two_sided_bootstrap"], abs=1e-12)
