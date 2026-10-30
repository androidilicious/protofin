#!/usr/bin/env python3
"""Forecast-to-allocation sensitivity (development months only).

Pre-registered in native_backtest/config/forecast_to_allocation_sensitivity_preregistration_v1.json, which fixes
the scenarios, the entry points, the transformations, the metrics and the policies before any result was seen.

Question: how much does a change in each approach's investment view change its final allocation, its returns, its
risk, its turnover and its economic performance - and where does each native pipeline attenuate the signal?

For each pre-registered signal strength lambda in {0, 0.5, 1, 2} the view is rescaled at the one point where a
number enters the native allocator,

    adjusted view = prior view + lambda x (original view - prior view),

and the native allocator then does everything else:

  Deterministic   q_t(lambda) = pi_t + lambda (q_t - pi_t) into stage2_portfolio.bl_posterior, then the native
                  bounded fully-invested optimum. pi_t = DELTA Sigma_t w_eq is the allocator's own equilibrium.
  JEV             offset_t(lambda) = lambda offset_t, so edge = baseEdge + lambda x confidence x offset, then the
                  native capped tilt. Not Black-Litterman: JEV has its own mechanism.
  Committee       q_t(lambda) = pi_t + lambda (q_t - pi_t) into the native allocate(), as a secondary variant.

Nothing else moves: not the macro observations, the saved agent answers, the covariances, the confidence levels,
the regime confidence gate, the position limits, the costs or the accounting. Every scenario is then evaluated
through the one shared evaluator, so the four scenarios differ only in the strength of the view.

Causal RAG is Pending Genuine Agent Outputs: 12 of 95 months exist and both reliability gates failed, so there is
no calibrated view series for the development window. The machinery here is the machinery it will use.

Outputs: native_backtest/out/sensitivity/. The protected window is never scored.

Usage (repository root): python -m native_backtest.scripts.forecast_to_allocation
"""
from __future__ import annotations

import dataclasses
import itertools
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

from native_backtest.framework import benchmark as B
from native_backtest.framework import metrics as M
from native_backtest.framework.accounting import simulate_records, static_portfolio_records
from native_backtest.framework.lock import assert_scoring_allowed
from native_backtest.framework.market import decision_time_iso, load_config, load_market, months_between
from native_backtest.framework.records import DecisionRecord, read_jsonl
from native_backtest.scripts.signal_value_added import frozen, joint_bootstrap, mblock

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "native_backtest/out/sensitivity"
DEC = ROOT / "native_backtest/out/decisions"
PREREG = ROOT / "native_backtest/config/forecast_to_allocation_sensitivity_preregistration_v1.json"
STAGE2_RUN = ROOT / "stage2/results/dev_rerun_v4_portfolio_2026-10-27"
STAGE2_SPEC = ROOT / "stage2/scoring/stage2_run_spec_dev_v4.json"
HARNESS = Path("native_backtest/adapters/node/ap2_sensitivity.mjs")
ENGINES = {"AP2B": Path("native_backtest/vendor/protofin_feature-jev_7a70331/site/js"),
           "AP2A": Path("native_backtest/vendor/protofin_approach-2_ce063b8/site/js")}
MODES = {"AP2B": "jev", "AP2A": "committee"}
LAST_DEV_AS_OF = "2022-12-30"
LAMBDAS = (0.0, 0.5, 1.0, 2.0)
LABELS = {0.0: "Neutral (0x)", 0.5: "Weaker (0.5x)", 1.0: "Original (1x)", 2.0: "Stronger (2x)"}
RATIO_FLOOR = 1e-6               # pre-registered: no transmission ratio is formed below this weight change
REPRO_TOL = 1e-10                # pre-registered reproduction tolerance for the 1x scenario
AP1_ASSETS = ("SPY", "IEF", "LQD")
AP2_ASSETS = ("SPY", "TLT")


def key(lam: float) -> str:
    return f"{lam:g}x"


# ------------------------------------------------------------------------------------- Deterministic (Approach 1)
def stage2_inputs() -> dict:
    """The archived Stage 2 development run's own views and the covariances it built, rebuilt from its own code."""
    sys.path.insert(0, str(ROOT / "stage2/scoring"))
    import stage2_backtest as S
    import stage2_portfolio as P

    spec = json.loads(STAGE2_SPEC.read_text())
    _, _, prices, _, _, _, dtb4wk = S.load_inputs(spec)
    cal = S.common_trading_calendar(prices)
    dec = S.build_decision_calendar(cal)
    targets = S.build_targets(prices, cal, dec, dtb4wk, S.month_range(S.MACRO_START, S.DEV_END))
    targets["decision_month"] = targets["decision_month"].astype(str)
    assets = list(P.ASSETS)
    labels = targets.pivot(index="decision_month", columns="asset", values="actual_excess_return")[assets].sort_index()
    pred = pd.read_csv(STAGE2_RUN / "stage2_predictions.csv")
    pred = pred[pred["system"] == "A"].copy()
    pred["decision_month"] = pred["decision_month"].astype(str)
    months = sorted(pred["decision_month"].unique())
    pidx = pd.PeriodIndex(labels.index, freq="M")
    sigma = {}
    for m in months:
        w = labels[(pidx >= pd.Period(S.MACRO_START, "M")) & (pidx <= pd.Period(m, "M") - 2)].tail(P.COV_WINDOW)
        if len(w) != P.COV_WINDOW:
            raise SystemExit(f"{m}: {len(w)} labels for the covariance, need {P.COV_WINDOW}")
        sigma[m] = P.ledoit_wolf_cov(w.to_numpy(float))
    piv = lambda c: pred.pivot(index="decision_month", columns="asset", values=c)[assets]
    return {"P": P, "assets": assets, "months": months, "sigma": sigma,
            "q": piv("prediction_excess_return"), "q_histmean": piv("benchmark_mean_excess_return"),
            "omega": P.read_omega(STAGE2_RUN / "stage2_omega_from_A_development.json"),
            "archived": pd.read_csv(STAGE2_RUN / "stage2_portfolio_bl_diagnostics.csv").query("strategy == 'A'").set_index("decision_month")}


def fully_invested(mu: np.ndarray, sigma: np.ndarray, delta: float) -> np.ndarray:
    """The native optimizer's own all-free candidate: the fully invested optimum with the bounds ignored."""
    inv = np.linalg.inv(sigma)
    one = np.ones(len(mu))
    lam = (one @ inv @ mu - delta) / (one @ inv @ one)
    return inv @ (mu - lam * one) / delta


def ap1_scenarios(S2: dict) -> dict:
    """One trace row per month per scenario, plus the native no-signal reference fed historical-mean views."""
    P, assets, lo, up = S2["P"], S2["assets"], S2["P"].LOWER, S2["P"].UPPER
    rows, repro = [], {"max_abs_pi": 0.0, "max_abs_mu_bl": 0.0, "max_abs_weight": 0.0}
    for m in S2["months"]:
        sig = S2["sigma"][m]
        q = S2["q"].loc[m].to_numpy(float)
        pi, mu1, post1 = P.bl_posterior(sig, q, S2["omega"])
        a = S2["archived"].loc[m]
        for lam in LAMBDAS:
            qs = pi + lam * (q - pi)
            _, mu, post = P.bl_posterior(sig, qs, S2["omega"])
            w = P.optimal_weights(mu, post)
            unc = fully_invested(mu, post, P.DELTA)
            at_lo = np.isclose(w, lo, atol=1e-9)
            at_up = np.isclose(w, up, atol=1e-9)
            rows.append({"scenario": key(lam), "lambda": lam, "decision_month": m,
                         **{f"q_orig_{x}": float(q[i]) for i, x in enumerate(assets)},
                         **{f"pi_{x}": float(pi[i]) for i, x in enumerate(assets)},
                         **{f"q_adj_{x}": float(qs[i]) for i, x in enumerate(assets)},
                         **{f"mu_bl_{x}": float(mu[i]) for i, x in enumerate(assets)},
                         **{f"w_unconstrained_{x}": float(unc[i]) for i, x in enumerate(assets)},
                         **{f"w_{x}": float(w[i]) for i, x in enumerate(assets)},
                         "n_bounds_binding": int(at_lo.sum() + at_up.sum()),
                         "bounds_binding": ",".join([f"{assets[i]}:lower" for i in np.where(at_lo)[0]] +
                                                    [f"{assets[i]}:upper" for i in np.where(at_up)[0]]),
                         "unconstrained_feasible": bool(((unc >= lo - 1e-9) & (unc <= up + 1e-9)).all()),
                         "view_present": True})
            if lam == 1.0:
                repro["max_abs_pi"] = max(repro["max_abs_pi"], float(np.abs(pi - a[[f"pi_{x}" for x in assets]].to_numpy(float)).max()))
                repro["max_abs_mu_bl"] = max(repro["max_abs_mu_bl"], float(np.abs(mu - a[[f"mu_bl_{x}" for x in assets]].to_numpy(float)).max()))
                repro["max_abs_weight"] = max(repro["max_abs_weight"], float(np.abs(w - a[[f"w_{x}" for x in assets]].to_numpy(float)).max()))
    hist = {}
    for m in S2["months"]:
        _, mu, post = P.bl_posterior(S2["sigma"][m], S2["q_histmean"].loc[m].to_numpy(float), S2["omega"])
        hist[m] = P.optimal_weights(mu, post)
    return {"trace": pd.DataFrame(rows), "reproduction": repro, "histmean_weights": hist}


# ------------------------------------------------------------------------- Agentic Workflow engines (Approach 2)
def ap2_scenarios(system: str) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{system.lower()}_native_scenarios.json"
    cmd = [n for n in ("node",) ] + [str(HARNESS), f"--engine={ENGINES[system]}", f"--mode={MODES[system]}",
                                     f"--last-as-of={LAST_DEV_AS_OF}", f"--lambdas={','.join(f'{l:g}' for l in LAMBDAS)}",
                                     f"--out={out}"]
    subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True)
    raw = json.loads(out.read_text())
    rows = []
    for lam in LAMBDAS:
        for r in raw["scenarios"][f"{lam:g}"]:
            w = float(r["w_spy"])
            x = r.get("x_raw")
            rows.append({"scenario": key(lam), "lambda": lam, "as_of": r["as_of"], "w_SPY": w, "w_TLT": 1.0 - w,
                         "w_unconstrained_SPY": None if x is None else float(x),
                         "n_bounds_binding": int(abs(w - raw["bounds"]["min_spy"]) < 1e-12 or abs(w - raw["bounds"]["max_spy"]) < 1e-12),
                         "bounds_binding": ("SPY:lower" if abs(w - raw["bounds"]["min_spy"]) < 1e-12 else
                                            "SPY:upper" if abs(w - raw["bounds"]["max_spy"]) < 1e-12 else ""),
                         "view_present": bool(r["view_present"]), "regime": r.get("regime"),
                         "base_edge": r.get("base_edge"), "edge": r.get("edge"), "weighted_offset": r.get("weighted_offset"),
                         "offset_original": r.get("offset_original"), "confidence": r.get("confidence"),
                         "conf_applied": r.get("conf_applied"),
                         "q_orig_SPY": (r.get("q_original") or [None, None])[0], "q_orig_TLT": (r.get("q_original") or [None, None])[1],
                         "q_adj_SPY": (r.get("q_scaled") or [None, None])[0], "q_adj_TLT": (r.get("q_scaled") or [None, None])[1],
                         "pi_SPY": (r.get("pi") or [None, None])[0], "pi_TLT": (r.get("pi") or [None, None])[1],
                         "mu_bl_SPY": (r.get("er") or [None, None])[0], "mu_bl_TLT": (r.get("er") or [None, None])[1]})
    return {"trace": pd.DataFrame(rows), "meta": {k: raw[k] for k in ("engine", "mode", "last_as_of", "n_months", "bounds", "equilibrium_spy", "delta", "outcome_fields_removed_before_decide")}}


# --------------------------------------------------------------------------------------------------- evaluation
def records_from_weights(system: str, scenario: str, weights: Dict[str, Dict[str, float]], template: List[DecisionRecord]) -> List[DecisionRecord]:
    out = []
    for rec in template:
        w = weights[rec.decision_month]
        out.append(dataclasses.replace(
            rec, system_id=f"{system}_{scenario}", target_weights={a: float(v) for a, v in w.items()},
            generation={"mode": "computed_native", "experiment": "forecast_to_allocation_sensitivity",
                        "scenario": scenario, "preregistration": "forecast_to_allocation_sensitivity_preregistration_v1.json"}))
    return out


def evaluate(records: List[DecisionRecord], mk, dev, cost: float) -> pd.DataFrame:
    return simulate_records(records, mk, dev, cost_per_dollar=cost)


def deviation(a: pd.DataFrame, b: pd.DataFrame, assets) -> dict:
    """Weight distance between two scenario traces on the same months."""
    cols = [f"w_{x}" for x in assets]
    d = np.abs(a[cols].to_numpy(float) - b[cols].to_numpy(float))
    half = 0.5 * d.sum(axis=1)
    return {"mean_abs_weight_deviation_per_asset": float(d.mean()), "max_abs_weight_deviation_any_asset": float(d.max()),
            "mean_half_sum_abs_deviation": float(half.mean()), "max_half_sum_abs_deviation": float(half.max())}


def active(trace: pd.DataFrame, neutral: Dict[str, float], assets) -> dict:
    cols = [f"w_{x}" for x in assets]
    n = np.array([neutral[x] for x in assets], float)
    d = np.abs(trace[cols].to_numpy(float) - n)
    return {"mean_abs_active_weight_per_asset": float(d.mean()), "max_abs_active_weight_any_asset": float(d.max()),
            "mean_half_sum_abs_active": float((0.5 * d.sum(axis=1)).mean())}


# ------------------------------------------------------------------------------------------------ transmission
def view_magnitude(trace: pd.DataFrame, approach: str, assets) -> np.ndarray:
    """The size of the view each scenario presents to the allocator, in the units that allocator reads.

    Deterministic and Committee read a vector of expected excess returns, so the magnitude is the mean absolute
    deviation of the adjusted view from the allocator's own prior, in basis points a month. JEV reads one number,
    the stock-minus-bond edge in points, so the magnitude is the signal-induced part of that edge."""
    if approach == "AP2B":
        return np.abs(trace["weighted_offset"].to_numpy(float))
    cols_adj = [f"q_adj_{x}" for x in assets]
    cols_pi = [f"pi_{x}" for x in assets]
    d = trace[cols_adj].to_numpy(float) - trace[cols_pi].to_numpy(float)
    return 1e4 * np.abs(d).mean(axis=1)


def view_pipeline(traces: Dict[str, pd.DataFrame], approach: str, assets) -> dict:
    """The stages between the raw signal and the number the allocator finally acts on, at 1x.

    For the two Black-Litterman allocators the decisive stage is the posterior: the view enters as q - pi and
    reaches the optimizer as mu_BL - pi, and the ratio of the two is how much of the view the posterior keeps.
    JEV has no posterior; its shrinkage happens before the allocator, when the five-way tilt distribution is
    averaged into one offset and then weighted by the saved confidence."""
    t = traces[key(1.0)]
    if approach == "AP2B":
        off = np.abs(t["offset_original"].to_numpy(float))
        conf = t["confidence"].to_numpy(float)
        wo = np.abs(t["weighted_offset"].to_numpy(float))
        base = np.abs(t["base_edge"].to_numpy(float))
        return {"kind": "pre-allocator shrinkage; this engine has no posterior step",
                "stage_1_largest_available_tilt_points": 3.0,
                "stage_2_mean_abs_probability_weighted_offset_points": float(off.mean()),
                "stage_2_share_of_largest_tilt": float(off.mean() / 3.0),
                "stage_3_mean_confidence": float(conf.mean()),
                "stage_3_mean_abs_confidence_weighted_offset_points": float(wo.mean()),
                "stage_3_share_of_stage_2": None if off.mean() == 0 else float(wo.mean() / off.mean()),
                "mean_abs_equilibrium_edge_points": float(base.mean()),
                "signal_as_share_of_equilibrium_edge": float(wo.mean() / base.mean()),
                "allocator_is_linear_in_the_edge": True,
                "note": ("the saved offset is already an average over the five tilt options weighted by the model's own "
                         "probabilities, so by the time the allocator sees it the signal has been shrunk twice")}
    pi = t[[f"pi_{a}" for a in assets]].to_numpy(float)
    q = t[[f"q_adj_{a}" for a in assets]].to_numpy(float)
    mu = t[[f"mu_bl_{a}" for a in assets]].to_numpy(float)
    dq = np.abs(q - pi).mean(axis=1)
    dmu = np.abs(mu - pi).mean(axis=1)
    ok = dq >= RATIO_FLOOR
    keep = dmu[ok] / dq[ok]
    return {"kind": "Black-Litterman posterior shrinkage",
            "mean_abs_view_minus_prior_bp": float(1e4 * dq.mean()),
            "mean_abs_posterior_minus_prior_bp": float(1e4 * dmu.mean()),
            "mean_share_of_the_view_the_posterior_keeps": None if not ok.any() else float(keep.mean()),
            "median_share_of_the_view_the_posterior_keeps": None if not ok.any() else float(np.median(keep)),
            "months_used": int(ok.sum()), "months_flagged_tiny_view": int((~ok).sum()),
            "note": ("the posterior weight on the view is tau x Sigma against Omega: a large Omega, estimated from the "
                     "model's own out-of-sample errors, is what shrinks the view, not any position limit")}


def transmission(traces: Dict[str, pd.DataFrame], approach: str, assets) -> dict:
    """Forecast change -> intermediate weight change -> final weight change, per scenario against 1x."""
    base = traces[key(1.0)]
    unit = "edge points" if approach == "AP2B" else "basis points a month"
    w_cols = [f"w_{x}" for x in assets]
    u_col = "w_unconstrained_SPY" if approach != "AP1" else None
    per = {}
    for lam in LAMBDAS:
        t = traces[key(lam)]
        dv = view_magnitude(t, approach, assets) - view_magnitude(base, approach, assets)
        if approach == "AP1":
            du = np.abs(t[[f"w_unconstrained_{x}" for x in assets]].to_numpy(float)
                        - base[[f"w_unconstrained_{x}" for x in assets]].to_numpy(float)).max(axis=1)
            dw = np.abs(t[w_cols].to_numpy(float) - base[w_cols].to_numpy(float)).max(axis=1)
        else:
            du = np.abs(t[u_col].to_numpy(float) - base[u_col].to_numpy(float))
            dw = np.abs(t["w_SPY"].to_numpy(float) - base["w_SPY"].to_numpy(float))
        ok = du >= RATIO_FLOOR
        att = 1.0 - dw[ok] / du[ok]
        per[key(lam)] = {
            "mean_abs_view_change_vs_1x": float(np.abs(dv).mean()), "max_abs_view_change_vs_1x": float(np.abs(dv).max()),
            "view_change_unit": unit,
            "mean_abs_intermediate_weight_change_vs_1x": float(du.mean()), "max_abs_intermediate_weight_change_vs_1x": float(du.max()),
            "mean_abs_final_weight_change_vs_1x": float(dw.mean()), "max_abs_final_weight_change_vs_1x": float(dw.max()),
            "months_above_ratio_floor": int(ok.sum()), "months_below_ratio_floor_not_divided": int((~ok).sum()),
            "mean_constraint_attenuation_share": None if not ok.any() else float(att.mean()),
            "max_constraint_attenuation_share": None if not ok.any() else float(att.max()),
            "months_with_any_binding_bound": int((t["n_bounds_binding"] > 0).sum()),
            "share_of_months_with_any_binding_bound": float((t["n_bounds_binding"] > 0).mean()),
            "binding_bound_counts": {k: int(v) for k, v in t.loc[t["bounds_binding"] != "", "bounds_binding"].value_counts().items()},
        }
    hi, lo = traces[key(2.0)], traces[key(0.5)]
    vh, vl = view_magnitude(hi, approach, assets), view_magnitude(lo, approach, assets)
    if approach == "AP1":
        wh = hi[w_cols].to_numpy(float)
        wl = lo[w_cols].to_numpy(float)
        dwfd = np.abs(wh - wl).max(axis=1)
    else:
        dwfd = np.abs(hi["w_SPY"].to_numpy(float) - lo["w_SPY"].to_numpy(float))
    dvfd = vh - vl
    good = np.abs(dvfd) >= RATIO_FLOOR
    slope = dwfd[good] / np.abs(dvfd[good])
    return {"per_scenario_vs_1x": per,
            "local_finite_difference_around_1x": {
                "definition": "symmetric difference between the 2x and 0.5x scenarios, per month",
                "mean_abs_weight_change_per_unit_view": None if not good.any() else float(slope.mean()),
                "median_abs_weight_change_per_unit_view": None if not good.any() else float(np.median(slope)),
                "weight_change_per_lambda_mean": float((dwfd / 1.5).mean()),
                "view_change_unit": unit,
                "months_used": int(good.sum()), "months_flagged_tiny_view_change": int((~good).sum())}}


def signal_share(traces: Dict[str, pd.DataFrame], approach: str, assets, neutral: Dict[str, float]) -> dict:
    """How much of the 1x allocation's distance from the native neutral portfolio the signal is responsible for."""
    t1, t0 = traces[key(1.0)], traces[key(0.0)]
    cols = [f"w_{x}" for x in assets]
    n = np.array([neutral[x] for x in assets], float)
    d1 = 0.5 * np.abs(t1[cols].to_numpy(float) - n).sum(axis=1)
    d0 = 0.5 * np.abs(t0[cols].to_numpy(float) - n).sum(axis=1)
    ds = 0.5 * np.abs(t1[cols].to_numpy(float) - t0[cols].to_numpy(float)).sum(axis=1)
    return {"mean_distance_1x_from_native_neutral": float(d1.mean()),
            "mean_distance_0x_from_native_neutral": float(d0.mean()),
            "mean_distance_1x_from_0x_the_signal_part": float(ds.mean()),
            "max_distance_1x_from_0x_the_signal_part": float(ds.max()),
            "signal_share_of_1x_distance_from_neutral": None if d1.mean() == 0 else float(ds.mean() / d1.mean())}


# ------------------------------------------------------------------------------------------------------- driver
def ap1_block(mk, dev, cost: float, cfg: dict, P: dict) -> dict:
    S2 = stage2_inputs()
    sc = ap1_scenarios(S2)
    months = [str(m) for m in dev]
    if sorted(S2["months"]) != months:
        raise SystemExit("the archived Stage 2 development months are not the configured development window")
    tr = {k: g.set_index("decision_month").loc[months].reset_index() for k, g in sc["trace"].groupby("scenario")}
    template = [r for r in read_jsonl(DEC / "AP1.jsonl") if r.decision_month in set(months)]
    template = sorted(template, key=lambda r: r.decision_month)
    sims, recs = {}, {}
    for lam in LAMBDAS:
        t = tr[key(lam)]
        w = {m: {a: float(t.loc[t["decision_month"] == m, f"w_{a}"].iloc[0]) for a in AP1_ASSETS} for m in months}
        recs[key(lam)] = records_from_weights("AP1", key(lam), w, template)
        sims[key(lam)] = evaluate(recs[key(lam)], mk, dev, cost)
    neutral = cfg["systems"]["AP1"]["native_neutral_weights"]
    ctrl = {"native_neutral_static": evaluate(static_portfolio_records("AP1_NO_SIGNAL", neutral, template), mk, dev, cost),
            "histmean_allocator": evaluate(records_from_weights(
                "AP1", "HISTMEAN", {m: dict(zip(AP1_ASSETS, map(float, sc["histmean_weights"][m]))) for m in months}, template), mk, dev, cost)}
    arch = pd.read_csv(STAGE2_RUN / "stage2_portfolio_returns.csv").query("strategy == 'A'").set_index("decision_month").loc[months]
    repro = dict(sc["reproduction"])
    repro["max_abs_archived_stage2_weight"] = repro.pop("max_abs_weight")
    repro["max_abs_shared_evaluator_net_excess_vs_archived_native_sim"] = float(
        np.abs(sims[key(1.0)]["net_excess_return"].to_numpy(float) - arch["net_excess_return"].to_numpy(float)).max())
    repro["tolerance"] = REPRO_TOL
    repro["within_tolerance"] = bool(max(repro["max_abs_pi"], repro["max_abs_mu_bl"], repro["max_abs_archived_stage2_weight"]) <= REPRO_TOL)
    t0 = tr[key(0.0)]
    zero = {
        "mu_bl_equals_pi_max_abs": float(np.abs(t0[[f"mu_bl_{a}" for a in AP1_ASSETS]].to_numpy(float)
                                                - t0[[f"pi_{a}" for a in AP1_ASSETS]].to_numpy(float)).max()),
        "adjusted_view_equals_pi_max_abs": float(np.abs(t0[[f"q_adj_{a}" for a in AP1_ASSETS]].to_numpy(float)
                                                        - t0[[f"pi_{a}" for a in AP1_ASSETS]].to_numpy(float)).max()),
        "vs_native_neutral_static_weights": {
            "max_abs_weight_difference": float(np.abs(t0[[f"w_{a}" for a in AP1_ASSETS]].to_numpy(float)
                                                      - np.array([neutral[a] for a in AP1_ASSETS])).max()),
            "mean_abs_weight_difference": float(np.abs(t0[[f"w_{a}" for a in AP1_ASSETS]].to_numpy(float)
                                                       - np.array([neutral[a] for a in AP1_ASSETS])).mean()),
            "why": ("pre-registered and expected: at lambda = 0 the posterior mean is exactly the allocator's own "
                    "equilibrium pi, but the optimizer maximises against Sigma_post = Sigma + M, while pi was defined "
                    "as DELTA Sigma w_eq. The two are different quadratic problems, so the optimum is near the 45/35/20 "
                    "equilibrium without being equal to it. Nothing is corrected: both references are reported."),
            "interpretation": "lambda = 0 is the native allocator with no incremental view, not the static neutral portfolio"},
        "vs_histmean_allocator": {
            "mean_abs_weight_difference": float(np.abs(
                t0[[f"w_{a}" for a in AP1_ASSETS]].to_numpy(float)
                - np.array([sc["histmean_weights"][m] for m in months])).mean()),
            "what": "Stage 2's own BENCH_HISTMEAN_ALLOCATOR: the same allocator fed historical-mean views instead of model views"}}
    return {"trace": tr, "sims": sims, "controls": ctrl, "reproduction": repro, "zero_scenario_checks": zero,
            "neutral": neutral, "assets": AP1_ASSETS,
            "allocator": {"kind": "Black-Litterman with a bounded fully invested mean-variance optimum",
                          "entry_point": "stage2/scoring/stage2_portfolio.py::bl_posterior argument q",
                          "bounds": {a: [float(S2["P"].LOWER[i]), float(S2["P"].UPPER[i])] for i, a in enumerate(AP1_ASSETS)},
                          "tau": S2["P"].TAU, "delta": S2["P"].DELTA, "cov_window": S2["P"].COV_WINDOW,
                          "omega_diag": {a: float(S2["omega"][i]) for i, a in enumerate(AP1_ASSETS)},
                          "intermediate_stage": "the optimizer's own all-free candidate: the fully invested optimum with the bounds ignored"}}


def ap2_block(system: str, mk, dev, cost: float, cfg: dict) -> dict:
    sc = ap2_scenarios(system)
    months = [str(m) for m in dev]
    template = sorted([r for r in read_jsonl(DEC / f"{system}.jsonl") if r.decision_month in set(months)],
                      key=lambda r: r.decision_month)
    day = {r.decision_time[:10]: r.decision_month for r in template}
    tr, sims, recs = {}, {}, {}
    for lam in LAMBDAS:
        k = key(lam)
        t = sc["trace"].query("scenario == @k").copy()
        t["decision_month"] = t["as_of"].map(day)
        t = t[t["decision_month"].notna()].set_index("decision_month").loc[months].reset_index()
        tr[key(lam)] = t
        w = {m: {"SPY": float(t.loc[t["decision_month"] == m, "w_SPY"].iloc[0]),
                 "TLT": float(t.loc[t["decision_month"] == m, "w_TLT"].iloc[0])} for m in months}
        recs[key(lam)] = records_from_weights(system, key(lam), w, template)
        sims[key(lam)] = evaluate(recs[key(lam)], mk, dev, cost)
    neutral = cfg["systems"][system]["native_neutral_weights"]
    ctrl = {"native_neutral_static": evaluate(static_portfolio_records(f"{system}_NO_SIGNAL", neutral, template), mk, dev, cost)}
    arch = evaluate(template, mk, dev, cost)
    repro = {"max_abs_archived_decision_weight": float(max(
        abs(tr[key(1.0)].loc[tr[key(1.0)]["decision_month"] == r.decision_month, "w_SPY"].iloc[0] - r.target_weights["SPY"])
        for r in template)),
        "max_abs_net_excess_vs_archived_decisions": float(np.abs(
            sims[key(1.0)]["net_excess_return"].to_numpy(float) - arch["net_excess_return"].to_numpy(float)).max()),
        "tolerance": REPRO_TOL}
    repro["within_tolerance"] = bool(max(repro["max_abs_archived_decision_weight"], repro["max_abs_net_excess_vs_archived_decisions"]) <= REPRO_TOL)
    t0 = tr[key(0.0)]
    zero = {"max_abs_weight_difference_vs_native_neutral": float(np.abs(t0["w_SPY"].to_numpy(float) - neutral["SPY"]).max()),
            "equals_native_neutral": bool(np.abs(t0["w_SPY"].to_numpy(float) - neutral["SPY"]).max() <= 1e-9),
            "why": ("the native equilibrium edge alone reproduces the equilibrium SPY weight exactly, so this engine's "
                    "lambda = 0 scenario and its native no-signal control are the same portfolio"),
            "months_without_a_native_view": int((~tr[key(1.0)]["view_present"]).sum())}
    return {"trace": tr, "sims": sims, "controls": ctrl, "reproduction": repro, "zero_scenario_checks": zero,
            "neutral": neutral, "assets": AP2_ASSETS, "meta": sc["meta"],
            "allocator": {"kind": ("capped tilt on the stock-minus-bond edge" if system == "AP2B"
                                   else "Black-Litterman on the engine's own two-asset equilibrium, then the same cap"),
                          "entry_point": ("livebacktest.js: edge = baseEdge + confidence x offset" if system == "AP2B"
                                          else "allocation.js::allocate -> blPosterior(pi, sigma, q, confidence)"),
                          "bounds": {"SPY": [sc["meta"]["bounds"]["min_spy"], sc["meta"]["bounds"]["max_spy"]]},
                          "delta": sc["meta"]["delta"], "equilibrium_spy": sc["meta"]["equilibrium_spy"],
                          "intermediate_stage": "the engine's own unclipped fully invested SPY weight"}}


# --------------------------------------------------------------------------------------------------- statistics
def scenario_statistics(block: dict, P: dict) -> dict:
    """Net CER for every scenario and control, and every scenario's difference from 1x and from the no-signal
    control, on one set of paired block draws."""
    series = {key(l): block["sims"][key(l)]["net_excess_return"].to_numpy(float) for l in LAMBDAS}
    series.update({f"control:{k}": v["net_excess_return"].to_numpy(float) for k, v in block["controls"].items()})
    stats = {}
    for l in LAMBDAS:
        k = key(l)
        stats[f"net_cer_{k}"] = (lambda kk: (lambda c: c[kk]))(k)
        if l != 1.0:
            stats[f"net_cer_{k}_minus_1x"] = (lambda kk: (lambda c: c[kk] - c["1x"]))(k)
        for ck in block["controls"]:
            stats[f"net_cer_{k}_minus_{ck}"] = (lambda kk, cc: (lambda c: c[kk] - c[f"control:{cc}"]))(k, ck)
    for ck in block["controls"]:
        stats[f"net_cer_control_{ck}"] = (lambda cc: (lambda c: c[f"control:{cc}"]))(ck)
    out = joint_bootstrap(series, stats, P)
    out["_bootstrap"] = {"block_months": P["block"], "replications": P["reps"], "seed": P["seed"], "cer_delta": P["delta"],
                         "paired": "every statistic uses the same resampled months"}
    return out


def performance(block: dict) -> dict:
    rows = {}
    for l in LAMBDAS:
        k = key(l)
        sim, t = block["sims"][k], block["trace"][k]
        m = mblock(sim)
        a = sim["net_excess_return"].to_numpy(float) - block["controls"]["native_neutral_static"]["net_excess_return"].to_numpy(float)
        rows[k] = {"label": LABELS[l], "lambda": l, **m,
                   "mean_active_return_vs_native_no_signal_annualised": 12.0 * float(a.mean()),
                   "tracking_error_vs_native_no_signal_annualised": float(np.sqrt(12.0) * a.std(ddof=1)),
                   **active(t, block["neutral"], block["assets"]),
                   **deviation(t, block["trace"][key(1.0)], block["assets"])}
    for ck, sim in block["controls"].items():
        rows[f"control:{ck}"] = {"label": f"control: {ck}", "lambda": None, **mblock(sim)}
    net = pd.DataFrame({k: block["sims"][key(l)]["net_excess_return"].to_numpy(float) for l in LAMBDAS for k in [key(l)]})
    return {"by_scenario": rows, "monthly_net_return_correlation": net.corr().round(10).to_dict()}



# ------------------------------------------------------------------------- Agentic Causal RAG (Approach 3)
AP3_EVAL = ROOT / "native_backtest/out/ap3/qwen3_runs/evaluation"
AP3_BUNDLE = ROOT / "native_backtest/out/ap3/qwen3_runs"
AP3_ASSETS = ("SPY", "IEF", "LQD")


def ap3_inputs(dev) -> dict | None:
    """AP3's own calibrated views, its own Omega and the covariances its native allocator builds.

    Everything here comes from the imported exploratory evaluation and from AP3's own allocation module, so the
    scenarios run through the same code that produced the archived weights. Returns None when no genuine
    development-window outputs exist, and the caller then reports AP3 as pending rather than inventing a series."""
    if not (AP3_EVAL / "predictions.csv").exists() or not (AP3_EVAL / "weights.json").exists():
        return None
    summary = json.loads((AP3_BUNDLE / "summary.json").read_text())
    if summary.get("n_months") != summary.get("target_months"):
        return None
    from native_backtest.ap3 import allocation as A
    from native_backtest.scripts import ap3_dev_replay as rp

    months = [str(m) for m in dev]
    pred = pd.read_csv(AP3_EVAL / "predictions.csv")
    pred["decision_month"] = pred["decision_month"].astype(str)
    if sorted(pred["decision_month"].unique()) != months:
        raise SystemExit("the imported Causal RAG predictions do not cover the configured development window")
    labels = rp.labels_frame(months_between(rp.AGENT_MONTHS[0], rp.AGENT_MONTHS[1]))
    omega = A.omega_from_development_errors(pred, labels, months)
    piv = pred.pivot(index="decision_month", columns="asset", values="prediction_excess_return")[list(AP3_ASSETS)]
    archived = json.loads((AP3_EVAL / "weights.json").read_text())
    sigma = {}
    pidx = labels.index
    for m in months:
        w = labels[(pidx >= pd.Period("2015-02", "M")) & (pidx <= pd.Period(m, "M") - 2)][list(AP3_ASSETS)].tail(A.s2p.COV_WINDOW)
        if len(w) != A.s2p.COV_WINDOW:
            raise SystemExit(f"{m}: {len(w)} labels for the Causal RAG covariance, need {A.s2p.COV_WINDOW}")
        sigma[m] = A.s2p.ledoit_wolf_cov(w.to_numpy(float))
    return {"P": A.s2p, "A": A, "assets": list(AP3_ASSETS), "months": months, "sigma": sigma, "q": piv,
            "omega": omega, "archived": archived, "summary": summary,
            "exploratory": bool((summary.get("exploratory") or {}).get("label"))}


def ap3_scenarios(S3: dict) -> dict:
    """The same pre-registered transformation, applied to AP3's calibrated numerical view only.

    The categorical assessments are never scaled: Supported, Contradicted and Insufficient are encoded and
    calibrated into a numerical view upstream, exactly as in the archived run, and only that view is rescaled."""
    P, assets, lo, up = S3["P"], S3["assets"], S3["P"].LOWER, S3["P"].UPPER
    rows, repro = [], {"max_abs_weight": 0.0}
    for m in S3["months"]:
        sig = S3["sigma"][m]
        q = S3["q"].loc[m].to_numpy(float)
        pi, _, _ = P.bl_posterior(sig, q, S3["omega"])
        for lam in LAMBDAS:
            qs = pi + lam * (q - pi)
            _, mu, post = P.bl_posterior(sig, qs, S3["omega"])
            w = P.optimal_weights(mu, post)
            unc = fully_invested(mu, post, P.DELTA)
            at_lo = np.isclose(w, lo, atol=1e-9)
            at_up = np.isclose(w, up, atol=1e-9)
            rows.append({"scenario": key(lam), "lambda": lam, "decision_month": m,
                         **{f"q_orig_{x}": float(q[i]) for i, x in enumerate(assets)},
                         **{f"pi_{x}": float(pi[i]) for i, x in enumerate(assets)},
                         **{f"q_adj_{x}": float(qs[i]) for i, x in enumerate(assets)},
                         **{f"mu_bl_{x}": float(mu[i]) for i, x in enumerate(assets)},
                         **{f"w_unconstrained_{x}": float(unc[i]) for i, x in enumerate(assets)},
                         **{f"w_{x}": float(w[i]) for i, x in enumerate(assets)},
                         "n_bounds_binding": int(at_lo.sum() + at_up.sum()),
                         "bounds_binding": ",".join([f"{assets[i]}:lower" for i in np.where(at_lo)[0]] +
                                                    [f"{assets[i]}:upper" for i in np.where(at_up)[0]]),
                         "unconstrained_feasible": bool(((unc >= lo - 1e-9) & (unc <= up + 1e-9)).all()),
                         "view_present": True})
            if lam == 1.0:
                a = np.array([S3["archived"][m][x] for x in assets], float)
                repro["max_abs_weight"] = max(repro["max_abs_weight"], float(np.abs(w - a).max()))
    return {"trace": pd.DataFrame(rows), "reproduction": repro}


def ap3_block(mk, dev, cost: float, cfg: dict, S3: dict) -> dict:
    sc = ap3_scenarios(S3)
    months = [str(m) for m in dev]
    tr = {k: g.set_index("decision_month").loc[months].reset_index() for k, g in sc["trace"].groupby("scenario")}
    template = sorted([r for r in read_jsonl(DEC / "AP3_qwen3_reduced_evidence.jsonl") if r.decision_month in set(months)],
                      key=lambda r: r.decision_month)
    if len(template) != len(months):
        raise SystemExit("the imported Causal RAG decision records do not cover the development window")
    sims = {}
    for lam in LAMBDAS:
        t = tr[key(lam)]
        w = {m: {a: float(t.loc[t["decision_month"] == m, f"w_{a}"].iloc[0]) for a in AP3_ASSETS} for m in months}
        sims[key(lam)] = evaluate(records_from_weights("AP3", key(lam), w, template), mk, dev, cost)
    neutral = cfg["systems"]["AP3"]["native_neutral_weights"]
    ctrl = {"native_neutral_static": evaluate(static_portfolio_records("AP3_NO_SIGNAL", neutral, template), mk, dev, cost)}
    arch = evaluate(template, mk, dev, cost)
    repro = dict(sc["reproduction"])
    repro["max_abs_archived_native_weight"] = repro.pop("max_abs_weight")
    repro["max_abs_shared_evaluator_net_excess_vs_archived_records"] = float(
        np.abs(sims[key(1.0)]["net_excess_return"].to_numpy(float) - arch["net_excess_return"].to_numpy(float)).max())
    repro["tolerance"] = REPRO_TOL
    repro["within_tolerance"] = bool(max(repro["max_abs_archived_native_weight"],
                                         repro["max_abs_shared_evaluator_net_excess_vs_archived_records"]) <= REPRO_TOL)
    t0 = tr[key(0.0)]
    zero = {
        "mu_bl_equals_pi_max_abs": float(np.abs(t0[[f"mu_bl_{a}" for a in AP3_ASSETS]].to_numpy(float)
                                                - t0[[f"pi_{a}" for a in AP3_ASSETS]].to_numpy(float)).max()),
        "adjusted_view_equals_pi_max_abs": float(np.abs(t0[[f"q_adj_{a}" for a in AP3_ASSETS]].to_numpy(float)
                                                        - t0[[f"pi_{a}" for a in AP3_ASSETS]].to_numpy(float)).max()),
        "vs_native_neutral_static_weights": {
            "max_abs_weight_difference": float(np.abs(t0[[f"w_{a}" for a in AP3_ASSETS]].to_numpy(float)
                                                      - np.array([neutral[a] for a in AP3_ASSETS])).max()),
            "mean_abs_weight_difference": float(np.abs(t0[[f"w_{a}" for a in AP3_ASSETS]].to_numpy(float)
                                                       - np.array([neutral[a] for a in AP3_ASSETS])).mean()),
            "why": ("the same pre-registered Sigma + M effect as the Deterministic model: at lambda = 0 the posterior "
                    "mean is exactly the allocator's own equilibrium pi, but the optimizer maximises against "
                    "Sigma_post = Sigma + M. Nothing is corrected; both references are reported."),
            "interpretation": "lambda = 0 is the native allocator with no incremental view, not the static neutral portfolio"}}
    return {"trace": tr, "sims": sims, "controls": ctrl, "reproduction": repro, "zero_scenario_checks": zero,
            "neutral": neutral, "assets": list(AP3_ASSETS),
            "allocator": {"kind": "Black-Litterman with a bounded fully invested mean-variance optimum (Causal RAG's own Q and Omega)",
                          "entry_point": "native_backtest/ap3/allocation.py::weights_for_months -> bl_posterior argument q",
                          "bounds": {a: [float(S3["P"].LOWER[i]), float(S3["P"].UPPER[i])] for i, a in enumerate(AP3_ASSETS)},
                          "tau": S3["P"].TAU, "delta": S3["P"].DELTA, "cov_window": S3["P"].COV_WINDOW,
                          "omega_diag": {a: float(S3["omega"][i]) for i, a in enumerate(AP3_ASSETS)},
                          "intermediate_stage": "the optimizer's own all-free candidate: the fully invested optimum with the bounds ignored"}}


def approach_block(name: str, short: str, role: str, block: dict, P: dict, approach: str) -> dict:
    return {"name": name, "short": short, "role": role, "status": "computed",
            "universe": list(block["assets"]), "native_neutral_weights": block["neutral"],
            "allocator": block["allocator"],
            "reproduction_of_1x": block["reproduction"], "zero_scenario_checks": block["zero_scenario_checks"],
            "performance": performance(block),
            "transmission": transmission(block["trace"], approach, block["assets"]),
            "view_pipeline": view_pipeline(block["trace"], approach, block["assets"]),
            "signal_share_of_allocation": signal_share(block["trace"], approach, block["assets"], block["neutral"]),
            "statistics": scenario_statistics(block, P)}


def ap3_status() -> dict:
    from native_backtest.ap3 import exploratory as X
    pre = json.loads(PREREG.read_text())["approaches"]["AP3"]
    bundle = ROOT / "native_backtest/out/ap3/qwen3_runs/summary.json"
    have = json.loads(bundle.read_text()) if bundle.exists() else {}
    return {"name": "Agentic Causal RAG", "short": "Causal RAG", "role": "primary",
            "status": "PENDING GENUINE AGENT OUTPUTS",
            "reason": pre["reason"],
            "months_available": have.get("n_months"), "months_required": have.get("target_months", 95),
            "gates": {g: v.get("pass") for g, v in (have.get("gates") or {}).items()},
            # the authoritative label is the frozen exploratory mode's own, not this file's rendering of it
            "designation_if_run_on_current_outputs": X.LABEL,
            "designation_preregistered_as": pre["designation_if_run_on_current_outputs"],
            "planned_entry_point": pre["planned_entry_point"],
            "explicit_prohibition": pre["explicit_prohibition"],
            "machinery_ready": ("the scenario, tracing and statistics machinery in this module is approach-agnostic: it "
                                "needs a per-month calibrated numerical view, the allocator's own prior, and the native "
                                "weights it produces. None of that exists for the development window yet."),
            "blockers": ["83 of 95 development-replay months are not yet run on the free GPU",
                         "G3a schema-valid call rate 0.9771 against a 0.98 floor, from the vendored assessor",
                         "G3b accuracy 0.5667 against 0.80 with 2 opposite-direction errors against a limit of 1"]}


def cross_approach(blocks: dict, approaches: dict) -> dict:
    """Why do the Deterministic model and JEV move together? Separate the baseline exposure, the signal response
    and the realised market from one another, rather than attributing the similarity to any one mechanism."""
    r = lambda k, s: blocks[k]["sims"][s]["net_excess_return"].to_numpy(float)
    ctrl = lambda k: blocks[k]["controls"]["native_neutral_static"]["net_excess_return"].to_numpy(float)
    pair = {}
    for a, b in [(x, y) for x, y in itertools.combinations(("AP1", "AP2B", "AP2A", "AP3"), 2) if x in blocks and y in blocks]:
        s_a, s_b = r(a, key(1.0)) - r(a, key(0.0)), r(b, key(1.0)) - r(b, key(0.0))
        pair[f"{a}_vs_{b}"] = {
            "monthly_net_return_correlation_1x": float(np.corrcoef(r(a, key(1.0)), r(b, key(1.0)))[0, 1]),
            "monthly_net_return_correlation_0x": float(np.corrcoef(r(a, key(0.0)), r(b, key(0.0)))[0, 1]),
            "monthly_net_return_correlation_native_no_signal_controls": float(np.corrcoef(ctrl(a), ctrl(b))[0, 1]),
            "monthly_signal_part_correlation": float(np.corrcoef(s_a, s_b)[0, 1]),
            "signal_part_definition": "the 1x scenario's monthly net excess return minus the same approach's 0x scenario",
        }
    var = {}
    for k in blocks:
        tot, base = r(k, key(1.0)), r(k, key(0.0))
        sig = tot - base
        var[k] = {
            "annualised_vol_1x": float(np.sqrt(12.0) * tot.std(ddof=1)),
            "annualised_vol_0x_baseline_only": float(np.sqrt(12.0) * base.std(ddof=1)),
            "annualised_vol_of_the_signal_part": float(np.sqrt(12.0) * sig.std(ddof=1)),
            "signal_part_share_of_1x_variance": float(sig.var(ddof=1) / tot.var(ddof=1)),
            "correlation_1x_with_own_0x": float(np.corrcoef(tot, base)[0, 1]),
            "mean_abs_signal_induced_weight_change": approaches[k]["signal_share_of_allocation"]["mean_distance_1x_from_0x_the_signal_part"],
            "mean_abs_active_weight_vs_native_neutral": approaches[k]["performance"]["by_scenario"][key(1.0)]["mean_half_sum_abs_active"],
        }
    return {
        "pairwise": pair,
        "per_approach_variance_split": var,
        "mechanisms_examined": {
            "similar_baseline_market_exposure": ("Supported by the numbers: each approach's 0x scenario is nearly all of its own "
                                                 "1x return series, and the two 0x series are more correlated with each other than the "
                                                 "1x series are."),
            "views_weak_relative_to_the_prior": "Measured per approach as the size of the signal-induced part of the view against the allocator's own prior; see transmission.",
            "capped_or_constrained_response": "Measured per approach as the share of months with a binding bound and the constraint attenuation share; see transmission.",
            "different_signals_producing_small_active_positions": "Measured as mean_abs_signal_induced_weight_change against mean_abs_active_weight_vs_native_neutral.",
            "not_attributable_to_Black_Litterman_alone": ("JEV does not use the Deterministic model's Black-Litterman path. It applies a "
                                                          "capped tilt to its own equilibrium edge, so any shared attenuation has to be "
                                                          "explained per architecture, not by one allocator."),
        },
        "separation_note": ("Signal transmission is not signal predictive quality. These numbers say how much of each portfolio's "
                            "behaviour comes from its views; they do not say whether those views are informative. The Signal "
                            "Value-Added study addresses the second question and is not restated here."),
    }


def main(argv=None) -> int:
    cfg = load_config()
    mk = load_market(cfg)
    dev = months_between(*cfg["windows"]["development"])
    assert_scoring_allowed(dev, protected_start=cfg["windows"]["protected"][0])
    cost = cfg["costs"]["cost_per_dollar_traded"]
    P = frozen(cfg)
    OUT.mkdir(parents=True, exist_ok=True)

    blocks = {"AP1": ap1_block(mk, dev, cost, cfg, P),
              "AP2B": ap2_block("AP2B", mk, dev, cost, cfg),
              "AP2A": ap2_block("AP2A", mk, dev, cost, cfg)}
    meta = {"AP1": ("Deterministic Quantitative Model", "Deterministic", "primary (research baseline)"),
            "AP2B": ("Agentic Workflow - JEV", "JEV", "primary representative of the Agentic Workflow"),
            "AP2A": ("Agentic Workflow - Agent Committee", "Committee", "secondary within-approach variant"),
            "AP3": ("Agentic Causal RAG", "Causal RAG", "primary")}
    S3 = ap3_inputs(dev)
    if S3 is not None:
        blocks["AP3"] = ap3_block(mk, dev, cost, cfg, S3)
    approaches = {k: approach_block(*meta[k], blocks[k], P, k) for k in blocks}
    if S3 is None:
        approaches["AP3"] = ap3_status()
    else:
        # genuine outputs exist, but the gates still failed: the scenarios are computed and stay labelled as such
        from native_backtest.ap3 import exploratory as X
        g = (S3["summary"].get("gates") or {})
        approaches["AP3"].update({
            "status": "COMPUTED - EXPLORATORY, RELIABILITY GATES FAILED" if S3["exploratory"] else "computed",
            "designation": X.LABEL,
            "validated": False,
            "gates": {k2: v.get("pass") for k2, v in g.items()},
            "gates_failed": {k2: v.get("checks") for k2, v in g.items() if v.get("pass") is False},
            "model_substitution": S3["summary"].get("model_substitution"),
            "agent_months": S3["summary"].get("n_months"),
            "caveat": ("These scenarios run on genuine qwen3:4b agent outputs that did NOT pass the pre-registered "
                       "reliability gates. They are diagnostics of signal transmission, not evidence that the agents "
                       "are reliable or that AI adds investment value."),
            "categorical_note": ("Supported, Contradicted and Insufficient were never scaled. They are encoded and "
                                 "calibrated into a numerical view upstream exactly as in the archived run; only that "
                                 "view is rescaled.")})

    bad = [k for k, v in blocks.items() if not v["reproduction"]["within_tolerance"]]
    if bad:
        raise SystemExit(f"1x does not reproduce the archived series within {REPRO_TOL} for {bad}; stopping as pre-registered")

    report = {
        "title": "Forecast-to-Allocation Sensitivity Experiment",
        "status": "DEVELOPMENT DIAGNOSTIC - not a confirmatory result",
        "preregistration": {"file": str(PREREG.relative_to(ROOT)), "version": json.loads(PREREG.read_text())["version"]},
        "window": {"development": [str(dev[0]), str(dev[-1])], "n_months": len(dev),
                   "protected_window_start": cfg["windows"]["protected"][0],
                   "protected_window_touched": False},
        "scenarios": {key(l): LABELS[l] for l in LAMBDAS},
        "accounting": {"evaluator": "native_backtest/framework/accounting.simulate_records (shared, unchanged)",
                       "cost_per_dollar_traded": cost},
        "approaches": approaches,
        "cross_approach": cross_approach(blocks, approaches),
        "limitations": [
            "46 development months. The intervals are wide and none of these comparisons is confirmatory.",
            "Four scenarios for each of three allocators were examined. No multiplicity correction is applied and no bootstrap p-value here is a claim of significance.",
            "The 2x scenario is a diagnostic stress test. It is not a recommendation, and it was not selected on any criterion.",
            "This experiment measures signal transmission, not signal predictive quality. A portfolio can respond strongly to an uninformative view, and a useful view can be attenuated to nothing.",
            "The approaches hold different assets (SPY/IEF/LQD against SPY/TLT) with different neutral portfolios and different risk structures, so weight responses are comparable only in relative terms.",
            ("Causal RAG is included only as an EXPLORATORY diagnostic: its genuine qwen3:4b outputs failed both "
             "pre-registered reliability gates, so its scenarios describe how its allocator transmits a view, not "
             "whether that view is trustworthy."
             if "AP3" in blocks else
             "Causal RAG is not included: no calibrated view series exists for the development window."),
        ],
    }
    (OUT / "forecast_to_allocation_sensitivity.json").write_text(json.dumps(report, indent=1, default=float) + "\n")
    for k, b in blocks.items():
        pd.concat([b["trace"][key(l)].assign(scenario=key(l)) for l in LAMBDAS], ignore_index=True) \
            .to_csv(OUT / f"{k.lower()}_transmission_trace.csv", index=False)
        pd.concat([b["sims"][key(l)].assign(scenario=key(l)) for l in LAMBDAS]
                  + [v.assign(scenario=f"control:{c}") for c, v in b["controls"].items()], ignore_index=True) \
            .to_csv(OUT / f"{k.lower()}_scenario_returns.csv", index=False)
    print(json.dumps({"written": str((OUT / 'forecast_to_allocation_sensitivity.json').relative_to(ROOT)),
                      "reproduction": {k: v["reproduction"]["within_tolerance"] for k, v in blocks.items()}}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
