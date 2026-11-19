"""Deterministic risk score. Fixed arithmetic on stored readings, no language model.

For each signal:
  S  strength      how far today's reading is from its own normal, |z| / 3, capped at 1
  R  trust         set by hand in alerts.py
  P  path          0.7 ** (steps - 1), from the causal map
  H  track record  when this signal pointed the same way before, how often the target
                   then jumped, compared with how often it jumps anyway

  points = max_points * R * S * P * H * direction
  score  = base + sum of points, kept between 0 and 100

The score is a gauge, not a probability.
"""
import numpy as np
import pandas as pd

Z_CAP = 3.0            # |z| at which S reaches 1
PATH_DECAY = 0.7
EVENT_Z = 1.0          # a signal "pointed at the risk" when its signed z was at least this
MIN_EVENTS = 20        # fewer past events than this: H falls back to H_DEFAULT
H_DEFAULT = 0.5
RANGE_BASE = 8         # half-width of the range, in score points
RANGE_EXTRA = 12       # added in proportion to the share of signals with no usable track record
HIGH, MODERATE = 65, 40


def transform(s, kind):
    if kind == "level":
        return s
    if kind == "chg20":
        return s - s.shift(20)
    if kind == "mean30":
        return s.rolling(30, min_periods=20).mean()
    raise ValueError(f"unknown transform: {kind}")


def zscore(x, window):
    """Distance from the mean of the previous `window` days, in standard deviations.
    Today is excluded from its own baseline."""
    past = x.shift(1)
    mean = past.rolling(window, min_periods=window // 2).mean()
    std = past.rolling(window, min_periods=window // 2).std()
    return (x - mean) / std.replace(0, np.nan)


def track_record(signed_z, outcome):
    """H from past data only. `outcome` is NaN where the future is not known yet."""
    known = outcome.notna()
    events = known & (signed_z >= EVENT_Z)
    n = int(events.sum())
    base_rate = float(outcome[known].mean()) if known.any() else float("nan")
    if n < MIN_EVENTS or not base_rate > 0:
        return {"H": H_DEFAULT, "events": n, "hit_rate": None,
                "base_rate": None if base_rate != base_rate else round(base_rate, 3), "default": True}
    hit_rate = float(outcome[events].mean())
    h = float(np.clip((hit_rate / base_rate) / 2.0, 0.1, 1.0))
    return {"H": round(h, 3), "events": n, "hit_rate": round(hit_rate, 3),
            "base_rate": round(base_rate, 3), "default": False}


def level_of(score):
    return "high" if score >= HIGH else ("moderate" if score >= MODERATE else "low")


def score_alert(alert, get_series, as_of=None):
    """Score one alert.

    get_series(name) returns a date-indexed pandas Series, or an empty one.
    as_of limits the calculation to dates on or before that day (for replays).
    """
    target = get_series(alert["target"]).dropna()
    if as_of is not None:
        target = target[target.index <= pd.Timestamp(as_of)]
    if len(target) < alert["horizon"] + 60:
        return {"id": alert["id"], "title": alert["title"], "status": "no target history",
                "score": None, "drivers": []}
    days = target.index
    future = target.shift(-alert["horizon"]) - target
    outcome = (future >= alert["threshold"]).astype(float).where(future.notna())

    drivers, total, defaults, usable = [], 0.0, 0, 0
    for sig in alert["signals"]:
        raw = get_series(sig["series"]).dropna()
        if as_of is not None:
            raw = raw[raw.index <= pd.Timestamp(as_of)]
        row = {"id": sig["id"], "label": sig["label"], "series": sig["series"], "status": "ok"}
        if raw.empty:
            row.update(status="no data", points=0.0)
            drivers.append(row)
            defaults += 1
            continue
        x = transform(raw, sig["transform"]).reindex(days, method="ffill")
        z = zscore(x, sig["window"])
        z_now = z.iloc[-1]
        if z_now != z_now:
            row.update(status="not enough history", points=0.0)
            drivers.append(row)
            defaults += 1
            continue
        usable += 1
        signed = sig["sign"] * z
        rec = track_record(signed, outcome)
        if rec["default"]:
            defaults += 1
        s = float(min(abs(z_now) / Z_CAP, 1.0))
        p = PATH_DECAY ** (sig["steps"] - 1)
        direction = 1.0 if signed.iloc[-1] > 0 else (-1.0 if signed.iloc[-1] < 0 else 0.0)
        points = alert["max_points"] * sig["trust"] * s * p * rec["H"] * direction
        total += points
        row.update({
            "reading_date": str(raw.index[-1].date()), "reading": round(float(raw.iloc[-1]), 4),
            "z": round(float(z_now), 2), "R": sig["trust"], "S": round(s, 3), "P": round(p, 3),
            "H": rec["H"], "H_default": rec["default"], "events": rec["events"],
            "hit_rate": rec["hit_rate"], "base_rate": rec["base_rate"],
            "points": round(points, 1),
            "text": f"{sig['label']} is {abs(z_now):.1f} standard deviations "
                    f"{'above' if z_now > 0 else 'below'} its normal",
        })
        drivers.append(row)

    score = int(round(float(np.clip(alert["base"] + total, 0, 100))))
    n = len(alert["signals"])
    half = RANGE_BASE + RANGE_EXTRA * (defaults / n if n else 1.0)
    drivers.sort(key=lambda d: -abs(d.get("points", 0.0)))
    return {
        "id": alert["id"], "title": alert["title"], "status": "ok" if usable else "no usable signals",
        "as_of": str(days[-1].date()), "target": alert["target"],
        "target_value": round(float(target.iloc[-1]), 3),
        "horizon_days": alert["horizon"], "threshold": alert["threshold"],
        "score": score, "low": int(max(0, round(score - half))), "high": int(min(100, round(score + half))),
        "level": level_of(score), "base": alert["base"],
        "signals_used": usable, "signals_total": n,
        "drivers": drivers,
        "note": "Risk score out of 100 with a range. It is a gauge, not a probability.",
    }
