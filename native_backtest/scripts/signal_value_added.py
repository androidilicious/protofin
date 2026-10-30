#!/usr/bin/env python3
"""Signal value-added and portfolio attribution (development months only).

Question: do the forecasting signals improve outcomes beyond what each system's own underlying allocation would
achieve without them?

For the Deterministic Quantitative Model (research baseline) and the Agentic Workflow (JEV):

- Signal-disabled counterfactual. Each system's frozen native neutral portfolio (framework_config
  systems.<id>.native_neutral_weights): Deterministic 45/35/20 SPY/IEF/LQD, JEV 60/40 SPY/TLT. Everything except
  the tilts is shared with the strategy: the same decision dates, entry and exit closes, adjusted prices, cash
  (DTB4WK), start from cash, and 5 bp per dollar traded against the drifted weights. Like the strategies, the
  references are rebalanced back to their weights every month. That is the frozen convention of the shared
  evaluator's own-benchmark contrast, of Stage 2's BENCH_STATIC_45_35_20 and of the native JEV engine's 'fixed'
  and 'prior' benchmarks. They are within-approach counterfactuals, not new approaches.
- Incremental value. All supporting metrics, the monthly active series, tracking error, and the frozen paired
  circular block bootstrap for net CER (6-month blocks, 5,000 draws, seed 20261027).
- JEV vs Deterministic after accounting for their allocations. The difference in signal value-added, with a joint
  bootstrap on the same resampled blocks, and an exact attribution of the observed net CER gap.
- Decision diagnostics: tilt size, direction changes, how much forecast variation survives the allocator,
  regimes, and whether the tilts cover their costs.
- Sensitivities:
  - the native JEV engine with its tilt switched off;
  - buy-and-hold drift references (labelled; not the frozen convention);
  - Stage 2's saved native runs for the Deterministic model.

Nothing here changes a frozen configuration, a decision record or a previously reported result. Outputs go to
native_backtest/out/signal_value/. The protected window is never scored: the framework lock is applied, and the
native engine is stepped only to the last development decision date.

Usage (repository root): python -m native_backtest.scripts.signal_value_added
"""
from __future__ import annotations

import dataclasses
import json
import math
import subprocess
from pathlib import Path
from typing import Callable, Dict

import numpy as np
import pandas as pd

from native_backtest.framework import benchmark as B
from native_backtest.framework import metrics as M
from native_backtest.framework.accounting import simulate_records, static_portfolio_records
from native_backtest.framework.lock import assert_scoring_allowed
from native_backtest.framework.market import load_config, load_market, months_between
from native_backtest.framework.records import read_jsonl

ROOT = Path(__file__).resolve().parents[2]
DEC = ROOT / "native_backtest/out/decisions"
OUT = ROOT / "native_backtest/out/signal_value"
DEV_REPORT = ROOT / "native_backtest/out/development/development_evaluation_report.json"
STAGE2 = ROOT / "stage2/results/dev_rerun_v4_portfolio_2026-10-27"
JEV_ENGINE = Path("native_backtest/vendor/protofin_feature-jev_7a70331/site/js")
HARNESS = Path("native_backtest/adapters/node/ap2_signal_disabled.mjs")
LAST_DEV_AS_OF = "2022-12-30"            # decision month 2022-12, the last development month (as in ap2_native_reproduction)
SYSTEMS = {"AP1": {"label": "Deterministic Quantitative Model", "short": "Deterministic", "role": "research baseline"},
           "AP2B": {"label": "Agentic Workflow — JEV", "short": "JEV", "role": "primary approach"}}
# Causal RAG joins only when its genuine development decisions exist. Its results stay labelled exploratory
# because its reliability gates failed; the AP1/AP2B pair analysis below is unchanged either way.
AP3_DECISIONS = DEC / "AP3_qwen3_reduced_evidence.jsonl"
AP3_META = {"label": "Agentic Causal RAG", "short": "Causal RAG", "role": "primary approach",
            "exploratory": True, "designation": "EXPLORATORY — RELIABILITY GATES FAILED"}
ASSETS = ("SPY", "IEF", "LQD", "TLT")
VOL_WINDOW, VOL_THRESHOLD = 63, 0.20     # ex-ante regime: trailing 63 trading days of SPY, 20% a year (a round level, not tuned)
AP3_TRACE = ROOT / "native_backtest/out/sensitivity/ap3_transmission_trace.csv"
STAGE2_BOUNDS = {"SPY": (0.20, 0.70), "IEF": (0.15, 0.60), "LQD": (0.10, 0.40)}   # stage2_portfolio LOWER / UPPER
JEV_BOUNDS = {"SPY": (0.40, 0.80)}                                                 # allocation.js MIN_SPY / MAX_SPY
JEV_MAX_OFFSET = 3.0                                                               # livebacktest.js TILT_OFFSET extremes
ON, OFF = {"AP1": "AP1_ON", "AP2B": "AP2B_ON", "AP3": "AP3_ON"}, {"AP1": "AP1_OFF", "AP2B": "AP2B_OFF", "AP3": "AP3_OFF"}
DEC_FILE = {"AP1": "AP1.jsonl", "AP2B": "AP2B.jsonl", "AP3": "AP3_qwen3_reduced_evidence.jsonl"}
HE, HB = "JEV_STOCKS_DET_BONDS", "DET_STOCKS_JEV_BONDS"


# ----------------------------------------------------------------------------------------------- construction
def mixes(cfg: dict) -> Dict[str, Dict[str, float]]:
    """The two no-signal mixes, and the two hybrids used to split their difference into a stock and a bond part."""
    d, j = cfg["systems"]["AP1"]["native_neutral_weights"], cfg["systems"]["AP2B"]["native_neutral_weights"]
    sd, sj = d["SPY"], j["SPY"]
    d_bonds = {a: w / (1 - sd) for a, w in d.items() if a != "SPY"}
    j_bonds = {a: w / (1 - sj) for a, w in j.items() if a != "SPY"}
    out = {"AP1": dict(d), "AP2B": dict(j),
           HE: {"SPY": sj, **{a: (1 - sj) * v for a, v in d_bonds.items()}},
           HB: {"SPY": sd, **{a: (1 - sd) * v for a, v in j_bonds.items()}},
           "_bond_sleeves": {"AP1": d_bonds, "AP2B": j_bonds}}
    if AP3_DECISIONS.exists():
        a3 = cfg["systems"]["AP3"]["native_neutral_weights"]
        out["AP3"] = dict(a3)
        s3 = a3["SPY"]
        out["_bond_sleeves"]["AP3"] = {a: w / (1 - s3) for a, w in a3.items() if a != "SPY"}
    return out


def drift_records(weights: Dict[str, float], template, mk, dev) -> list:
    """Buy-and-hold sensitivity: the mix is bought at the first entry close and then left to drift (no rebalancing)."""
    assets, w, out = list(weights), np.array(list(weights.values()), float), []
    for m, rec in zip(dev, static_portfolio_records("BUY_AND_HOLD", weights, template)):
        out.append(dataclasses.replace(rec, target_weights=dict(zip(assets, map(float, w))),
                                       generation={"mode": "computed_native", "benchmark": "buy_and_hold", "weights": dict(weights)}))
        r = np.array([mk.period_returns(m, assets)[a] for a in assets])
        g = w * (1 + r)
        w = g / g.sum()
    return out


def present_systems() -> list:
    """AP1 and AP2B always; AP3 only once its genuine development decisions have been imported."""
    return list(SYSTEMS) + (["AP3"] if AP3_DECISIONS.exists() else [])


def build(cfg, mk, dev) -> dict:
    cost = cfg["costs"]["cost_per_dollar_traded"]
    recs = {}
    for s in present_systems():
        by = {r.decision_month: r for r in read_jsonl(DEC / DEC_FILE[s])}
        recs[s] = [by[str(m)] for m in dev]
    mx = mixes(cfg)
    sim = lambda rs: simulate_records(rs, mk, dev, cost_per_dollar=cost)
    S = {}
    for s in present_systems():
        S[ON[s]] = sim(recs[s])
        S[OFF[s]] = sim(static_portfolio_records(f"{s}_NO_SIGNAL", mx[s], recs[s]))
        S[f"{s}_OFF_BUY_AND_HOLD"] = sim(drift_records(mx[s], recs[s], mk, dev))
    for k in (HE, HB):
        S[k] = sim(static_portfolio_records(k, mx[k], recs["AP1"]))
    months = [str(m) for m in dev]
    for k, v in S.items():
        assert v["decision_month"].tolist() == months, k
    asset_r = pd.DataFrame([{"decision_month": str(m), **mk.period_returns(m, ASSETS)} for m in dev])
    return {"records": recs, "mixes": mx, "sims": S, "asset_returns": asset_r}


# ----------------------------------------------------------------------------------------------- statistics
def frozen(cfg) -> dict:
    m = cfg["metrics"]
    return {"delta": m["cer_delta"], "block": m["bootstrap_block_months"], "reps": m["bootstrap_reps"], "seed": m["bootstrap_seed"]}


def mblock(sim: pd.DataFrame) -> dict:
    m = M.metrics(sim)
    return {"net_cer": m["cer_delta_2_5"], "net_annualized_excess_return": m["net_annualized_excess_return"],
            "cumulative_return": B.cumulative_return(sim), "net_sharpe": m["net_sharpe"], "max_drawdown": m["max_drawdown"],
            "annualized_volatility": m["annualized_volatility"], "annualized_one_way_turnover": m["annualized_one_way_turnover"],
            "total_cost": m["total_cost"], "annualized_cost": 12.0 * float(sim["cost"].mean()), "n_months": m["n_months"]}


def summarise_draws(point: float, d: np.ndarray) -> dict:
    return {"point": point, "ci90": [float(np.percentile(d, 5)), float(np.percentile(d, 95))],
            "ci95": [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))],
            "p_two_sided_bootstrap": float(min(1.0, 2.0 * min(np.mean(d <= 0.0), np.mean(d >= 0.0)))),
            "share_of_draws_above_zero": float(np.mean(d > 0.0))}


def joint_bootstrap(x: Dict[str, np.ndarray], stats: Dict[str, Callable[[Dict[str, float]], float]], P: dict) -> dict:
    """The frozen paired circular block bootstrap (metrics.paired_cer_contrast), applied to several series at once.

    Every statistic is computed on the same resampled months. For a two-series statistic the draws are identical
    to paired_cer_contrast's: same sampler, same seed, one index draw per replication."""
    T = len(next(iter(x.values())))
    rng = np.random.default_rng(P["seed"])
    draws = {k: np.empty(P["reps"]) for k in stats}
    for i in range(P["reps"]):
        idx = M._block_indices(T, P["block"], rng)
        c = {k: M.cer(v[idx], P["delta"]) for k, v in x.items()}
        for k, f in stats.items():
            draws[k][i] = f(c)
    pt = {k: M.cer(v, P["delta"]) for k, v in x.items()}
    return {k: summarise_draws(f(pt), draws[k]) for k, f in stats.items()}


def clear(c: dict) -> bool:
    return bool(c["p_two_sided_bootstrap"] < 0.05 and (c["ci95"][0] > 0 or c["ci95"][1] < 0))


def incremental(on: pd.DataFrame, off: pd.DataFrame, P: dict) -> dict:
    c = M.paired_cer_contrast(on, off, delta=P["delta"], block=P["block"], reps=P["reps"], seed=P["seed"])
    a = on["net_excess_return"].to_numpy(float) - off["net_excess_return"].to_numpy(float)
    mon, moff = mblock(on), mblock(off)
    te = math.sqrt(12.0) * float(a.std(ddof=1))
    be = M.s2p.break_even_cost(on, off)
    return {"net_cer_difference": c["cer_difference"], "ci90": c["ci90"], "ci95": c["ci95"], "p_two_sided_bootstrap": c["p_two_sided_bootstrap"],
            "statistically_clear_at_5pct": clear(c),
            "observed_direction": "higher with signals" if c["cer_difference"] > 0 else "lower with signals",
            "mean_active_return_annualised": 12.0 * float(a.mean()), "tracking_error_annualised": te,
            "information_ratio": 12.0 * float(a.mean()) / te if te > 0 else None,
            "months_active_positive": int((a > 0).sum()), "months": int(len(a)),
            "differences_with_minus_without": {k: mon[k] - moff[k] for k in mon if k != "n_months"},
            "break_even_cost_stage2_convention_14": {k: (float(v) if isinstance(v, (int, float, np.floating)) and not isinstance(v, bool) else v) for k, v in be.items()},
            "bootstrap": {"block_months": c["block_months"], "replications": c["replications"], "seed": c["seed"]}}


# ----------------------------------------------------------------------------------------------- attribution
def attribution(S: dict, P: dict) -> dict:
    """Exact accounting identities for CER(JEV) - CER(Deterministic). Not a causal attribution.

    The stock/bond split of the mix difference is a two-factor Shapley average over the two hybrid mixes, so it is
    order-free and exact; both orders are reported. The tilt terms use the identity
    CER(x0 + t) - CER(x0) = 12 mean(t) - 6 delta var(t) - 12 delta cov(x0, t), with sample (ddof = 1) moments."""
    d = P["delta"]
    cer = lambda v: M.cer(v, d)
    x = {k: S[k]["net_excess_return"].to_numpy(float) for k in S}
    g = {k: S[k]["gross_excess_return"].to_numpy(float) for k in S}
    D1, D0, J1, J0 = ON["AP1"], OFF["AP1"], ON["AP2B"], OFF["AP2B"]
    total = cer(x[J1]) - cer(x[D1])

    def shapley(v):
        a1, a2 = cer(v[HE]) - cer(v[D0]), cer(v[J0]) - cer(v[HE])     # stocks first, then bonds
        b1, b2 = cer(v[HB]) - cer(v[D0]), cer(v[J0]) - cer(v[HB])     # bonds first, then stocks
        return 0.5 * (a1 + b2), 0.5 * (b1 + a2), {"stocks_first": {"stock": a1, "bond": a2}, "bonds_first": {"bond": b1, "stock": b2}}

    stock_g, bond_g, order_g = shapley(g)
    stock_n, bond_n, order_n = shapley(x)
    per = {}
    # per-system quantities (each approach against its OWN no-signal portfolio). The two- and four-part
    # decompositions below stay the JEV-minus-Deterministic pair they were defined for.
    for s in present_systems():
        on, off = ON[s], OFF[s]
        t = g[on] - g[off]
        standalone = 12.0 * float(t.mean()) - 6.0 * d * float(np.var(t, ddof=1))
        interaction = -12.0 * d * float(np.cov(g[off], t, ddof=1)[0, 1])
        extra = (cer(x[on]) - cer(g[on])) - (cer(x[off]) - cer(g[off]))
        sva = cer(x[on]) - cer(x[off])
        per[s] = {"signal_value_net": sva, "tilts_before_costs": cer(g[on]) - cer(g[off]),
                  "tilts_before_costs_standalone": standalone, "interaction_tilt_with_own_mix": interaction,
                  "extra_costs_from_tilts": extra, "residual": sva - (standalone + interaction + extra)}
    mix_gross, mix_net = cer(g[J0]) - cer(g[D0]), cer(x[J0]) - cer(x[D0])
    costs_all = (cer(x[J1]) - cer(g[J1])) - (cer(x[D1]) - cer(g[D1]))
    mix_costs = (cer(x[J0]) - cer(g[J0])) - (cer(x[D0]) - cer(g[D0]))
    tilt_costs = per["AP2B"]["extra_costs_from_tilts"] - per["AP1"]["extra_costs_from_tilts"]
    four = {"1a_mix_stock_weight_before_costs": stock_g,
            "1b_mix_bond_sleeve_before_costs": bond_g,
            "2a_jev_tilts_before_costs": per["AP2B"]["tilts_before_costs_standalone"],
            "2b_minus_deterministic_tilts_before_costs": -per["AP1"]["tilts_before_costs_standalone"],
            "3_trading_costs": costs_all,
            "4_interaction_tilts_with_mix": per["AP2B"]["interaction_tilt_with_own_mix"] - per["AP1"]["interaction_tilt_with_own_mix"]}
    two = {"mix_stock_weight_net": stock_n, "mix_bond_sleeve_net": bond_n,
           "jev_signal_value": per["AP2B"]["signal_value_net"], "minus_deterministic_signal_value": -per["AP1"]["signal_value_net"]}
    return {"total_net_cer_difference": total,
            "four_parts": four, "four_parts_residual": total - sum(four.values()),
            "trading_costs_split": {"rebalancing_the_mixes": mix_costs, "extra_trading_from_tilts": tilt_costs, "residual": costs_all - mix_costs - tilt_costs},
            "mix_before_costs": mix_gross, "mix_before_costs_shapley_residual": mix_gross - stock_g - bond_g, "mix_order_effects_before_costs": order_g,
            "two_by_two": two, "two_by_two_residual": total - sum(two.values()),
            "mix_net_of_costs": mix_net, "mix_net_shapley_residual": mix_net - stock_n - bond_n, "mix_order_effects_net": order_n,
            "per_system": per}


def return_attribution(S: dict, mx: dict, ar: pd.DataFrame) -> dict:
    """The same split on average annual return above cash (12 x the monthly mean). It is linear, so it is exact
    month by month, with no risk penalty and no interaction term."""
    D1, D0, J1, J0 = (S[k] for k in (ON["AP1"], OFF["AP1"], ON["AP2B"], OFF["AP2B"]))
    sd, sj = mx["AP1"]["SPY"], mx["AP2B"]["SPY"]
    bd = sum(w * ar[a] for a, w in mx["_bond_sleeves"]["AP1"].items())
    bj = sum(w * ar[a] for a, w in mx["_bond_sleeves"]["AP2B"].items())
    stock = (sj - sd) * (ar["SPY"] - bd)                    # more stocks, paid for out of Deterministic's bond sleeve
    bond = (1 - sj) * (bj - bd)                             # JEV's bond sleeve in place of Deterministic's
    tilt_j = J1["gross_total_return"] - J0["gross_total_return"]
    tilt_d = D1["gross_total_return"] - D0["gross_total_return"]
    costs = -(J1["cost"] - D1["cost"])
    total = J1["net_excess_return"] - D1["net_excess_return"]
    mix_check = (J0["gross_total_return"] - D0["gross_total_return"]) - (stock + bond)
    resid = total - (stock + bond + tilt_j - tilt_d + costs)
    parts = {"mix_stock_weight": stock, "mix_bond_sleeve": bond, "jev_tilts": tilt_j, "minus_deterministic_tilts": -tilt_d, "trading_costs": costs}
    ann = {k: 12.0 * float(v.mean()) for k, v in parts.items()}
    cost_split = {"rebalancing_the_mixes": -12.0 * float((J0["cost"] - D0["cost"]).mean()),
                  "extra_trading_from_tilts": -12.0 * float(((J1["cost"] - J0["cost"]) - (D1["cost"] - D0["cost"])).mean())}
    monthly = pd.DataFrame({"decision_month": D1["decision_month"], **{f"ret_attr_{k}": v for k, v in parts.items()}, "ret_attr_total": total})
    return {"annualised_mean_difference": 12.0 * float(total.mean()), "parts_annualised": ann, "trading_costs_split_annualised": cost_split,
            "max_abs_monthly_residual": float(np.abs(resid).max()), "max_abs_mix_identity_residual": float(np.abs(mix_check).max()),
            "_monthly": monthly}


# ----------------------------------------------------------------------------------------------- decisions
def sign_changes(v: np.ndarray, tol: float = 1e-12) -> int:
    s = np.sign(np.where(np.abs(v) < tol, 0.0, v))
    s = s[s != 0]
    return int((s[1:] != s[:-1]).sum())


def decisions(built: dict, ar: pd.DataFrame) -> dict:
    S, mx, recs = built["sims"], built["mixes"], built["records"]
    out = {}
    for s in present_systems():
        on, off = S[ON[s]], S[OFF[s]]
        assets = list(mx[s])
        tilt = pd.DataFrame({a: on[f"w_{a}"] - mx[s][a] for a in assets})
        one_way = 0.5 * tilt.abs().sum(axis=1)
        spy = tilt["SPY"].to_numpy()
        sleeve = sum(w * ar[a] for a, w in mx["_bond_sleeves"][s].items())
        t = (on["gross_total_return"] - off["gross_total_return"]).to_numpy()
        c_extra = (on["cost"] - off["cost"]).to_numpy()
        # Causal RAG allocates through the same Stage 2 optimiser as the Deterministic model, so it has the
        # same weight bounds; only JEV uses its own capped-tilt range.
        bounds = JEV_BOUNDS if s == "AP2B" else STAGE2_BOUNDS
        at_bound = sum(int(((on[f"w_{a}"] - lo).abs() < 1e-9).sum() + ((on[f"w_{a}"] - hi).abs() < 1e-9).sum()) for a, (lo, hi) in bounds.items())
        o = {"one_way_tilt_mean": float(one_way.mean()), "one_way_tilt_max": float(one_way.max()),
             "spy_tilt": {"mean": float(spy.mean()), "sd": float(spy.std(ddof=1)), "min": float(spy.min()), "max": float(spy.max()),
                          "months_overweight": int((spy > 0).sum()), "months_underweight": int((spy < 0).sum())},
             "tilt_sd_by_asset": {a: float(tilt[a].std(ddof=1)) for a in assets},
             "spy_tilt_direction_changes": sign_changes(spy), "possible_direction_changes": int(len(spy) - 1),
             "months_spy_tilt_at_least": {"1pt": int((np.abs(spy) >= 0.01).sum()), "2pt": int((np.abs(spy) >= 0.02).sum()), "5pt": int((np.abs(spy) >= 0.05).sum())},
             "months_at_a_weight_bound": at_bound, "weight_bounds": {a: list(v) for a, v in bounds.items()},
             "turnover_with_minus_without_annualised": 12.0 * float((on["one_way_turnover"] - off["one_way_turnover"]).mean()),
             "tilt_hit_rate_before_costs": float((t > 0).mean()),
             "tilt_timing_correlation": float(np.corrcoef(spy, ar["SPY"].to_numpy() - sleeve.to_numpy())[0, 1]),
             "tilt_return_before_costs_annualised": 12.0 * float(t.mean()), "extra_cost_annualised": 12.0 * float(c_extra.mean()),
             "tilt_return_after_costs_annualised": 12.0 * float((t - c_extra).mean()),
             "tilt_covers_its_costs": bool(t.mean() > c_extra.mean())}
        W, R = on[[f"w_{a}" for a in assets]].to_numpy(float), ar[assets].to_numpy(float)
        w0v, wbar = np.array([mx[s][a] for a in assets]), on[[f"w_{a}" for a in assets]].to_numpy(float).mean(axis=0)
        bias, timing = R @ (wbar - w0v), ((W - wbar) * R).sum(axis=1)
        assert np.abs(bias + timing - t).max() < 1e-14
        g_off, g_on = off["gross_excess_return"].to_numpy(float), on["gross_excess_return"].to_numpy(float)
        o["average_tilt_vs_timing_ex_post"] = {
            "note": "uses the full-period average weights, known only afterwards: descriptive only",
            "average_tilt": {a: float(wbar[i] - w0v[i]) for i, a in enumerate(assets)},
            "average_tilt_return_annualised": 12.0 * float(bias.mean()), "timing_return_annualised": 12.0 * float(timing.mean()),
            "cer_before_costs_from_average_tilt": M.cer(g_off + bias) - M.cer(g_off), "cer_before_costs_from_timing": M.cer(g_on) - M.cer(g_off + bias)}
        k = int(one_way.idxmax())
        o["largest_tilt_month"] = {"decision_month": on["decision_month"].iloc[k], "one_way_tilt": float(one_way.iloc[k]),
                                   "weights": {a: float(on[f"w_{a}"].iloc[k]) for a in assets},
                                   "active_net_return_that_month": float(on["net_excess_return"].iloc[k] - off["net_excess_return"].iloc[k])}
        if s in ("AP1", "AP3"):
            # Both allocate through Stage 2's Black-Litterman, so both get the same survival analysis. AP1's
            # diagnostics are the archived Stage 2 run; AP3's are its own 1x transmission trace.
            if s == "AP1":
                bl = pd.read_csv(STAGE2 / "stage2_portfolio_bl_diagnostics.csv")
                bl = bl[bl["strategy"] == "A"]
            else:
                bl = pd.read_csv(AP3_TRACE)
                bl = bl[bl["scenario"] == "1x"].rename(columns={f"q_orig_{a}": f"q_{a}" for a in assets})
            bl = bl.astype({"decision_month": str}).set_index("decision_month").loc[on["decision_month"]]
            o["native_bl_weights_match_records"] = float(max(np.abs(bl[f"w_{a}"].to_numpy() - on[f"w_{a}"].to_numpy()).max() for a in assets))
            surv = {}
            for a in assets:
                dq, dm = (bl[f"q_{a}"] - bl[f"pi_{a}"]).to_numpy(), (bl[f"mu_bl_{a}"] - bl[f"pi_{a}"]).to_numpy()
                surv[a] = {"forecast_sd": float(bl[f"q_{a}"].std(ddof=1)), "forecast_minus_prior_sd": float(dq.std(ddof=1)),
                           "posterior_minus_prior_sd": float(dm.std(ddof=1)), "share_of_forecast_departure_kept": float(np.abs(dm).mean() / np.abs(dq).mean()),
                           "corr_weight_tilt_with_posterior_departure": float(np.corrcoef(tilt[a], dm)[0, 1])}
            o["forecast_survival_through_black_litterman"] = surv
            rel = (bl["q_SPY"] - 0.5 * (bl["q_IEF"] + bl["q_LQD"])).to_numpy()
            terc = pd.qcut(rel, 3, labels=["lowest third", "middle third", "highest third"])
            grp = pd.Series(on["w_SPY"].to_numpy()).groupby(np.asarray(terc)).mean()
            o["spy_weight_by_forecast_tercile"] = {str(k): float(v) for k, v in grp.items()}
            o["spy_weight_range_across_forecast_terciles"] = float(grp.max() - grp.min())
            o["forecast_spread_corr_with_spy_tilt"] = float(np.corrcoef(rel, spy)[0, 1])
        else:
            fc = [r.forecast["values"] for r in recs[s]]
            conf = np.array([r.confidence["applied"] for r in recs[s]], float)
            offset = np.array([v["offset"] for v in fc], float)
            p = np.array([v["p"] for v in fc], float)
            choice = [v["choice"] for v in fc]
            applied = conf * offset
            slope = float(np.polyfit(applied, spy, 1)[0])
            o["forecast_survival_through_allocation"] = {
                "offset_sd_points": float(offset.std(ddof=1)), "offset_range_points": [float(offset.min()), float(offset.max())],
                "max_possible_offset_points": JEV_MAX_OFFSET, "confidence_mean": float(conf.mean()), "confidence_range": [float(conf.min()), float(conf.max())],
                "applied_edge_sd_points": float(applied.std(ddof=1)), "share_of_offset_kept_after_confidence": float(np.abs(applied).mean() / np.abs(offset).mean()),
                "spy_weight_points_per_applied_edge_point": 100.0 * slope, "corr_spy_tilt_with_applied_edge": float(np.corrcoef(applied, spy)[0, 1]),
                "corr_spy_tilt_with_p_stocks_beat_bonds": float(np.corrcoef(p, spy)[0, 1])}
            side = np.array([1 if c.endswith("equities") else -1 if c.endswith("bonds") else 0 for c in choice])
            o["choice_direction_changes"] = sign_changes(side.astype(float))
            o["choices"] = {c: int(choice.count(c)) for c in sorted(set(choice))}
            grp = pd.Series(on["w_SPY"].to_numpy()).groupby(np.asarray(choice)).mean()
            o["spy_weight_by_choice"] = {str(k): float(v) for k, v in grp.items()}
            o["spy_weight_range_across_choices"] = float(grp.max() - grp.min())
        out[s] = o
    return out


def regimes(built: dict, mk, dev, ar: pd.DataFrame) -> dict:
    S = built["sims"]
    spy = mk.prices["SPY"].reindex(mk.calendar)
    lr = np.log(spy).diff()
    vol = []
    for m in dev:
        day = mk.decision_dates[m]
        w = lr.loc[:day].iloc[-VOL_WINDOW:]
        assert w.index[-1] == day and len(w) == VOL_WINDOW
        vol.append(float(w.std(ddof=1) * math.sqrt(252.0)))
    lab = pd.DataFrame({"decision_month": [str(m) for m in dev], "spy_vol_63d_at_decision": vol})
    lab["volatility_at_decision"] = np.where(lab["spy_vol_63d_at_decision"] >= VOL_THRESHOLD, "high (20%+ a year)", "normal (below 20%)")
    lab["year"] = lab["decision_month"].str[:4]
    lab["stock_market_that_month_ex_post"] = np.where(ar["SPY"].to_numpy() >= 0, "SPY up", "SPY down")
    out = {"definitions": {"year": "calendar year of the decision month",
                           "volatility_at_decision": f"SPY realised volatility over the {VOL_WINDOW} common trading days up to the decision close, annualised; "
                                                     f"'high' at {VOL_THRESHOLD:.0%} or more. Known at the decision date.",
                           "stock_market_that_month_ex_post": "whether SPY rose over the holding month: known only afterwards, so descriptive only"},
           "caution": "Small groups and several splits: descriptive only, no significance claimed."}
    for s in present_systems():
        a = (S[ON[s]]["net_excess_return"] - S[OFF[s]]["net_excess_return"]).to_numpy()
        res = {}
        for col in ("year", "volatility_at_decision", "stock_market_that_month_ex_post"):
            res[col] = {}
            for k, idx in lab.groupby(col).groups.items():
                v = a[np.asarray(list(idx))]
                res[col][str(k)] = {"months": int(len(v)), "active_return_sum": float(v.sum()), "active_return_mean_monthly": float(v.mean()),
                                    "months_signals_ahead": int((v > 0).sum())}
        out[s] = res
    return out, lab


def influence(S: dict, P: dict) -> dict:
    """Leave-one-month-out: how much each result depends on a single month (descriptive)."""
    d = P["delta"]
    sysms = present_systems()
    keys = [k for s_ in sysms for k in (ON[s_], OFF[s_])]
    x = {k: S[k]["net_excess_return"].to_numpy(float) for k in keys}
    months = S[ON["AP1"]]["decision_month"].tolist()
    sv = lambda s_: (lambda v: M.cer(v[ON[s_]], d) - M.cer(v[OFF[s_]], d))
    stats = {s_: sv(s_) for s_ in sysms}
    stats["jev_minus_deterministic_signal_value"] = lambda v: (M.cer(v[ON["AP2B"]], d) - M.cer(v[OFF["AP2B"]], d)) - (M.cer(v[ON["AP1"]], d) - M.cer(v[OFF["AP1"]], d))
    out = {}
    for k, f in stats.items():
        full = f(x)
        loo = np.array([f({n: np.delete(v, i) for n, v in x.items()}) for i in range(len(months))])
        i = int(np.argmax(np.abs(loo - full)))
        out[k] = {"full": full, "leave_one_out_min": float(loo.min()), "leave_one_out_max": float(loo.max()),
                  "most_influential_month": months[i], "without_most_influential_month": float(loo[i]),
                  "months_whose_removal_flips_the_sign": int((np.sign(loo) != np.sign(full)).sum())}
    return out


def information_checks(recs: dict, mk, dev) -> dict:
    """Point-in-time checks on the decision records used: each decision is dated on the last common trading day of
    its month, its information cutoff is at or before the decision time, and JEV's saved answer is dated on or
    before the decision date. The no-signal portfolios use no information at all."""
    problems = []
    for s, rs in recs.items():
        for m, r in zip(dev, rs):
            dt, cut = pd.Timestamp(r.decision_time), pd.Timestamp(r.info_cutoff)
            if dt.date() != mk.decision_dates[m].date():
                problems.append(f"{s} {m}: decision date {dt.date()} is not the last common trading day")
            if cut > dt:
                problems.append(f"{s} {m}: information cutoff after the decision time")
            nat = (r.generation or {}).get("native_as_of")
            if nat and pd.Timestamp(nat).date() > dt.date():
                problems.append(f"{s} {m}: native answer dated after the decision")
    return {"records_checked": sum(len(v) for v in recs.values()), "problems": problems}


# ----------------------------------------------------------------------------------------------- sensitivities
def jev_native(dev, P) -> dict:
    """The native JEV engine with Jev's tilt switched off (offset 0), on the development months only."""
    out = OUT / "jev_native_signal_on_off_engine.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["node", str(HARNESS), f"--engine={JEV_ENGINE}", f"--last-as-of={LAST_DEV_AS_OF}", f"--out={out.relative_to(ROOT)}"],
                   cwd=ROOT, check=True, capture_output=True, text=True)
    d = json.loads(out.read_text())
    rows = pd.DataFrame(d["rows"])
    months = [str(m) for m in dev]
    assert rows["as_of"].max() <= LAST_DEV_AS_OF
    for k in ("on", "off", "fixed"):
        nav = rows[f"nav_{k}"].to_numpy()
        rows[f"net_{k}"] = nav / np.concatenate([[1.0], nav[:-1]]) - 1.0
    rows["decision_month"] = rows["as_of"].str[:7]
    sel = rows[rows["decision_month"].isin(months)].reset_index(drop=True)
    assert sel["decision_month"].tolist() == months
    frame = lambda k: pd.DataFrame({"decision_month": sel["decision_month"], "net_excess_return": sel[f"net_{k}"] - sel["rf_month"],
                                    "net_total_return": sel[f"net_{k}"]})
    on, off = frame("on"), frame("off")
    c = M.paired_cer_contrast(on, off, delta=P["delta"], block=P["block"], reps=P["reps"], seed=P["seed"])
    recs = {r.decision_month: r for r in read_jsonl(DEC / "AP2B.jsonl")}
    cum = lambda f: float(np.prod(1 + f["net_total_return"]) - 1)
    return {"convention": "native JEV engine (vendored feature-jev livebacktest.js, unchanged): trade at the decision close, "
                          "5 bp per unit of one-way SPY turnover against the drifted weight, monthly rebalancing to target, native returns and cash",
            "signal_disabled_how": "Jev's saved answers with offset set to 0, so edge = equilibrium edge + confidence x 0",
            "months": len(sel), "first_as_of": sel["as_of"].iloc[0], "last_as_of": sel["as_of"].iloc[-1],
            "max_abs_spy_weight_off_minus_60pct": float(np.abs(rows["w_off"] - 0.60).max()),
            "max_abs_prior_weight_minus_60pct": float(np.abs(rows["w_prior_pct"] / 100.0 - 0.60).max()),
            "max_abs_nav_off_minus_engine_fixed_60_40": float(np.abs(rows["nav_off"] - rows["nav_fixed"]).max()),
            "max_abs_weight_on_minus_decision_records": float(max(abs(r.w_on - recs[r.as_of[:7]].target_weights["SPY"]) for r in rows.itertuples() if r.as_of[:7] in recs)),
            "net_cer_with": M.cer(on["net_excess_return"], P["delta"]), "net_cer_without": M.cer(off["net_excess_return"], P["delta"]),
            "cumulative_with": cum(on), "cumulative_without": cum(off),
            "incremental": {"net_cer_difference": c["cer_difference"], "ci95": c["ci95"], "ci90": c["ci90"], "p_two_sided_bootstrap": c["p_two_sided_bootstrap"],
                            "statistically_clear_at_5pct": clear(c)},
            "engine_output": str(out.relative_to(ROOT))}


def stage2_native(S: dict, P: dict) -> dict:
    r = pd.read_csv(STAGE2 / "stage2_portfolio_returns.csv").astype({"decision_month": str})
    m = pd.read_csv(STAGE2 / "stage2_portfolio_metrics.csv").set_index("strategy")
    get = lambda k: r[r["strategy"] == k].sort_values("decision_month").reset_index(drop=True)
    a, st, hm = get("A"), get("BENCH_STATIC_45_35_20"), get("BENCH_HISTMEAN_ALLOCATOR")
    c = M.paired_cer_contrast(a, hm, delta=P["delta"], block=P["block"], reps=P["reps"], seed=P["seed"])
    return {"max_abs_diff_net_return_A_vs_signals_on": float(np.abs(a["net_total_return"].to_numpy() - S[ON["AP1"]]["net_total_return"].to_numpy()).max()),
            "max_abs_diff_net_return_static_vs_signals_off": float(np.abs(st["net_total_return"].to_numpy() - S[OFF["AP1"]]["net_total_return"].to_numpy()).max()),
            "frozen_break_even_vs_static_status": m.loc["A", "break_even_vs_static_45_35_20_status"],
            "naive_forecast_reference": {"what": "Stage 2's frozen BENCH_HISTMEAN_ALLOCATOR: the same Black-Litterman allocator fed historical-mean forecasts",
                                         "net_cer": M.cer(hm["net_excess_return"], P["delta"]),
                                         "deterministic_minus_naive": {"net_cer_difference": c["cer_difference"], "ci95": c["ci95"], "p_two_sided_bootstrap": c["p_two_sided_bootstrap"]},
                                         "frozen_break_even_bps": float(m.loc["A", "break_even_vs_histmean_allocator_bps"])}}


def buy_and_hold(S: dict, P: dict) -> dict:
    out = {}
    for s in present_systems():
        bh = S[f"{s}_OFF_BUY_AND_HOLD"]
        c = M.paired_cer_contrast(S[ON[s]], bh, delta=P["delta"], block=P["block"], reps=P["reps"], seed=P["seed"])
        out[s] = {"net_cer_without_buy_and_hold": M.cer(bh["net_excess_return"], P["delta"]),
                  "cumulative_without_buy_and_hold": B.cumulative_return(bh),
                  "spy_weight_at_end": float(bh["w_SPY"].iloc[-1]), "traded_after_first_month": float(bh["traded_notional"].iloc[1:].sum()),
                  "incremental": {"net_cer_difference": c["cer_difference"], "ci95": c["ci95"], "p_two_sided_bootstrap": c["p_two_sided_bootstrap"],
                                  "statistically_clear_at_5pct": clear(c)}}
    return out


# ----------------------------------------------------------------------------------------------- main
def main(argv=None) -> int:
    cfg = load_config()
    dev = months_between(*cfg["windows"]["development"])
    assert_scoring_allowed(dev, protected_start=cfg["windows"]["protected"][0])
    mk = load_market(cfg)
    P = frozen(cfg)
    built = build(cfg, mk, dev)
    S, mx, ar = built["sims"], built["mixes"], built["asset_returns"]

    systems = {}
    meta_all = {**SYSTEMS, **({"AP3": AP3_META} if "AP3" in built["records"] else {})}
    for s, meta in meta_all.items():
        on, off = S[ON[s]], S[OFF[s]]
        systems[s] = {**meta, "universe": list(mx[s]), "no_signal_weights": mx[s],
                      "with_signals": mblock(on), "without_signals": mblock(off), "incremental": incremental(on, off, P)}
    if "AP3" in systems:
        systems["AP3"]["note"] = (
            "Causal RAG's frozen neutral weights are the same 45/35/20 portfolio as the Deterministic model's, so "
            "the two share an identical no-signal control. Its incremental value is therefore directly comparable "
            "with the Deterministic model's, and not with JEV's, whose control is a different portfolio.")

    keys = [ON["AP1"], OFF["AP1"], ON["AP2B"], OFF["AP2B"], HE, HB]
    if "AP3" in systems:
        keys += [ON["AP3"], OFF["AP3"]]
    x = {k: S[k]["net_excess_return"].to_numpy(float) for k in keys}
    D1, D0, J1, J0 = ON["AP1"], OFF["AP1"], ON["AP2B"], OFF["AP2B"]
    stats = {"deterministic_signal_value": lambda c: c[D1] - c[D0],
             "jev_signal_value": lambda c: c[J1] - c[J0],
             "jev_minus_deterministic_signal_value": lambda c: (c[J1] - c[J0]) - (c[D1] - c[D0]),
             "jev_minus_deterministic_total": lambda c: c[J1] - c[D1],
             "no_signal_mix_difference": lambda c: c[J0] - c[D0],
             "mix_stock_weight_net": lambda c: 0.5 * ((c[HE] - c[D0]) + (c[J0] - c[HB])),
             "mix_bond_sleeve_net": lambda c: 0.5 * ((c[HB] - c[D0]) + (c[J0] - c[HE]))}
    if "AP3" in systems:
        R1, R0 = ON["AP3"], OFF["AP3"]
        stats["causal_rag_signal_value"] = lambda c: c[R1] - c[R0]
        stats["causal_rag_minus_deterministic_signal_value"] = lambda c: (c[R1] - c[R0]) - (c[D1] - c[D0])
        stats["causal_rag_minus_jev_signal_value"] = lambda c: (c[R1] - c[R0]) - (c[J1] - c[J0])
        stats["causal_rag_minus_deterministic_total"] = lambda c: c[R1] - c[D1]
    jb = joint_bootstrap(x, stats, P)
    for k in jb:
        jb[k]["statistically_clear_at_5pct"] = clear(jb[k])

    # previously reported results: the development report's own-benchmark and primary contrasts must be reproduced exactly
    rep = json.loads(DEV_REPORT.read_text())
    rows = {r["system"]: r for r in rep["common_evaluation_matched_dev"]}
    prim = rep["primary_contrasts_matched_dev"]["computed"]["AP2B-AP1"]
    checks = {}
    for s, key in (("AP1", "deterministic_signal_value"), ("AP2B", "jev_signal_value")):
        prev = rows[s]["vs_own_neutral"]
        checks[s] = {"previously_reported_vs_own_benchmark": prev["cer_difference"], "ci95_previous": prev["ci95"], "p_previous": prev["p_two_sided_bootstrap"],
                     "max_abs_difference": max(abs(prev["cer_difference"] - jb[key]["point"]), abs(prev["ci95"][0] - jb[key]["ci95"][0]),
                                               abs(prev["ci95"][1] - jb[key]["ci95"][1]), abs(prev["p_two_sided_bootstrap"] - jb[key]["p_two_sided_bootstrap"]),
                                               abs(prev["cer_difference"] - systems[s]["incremental"]["net_cer_difference"])),
                     "previous_no_signal_net_cer": rows[s]["native_neutral"]["cer_delta_2_5"],
                     "no_signal_net_cer_abs_difference": abs(rows[s]["native_neutral"]["cer_delta_2_5"] - systems[s]["without_signals"]["net_cer"])}
    if "AP3" in systems:
        ev = json.loads((ROOT / "native_backtest/out/ap3/qwen3_runs/evaluation/evaluation.json").read_text())
        prev = ev["vs_own_benchmark"]
        checks["AP3"] = {"source": "native_backtest/out/ap3/qwen3_runs/evaluation/evaluation.json (exploratory)",
                         "previously_reported_vs_own_benchmark": prev["cer_difference"], "ci95_previous": prev["ci95"],
                         "p_previous": prev["p_two_sided_bootstrap"],
                         "max_abs_difference": max(abs(prev["cer_difference"] - jb["causal_rag_signal_value"]["point"]),
                                                   abs(prev["ci95"][0] - jb["causal_rag_signal_value"]["ci95"][0]),
                                                   abs(prev["ci95"][1] - jb["causal_rag_signal_value"]["ci95"][1]),
                                                   abs(prev["cer_difference"] - systems["AP3"]["incremental"]["net_cer_difference"])),
                         "previous_with_signals_net_cer": ev["metrics"]["AP3"]["cer_delta_2_5"],
                         "with_signals_net_cer_abs_difference": abs(ev["metrics"]["AP3"]["cer_delta_2_5"] - systems["AP3"]["with_signals"]["net_cer"])}
    jt = jb["jev_minus_deterministic_total"]
    checks["primary_contrast_AP2B_minus_AP1"] = {"previously_reported": prim["cer_difference"], "ci95_previous": prim["ci95"], "p_previous": prim["p_two_sided_bootstrap"],
                                                 "max_abs_difference": max(abs(prim["cer_difference"] - jt["point"]), abs(prim["ci95"][0] - jt["ci95"][0]),
                                                                           abs(prim["ci95"][1] - jt["ci95"][1]), abs(prim["p_two_sided_bootstrap"] - jt["p_two_sided_bootstrap"]))}

    att = attribution(S, P)
    ret = return_attribution(S, mx, ar)
    monthly_attr = ret.pop("_monthly")
    reg, lab = regimes(built, mk, dev, ar)
    res = {
        "title": ("Signal value-added and portfolio attribution: each approach against its own signal-disabled portfolio"
                  if "AP3" in systems else
                  "Signal value-added and portfolio attribution: Deterministic and JEV vs their own signal-disabled portfolios"),
        "status": "DEVELOPMENT DIAGNOSTIC (2019-03..2022-12); not a protected historical result; the protected window stays sealed",
        "months": [str(dev[0]), str(dev[-1]), len(dev)],
        "research_design": "Three primary approaches unchanged (Deterministic research baseline, Agentic Workflow - JEV, Agentic Causal RAG). "
                           "The no-signal portfolios are within-approach counterfactuals, not approaches. The passive 60/40 SPY/IEF reference is separate.",
        "conventions": {
            "no_signal_definition": "each system's frozen native neutral weights (framework_config systems.<id>.native_neutral_weights)",
            "rebalancing": "monthly rebalancing back to the fixed weights at each entry close, like the strategies: the frozen convention of the shared "
                           "evaluator's own-benchmark contrast, Stage 2 BENCH_STATIC_45_35_20 and the native JEV engine's fixed/prior benchmarks. "
                           "Buy-and-hold drift is reported only as a labelled sensitivity.",
            "execution": "decision at the last common trading day of the month (20:00 ET); trade at the next common close; hold to the first common close after the next month-end",
            "prices": "adjusted closes (distributions included), pinned and hash-checked", "cash": "DTB4WK quote as of entry",
            "costs": f"{cfg['costs']['cost_per_dollar_traded']*1e4:.0f} bp per dollar traded against drifted weights; first month from cash",
            "metric": f"net CER = 12 x (mean monthly net excess return - {P['delta']}/2 x its variance); differences are in percentage points",
            "bootstrap": f"paired circular block bootstrap, {P['block']}-month blocks, {P['reps']} draws, seed {P['seed']} (frozen); joint draws for multi-series statistics",
            "information": "signals come from the frozen decision records (information cutoff at or before each decision time); the no-signal portfolios use no information",
            "multiplicity": "these within-approach contrasts are diagnostics outside the pre-registered primary family; unadjusted p-values are reported"},
        "systems": systems,
        "questions": {
            "q1_deterministic_signals_vs_own_no_signal": jb["deterministic_signal_value"],
            "q2_jev_signals_vs_own_no_signal": jb["jev_signal_value"],
            "q3_jev_vs_deterministic_after_allocation": {**jb["jev_minus_deterministic_signal_value"],
                                                          "meaning": "JEV's signal value-added minus Deterministic's: the part of the JEV-Deterministic gap not due to their different no-signal mixes"},
            "jev_minus_deterministic_total": jb["jev_minus_deterministic_total"],
            "no_signal_mix_difference": jb["no_signal_mix_difference"],
            "mix_stock_weight_net": jb["mix_stock_weight_net"], "mix_bond_sleeve_net": jb["mix_bond_sleeve_net"],
            **({"q4_causal_rag_signals_vs_own_no_signal": {
                    **jb["causal_rag_signal_value"],
                    "designation": AP3_META["designation"],
                    "meaning": "Causal RAG's signal value-added against its own frozen 45/35/20 no-signal portfolio, "
                               "same accounting as the other two. EXPLORATORY: its reliability gates failed."},
                "q5_causal_rag_vs_deterministic_after_allocation": {
                    **jb["causal_rag_minus_deterministic_signal_value"],
                    "designation": AP3_META["designation"],
                    "meaning": "Causal RAG's signal value-added minus Deterministic's. They share an identical "
                               "no-signal control, so this is the whole of their gap that is not the market."},
                "q6_causal_rag_vs_jev_signal_value": {
                    **jb["causal_rag_minus_jev_signal_value"],
                    "designation": AP3_META["designation"],
                    "meaning": "Causal RAG's signal value-added minus JEV's. Their no-signal controls differ, so "
                               "this compares signal contributions, not portfolios."},
                "causal_rag_minus_deterministic_total": {
                    **jb["causal_rag_minus_deterministic_total"], "designation": AP3_META["designation"]},
                } if "AP3" in systems else {})},
        "reproduces_previous_results": checks,
        "attribution_net_cer": att, "attribution_mean_return": ret,
        "information_checks": information_checks(built["records"], mk, dev),
        "decisions": decisions(built, ar), "regimes": reg, "influence_leave_one_month_out": influence(S, P),
        "sensitivities": {"jev_native_engine": jev_native(dev, P), "buy_and_hold_no_signal": buy_and_hold(S, P), "stage2_native_deterministic": stage2_native(S, P)},
        "safeguards": {"protected_window_scored": False, "framework_lock_applied": True, "native_engine_last_as_of": LAST_DEV_AS_OF,
                       "frozen_configuration_changed": False, "model_calls": 0},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "signal_value_v1.json").write_text(json.dumps(res, indent=1, default=float) + "\n")
    cols = ["decision_month", "entry_date", "exit_date", "rf_return"]
    mon = S[D1][cols].copy()
    for k, v in S.items():
        for c in ("net_total_return", "gross_total_return", "cost", "traded_notional"):
            mon[f"{k}__{c}"] = v[c].to_numpy()
        for c in [c for c in v.columns if c.startswith("w_")]:
            mon[f"{k}__{c}"] = v[c].to_numpy()
    for a in ASSETS:
        mon[f"asset_return_{a}"] = ar[a].to_numpy()
    for s in present_systems():
        mon[f"{s}_active_net"] = S[ON[s]]["net_excess_return"].to_numpy() - S[OFF[s]]["net_excess_return"].to_numpy()
    mon = mon.merge(monthly_attr, on="decision_month").merge(lab, on="decision_month")
    mon.to_csv(OUT / "monthly_v1.csv", index=False, float_format="%.12g")
    q = res["questions"]
    print(json.dumps({k: {kk: q[k][kk] for kk in ("point", "ci95", "p_two_sided_bootstrap")} for k in q}, indent=1))
    bad = [s for s, c in checks.items() if c.get("max_abs_difference", 0) > 1e-12 or c.get("no_signal_net_cer_abs_difference", 0) > 1e-12]
    bad += ["information"] if res["information_checks"]["problems"] else []
    bad += [k for k, v in (("four_parts", att["four_parts_residual"]), ("two_by_two", att["two_by_two_residual"]), ("returns", ret["max_abs_monthly_residual"])) if abs(v) > 1e-12]
    if bad:
        print("RECONCILIATION FAILED:", bad)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
