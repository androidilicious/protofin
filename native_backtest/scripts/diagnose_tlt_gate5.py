#!/usr/bin/env python3
"""Diagnose the TLT gate 5 C2 result: market-close prices vs NAV vs ex-dividend adjustment.

Gate 5 criterion C2 compares, on each ex-date, the adjusted market-price move with the official NAV move
plus the distribution. Its numerator therefore contains two things: any error in the distribution
adjustment, and the day's change in the ETF's premium/discount to NAV. This script separates them using
iShares' official daily NAV history (2013-12-31..2023-02-01; captured in the browser, hash-verified):

1. daily residual r_t = dlog(adjusted close) - dlog(NAV) - [ex-date] log(1 + D/NAV_ex)
   On days without a distribution r_t is purely the change in the premium (the adjustment factor is
   constant between ex-dates); on ex-dates it is the premium change plus any adjustment error.
2. turn-of-month comparison: ex-dates are almost all the first trading day of the month, so the ex-date
   residual is compared with first-trading-day residuals that carry no distribution, and with other days;
3. cumulative tracking: log(adjusted close / official NAV total-return index) over 2014-2023. A missing or
   double-counted distribution would accumulate (about 19 bp per month); the premium alone is bounded;
4. materiality: JEV and the Committee re-scored on development months with TLT returns taken from the
   official NAV total-return index instead of market prices (premium removed entirely).

None of this changes the pre-registered gate; it explains its result. Outputs go to
native_backtest/out/tlt_dividend_gate/diagnosis.json. Usage: python -m native_backtest.scripts.diagnose_tlt_gate5
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from native_backtest.framework import metrics as M
from native_backtest.framework.accounting import simulate_records, static_portfolio_records
from native_backtest.framework.lock import assert_scoring_allowed
from native_backtest.framework.market import load_config, load_market, months_between
from native_backtest.framework.records import read_jsonl

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "native_backtest/data/tlt_dividend_check/raw_capture"
DATA = ROOT / "native_backtest/data/tlt_dividend_check"
OUT = ROOT / "native_backtest/out/tlt_dividend_gate/diagnosis.json"
NAV_SHA = {"TLT_daily_nav_part0.txt": "a9bc7685c09ba6974cc65b54ad3e2ea92e42e1ca4dd63b6b4ea70669b7ec5340",
           "TLT_daily_nav_part1.txt": "f2410acd542acdb53af68d37313794dfe077b692095878fcdfb03aa5f4f7cf12",
           "TLT_daily_nav_part2.txt": "3f5216fbc716b13525fc98fabc0da34939a65ae51bd2f6343fa16a9dd820c986"}
LAST = pd.Timestamp("2023-02-01")


def load_nav() -> pd.Series:
    rows = []
    for name, sha in NAV_SHA.items():
        b = (RAW / name).read_bytes().rstrip(b"\n")
        if hashlib.sha256(b).hexdigest() != sha:
            raise SystemExit(f"STOP: {name} differs from its browser-side SHA-256")
        rows += [line.split(",") for line in b.decode().split("\n")]
    s = pd.Series([float(v) for _, v in rows], index=pd.to_datetime([d for d, _ in rows], format="%Y%m%d"))
    if s.index.duplicated().any():
        raise SystemExit("duplicate NAV dates")
    return s.sort_index()


def stats(x: pd.Series) -> dict:
    x = x.dropna()
    n = len(x)
    return {"n": n, "mean_bp": 1e4 * float(x.mean()), "sd_bp": 1e4 * float(x.std(ddof=1)),
            "se_bp": 1e4 * float(x.std(ddof=1) / math.sqrt(n)) if n > 1 else None,
            "t": float(x.mean() / (x.std(ddof=1) / math.sqrt(n))) if n > 1 and x.std(ddof=1) > 0 else None}


def main() -> int:
    nav = load_nav()
    dist = pd.read_csv(DATA / "official_distributions_TLT.csv", parse_dates=["ex_date"]).set_index("ex_date")["distribution_per_share"]
    cfg = load_config()
    mk = load_market(cfg)
    adj = mk.prices["TLT"]
    adj = adj[(adj.index >= nav.index[0]) & (adj.index <= LAST)]
    common = adj.index.intersection(nav.index)
    only_mkt, only_nav = adj.index.difference(nav.index), nav.index.difference(adj.index)
    a, n = adj.reindex(common), nav.reindex(common)
    da, dn = np.log(a).diff(), np.log(n).diff()
    y = pd.Series(0.0, index=common)
    for d, D in dist.items():
        if d in y.index:
            y.loc[d] = math.log(1 + D / n.loc[d])
    r = (da - dn - y).iloc[1:]
    is_ex = pd.Series(common.isin(dist.index), index=common).iloc[1:]
    month = pd.Series(common.to_period("M"), index=common)
    ftd = (month != month.shift(1)).iloc[1:]  # first trading day of each month
    lag1 = float(r.autocorr(1))

    # 3. cumulative tracking vs official NAV total-return index (distribution reinvested at the ex-date NAV)
    tr = np.exp((dn + y).fillna(0.0).cumsum())
    track = np.log(a / a.iloc[0]) - np.log(tr / tr.iloc[0])
    by_year = track.groupby(track.index.year).agg(["min", "max", "last"])

    # C2 under the same formula, and how much of its excess the turn-of-month premium move accounts for
    ex_r, ex_y = r[is_ex], y.reindex(r.index)[is_ex]
    kappa = 1 + ex_r.mean() / ex_y.mean()
    ftd_noex = r[ftd & ~is_ex]
    other = r[~ftd & ~is_ex]
    ex_ftd = r[is_ex & ftd]
    ex_mid = r[is_ex & ~ftd]

    # 4. materiality: development months re-scored with TLT = official NAV total-return index
    months = months_between(*cfg["windows"]["development"])
    assert_scoring_allowed(months, protected_start=cfg["windows"]["protected"][0])
    nav_tr_px = pd.Series(tr.to_numpy() * float(a.iloc[0]), index=common)
    alt_prices = dict(mk.prices)
    alt_prices["TLT"] = nav_tr_px
    alt = dataclasses.replace(mk, prices=alt_prices)
    cost = cfg["costs"]["cost_per_dollar_traded"]
    mat = {}
    for sid, label in (("AP2B", "Agentic Workflow (JEV)"), ("AP2A", "Agent Committee (variant)")):
        recs = [x for x in read_jsonl(ROOT / f"native_backtest/out/decisions/{sid}.jsonl") if x.decision_month in {str(m) for m in months}]
        res = {}
        for name, market in (("pinned market prices", mk), ("official NAV total return", alt)):
            sim = simulate_records(recs, market, months, cost_per_dollar=cost)
            neu = simulate_records(static_portfolio_records(f"{sid}_N", cfg["systems"][sid]["native_neutral_weights"], recs), market, months, cost_per_dollar=cost)
            mm = M.metrics(sim)
            res[name] = {"net_cer": mm["cer_delta_2_5"], "net_sharpe": mm["net_sharpe"], "max_drawdown": mm["max_drawdown"],
                         "cer_vs_own_benchmark": M.cer(sim["net_excess_return"]) - M.cer(neu["net_excess_return"]) if "net_excess_return" in sim else None}
        res["difference_net_cer_pts"] = 100 * (res["official NAV total return"]["net_cer"] - res["pinned market prices"]["net_cer"])
        if res["pinned market prices"]["cer_vs_own_benchmark"] is not None:
            res["difference_vs_benchmark_pts"] = 100 * (res["official NAV total return"]["cer_vs_own_benchmark"] - res["pinned market prices"]["cer_vs_own_benchmark"])
        mat[label] = res

    out = {
        "inputs": {"official_daily_nav": {"first": str(nav.index[0].date()), "last": str(nav.index[-1].date()), "n": len(nav), "parts_sha256": NAV_SHA},
                   "calendar_mismatches": {"market_days_without_nav": [str(d.date()) for d in only_mkt][:20], "nav_days_without_market": [str(d.date()) for d in only_nav][:20]}},
        "daily_residual_all_days": {**stats(r), "lag1_autocorrelation": lag1},
        "ex_dates": {**stats(ex_r), "mean_distribution_bp": 1e4 * float(ex_y.mean()), "kappa_reproduced": float(kappa)},
        "ex_dates_first_trading_day": stats(ex_ftd),
        "ex_dates_mid_month": stats(ex_mid),
        "first_trading_day_without_distribution": stats(ftd_noex),
        "other_days": stats(other),
        "next_day_after_ex_date": stats(r.shift(-1)[is_ex]),
        "two_day_window_ex_kappa": float(1 + (ex_r + r.shift(-1)[is_ex]).mean() / ex_y.mean()),
        "cumulative_tracking_log_adjclose_over_navtr": {"start": 0.0, "end_pct": 100 * float(track.iloc[-1]), "min_pct": 100 * float(track.min()),
                                                        "max_pct": 100 * float(track.max()), "sd_pct": 100 * float(track.std()),
                                                        "by_year_pct": {int(k): {c: round(100 * float(v), 3) for c, v in row.items()} for k, row in by_year.iterrows()},
                                                        "accumulation_if_C2_excess_were_an_adjustment_error_pct": 100 * float((kappa - 1) * ex_y.sum())},
        "materiality_development_2019_03_2022_12": mat,
    }
    OUT.write_text(json.dumps(out, indent=1, default=float) + "\n")
    print(json.dumps(out, indent=1, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
