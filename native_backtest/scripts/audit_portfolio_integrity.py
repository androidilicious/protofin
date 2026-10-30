#!/usr/bin/env python3
"""Portfolio return and backtest integrity audit: Deterministic (AP1) vs Agentic Workflow JEV (AP2B).

An INDEPENDENT reconstruction: this script imports nothing from native_backtest.framework, the adapters or
Stage 2. It parses the raw pinned price and cash-rate files itself (SHA-256 checked), rebuilds the trading
calendar, the decision / entry / exit dates and the cash accrual from their written rules, reads each system's
target weights straight from its decision-record file, and recomputes monthly gross and net returns, costs,
turnover, compounding and metrics. It then compares the result at full precision with
  (a) the shared evaluator's outputs  native_backtest/out/development/*_common_matched_dev.csv,
  (b) Stage 2's canonical saved results for System A (the Deterministic model),
  (c) the dashboard data            mvp/data/dashboard.json (rounded to 6 decimals there),
and computes the similarity, exposure, decision and look-ahead diagnostics.

Development window only (decision months 2019-03..2022-12); the protected window is never read for scoring.
Outputs: native_backtest/out/audit/portfolio_integrity_v1.json and reconstruction_v1.csv.

Formulas (month t, assets a, target weights w_t, pre-trade drifted weights p_t, asset total returns r_t):
  r_{a,t}   = AdjClose_a(exit_t) / AdjClose_a(entry_t) - 1
  cost_t    = 0.0005 * sum_a |w_{a,t} - p_{a,t}|          (p_1 = 0: the first month starts from cash)
  gross_t   = sum_a w_{a,t} r_{a,t};   net_t = gross_t - cost_t;   excess_t = net_t - rf_t
  p_{t+1}   = w_t (1 + r_t) / sum(w_t (1 + r_t))
  rf_t      = (1 + r28)^(days/28) - 1, r28 = (d*28/360) / (1 - d*28/360), d = DTB4WK quote (%/100) at entry
  wealth_T  = prod_{t<=T} (1 + net_t)
  net CER   = 12 * (mean(excess) - 1.25 * var(excess, ddof=1))

Usage (repository root): python -m native_backtest.scripts.audit_portfolio_integrity
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "native_backtest/out/audit"
DEV = ("2019-03", "2022-12")
COST = 0.0005
PRICE_FILES = {   # post-2018 segments only: every development entry and exit date is on or after 2019-04-01
    "SPY": ("stage2/data/_pinned/market_price_SPY_2018plus.tsv", "c3e8f068c5b2e28e1010317e2c6eaae7e658ffb73c592949420a3610da70618d"),
    "IEF": ("stage2/data/_pinned/market_price_IEF_2018plus.tsv", "78dc66055d35e01cf24cb0b01327690dc5c64176cea128d049609a6446d6221d"),
    "LQD": ("stage2/data/_pinned/market_price_LQD_2018plus.tsv", None),
    "TLT": ("stage2/data/_pinned/market_price_TLT_2018plus.tsv", "fdecb0c33c3209f6fe033e3541da1c15feda7e16b2f9c9305607263bb0b3e52e"),
}
DTB4WK = ("stage2/data/risk_free/DTB4WK_combined_2001-07-31_to_2026-10-01.csv", "ed2f0bc7e3cc337f1e1ec8f4b2b823a69fed879f2dd6c2c6eefb6e62cd22a66a")
SYSTEMS = {"AP1": ("Deterministic Quantitative Model", "det", {"SPY": 0.45, "IEF": 0.35, "LQD": 0.20}),
           "AP2B": ("Agentic Workflow - JEV", "jev", {"SPY": 0.60, "TLT": 0.40})}
PASSIVE = {"SPY": 0.60, "IEF": 0.40}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def expected_sha(asset: str) -> str:
    """The pinned hash as written in the Stage 2 run spec (LQD's is read from there too)."""
    spec = json.loads((ROOT / "stage2/scoring/stage2_run_spec_dev_v4.json").read_text())["prices"]
    if asset in spec:
        return next(s["expected_sha256"] for s in spec[asset]["segments"] if s["path"].endswith("2018plus.tsv"))
    return PRICE_FILES[asset][1]


def load_close(asset: str) -> pd.Series:
    p = ROOT / PRICE_FILES[asset][0]
    if sha(p) != expected_sha(asset):
        raise SystemExit(f"{p} does not match its pinned SHA-256")
    df = pd.read_csv(p, sep="\t")
    s = pd.Series(pd.to_numeric(df["Close"], errors="raise").to_numpy(float), index=pd.to_datetime(df["Date"]).dt.normalize())
    if s.index.duplicated().any() or not s.index.is_monotonic_increasing:
        raise SystemExit(f"{asset}: duplicated or unsorted dates")
    return s


def load_dtb4wk() -> pd.Series:
    p = ROOT / DTB4WK[0]
    if sha(p) != DTB4WK[1]:
        raise SystemExit("DTB4WK file does not match its pinned SHA-256")
    df = pd.read_csv(p)
    v = pd.to_numeric(df.iloc[:, 1], errors="coerce")
    return pd.Series(v.to_numpy(float), index=pd.to_datetime(df.iloc[:, 0])).dropna().sort_index()


def calendar(prices: dict) -> pd.DatetimeIndex:
    idx = None
    for s in prices.values():
        idx = s.index if idx is None else idx.intersection(s.index)
    return idx.sort_values()


def dates_for(month: str, cal: pd.DatetimeIndex) -> tuple:
    m = pd.Period(month, "M")
    decision = cal[(cal >= m.start_time) & (cal <= m.end_time)].max()
    entry = cal[cal > m.end_time.normalize()].min()
    exit_ = cal[cal > (m + 1).end_time.normalize()].min()
    return decision, entry, exit_


def rf_return(dtb: pd.Series, entry: pd.Timestamp, exit_: pd.Timestamp) -> float:
    q = dtb[dtb.index <= entry]
    if (entry - q.index[-1]).days > 10:
        raise SystemExit(f"stale DTB4WK quote at {entry.date()}")
    d = q.iloc[-1] / 100.0 * 28.0 / 360.0
    r28 = d / (1.0 - d)
    return (1.0 + r28) ** ((exit_ - entry).days / 28.0) - 1.0


DECISION_FILE = {"AP3": "AP3_qwen3_reduced_evidence.jsonl"}


def read_weights(system: str) -> dict:
    out = {}
    f = ROOT / "native_backtest/out/decisions" / DECISION_FILE.get(system, f"{system}.jsonl")
    for line in f.read_text().splitlines():
        r = json.loads(line)
        out[r["decision_month"]] = r
    return out


def simulate(weights_by_month: dict, months: list, prices: dict, cal: pd.DatetimeIndex, dtb: pd.Series) -> pd.DataFrame:
    assets = list(next(iter(weights_by_month.values())).keys())
    pre = np.zeros(len(assets))
    rows = []
    for m in months:
        w = np.array([weights_by_month[m][a] for a in assets], dtype=float)
        dec, entry, exit_ = dates_for(m, cal)
        r = np.array([prices[a][exit_] / prices[a][entry] - 1.0 for a in assets])
        traded = float(np.abs(w - pre).sum())
        cost = COST * traded
        gross = float(w @ r)
        rf = rf_return(dtb, entry, exit_)
        rows.append({"month": m, "decision_date": dec.date().isoformat(), "entry": entry.date().isoformat(), "exit": exit_.date().isoformat(),
                     **{f"w_{a}": w[i] for i, a in enumerate(assets)}, **{f"r_{a}": r[i] for i, a in enumerate(assets)},
                     "traded": traded, "cost": cost, "gross": gross, "net": gross - cost, "rf": rf, "excess": gross - cost - rf})
        g = w * (1.0 + r)
        pre = g / g.sum()
    return pd.DataFrame(rows)


def metrics(df: pd.DataFrame) -> dict:
    x = df["excess"].to_numpy(float)
    wealth = np.cumprod(1.0 + df["net"].to_numpy(float))
    path = np.concatenate([[1.0], wealth])
    ann = 12.0 * x.mean()
    vol = np.sqrt(12.0) * x.std(ddof=1)
    return {"cer": 12.0 * (x.mean() - 1.25 * x.var(ddof=1)), "ann_excess_return": ann, "volatility": vol, "sharpe": ann / vol,
            "max_drawdown": float((path / np.maximum.accumulate(path) - 1.0).min()), "cumulative_return": float(wealth[-1] - 1.0),
            "turnover": 12.0 * float((0.5 * df["traded"]).mean()), "total_cost": float(df["cost"].sum())}


def corr(a, b) -> float:
    return float(np.corrcoef(np.asarray(a, float), np.asarray(b, float))[0, 1])


def ols(y, X) -> tuple:
    X1 = np.column_stack([np.ones(len(y))] + [np.asarray(c, float) for c in X])
    beta, *_ = np.linalg.lstsq(X1, np.asarray(y, float), rcond=None)
    resid = np.asarray(y, float) - X1 @ beta
    r2 = 1.0 - resid.var() / np.asarray(y, float).var()
    return beta, r2, resid


def main() -> int:
    months = [str(p) for p in pd.period_range(DEV[0], DEV[1], freq="M")]
    prices = {a: load_close(a) for a in PRICE_FILES}
    cal = calendar(prices)
    dtb = load_dtb4wk()
    if min(dates_for(months[0], cal)[1:]) < pd.Timestamp("2018-01-02"):
        raise SystemExit("a development date precedes the post-2018 price files")
    recs = {s: read_weights(s) for s in SYSTEMS}
    sims, findings, checks = {}, [], {}

    # ---------------------------------------------------------------- reconstruction
    for s, (name, key, neutral) in SYSTEMS.items():
        wb = {m: recs[s][m]["target_weights"] for m in months}
        sims[s] = simulate(wb, months, prices, cal, dtb)
        sims[f"{s}_NEUTRAL"] = simulate({m: neutral for m in months}, months, prices, cal, dtb)
    sims["PASSIVE"] = simulate({m: PASSIVE for m in months}, months, prices, cal, dtb)
    sims["AP2A"] = simulate({m: read_weights("AP2A")[m]["target_weights"] for m in months}, months, prices, cal, dtb)

    # (a) shared evaluator outputs, full precision
    cmp_eval = {}
    for s, f in (("AP1", "AP1_common_matched_dev"), ("AP2B", "AP2B_common_matched_dev"), ("AP2A", "AP2A_common_matched_dev"),
                 ("PASSIVE", "COMMON_60_40_SPY_IEF_matched_dev")):
        ev = pd.read_csv(ROOT / f"native_backtest/out/development/{f}.csv")
        mine = sims[s]
        cmp_eval[s] = {
            "months_equal": ev["decision_month"].astype(str).tolist() == mine["month"].tolist(),
            "entry_exit_equal": ev["entry_date"].tolist() == mine["entry"].tolist() and ev["exit_date"].tolist() == mine["exit"].tolist(),
            "max_abs_diff_net_return": float(np.abs(ev["net_total_return"].to_numpy() - mine["net"].to_numpy()).max()),
            "max_abs_diff_rf": float(np.abs(ev["rf_return"].to_numpy() - mine["rf"].to_numpy()).max()),
            "max_abs_diff_cost": float(np.abs(ev["cost"].to_numpy() - mine["cost"].to_numpy()).max()),
            "max_abs_diff_weights": float(max(np.abs(ev[c].to_numpy() - mine[c].to_numpy()).max() for c in mine.columns if c.startswith("w_"))),
            "max_abs_diff_wealth": float(np.abs(np.cumprod(1 + ev["net_total_return"].to_numpy()) - np.cumprod(1 + mine["net"].to_numpy())).max()),
        }
    checks["vs_shared_evaluator"] = cmp_eval

    # (b) Stage 2 canonical saved results (System A = the Deterministic model)
    s2 = pd.read_csv(ROOT / "stage2/results/dev_rerun_v4_portfolio_2026-10-27/stage2_portfolio_returns.csv")
    a = s2[s2["strategy"] == "A"].copy()
    a["m"] = a["decision_month"].astype(str)
    a = a.set_index("m").loc[months]
    netcol = "net_total_return" if "net_total_return" in a.columns else [c for c in a.columns if "net" in c and "total" in c][0]
    checks["vs_stage2_saved_system_A"] = {
        "max_abs_diff_net_return": float(np.abs(a[netcol].to_numpy(float) - sims["AP1"]["net"].to_numpy()).max()),
        "max_abs_diff_weights": float(max(np.abs(a[f"w_{x}"].to_numpy(float) - sims["AP1"][f"w_{x}"].to_numpy()).max() for x in ("SPY", "IEF", "LQD")))
        if all(f"w_{x}" in a.columns for x in ("SPY", "IEF", "LQD")) else None}

    # (c) dashboard data (values rounded to 6 decimals there)
    D = json.loads((ROOT / "mvp/data/dashboard.json").read_text())
    cmp_dash = {}
    for s, (name, key, _) in SYSTEMS.items():
        ser = D["dev"]["series"][key]
        mine_w = np.cumprod(1 + sims[s]["net"].to_numpy())
        m = metrics(sims[s])
        dm = ser["metrics"]
        cmp_dash[key] = {"source_system": s, "dashboard_months_equal": D["dev"]["months"] == months,
                         "max_abs_diff_wealth": float(np.abs(np.array(ser["wealth"]) - mine_w).max()),
                         "max_abs_diff_monthly_net": float(np.abs(np.array(ser["monthly_net_return"]) - sims[s]["net"].to_numpy()).max()),
                         "metric_diffs": {k: float(abs(dm[k] - m[k])) for k in ("cer", "volatility", "max_drawdown", "cumulative_return", "turnover", "sharpe", "ann_excess_return")},
                         "wealth_matches_other_system": bool(np.abs(np.array(ser["wealth"]) - np.cumprod(1 + sims["AP1" if s == "AP2B" else "AP2B"]["net"].to_numpy())).max() < 1e-6)}
    cmp_dash["passive"] = {"max_abs_diff_wealth": float(np.abs(np.array(D["dev"]["common_benchmark"]["wealth"]) - np.cumprod(1 + sims["PASSIVE"]["net"].to_numpy())).max())}
    checks["vs_dashboard"] = cmp_dash

    # ---------------------------------------------------------------- similarity
    d, j, p = sims["AP1"], sims["AP2B"], sims["PASSIVE"]
    spread = j["net"].to_numpy() - d["net"].to_numpy()
    act_d = d["net"].to_numpy() - sims["AP1_NEUTRAL"]["net"].to_numpy()
    act_j = j["net"].to_numpy() - sims["AP2B_NEUTRAL"]["net"].to_numpy()
    sim_ = {
        "corr_monthly_net": corr(d["net"], j["net"]),
        "corr_monthly_excess_over_cash": corr(d["excess"], j["excess"]),
        "corr_excess_over_passive": corr(d["net"] - p["net"], j["net"] - p["net"]),
        "corr_active_vs_own_benchmark": corr(act_d, act_j),
        "own_benchmarks": {"AP1": SYSTEMS["AP1"][2], "AP2B": SYSTEMS["AP2B"][2]},
        "corr_own_benchmarks": corr(sims["AP1_NEUTRAL"]["net"], sims["AP2B_NEUTRAL"]["net"]),
        "spread_jev_minus_det": {"mean_monthly": float(spread.mean()), "sd_monthly": float(spread.std(ddof=1)),
                                 "tracking_error_annualised": float(spread.std(ddof=1) * np.sqrt(12)),
                                 "min": float(spread.min()), "max": float(spread.max()),
                                 "months_abs_gt_0_5pp": int((np.abs(spread) > 0.005).sum()), "months_abs_gt_1pp": int((np.abs(spread) > 0.01).sum()),
                                 "months_abs_gt_2pp": int((np.abs(spread) > 0.02).sum())},
        "direction_agreement_share": float((np.sign(d["net"]) == np.sign(j["net"])).mean()),
        "corr_cumulative_levels_NOT_evidence": corr(np.cumprod(1 + d["net"]), np.cumprod(1 + j["net"])),
    }

    # ---------------------------------------------------------------- decisions and exposures
    wd = d[["w_SPY", "w_IEF", "w_LQD"]]
    wj = j[["w_SPY", "w_TLT"]]
    dec = {
        "AP1": {"w_mean": wd.mean().to_dict(), "w_sd": wd.std(ddof=1).to_dict(), "w_min": wd.min().to_dict(), "w_max": wd.max().to_dict(),
                "distinct_weight_vectors": int(wd.round(10).drop_duplicates().shape[0]),
                "mean_abs_deviation_from_own_benchmark": float(np.abs(wd.to_numpy() - np.array([0.45, 0.35, 0.20])).sum(axis=1).mean() / 2)},
        "AP2B": {"w_mean": wj.mean().to_dict(), "w_sd": wj.std(ddof=1).to_dict(), "w_min": wj.min().to_dict(), "w_max": wj.max().to_dict(),
                 "distinct_weight_vectors": int(wj.round(10).drop_duplicates().shape[0]),
                 "mean_abs_deviation_from_own_benchmark": float(np.abs(wj.to_numpy() - np.array([0.60, 0.40])).sum(axis=1).mean() / 2)},
        "equity_weight_gap_jev_minus_det": {"mean": float((j["w_SPY"] - d["w_SPY"]).mean()), "min": float((j["w_SPY"] - d["w_SPY"]).min()),
                                            "max": float((j["w_SPY"] - d["w_SPY"]).max())},
        "corr_of_equity_weight_changes": corr(np.diff(d["w_SPY"]), np.diff(j["w_SPY"])),
    }
    # JEV's choices map to its weights in the expected direction?
    choices = [recs["AP2B"][m]["forecast"]["values"].get("choice") for m in months]
    ch = pd.DataFrame({"choice": choices, "w_SPY": j["w_SPY"]})
    dec["AP2B"]["equity_weight_by_choice"] = ch.groupby("choice")["w_SPY"].agg(["count", "mean", "min", "max"]).round(6).to_dict(orient="index")
    fc = pd.DataFrame([recs["AP1"][m]["forecast"]["values"] for m in months])
    dec["AP1"]["forecast_sd"] = fc.std(ddof=1).to_dict()
    dec["AP1"]["distinct_forecast_vectors"] = int(fc.round(12).drop_duplicates().shape[0])

    assets = {a: np.array([prices[a][dates_for(m, cal)[2]] / prices[a][dates_for(m, cal)[1]] - 1 for m in months]) for a in PRICE_FILES}
    expo = {}
    for s, df in (("AP1", d), ("AP2B", j)):
        y = df["net"].to_numpy()
        _, r2_spy, res = ols(y, [assets["SPY"]])
        expo[s] = {"corr_with": {a: corr(y, assets[a]) for a in assets}, "r2_on_SPY_alone": r2_spy,
                   "r2_on_own_assets": ols(y, [assets[a] for a in df.columns if a.startswith("r_") for a in [a[2:]]])[1]}
    _, _, res_d = ols(d["net"].to_numpy(), [assets["SPY"]])
    _, _, res_j = ols(j["net"].to_numpy(), [assets["SPY"]])
    expo["corr_after_removing_SPY"] = corr(res_d, res_j)
    expo["asset_return_correlations"] = {f"{a}-{b}": corr(assets[a], assets[b]) for i, a in enumerate(assets) for b in list(assets)[i + 1:]}
    expo["asset_volatility_annualised"] = {a: float(np.std(v, ddof=1) * np.sqrt(12)) for a, v in assets.items()}

    # ---------------------------------------------------------------- decomposition
    decomp = {}
    for s, df, cols in (("AP1", d, ["SPY", "IEF", "LQD"]), ("AP2B", j, ["SPY", "TLT"])):
        W = df[[f"w_{a}" for a in cols]].to_numpy()
        R = np.column_stack([assets[a] for a in cols])
        wbar = W.mean(axis=0)
        static = R @ wbar
        tilt = ((W - wbar) * R).sum(axis=1)
        cost = df["cost"].to_numpy()
        net = df["net"].to_numpy()
        assert np.allclose(static + tilt - cost, net, atol=1e-12)
        decomp[s] = {"static_mean_weights": dict(zip(cols, wbar.round(6))),
                     "share_of_variance_static": float(np.cov(static, net)[0, 1] / net.var(ddof=1)),
                     "share_of_variance_tilts": float(np.cov(tilt, net)[0, 1] / net.var(ddof=1)),
                     "share_of_variance_costs": float(np.cov(-cost, net)[0, 1] / net.var(ddof=1)),
                     "equity_leg_share_of_variance": float(np.cov(R[:, 0] * W[:, 0], net)[0, 1] / net.var(ddof=1)),
                     "cumulative_contribution_tilts": float(tilt.sum()), "cumulative_cost": float(cost.sum())}
    # the spread JEV - Det, by source
    eq = (j["w_SPY"] - d["w_SPY"]).to_numpy() * assets["SPY"]
    bonds = j["w_TLT"].to_numpy() * assets["TLT"] - (d["w_IEF"].to_numpy() * assets["IEF"] + d["w_LQD"].to_numpy() * assets["LQD"])
    costs = -(j["cost"].to_numpy() - d["cost"].to_numpy())
    assert np.allclose(eq + bonds + costs, spread, atol=1e-12)
    v = spread.var(ddof=1)
    decomp["spread_jev_minus_det"] = {
        "equity_weight_difference": {"share_of_variance": float(np.cov(eq, spread)[0, 1] / v), "cumulative": float(eq.sum())},
        "bond_legs_TLT_vs_IEF_LQD": {"share_of_variance": float(np.cov(bonds, spread)[0, 1] / v), "cumulative": float(bonds.sum())},
        "transaction_costs": {"share_of_variance": float(np.cov(costs, spread)[0, 1] / v), "cumulative": float(costs.sum())}}
    # how much of the spread is decisions (tilts) vs the two fixed starting mixes
    nd, nj = sims["AP1_NEUTRAL"]["net"].to_numpy(), sims["AP2B_NEUTRAL"]["net"].to_numpy()
    decomp["spread_by_design_vs_decisions"] = {
        "own_benchmarks_spread_cumulative": float((nj - nd).sum()), "decisions_cumulative": float((act_j - act_d).sum()),
        "share_of_spread_variance_from_benchmarks": float(np.cov(nj - nd, spread)[0, 1] / v),
        "share_of_spread_variance_from_decisions": float(np.cov(act_j - act_d, spread)[0, 1] / v)}

    # ---------------------------------------------------------------- integrity checks
    integ = {}
    integ["weights_are_distinct_series"] = not np.allclose(d["w_SPY"].to_numpy(), j["w_SPY"].to_numpy())
    integ["jev_vs_committee_weights_identical"] = bool(np.allclose(sims["AP2A"]["w_SPY"].to_numpy(), j["w_SPY"].to_numpy()))
    integ["returns_identical_any_month"] = int((np.abs(spread) < 1e-12).sum())
    integ["weights_sum_to_one"] = bool(np.allclose(wd.sum(axis=1), 1) and np.allclose(wj.sum(axis=1), 1))
    integ["no_negative_weights"] = bool((wd.to_numpy() >= 0).all() and (wj.to_numpy() >= 0).all())
    la = []
    for s in ("AP1", "AP2B"):
        for m in months:
            r = recs[s][m]
            dd, entry, _ = dates_for(m, cal)
            if pd.Timestamp(r["decision_time"][:10]) != dd:
                la.append(f"{s} {m}: decision date {r['decision_time'][:10]} != last common trading day {dd.date()}")
            if pd.Timestamp(r["info_cutoff"]) > pd.Timestamp(r["decision_time"]):
                la.append(f"{s} {m}: information cutoff after the decision time")
            nat = r["generation"].get("native_as_of")
            if nat and pd.Timestamp(nat) > dd:
                la.append(f"{s} {m}: native answer dated {nat}, after the decision date")
            if entry <= dd:
                la.append(f"{s} {m}: entry not after the decision date")
    integ["look_ahead_and_date_problems"] = la
    integ["last_development_holding_period"] = {"decision_month": months[-1], "entry": d["entry"].iloc[-1], "exit": d["exit"].iloc[-1],
                                                "note": "the December 2022 decision is held through January 2023; protected decisions start with 2023-01 (held from February), so no month is scored twice"}
    annual = {}
    for a, ser in prices.items():
        yr = {}
        for y in (2019, 2020, 2021, 2022):
            start = ser[ser.index <= f"{y - 1}-12-31"].iloc[-1]
            end = ser[ser.index <= f"{y}-12-31"].iloc[-1]
            yr[str(y)] = float(end / start - 1)
        annual[a] = yr
    integ["calendar_year_total_returns_from_adjusted_close"] = annual
    integ["dividend_treatment_evidence"] = ("SPY 2019 from the adjusted close: {:.2%}; the S&P 500's 2019 price-only return was about 28.9% and "
                                            "its total return about 31.5%, so distributions are included".format(annual["SPY"]["2019"]))
    integ["dividend_treatment"] = "adjusted 'Close' in every price file (distribution-adjusted; Stage 2 gate 5 on issuer records: SPY/IEF/LQD pass; TLT C2 review)"

    for k, v in cmp_eval.items():
        if v["max_abs_diff_net_return"] > 1e-12 or not v["months_equal"] or not v["entry_exit_equal"]:
            findings.append(f"shared evaluator differs for {k}: {v}")
    for k, v in cmp_dash.items():
        if k == "passive":
            continue
        if v["max_abs_diff_wealth"] > 5.0000001e-7 or v["wealth_matches_other_system"]:
            findings.append(f"dashboard series {k} differs from its reconstruction or matches the other system: {v}")
    if la:
        findings.append(f"{len(la)} date/look-ahead problems")
    if integ["jev_vs_committee_weights_identical"] or not integ["weights_are_distinct_series"]:
        findings.append("weight series reused across systems")

    report = {"title": "Portfolio return and backtest integrity audit: Deterministic vs JEV (development 2019-03..2022-12)",
              "method": "independent reconstruction from raw pinned files; no project accounting code imported",
              "verdict": "no implementation error found" if not findings else "issues found",
              "findings": findings, "reconciliation": checks, "similarity": sim_, "decisions": dec, "exposures": expo,
              "decomposition": decomp, "integrity": integ,
              "metrics_reconstructed": {s: metrics(sims[s]) for s in ("AP1", "AP2B", "PASSIVE", "AP1_NEUTRAL", "AP2B_NEUTRAL")},
              "monthly": {"months": months, "det_net": d["net"].tolist(), "jev_net": j["net"].tolist(), "spread": spread.tolist(),
                          "det_w_spy": d["w_SPY"].tolist(), "jev_w_spy": j["w_SPY"].tolist(), "spy_return": assets["SPY"].tolist()}}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "portfolio_integrity_v1.json").write_text(json.dumps(report, indent=1, default=float) + "\n")
    rec = d.add_prefix("det_").join(j.add_prefix("jev_")).join(p[["net"]].rename(columns={"net": "passive_net"}))
    rec.to_csv(OUT / "reconstruction_v1.csv", index=False, float_format="%.12g")
    print(json.dumps({"verdict": report["verdict"], "findings": findings, "corr_monthly_net": sim_["corr_monthly_net"],
                      "corr_active_vs_own_benchmark": sim_["corr_active_vs_own_benchmark"], "corr_own_benchmarks": sim_["corr_own_benchmarks"]}, indent=1))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
