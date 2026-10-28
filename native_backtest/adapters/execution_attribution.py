"""External evaluation adapter for the two-asset AP2 systems: native -> common execution, step by step.

The system's decisions (target SPY weights) are held fixed. Only evaluation assumptions change, one at
a time, so the effect of each adjustment is visible:

  V0 native            native returns (backtest_months.json r_spy/r_tlt, month-end close to close),
                       trade at the decision close, 5 bp per unit of SPY-weight change applied
                       multiplicatively, start at 60/40 with no cost, native cash (rf_pct)
  V1 pinned prices     as V0 but returns from the pinned, shared price files (same closes)
  V2 next-day trade    as V1 but executed at the next trading day's close (common timing)
  V3 common costs      as V2 but 5 bp per dollar traded, additive, starting from cash (Stage 2 rule)
  V4 common cash       as V3 but excess returns over DTB4WK accrued from entry = COMMON EVALUATION

Development months only (decision months up to 2022-12).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np
import pandas as pd

from native_backtest.framework import metrics as M
from native_backtest.framework.market import Market
from native_backtest.adapters import ap2_native as a

ROOT = Path(__file__).resolve().parents[2]


def _native_months() -> Dict[str, dict]:
    raw = json.loads((a.A2 / "site/data/backtest_months.json").read_text())["months"]
    return {m["as_of"]: m for m in raw}


def _summarise(name: str, net_total: np.ndarray, rf: np.ndarray, turnover: float, months: List[str]) -> dict:
    ex = net_total - rf
    sim = pd.DataFrame({"net_excess_return": ex, "net_total_return": net_total, "one_way_turnover": np.r_[turnover / len(ex) * np.ones(len(ex))], "cost": np.zeros(len(ex))})
    out = M.metrics(sim)
    out = {k: out[k] for k in ("n_months", "net_annualized_excess_return", "annualized_volatility", "net_sharpe", "max_drawdown", "cer_delta_2_5")}
    out["total_one_way_turnover"] = float(turnover)
    out["variant"] = name
    out["first_month"], out["last_month"] = months[0], months[-1]
    return out


def run_variants(weights_by_asof: Dict[str, float], market: Market, months: Sequence[pd.Period]) -> List[dict]:
    nat = _native_months()
    asof = {pd.Timestamp(k).to_period("M"): k for k in nat}
    sel = [m for m in months if m in asof]
    keys = [asof[m] for m in sel]
    w = np.array([weights_by_asof[k] for k in keys])
    names = [str(m) for m in sel]
    results = []

    def native_path(r_spy, r_tlt, rf, start=0.60, cost=5e-4):
        nav_ret, prev, turn_total = [], start, 0.0
        for t, rs, rt in zip(w, r_spy, r_tlt):
            turn = abs(t - prev)
            ret = t * rs + (1 - t) * rt
            net = (1 - turn * cost) * (1 + ret) - 1 if turn > 1e-9 else ret
            nav_ret.append(net)
            turn_total += turn
            prev = t * (1 + rs) / (1 + ret)
        return np.array(nav_ret), turn_total

    rf_native = np.array([(1 + nat[k]["rf_pct"] / 100) ** (1 / 12) - 1 for k in keys])
    # V0 native
    r0s = np.array([nat[k]["r_spy"] for k in keys]); r0t = np.array([nat[k]["r_tlt"] for k in keys])
    v0, t0 = native_path(r0s, r0t, rf_native)
    results.append(_summarise("V0 native", v0, rf_native, t0, names))
    # V1 pinned prices, same-close
    p = market.prices
    r1s, r1t = [], []
    for m in sel:
        d0, d1 = market.decision_dates[m], market.decision_dates[m + 1]
        if m < market.scorable_from:
            raise ValueError(f"{m} is before the pinned-price validity start {market.scorable_from}")
        r1s.append(float(p["SPY"].loc[d1] / p["SPY"].loc[d0] - 1)); r1t.append(float(p["TLT"].loc[d1] / p["TLT"].loc[d0] - 1))
    v1, t1 = native_path(np.array(r1s), np.array(r1t), rf_native)
    results.append(_summarise("V1 pinned prices (same close)", v1, rf_native, t1, names))
    # V2 next-day execution
    r2 = [market.period_returns(m, ["SPY", "TLT"]) for m in sel]
    r2s = np.array([x["SPY"] for x in r2]); r2t = np.array([x["TLT"] for x in r2])
    v2, t2 = native_path(r2s, r2t, rf_native)
    results.append(_summarise("V2 + next-trading-day execution", v2, rf_native, t2, names))
    # V3 common costs: 5 bp per dollar traded (sum of |dw| over both assets), additive, from cash
    pre = np.zeros(2); v3, notional_total = [], 0.0
    for t, rs, rt in zip(w, r2s, r2t):
        wt = np.array([t, 1 - t]); notional = float(np.abs(wt - pre).sum()); notional_total += notional
        gross = t * rs + (1 - t) * rt
        v3.append(gross - 5e-4 * notional)
        grown = wt * (1 + np.array([rs, rt])); pre = grown / grown.sum()
    v3 = np.array(v3)
    results.append(_summarise("V3 + common costs (5 bp per $ traded, from cash)", v3, rf_native, 0.5 * notional_total, names))
    # V4 common cash
    rf_dtb = np.array([market.rf_return(m) for m in sel])
    results.append(_summarise("V4 + DTB4WK cash = common evaluation", v3, rf_dtb, 0.5 * notional_total, names))
    for i in range(1, len(results)):
        results[i]["delta_cer_vs_previous"] = results[i]["cer_delta_2_5"] - results[i - 1]["cer_delta_2_5"]
    return results
