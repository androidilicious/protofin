"""FOMC statement calendar for AP3's FOMC triggers.

Source: the team repository's FOMC statement index (approach-2 @ ce063b8, data/news/fomc_index.csv),
vendored byte-identically under native_backtest/vendor. Only the dates are used; the hawkish/dovish
score columns are another model's output and are ignored.

Timing rule. Scheduled FOMC statements are released at 14:00 ET, before AP3's 20:00 ET decision
time, so a statement dated on a decision day precedes that decision. Unscheduled communications in
the index (for example 3, 15 and 23 March 2020) are never dated on a decision day; the loader checks
this, so no event can be assigned to a decision it followed. An event belongs to decision month M when
decision_day(M-1) < event date <= decision_day(M); events after the last trading day of a month (for
example a weekend) roll to the next month.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict, List, Mapping, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "native_backtest/vendor/protofin_approach-2_ce063b8/data/news/fomc_index.csv"
EXPECTED_SHA256 = "8d175ef8cf0ae38440a3fa5c660dd37d57ca38762b49a4e29b4a9cf2103e656a"
SCHEDULED_RELEASE_ET = "14:00"


class CalendarError(RuntimeError):
    pass


def load_dates(path: Path = SOURCE, expected_sha256: Optional[str] = EXPECTED_SHA256) -> List[pd.Timestamp]:
    raw = path.read_bytes()
    if expected_sha256 and hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise CalendarError(f"{path} does not match its pinned SHA-256")
    df = pd.read_csv(path, usecols=["date"])
    dates = pd.to_datetime(df["date"], format="%Y-%m-%d")
    if dates.duplicated().any():
        raise CalendarError("duplicate FOMC dates in the index")
    return sorted(dates.tolist())


UNSCHEDULED = ("2019-10-11", "2020-03-03", "2020-03-15", "2020-03-23", "2020-08-27")


def events_by_decision_month(decision_days: Mapping[pd.Period, pd.Timestamp], dates: Optional[List[pd.Timestamp]] = None,
                             unscheduled: tuple = UNSCHEDULED) -> Dict[pd.Period, List[dict]]:
    """Assign each FOMC event to the first decision whose day is on or after the event date.

    The first month's window starts after the previous month's last business day."""
    dates = load_dates() if dates is None else sorted(pd.Timestamp(d) for d in dates)
    months = sorted(decision_days)
    days = [pd.Timestamp(decision_days[m]).normalize() for m in months]
    prev = pd.offsets.BMonthEnd().rollback(pd.Timestamp((months[0] - 1).end_time).normalize())
    out: Dict[pd.Period, List[dict]] = {m: [] for m in months}
    for d in (pd.Timestamp(x).normalize() for x in dates):
        if d <= prev:
            continue
        for m, day in zip(months, days):
            if d <= day:
                on_day = bool(d == day)
                if on_day and str(d.date()) in unscheduled:
                    raise CalendarError(f"unscheduled FOMC communication {d.date()} falls on decision day {day.date()}; its release time must be checked")
                out[m].append({"date": str(d.date()), "on_decision_day": on_day,
                               "release": "scheduled statement, 14:00 ET" if str(d.date()) not in unscheduled else "unscheduled communication"})
                break
    return out


def check_unscheduled_not_on_decision_days(decision_days: Mapping[pd.Period, pd.Timestamp], unscheduled: tuple = UNSCHEDULED) -> List[str]:
    """Unscheduled communications in the index that fall on a decision day (expected: none)."""
    dd = {pd.Timestamp(v).normalize() for v in decision_days.values()}
    return [u for u in unscheduled if pd.Timestamp(u) in dd]
