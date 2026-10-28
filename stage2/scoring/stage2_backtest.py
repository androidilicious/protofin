#!/usr/bin/env python3
"""Canonical reconstruction of the frozen Stage-2 A/B forecast scorer.

Duke MIDS / BNY Macro-Financial Capstone
Freeze version: Stage 2 v2.0 (2026-10-27)

IMPORTANT
---------
This file is a reconstruction from the frozen methodology/config and the saved
Stage-2 development result summary. The earlier development scorer was executed
but was not preserved as a standalone source file, so this file must NOT be
represented as byte-for-byte identical to that earlier ephemeral implementation.

The purpose of this implementation is to make the experiment auditable and
reproducible going forward. It deliberately keeps the historical test locked by
default and includes a development-result comparison step.

Implemented scope
-----------------
* Systems A, B1, B2, B3, B4, B5, B-All.
* Exact frozen decision/holding timing.
* t-2 outer-label rule.
* Expanding Ridge with an unpenalized intercept.
* Training-fold-only feature scaling; missing -> 0 only after scaling.
* Expanding one-step-ahead inner CV with a one-month purge.
* Frozen alpha grid including INTERCEPT_ONLY.
* Forecast benchmark and primary forecast metrics.
* Normalized pooled squared-error contrasts.
* Paired circular moving-block bootstrap over months.
* SHA-256 run manifest and optional expected-hash enforcement.
* Historical-test hard gate.
* Secondary evidence: the frozen Black-Litterman portfolio layer, portfolio
  benchmarks and secondary metrics (``stage2_portfolio.py``). Details the freeze
  leaves open are fixed, before any portfolio result was computed, in
  stage2/methodology/Stage2_Portfolio_Conventions_v1.md.

Status
------
Adopted on 2026-10-27 as the canonical Stage-2 reference implementation; see
stage2/methodology/Stage2_Canonical_Scorer_Adoption_2026-10-27.md.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

import stage2_portfolio as s2p


# -----------------------------------------------------------------------------
# Frozen experiment constants
# -----------------------------------------------------------------------------

ASSETS: Tuple[str, ...] = ("SPY", "IEF", "LQD")
MACRO_FEATURES: Tuple[str, ...] = (
    "nfp_z",
    "retail_sales_z",
    "industrial_production_z",
    "ism_manufacturing_z",
    "cpi_z",
    "core_cpi_z",
    "ppi_z",
    "ahe_z",
)

SYSTEMS: Tuple[str, ...] = ("A", "B1", "B2", "B3", "B4", "B5", "B-All")

B_FEATURES: Mapping[str, Tuple[str, ...]] = {
    "A": (),
    "B1": ("credit_level",),
    "B2": ("credit_change_3m",),
    "B3": ("curve_10y_3m",),
    "B4": ("vrp_proxy",),
    "B5": ("own_asset_momentum_12m",),
    "B-All": (
        "credit_level",
        "credit_change_3m",
        "curve_10y_3m",
        "vrp_proxy",
        "own_asset_momentum_12m",
    ),
}

DEV_START = pd.Period("2019-03", freq="M")
DEV_END = pd.Period("2022-12", freq="M")
HIST_START = pd.Period("2023-01", freq="M")
HIST_END = pd.Period("2026-08", freq="M")
MACRO_START = pd.Period("2015-02", freq="M")

MIN_OUTER_LABELS = 48
MIN_INNER_LABELS = 36
INNER_PURGE_MONTHS = 1
INNER_STRIDE = 1

ALPHAS: Tuple[Any, ...] = (
    1e-4,
    1e-2,
    1.0,
    1e2,
    1e4,
    1e6,
    1e8,
    1e10,
    "INTERCEPT_ONLY",
)

BOOTSTRAP_BLOCK_MONTHS = 6
BOOTSTRAP_REPS = 5000
BOOTSTRAP_SEED = 20261027

# Operational convention inherited from the saved Stage-1 implementation.
# The Stage-2 freeze says "mean/std" but does not state ddof for MODEL scaling.
# This is separate from macro-surprise construction, which is explicitly ddof=1.
MODEL_SCALER_DDOF = 0

# Conservative BAA10Y availability rule frozen in the source snapshot manifest.
BAA10Y_AVAILABILITY_LAG_DAYS = 5

# Splice factors frozen in the data snapshot manifest. Only needed when the
# supplied pre-2018 adjusted-price segment is on a different level scale.
DEFAULT_PRE2018_SCALE = {
    "SPY": 0.9837908780846654,
    "IEF": 0.8567598076451666,
    "LQD": 0.8061661485414546,
}
DEFAULT_SPLICE_DATE = pd.Timestamp("2018-01-02")


# -----------------------------------------------------------------------------
# Errors and helpers
# -----------------------------------------------------------------------------


class Stage2Error(RuntimeError):
    """Base error for a hard Stage-2 integrity or scoring failure."""


class IntegrityError(Stage2Error):
    """Raised when a frozen/integrity invariant is violated."""


class HistoricalTestLocked(Stage2Error):
    """Raised when a historical score is attempted without an explicit GO gate."""


def period(value: Any) -> pd.Period:
    """Parse any YYYY-MM-like value safely as a monthly Period."""
    if isinstance(value, pd.Period):
        return value.asfreq("M")
    return pd.Period(str(value)[:7], freq="M")


def month_str(value: Any) -> str:
    return str(period(value))


def month_add(value: Any, n: int) -> pd.Period:
    """Safe calendar-month arithmetic (prevents the prior January-minus bug)."""
    return period(value) + int(n)


def month_range(start: Any, end: Any) -> List[pd.Period]:
    s, e = period(start), period(end)
    if e < s:
        return []
    return list(pd.period_range(s, e, freq="M"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_json_dump(obj: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _read_delimited(path: Path, sep: Optional[str] = None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    if sep is None:
        sep = "\t" if path.suffix.lower() in {".tsv", ".tab"} else ","
    try:
        return pd.read_csv(path, sep=sep)
    except Exception as exc:
        raise Stage2Error(f"Could not read {path}: {exc}") from exc


def _find_col(df: pd.DataFrame, candidates: Sequence[str], required: bool = True) -> Optional[str]:
    norm = {str(c).strip().lower().replace("_", " "): c for c in df.columns}
    for cand in candidates:
        key = cand.strip().lower().replace("_", " ")
        if key in norm:
            return str(norm[key])
    # loose normalized alphanumeric pass
    def key2(x: str) -> str:
        return "".join(ch for ch in x.lower() if ch.isalnum())
    norm2 = {key2(str(c)): c for c in df.columns}
    for cand in candidates:
        if key2(cand) in norm2:
            return str(norm2[key2(cand)])
    if required:
        raise IntegrityError(f"Missing required column. Tried {list(candidates)}; found {list(df.columns)}")
    return None


def _numeric(series: pd.Series) -> pd.Series:
    # FRED-style missing marker '.': coerce to NaN.
    return pd.to_numeric(series.replace({".": np.nan, "": np.nan, "NA": np.nan, "N/A": np.nan}), errors="coerce")


def _date_series(series: pd.Series) -> pd.Series:
    out = pd.to_datetime(series, errors="coerce", utc=True)
    # Date-only semantics: normalize in UTC, then remove timezone for simple joins.
    return out.dt.tz_convert(None).dt.normalize()


# -----------------------------------------------------------------------------
# Run-spec and hash handling
# -----------------------------------------------------------------------------


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_paths_in_spec(node: Any, prefix: str = "spec") -> Iterable[Tuple[str, Path, Optional[str]]]:
    """Yield (logical_name, path, expected_sha256) for file objects in a run spec.

    A file object may look like:
      {"path": "/x/file.csv", "expected_sha256": "...", ...}
    Nested arrays/dicts are supported.
    """
    if isinstance(node, Mapping):
        if "path" in node and isinstance(node["path"], str):
            yield prefix, Path(os.path.expanduser(node["path"])), node.get("expected_sha256")
        for k, v in node.items():
            if k not in {"path", "expected_sha256"}:
                yield from _iter_paths_in_spec(v, f"{prefix}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _iter_paths_in_spec(v, f"{prefix}[{i}]")


def verify_and_hash_inputs(spec: Mapping[str, Any], scorer_path: Path, spec_path: Path) -> Dict[str, Any]:
    files: List[Dict[str, Any]] = []
    seen: set[Path] = set()
    for logical, p, expected in _iter_paths_in_spec(spec):
        p = p.resolve()
        if p in seen:
            continue
        seen.add(p)
        if not p.exists():
            raise IntegrityError(f"Required input does not exist: {logical} -> {p}")
        actual = sha256_file(p)
        if expected and actual.lower() != str(expected).lower():
            raise IntegrityError(
                f"SHA-256 mismatch for {logical}: {p}\n"
                f" expected={expected}\n actual={actual}"
            )
        files.append({"logical_name": logical, "path": str(p), "sha256": actual, "expected_sha256": expected})

    files.append({"logical_name": "run_spec", "path": str(spec_path.resolve()), "sha256": sha256_file(spec_path)})
    files.append({"logical_name": "scorer_source", "path": str(scorer_path.resolve()), "sha256": sha256_file(scorer_path)})
    return {"files": sorted(files, key=lambda x: x["logical_name"])}


# -----------------------------------------------------------------------------
# Data loading
# -----------------------------------------------------------------------------


def load_macro_panel(file_cfg: Mapping[str, Any]) -> pd.DataFrame:
    """Load the monthly same-definition macro panel WITHOUT dropping no-release rows."""
    p = Path(os.path.expanduser(str(file_cfg["path"])))
    df = _read_delimited(p, file_cfg.get("sep"))

    month_col = file_cfg.get("month_column") or _find_col(df, ["month", "decision_month"])
    out = pd.DataFrame({"month": df[month_col].map(period)})
    for c in MACRO_FEATURES:
        if c not in df.columns:
            raise IntegrityError(f"Macro panel is missing frozen feature column {c!r}")
        out[c] = _numeric(df[c])

    if out["month"].duplicated().any():
        dup = sorted({str(x) for x in out.loc[out["month"].duplicated(keep=False), "month"]})
        raise IntegrityError(f"Macro panel has duplicate monthly rows: {dup[:12]}")
    out = out.sort_values("month").reset_index(drop=True)
    if len(out) == 0:
        raise IntegrityError("Macro panel is empty after parsing")

    # Stage-2 same-definition sample starts at 2015-02.
    out = out[out["month"] >= MACRO_START].copy().reset_index(drop=True)

    # Calendar completeness is a frozen-methodology invariant: a no-release
    # indicator is missing *inside* a retained month; the month itself is not dropped.
    expected = month_range(out["month"].min(), out["month"].max())
    actual = set(out["month"])
    missing_months = [str(m) for m in expected if m not in actual]
    if missing_months and not bool(file_cfg.get("allow_incomplete_calendar_for_diagnostic", False)):
        raise IntegrityError(
            "Macro panel drops whole calendar months, which violates the Stage-2 no-release rule. "
            f"Missing month rows include: {missing_months[:12]}"
        )

    # Explicit regression check for the known 2019-01 shutdown month whenever
    # the panel spans that date.
    jan19 = pd.Period("2019-01", freq="M")
    if out["month"].min() <= jan19 <= out["month"].max():
        row = out[out["month"] == jan19]
        if row.empty:
            if not bool(file_cfg.get("allow_incomplete_calendar_for_diagnostic", False)):
                raise IntegrityError(
                    "2019-01 is absent. It must be retained with retail_sales_z missing; do not drop the whole month."
                )
        elif pd.notna(row.iloc[0]["retail_sales_z"]):
            # Do not hard fail if a later corrected source legitimately contains a first-print
            # release available by that decision date; instead require explicit override.
            if not bool(file_cfg.get("allow_2019_01_retail_value", False)):
                raise IntegrityError(
                    "2019-01 retail_sales_z is non-missing. The audited frozen panel had no January retail-sales "
                    "release; set allow_2019_01_retail_value=true only with documented point-in-time evidence."
                )

    return out


def load_series_file(
    cfg: Mapping[str, Any],
    *,
    value_candidates: Sequence[str],
    date_candidates: Sequence[str] = ("date", "DATE", "Date", "observation_date", "timestamp", "datetime"),
) -> pd.DataFrame:
    p = Path(os.path.expanduser(str(cfg["path"])))
    df = _read_delimited(p, cfg.get("sep"))
    date_col = cfg.get("date_column") or _find_col(df, date_candidates)
    value_col = cfg.get("value_column") or _find_col(df, value_candidates)
    out = pd.DataFrame({"date": _date_series(df[date_col]), "value": _numeric(df[value_col])})
    out = out.dropna(subset=["date", "value"]).drop_duplicates("date", keep="last").sort_values("date")
    if out.empty:
        raise IntegrityError(f"No valid date/value observations in {p}")
    return out.reset_index(drop=True)


def load_series_segment(cfg: Mapping[str, Any], *, value_candidates: Sequence[str]) -> pd.DataFrame:
    out = load_series_file(cfg, value_candidates=value_candidates)
    if "start_inclusive" in cfg:
        out = out[out["date"] >= pd.Timestamp(cfg["start_inclusive"])]
    if "end_exclusive" in cfg:
        out = out[out["date"] < pd.Timestamp(cfg["end_exclusive"])]
    if out.empty:
        raise IntegrityError(f"Series segment is empty after date filters: {cfg.get('path')}")
    return out.reset_index(drop=True)


def load_price_segment(cfg: Mapping[str, Any]) -> pd.DataFrame:
    """Load one adjusted-price / total-return-level segment."""
    candidates = (
        "adjusted_close",
        "adj_close",
        "adj close",
        "Adj Close",
        "adjclose",
        "adjusted",
        "total_return_index",
        "total return index",
        "close_adjusted",
    )
    try:
        out = load_series_file(cfg, value_candidates=candidates)
    except IntegrityError:
        # Close is allowed only with an explicit acknowledgement in the spec.
        if not cfg.get("allow_close_as_adjusted", False):
            raise IntegrityError(
                f"Price input {cfg.get('path')} has no recognized adjusted/total-return column. "
                "Do not silently use raw Close. If the supplied 'Close' is already distribution-adjusted, "
                "set allow_close_as_adjusted=true and document it."
            )
        out = load_series_file(cfg, value_candidates=("close", "Close"))

    if "start_inclusive" in cfg:
        out = out[out["date"] >= pd.Timestamp(cfg["start_inclusive"])]
    if "end_exclusive" in cfg:
        out = out[out["date"] < pd.Timestamp(cfg["end_exclusive"])]
    scale = float(cfg.get("scale", 1.0))
    out["value"] *= scale
    if (out["value"] <= 0).any():
        raise IntegrityError(f"Non-positive adjusted price/total-return level in {cfg.get('path')}")
    return out


def load_asset_prices(asset: str, cfg: Mapping[str, Any]) -> pd.Series:
    segments_cfg = cfg.get("segments")
    if not segments_cfg:
        segments_cfg = [cfg]

    parts = [load_price_segment(s) for s in segments_cfg]
    out = pd.concat(parts, ignore_index=True).sort_values("date")
    # Later segment wins at overlaps.
    out = out.drop_duplicates("date", keep="last")
    out = out.set_index("date")["value"].sort_index().astype(float)
    out.name = asset
    if not out.index.is_monotonic_increasing or out.index.has_duplicates:
        raise IntegrityError(f"Bad price index for {asset}")
    return out


def load_market_prices(prices_cfg: Mapping[str, Any]) -> Dict[str, pd.Series]:
    missing = [a for a in ASSETS if a not in prices_cfg]
    if missing:
        raise IntegrityError(f"Run spec is missing price configuration for {missing}")
    return {a: load_asset_prices(a, prices_cfg[a]) for a in ASSETS}


def common_trading_calendar(prices: Mapping[str, pd.Series]) -> pd.DatetimeIndex:
    common: Optional[pd.DatetimeIndex] = None
    for a in ASSETS:
        idx = pd.DatetimeIndex(prices[a].index)
        common = idx if common is None else common.intersection(idx)
    assert common is not None
    common = common.sort_values()
    if len(common) == 0:
        raise IntegrityError("No common trading dates across SPY/IEF/LQD")
    return common


def build_decision_calendar(common_dates: pd.DatetimeIndex) -> Dict[pd.Period, pd.Timestamp]:
    s = pd.Series(common_dates, index=common_dates)
    by_month: Dict[pd.Period, pd.Timestamp] = {}
    for m, grp in s.groupby(common_dates.to_period("M")):
        by_month[pd.Period(m, freq="M")] = pd.Timestamp(grp.iloc[-1]).normalize()
    return by_month


def first_common_day_after_month_end(month: pd.Period, common_dates: pd.DatetimeIndex) -> pd.Timestamp:
    cutoff = month.end_time.normalize()
    candidates = common_dates[common_dates > cutoff]
    if len(candidates) == 0:
        raise IntegrityError(f"No common trading day after month-end {month}")
    return pd.Timestamp(candidates[0]).normalize()


# -----------------------------------------------------------------------------
# Risk-free return: DTB4WK operationalization used in the saved development run
# -----------------------------------------------------------------------------


def dtb4wk_28d_effective_return(discount_quote_percent: float) -> float:
    """Convert a 4-week T-bill bank-discount quote (%) to a 28-day effective return.

    Bank-discount yield d: price = 1 - (d/100)*(28/360).
    Holding-period return = (1-price)/price.
    """
    d = float(discount_quote_percent) / 100.0
    discount = d * 28.0 / 360.0
    price = 1.0 - discount
    if not (price > 0):
        raise IntegrityError(f"Invalid DTB4WK quote {discount_quote_percent}: implied bill price <= 0")
    return discount / price


def accrue_dtb4wk(discount_quote_percent: float, calendar_days: int) -> float:
    if calendar_days < 0:
        raise IntegrityError("calendar_days cannot be negative")
    r28 = dtb4wk_28d_effective_return(discount_quote_percent)
    return (1.0 + r28) ** (float(calendar_days) / 28.0) - 1.0


def asof_value(series_df: pd.DataFrame, on_date: pd.Timestamp, *, max_staleness_days: Optional[int] = None) -> Tuple[float, pd.Timestamp]:
    eligible = series_df[series_df["date"] <= pd.Timestamp(on_date).normalize()]
    if eligible.empty:
        raise IntegrityError(f"No observation available on or before {on_date.date()}")
    row = eligible.iloc[-1]
    obs_date = pd.Timestamp(row["date"])
    if max_staleness_days is not None and (pd.Timestamp(on_date).normalize() - obs_date).days > max_staleness_days:
        raise IntegrityError(
            f"Last observation {obs_date.date()} is too stale for {pd.Timestamp(on_date).date()} "
            f"(>{max_staleness_days} days)"
        )
    return float(row["value"]), obs_date


def interval_rf_return(dtb4wk: pd.DataFrame, start_date: pd.Timestamp, end_date: pd.Timestamp) -> float:
    """Development-run rule: quote at period start, accrue over exact calendar days."""
    if end_date <= start_date:
        raise IntegrityError(f"RF interval must be positive: {start_date} -> {end_date}")
    quote, _ = asof_value(dtb4wk, start_date, max_staleness_days=10)
    days = int((end_date - start_date).days)
    return accrue_dtb4wk(quote, days)


# -----------------------------------------------------------------------------
# Frozen B-signal construction
# -----------------------------------------------------------------------------


def monthly_asof_with_availability_lag(
    raw: pd.DataFrame,
    decision_dates: Mapping[pd.Period, pd.Timestamp],
    lag_days: int,
) -> Dict[pd.Period, float]:
    tmp = raw.copy()
    tmp["available_at"] = tmp["date"] + pd.to_timedelta(int(lag_days), unit="D")
    out: Dict[pd.Period, float] = {}
    for m, d in decision_dates.items():
        eligible = tmp[tmp["available_at"] <= d]
        if not eligible.empty:
            out[m] = float(eligible.iloc[-1]["value"])
    return out


def monthly_asof_same_day(
    raw: pd.DataFrame,
    decision_dates: Mapping[pd.Period, pd.Timestamp],
) -> Dict[pd.Period, float]:
    out: Dict[pd.Period, float] = {}
    for m, d in decision_dates.items():
        eligible = raw[raw["date"] <= d]
        if not eligible.empty:
            out[m] = float(eligible.iloc[-1]["value"])
    return out


def monthly_vix_exact_day(
    vix: pd.DataFrame,
    decision_dates: Mapping[pd.Period, pd.Timestamp],
    months: Iterable[pd.Period],
) -> Dict[pd.Period, float]:
    by_date = vix.set_index("date")["value"]
    out: Dict[pd.Period, float] = {}
    for m in months:
        d = decision_dates.get(m)
        if d is None:
            continue
        if d not in by_date.index:
            raise IntegrityError(
                f"No VIX close on decision trading date {d.date()} ({m}); frozen B4 requires end-of-day VIX."
            )
        out[m] = float(by_date.loc[d])
    return out


def build_vrp(
    spy: pd.Series,
    vix: pd.DataFrame,
    decision_dates: Mapping[pd.Period, pd.Timestamp],
    months: Iterable[pd.Period],
) -> Dict[pd.Period, float]:
    logret = np.log(spy.astype(float)).diff().dropna()
    vix_by_month = monthly_vix_exact_day(vix, decision_dates, months)
    out: Dict[pd.Period, float] = {}
    for m in months:
        if m not in vix_by_month or m not in decision_dates:
            continue
        d = decision_dates[m]
        trailing = logret[logret.index <= d].tail(22)
        if len(trailing) != 22:
            continue
        realized_var = float(np.sum(np.square(trailing.to_numpy())) * 10000.0)
        out[m] = float(vix_by_month[m] ** 2 / 12.0 - realized_var)
    return out


def build_momentum_12m(
    asset_prices: pd.Series,
    dtb4wk: pd.DataFrame,
    decision_dates: Mapping[pd.Period, pd.Timestamp],
    months: Iterable[pd.Period],
) -> Dict[pd.Period, float]:
    """Own-asset 12M excess total return ending at the decision snapshot.

    Asset leg: adjusted/total-return level from month-end decision t-12 to t.
    Cash leg: compound the frozen DTB4WK rule across each adjacent month-end
    decision-date subperiod ("rolls the same rule month-end to month-end").
    """
    out: Dict[pd.Period, float] = {}
    for m in months:
        old = month_add(m, -12)
        if old not in decision_dates or m not in decision_dates:
            continue
        d0, d1 = decision_dates[old], decision_dates[m]
        if d0 not in asset_prices.index or d1 not in asset_prices.index:
            continue
        asset_return = float(asset_prices.loc[d1] / asset_prices.loc[d0] - 1.0)
        cash_gross = 1.0
        ok = True
        for k in range(12):
            mk0 = month_add(old, k)
            mk1 = month_add(old, k + 1)
            if mk0 not in decision_dates or mk1 not in decision_dates:
                ok = False
                break
            cash_gross *= 1.0 + interval_rf_return(dtb4wk, decision_dates[mk0], decision_dates[mk1])
        if ok:
            out[m] = asset_return - (cash_gross - 1.0)
    return out


def build_signal_table(
    prices: Mapping[str, pd.Series],
    decision_dates: Mapping[pd.Period, pd.Timestamp],
    baa10y: pd.DataFrame,
    curve: pd.DataFrame,
    vix: pd.DataFrame,
    dtb4wk: pd.DataFrame,
    all_months: Sequence[pd.Period],
) -> Dict[str, pd.DataFrame]:
    """Return one monthly signal table per asset (momentum is asset-specific)."""
    credit = monthly_asof_with_availability_lag(baa10y, decision_dates, BAA10Y_AVAILABILITY_LAG_DAYS)
    curve_m = monthly_asof_same_day(curve, decision_dates)
    vrp = build_vrp(prices["SPY"], vix, decision_dates, all_months)

    asset_tables: Dict[str, pd.DataFrame] = {}
    for asset in ASSETS:
        mom = build_momentum_12m(prices[asset], dtb4wk, decision_dates, all_months)
        rows = []
        for m in all_months:
            c = credit.get(m, np.nan)
            c3 = credit.get(month_add(m, -3), np.nan)
            rows.append(
                {
                    "month": m,
                    "credit_level": c,
                    "credit_change_3m": c - c3 if np.isfinite(c) and np.isfinite(c3) else np.nan,
                    "curve_10y_3m": curve_m.get(m, np.nan),
                    "vrp_proxy": vrp.get(m, np.nan),
                    "own_asset_momentum_12m": mom.get(m, np.nan),
                }
            )
        asset_tables[asset] = pd.DataFrame(rows).set_index("month")
    return asset_tables


# -----------------------------------------------------------------------------
# Target construction
# -----------------------------------------------------------------------------


def build_targets(
    prices: Mapping[str, pd.Series],
    common_dates: pd.DatetimeIndex,
    decision_dates: Mapping[pd.Period, pd.Timestamp],
    dtb4wk: pd.DataFrame,
    months: Sequence[pd.Period],
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for m in months:
        if m not in decision_dates:
            continue
        entry = first_common_day_after_month_end(m, common_dates)
        exit_ = first_common_day_after_month_end(month_add(m, 1), common_dates)
        rf = interval_rf_return(dtb4wk, entry, exit_)
        for asset in ASSETS:
            s = prices[asset]
            if entry not in s.index or exit_ not in s.index:
                raise IntegrityError(f"{asset} missing required target price on {entry.date()} or {exit_.date()}")
            total_return = float(s.loc[exit_] / s.loc[entry] - 1.0)
            rows.append(
                {
                    "asset": asset,
                    "decision_month": m,
                    "decision_date": decision_dates[m],
                    "entry_date": entry,
                    "exit_date": exit_,
                    "asset_total_return": total_return,
                    "rf_return": rf,
                    "actual_excess_return": total_return - rf,
                }
            )
    if not rows:
        raise IntegrityError("No targets constructed")
    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# Model scaling, Ridge, and nested CV
# -----------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class FittedScaler:
    mean: np.ndarray
    std: np.ndarray


def fit_scaler(X: np.ndarray) -> FittedScaler:
    X = np.asarray(X, dtype=float)
    if X.ndim != 2:
        raise ValueError("X must be 2-D")
    p = X.shape[1]
    mu = np.zeros(p, dtype=float)
    sd = np.ones(p, dtype=float)
    for j in range(p):
        v = X[:, j]
        mask = np.isfinite(v)
        if mask.any():
            mu[j] = float(v[mask].mean())
            s = float(v[mask].std(ddof=MODEL_SCALER_DDOF))
            sd[j] = s if np.isfinite(s) and s > 1e-12 else 1.0
    return FittedScaler(mu, sd)


def transform_with_scaler(X: np.ndarray, scaler: FittedScaler) -> np.ndarray:
    arr = np.asarray(X, dtype=float)
    was_1d = arr.ndim == 1
    if was_1d:
        arr = arr[None, :]
    Z = (arr - scaler.mean) / scaler.std
    Z[~np.isfinite(arr)] = 0.0
    return Z[0] if was_1d else Z


def _alpha_strength(alpha: Any) -> float:
    return math.inf if alpha == "INTERCEPT_ONLY" else float(alpha)


def ridge_fit_predict(Xtr: np.ndarray, ytr: np.ndarray, x: np.ndarray, alpha: Any) -> Tuple[float, float]:
    Xtr = np.asarray(Xtr, dtype=float)
    ytr = np.asarray(ytr, dtype=float)
    x = np.asarray(x, dtype=float)
    if len(ytr) == 0:
        raise IntegrityError("Cannot fit Ridge with zero labels")
    scaler = fit_scaler(Xtr)
    Xz = transform_with_scaler(Xtr, scaler)
    xz = transform_with_scaler(x, scaler)
    ybar = float(np.mean(ytr))
    if alpha == "INTERCEPT_ONLY":
        return ybar, 0.0
    a = float(alpha)
    gram = Xz.T @ Xz + a * np.eye(Xz.shape[1])
    rhs = Xz.T @ (ytr - ybar)
    try:
        beta = np.linalg.solve(gram, rhs)
    except np.linalg.LinAlgError:
        beta = np.linalg.lstsq(gram, rhs, rcond=None)[0]
    pred = float(ybar + xz @ beta)
    return pred, float(np.linalg.norm(beta, ord=2))


def inner_splits(n: int, minimum_train: int = MIN_INNER_LABELS, purge: int = INNER_PURGE_MONTHS, stride: int = INNER_STRIDE) -> List[Tuple[np.ndarray, int]]:
    """Expanding one-step validation with a purge directly before validation.

    For validation index j, the purged rows are [j-purge, ..., j-1].
    Training is [0, ..., j-purge-1].
    """
    splits: List[Tuple[np.ndarray, int]] = []
    first_val = minimum_train + purge
    for j in range(first_val, n, stride):
        train_end_exclusive = j - purge
        train_idx = np.arange(0, train_end_exclusive, dtype=int)
        if len(train_idx) >= minimum_train:
            splits.append((train_idx, j))
    return splits


def choose_alpha(X: np.ndarray, y: np.ndarray) -> Tuple[Any, int, Dict[str, float]]:
    """Select the frozen Ridge alpha by purged expanding inner CV.

    All numeric alphas are evaluated from one eigendecomposition per fold. This
    is algebraically equivalent to solving each Ridge system separately but
    makes a full 7-system x 3-asset x 46-month development rerun practical.
    """
    splits = inner_splits(len(y))
    if not splits:
        raise IntegrityError(
            f"No valid inner folds with n={len(y)}, min_train={MIN_INNER_LABELS}, purge={INNER_PURGE_MONTHS}"
        )

    numeric_alphas = [float(a) for a in ALPHAS if a != "INTERCEPT_ONLY"]
    ses: Dict[Any, List[float]] = {a: [] for a in ALPHAS}

    for tr_idx, val_idx in splits:
        Xtr = np.asarray(X[tr_idx], dtype=float)
        ytr = np.asarray(y[tr_idx], dtype=float)
        xv = np.asarray(X[val_idx], dtype=float)

        sc = fit_scaler(Xtr)
        Xz = transform_with_scaler(Xtr, sc)
        xz = transform_with_scaler(xv, sc)
        ybar = float(np.mean(ytr))
        centered = ytr - ybar
        gram = Xz.T @ Xz
        rhs = Xz.T @ centered

        # gram is symmetric positive semidefinite. eigh is stable here and lets
        # us evaluate the complete alpha grid without repeating matrix solves.
        eigvals, eigvecs = np.linalg.eigh(gram)
        proj_rhs = eigvecs.T @ rhs
        x_proj = xz @ eigvecs
        yv = float(y[val_idx])

        for a in numeric_alphas:
            pred = ybar + float(np.sum(x_proj * (proj_rhs / (eigvals + a))))
            ses[a].append((yv - pred) ** 2)
        ses["INTERCEPT_ONLY"].append((yv - ybar) ** 2)

    losses: Dict[Any, float] = {a: float(np.mean(ses[a])) for a in ALPHAS}
    best = min(losses.values())
    tol = 1e-12 * max(1.0, abs(best))
    tied = [a for a, loss in losses.items() if loss <= best + tol]
    selected = max(tied, key=_alpha_strength)
    printable = {str(k): v for k, v in losses.items()}
    return selected, len(splits), printable


# -----------------------------------------------------------------------------
# Feature assembly and scoring
# -----------------------------------------------------------------------------


def feature_columns(system: str) -> Tuple[str, ...]:
    if system not in SYSTEMS:
        raise ValueError(system)
    return MACRO_FEATURES + B_FEATURES[system]


def assemble_asset_features(
    macro: pd.DataFrame,
    signals: Mapping[str, pd.DataFrame],
    asset: str,
) -> pd.DataFrame:
    m = macro.set_index("month")[list(MACRO_FEATURES)].copy()
    s = signals[asset]
    out = m.join(s, how="left")
    out.index = pd.PeriodIndex(out.index, freq="M")
    return out.sort_index()


def _target_map(targets: pd.DataFrame, asset: str) -> Dict[pd.Period, Dict[str, Any]]:
    rows = targets[targets["asset"] == asset]
    return {period(r.decision_month): r._asdict() for r in rows.itertuples(index=False)}


def score_system_asset(
    system: str,
    asset: str,
    Xdf: pd.DataFrame,
    targets: pd.DataFrame,
    score_months: Sequence[pd.Period],
) -> List[Dict[str, Any]]:
    cols = list(feature_columns(system))
    tmap = _target_map(targets, asset)
    rows: List[Dict[str, Any]] = []

    for dm in score_months:
        if dm not in Xdf.index:
            raise IntegrityError(f"Feature row missing for {asset}/{system}/{dm}")
        if dm not in tmap:
            raise IntegrityError(f"Target row missing for {asset}/{dm}")

        latest_train_month = month_add(dm, -2)
        train_months = [
            m
            for m in Xdf.index
            if MACRO_START <= m <= latest_train_month and m in tmap and np.isfinite(tmap[m]["actual_excess_return"])
        ]
        train_months = sorted(train_months)
        if len(train_months) < MIN_OUTER_LABELS:
            raise IntegrityError(
                f"Only {len(train_months)} completed labels for {asset}/{system}/{dm}; "
                f"need {MIN_OUTER_LABELS}. Latest allowed label={latest_train_month}."
            )
        if dm == DEV_START and len(train_months) != 48:
            raise IntegrityError(
                f"First development forecast must have exactly 48 labels (2015-02..2019-01); got {len(train_months)}. "
                "This usually means a no-release month was dropped."
            )

        Xtr = Xdf.loc[train_months, cols].to_numpy(dtype=float)
        ytr = np.array([float(tmap[m]["actual_excess_return"]) for m in train_months], dtype=float)
        x = Xdf.loc[dm, cols].to_numpy(dtype=float)

        alpha, n_folds, _ = choose_alpha(Xtr, ytr)
        pred, coef_l2 = ridge_fit_predict(Xtr, ytr, x, alpha)
        benchmark = float(np.mean(ytr))
        actual = float(tmap[dm]["actual_excess_return"])
        target_row = tmap[dm]
        rows.append(
            {
                "system": system,
                "asset": asset,
                "decision_month": str(dm),
                "decision_date": pd.Timestamp(target_row["decision_date"]).date().isoformat(),
                "entry_date": pd.Timestamp(target_row["entry_date"]).date().isoformat(),
                "exit_date": pd.Timestamp(target_row["exit_date"]).date().isoformat(),
                "n_train": len(train_months),
                "latest_train_month": str(latest_train_month),
                "alpha": str(alpha) if alpha == "INTERCEPT_ONLY" else float(alpha),
                "n_inner_folds": n_folds,
                "prediction_excess_return": pred,
                "actual_excess_return": actual,
                "benchmark_mean_excess_return": benchmark,
                "error": actual - pred,
                "benchmark_error": actual - benchmark,
                "coef_l2": coef_l2,
                "n_features": len(cols),
            }
        )
    return rows


def score_all_systems(
    macro: pd.DataFrame,
    signals: Mapping[str, pd.DataFrame],
    targets: pd.DataFrame,
    score_months: Sequence[pd.Period],
) -> pd.DataFrame:
    out: List[Dict[str, Any]] = []
    for system in SYSTEMS:
        for asset in ASSETS:
            Xdf = assemble_asset_features(macro, signals, asset)
            out.extend(score_system_asset(system, asset, Xdf, targets, score_months))
    pred = pd.DataFrame(out)
    expected = len(SYSTEMS) * len(ASSETS) * len(score_months)
    if len(pred) != expected:
        raise IntegrityError(f"Expected {expected} forecast rows; got {len(pred)}")
    # Common dates are mandatory.
    group_counts = pred.groupby(["system", "asset"])["decision_month"].nunique()
    if not (group_counts == len(score_months)).all():
        raise IntegrityError("Systems/assets do not share identical scoring dates")
    return pred


# -----------------------------------------------------------------------------
# Metrics and contrasts
# -----------------------------------------------------------------------------


def per_asset_metrics(pred: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for (system, asset), g in pred.groupby(["system", "asset"], sort=False):
        e = g["error"].to_numpy(float)
        be = g["benchmark_error"].to_numpy(float)
        actual = g["actual_excess_return"].to_numpy(float)
        forecast = g["prediction_excess_return"].to_numpy(float)
        mse = float(np.mean(e**2))
        bmse = float(np.mean(be**2))
        rel = mse / bmse if bmse > 0 else np.nan
        rows.append(
            {
                "system": system,
                "asset": asset,
                "n": len(g),
                "rmse": math.sqrt(mse),
                "mae": float(np.mean(np.abs(e))),
                "relative_mspe": rel,
                "oos_r2": 1.0 - rel if np.isfinite(rel) else np.nan,
                "directional_accuracy": float(np.mean(np.sign(forecast) == np.sign(actual))),
            }
        )
    return pd.DataFrame(rows)


def realized_variance_through_t_minus_2(
    pred: pd.DataFrame,
    targets: pd.DataFrame,
) -> Dict[Tuple[str, str], float]:
    """Expanding sample variance of realized excess-return labels available through t-2."""
    out: Dict[Tuple[str, str], float] = {}
    for asset in ASSETS:
        tg = targets[targets["asset"] == asset].copy()
        tg["decision_month"] = tg["decision_month"].map(period)
        ymap = dict(zip(tg["decision_month"], tg["actual_excess_return"].astype(float)))
        for dm_s in sorted(pred["decision_month"].unique()):
            dm = period(dm_s)
            end = month_add(dm, -2)
            vals = [
                float(v)
                for m, v in ymap.items()
                if MACRO_START <= m <= end and np.isfinite(v)
            ]
            if len(vals) < 2:
                raise IntegrityError(f"Insufficient variance history for {asset}/{dm}")
            v = float(np.var(vals, ddof=1))
            if not np.isfinite(v) or v <= 1e-18:
                raise IntegrityError(f"Degenerate expanding realized-return variance for {asset}/{dm}: {v}")
            out[(asset, str(dm))] = v
    return out


def circular_block_bootstrap_mean(
    monthly_values: Sequence[float],
    *,
    block: int = BOOTSTRAP_BLOCK_MONTHS,
    reps: int = BOOTSTRAP_REPS,
    seed: int = BOOTSTRAP_SEED,
) -> Dict[str, Any]:
    x = np.asarray(monthly_values, dtype=float)
    if x.ndim != 1 or len(x) == 0 or not np.isfinite(x).all():
        raise ValueError("monthly_values must be a nonempty finite 1-D array")
    T = len(x)
    rng = np.random.default_rng(seed)
    draws = np.empty(reps, dtype=float)
    nblocks = math.ceil(T / block)
    for b in range(reps):
        idx_parts = []
        starts = rng.integers(0, T, size=nblocks)
        for s in starts:
            idx_parts.extend((int(s) + k) % T for k in range(block))
        idx = np.array(idx_parts[:T], dtype=int)
        draws[b] = float(np.mean(x[idx]))
    return {
        "point_estimate": float(np.mean(x)),
        "ci90": [float(np.percentile(draws, 5)), float(np.percentile(draws, 95))],
        "ci95": [float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))],
        "bootstrap_prob_le_zero": float(np.mean(draws <= 0.0)),
        "block_months": block,
        "replications": reps,
        "seed": seed,
    }


def contrast_vs_A(
    pred: pd.DataFrame,
    targets: pd.DataFrame,
    system: str,
) -> Dict[str, Any]:
    if system == "A":
        raise ValueError("Contrast system must differ from A")
    a = pred[pred["system"] == "A"].copy()
    b = pred[pred["system"] == system].copy()
    keys = ["asset", "decision_month"]
    m = a[keys + ["error"]].merge(
        b[keys + ["error"]], on=keys, suffixes=("_A", "_B"), validate="one_to_one"
    )
    expected = len(a)
    if len(m) != expected:
        raise IntegrityError(f"Contrast {system} vs A lost rows: {len(m)} vs {expected}")

    variances = realized_variance_through_t_minus_2(pred, targets)
    m["variance"] = [variances[(r.asset, r.decision_month)] for r in m.itertuples()]
    # Positive = added system lowers normalized squared error relative to A.
    m["improvement"] = (m["error_A"] ** 2 - m["error_B"] ** 2) / m["variance"]
    monthly = m.groupby("decision_month", sort=True)["improvement"].mean()
    boot = circular_block_bootstrap_mean(monthly.to_numpy())
    return {
        "system": system,
        "normalized_pooled_se_improvement": boot["point_estimate"],
        "ci90": boot["ci90"],
        "ci95": boot["ci95"],
        "bootstrap_prob_le_zero": boot["bootstrap_prob_le_zero"],
        "n_months": len(monthly),
        "n_asset_months": len(m),
        "monthly_improvement": {str(k): float(v) for k, v in monthly.items()},
    }


def build_result_summary(pred: pd.DataFrame, targets: pd.DataFrame, mode: str) -> Dict[str, Any]:
    metrics = per_asset_metrics(pred)
    contrasts = {s: contrast_vs_A(pred, targets, s) for s in SYSTEMS if s != "A"}
    r2: Dict[str, Dict[str, float]] = {}
    for system in SYSTEMS:
        r2[system] = {
            asset: float(metrics[(metrics.system == system) & (metrics.asset == asset)].iloc[0].oos_r2)
            for asset in ASSETS
        }
    return {
        "status": "DEVELOPMENT_SCORED" if mode == "development" else "HISTORICAL_PSEUDO_OOS_SCORED",
        "mode": mode,
        "window": [pred["decision_month"].min(), pred["decision_month"].max()],
        "n_months": int(pred["decision_month"].nunique()),
        "historical_test_opened": mode == "historical",
        "rf_rule": (
            "DTB4WK bank-discount quote at period start; convert quoted 28-day bill to effective return and "
            "accrue over exact calendar holding days. Momentum cash leg rolls the same rule month-end to month-end."
        ),
        "primary_contrast_BAll_vs_A": contrasts["B-All"],
        "component_contrasts": {
            "B1_credit_level": contrasts["B1"],
            "B2_credit_change_3m": contrasts["B2"],
            "B3_curve_10y_3m": contrasts["B3"],
            "B4_vrp": contrasts["B4"],
            "B5_momentum": contrasts["B5"],
        },
        "per_asset_oos_r2": r2,
        "model_scaler_ddof": MODEL_SCALER_DDOF,
        "note": (
            "This summary was produced by the reconstructed canonical Stage-2 scorer. "
            "Compare development output against the saved 2026-10-27 summary before treating it as a reproduced run."
        ),
    }


# -----------------------------------------------------------------------------
# Development-result comparison
# -----------------------------------------------------------------------------


def _compare_number(path: str, got: float, expected: float, atol: float, diffs: List[Dict[str, Any]]) -> None:
    if not (np.isfinite(got) and np.isfinite(expected)) or not math.isclose(got, expected, abs_tol=atol, rel_tol=0.0):
        diffs.append({"field": path, "expected": expected, "got": got, "difference": got - expected})


def compare_to_saved_development(
    got: Mapping[str, Any],
    expected: Mapping[str, Any],
    atol: float = 1e-8,
) -> Dict[str, Any]:
    diffs: List[Dict[str, Any]] = []
    if int(got["n_months"]) != int(expected["n_months"]):
        diffs.append({"field": "n_months", "expected": expected["n_months"], "got": got["n_months"]})

    gp = got["primary_contrast_BAll_vs_A"]
    ep = expected["primary_contrast_BAll_vs_A"]
    _compare_number("BAll.point", gp["normalized_pooled_se_improvement"], ep["normalized_pooled_se_improvement"], atol, diffs)
    for i in range(2):
        _compare_number(f"BAll.ci90[{i}]", gp["ci90"][i], ep["ci90"][i], atol, diffs)
        _compare_number(f"BAll.ci95[{i}]", gp["ci95"][i], ep["ci95"][i], atol, diffs)
    _compare_number("BAll.prob_le_zero", gp["bootstrap_prob_le_zero"], ep["bootstrap_prob_le_zero"], atol, diffs)

    for name in ["B1_credit_level", "B2_credit_change_3m", "B3_curve_10y_3m", "B4_vrp", "B5_momentum"]:
        gg, ee = got["component_contrasts"][name], expected["component_contrasts"][name]
        _compare_number(f"{name}.point", gg["normalized_pooled_se_improvement"], ee["normalized_pooled_se_improvement"], atol, diffs)
        for i in range(2):
            _compare_number(f"{name}.ci90[{i}]", gg["ci90"][i], ee["ci90"][i], atol, diffs)

    for system in ["A", "BAll"]:
        got_key = "B-All" if system == "BAll" else system
        # The 2026-10-27 saved summary labels B-All as "BAll"; this scorer's own
        # summaries use "B-All". Accept either so canonical results can be the reference.
        exp_r2 = expected["per_asset_oos_r2"]
        exp_key = system if system in exp_r2 else got_key
        for asset in ASSETS:
            _compare_number(
                f"oos_r2.{system}.{asset}",
                got["per_asset_oos_r2"][got_key][asset],
                exp_r2[exp_key][asset],
                atol,
                diffs,
            )
    return {
        "status": "MATCH" if not diffs else "MISMATCH",
        "absolute_tolerance": atol,
        "n_differences": len(diffs),
        "differences": diffs,
        "interpretation": (
            "MATCH means the reconstructed scorer reproduces the saved development summary at the stated tolerance."
            if not diffs
            else "MISMATCH is a stop signal, not permission to tune the scorer. Audit panel/month handling, risk-free data, source snapshots, and implementation conventions before any historical scoring."
        ),
    }


# -----------------------------------------------------------------------------
# Historical gate
# -----------------------------------------------------------------------------


def assert_historical_go(gate_path: Path, approval_token: Optional[str]) -> Dict[str, Any]:
    if approval_token != "CONFIRM_HISTORICAL_TEST_GO":
        raise HistoricalTestLocked(
            "Historical test is locked. An explicit --historical-approval-token CONFIRM_HISTORICAL_TEST_GO is required."
        )
    gate = load_json(gate_path)
    status = str(gate.get("historical_test_status", "")).upper()
    if status not in {"GO", "APPROVED_GO", "READY_GO", "UNSEALED_GO"}:
        raise HistoricalTestLocked(
            f"Historical gate is not GO (historical_test_status={status!r}). Do not score 2023-01..2026-08."
        )
    return gate


# -----------------------------------------------------------------------------
# Configuration validation
# -----------------------------------------------------------------------------


def validate_frozen_config(config: Mapping[str, Any]) -> None:
    problems = []
    if config.get("freeze_version") != "2.0":
        problems.append(f"freeze_version={config.get('freeze_version')!r}, expected '2.0'")
    if tuple(config.get("universe", {}).get("assets", [])) != ASSETS:
        problems.append("asset universe differs from SPY/IEF/LQD")
    fm = config.get("forecast_model", {})
    if int(fm.get("minimum_completed_training_labels", -1)) != MIN_OUTER_LABELS:
        problems.append("minimum_completed_training_labels differs from 48")
    got_alphas = tuple(fm.get("ridge_alpha_candidates", []))
    if got_alphas != ALPHAS:
        problems.append(f"alpha grid differs: {got_alphas!r}")
    sample = config.get("sample", {})
    if sample.get("balanced_macro_start") != "2015-02":
        problems.append("macro start differs from 2015-02")
    if list(sample.get("development_decisions", [])) != ["2019-03", "2022-12"]:
        problems.append("development window differs")
    if list(sample.get("historical_test_decisions", [])) != ["2023-01", "2026-08"]:
        problems.append("historical window differs")
    no_rel = config.get("macro_feature_construction", {}).get("no_release", "")
    if "missing" not in no_rel.lower() or "0" not in no_rel:
        problems.append("no-release/missing rule differs")
    if problems:
        raise IntegrityError("Frozen config validation failed:\n- " + "\n- ".join(problems))


# -----------------------------------------------------------------------------
# Main orchestration
# -----------------------------------------------------------------------------


def load_inputs(spec: Mapping[str, Any]) -> Tuple[
    Dict[str, Any], pd.DataFrame, Dict[str, pd.Series], pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame
]:
    frozen_cfg_path = Path(os.path.expanduser(spec["frozen_config"]["path"]))
    frozen_cfg = load_json(frozen_cfg_path)
    validate_frozen_config(frozen_cfg)

    macro = load_macro_panel(spec["macro_panel"])
    prices = load_market_prices(spec["prices"])
    baa = load_series_file(spec["baa10y"], value_candidates=("BAA10Y", "value", "Value", "close"))
    curve = load_series_file(spec["t10y3m"], value_candidates=("T10Y3M", "value", "Value", "close"))

    # VIX can be supplied as one file or multiple historical segments.
    vix_cfg = spec["vix"]
    if "segments" in vix_cfg:
        vparts = [load_series_segment(s, value_candidates=("VIXCLS", "VIX", "Adj Close", "Close", "value")) for s in vix_cfg["segments"]]
        vix = pd.concat(vparts, ignore_index=True).sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)
    else:
        vix = load_series_file(vix_cfg, value_candidates=("VIXCLS", "VIX", "Adj Close", "Close", "value"))

    dtb4wk = load_series_file(spec["dtb4wk"], value_candidates=("DTB4WK", "value", "Value"))
    return frozen_cfg, macro, prices, baa, curve, vix, dtb4wk


def run(spec_path: Path, mode: str, output_dir: Path, historical_approval_token: Optional[str]) -> Dict[str, Any]:
    spec = load_json(spec_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Hash everything first. Expected hashes, when present in the run spec, are hard gates.
    hash_manifest = verify_and_hash_inputs(spec, Path(__file__), spec_path)
    hash_manifest.update(
        {
            "scorer_status": "RECONSTRUCTED_CANONICAL_IMPLEMENTATION",
            "freeze_version": "2.0",
            "mode": mode,
        }
    )
    stable_json_dump(hash_manifest, output_dir / "run_hash_manifest.json")

    if mode == "historical":
        if "historical_gate" not in spec:
            raise HistoricalTestLocked("Run spec must include historical_gate for historical mode")
        gate_path = Path(os.path.expanduser(spec["historical_gate"]["path"]))
        assert_historical_go(gate_path, historical_approval_token)

    frozen_cfg, macro, prices, baa, curve, vix, dtb4wk = load_inputs(spec)
    common_dates = common_trading_calendar(prices)
    decisions = build_decision_calendar(common_dates)

    start, end = (DEV_START, DEV_END) if mode == "development" else (HIST_START, HIST_END)
    score_months = month_range(start, end)

    # Need targets from macro start through score end so t-2 training labels and
    # expanding benchmark/variance are constructed on the same definition.
    required_months = month_range(MACRO_START, end)
    # Ensure the decision calendar covers all macro/training/scoring months.
    missing_decisions = [str(m) for m in required_months if m not in decisions]
    if missing_decisions:
        raise IntegrityError(f"Price calendar missing decision months: {missing_decisions[:12]}")

    macro_months = set(macro["month"])
    missing_macro = [str(m) for m in required_months if m not in macro_months]
    if missing_macro:
        raise IntegrityError(
            "Macro panel must retain every calendar month from 2015-02 through the scored window. "
            f"Missing: {missing_macro[:20]}"
        )

    targets = build_targets(prices, common_dates, decisions, dtb4wk, required_months)
    signals = build_signal_table(prices, decisions, baa, curve, vix, dtb4wk, required_months)

    predictions = score_all_systems(macro, signals, targets, score_months)
    predictions.to_csv(output_dir / "stage2_predictions.csv", index=False)

    metrics = per_asset_metrics(predictions)
    metrics.to_csv(output_dir / "stage2_metrics.csv", index=False)

    summary = build_result_summary(predictions, targets, mode)
    stable_json_dump(summary, output_dir / "stage2_result_summary.json")

    # Useful feature availability diagnostic; it never changes the run.
    availability_rows = []
    for asset in ASSETS:
        x = assemble_asset_features(macro, signals, asset)
        for m in score_months:
            row = {"asset": asset, "decision_month": str(m)}
            for c in list(MACRO_FEATURES) + list(B_FEATURES["B-All"]):
                row[c] = bool(np.isfinite(float(x.loc[m, c])))
            availability_rows.append(row)
    pd.DataFrame(availability_rows).to_csv(output_dir / "stage2_feature_availability.csv", index=False)

    reproduction = None
    if mode == "development" and spec.get("expected_development_summary"):
        expected_path = Path(os.path.expanduser(spec["expected_development_summary"]["path"]))
        expected = load_json(expected_path)
        reproduction = compare_to_saved_development(
            summary,
            expected,
            atol=float(spec.get("development_reproduction_atol", 1e-8)),
        )
        stable_json_dump(reproduction, output_dir / "development_reproduction_check.json")

    # Secondary evidence: frozen Black-Litterman portfolio layer (Freeze v2 §8-10;
    # open details fixed in stage2/methodology/Stage2_Portfolio_Conventions_v1.md).
    if mode == "development":
        a_rows = predictions[predictions["system"] == "A"].sort_values("decision_month")
        omega = s2p.omega_from_errors({a: a_rows[a_rows["asset"] == a]["error"].to_numpy(float) for a in ASSETS})
        s2p.write_omega(
            output_dir / "stage2_omega_from_A_development.json",
            omega,
            source=f"System A development OOS errors, decisions {start}..{end}, this run",
        )
    else:
        omega_cfg = spec.get("portfolio", {}).get("omega")
        if not omega_cfg:
            raise IntegrityError("Historical mode requires the frozen Omega file in the run spec (portfolio.omega.path)")
        omega = s2p.read_omega(Path(os.path.expanduser(omega_cfg["path"])))
    portfolio = s2p.run_portfolio_layer(predictions, targets, SYSTEMS, score_months, omega, MACRO_START)
    portfolio["returns"].to_csv(output_dir / "stage2_portfolio_returns.csv", index=False)
    portfolio["bl_diagnostics"].to_csv(output_dir / "stage2_portfolio_bl_diagnostics.csv", index=False)
    portfolio["metrics"].to_csv(output_dir / "stage2_portfolio_metrics.csv", index=False)

    run_report = {
        "status": "SUCCESS" if reproduction is None or reproduction["status"] == "MATCH" else "REPRODUCTION_MISMATCH",
        "mode": mode,
        "output_dir": str(output_dir.resolve()),
        "n_score_months": len(score_months),
        "score_window": [str(start), str(end)],
        "historical_test_opened": mode == "historical",
        "macro_panel_rule": "calendar-complete monthly rows; no-release indicators stay NaN until training-fold scaling, then map to 0",
        "first_dev_training_rule": "2015-02..2019-01 inclusive = 48 labels; 2019-01 row must be retained",
        "risk_free_rule": summary["rf_rule"],
        "reproduction_check": reproduction,
        "warnings": [
            "MODEL_SCALER_DDOF=0 is inherited from the saved Stage-1 implementation because the Stage-2 freeze says mean/std but does not specify ddof for model scaling.",
            "The risk-free series is DTB4WK (data snapshot v3); DGS1MO is not used.",
            "Portfolio results are secondary evidence. In development mode Omega is estimated from the same development errors, so development portfolio results are diagnostics only.",
        ],
        "portfolio_conventions": "stage2/methodology/Stage2_Portfolio_Conventions_v1.md",
        "portfolio_omega_diag": portfolio["omega_diag"],
    }
    stable_json_dump(run_report, output_dir / "run_report.json")
    return run_report


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Frozen Stage-2 A/B forecast scorer (canonical reconstruction).")
    p.add_argument("--spec", required=True, type=Path, help="Path to stage2_run_spec.json")
    p.add_argument("--mode", choices=["development", "historical"], default="development")
    p.add_argument("--output-dir", type=Path, default=Path("stage2_run_output"))
    p.add_argument(
        "--historical-approval-token",
        default=None,
        help="Historical mode additionally requires exactly CONFIRM_HISTORICAL_TEST_GO and a GO gate file.",
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = run(args.spec, args.mode, args.output_dir, args.historical_approval_token)
    except HistoricalTestLocked as exc:
        print(f"HISTORICAL TEST LOCKED: {exc}", file=sys.stderr)
        return 4
    except (IntegrityError, Stage2Error, FileNotFoundError, KeyError, ValueError) as exc:
        print(f"STAGE-2 HARD STOP: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(report, indent=2, default=str))
    return 0 if report["status"] == "SUCCESS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
