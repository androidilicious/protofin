"""Freeze gate 5 tests (stage2/methodology/Stage2_Dividend_Adjustment_Gate_v1.md).

Synthetic tests always run. They show that C2-C5 accept a correctly adjusted
series and reject price-only and double-counted series. The real-data test runs
the gate against the official issuer records and the scorer's pinned prices,
and skips only if the pinned prices have not been fetched.
"""
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import check_dividend_adjustment as cda

REPO = Path(__file__).resolve().parents[2]


def _synthetic(mode: str, seed: int = 7, skip_factor_at=None):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2013-11-01", "2023-02-01")
    ex_dates = pd.DatetimeIndex([dates[dates.to_period("M") == m][0] for m in pd.period_range("2014-01", "2023-02", freq="M")])
    close = np.empty(len(dates))
    close[0] = 100.0
    div = {}
    for i in range(1, len(dates)):
        close[i] = close[i - 1] * (1 + 0.004 * rng.standard_normal())
        if dates[i] in ex_dates:
            div[dates[i]] = round(0.003 * close[i - 1], 6)
            close[i] -= div[dates[i]]
    close = np.round(close, 2)
    c = pd.Series(close, index=dates)
    mult = {"correct": 1.0, "price_only": 0.0, "double": 2.0}[mode]
    factor = pd.Series(1.0, index=dates)
    for ex, d in div.items():
        if skip_factor_at is not None and ex == skip_factor_at:
            continue
        prev = dates[dates.get_loc(ex) - 1]
        factor[dates <= prev] *= 1 - mult * d / c[prev]
    adj = (c * factor).round(2)
    nav = c * (1 + 0.0002 * rng.standard_normal(len(dates)))
    hi = c * (1 + np.abs(0.002 * rng.standard_normal(len(dates))))
    lo = c * (1 - np.abs(0.002 * rng.standard_normal(len(dates))))
    at_hi, at_lo = rng.random(len(dates)) < 0.25, rng.random(len(dates)) < 0.25
    hi[at_hi], lo[at_lo] = c[at_hi], c[at_lo]
    raw = pd.DataFrame({"High": np.round(hi, 2), "Low": np.round(lo, 2), "adj": adj})
    raw["High"] = np.maximum(raw["High"], c)
    raw["Low"] = np.minimum(raw["Low"], c)
    raw = raw[raw.index >= "2018-01-02"]
    dist = pd.DataFrame({"ticker": "X", "ex_date": list(div), "distribution_per_share": list(div.values())})
    pairs = pd.DataFrame({"ticker": "X", "ex_date": list(div),
                          "prev_nav_date": [dates[dates.get_loc(e) - 1] for e in div],
                          "nav_prev": [nav.iloc[dates.get_loc(e) - 1] for e in div], "nav_ex": [nav[e] for e in div]})
    me = nav.groupby(nav.index.to_period("M")).tail(1)
    months = me.index.to_period("M")
    dp = dist.merge(pairs, on=["ticker", "ex_date"])
    y_m = np.log1p(dp.distribution_per_share / dp.nav_ex).groupby(dp.ex_date.dt.to_period("M")).sum()
    monthly = pd.DataFrame({"month": months[1:], "p": np.log(me.to_numpy()[1:] / me.to_numpy()[:-1]),
                            "y": y_m.reindex(months[1:]).fillna(0).to_numpy()})
    return adj, raw, dist, pairs, monthly


@pytest.mark.parametrize("mode", ["correct", "price_only", "double"])
def test_gate_criteria_on_synthetic_series(mode):
    adj, raw, dist, pairs, monthly = _synthetic(mode)
    per, mon, s = cda.check_ticker("X", adj, raw, dist, pairs, monthly)
    assert s["C1_coverage"]["pass"]
    expected = mode == "correct"
    for c in ("C2_ex_date_capture", "C3_monthly_capture", "C4_cumulative_capture", "C5_implied_distribution", "C6_informative_nav"):
        assert s[c]["pass"] is expected, (mode, c, s[c])
    assert s["pass"] is expected
    if mode == "correct":
        assert abs(s["C2_ex_date_capture"]["kappa"] - 1) < 0.05


def test_missing_ex_date_in_series_fails_coverage():
    adj, raw, dist, pairs, monthly = _synthetic("correct")
    ex = dist.ex_date.iloc[50]
    per, mon, s = cda.check_ticker("X", adj.drop(ex), raw.drop(ex, errors="ignore"), dist, pairs, monthly)
    assert not s["C1_coverage"]["pass"]


def test_single_missed_distribution_is_caught_by_c5():
    adj, raw, dist, pairs, monthly = _synthetic("correct")
    ex = dist.ex_date[dist.ex_date >= "2019-01-01"].iloc[0]
    adj, raw, dist, pairs, monthly = _synthetic("correct", skip_factor_at=ex)
    per, mon, s = cda.check_ticker("X", adj, raw, dist, pairs, monthly)
    row = per[per.ex_date == ex.date().isoformat()].iloc[0]
    assert str(row["c5_status"]).startswith("FAIL")
    assert not s["pass"]


@pytest.mark.skipif(not (REPO / "stage2/data/_pinned/market_price_SPY_2018plus.tsv").exists(),
                    reason="Pinned price inputs not fetched (run stage2/scoring/fetch_pinned_inputs.py)")
def test_official_records_gate(tmp_path):
    cwd = os.getcwd()
    os.chdir(REPO)
    try:
        status = cda.run(Path("stage2/scoring/stage2_run_spec_dev_v4.json"), cda.DATA_DIR, tmp_path)
    finally:
        os.chdir(cwd)
    failed = {s["ticker"]: [k for k in s if k.startswith("C") and not s[k]["pass"]] for s in status["by_ticker"]}
    assert status["status"] == "PASS", failed
