"""Point-in-time mediator series and the Testing Agent's mediator tests.

A mediator test measures the change in a series over a pre-registered window ending at the
decision time, and its z-score against the distribution of the same-length changes over the
trailing 36 months up to the window start. Only rows with available_at <= decision time are used.
A move is informative only if |z| >= 1; a consistent move is recorded as empirical consistency,
never as causal proof.
"""
from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd


class MediatorStore:
    def __init__(self, series: Dict[str, pd.DataFrame], labels: Optional[Dict[str, str]] = None):
        # each frame: columns date, value, available_at (tz-aware). A date may have several rows (revised
        # versions, each with its own available_at); asof keeps the latest version visible at t.
        self.series = {}
        self.labels = dict(labels) if labels else {}
        for k, df in series.items():
            d = df.copy()
            d["date"] = pd.to_datetime(d["date"])
            d["available_at"] = pd.to_datetime(d["available_at"], utc=True)
            self.series[k] = d.sort_values(["date", "available_at"], kind="mergesort").reset_index(drop=True)

    def asof(self, name: str, t) -> pd.DataFrame:
        t = pd.Timestamp(t).tz_convert("UTC") if pd.Timestamp(t).tzinfo else pd.Timestamp(t, tz="UTC")
        d = self.series[name]
        d = d[d["available_at"] <= t]
        if d["date"].duplicated().any():
            d = d.drop_duplicates("date", keep="last")
        return d


def mediator_test(store: MediatorStore, name: str, expected_sign: int, window_start, decision_time,
                  ref_months: int = 36, z_threshold: float = 1.0) -> dict:
    if name not in store.series:
        return {"series": name, "result": "unavailable", "reason": "series not in the point-in-time store"}
    d = store.asof(name, decision_time).set_index("date")["value"].dropna()
    ws = pd.Timestamp(window_start).tz_localize(None) if pd.Timestamp(window_start).tzinfo else pd.Timestamp(window_start)
    if d.empty or d.index[0] > ws:
        return {"series": name, "result": "unavailable", "reason": "no data before the window start"}
    start_val = float(d[d.index <= ws].iloc[-1])
    end_val = float(d.iloc[-1])
    change = end_val - start_val
    span = max(1, int(((d.index[-1] - ws).days)))
    ref = d[(d.index > ws - pd.DateOffset(months=ref_months)) & (d.index <= ws)]
    if len(ref) < 30:
        return {"series": name, "result": "unavailable", "reason": "too little reference history", "change": change}
    # same-length changes over the reference period: lag in observations matching the window span
    ref_changes = ref.diff(max(1, min(len(ref) - 1, _obs_in_span(ref, span)))).dropna()
    sd = float(ref_changes.std(ddof=1)) if len(ref_changes) > 2 else np.nan
    z = change / sd if sd and np.isfinite(sd) and sd > 0 else np.nan
    if not np.isfinite(z) or abs(z) < z_threshold:
        result = "uninformative"
    else:
        result = "consistent" if np.sign(z) == np.sign(expected_sign) else "inconsistent"
    return {"series": name, **({"series_label": store.labels[name]} if name in store.labels else {}),
            "expected_sign": int(expected_sign), "window_start": str(ws.date()), "window_end": str(d.index[-1].date()),
            "change": change, "z": None if not np.isfinite(z) else float(z), "result": result,
            "interpretation": "empirical consistency only; not causal validation"}


def _obs_in_span(ref: pd.Series, span_days: int) -> int:
    if len(ref) < 2:
        return 1
    per_day = len(ref) / max(1, (ref.index[-1] - ref.index[0]).days)
    return max(1, int(round(span_days * per_day)))
