"""Append-only dated store, one CSV per series under data/store/.

Rows are never edited or deleted. Each row records the date the value describes and
the time we fetched it, so the store can answer "what did we know on day X".

vintage
  backfill  history loaded the first time a series was seen. It is the source's history
            as published on that day, so it may contain later revisions.
  live      a new date, first seen on a later run. This is true point-in-time data.
  revision  a date we already held, republished with a different value.
"""
import csv
import json
import os
from datetime import datetime, timezone

import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE_DIR = os.path.join(BASE_DIR, "data", "store")
COLUMNS = ["date", "value", "vintage", "fetched_at", "plugin"]
SOURCES_FILE = "sources.json"   # where each series came from, kept once instead of on every row


def _path(series, store_dir=None):
    return os.path.join(store_dir or STORE_DIR, f"{series}.csv")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read(series, store_dir=None):
    """Every stored row for a series, oldest fetch first."""
    path = _path(series, store_dir)
    if not os.path.exists(path):
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(path, dtype={"date": str, "vintage": str, "fetched_at": str, "plugin": str})


def append(readings, plugin, store_dir=None, fetched_at=None):
    """Add readings that are new or changed. Returns counts per vintage."""
    fetched_at = fetched_at or _now()
    os.makedirs(store_dir or STORE_DIR, exist_ok=True)
    counts = {"backfill": 0, "live": 0, "revision": 0}
    by_series = {}
    for r in readings:
        by_series.setdefault(r.series, []).append(r)
    for series, items in by_series.items():
        existing = read(series, store_dir)
        first_time = existing.empty
        latest = {}
        if not first_time:
            latest = existing.groupby("date")["value"].last().to_dict()
        rows = []
        for r in sorted(items, key=lambda x: x.date):
            value = float(r.value)
            if value != value:      # NaN
                continue
            if r.date in latest:
                if abs(latest[r.date] - value) <= 1e-9:
                    continue
                vintage = "revision"
            else:
                vintage = "backfill" if first_time else "live"
            latest[r.date] = value
            counts[vintage] += 1
            rows.append([r.date, repr(value), vintage, fetched_at, plugin])
        if not rows:
            continue
        _record_sources(series, {r.source for r in items}, store_dir)
        path = _path(series, store_dir)
        new_file = not os.path.exists(path)
        with open(path, "a", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            if new_file:
                writer.writerow(COLUMNS)
            writer.writerows(rows)
    return counts


def _record_sources(series, sources, store_dir=None):
    path = os.path.join(store_dir or STORE_DIR, SOURCES_FILE)
    try:
        with open(path, encoding="utf-8") as fh:
            known = json.load(fh)
    except (OSError, ValueError):
        known = {}
    merged = sorted(set(known.get(series, [])) | set(sources))
    if merged != known.get(series):
        known[series] = merged
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(known, fh, indent=1, sort_keys=True)


def series(name, as_of=None, store_dir=None):
    """Value per date as known at `as_of` (a fetch timestamp or date). Default: latest."""
    df = read(name, store_dir)
    if df.empty:
        return pd.Series(dtype=float, name=name)
    if as_of is not None:
        df = df[df["fetched_at"] <= str(as_of)]
    s = df.groupby("date")["value"].last()
    s.index = pd.to_datetime(s.index)
    return s.sort_index().rename(name)


def stats(name, store_dir=None):
    df = read(name, store_dir)
    if df.empty:
        return {"rows": 0, "live": 0, "backfill": 0, "revision": 0, "first": None, "last": None}
    v = df["vintage"].value_counts().to_dict()
    return {"rows": int(len(df)), "live": int(v.get("live", 0)), "backfill": int(v.get("backfill", 0)),
            "revision": int(v.get("revision", 0)), "first": df["date"].min(), "last": df["date"].max()}
