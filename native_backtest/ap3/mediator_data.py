"""Point-in-time mediator series for AP3's Testing Agent and its market-stress triggers.

Sources (all pinned by SHA-256; raw files are git-ignored):

| AP3 series   | Source                                   | Status |
|--------------|------------------------------------------|--------|
| UST2Y        | FRED DGS2 (ap3_mediator_manifest_v1)     | pinned |
| UST10Y       | FRED DGS10 (ap3_mediator_manifest_v1)    | pinned |
| SLOPE_10Y3M  | FRED T10Y3M (Stage 2 snapshot v3)        | pinned |
| VIX          | ^VIX before 2018-12-03, VIXCLS after (Stage 2 snapshot v3, same boundary) | pinned |
| IG_SPREAD    | FRED BAA10Y (Stage 2 snapshot v3) as a SUBSTITUTE for an investment-grade OAS | substitute, pending team approval |
| BEI5Y        | FRED T5YIE                               | not yet pinned |
| FF_FUTURES_6M| fed funds futures (Bloomberg)            | not available |

Availability rules (conservative, America/New_York):
- Treasury yields, the 10Y-3M slope and BAA10Y come from the Federal Reserve's H.15 release, which publishes
  a day's values on the following business day. available_at = next US business day, 18:00 ET.
- VIX is a market close observable at 16:15 ET on the same day. available_at = the same day, 17:00 ET.
A value is usable for a decision only if available_at <= the decision time (20:00 ET on the decision day).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

from native_backtest.ap3.mediators import MediatorStore

ROOT = Path(__file__).resolve().parents[2]
PINNED = ROOT / "stage2/data/_pinned"

SERIES = {
    "UST2Y": {"file": "mediator_UST2Y.csv", "column": "DGS2", "rule": "h15", "status": "pinned",
              "sha256": "709efc3c9cbd7826d960a8cfd052cc2cd39eee4a4b209443b74fd48be1d1ab1a"},
    "UST10Y": {"file": "mediator_UST10Y.csv", "column": "DGS10", "rule": "h15", "status": "pinned",
               "sha256": "19f98e90edb98a9e861f534980d7f6189fe69c771159197585a057589b65327d"},
    "SLOPE_10Y3M": {"file": "signal_yield_curve.csv", "column": "T10Y3M", "rule": "h15", "status": "pinned",
                    "sha256": "ea6d51b4116e6c5b463bab7fab6eba0ded988921ff126594b492c0dc6690cac6"},
    "IG_SPREAD": {"file": "signal_credit_spread.csv", "column": "BAA10Y", "rule": "h15", "status": "substitute_pending_approval",
                  "sha256": "64fb420ac4fc8189d3c7f2271e618f0e280dc8939a6a81f1783a2faffc7da24e",
                  "note": "Moody's Baa yield minus 10-year Treasury, standing in for an investment-grade OAS (ICE BofA history is not obtainable)"},
    "VIX": {"segments": [{"file": "signal_vix_pre2018.csv", "column": "close", "date_column": "date", "end_exclusive": "2018-12-03",
                          "sha256": "b00425a2282e185fe6429e0db3620d6f66d00e4aa703842a6b783b70cd274cc1"},
                         {"file": "signal_vix_2018plus.csv", "column": "VIXCLS", "start_inclusive": "2018-12-03",
                          "sha256": "cd584d562e318348bfb495284206a3d9fbf06a28cd8edadd62af3ca166727a0a"}],
            "rule": "close", "status": "pinned"},
    "BEI5Y": {"status": "not_pinned", "note": "FRED T5YIE: needs a pinned copy (sandbox cannot reach FRED)"},
    "FF_FUTURES_6M": {"status": "not_available", "note": "fed funds futures need a Bloomberg export, or team approval to drop or proxy this mediator"},
}


class MediatorDataError(RuntimeError):
    pass


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _read(file: str, column: str, sha: str, date_column: Optional[str] = None) -> pd.Series:
    p = PINNED / file
    if not p.exists():
        raise MediatorDataError(f"{p} missing: run python mvp/run.py fetch")
    if _sha(p) != sha:
        raise MediatorDataError(f"{p} does not match its pinned SHA-256")
    df = pd.read_csv(p)
    dc = date_column or ("observation_date" if "observation_date" in df.columns else df.columns[0])
    s = pd.to_numeric(df[column], errors="coerce")
    s.index = pd.to_datetime(df[dc]).dt.tz_localize(None).dt.normalize()
    return s.dropna().sort_index()


def available_at(dates: pd.DatetimeIndex, rule: str) -> pd.DatetimeIndex:
    if rule == "h15":
        hol = USFederalHolidayCalendar().holidays(start="1960-01-01", end="2035-12-31").values.astype("datetime64[D]")
        nxt = np.busday_offset(dates.values.astype("datetime64[D]"), 1, roll="forward", holidays=hol)
        return (pd.DatetimeIndex(nxt) + pd.Timedelta(hours=18)).tz_localize("America/New_York")
    if rule == "close":
        return (dates + pd.Timedelta(hours=17)).tz_localize("America/New_York")
    raise ValueError(rule)


def load_series(name: str) -> pd.DataFrame:
    spec = SERIES[name]
    if spec["status"] in ("not_pinned", "not_available"):
        raise MediatorDataError(f"{name}: {spec['note']}")
    if "segments" in spec:
        parts = []
        for seg in spec["segments"]:
            s = _read(seg["file"], seg["column"], seg["sha256"], seg.get("date_column"))
            if "end_exclusive" in seg:
                s = s[s.index < pd.Timestamp(seg["end_exclusive"])]
            if "start_inclusive" in seg:
                s = s[s.index >= pd.Timestamp(seg["start_inclusive"])]
            parts.append(s)
        s = pd.concat(parts).sort_index()
    else:
        s = _read(spec["file"], spec["column"], spec["sha256"])
    idx = pd.DatetimeIndex(s.index)
    return pd.DataFrame({"date": idx, "value": s.to_numpy(float), "available_at": available_at(idx, spec["rule"])})


def load_store(include_pending_substitutes: bool = False) -> tuple:
    """Returns (MediatorStore, status) where status lists every series and why it is or is not loaded."""
    frames, status = {}, {}
    for name, spec in SERIES.items():
        if spec["status"] == "substitute_pending_approval" and not include_pending_substitutes:
            status[name] = "not loaded: substitute pending team approval"
            continue
        try:
            frames[name] = load_series(name)
            status[name] = spec["status"]
        except MediatorDataError as e:
            status[name] = f"unavailable: {e}"
    return MediatorStore(frames), status


def stress_events(store: MediatorStore, month_start: pd.Timestamp, decision_time: pd.Timestamp, z_threshold: float,
                  ref_months: int = 36, per_series: bool = True) -> List[dict]:
    """Market-stress triggers: days in the decision month whose one-day change in a mediator has |z| >= z_threshold,
    z measured against one-day changes over the trailing ref_months before the month (only data available by the
    decision time is used). With per_series (the AP3 rule, limits_v1 'stress_aggregation'), each series contributes
    one trigger: its largest-|z| day, with the number of days at or above the threshold."""
    out = []
    ms = pd.Timestamp(month_start)
    for name in store.series:
        d = store.asof(name, decision_time).set_index("date")["value"].dropna()
        ch = d.diff().dropna()
        ref = ch[(ch.index < ms) & (ch.index >= ms - pd.DateOffset(months=ref_months))]
        if len(ref) < 60:
            continue
        sd = float(ref.std(ddof=1))
        if not np.isfinite(sd) or sd <= 0:
            continue
        cur = ch[ch.index >= ms]
        for day, v in cur.items():
            z = v / sd
            if abs(z) >= z_threshold:
                out.append({"series": name, "date": str(day.date()), "change": round(float(v), 4), "z": round(float(z), 2)})
    if per_series:
        agg = {}
        for e in out:
            k = e["series"]
            agg.setdefault(k, {**e, "days_at_or_above_threshold": 0})
            agg[k]["days_at_or_above_threshold"] += 1
            if abs(e["z"]) > abs(agg[k]["z"]):
                agg[k].update({kk: e[kk] for kk in ("date", "change", "z")})
        out = list(agg.values())
    return sorted(out, key=lambda e: (e["date"], e["series"]))


def manifest_status() -> Dict[str, dict]:
    return {k: {"status": v["status"], **({"note": v["note"]} if "note" in v else {})} for k, v in SERIES.items()}
