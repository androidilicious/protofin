"""Shared market data, calendar and holding-period returns.

Reuses the verified Stage 2 loaders and conventions unchanged (stage2/scoring/stage2_backtest.py):
segment splicing with scale, last common trading day as decision day, entry and exit at the first
common trading day after month-end, DTB4WK accrued from entry over exact calendar days.
The only generalisation is that the calendar spans every asset used by any system, so all systems
share identical decision, entry and exit dates.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Mapping, Sequence

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
_S2 = REPO_ROOT / "stage2" / "scoring"
if str(_S2) not in sys.path:
    sys.path.insert(0, str(_S2))
import stage2_backtest as s2  # noqa: E402  (verified Stage 2 conventions)

DEFAULT_CONFIG = REPO_ROOT / "native_backtest" / "config" / "framework_config_v1.json"


class MarketDataError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_config(path: Path = DEFAULT_CONFIG) -> dict:
    cfg = json.loads(Path(path).read_text())
    spec = json.loads((REPO_ROOT / cfg["inherits_stage2_run_spec"]["path"]).read_text())
    prices = dict(spec["prices"])
    prices.update(cfg.get("extra_prices", {}))
    cfg["_prices"] = prices
    cfg["_dtb4wk"] = spec["dtb4wk"]
    return cfg


def _abs(cfg_seg: Mapping) -> dict:
    seg = dict(cfg_seg)
    seg["path"] = str(REPO_ROOT / seg["path"])
    return seg


def verify_input_hashes(cfg: dict) -> Dict[str, str]:
    """Check every price and DTB4WK file against its expected SHA-256; hard stop on mismatch."""
    got: Dict[str, str] = {}
    entries = [(f"{a}#{i}", s) for a, c in cfg["_prices"].items() for i, s in enumerate(c.get("segments", [c]))]
    entries.append(("DTB4WK", cfg["_dtb4wk"]))
    for name, seg in entries:
        p = REPO_ROOT / seg["path"]
        if not p.exists():
            raise MarketDataError(f"missing input {p}; run stage2/scoring/fetch_pinned_inputs.py with the manifests")
        h = sha256_file(p)
        exp = seg.get("expected_sha256")
        if exp and h != exp:
            raise MarketDataError(f"hash mismatch for {name}: {h} != {exp}")
        got[name] = h
    return got


@dataclasses.dataclass
class Market:
    prices: Dict[str, pd.Series]
    calendar: pd.DatetimeIndex
    decision_dates: Dict[pd.Period, pd.Timestamp]
    dtb4wk: pd.DataFrame
    input_hashes: Dict[str, str]
    scorable_from: pd.Period = pd.Period("2011-01", "M")

    def holding_period(self, month: pd.Period):
        entry = s2.first_common_day_after_month_end(month, self.calendar)
        exit_ = s2.first_common_day_after_month_end(month + 1, self.calendar)
        return entry, exit_

    def period_returns(self, month: pd.Period, assets: Sequence[str]) -> Dict[str, float]:
        if month < self.scorable_from:
            raise MarketDataError(f"{month} is before {self.scorable_from}: pinned prices there omit distributions (see config pinned_price_validity)")
        entry, exit_ = self.holding_period(month)
        out = {}
        for a in assets:
            s = self.prices[a]
            if entry not in s.index or exit_ not in s.index:
                raise MarketDataError(f"{a} has no price on {entry.date()} or {exit_.date()}")
            out[a] = float(s.loc[exit_] / s.loc[entry] - 1.0)
        return out

    def rf_return(self, month: pd.Period) -> float:
        entry, exit_ = self.holding_period(month)
        return s2.interval_rf_return(self.dtb4wk, entry, exit_)

    def last_scorable_month(self) -> pd.Period:
        """Latest decision month whose exit date exists in the calendar."""
        months = sorted(self.decision_dates)
        for m in reversed(months):
            try:
                self.holding_period(m)
                return m
            except Exception:
                continue
        raise MarketDataError("no scorable month")


def load_market(cfg: dict) -> Market:
    hashes = verify_input_hashes(cfg)
    prices = {}
    for a in cfg["calendar_assets"]:
        c = cfg["_prices"][a]
        segs = [_abs(s) for s in c.get("segments", [c])]
        prices[a] = s2.load_asset_prices(a, {"segments": segs})
    common = None
    for a in cfg["calendar_assets"]:
        idx = pd.DatetimeIndex(prices[a].index)
        common = idx if common is None else common.intersection(idx)
    common = common.sort_values()
    dtb = s2.load_series_file(_abs(cfg["_dtb4wk"]), value_candidates=("DTB4WK", "value", "Value"))
    valid = pd.Period(cfg.get("pinned_price_validity", {}).get("scorable_from_decision_month", "2011-01"), "M")
    return Market(prices=prices, calendar=common, decision_dates=s2.build_decision_calendar(common), dtb4wk=dtb, input_hashes=hashes, scorable_from=valid)


def decision_time_iso(day: pd.Timestamp) -> str:
    """20:00 America/New_York on the decision day, with the correct UTC offset."""
    ts = pd.Timestamp(year=day.year, month=day.month, day=day.day, hour=20, tz="America/New_York")
    return ts.isoformat()


def close_time_iso(day: pd.Timestamp) -> str:
    ts = pd.Timestamp(year=day.year, month=day.month, day=day.day, hour=16, tz="America/New_York")
    return ts.isoformat()


def months_between(start: str, end: str) -> List[pd.Period]:
    return list(pd.period_range(pd.Period(start, "M"), pd.Period(end, "M"), freq="M"))
