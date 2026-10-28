#!/usr/bin/env python3
"""Extend freeze gate 5 (ETF distribution adjustment) to TLT.

TLT is held by the primary Agentic Workflow (JEV) and by its Committee variant. This script checks
that the pinned TLT prices used by the shared evaluator include every official iShares distribution,
using the Stage 2 gate's criteria C1-C6 unchanged (imported from stage2/scoring/check_dividend_adjustment.py).

Inputs. iShares' fund download for TLT (portfolioId 239454) was read in a browser on 2026-10-28 UTC;
the Distributions, Historical NAV and monthly NAV total-return rows for ex-dates 2014-01-01..2023-02-01
and months 2013-12..2023-01 were extracted, each capture's SHA-256 was computed in the browser, and the
captures are stored under native_backtest/data/tlt_dividend_check/raw_capture/. No historical-test-period
value is stored. This script re-verifies those hashes, normalises the records, and runs the gate on the
shared evaluator's own TLT series, cut at 2023-02-01 (the last development price).

Usage (repository root): python -m native_backtest.scripts.check_tlt_distributions
Exit code: 0 PASS, 2 FAIL.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "stage2" / "scoring"))
import check_dividend_adjustment as gate5  # noqa: E402  (Stage 2 gate code, unchanged)

from native_backtest.framework.market import _abs, load_config, load_market  # noqa: E402

DATA = ROOT / "native_backtest/data/tlt_dividend_check"
RAW = DATA / "raw_capture"
OUT = ROOT / "native_backtest/out/tlt_dividend_gate"
SOURCE = {
    "issuer": "BlackRock iShares",
    "fund": "iShares 20+ Year Treasury Bond ETF (TLT)",
    "page": "https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf",
    "fund_download_url": "https://www.blackrock.com/varnish-api/blk-one01-product-data/product-data/api/v1/get-fund-document?appType=PRODUCT_PAGE&appSubType=ISHARES&targetSite=us-ishares&locale=en_US&portfolioId=239454&component=fundDownload&userType=individual",
    "fund_download_sha256": "8a1ae8e2b56e5e8bce9d6a73a85b5675f726631d8d26b32cdac9fa0a7585b003",
    "fund_download_bytes": 2546273,
    "sheets_used": ["Distributions", "Historical", "Performance"],
    "retrieved_utc": "2026-10-28T20:33:31Z",
}
# SHA-256 of each capture's text (no trailing newline), computed in the browser at extraction.
CAPTURE_SHA = {
    "TLT_distributions.txt": "ecea1842466ad34edf7bd1ae903d8c3f5bb4942b9423be485ea40ab20f7d9d3b",
    "TLT_navpairs.txt": "aabb6b92b6bf78b58f351361869c67f7b30e2ae3d9c4e08908d393bcec34b6a4",
    "TLT_monthly.txt": "9b4f746b491ecc8940fc8d49f09765b51914099f6f143ea3587d34327f68226d",
}


def read_capture(name: str) -> list:
    b = (RAW / name).read_bytes()
    if b.endswith(b"\n"):
        b = b[:-1]
    got = hashlib.sha256(b).hexdigest()
    if got != CAPTURE_SHA[name]:
        raise SystemExit(f"STOP: capture {name} sha256 {got} != browser-side {CAPTURE_SHA[name]}")
    return [line.split(",") for line in b.decode().split("\n")]


def ymd(s: str) -> str:
    return f"{s[:4]}-{s[4:6]}-{s[6:]}"


def build_records():
    dist = [{"ticker": "TLT", "ex_date": ymd(ex), "record_date": ymd(rec), "payable_date": ymd(pay), "distribution_per_share": float(tot),
             "income": float(inc), "st_cap_gain": float(st), "lt_cap_gain": float(lt), "return_of_capital": float(roc)}
            for rec, ex, pay, tot, inc, st, lt, roc in read_capture("TLT_distributions.txt")]
    pairs = [{"ticker": "TLT", "ex_date": ex, "prev_nav_date": prev, "nav_prev": float(a), "nav_ex": float(b), "nav_file_ex_dividend": float(x)}
             for ex, prev, a, b, x in read_capture("TLT_navpairs.txt")]
    monthly = [{"ticker": "TLT", "month_end": d, "nav_total_return_pct": float(v)} for d, v in read_capture("TLT_monthly.txt")]
    dist_df = pd.DataFrame(dist).sort_values("ex_date")
    pairs_df = pd.DataFrame(pairs).sort_values("ex_date")
    m = dist_df.merge(pairs_df, on=["ticker", "ex_date"], how="outer", indicator=True)
    if (m["_merge"] != "both").any():
        raise SystemExit("STOP: ex-dates differ between the distribution and NAV captures")
    if ((m["distribution_per_share"] - m["nav_file_ex_dividend"]).abs() > 1e-9).any():
        raise SystemExit("STOP: distribution table and NAV-file ex-dividend column disagree")
    if (dist_df[["st_cap_gain", "lt_cap_gain", "return_of_capital"]].abs().sum(axis=1) > 0).any():
        raise SystemExit("STOP: non-income distribution component present")
    DATA.mkdir(parents=True, exist_ok=True)
    dist_df.to_csv(DATA / "official_distributions_TLT.csv", index=False, float_format="%.6f")
    pairs_df.to_csv(DATA / "official_nav_exdate_pairs_TLT.csv", index=False, float_format="%.6f")
    pd.DataFrame(monthly).to_csv(DATA / "official_monthly_nav_total_return_TLT.csv", index=False)
    outputs = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(DATA.glob("official_*_TLT.csv"))}
    prov = {"purpose": "Freeze gate 5 extended to TLT: official issuer records", "source": SOURCE,
            "window": {"ex_dates": ["2014-01-01", "2023-02-01"], "months": ["2013-12", "2023-01"]},
            "historical_test_values_stored": False, "raw_capture_sha256": CAPTURE_SHA, "normalized_output_sha256": outputs,
            "counts": {"distributions": len(dist_df), "nav_pairs": len(pairs_df), "months": len(monthly)}}
    (DATA / "official_records_provenance_TLT.json").write_text(json.dumps(prov, indent=2) + "\n")
    return dist_df, pairs_df, pd.DataFrame(monthly)


def main() -> int:
    dist, pairs, mtr = build_records()
    dist["ex_date"] = pd.to_datetime(dist["ex_date"])
    pairs["ex_date"] = pd.to_datetime(pairs["ex_date"])
    pairs["prev_nav_date"] = pd.to_datetime(pairs["prev_nav_date"])
    mtr["month_end"] = pd.to_datetime(mtr["month_end"])

    cfg = load_config()
    mk = load_market(cfg)
    adj = mk.prices["TLT"]
    adj = adj[adj.index <= gate5.LAST_DEV_PRICE]
    seg = _abs(cfg["_prices"]["TLT"]["segments"][-1])
    f = pd.read_csv(Path(seg["path"]), sep=None, engine="python", parse_dates=["Date"]).set_index("Date")
    f = f[(f.index >= pd.Timestamp(seg["start_inclusive"])) & (f.index <= gate5.LAST_DEV_PRICE)]
    if not np.allclose(f["Close"].to_numpy(), adj.reindex(f.index).to_numpy(), rtol=0, atol=1e-9):
        raise SystemExit("STOP: 2018+ TLT Close differs from the shared evaluator's series")
    raw = f.rename(columns={"Close": "adj"})[["High", "Low", "adj"]]

    monthly = gate5.monthly_official("TLT", dist, pairs, mtr, pd.DataFrame(columns=["ticker", "nav_date", "nav"]))
    per, mon, summary = gate5.check_ticker("TLT", adj, raw, dist, pairs, monthly)
    OUT.mkdir(parents=True, exist_ok=True)
    per.to_csv(OUT / "tlt_dividend_check_by_ex_date.csv", index=False, float_format="%.6f")
    mon.to_csv(OUT / "tlt_dividend_check_by_month.csv", index=False, float_format="%.4f")
    status = {"gate": "freeze_gate_5_distribution_adjustment, extended to TLT",
              "design": "stage2/methodology/Stage2_Dividend_Adjustment_Gate_v1.md (criteria C1-C6 unchanged)",
              "code": "stage2/scoring/check_dividend_adjustment.py check_ticker / monthly_official (imported unchanged)",
              "prices": "shared evaluator TLT series (native_backtest/config/framework_config_v1.json extra_prices.TLT)",
              "price_data_cutoff": gate5.LAST_DEV_PRICE.date().isoformat(),
              "official_records": "native_backtest/data/tlt_dividend_check/official_records_provenance_TLT.json",
              "status": "PASS" if summary["pass"] else "FAIL", "by_ticker": [summary]}
    (OUT / "tlt_dividend_gate_status.json").write_text(json.dumps(status, indent=2, default=float) + "\n")
    print("TLT", "PASS" if summary["pass"] else "FAIL", {k: summary[k]["pass"] for k in summary if k.startswith("C")})
    for k in ("C2_ex_date_capture", "C3_monthly_capture"):
        print(" ", k, {x: round(summary[k][x], 4) for x in ("kappa", "se")}, [round(v, 3) for v in summary[k]["ci99"]])
    print("  C4", round(summary["C4_cumulative_capture"]["kappa"], 4), "C5", summary["C5_implied_distribution"]["n_pass"], "/",
          summary["C5_implied_distribution"]["n_tested"], "C6 informative", summary["C6_informative_nav"]["n_informative"],
          "pass", summary["C6_informative_nav"]["n_pass"])
    if summary["C1_coverage"]["problems"]:
        print("  C1 problems:", summary["C1_coverage"]["problems"][:5])
    return 0 if summary["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
