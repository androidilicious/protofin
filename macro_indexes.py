"""Economic Policy Uncertainty (EPU) and Geopolitical Risk (GPR) daily indexes.

Sources (free with attribution):
  EPU  Baker, Bloom & Davis, "Measuring Economic Policy Uncertainty", www.PolicyUncertainty.com
  GPR  Caldara & Iacoviello, "Measuring Geopolitical Risk", www.matteoiacoviello.com/gpr.htm

Files are cached under data/ and refreshed when older than REFRESH_HOURS. Both series are
"as published today": the authors revise history, so a backtest on them is not a true
vintage test. The daily values are what a reader would have seen that day only approximately.
"""
import io
import os
import time
import urllib.request

import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
REFRESH_HOURS = 24
SOURCES = {
    "epu": "https://www.policyuncertainty.com/media/All_Daily_Policy_Data.csv",
    "gpr": "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls",
}
LOOKBACK_YEARS = 10      # window for percentile ranks
SMOOTH_DAYS = 30         # trailing mean used for the regime read
HIGH_PCTL = 80.0         # "elevated" when BOTH indexes sit at/above this percentile...
VERY_HIGH_PCTL = 90.0    # ...or EITHER sits at/above this one


def _fetch(key):
    os.makedirs(DATA_DIR, exist_ok=True)
    url = SOURCES[key]
    path = os.path.join(DATA_DIR, f"{key}_daily" + os.path.splitext(url)[1])
    fresh = os.path.exists(path) and (time.time() - os.path.getmtime(path)) < REFRESH_HOURS * 3600
    if not fresh:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=60).read()
            with open(path, "wb") as fh:
                fh.write(data)
        except Exception:
            if not os.path.exists(path):
                raise
    with open(path, "rb") as fh:
        return fh.read()


def load_epu():
    """Daily US news-based EPU index as a Series indexed by date."""
    df = pd.read_csv(io.BytesIO(_fetch("epu")))
    idx = pd.to_datetime(dict(year=df["year"], month=df["month"], day=df["day"]))
    return pd.Series(df["daily_policy_index"].values, index=idx, name="EPU").dropna().sort_index()


def load_gpr():
    """Daily GPR index (GPRD) as a Series indexed by date."""
    df = pd.read_excel(io.BytesIO(_fetch("gpr")))
    df = df[["date", "GPRD"]].dropna()
    return pd.Series(df["GPRD"].values, index=pd.to_datetime(df["date"]), name="GPR").sort_index()


def load_all():
    return pd.concat([load_epu(), load_gpr()], axis=1).sort_index()


def _percentile(history, value):
    return float((history < value).mean() * 100)


def snapshot(series, as_of=None):
    """Latest value, 30-day mean, and where that mean sits in the trailing 10-year distribution."""
    s = series.dropna()
    if as_of is not None:
        s = s[s.index <= pd.Timestamp(as_of)]
    if len(s) < SMOOTH_DAYS * 2:
        return None
    window = s[s.index >= s.index[-1] - pd.DateOffset(years=LOOKBACK_YEARS)]
    smooth = window.rolling(SMOOTH_DAYS).mean().dropna()
    latest_mean = float(smooth.iloc[-1])
    return {
        "as_of": str(s.index[-1].date()),
        "latest": round(float(s.iloc[-1]), 1),
        "mean_30d": round(latest_mean, 1),
        "percentile_10y": round(_percentile(smooth.values, latest_mean), 1),
        "elevated": _percentile(smooth.values, latest_mean) >= HIGH_PCTL,
    }


def _regime(pctls):
    pctls = [p for p in pctls if p is not None and not np.isnan(p)]
    if not pctls:
        return "normal"
    if max(pctls) >= VERY_HIGH_PCTL or (len(pctls) == 2 and min(pctls) >= HIGH_PCTL):
        return "elevated"
    return "normal"


def uncertainty_regime(epu_snap, gpr_snap):
    """'elevated' if either index is in its top decile, or both are in their top quintile,
    measured on 30-day means against the trailing 10-year history."""
    return _regime([snap["percentile_10y"] if snap else None for snap in (epu_snap, gpr_snap)])


def downgrade_confidence(confidence, regime):
    """Elevated uncertainty lowers trust in views by one notch; it never raises it."""
    if regime != "elevated":
        return confidence
    return {"High": "Medium", "Medium": "Low", "Low": "Low"}[confidence]


def regime_series(indexes):
    """Point-in-time regime flag for every date in `indexes` (for the backtest).

    Uses only data up to each date: rolling 30-day mean ranked against the trailing 10-year
    window of that same rolling mean.
    """
    out = {}
    for col in indexes.columns:
        s = indexes[col].dropna()
        smooth = s.rolling(SMOOTH_DAYS).mean()
        window = int(252 * LOOKBACK_YEARS * 365 / 252)  # calendar days ~ observations here (daily incl. weekends)
        rank = smooth.rolling(window, min_periods=SMOOTH_DAYS * 12).rank(pct=True) * 100
        out[col + "_pctl"] = rank
    df = pd.DataFrame(out)
    df["regime"] = [_regime(row) for row in df.values.tolist()]
    return df


if __name__ == "__main__":
    data = load_all()
    print(data.tail(3))
    e, g = snapshot(data["EPU"]), snapshot(data["GPR"])
    print("EPU", e)
    print("GPR", g)
    print("regime:", uncertainty_regime(e, g))
