"""Point-in-time mediator series for AP3's Testing Agent and its market-stress triggers.

Two inventories are kept. v1 is unchanged so the v1 dry-run outputs stay reproducible; v2 is the
validated inventory (native_backtest/out/ap3/mediator_inventory_v2.json) and the default.

| AP3 series    | v1 source                                     | v2 source and status                                                    |
|---------------|-----------------------------------------------|-------------------------------------------------------------------------|
| UST2Y         | FRED DGS2 (ap3_mediator_manifest_v1)          | same pin; ALFRED-checked, vintage-aware availability                    |
| UST10Y        | FRED DGS10 (ap3_mediator_manifest_v1)         | same pin; ALFRED-checked, vintage-aware availability and revisions      |
| SLOPE_10Y3M   | FRED T10Y3M (Stage 2 snapshot v3)             | same pin; ALFRED-checked, vintage-aware availability and revisions      |
| VIX           | ^VIX to 2018-11-30, then VIXCLS (Stage 2 v3)  | CBOE daily close, one source (ap3_mediator_manifest_v2), = VIXCLS       |
| IG_SPREAD     | FRED BAA10Y, substitute pending approval      | PROXY, approved 2026-10-28: Moody's Baa minus 10-year Treasury (BAA10Y); |
|               |                                               | not an IG option-adjusted spread. ALFRED-checked, vintage-aware         |
| BEI5Y         | not pinned                                    | FRED T5YIE, browser capture committed with hashes; ALFRED-checked       |
| FF_FUTURES_6M | not available                                 | not available: Bloomberg export requested                               |

Availability (America/New_York; a value is usable only if available_at <= the 20:00 ET decision time):
- "h15" series (Treasury yields, the 10Y-3M slope, BAA10Y, T5YIE): next US federal business day, 18:00 ET.
  In v2 this is a floor: when ALFRED shows FRED first posted an observation later, available_at is
  that first vintage date, 18:00 ET. Revised values enter as new versions at their vintage date, so a
  decision sees the value that was public at the time (MediatorStore.asof keeps the latest visible version).
- "close" (VIX): a market close known on the day; available_at = the same day, 17:00 ET.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

from native_backtest.ap3.mediators import MediatorStore

ROOT = Path(__file__).resolve().parents[2]
PINNED = ROOT / "stage2/data/_pinned"
MEDIATOR_DATA = ROOT / "native_backtest/data/ap3_mediators"
EVIDENCE = MEDIATOR_DATA / "alfred_vintage_evidence_v1.json"
DEFAULT_INVENTORY = "v2"

SERIES_V1 = {
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
SERIES = SERIES_V1   # name kept for v1 callers

IG_PROXY_LABEL = ("PROXY for the investment-grade credit spread: Moody's seasoned Baa corporate bond yield minus the "
                  "10-year Treasury yield (FRED BAA10Y, percentage points). Not an option-adjusted IG index spread.")

SERIES_V2 = {
    "UST2Y": {**SERIES_V1["UST2Y"], "alfred": "DGS2",
              "label": "2-year Treasury constant-maturity yield (FRED DGS2, percent)"},
    "UST10Y": {**SERIES_V1["UST10Y"], "alfred": "DGS10",
               "label": "10-year Treasury constant-maturity yield (FRED DGS10, percent)"},
    "SLOPE_10Y3M": {**SERIES_V1["SLOPE_10Y3M"], "alfred": "T10Y3M",
                    "label": "10-year minus 3-month Treasury yield (FRED T10Y3M, percentage points)"},
    "IG_SPREAD": {"file": "signal_credit_spread.csv", "column": "BAA10Y", "rule": "h15", "status": "proxy_approved", "alfred": "BAA10Y",
                  "sha256": "64fb420ac4fc8189d3c7f2271e618f0e280dc8939a6a81f1783a2faffc7da24e", "label": IG_PROXY_LABEL,
                  "note": "approved 2026-10-28 as an explicitly labelled proxy, not an equivalent of IG OAS (MEDIATOR_INVENTORY_v2_2026-10-28.md)"},
    "VIX": {"file": "mediator_VIX_cboe.csv", "column": "CLOSE", "date_column": "DATE", "rule": "close", "status": "pinned",
            "sha256": "570e05630c9a5e7350d0c3dbe3acc58e793cb5248181ab0e949c121cc082fb83",
            "label": "CBOE Volatility Index (VIX), daily close, index points"},
    "BEI5Y": {"capture": "T5YIE", "rule": "h15", "status": "pinned", "alfred": "T5YIE",
              "label": "5-year breakeven inflation rate (FRED T5YIE: 5-year nominal minus 5-year TIPS yield, percent)"},
    "FF_FUTURES_6M": {"status": "not_available",
                      "label": "Fed funds rate implied by the 30-day fed funds futures contract six months ahead (100 minus settlement price, percent)",
                      "note": "Bloomberg export requested (BLOOMBERG_FED_FUNDS_FUTURES_REQUEST_2026-10-28.md); importer: native_backtest/scripts/import_ff_futures.py"},
}
POLICY_PROXY_LABEL = ("PROXY for the expected policy-rate path (stand-in for fed funds futures, which need a Bloomberg export): "
                      "2-year Treasury yield minus the 4-week Treasury bill rate (FRED DGS2 minus DTB4WK, percentage points). "
                      "Includes a term premium; not fed funds futures.")
DTB4WK_FILE = ROOT / "stage2/data/risk_free/DTB4WK_combined_2001-07-31_to_2026-10-01.csv"
DTB4WK_SHA = "ed2f0bc7e3cc337f1e1ec8f4b2b823a69fed879f2dd6c2c6eefb6e62cd22a66a"
# Separately documented sensitivity variant (not the frozen specification): FF_FUTURES_6M is replaced by a labelled
# proxy built from two pinned, hash-checked series. Used only by the variant that names this inventory.
SERIES_V2_POLICY_PROXY = {**SERIES_V2, "FF_FUTURES_6M": {
    "derived": "policy_path_proxy", "rule": "h15", "status": "proxy_variant_not_in_frozen_spec", "label": POLICY_PROXY_LABEL,
    "note": "variant reduced_evidence_policy_proxy only; frozen specification keeps FF_FUTURES_6M as unavailable until the Bloomberg export"}}
INVENTORIES = {"v1": SERIES_V1, "v2": SERIES_V2, "v2_policy_proxy": SERIES_V2_POLICY_PROXY}


def _policy_path_proxy() -> pd.DataFrame:
    """DGS2 (with its ALFRED vintages) minus DTB4WK on the same date; available when both are."""
    if _sha(DTB4WK_FILE) != DTB4WK_SHA:
        raise MediatorDataError(f"{DTB4WK_FILE} does not match its pinned SHA-256")
    two = load_series("UST2Y", "v2")
    df = pd.read_csv(DTB4WK_FILE)
    dc = "observation_date" if "observation_date" in df.columns else df.columns[0]
    vc = "DTB4WK" if "DTB4WK" in df.columns else df.columns[1]
    b = pd.DataFrame({"date": pd.to_datetime(df[dc]).dt.normalize(), "bill": pd.to_numeric(df[vc], errors="coerce")}).dropna()
    b["bill_available_at"] = available_at(pd.DatetimeIndex(b["date"]), "h15")
    m = two.merge(b, on="date", how="inner")
    m["value"] = m["value"] - m["bill"]
    m["available_at"] = m[["available_at", "bill_available_at"]].max(axis=1)
    return m[["date", "value", "available_at"]].sort_values(["date", "available_at"]).reset_index(drop=True)


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


def read_capture(series_id: str) -> pd.Series:
    """A series captured in the browser and committed as hashed parts (YYYYMMDD,value joined by newlines)."""
    prov = json.loads((MEDIATOR_DATA / f"{series_id}_provenance.json").read_text())
    rows = []
    for part in prov["parts"]:
        p = MEDIATOR_DATA / part["file"]
        if _sha(p) != part["sha256"]:
            raise MediatorDataError(f"{p} does not match its browser-side SHA-256")
        rows += p.read_text().split("\n")
    if hashlib.sha256("\n".join(rows).encode()).hexdigest() != prov["window_table_sha256"]:
        raise MediatorDataError(f"{series_id}: joined capture does not match its window hash")
    d = pd.to_datetime([r.split(",")[0] for r in rows], format="%Y%m%d")
    return pd.Series([float(r.split(",")[1]) for r in rows], index=d).sort_index()


def available_at(dates: pd.DatetimeIndex, rule: str) -> pd.DatetimeIndex:
    if rule == "h15":
        hol = USFederalHolidayCalendar().holidays(start="1960-01-01", end="2035-12-31").values.astype("datetime64[D]")
        nxt = np.busday_offset(dates.values.astype("datetime64[D]"), 1, roll="forward", holidays=hol)
        return (pd.DatetimeIndex(nxt) + pd.Timedelta(hours=18)).tz_localize("America/New_York")
    if rule == "close":
        return (dates + pd.Timedelta(hours=17)).tz_localize("America/New_York")
    raise ValueError(rule)


def vintage_time(day: str) -> pd.Timestamp:
    """A FRED vintage date as a time: 18:00 ET on that date (the same convention as the h15 rule)."""
    return (pd.Timestamp(day) + pd.Timedelta(hours=18)).tz_localize("America/New_York")


@lru_cache(maxsize=1)
def alfred_evidence() -> dict:
    return json.loads(EVIDENCE.read_text())


def _version_value(v: dict, current: Optional[float]) -> float:
    if v.get("deleted"):
        return np.nan
    if "value" in v:
        return float(v["value"])
    if "minus_current_bp" in v:
        return round(current + v["minus_current_bp"] / 100.0, 6)
    if "minus_current" in v:
        return round(current + v["minus_current"], 6)
    raise ValueError(v)


def apply_alfred(frame: pd.DataFrame, series_id: str) -> pd.DataFrame:
    """Vintage-aware availability: later first postings move available_at; revisions become dated versions."""
    ev = alfred_evidence()["series"][series_id]
    f = frame.copy()
    later = ev.get("first_vintage_later_than_rule")
    if isinstance(later, list):
        ov = {}
        for x in later:
            o, v = x.split(":")
            ov[pd.Timestamp(o)] = vintage_time(v)
        upd = f["date"].map(ov)
        m = upd.notna()
        f.loc[m, "available_at"] = [max(a, b) for a, b in zip(f.loc[m, "available_at"], upd[m])]
    extra, drop = [], []
    cur = f.set_index("date")["value"]
    rule_at = f.set_index("date")["available_at"]
    lo, hi = f["date"].min(), f["date"].max()
    for r in ev.get("revisions", []):
        obs = pd.Timestamp(r["obs"])
        vers = r["versions"]
        if obs < lo or obs > hi:      # outside this file's range; a revised date inside the range must be present
            continue
        if obs in cur.index:
            current = float(cur[obs])
            last = _version_value(vers[-1], current)
            if not np.isclose(last, current, atol=1e-9):
                raise MediatorDataError(f"{series_id} {obs.date()}: latest ALFRED version differs from the pinned value")
            first_at = rule_at[obs]
            drop.append(obs)
        else:
            if not vers[-1].get("deleted"):
                raise MediatorDataError(f"{series_id} {obs.date()}: revised observation missing from the pinned file")
            current = None
            first_at = available_at(pd.DatetimeIndex([obs]), "h15")[0]
        for i, v in enumerate(vers):
            t = vintage_time(v["vintage"])
            extra.append({"date": obs, "value": _version_value(v, current), "available_at": max(t, first_at) if i == 0 else t})
    if drop:
        f = f[~f["date"].isin(drop)]
    if extra:
        f = pd.concat([f, pd.DataFrame(extra)], ignore_index=True)
    return f.sort_values(["date", "available_at"]).reset_index(drop=True)


def load_series(name: str, inventory: str = DEFAULT_INVENTORY) -> pd.DataFrame:
    spec = INVENTORIES[inventory][name]
    if spec.get("derived") == "policy_path_proxy":
        return _policy_path_proxy()
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
    elif "capture" in spec:
        s = read_capture(spec["capture"])
    else:
        s = _read(spec["file"], spec["column"], spec["sha256"], spec.get("date_column"))
    idx = pd.DatetimeIndex(s.index)
    frame = pd.DataFrame({"date": idx, "value": s.to_numpy(float), "available_at": available_at(idx, spec["rule"])})
    if inventory != "v1" and spec.get("alfred"):
        frame = apply_alfred(frame, spec["alfred"])
    return frame


def labels(inventory: str = DEFAULT_INVENTORY) -> Dict[str, str]:
    return {k: v["label"] for k, v in INVENTORIES[inventory].items() if "label" in v}


def load_store(include_pending_substitutes: bool = False, inventory: str = "v1") -> tuple:
    """Returns (MediatorStore, status) where status lists every series and why it is or is not loaded.
    inventory="v1" reproduces the v1 dry run; "v2" is the validated inventory (labels attached)."""
    frames, status = {}, {}
    for name, spec in INVENTORIES[inventory].items():
        if spec["status"] == "substitute_pending_approval" and not include_pending_substitutes:
            status[name] = "not loaded: substitute pending team approval"
            continue
        try:
            frames[name] = load_series(name, inventory)
            status[name] = spec["status"]
        except MediatorDataError as e:
            status[name] = f"unavailable: {e}"
    return MediatorStore(frames, labels(inventory) if inventory != "v1" else None), status


def visible_available_at(store: MediatorStore, name: str, day, t) -> pd.Timestamp:
    """available_at of the version of `day` that is visible at time t (the one the store uses)."""
    d = store.asof(name, t)
    row = d[d["date"] == pd.Timestamp(day)]
    if row.empty:
        raise KeyError(f"{name} {day} not visible at {t}")
    return row["available_at"].iloc[-1]


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
                e = {"series": name, "date": str(day.date()), "change": round(float(v), 4), "z": round(float(z), 2)}
                if store.labels and name in store.labels:
                    e["series_label"] = store.labels[name]
                out.append(e)
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


def manifest_status(inventory: str = DEFAULT_INVENTORY) -> Dict[str, dict]:
    return {k: {"status": v["status"], **({"note": v["note"]} if "note" in v else {}), **({"label": v["label"]} if "label" in v else {})}
            for k, v in INVENTORIES[inventory].items()}
