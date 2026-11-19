"""Daily Treasury yields (10-year, 2-year, 3-month).

Primary source: the US Treasury's daily par yield curve, one CSV per year.
Fallback: the same rates from the Federal Reserve's H.15 release via FRED's no-key CSV.
Both are US government data. This replaces the Yahoo Finance quote for anything written
to the store, because Yahoo's terms do not allow republishing.
"""
import io
import time
import urllib.request
from datetime import datetime, timezone

import pandas as pd

from ..contract import PUBLIC, Plugin, Reading

TREASURY = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
            "daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve"
            "&field_tdr_date_value={year}&page&_format=csv")
TREASURY_COLUMNS = {"us10y": "10 Yr", "us2y": "2 Yr", "us3m": "3 Mo"}
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}"
FRED_IDS = {"us10y": "DGS10", "us2y": "DGS2", "us3m": "DGS3MO"}
FIRST_YEAR = 1990
HEADERS = {"User-Agent": "Mozilla/5.0 protofin-research"}


def _get(url, timeout=30, tries=2):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(2 * (attempt + 1))
    raise last


def parse_treasury(text, source):
    """Treasury yearly CSV: a Date column (MM/DD/YYYY) and one column per maturity."""
    df = pd.read_csv(io.StringIO(text))
    df.columns = [str(c).strip() for c in df.columns]
    if "Date" not in df.columns or "10 Yr" not in df.columns:
        raise ValueError(f"unexpected Treasury CSV columns: {list(df.columns)[:6]}")
    dates = pd.to_datetime(df["Date"], format="%m/%d/%Y", errors="coerce")
    out = []
    for series, col in TREASURY_COLUMNS.items():
        if col not in df.columns:
            continue
        values = pd.to_numeric(df[col], errors="coerce")
        for d, v in zip(dates, values):
            if pd.isna(d) or pd.isna(v):
                continue
            out.append(Reading(series=series, date=str(d.date()), value=float(v), source=source, unit="percent"))
    return out


def parse_fred(text, series, source):
    """FRED graph CSV: a date column, then one value column; '.' marks a missing day."""
    df = pd.read_csv(io.StringIO(text))
    if df.shape[1] < 2:
        raise ValueError(f"unexpected FRED CSV shape for {series}: {list(df.columns)}")
    dates = pd.to_datetime(df.iloc[:, 0], errors="coerce")
    values = pd.to_numeric(df.iloc[:, 1], errors="coerce")
    out = []
    for d, v in zip(dates, values):
        if pd.isna(d) or pd.isna(v):
            continue
        out.append(Reading(series=series, date=str(d.date()), value=float(v), source=source, unit="percent"))
    return out


class TreasuryYields(Plugin):
    name = "treasury_yields"
    title = "Treasury yields"
    licence = PUBLIC
    series = tuple(TREASURY_COLUMNS)

    def _from_treasury(self, since):
        this_year = datetime.now(timezone.utc).year
        start = FIRST_YEAR if not since else max(FIRST_YEAR, int(str(since)[:4]) - 1)
        out = []
        for year in range(start, this_year + 1):
            url = TREASURY.format(year=year)
            out.extend(parse_treasury(_get(url), url))
        if not out:
            raise ValueError("Treasury returned no rows")
        return out

    def _from_fred(self):
        out = []
        for series, fred_id in FRED_IDS.items():
            url = FRED.format(id=fred_id)
            out.extend(parse_fred(_get(url), series, url))
        return out

    def fetch(self, since=None):
        try:
            return self._from_treasury(since)
        except Exception as first:  # noqa: BLE001
            try:
                return self._from_fred()
            except Exception as second:  # noqa: BLE001
                raise RuntimeError(f"Treasury failed ({type(first).__name__}: {first}); "
                                   f"FRED failed ({type(second).__name__}: {second})") from second
