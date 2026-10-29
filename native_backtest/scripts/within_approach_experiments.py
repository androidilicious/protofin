#!/usr/bin/env python3
"""Within-approach experiments resumed or completed on 2026-10-29 (development months only).

Pre-registered in native_backtest/config/within_approach_preregistration_v1.json, which was written and pushed
before any of these results was computed. None of these enters the primary Holm family of three. The protected
window 2023-01..2026-08 is never scored.

1. AP1 financial signals (B1..B5, B-All). The frozen Stage 2 scorer is re-run from the canonical development
   spec into a new folder and must reproduce the archived 2026-10-27 run file-for-file before anything is
   reported. This script then recomputes the scorer's own forecast contrast from the saved predictions, with no
   scorer code, and extends it with what the pre-registration adds: a two-sided bootstrap p-value, Holm within
   the five-component family, the two development halves, per-asset improvement, the robustness rule, portfolio
   net CER with a paired net-CER bootstrap against A, break-even cost and signal coverage.
2. Market regimes (REG): a date split and a VIX >= 20 split at the decision date, both known at the decision
   time, for the Deterministic model, JEV, the Committee and the passive 60/40 reference. Diagnostic only.
3. Committee + JEV (AP2-COMBO): the equal-weight average of the two saved SPY target weights, evaluated on the
   shared evaluator against each component and against its own 60/40 SPY/TLT benchmark.

Usage (repository root): python -m native_backtest.scripts.within_approach_experiments
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np
import pandas as pd

from native_backtest.framework import benchmark as B
from native_backtest.framework import metrics as M
from native_backtest.framework.accounting import simulate_records, static_portfolio_records
from native_backtest.framework.lock import assert_scoring_allowed
from native_backtest.framework.market import load_config, load_market, months_between
from native_backtest.framework.records import DecisionRecord, read_jsonl, write_jsonl

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "native_backtest/config/within_approach_preregistration_v1.json"
RUN = ROOT / "stage2/results/dev_rerun_v5_within_approach_2026-10-29"
ARCHIVE = ROOT / "stage2/results/dev_rerun_v4_portfolio_2026-10-27"
OUT = ROOT / "native_backtest/out/within_approach"
DEC = ROOT / "native_backtest/out/decisions"
VIX = ROOT / "stage2/data/_pinned/mediator_VIX_cboe.csv"
ASSETS = ("SPY", "IEF", "LQD")
B_SYSTEMS = {"B1": "credit spread level", "B2": "credit spread 3-month change", "B3": "10Y-3M Treasury slope",
             "B4": "VRP proxy (VIX^2/12 - 22-day realised variance)", "B5": "own-asset 12-month momentum",
             "B-All": "all five financial signals"}
B_FEATURE = {"B1": ["credit_level"], "B2": ["credit_change_3m"], "B3": ["curve_10y_3m"], "B4": ["vrp_proxy"],
             "B5": ["own_asset_momentum_12m"], "B-All": ["credit_level", "credit_change_3m", "curve_10y_3m", "vrp_proxy", "own_asset_momentum_12m"]}
MACRO_START = pd.Period("2015-02", freq="M")
SHARED = ("stage2_predictions.csv", "stage2_metrics.csv", "stage2_portfolio_returns.csv", "stage2_portfolio_metrics.csv",
          "stage2_portfolio_bl_diagnostics.csv", "stage2_feature_availability.csv", "stage2_result_summary.json")


# ----------------------------------------------------------------- frozen bootstrap (as stage2_backtest, restated here)
def block_draws(x: Sequence[float], block: int, reps: int, seed: int) -> np.ndarray:
    x = np.asarray(x, float)
    T = len(x)
    rng = np.random.default_rng(seed)
    nblocks = math.ceil(T / block)
    out = np.empty(reps)
    for b in range(reps):
        idx = [(int(s) + k) % T for s in rng.integers(0, T, size=nblocks) for k in range(block)][:T]
        out[b] = float(np.mean(x[np.array(idx, dtype=int)]))
    return out


def boot_summary(x: Sequence[float], P: dict) -> dict:
    d = block_draws(x, P["block"], P["reps"], P["seed"])
    return {"point": float(np.mean(np.asarray(x, float))),
            "ci90": [float(np.percentile(d, 5)), float(np.percentile(d, 95))],
            "ci95": [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))],
            "bootstrap_prob_le_zero": float(np.mean(d <= 0.0)),
            "p_two_sided": float(min(1.0, 2.0 * min(np.mean(d <= 0.0), np.mean(d >= 0.0))))}


def holm(pvalues: Dict[str, float], alpha: float = 0.05) -> Dict[str, dict]:
    return M.holm(pvalues, alpha)


# ----------------------------------------------------------------- 1. AP1 financial signals
def reproduction_check() -> dict:
    """The new run must reproduce the archived development run file-for-file before anything is reported."""
    rows = {}
    for f in SHARED:
        a, b = ARCHIVE / f, RUN / f
        if f.endswith(".json"):          # the summary carries the run's own folder path; compare the numbers
            ja, jb = json.loads(a.read_text()), json.loads(b.read_text())
            rows[f] = {"identical": ja == jb, "kind": "json equality"}
        else:
            rows[f] = {"identical": hashlib.sha256(a.read_bytes()).hexdigest() == hashlib.sha256(b.read_bytes()).hexdigest(),
                       "kind": "sha256", "sha256": hashlib.sha256(b.read_bytes()).hexdigest()[:16]}
    own = json.loads((RUN / "run_report.json").read_text())["reproduction_check"]
    return {"archived_run": str(ARCHIVE.relative_to(ROOT)), "new_run": str(RUN.relative_to(ROOT)), "files": rows,
            "all_identical": all(v["identical"] for v in rows.values()),
            "scorer_own_check_vs_saved_summary": own["status"], "scorer_check_differences": own["n_differences"]}


def ap1_signals(P: dict) -> dict:
    pred = pd.read_csv(RUN / "stage2_predictions.csv", dtype={"decision_month": str})
    metrics = pd.read_csv(RUN / "stage2_metrics.csv")
    avail = pd.read_csv(RUN / "stage2_feature_availability.csv", dtype={"decision_month": str})
    pret = pd.read_csv(RUN / "stage2_portfolio_returns.csv", dtype={"decision_month": str})
    pmet = pd.read_csv(RUN / "stage2_portfolio_metrics.csv").set_index("strategy")
    saved = json.loads((RUN / "stage2_result_summary.json").read_text())
    halves = json.loads(PREREG.read_text())["AP1_financial_signals"]["robustness"]["halves"]
    key = {"B1": "B1_credit_level", "B2": "B2_credit_change_3m", "B3": "B3_curve_10y_3m", "B4": "B4_vrp", "B5": "B5_momentum"}
    sq = pred.assign(sq=pred["error"] ** 2).groupby(["system", "asset"])["sq"].mean()

    def forecast_contrast(sysname: str) -> dict:
        """The frozen normalisation needs labels from 2015-02, which the saved predictions do not carry, so the
        monthly improvement series is taken from the scorer's own output and the bootstrap is recomputed on it;
        the recomputation must reproduce the scorer's published point estimate and intervals exactly."""
        ref = saved["primary_contrast_BAll_vs_A"] if sysname == "B-All" else saved["component_contrasts"][key[sysname]]
        by_month = pd.Series({k: float(v) for k, v in ref["monthly_improvement"].items()}).sort_index()
        res = boot_summary(by_month.to_numpy(), P)
        # per asset: mean squared forecast error against A, the measure behind "improves forecasts for an asset"
        per_asset = {a: {"mse": float(sq[(sysname, a)]), "mse_A": float(sq[("A", a)]),
                         "mse_ratio_vs_A": float(sq[(sysname, a)] / sq[("A", a)]),
                         "improves": bool(sq[(sysname, a)] < sq[("A", a)])} for a in ASSETS}
        half = {}
        for lo, hi in halves:
            sel = by_month[(by_month.index >= lo) & (by_month.index <= hi)]
            half[f"{lo}..{hi}"] = {"months": int(len(sel)), "improvement": float(sel.mean())}
        return {"normalized_pooled_se_improvement": res["point"], "ci90": res["ci90"], "ci95": res["ci95"],
                "bootstrap_prob_le_zero": res["bootstrap_prob_le_zero"], "p_two_sided": res["p_two_sided"],
                "n_months": int(len(by_month)), "n_asset_months": int(ref["n_asset_months"]),
                "per_asset_mse": per_asset, "assets_improved": int(sum(v["improves"] for v in per_asset.values())),
                "halves": half, "monthly_improvement": {k: float(v) for k, v in by_month.items()}}

    # the recomputed bootstrap must reproduce the scorer's own saved contrast exactly
    checks = []
    fc = {s: forecast_contrast(s) for s in B_SYSTEMS}
    for s, mine in fc.items():
        ref = saved["primary_contrast_BAll_vs_A"] if s == "B-All" else saved["component_contrasts"][key[s]]
        checks.append({"system": s, "max_abs_diff": max(abs(mine["normalized_pooled_se_improvement"] - ref["normalized_pooled_se_improvement"]),
                                                        abs(mine["ci90"][0] - ref["ci90"][0]), abs(mine["ci90"][1] - ref["ci90"][1]),
                                                        abs(mine["ci95"][0] - ref["ci95"][0]), abs(mine["ci95"][1] - ref["ci95"][1]),
                                                        abs(mine["bootstrap_prob_le_zero"] - ref["bootstrap_prob_le_zero"]))})

    comp_holm = holm({s: fc[s]["p_two_sided"] for s in ("B1", "B2", "B3", "B4", "B5")})
    # portfolio level: the same frozen allocator, paired net-CER bootstrap against A
    get = lambda s: pret[pret["strategy"] == s].sort_values("decision_month").reset_index(drop=True)
    pa = get("A")
    port = {}
    for s in B_SYSTEMS:
        ps = get(s)
        c = M.paired_cer_contrast(ps, pa, delta=P["delta"], block=P["block"], reps=P["reps"], seed=P["seed"])
        row = pmet.loc[s]
        port[s] = {"net_cer": float(row["cer_delta_2_5"]), "net_annualized_excess_return": float(row["net_annualized_excess_return"]),
                   "annualized_volatility": float(row["annualized_volatility"]), "net_sharpe": float(row["net_sharpe"]),
                   "max_drawdown": float(row["max_drawdown"]), "annualized_one_way_turnover": float(row["annualized_one_way_turnover"]),
                   "total_cost": float(row["total_cost"]),
                   "break_even_cost_vs_A": {"bps": None if pd.isna(row["break_even_vs_A_bps"]) else float(row["break_even_vs_A_bps"]),
                                            "status": row["break_even_vs_A_status"]},
                   "vs_A": {"net_cer_difference": c["cer_difference"], "ci95": c["ci95"], "p_two_sided_bootstrap": c["p_two_sided_bootstrap"]}}
    a_cer = float(pmet.loc["A", "cer_delta_2_5"])

    met = metrics.set_index(["system", "asset"])
    coverage = {}
    for s, feats in B_FEATURE.items():
        rows = {}
        for f in feats:
            col = avail[f]
            rows[f] = {"asset_months_available": int(col.sum()), "of": int(len(col)), "share": float(col.mean()),
                       "first_month_all_assets": min(avail[avail[f]]["decision_month"]) if col.any() else None}
        coverage[s] = rows

    out = {}
    for s in B_SYSTEMS:
        f = fc[s]
        sig = f["p_two_sided"] < 0.05
        same_sign = len({np.sign(v["improvement"]) for v in f["halves"].values()}) == 1
        out[s] = {"signal": B_SYSTEMS[s], "role": "confirmatory" if s == "B-All" else "attribution diagnostic",
                  "forecast": f, "holm_within_component_family": comp_holm.get(s),
                    "per_asset": {a: {"oos_r2": float(met.loc[(s, a), "oos_r2"]), "relative_mspe": float(met.loc[(s, a), "relative_mspe"]),
                                    "rmse": float(met.loc[(s, a), "rmse"]), "directional_accuracy": float(met.loc[(s, a), "directional_accuracy"]),
                                    **f["per_asset_mse"][a]} for a in ASSETS},
                  "portfolio": port[s], "coverage": coverage[s],
                  "robust": {"significant_overall": bool(sig), "same_sign_in_both_halves": bool(same_sign),
                             "assets_improved_at_least_2_of_3": bool(f["assets_improved"] >= 2),
                             "robust_improvement": bool(sig and same_sign and f["assets_improved"] >= 2 and f["normalized_pooled_se_improvement"] > 0)}}
    return {"reproduction": reproduction_check(), "scorer_contrast_reproduced_here": checks,
            "max_abs_difference_vs_scorer": max(c["max_abs_diff"] for c in checks),
            "A_reference": {"net_cer": a_cer, "per_asset": {a: {"oos_r2": float(met.loc[("A", a), "oos_r2"]),
                                                                "directional_accuracy": float(met.loc[("A", a), "directional_accuracy"])} for a in ASSETS}},
            "systems": out,
            "reading": "Positive improvement means lower normalised squared forecast error than A. Component p-values are Holm-corrected within the five-component family; B-All vs A is the predeclared confirmatory contrast."}


# ----------------------------------------------------------------- 2. market regimes
def vix_at_decision(mk, months) -> pd.DataFrame:
    df = pd.read_csv(VIX)
    col = [c for c in df.columns if c.lower() not in ("date", "observation_date")][0]
    s = pd.Series(pd.to_numeric(df[col], errors="coerce").to_numpy(float),
                  index=pd.to_datetime(df[df.columns[0]])).dropna().sort_index()
    rows = []
    for m in months:
        day = mk.decision_dates[m]
        q = s[s.index <= day]
        if q.empty or (day - q.index[-1]).days > 7:
            raise SystemExit(f"no VIX close at or before {day.date()}")
        rows.append({"decision_month": str(m), "decision_date": day.date().isoformat(),
                     "vix_close_date": q.index[-1].date().isoformat(), "vix_close": float(q.iloc[-1])})
    return pd.DataFrame(rows)


def regimes(cfg, mk, dev, sims: Dict[str, pd.DataFrame], P: dict) -> dict:
    pre = json.loads(PREREG.read_text())["REG_market_regimes"]
    vix = vix_at_decision(mk, dev)
    months = [str(m) for m in dev]
    r1 = pre["regimes"]["R1_date"]
    lab = pd.DataFrame({"decision_month": months})
    lab["R1_date"] = np.where(lab["decision_month"] <= r1["pre_2020"][1], f"{r1['pre_2020'][0]}..{r1['pre_2020'][1]}", f"{r1['from_2020'][0]}..{r1['from_2020'][1]}")
    lab = lab.merge(vix, on="decision_month")
    lab["R2_volatility"] = np.where(lab["vix_close"] >= 20.0, "stressed (VIX >= 20)", "calm (VIX < 20)")
    out = {"definitions": {"R1_date": r1, "R2_volatility": pre["regimes"]["R2_volatility"],
                           "status": pre["status"], "vix_source": "CBOE VIX close, pinned Stage 2 series mediator_VIX_cboe.csv"},
           "months_by_regime": {k: {str(g): int(n) for g, n in lab[k].value_counts().items()} for k in ("R1_date", "R2_volatility")},
           "systems": {}, "contrasts": {}}
    for split in ("R1_date", "R2_volatility"):
        for g, idx in lab.groupby(split).groups.items():
            sel = np.array(sorted(idx))
            for key, sim in sims.items():
                x = sim["net_excess_return"].to_numpy(float)[sel]
                out["systems"].setdefault(key, {}).setdefault(split, {})[str(g)] = {
                    "months": int(len(x)), "annualized_mean_net_excess_return": float(12 * x.mean()),
                    "annualized_volatility": float(math.sqrt(12) * x.std(ddof=1)), "net_cer": M.cer(x, P["delta"])}
            for name, (a, b) in (("JEV - Deterministic", ("jev", "det")), ("Committee - JEV", ("com", "jev"))):
                xa, xb = (sims[a]["net_excess_return"].to_numpy(float)[sel], sims[b]["net_excess_return"].to_numpy(float)[sel])
                res = paired_cer(xa, xb, P)
                out["contrasts"].setdefault(name, {}).setdefault(split, {})[str(g)] = {"months": int(len(xa)), **res}
    out["caution"] = ("Small groups and two splits: descriptive only. Both splits are known at the decision time; "
                      "neither is used to select or tune anything.")
    return out, lab


def paired_cer(xa: np.ndarray, xb: np.ndarray, P: dict) -> dict:
    """CER(a) - CER(b) with the frozen paired circular block bootstrap, on a subset of months."""
    T = len(xa)
    rng = np.random.default_rng(P["seed"])
    nblocks = math.ceil(T / P["block"])
    draws = np.empty(P["reps"])
    for i in range(P["reps"]):
        idx = np.array([(int(s) + k) % T for s in rng.integers(0, T, size=nblocks) for k in range(P["block"])][:T], dtype=int)
        draws[i] = M.cer(xa[idx], P["delta"]) - M.cer(xb[idx], P["delta"])
    return {"net_cer_difference": M.cer(xa, P["delta"]) - M.cer(xb, P["delta"]),
            "ci95": [float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))],
            "p_two_sided_bootstrap": float(min(1.0, 2.0 * min(np.mean(draws <= 0), np.mean(draws >= 0))))}


# ----------------------------------------------------------------- 3. Committee + JEV
def combo(cfg, mk, dev, P: dict) -> dict:
    cost = cfg["costs"]["cost_per_dollar_traded"]
    recs = {s: {r.decision_month: r for r in read_jsonl(DEC / f"{s}.jsonl")} for s in ("AP2A", "AP2B")}
    months = [str(m) for m in dev]
    checks = {"same_universe": [], "same_decision_dates": [], "cutoff_at_or_before_decision": [], "weights_in_native_band": []}
    out_recs: List[DecisionRecord] = []
    rows = []
    for m in months:
        a, b = recs["AP2A"][m], recs["AP2B"][m]
        checks["same_universe"].append(list(a.universe) == list(b.universe) == ["SPY", "TLT"])
        checks["same_decision_dates"].append(a.decision_time == b.decision_time
                                             and pd.Timestamp(a.decision_time).date() == mk.decision_dates[pd.Period(m, "M")].date())
        checks["cutoff_at_or_before_decision"].append(pd.Timestamp(a.info_cutoff) <= pd.Timestamp(a.decision_time) and pd.Timestamp(b.info_cutoff) <= pd.Timestamp(b.decision_time))
        spy = 0.5 * (float(a.target_weights["SPY"]) + float(b.target_weights["SPY"]))
        checks["weights_in_native_band"].append(0.40 - 1e-12 <= spy <= 0.80 + 1e-12)
        rows.append({"decision_month": m, "committee_spy": float(a.target_weights["SPY"]), "jev_spy": float(b.target_weights["SPY"]), "combo_spy": spy})
        out_recs.append(DecisionRecord(
            system_id="AP2-COMBO", decision_month=m, decision_time=a.decision_time, info_cutoff=max(a.info_cutoff, b.info_cutoff),
            universe=["SPY", "TLT"], target_weights={"SPY": spy, "TLT": 1.0 - spy},
            generation={"mode": "computed_native", "rule": "equal-weight average of the saved Committee and JEV SPY target weights",
                        "components": {"AP2A": a.generation.get("mode"), "AP2B": b.generation.get("mode")}, "parameters": 0},
            forecast={"horizon_months": 12, "kind": "combined_target_weight",
                      "values": {"committee_spy": float(a.target_weights["SPY"]), "jev_spy": float(b.target_weights["SPY"])}},
            confidence=None, native_detail=None))
    write_jsonl(out_recs, DEC / "AP2_COMBO.jsonl")
    sims = {"com": simulate_records([recs["AP2A"][m] for m in months], mk, dev, cost_per_dollar=cost),
            "jev": simulate_records([recs["AP2B"][m] for m in months], mk, dev, cost_per_dollar=cost),
            "combo": simulate_records(out_recs, mk, dev, cost_per_dollar=cost)}
    neutral = cfg["systems"]["AP2B"]["native_neutral_weights"]
    sims["own_benchmark"] = simulate_records(static_portfolio_records("AP2_COMBO_NEUTRAL", neutral, out_recs), mk, dev, cost_per_dollar=cost)
    mb = lambda sim: {**M.metrics(sim), "cumulative_return": B.cumulative_return(sim)}
    comparisons = {}
    for name, other in (("vs JEV", "jev"), ("vs Committee", "com"), ("vs its own 60/40 SPY/TLT benchmark", "own_benchmark")):
        c = M.paired_cer_contrast(sims["combo"], sims[other], delta=P["delta"], block=P["block"], reps=P["reps"], seed=P["seed"])
        comparisons[name] = {"net_cer_difference": c["cer_difference"], "ci90": c["ci90"], "ci95": c["ci95"],
                             "p_two_sided_bootstrap": c["p_two_sided_bootstrap"],
                             "statistically_clear_at_5pct": bool(c["p_two_sided_bootstrap"] < 0.05 and (c["ci95"][0] > 0 or c["ci95"][1] < 0))}
    w = pd.DataFrame(rows)
    return {"rule": json.loads(PREREG.read_text())["AP2_committee_plus_jev"]["rule"],
            "validity_checks": {k: {"months_passing": int(sum(v)), "of": len(v), "all_pass": bool(all(v))} for k, v in checks.items()},
            "weights": {"combo_spy_mean": float(w["combo_spy"].mean()), "combo_spy_min": float(w["combo_spy"].min()), "combo_spy_max": float(w["combo_spy"].max()),
                        "mean_abs_committee_minus_jev": float((w["committee_spy"] - w["jev_spy"]).abs().mean()),
                        "correlation_of_component_spy_weights": float(w["committee_spy"].corr(w["jev_spy"]))},
            "metrics": {k: mb(sims[k]) for k in ("combo", "jev", "com", "own_benchmark")},
            "comparisons": comparisons, "monthly": w.to_dict("records"),
            "decision_records": str((DEC / "AP2_COMBO.jsonl").relative_to(ROOT))}, sims


# ----------------------------------------------------------------- main
def main(argv=None) -> int:
    cfg = load_config()
    dev = months_between(*cfg["windows"]["development"])
    assert_scoring_allowed(dev, protected_start=cfg["windows"]["protected"][0])
    mk = load_market(cfg)
    mcfg = cfg["metrics"]
    P = {"delta": mcfg["cer_delta"], "block": mcfg["bootstrap_block_months"], "reps": mcfg["bootstrap_reps"], "seed": mcfg["bootstrap_seed"]}
    cost = cfg["costs"]["cost_per_dollar_traded"]

    ap1 = ap1_signals(P)
    combo_res, combo_sims = combo(cfg, mk, dev, P)
    months = [str(m) for m in dev]
    sims = {"det": simulate_records([r for r in read_jsonl(DEC / "AP1.jsonl") if r.decision_month in set(months)], mk, dev, cost_per_dollar=cost),
            "jev": combo_sims["jev"], "com": combo_sims["com"]}
    sims["passive"] = B.simulate(cfg, mk, dev, [r for r in read_jsonl(DEC / "AP1.jsonl") if r.decision_month in set(months)])
    reg, lab = regimes(cfg, mk, dev, sims, P)

    res = {"title": "Within-approach experiments completed on 2026-10-29 (development diagnostics)",
           "status": "DEVELOPMENT ONLY (2019-03..2022-12). Not protected historical results; the protected window stays sealed.",
           "preregistration": str(PREREG.relative_to(ROOT)),
           "preregistration_sha256": hashlib.sha256(PREREG.read_bytes()).hexdigest(),
           "months": [months[0], months[-1], len(months)],
           "bootstrap": {"block_months": P["block"], "replications": P["reps"], "seed": P["seed"], "cer_delta": P["delta"]},
           "AP1_financial_signals": ap1, "REG_market_regimes": reg, "AP2_committee_plus_jev": combo_res,
           "safeguards": {"protected_window_scored": False, "frozen_configuration_changed": False, "model_calls": 0, "cost_usd": 0.0}}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "within_approach_v1.json").write_text(json.dumps(res, indent=1, default=float) + "\n")
    lab.to_csv(OUT / "regime_labels_v1.csv", index=False)
    pd.DataFrame(combo_res["monthly"]).to_csv(OUT / "committee_plus_jev_weights_v1.csv", index=False)

    print(json.dumps({"reproduction_all_identical": ap1["reproduction"]["all_identical"],
                      "max_abs_difference_vs_scorer": ap1["max_abs_difference_vs_scorer"],
                      "B_systems": {s: {"improvement": round(v["forecast"]["normalized_pooled_se_improvement"], 6),
                                        "p": round(v["forecast"]["p_two_sided"], 4), "robust": v["robust"]["robust_improvement"],
                                        "net_cer": round(v["portfolio"]["net_cer"], 5)} for s, v in ap1["systems"].items()},
                      "combo": {k: round(v["net_cer_difference"], 5) for k, v in combo_res["comparisons"].items()},
                      "combo_checks_all_pass": all(v["all_pass"] for v in combo_res["validity_checks"].values())}, indent=1))
    bad = []
    if not ap1["reproduction"]["all_identical"] or ap1["max_abs_difference_vs_scorer"] > 1e-12:
        bad.append("AP1 reproduction")
    if not all(v["all_pass"] for v in combo_res["validity_checks"].values()):
        bad.append("combo validity")
    if bad:
        print("FAILED:", bad)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
