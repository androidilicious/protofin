#!/usr/bin/env python3
"""Import and validate the Bloomberg fed funds futures export, and build the AP3 mediator FF_FUTURES_6M.

Request: native_backtest/config/bloomberg_ff_futures_request_v1.json and
native_backtest/docs/BLOOMBERG_FED_FUNDS_FUTURES_REQUEST_2026-10-28.md.

Inputs (licensed, git-ignored), in native_backtest/data/_licensed/bloomberg/:
- ff_futures_history.csv  long format date,ticker,field,value (or a wide BDH sheet: Date, '<ticker>|<field>', ...)
- ff_futures_static.csv   ticker,field,value (FUT_DLV_DT_FIRST, FUT_DLV_DT_LAST, LAST_TRADEABLE_DT, ...)

Outputs:
- native_backtest/data/_licensed/bloomberg/ff_futures_6m.csv   date, contract_month, implied_rate, change_same_contract
  (derived from licensed data, so also git-ignored)
- native_backtest/out/ap3/ff_futures_import_report.json        hashes, coverage and check results only, no prices (committed)

FF_FUTURES_6M on day d is the average effective fed funds rate implied for calendar month month(d)+6:
100 minus that contract's daily settlement price. One-day changes are taken on the same contract, so the
monthly switch to the next contract never creates a jump. Contract months come from the delivery dates in
the static file, not from the ticker text.

Usage (repository root): python -m native_backtest.scripts.import_ff_futures [--dir DIR]
Exit status 0 when every required check passes, 2 otherwise.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

ROOT = Path(__file__).resolve().parents[2]
REQUEST = ROOT / "native_backtest/config/bloomberg_ff_futures_request_v1.json"
DEFAULT_DIR = ROOT / "native_backtest/data/_licensed/bloomberg"
REPORT = ROOT / "native_backtest/out/ap3/ff_futures_import_report.json"
MONTH_CODES = "FGHJKMNQUVXZ"
HORIZON_MONTHS = 6


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read_history(path: Path) -> pd.DataFrame:
    """Long frame date, ticker, field, value from either accepted layout."""
    df = pd.read_csv(path)
    cols = [c.strip() for c in df.columns]
    df.columns = cols
    if [c.lower() for c in cols[:4]] == ["date", "ticker", "field", "value"]:
        out = df.rename(columns=str.lower)[["date", "ticker", "field", "value"]]
    else:   # wide: Date, '<ticker>|<field>', ...
        date_col = cols[0]
        bad = [c for c in cols[1:] if "|" not in c]
        if bad:
            raise ValueError(f"wide layout needs '<ticker>|<field>' column names; got {bad[:3]}")
        out = df.melt(id_vars=[date_col], var_name="key", value_name="value").rename(columns={date_col: "date"})
        out[["ticker", "field"]] = out["key"].str.split("|", n=1, expand=True)
        out = out[["date", "ticker", "field", "value"]]
    out = out.dropna(subset=["value"]).copy()
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    out["ticker"] = out["ticker"].str.strip()
    out["field"] = out["field"].str.strip().str.upper()
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    return out.dropna(subset=["value"])


def read_static(path: Path) -> Dict[str, Dict[str, str]]:
    df = pd.read_csv(path, dtype=str)
    st: Dict[str, Dict[str, str]] = {}
    for t, f, v in zip(df["ticker"].str.strip(), df["field"].str.strip().str.upper(), df["value"].str.strip()):
        st.setdefault(t, {})[f] = v
    return st


def contract_month(ticker: str, static: Dict[str, str]) -> Tuple[Optional[pd.Period], str]:
    """(month, source). Delivery dates first; the ticker text only as a cross-check."""
    a, b = static.get("FUT_DLV_DT_FIRST"), static.get("FUT_DLV_DT_LAST")
    if a and b:
        da, db = pd.Timestamp(a), pd.Timestamp(b)
        if da.to_period("M") == db.to_period("M") and da.day == 1 and db == db.to_period("M").end_time.normalize():
            return da.to_period("M"), "delivery_dates"
        return None, f"delivery dates {a}..{b} are not one calendar month"
    m = re.match(r"^FF([FGHJKMNQUVXZ])(\d{1,2})\s+COMDTY$", ticker.upper())
    if m:
        return None, "no delivery dates in the static file (ticker text alone is not trusted)"
    return None, "unrecognised ticker"


def build(hist: pd.DataFrame, static: Dict[str, Dict[str, str]], start: str, end: str) -> Tuple[pd.DataFrame, dict]:
    checks: dict = {}
    dup = int(hist.duplicated(["date", "ticker", "field"]).sum())
    checks["duplicate_rows"] = {"count": dup, "pass": dup == 0}
    settle = hist[hist["field"] == "PX_SETTLE"]
    checks["has_px_settle"] = {"pass": not settle.empty}
    months, problems = {}, {}
    for t in sorted(set(settle["ticker"]) - {"FEDL01 Index"}):
        m, src = contract_month(t, static.get(t, {}))
        if m is None:
            problems[t] = src
        else:
            months[t] = m
    by_month: Dict[pd.Period, str] = {}
    clash = []
    for t, m in months.items():
        if m in by_month and by_month[m] != t:
            clash.append(f"{m}: {by_month[m]} and {t}")
        by_month[m] = t
    checks["contract_identification"] = {"identified": len(months), "unidentified": problems, "duplicate_months": clash,
                                         "pass": not problems and not clash and bool(months)}
    px = settle[settle["ticker"].isin(months)].pivot_table(index="date", columns="ticker", values="value", aggfunc="last").sort_index()
    oob = int(((px <= 90) | (px > 100.5)).sum().sum())
    checks["price_bounds_90_to_100.5"] = {"out_of_bounds": oob, "pass": oob == 0}

    # FF_FUTURES_6M: for each trading day, the contract for month(d)+6; change on the same contract
    rows = []
    for d in px.index[(px.index >= pd.Timestamp(start)) & (px.index <= pd.Timestamp(end))]:
        target = d.to_period("M") + HORIZON_MONTHS
        t = by_month.get(target)
        if t is None or pd.isna(px.at[d, t]):
            continue
        s = px[t].loc[:d].dropna()
        prev = s.iloc[-2] if len(s) >= 2 else np.nan
        rows.append({"date": d.date().isoformat(), "contract_month": str(target), "implied_rate": round(100.0 - float(s.iloc[-1]), 6),
                     "change_same_contract": None if pd.isna(prev) else round(float(prev) - float(s.iloc[-1]), 6)})
    series = pd.DataFrame(rows, columns=["date", "contract_month", "implied_rate", "change_same_contract"])

    # coverage against US federal business days in the window
    hol = set(USFederalHolidayCalendar().holidays(start=start, end=end).strftime("%Y-%m-%d"))
    bdays = [d.strftime("%Y-%m-%d") for d in pd.bdate_range(start, end) if d.strftime("%Y-%m-%d") not in hol]
    have = set(series["date"])
    missing = [d for d in bdays if d not in have]
    run, longest = 0, 0
    for d in bdays:
        run = run + 1 if d not in have else 0
        longest = max(longest, run)
    share = len(missing) / max(1, len(bdays))
    checks["coverage"] = {"business_days": len(bdays), "days_with_value": len(series), "missing": len(missing), "missing_share": round(share, 5),
                          "longest_gap_business_days": longest, "first_missing": missing[:10], "pass": share <= 0.005 and longest <= 3}

    # large one-day moves (informational)
    ch = series["change_same_contract"].dropna().astype(float)
    checks["one_day_moves_over_50bp"] = {"count": int((ch.abs() > 0.5).sum()), "dates": series.loc[ch.index[ch.abs() > 0.5], "date"].tolist()[:20],
                                         "pass": True, "note": "informational: inspect against FOMC days before use"}

    # final settlement vs the effective fed funds rate: last settle of an expired contract ~ 100 - monthly average EFFR
    eff = hist[(hist["ticker"] == "FEDL01 Index") & (hist["field"].isin(["PX_LAST", "PX_SETTLE"]))].set_index("date")["value"].sort_index()
    if eff.empty:
        checks["final_settlement_vs_effr"] = {"pass": None, "note": "FEDL01 Index not supplied; check skipped"}
    else:
        devs = {}
        daily = eff.reindex(pd.date_range(eff.index.min(), eff.index.max(), freq="D")).ffill()   # weekends carry Friday's rate
        for t, m in months.items():
            ltd = static.get(t, {}).get("LAST_TRADEABLE_DT")
            s = px[t].dropna() if t in px else pd.Series(dtype=float)
            if s.empty or not ltd or s.index.max() < pd.Timestamp(ltd) or m.end_time > daily.index.max():
                continue
            avg = float(daily.loc[m.start_time.normalize(): m.end_time.normalize()].mean())
            devs[str(m)] = round(abs((100.0 - float(s.loc[:pd.Timestamp(ltd)].iloc[-1])) - avg), 5)
        worst = max(devs.values()) if devs else None
        checks["final_settlement_vs_effr"] = {"contracts_checked": len(devs), "max_abs_deviation_pct_points": worst,
                                              "over_1bp": {k: v for k, v in devs.items() if v > 0.01},
                                              "pass": bool(devs) and worst is not None and worst <= 0.01}
    return series, checks


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    ap.add_argument("--report", type=Path, default=REPORT)
    a = ap.parse_args(argv)
    req = json.loads(REQUEST.read_text())
    hp, sp = a.dir / req["export_format"]["history_file"], a.dir / req["export_format"]["static_file"]
    if not hp.exists() or not sp.exists():
        print(f"waiting for the Bloomberg export: expected {hp} and {sp}")
        return 2
    hist, static = read_history(hp), read_static(sp)
    start, end = req["date_range"]
    series, checks = build(hist, static, start, end)
    out_csv = a.dir / "ff_futures_6m.csv"
    series.to_csv(out_csv, index=False)
    required = [k for k, v in checks.items() if v.get("pass") is False]
    report = {"request": "bloomberg_ff_futures_request_v1", "imported_utc": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
              "inputs_sha256": {hp.name: sha256(hp), sp.name: sha256(sp)}, "derived_sha256": {out_csv.name: sha256(out_csv)},
              "window": [start, end], "rows": len(series), "checks": checks, "failed_checks": required, "status": "PASS" if not required else "FAIL",
              "licence": "Bloomberg data and derived values stay out of git; only these hashes and check results are committed."}
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, indent=1, default=str) + "\n")
    print(json.dumps({k: report[k] for k in ("rows", "failed_checks", "status")}))
    return 0 if not required else 2


if __name__ == "__main__":
    raise SystemExit(main())
