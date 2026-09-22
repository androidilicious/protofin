"""Backtest harness for the Protofin allocation policy.

Runs several strategies through the SAME allocation code the dashboard uses (allocation.py),
on identical dates, prices and transaction costs, so their differences isolate the policy.

    python research/backtest.py                      # 2004-01 to today, monthly, 5 bps one-way
    python research/backtest.py --start 2010-01-01 --cost-bps 10 --rebalance W

Strategies
  fixed_60_40      Rebalance to 60/40 on every rebalance date (the naive benchmark)
  prior_only       Equilibrium prior only -> constrained optimizer -> trade policy
                   (no views; shows what the hold band and move cap do on their own)
  rate_shock_rule  Deterministic placeholder views driven by the 10Y-vs-3-month shock.
                   NOT a validated signal; it exists so a signal can be compared to none.
  rate_shock_gated Same rule views, but confidence is downgraded one notch when the EPU/GPR
                   uncertainty regime is "elevated" (top decile of either index, or top
                   quintile of both, on 30-day means vs 10 years of history).
  logged_llm       Replays views recorded in runs/pipeline_log.jsonl on the dates they were
                   made (forward test). Dates without a logged view fall back to prior_only.
  logged_llm_gated Logged views with the same uncertainty gate applied.
  masked_llm       Views from research/masked_replay.py (--views-file), the masked historical
                   replay of the LLM committee; masked_llm_gated applies the uncertainty gate.

What this backtest cannot do
  * Historical LLM views: there is no point-in-time news archive here, and any current LLM has
    read the history it would be forecasting. Only the forward log is an honest LLM test.
  * Market impact and financing: costs are a flat per-unit-turnover charge.
  * EPU and GPR are as published today; the authors revise history, so the regime flag is
    point-in-time in construction but not in data vintage.
Outputs: research/out/backtest_summary.csv, research/out/backtest_curves.csv,
         research/out/backtest_weights.csv
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from allocation import EQUILIBRIUM_SPY, allocate  # noqa: E402
import macro_indexes  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "research", "out")
LOG_PATH = os.path.join(BASE, "runs", "pipeline_log.jsonl")
COV_WINDOW = 252       # trailing days for covariance (matches server: 1y)
SHOCK_WINDOW = 63      # trailing days for the 10Y average (matches server: 3mo)


# ------------------------------------------------------------------ data
def load_prices(start):
    raw = yf.download(["SPY", "TLT", "^TNX", "^IRX"], start="2002-07-01", auto_adjust=True,
                      progress=False)["Close"]
    raw = raw.rename(columns={"^TNX": "TNX", "^IRX": "IRX"})
    raw[["TNX", "IRX"]] = raw[["TNX", "IRX"]].ffill()
    raw = raw.dropna()
    return raw[raw.index >= pd.Timestamp("2002-07-01")], raw[raw.index >= pd.Timestamp(start)]


def rebalance_dates(index, freq):
    """Last trading day of each period ('M' month, 'W' week, 'Q' quarter)."""
    rule = {"M": "ME", "W": "W-FRI", "Q": "QE"}[freq]
    return index.to_series().groupby(index.to_period({"M": "M", "W": "W", "Q": "Q"}[freq])).last().values


# ------------------------------------------------------------------ views
def load_logged_views():
    """Date -> (views_total_pct, confidence) from the live pipeline log."""
    views = {}
    if not os.path.exists(LOG_PATH):
        return views
    with open(LOG_PATH, encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            if rec.get("llm_parse_ok"):
                views[pd.Timestamp(rec["as_of"])] = ([rec["spy_q"], rec["tlt_q"]], rec["confidence"])
    return views


def load_views_csv(path):
    """Date -> (views_total_pct, confidence) from a CSV with date, spy_q, tlt_q, confidence."""
    df = pd.read_csv(path, parse_dates=["date"])
    return {pd.Timestamp(r.date): ([float(r.spy_q), float(r.tlt_q)], str(r.confidence)) for r in df.itertuples()}


def rate_shock_views(shock_bps, rf_pct):
    """Placeholder rule: a large hawkish shock is read as bearish bonds, dovish as bullish bonds.
    Views are TOTAL 12m returns; the allocator converts them to excess over cash."""
    if shock_bps > 25:
        return [rf_pct + 3.0, rf_pct - 2.0], "Medium"
    if shock_bps < -25:
        return [rf_pct + 2.0, rf_pct + 4.0], "Medium"
    return None, "Medium"


# ------------------------------------------------------------------ engine
def run_strategy(name, full, window, rdates, cost, logged, regimes, masked=None):
    """Daily simulation with drifting weights; decisions only on rebalance dates."""
    rets = full[["SPY", "TLT"]].pct_change()
    dates = window.index
    w = np.array([EQUILIBRIUM_SPY, 1 - EQUILIBRIUM_SPY])   # start at 60/40
    nav, weights, trades, rows = 1.0, [], 0, []
    turnover_total, cost_total = 0.0, 0.0
    rset = set(pd.Timestamp(d) for d in rdates)

    for d in dates:
        r = rets.loc[d].values
        # drift through the day
        gross = w * (1 + r)
        day_ret = gross.sum() - 1
        nav *= 1 + day_ret
        w = gross / gross.sum()

        if d in rset:
            hist = full.loc[:d]
            if len(hist) < COV_WINDOW + 5:
                weights.append((d, w[0], nav, 0.0, "warmup")); continue
            sigma = hist[["SPY", "TLT"]].iloc[-COV_WINDOW:].pct_change().dropna().cov().values * 252
            rf = float(hist["IRX"].iloc[-1])
            shock = float((hist["TNX"].iloc[-1] - hist["TNX"].iloc[-SHOCK_WINDOW:].mean()) * 100)

            if name == "fixed_60_40":
                new_spy, status = EQUILIBRIUM_SPY, "rebalanced to 60/40"
            else:
                base = {"rate_shock_gated": "rate_shock_rule", "logged_llm_gated": "logged_llm",
                        "masked_llm_gated": "masked_llm"}.get(name, name)
                if base == "prior_only":
                    views, conf = None, "Medium"
                elif base == "rate_shock_rule":
                    views, conf = rate_shock_views(shock, rf)
                elif base == "logged_llm":
                    views, conf = logged.get(d, (None, "Medium"))
                elif base == "masked_llm":
                    views, conf = (masked or {}).get(d, (None, "Medium"))
                else:
                    raise ValueError(name)
                if name.endswith("_gated"):
                    regime = regimes.get(d, "normal")
                    conf = macro_indexes.downgrade_confidence(conf, regime)
                dec = allocate(sigma, views, conf, rf, previous_spy=float(w[0]))
                new_spy, status = dec["final_spy"], dec["status"]

            new_w = np.array([new_spy, 1 - new_spy])
            turnover = float(np.abs(new_w - w).sum() / 2)      # one-way turnover
            if turnover > 1e-9:
                trades += 1
                c = turnover * cost
                nav *= 1 - c
                cost_total += c
                turnover_total += turnover
            w = new_w
            weights.append((d, w[0], nav, turnover, status))
        rows.append((d, nav, w[0]))

    curve = pd.DataFrame(rows, columns=["date", "nav", "spy_w"]).set_index("date")
    wdf = pd.DataFrame(weights, columns=["date", "spy_w", "nav", "turnover", "status"]).set_index("date")
    return curve, wdf, trades, turnover_total, cost_total


def metrics(curve, rf_daily):
    r = curve["nav"].pct_change().dropna()
    years = (curve.index[-1] - curve.index[0]).days / 365.25
    cagr = curve["nav"].iloc[-1] ** (1 / years) - 1
    vol = r.std() * np.sqrt(252)
    excess = r - rf_daily.reindex(r.index).fillna(0)
    sharpe = excess.mean() / excess.std() * np.sqrt(252) if excess.std() > 0 else np.nan
    dd = (curve["nav"] / curve["nav"].cummax() - 1).min()
    return cagr, vol, sharpe, dd


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2004-01-01")
    ap.add_argument("--rebalance", default="M", choices=["W", "M", "Q"])
    ap.add_argument("--cost-bps", type=float, default=5.0, help="one-way cost per unit turnover")
    ap.add_argument("--strategies",
                    default="fixed_60_40,prior_only,rate_shock_rule,rate_shock_gated,logged_llm")
    ap.add_argument("--views-file", default=None,
                    help="CSV of dated views (from masked_replay.py); enables masked_llm strategies")
    args = ap.parse_args()

    full, window = load_prices(args.start)
    rdates = rebalance_dates(window.index, args.rebalance)
    cost = args.cost_bps / 1e4
    logged = load_logged_views()
    masked = load_views_csv(args.views_file) if args.views_file else None
    if masked:
        print(f"masked views loaded: {len(masked)} dates")
    rf_daily = (window["IRX"] / 100) / 252
    try:
        reg = macro_indexes.regime_series(macro_indexes.load_all())["regime"]
        regimes = reg.reindex(window.index, method="ffill").to_dict()
        print(f"uncertainty regime elevated on {sum(v == 'elevated' for v in regimes.values())} of "
              f"{len(regimes)} days")
    except Exception as exc:
        print("uncertainty indexes unavailable, gated strategies run ungated:", exc)
        regimes = {}

    os.makedirs(OUT, exist_ok=True)
    summary, curves, wtabs = [], {}, {}
    for name in args.strategies.split(","):
        curve, wdf, trades, turn, cst = run_strategy(name, full, window, rdates, cost, logged, regimes, masked)
        cagr, vol, sharpe, dd = metrics(curve, rf_daily)
        curves[name] = curve["nav"]
        wtabs[name] = curve["spy_w"]
        held = int((wdf["status"].str.startswith("held")).sum())
        summary.append({"strategy": name, "CAGR_%": round(cagr * 100, 2), "Vol_%": round(vol * 100, 2),
                        "Sharpe": round(sharpe, 2), "MaxDD_%": round(dd * 100, 2),
                        "trades": trades, "held_decisions": held,
                        "turnover_total_%": round(turn * 100, 1), "cost_drag_total_%": round(cst * 100, 2),
                        "avg_SPY_w_%": round(curve["spy_w"].mean() * 100, 1),
                        "views_available": (len(logged) if name.startswith("logged_llm") else
                                            len(masked or {}) if name.startswith("masked_llm") else None)})

    sdf = pd.DataFrame(summary).set_index("strategy")
    sdf.to_csv(os.path.join(OUT, "backtest_summary.csv"))
    pd.DataFrame(curves).to_csv(os.path.join(OUT, "backtest_curves.csv"))
    pd.DataFrame(wtabs).to_csv(os.path.join(OUT, "backtest_weights.csv"))

    print(f"Window {window.index[0].date()} -> {window.index[-1].date()} | rebalance {args.rebalance} "
          f"| cost {args.cost_bps:.0f} bps one-way | {len(rdates)} decision dates")
    print(sdf.to_string())
    print(f"\nlogged LLM views available: {len(logged)} date(s)")
    print(f"outputs -> {OUT}")


if __name__ == "__main__":
    main()
