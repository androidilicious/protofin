#!/usr/bin/env python3
"""Validate the AP3 mediator-data inventory (v2) and write native_backtest/out/ap3/mediator_inventory_v2.json.

For every mediator series it checks, without network access:
- the pinned or captured file's SHA-256;
- coverage of the span the triggers need: 2011-12-01 (36-month stress reference before the first
  development month, 2015-02) through 2026-08-31 (last protected decision);
- missing US federal business days inside that span;
- equality with the official ALFRED latest vintage: the window table built from the pinned file must
  have the SHA-256 recorded from ALFRED (alfred_vintage_evidence_v1.json);
- vintage-aware availability: how many observations ALFRED shows were first posted after the h15 rule
  date, and the decision months in which a decision saw a value that was later revised;
- whether every development and protected decision month has the 60 reference changes the stress
  rule requires.
FF_FUTURES_6M is reported as pending (Bloomberg export).

Usage (repository root, after `python mvp/run.py fetch`):
  python -m native_backtest.scripts.ap3_mediator_inventory
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

from native_backtest.ap3 import mediator_data as md
from native_backtest.framework.market import load_config, load_market, months_between

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "native_backtest/out/ap3/mediator_inventory_v2.json"
SPAN = ("2011-12-01", "2026-08-31")
WINDOW = ("2011-12-01", "2026-09-30")


def _rows(dates, raw_values, lo=WINDOW[0], hi=WINDOW[1]):
    out = []
    for d, v in zip(dates, raw_values):
        if pd.isna(v) or v in ("", "."):
            continue
        if lo <= d <= hi:
            out.append(d.replace("-", "") + "," + v)
    return out


def window_table(name: str, spec: dict, lo=WINDOW[0], hi=WINDOW[1]) -> list:
    """'YYYYMMDD,value' rows as the source serves them (FRED CSV strings; CBOE closes at 2 decimals)."""
    if "capture" in spec:
        prov = json.loads((md.MEDIATOR_DATA / f"{spec['capture']}_provenance.json").read_text())
        rows = []
        for part in prov["parts"]:
            rows += (md.MEDIATOR_DATA / part["file"]).read_text().split("\n")
        return [r for r in rows if lo.replace("-", "") <= r[:8] <= hi.replace("-", "")]
    df = pd.read_csv(md.PINNED / spec["file"], dtype=str)
    dc = spec.get("date_column") or ("observation_date" if "observation_date" in df.columns else df.columns[0])
    dates = pd.to_datetime(df[dc]).dt.strftime("%Y-%m-%d")
    vals = df[spec["column"]]
    if name == "VIX":
        vals = vals.map(lambda x: x if pd.isna(x) else "%.2f" % float(x))
    return _rows(dates, vals, lo, hi)


def _sha_rows(rows) -> str:
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()


def main() -> int:
    ev = md.alfred_evidence()["series"]
    cfg = load_config()
    mk = load_market(cfg)
    months = months_between("2015-02", "2026-08")
    dtimes = {str(m): pd.Timestamp(f"{mk.decision_dates[m]} 20:00", tz="America/New_York") for m in months if m in mk.decision_dates}
    hol = set(USFederalHolidayCalendar().holidays(start=SPAN[0], end=SPAN[1]).strftime("%Y-%m-%d"))
    bdays = [d.strftime("%Y-%m-%d") for d in pd.bdate_range(SPAN[0], SPAN[1]) if d.strftime("%Y-%m-%d") not in hol]
    store, status = md.load_store(include_pending_substitutes=True, inventory="v2")
    inv = {}
    for name, spec in md.SERIES_V2.items():
        rec = {"label": spec.get("label"), "status": status.get(name)}
        if name not in store.series:
            rec["validated"] = False
            rec["reason"] = spec.get("note")
            inv[name] = rec
            continue
        s = store.asof(name, pd.Timestamp("2035-01-01", tz="UTC")).dropna(subset=["value"])
        dates = set(s["date"].dt.strftime("%Y-%m-%d"))
        cover = s[(s["date"] >= SPAN[0]) & (s["date"] <= SPAN[1])]
        missing = [d for d in bdays if d not in dates]
        rec.update({
            "source": spec.get("file") or f"browser capture ({spec.get('capture')})",
            "first_observation": str(s["date"].min().date()), "last_observation": str(s["date"].max().date()),
            "covers_required_span": bool(s["date"].min() <= pd.Timestamp(SPAN[0]) and s["date"].max() >= pd.Timestamp(SPAN[1])),
            "observations_in_span": int(len(cover)),
            "business_days_without_value_in_span": len(missing),
            "business_days_without_value_examples": missing[:12],
            "availability_rule": {"h15": "next US federal business day 18:00 ET, floored by ALFRED first vintage 18:00 ET",
                                  "close": "same day 17:00 ET (market close)"}[spec["rule"]],
        })
        # equality with ALFRED latest vintage
        aid = spec.get("alfred") or ("VIXCLS" if name == "VIX" else None)
        if aid:
            e = ev[aid]
            if name == "VIX":
                checks = {}
                for k, segment in e["segment_sha256"].items():
                    lo, hi = k.split("..")
                    if pd.Timestamp(hi) > s["date"].max():   # segment runs past the pinned file's last observation
                        continue
                    rows = window_table(name, spec, lo, hi)
                    checks[k] = {"rows": len(rows), "equals_alfred": _sha_rows(rows) == segment["sha256"] and len(rows) == segment["n"]}
                covered = [k for k, c in checks.items() if c["equals_alfred"]]
                rec["alfred_check"] = {"segments": checks,
                                       "summary": f"equals VIXCLS on {', '.join(covered)}" if covered else "MISMATCH"}
                rec["validated"] = "2011-12-01..2014-12-31" in covered and "2015-01-02..2018-11-30" in covered and "2018-12-03..2026-09-22" in covered
            else:
                rows = window_table(name, spec)
                same = _sha_rows(rows) == e["latest_window_table_sha256"] and len(rows) == e["n_observations_latest"]
                later = e.get("first_vintage_later_than_rule") or []
                rule_floor = md.available_at(pd.DatetimeIndex([pd.Timestamp(x.split(":")[0]) for x in later]), "h15")
                binding = sum(md.vintage_time(x.split(":")[1]) > r for x, r in zip(later, rule_floor))
                # decision months that saw a value later revised (the store gives them the then-public value)
                saw_unrevised = []
                for r in e.get("revisions", []):
                    vs = r["versions"]
                    if len(vs) < 2:
                        continue
                    t0, t1 = md.vintage_time(vs[0]["vintage"]), md.vintage_time(vs[-1]["vintage"])
                    for mo, t in dtimes.items():
                        if t0 <= t < t1:
                            saw_unrevised.append({"obs": r["obs"], "decision_month": mo})
                rec["alfred_check"] = {"latest_vintage_equals_pinned": same, "rows": len(rows),
                                       "first_posted_after_rule": binding, "revised_observations": len(e.get("revisions", [])),
                                       "decisions_that_saw_a_later_revised_value": saw_unrevised}
                rec["validated"] = bool(same)
        # stress-reference sufficiency per decision month (60 one-day changes in the 36 months before the month)
        short = []
        for mo, t in dtimes.items():
            ms = pd.Period(mo, "M").start_time
            d = store.asof(name, t).set_index("date")["value"].dropna()
            ch = d.diff().dropna()
            n = int(((ch.index < ms) & (ch.index >= ms - pd.DateOffset(months=36))).sum())
            if n < 60:
                short.append({"month": mo, "reference_changes": n})
        rec["months_without_stress_reference"] = short
        inv[name] = rec
    gap = inv["IG_SPREAD"]
    result = {
        "inventory": "v2", "created": "2026-10-28",
        "required_span": list(SPAN),
        "decision_months_checked": [min(dtimes), max(dtimes)],
        "series": inv,
        "validated": [k for k, v in inv.items() if v.get("validated")],
        "pending": [k for k, v in inv.items() if not v.get("validated")],
        "complete": all(v.get("validated") for v in inv.values()),
        "notes": ["IG_SPREAD is an approved, explicitly labelled PROXY (Moody's Baa minus 10-year Treasury), not an IG option-adjusted spread.",
                  "Development packets and trigger counts built on this inventory remain provisional while FF_FUTURES_6M is pending."],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps({k: {kk: v.get(kk) for kk in ("validated", "observations_in_span", "business_days_without_value_in_span", "alfred_check")}
                      for k, v in inv.items()}, indent=1, default=str)[:6000])
    print("validated:", result["validated"], "pending:", result["pending"])
    return 0 if set(result["pending"]) <= {"FF_FUTURES_6M"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
