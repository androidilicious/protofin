"""Level playing field: the deterministic model, Jev and the agent committee through one SPY/TLT pipeline.

Each approach supplies only a raw monthly signal. Everything else is shared and identical:

  raw signal (known at the month-end decision)
    -> view Q per fund: Stage 2's Ridge with its frozen alpha grid, expanding window from 2015-02,
       labels through t-2 only, predicting next month's return above cash        (same learner for all)
    -> view uncertainty Omega: mean squared one-step validation error of the chosen alpha on past
       months only                                                                (same rule for all)
    -> Black-Litterman around the configured prior mix (default 60/40), P = I, tau, delta,
       36-month Ledoit-Wolf covariance of completed labels, He-Litterman Sigma_BL
    -> bounded mean-variance weights (prior +/- band)
    -> the shared evaluator's accounting, net CER and paired block bootstrap

Systems: DET (8 macro surprises), JEV (P(stocks beat bonds), expected tilt, confidence),
COMMITTEE (CIO SPY and TLT views, confidence), PLACEBO (no signal: Q = historical average),
JEV and COMMITTEE answer the one-month question (collect_1m.py); JEV_12M and COMMITTEE_12M are the
original 12-month answers, kept as a check on what the horizon changes;
and STATIC (the prior mix with no views, rebalanced monthly).
Only development months are scored; the protected window is never touched.

    python -m level_playing_field.run            # default mix from config.json
    python -m level_playing_field.run --grid     # also 50/50 and 70/30
"""
from __future__ import annotations

import argparse
import dataclasses
import itertools
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Mapping, Sequence

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "stage2" / "scoring"))
import stage2_backtest as s2  # noqa: E402
from native_backtest.framework import market as mk  # noqa: E402
from native_backtest.framework import records as rc  # noqa: E402
from native_backtest.framework.accounting import simulate_records  # noqa: E402
from native_backtest.framework.metrics import cer, holm, metrics, paired_cer_contrast  # noqa: E402
from sklearn.covariance import LedoitWolf  # noqa: E402

HERE = Path(__file__).resolve().parent
CONF_NUM = {"Low": 0.0, "Medium": 1.0, "High": 2.0}


# ------------------------------------------------------------------ raw signals (one table per approach)
def month_of(as_of: str) -> pd.Period:
    return pd.Period(as_of[:7], "M")


def signals_det(spec: dict) -> pd.DataFrame:
    cfg = dict(spec["macro_panel"]); cfg["path"] = str(ROOT / cfg["path"])
    macro = s2.load_macro_panel(cfg)
    df = macro.set_index("month")[list(s2.MACRO_FEATURES)].copy()
    df.index = pd.PeriodIndex(df.index, freq="M")
    return df.sort_index()


def signals_jev(path: Path) -> pd.DataFrame:
    rows = {}
    for as_of, j in json.loads(path.read_text(encoding="utf-8"))["months"].items():
        rows[month_of(as_of)] = {"p_stocks_beat_bonds": j["p"], "expected_tilt": j["offset"], "confidence": j["confidence"]}
    return pd.DataFrame.from_dict(rows, orient="index").sort_index()


def signals_committee(path: Path) -> pd.DataFrame:
    rows = {}
    for as_of, c in json.loads(path.read_text(encoding="utf-8"))["months"].items():
        f = c["cio"]
        ok = not c["problems"]
        rows[month_of(as_of)] = {"cio_spy_12m": f["spy_q"] if ok else np.nan, "cio_tlt_12m": f["tlt_q"] if ok else np.nan,
                                 "confidence": CONF_NUM.get(f["confidence"], np.nan) if ok else np.nan}
    return pd.DataFrame.from_dict(rows, orient="index").sort_index()


# ------------------------------------------------------------------ views and Omega (identical learner)
def view_and_omega(X: pd.DataFrame | None, y: pd.Series, dm: pd.Period, train_start: pd.Period):
    """Q and Omega for one fund at decision month dm. X None = placebo (historical average)."""
    last = dm - 2
    months = [m for m in y.index if train_start <= m <= last and np.isfinite(y[m])]
    ytr = y.loc[months].to_numpy(dtype=float)
    if X is None:
        q = float(ytr.mean())
        errs = [(ytr[j] - ytr[tr].mean()) ** 2 for tr, j in s2.inner_splits(len(ytr))]
        return q, float(np.mean(errs)), "INTERCEPT_ONLY", len(ytr)
    Xtr = X.reindex(months).to_numpy(dtype=float)
    x = X.reindex([dm]).to_numpy(dtype=float)[0]
    alpha, _, losses = s2.choose_alpha(Xtr, ytr)
    q, _ = s2.ridge_fit_predict(Xtr, ytr, x, alpha)
    return float(q), float(losses[str(alpha)]), alpha, len(ytr)


# ------------------------------------------------------------------ allocation (Black-Litterman, bounded)
def allocate(sigma, q, omega, prior, lo, hi, delta, tau):
    pi = delta * sigma @ prior
    ts_inv = np.linalg.inv(tau * sigma)
    om_inv = np.diag(1.0 / omega)
    m = np.linalg.inv(ts_inv + om_inv)
    mu = m @ (ts_inv @ pi + om_inv @ q)
    S = sigma + m
    best, best_u = None, -math.inf
    n = len(mu)
    for states in itertools.product((0, 1, 2), repeat=n):
        w = np.zeros(n)
        free = [i for i, s in enumerate(states) if s == 0]
        fixed = [i for i, s in enumerate(states) if s != 0]
        for i in fixed:
            w[i] = lo[i] if states[i] == 1 else hi[i]
        rem = 1.0 - w[fixed].sum()
        if not free:
            if abs(rem) > 1e-12:
                continue
        else:
            b = mu[free] - (delta * S[np.ix_(free, fixed)] @ w[fixed] if fixed else 0.0)
            inv = np.linalg.inv(S[np.ix_(free, free)])
            one = np.ones(len(free))
            lam = (one @ inv @ b - delta * rem) / (one @ inv @ one)
            w[free] = inv @ (b - lam * one) / delta
        if (w < lo - 1e-12).any() or (w > hi + 1e-12).any():
            continue
        u = float(w @ mu - 0.5 * delta * w @ S @ w)
        if u > best_u + 1e-15:
            best, best_u = w.copy(), u
    return best, pi, mu


# ------------------------------------------------------------------ run
def run(cfg: dict, prior_spy: float, market, spec, months, raw, y_by_asset) -> Dict:
    assets = cfg["assets"]
    prior = np.array([prior_spy, 1 - prior_spy])
    band = cfg["bounds_band"]
    lo, hi = np.clip(prior - band, 0, 1), np.clip(prior + band, 0, 1)
    train_start = pd.Period(cfg["train_start"], "M")
    excess = pd.DataFrame({a: y_by_asset[a] for a in assets})
    recs: Dict[str, List[rc.DecisionRecord]] = {k: [] for k in raw}
    detail_rows = []
    for dm in months:
        win = [m for m in excess.index if dm - 1 - cfg["cov_window_months"] <= m <= dm - 2]
        sigma = LedoitWolf(assume_centered=False).fit(excess.loc[win].to_numpy()).covariance_
        day = market.decision_dates[dm]
        t = mk.decision_time_iso(day)
        for name, X in raw.items():
            q, om, al = np.zeros(2), np.zeros(2), []
            for i, a in enumerate(assets):
                q[i], om[i], alpha, n = view_and_omega(X, excess[a], dm, train_start)
                al.append(str(alpha))
            w, pi, mu = allocate(sigma, q, om, prior, lo, hi, cfg["delta"], cfg["tau"])
            recs[name].append(rc.DecisionRecord(
                system_id=f"LPF_{name}", decision_month=str(dm), decision_time=t, info_cutoff=t, universe=list(assets),
                target_weights={a: float(w[i]) for i, a in enumerate(assets)},
                generation={"mode": "computed_native", "pipeline": "level_playing_field", "prior": dict(zip(assets, prior.tolist()))},
                forecast={"horizon_months": 1, "kind": "excess_return_view", "values": dict(zip(assets, q.tolist()))},
                confidence={"omega_diag": dict(zip(assets, om.tolist())), "ridge_alpha": dict(zip(assets, al))}))
            detail_rows.append({"system": name, "decision_month": str(dm), **{f"q_{a}": q[i] for i, a in enumerate(assets)},
                                **{f"omega_{a}": om[i] for i, a in enumerate(assets)}, **{f"pi_{a}": pi[i] for i, a in enumerate(assets)},
                                **{f"mu_{a}": mu[i] for i, a in enumerate(assets)}, **{f"w_{a}": w[i] for i, a in enumerate(assets)},
                                **{f"alpha_{a}": al[i] for i, a in enumerate(assets)}})
    static = [dataclasses.replace(r, system_id="LPF_STATIC", target_weights={a: float(prior[i]) for i, a in enumerate(assets)},
                                  generation={"mode": "computed_native", "benchmark": "static prior, monthly rebalance"},
                                  forecast=None, confidence=None) for r in recs[next(iter(recs))]]
    for lst in list(recs.values()) + [static]:
        for r in lst:
            rc.validate(r)
    sims = {k: simulate_records(v, market, months, cost_per_dollar=cfg["cost_per_dollar"]) for k, v in recs.items()}
    sims["STATIC"] = simulate_records(static, market, months, cost_per_dollar=cfg["cost_per_dollar"])
    b = cfg["bootstrap"]
    kw = dict(delta=cfg["delta"], block=b["block_months"], reps=b["reps"], seed=b["seed"])
    table = {k: {**metrics(s), "net_cer": cer(s["net_excess_return"], cfg["delta"]),
                 "mean_spy_weight": float(s[f"w_{assets[0]}"].mean()), "min_spy_weight": float(s[f"w_{assets[0]}"].min()),
                 "max_spy_weight": float(s[f"w_{assets[0]}"].max())} for k, s in sims.items()}
    approaches = [k for k in raw if k != "PLACEBO"]
    primary = cfg["primary"]
    vs_static = {k: paired_cer_contrast(sims[k], sims["STATIC"], **kw) for k in approaches + ["PLACEBO"]}
    vs_placebo = {k: paired_cer_contrast(sims[k], sims["PLACEBO"], **kw) for k in approaches}
    vs_det = {k: paired_cer_contrast(sims[k], sims["DET"], **kw) for k in approaches if k != "DET"} if "DET" in sims else {}
    return {"prior_spy": prior_spy, "metrics": table,
            "vs_static": vs_static, "vs_static_holm": holm({k: vs_static[k]["p_two_sided_bootstrap"] for k in primary}),
            "vs_placebo": vs_placebo, "vs_det": vs_det, "vs_det_holm": holm({k: vs_det[k]["p_two_sided_bootstrap"] for k in primary if k != "DET"}),
            "_detail": pd.DataFrame(detail_rows), "_sims": sims}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", action="store_true", help="also run the other prior mixes in config.json")
    args = ap.parse_args(argv)
    cfg = json.loads((HERE / "config.json").read_text())
    fcfg = mk.load_config()
    market = mk.load_market(fcfg)
    spec = json.loads((ROOT / fcfg["inherits_stage2_run_spec"]["path"]).read_text())
    d0, d1 = cfg["development"]
    months = mk.months_between(d0, d1)
    if months[-1] >= pd.Period("2023-01", "M"):
        raise SystemExit("refusing: development window reaches the protected window")
    # completed monthly labels (excess return over the holding period) for every month we may train on
    label_months = mk.months_between("2012-01", d1)   # labels for training (from 2015-02) and the 36-month covariance
    y = {a: pd.Series({m: market.period_returns(m, [a])[a] - market.rf_return(m) for m in label_months}) for a in cfg["assets"]}
    src = cfg["sources"]
    raw = {"DET": signals_det(spec), "JEV": signals_jev(ROOT / src["jev_1m"]), "COMMITTEE": signals_committee(ROOT / src["committee_1m"]),
           "JEV_12M": signals_jev(ROOT / src["jev_12m"]), "COMMITTEE_12M": signals_committee(ROOT / src["committee_12m"]), "PLACEBO": None}
    # a source with no answers would silently act as the placebo; skip it loudly instead
    need = mk.months_between(cfg["train_start"], d1)
    for name in [k for k, X in raw.items() if X is not None]:
        cov = raw[name].reindex(need).notna().all(axis=1).mean() if raw[name].shape[1] else 0.0
        if cov < 0.9:
            print(f"SKIPPED {name}: answers for only {cov:.0%} of {need[0]}..{need[-1]} (need 90%); run collect_1m.py first")
            del raw[name]
    cfg["primary"] = [k for k in cfg["primary"] if k in raw]
    out_dir = HERE / "out"; out_dir.mkdir(exist_ok=True)
    mixes = [cfg["prior_weights"]["SPY"]] + ([p for p in cfg["prior_grid"] if abs(p - cfg["prior_weights"]["SPY"]) > 1e-9] if args.grid else [])
    summary = {}
    for p in mixes:
        res = run(cfg, p, market, spec, months, raw, y)
        tag = f"spy{int(round(p * 100))}"
        res.pop("_detail").to_csv(out_dir / f"views_weights_{tag}.csv", index=False)
        pd.concat(res.pop("_sims").values()).to_csv(out_dir / f"returns_{tag}.csv", index=False)
        summary[tag] = res
        m = res["metrics"]
        print(f"\nprior {p:.0%} SPY / {1 - p:.0%} TLT  ({len(months)} development months)")
        for k in [k for k in ["STATIC", "PLACEBO", "DET", "JEV", "COMMITTEE", "JEV_12M", "COMMITTEE_12M"] if k in m]:
            line = f"  {k:13s} net CER {m[k]['net_cer'] * 100:6.2f}%  SPY {m[k]['min_spy_weight'] * 100:4.1f}-{m[k]['max_spy_weight'] * 100:4.1f}%"
            if k in res["vs_static"]:
                c = res["vs_static"][k]
                line += f"  vs static {c['cer_difference'] * 100:+6.2f} pts  95% [{c['ci95'][0] * 100:+.2f}, {c['ci95'][1] * 100:+.2f}]  p={c['p_two_sided_bootstrap']:.2f}"
            print(line)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
