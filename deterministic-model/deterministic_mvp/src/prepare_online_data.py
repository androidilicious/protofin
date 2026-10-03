#!/usr/bin/env python3
"""Download and align public supplemental series for the deterministic MVP."""

from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


URLS = {
    "anfci": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=ANFCI",
    "gpr": "https://www.matteoiacoviello.com/gpr_files/data_gpr_export.dta",
    "spy": "https://query2.finance.yahoo.com/v8/finance/chart/SPY?range=10y&interval=1d&events=div%2Csplits&includeAdjustedClose=true",
    "ief": "https://query2.finance.yahoo.com/v8/finance/chart/IEF?range=10y&interval=1d&events=div%2Csplits&includeAdjustedClose=true",
    "lqd": "https://query2.finance.yahoo.com/v8/finance/chart/LQD?range=10y&interval=1d&events=div%2Csplits&includeAdjustedClose=true",
}

RAW_NAMES = {
    "anfci": "anfci_fred.csv",
    "gpr": "gpr_caldara_iacoviello.dta",
    "spy": "spy_yahoo_chart.json",
    "ief": "ief_yahoo_chart.json",
    "lqd": "lqd_yahoo_chart.json",
}


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 deterministic-capstone-mvp/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        destination.write_bytes(response.read())


def download_all(raw_dir: Path) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    for key, url in URLS.items():
        download(url, raw_dir / RAW_NAMES[key])


def prepare_anfci(path: Path) -> pd.DataFrame:
    data = pd.read_csv(path)
    data["observation_date"] = pd.to_datetime(data["observation_date"])
    data["ANFCI"] = pd.to_numeric(data["ANFCI"], errors="coerce")
    # The weekly Friday observation is normally published the following
    # Wednesday. Five calendar days prevents using it before publication.
    data["available_date"] = data["observation_date"] + pd.Timedelta(days=5)
    data["date"] = data["available_date"].dt.to_period("M").dt.to_timestamp("M")
    monthly = data.sort_values("available_date").groupby("date", as_index=False).tail(1)
    return monthly[["date", "ANFCI", "observation_date", "available_date"]].rename(columns={"ANFCI": "anfci"})


def prepare_gpr(path: Path) -> pd.DataFrame:
    data = pd.read_stata(path, columns=["month", "GPR"])
    data["month"] = pd.to_datetime(data["month"])
    data["GPR"] = pd.to_numeric(data["GPR"], errors="coerce")
    # The official monthly file is updated at the beginning of the following
    # month. A value for month t is therefore first usable at month-end t+1.
    data["date"] = (data["month"].dt.to_period("M") + 1).dt.to_timestamp("M")
    return data[["date", "GPR", "month"]].rename(columns={"GPR": "gpr", "month": "gpr_reference_month"})


def prepare_adjusted_return(path: Path, output_name: str) -> pd.DataFrame:
    payload = json.loads(path.read_text(encoding="utf-8"))
    result = payload["chart"]["result"][0]
    timestamps = pd.to_datetime(result["timestamp"], unit="s", utc=True).tz_convert(None)
    adjusted = result["indicators"]["adjclose"][0]["adjclose"]
    data = pd.DataFrame({"trading_date": timestamps, "adjusted_close": adjusted}).dropna()
    data["date"] = data["trading_date"].dt.to_period("M").dt.to_timestamp("M")
    monthly = data.sort_values("trading_date").groupby("date", as_index=False).tail(1).sort_values("date")
    monthly[output_name] = monthly["adjusted_close"].pct_change()
    return monthly[["date", output_name]]


def build_supplemental(raw_dir: Path, output_csv: Path, sources_csv: Path) -> pd.DataFrame:
    anfci = prepare_anfci(raw_dir / RAW_NAMES["anfci"])
    gpr = prepare_gpr(raw_dir / RAW_NAMES["gpr"])
    equity = prepare_adjusted_return(raw_dir / RAW_NAMES["spy"], "equity_return")
    treasury = prepare_adjusted_return(raw_dir / RAW_NAMES["ief"], "treasury_return")
    credit = prepare_adjusted_return(raw_dir / RAW_NAMES["lqd"], "ig_credit_return")

    start = pd.Timestamp("2018-01-31")
    end = min(frame["date"].max() for frame in [anfci, gpr, equity, treasury, credit])
    panel = pd.DataFrame({"date": pd.date_range(start, end, freq="ME")})
    for frame in [anfci[["date", "anfci"]], gpr[["date", "gpr"]], equity, treasury, credit]:
        panel = panel.merge(frame, on="date", how="left", validate="one_to_one")
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(output_csv, index=False)

    downloaded_at = datetime.now(timezone.utc).isoformat()
    sources = pd.DataFrame(
        [
            {
                "field": "anfci",
                "series_or_proxy": "Chicago Fed ANFCI",
                "source_url": URLS["anfci"],
                "transformation": "last weekly observation published by month-end; assumed five-calendar-day publication lag",
                "downloaded_at_utc": downloaded_at,
                "limitation": "latest revised history, not an ALFRED real-time vintage panel",
            },
            {
                "field": "gpr",
                "series_or_proxy": "Caldara-Iacoviello Recent GPR",
                "source_url": URLS["gpr"],
                "transformation": "reference-month value lagged to the following decision month",
                "downloaded_at_utc": downloaded_at,
                "limitation": "latest vintage can contain historical revisions",
            },
            {
                "field": "equity_return",
                "series_or_proxy": "SPY adjusted close",
                "source_url": URLS["spy"],
                "transformation": "month-end adjusted-close percentage change",
                "downloaded_at_utc": downloaded_at,
                "limitation": "ETF proxy includes fund fees and tracking difference",
            },
            {
                "field": "treasury_return",
                "series_or_proxy": "IEF adjusted close (7-10 Year U.S. Treasury ETF)",
                "source_url": URLS["ief"],
                "transformation": "month-end adjusted-close percentage change",
                "downloaded_at_utc": downloaded_at,
                "limitation": "duration-specific ETF proxy, not the full Treasury market",
            },
            {
                "field": "ig_credit_return",
                "series_or_proxy": "LQD adjusted close (U.S. investment-grade corporate bond ETF)",
                "source_url": URLS["lqd"],
                "transformation": "month-end adjusted-close percentage change",
                "downloaded_at_utc": downloaded_at,
                "limitation": "ETF proxy includes fund fees and tracking difference",
            },
        ]
    )
    sources.to_csv(sources_csv, index=False)
    return panel


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare online supplemental data for the deterministic MVP")
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--download", action="store_true", help="Refresh all raw files before preparing the panel")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.download:
        download_all(args.raw_dir)
    built = build_supplemental(args.raw_dir, args.output, args.sources)
    print(
        json.dumps(
            {
                "rows": len(built),
                "start": built["date"].min().strftime("%Y-%m-%d"),
                "end": built["date"].max().strftime("%Y-%m-%d"),
                "missing": {column: int(built[column].isna().sum()) for column in built.columns if column != "date"},
            },
            indent=2,
        )
    )
