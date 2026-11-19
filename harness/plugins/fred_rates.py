"""Daily Treasury yields (10-year, 2-year, 3-month).

Source: Board of Governors H.15 release, downloaded from FRED's no-key CSV endpoint.
The underlying data is a US government work. This replaces the Yahoo Finance quote
for anything written to the store, because Yahoo's terms do not allow republishing.
"""
import io
import urllib.request

import pandas as pd

from ..contract import PUBLIC, Plugin, Reading

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}"
IDS = {"us10y": "DGS10", "us2y": "DGS2", "us3m": "DGS3MO"}


def parse(text, series, source):
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


class FredRates(Plugin):
    name = "fred_rates"
    title = "Treasury yields"
    licence = PUBLIC
    series = tuple(IDS)

    def fetch(self):
        out = []
        for series, fred_id in IDS.items():
            url = URL.format(id=fred_id)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 protofin-research"})
            text = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "ignore")
            out.extend(parse(text, series, url))
        return out
