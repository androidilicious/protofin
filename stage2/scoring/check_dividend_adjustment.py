#!/usr/bin/env python3
"""Freeze gate 5: do the scorer's adjusted ETF prices include every official distribution?

Implements criteria C1-C6 of stage2/methodology/Stage2_Dividend_Adjustment_Gate_v1.md
against official issuer records (State Street for SPY; iShares for IEF and LQD).

Every price and NAV used is dated on or before 2023-02-01, the last price in the
development run. No historical-test-period data is read past that point.

Usage (repository root):
  python stage2/scoring/check_dividend_adjustment.py --spec stage2/scoring/stage2_run_spec_dev_v4.json
Exit code: 0 PASS, 2 FAIL, 3 inputs missing.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

TICKERS = ("SPY", "IEF", "LQD")
EX_START, LAST_DEV_PRICE = pd.Timestamp("2014-01-01"), pd.Timestamp("2023-02-01")
MONTHS = pd.period_range("2014-01", "2023-01", freq="M")
KAPPA_BAND, KAPPA_CUM_BAND, Z99 = (0.75, 1.25), (0.90, 1.10), 2.576
C5_WINDOW, ROUNDING = 10, 0.005
INFORMATIVE_SIGMAS = 6.0
DATA_DIR = Path("stage2/data/dividend_check")


# --------------------------------------------------------------------------- helpers
def robust_sd(x: np.ndarray) -> float:
    x = np.asarray(x, float)
    return float(1.4826 * np.median(np.abs(x - np.median(x))))


def capture_ratio(a_minus_p: np.ndarray, y: np.ndarray) -> Dict[str, float]:
    a_minus_p, y = np.asarray(a_minus_p, float), np.asarray(y, float)
    my = float(y.mean())
    kappa = float(a_minus_p.mean() / my)
    r = a_minus_p - y
    se = float(r.std(ddof=1) / math.sqrt(len(r)) / my)
    return {"kappa": kappa, "se": se, "ci99": [kappa - Z99 * se, kappa + Z99 * se], "n": int(len(r)),
            "mean_distribution_bp": 1e4 * my, "mean_residual_bp": 1e4 * float(r.mean())}


def kappa_ok(stat: Mapping[str, object], band=KAPPA_BAND) -> bool:
    lo, hi = stat["ci99"]
    return bool(band[0] <= stat["kappa"] <= band[1] and not (lo <= 0.0 <= hi) and not (lo <= 2.0 <= hi))


# --------------------------------------------------------------------------- C5 (no NAV)
def factor_interval(days: pd.DataFrame) -> Optional[tuple]:
    """Intersect F in [A/High, A/Low] over days; bounds widened for 2-decimal rounding of A."""
    if days.empty:
        return None
    lo = ((days["adj"] - ROUNDING) / days["High"]).max()
    hi = ((days["adj"] + ROUNDING) / days["Low"]).min()
    return (float(lo), float(hi))


def implied_fraction(raw: pd.DataFrame, ex: pd.Timestamp, prev_ex: Optional[pd.Timestamp],
                     next_ex: Optional[pd.Timestamp]) -> Dict[str, object]:
    idx = raw.index
    before = raw[(idx < ex) & ((idx >= prev_ex) if prev_ex is not None else True)].tail(C5_WINDOW)
    after = raw[(idx >= ex) & ((idx < next_ex) if next_ex is not None else True)].head(C5_WINDOW)
    fb, fa = factor_interval(before), factor_interval(after)
    out: Dict[str, object] = {"c5_days_before": len(before), "c5_days_after": len(after)}
    if fb is None or fa is None:
        out["c5_status"] = "FAIL: no window"
        return out
    if fb[0] > fb[1] or fa[0] > fa[1]:
        out["c5_status"] = "FAIL: adjustment factor not constant within window"
        return out
    lo, hi = 1.0 - fb[1] / fa[0], 1.0 - fb[0] / fa[1]
    out.update({"implied_fraction_lo": lo, "implied_fraction_hi": hi})
    return out


# --------------------------------------------------------------------------- loading
def load_inputs(spec_path: Path, data_dir: Path):
    import stage2_backtest as s2

    spec = s2.load_json(spec_path)
    adjusted = {t: s[s.index <= LAST_DEV_PRICE] for t, s in s2.load_market_prices(spec["prices"]).items()}
    raw = {}
    for t in TICKERS:
        seg = spec["prices"][t]["segments"][-1]
        f = pd.read_csv(Path(seg["path"]), sep=None, engine="python", parse_dates=["Date"]).set_index("Date")
        f = f[(f.index >= pd.Timestamp(seg["start_inclusive"])) & (f.index <= LAST_DEV_PRICE)]
        if not np.allclose(f["Close"].to_numpy(), adjusted[t].reindex(f.index).to_numpy(), rtol=0, atol=1e-9):
            raise SystemExit(f"STOP: 2018+ Close for {t} differs from the scorer's series")
        raw[t] = f.rename(columns={"Close": "adj"})[["High", "Low", "adj"]]
    dist = pd.read_csv(data_dir / "official_distributions.csv", parse_dates=["ex_date"])
    pairs = pd.read_csv(data_dir / "official_nav_exdate_pairs.csv", parse_dates=["ex_date", "prev_nav_date"])
    mtr = pd.read_csv(data_dir / "official_monthly_nav_total_return_ishares.csv", parse_dates=["month_end"])
    me_nav = pd.read_csv(data_dir / "official_month_end_nav_ssga.csv", parse_dates=["nav_date"])
    return adjusted, raw, dist, pairs, mtr, me_nav


# --------------------------------------------------------------------------- per ticker
def check_ticker(t: str, adj: pd.Series, raw: Optional[pd.DataFrame], dist: pd.DataFrame, pairs: pd.DataFrame,
                 monthly: pd.DataFrame) -> tuple:
    """monthly: columns month (Period), p (log NAV price move), y (log distribution contribution)."""
    d = dist[(dist.ticker == t) & (dist.ex_date >= EX_START) & (dist.ex_date <= LAST_DEV_PRICE)]
    d = d.merge(pairs[pairs.ticker == t], on=["ticker", "ex_date"], how="left").sort_values("ex_date").reset_index(drop=True)
    coverage_fail: List[str] = []
    rows = []
    for k, r in d.iterrows():
        ex = r.ex_date
        if ex not in adj.index:
            coverage_fail.append(f"{ex.date()} not a trading day in scorer series")
            continue
        prev = adj.index[adj.index.get_loc(ex) - 1]
        if pd.isna(r.prev_nav_date) or prev != r.prev_nav_date:
            coverage_fail.append(f"{ex.date()} previous trading day {prev.date()} != official previous NAV date {r.prev_nav_date}")
        D = float(r.distribution_per_share)
        a = math.log(adj.loc[ex] / adj.loc[prev])
        p = math.log(r.nav_ex / r.nav_prev)
        y = math.log(1.0 + D / r.nav_ex)
        row = {"ticker": t, "ex_date": ex.date().isoformat(), "prev_trading_day": prev.date().isoformat(),
               "official_distribution": D, "nav_prev": r.nav_prev, "nav_ex": r.nav_ex,
               "raw_nav_move_bp": 1e4 * (math.exp(p) - 1), "official_nav_total_return_bp": 1e4 * (math.exp(p + y) - 1),
               "adjusted_price_return_bp": 1e4 * (math.exp(a) - 1), "distribution_bp": 1e4 * y,
               "residual_vs_total_return_bp": 1e4 * (a - p - y), "_a": a, "_p": p, "_y": y}
        if raw is not None and raw.index[0] <= ex <= raw.index[-1]:
            prev_ex = d.ex_date.iloc[k - 1] if k > 0 else None
            next_ex = d.ex_date.iloc[k + 1] if k + 1 < len(d) else None
            c5 = implied_fraction(raw, ex, prev_ex, next_ex)
            if "implied_fraction_lo" in c5:
                off_lo, off_hi = D / raw.loc[prev, "High"], D / raw.loc[prev, "Low"]
                overlap = c5["implied_fraction_lo"] <= off_hi and off_lo <= c5["implied_fraction_hi"]
                mid_close = 0.5 * (raw.loc[prev, "High"] + raw.loc[prev, "Low"])
                c5.update({"raw_prev_low": raw.loc[prev, "Low"], "raw_prev_high": raw.loc[prev, "High"],
                           "implied_distribution_lo": c5["implied_fraction_lo"] * raw.loc[prev, "Low"],
                           "implied_distribution_hi": c5["implied_fraction_hi"] * raw.loc[prev, "High"],
                           "implied_distribution_mid": 0.5 * (c5["implied_fraction_lo"] + c5["implied_fraction_hi"]) * mid_close,
                           "c5_status": "PASS" if overlap else "FAIL: implied distribution differs from official"})
            row.update(c5)
        else:
            row["c5_status"] = "not applicable (pre-2018 file has no raw prices)"
        rows.append(row)
    per = pd.DataFrame(rows)

    # C2 ex-date capture; C6 informative per-date NAV check
    c2 = capture_ratio(per["_a"] - per["_p"], per["_y"])
    res = (per["_a"] - per["_p"] - per["_y"]).to_numpy()
    sig = robust_sd(res)
    informative = per["_y"].to_numpy() > INFORMATIVE_SIGMAS * sig
    closest_ok = (np.abs(res) < np.abs(res + per["_y"])) & (np.abs(res) < np.abs(res - per["_y"]))
    per["c6_status"] = np.where(~informative, "non-decisive (distribution < 6 noise SD)",
                                np.where(closest_ok, "PASS", "FAIL: closer to price-only or double-counted"))

    # C3 monthly, C4 cumulative
    month_end = adj.groupby(adj.index.to_period("M")).tail(1)
    me = pd.Series(month_end.values, index=month_end.index.to_period("M"))
    missing = [str(m) for m in MONTHS if m not in me.index or (m - 1) not in me.index]
    if missing:
        coverage_fail.append(f"months missing: {missing}")
    mm = monthly.set_index("month").reindex(MONTHS)
    if mm[["p", "y"]].isna().any().any():
        coverage_fail.append("official monthly NAV data incomplete")
    if "nav_date" in mm:
        scorer_me = pd.Series(month_end.index, index=month_end.index.to_period("M")).reindex(MONTHS)
        off = [str(m) for m, a, b in zip(MONTHS, scorer_me, mm["nav_date"]) if pd.Timestamp(a) != pd.Timestamp(b)]
        if off:
            coverage_fail.append(f"official month-end NAV date differs from scorer month-end: {off}")
    a_m = np.log(me.reindex(MONTHS).to_numpy() / me.reindex(MONTHS - 1).to_numpy())
    mon = pd.DataFrame({"ticker": t, "month": MONTHS.astype(str), "adjusted_return_bp": 1e4 * (np.exp(a_m) - 1),
                        "official_nav_total_return_bp": 1e4 * (np.exp(mm.p + mm.y).to_numpy() - 1),
                        "distribution_bp": 1e4 * mm.y.to_numpy(),
                        "residual_vs_total_return_bp": 1e4 * (a_m - mm.p.to_numpy() - mm.y.to_numpy())})
    c3 = capture_ratio(a_m - mm.p.to_numpy(), mm.y.to_numpy())
    cum = slice(1, None)  # 2014-01-31 -> 2023-01-31 (months 2014-02..2023-01)
    kc = float((a_m[cum] - mm.p.to_numpy()[cum]).sum() / mm.y.to_numpy()[cum].sum())

    n_c5 = per["c5_status"].eq("PASS").sum()
    c5_fail = per[per["c5_status"].astype(str).str.startswith("FAIL")]
    c6_fail = per[per["c6_status"].str.startswith("FAIL")]
    summary = {
        "ticker": t, "n_ex_dates": len(per), "first_ex_date": per.ex_date.iloc[0], "last_ex_date": per.ex_date.iloc[-1],
        "C1_coverage": {"pass": bool(not coverage_fail), "problems": coverage_fail},
        "C2_ex_date_capture": {**c2, "pass": kappa_ok(c2)},
        "C3_monthly_capture": {**c3, "pass": kappa_ok(c3)},
        "C4_cumulative_capture": {"kappa": kc, "band": list(KAPPA_CUM_BAND),
                                  "pass": bool(KAPPA_CUM_BAND[0] <= kc <= KAPPA_CUM_BAND[1])},
        "C5_implied_distribution": {"n_tested": int(n_c5 + len(c5_fail)), "n_pass": int(n_c5),
                                    "failures": c5_fail[["ex_date", "c5_status"]].to_dict("records"),
                                    "pass": bool(len(c5_fail) == 0 and (n_c5 + len(c5_fail)) > 0)},
        "C6_informative_nav": {"robust_sd_bp": 1e4 * sig, "n_informative": int(informative.sum()),
                               "n_pass": int((per["c6_status"] == "PASS").sum()),
                               "failures": c6_fail[["ex_date", "residual_vs_total_return_bp", "distribution_bp"]].to_dict("records"),
                               "pass": bool(len(c6_fail) == 0)},
    }
    summary["pass"] = bool(all(summary[k]["pass"] for k in summary if k.startswith("C")))
    return per.drop(columns=["_a", "_p", "_y"]), mon, summary


def monthly_official(t: str, dist: pd.DataFrame, pairs: pd.DataFrame, mtr: pd.DataFrame, me_nav: pd.DataFrame) -> pd.DataFrame:
    dp = dist[dist.ticker == t].merge(pairs[pairs.ticker == t], on=["ticker", "ex_date"])
    dp["y"] = np.log1p(dp.distribution_per_share / dp.nav_ex)
    y_m = dp.groupby(dp.ex_date.dt.to_period("M"))["y"].sum()
    if t == "SPY":
        n = me_nav[me_nav.ticker == t].sort_values("nav_date")
        months = n.nav_date.dt.to_period("M").iloc[1:].to_numpy()
        p = np.log(n.nav.iloc[1:].to_numpy() / n.nav.iloc[:-1].to_numpy())
        return pd.DataFrame({"month": months, "p": p, "y": y_m.reindex(months).fillna(0.0).to_numpy(),
                             "nav_date": n.nav_date.iloc[1:].to_numpy()})
    m = mtr[mtr.ticker == t].copy()
    m["month"] = m.month_end.dt.to_period("M")
    m["y"] = y_m.reindex(m.month).fillna(0.0).to_numpy()
    m["p"] = np.log1p(m.nav_total_return_pct / 100.0) - m["y"]
    return m[["month", "p", "y"]]


def run(spec: Path, data_dir: Path, out_dir: Path) -> Dict[str, object]:
    adjusted, raw, dist, pairs, mtr, me_nav = load_inputs(spec, data_dir)
    per_all, mon_all, sums = [], [], []
    for t in TICKERS:
        per, mon, s = check_ticker(t, adjusted[t], raw[t], dist, pairs, monthly_official(t, dist, pairs, mtr, me_nav))
        per_all.append(per), mon_all.append(mon), sums.append(s)
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.concat(per_all).to_csv(out_dir / "dividend_check_by_ex_date.csv", index=False, float_format="%.6f")
    pd.concat(mon_all).to_csv(out_dir / "dividend_check_by_month.csv", index=False, float_format="%.4f")
    status = {"gate": "freeze_gate_5_distribution_adjustment",
              "design": "stage2/methodology/Stage2_Dividend_Adjustment_Gate_v1.md",
              "spec": str(spec), "price_data_cutoff": LAST_DEV_PRICE.date().isoformat(),
              "status": "PASS" if all(s["pass"] for s in sums) else "FAIL", "by_ticker": sums}
    (out_dir / "dividend_gate_status.json").write_text(json.dumps(status, indent=2, default=float) + "\n")
    return status


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", type=Path, required=True)
    ap.add_argument("--data-dir", type=Path, default=DATA_DIR)
    ap.add_argument("--out-dir", type=Path, default=Path("stage2/results/dividend_gate"))
    args = ap.parse_args()
    if not (args.data_dir / "official_distributions.csv").exists():
        print("NOT_RUN: official records missing")
        return 3
    status = run(args.spec, args.data_dir, args.out_dir)
    for s in status["by_ticker"]:
        print(s["ticker"], "PASS" if s["pass"] else "FAIL",
              {k: s[k]["pass"] for k in s if k.startswith("C")})
    print("GATE:", status["status"])
    return 0 if status["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
