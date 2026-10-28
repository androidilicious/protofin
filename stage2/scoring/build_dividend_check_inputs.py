#!/usr/bin/env python3
"""Build the normalized official-record inputs for freeze gate 5 from the raw issuer captures.

The raw captures in stage2/data/dividend_check/raw_capture/ were extracted on
2026-10-28 (UTC) from the issuers' own published files in a browser session:

  SPY  State Street  spdr-etf-historical-distributions.xlsx  (distributions)
                     navhist-us-en-spy.xlsx                   (daily NAV)
  IEF  iShares       fund download, portfolioId 239456       (Distributions, Historical NAV, monthly NAV TR)
  LQD  iShares       fund download, portfolioId 239566       (same sheets)

Only rows with ex-dates 2014-01-01..2023-02-01 and months 2013-12..2023-01 were
extracted, so no historical-test-period values are stored. Each capture's
SHA-256 was computed in the browser on the extracted text and is re-verified
here; a mismatch stops the build.

Usage (repository root):  python stage2/scoring/build_dividend_check_inputs.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path("stage2/data/dividend_check")
RAW = ROOT / "raw_capture"
RETRIEVED = {"SPY": "2026-10-28T01:46:42Z", "IEF": "2026-10-28T01:44:07Z", "LQD": "2026-10-28T01:44:26Z"}

SOURCES = {
    "SPY": {
        "issuer": "State Street Global Advisors (SPDR)",
        "distributions_url": "https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/spdr-etf-historical-distributions.xlsx",
        "distributions_file_sha256": "6b65cbf956b5d25705d08470006a0e97e6a7d2a0d5cfd08b63f6f79783b06320",
        "distributions_file_bytes": 581216,
        "nav_url": "https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/navhist-us-en-spy.xlsx",
        "nav_file_sha256": "42047d96eda2b392d80730edebb82c6e9b3b59a6e9944529f290790c49598fdf",
        "nav_file_bytes": 278259,
        "page": "https://www.ssga.com/us/en/intermediary/etfs/spdr-sp-500-etf-trust-spy",
    },
    "IEF": {
        "issuer": "BlackRock iShares",
        "distributions_url": "https://www.ishares.com/us/products/239456/ishares-710-year-treasury-bond-etf (embedded distribution table; identical amounts in the fund download's Historical 'Ex-Dividends' column)",
        "nav_url": "https://www.blackrock.com/varnish-api/blk-one01-product-data/product-data/api/v1/get-fund-document?appType=PRODUCT_PAGE&appSubType=ISHARES&targetSite=us-ishares&locale=en_US&portfolioId=239456&component=fundDownload&userType=individual",
        "nav_file_sha256": "0fc24b027c11ed6934f8ee6e4f2d6f376e2516a8e9d5527c857dfee23152fd7c",
        "nav_file_bytes": 2485475,
        "page": "https://www.ishares.com/us/products/239456/ishares-710-year-treasury-bond-etf",
    },
    "LQD": {
        "issuer": "BlackRock iShares",
        "distributions_url": "https://www.blackrock.com/varnish-api/blk-one01-product-data/product-data/api/v1/get-fund-document?appType=PRODUCT_PAGE&appSubType=ISHARES&targetSite=us-ishares&locale=en_US&portfolioId=239566&component=fundDownload&userType=individual (Distributions sheet)",
        "nav_url": "https://www.blackrock.com/varnish-api/blk-one01-product-data/product-data/api/v1/get-fund-document?appType=PRODUCT_PAGE&appSubType=ISHARES&targetSite=us-ishares&locale=en_US&portfolioId=239566&component=fundDownload&userType=individual",
        "nav_file_sha256": "8e62a96be6baa5dddaccbd3a9dae1be9152f41f3f0517db09208c8815cbfe0f0",
        "nav_file_bytes": 8919972,
        "page": "https://www.ishares.com/us/products/239566/ishares-iboxx-investment-grade-corporate-bond-etf",
    },
}

# SHA-256 of each capture's text (no trailing newline), computed in the browser at extraction.
CAPTURE_SHA = {
    "IEF_distributions.txt": "c7159d91b06eb612df0cd512516cc25b5dd3fbbf447a8081f69669e3d9bdfab5",
    "IEF_navpairs.txt": "63c7ad1192030974a134aea17dafe18bd1fee10485dbf1ff5c92e6a6442c8e58",
    "IEF_monthly.txt": "f4b05b2b0a715c8d3315c8a1856ff3c85a234ad9263aad04d83142b9c807ab94",
    "LQD_distributions.txt": "4b1c362a342f9a5db13164d72cb8f822afac38a54514ccd71c696169282c84e2",
    "LQD_navpairs.txt": "1cf8fe048f1a85be83cce08223558ef689edbb880bafb1025b80115dbbb3bb19",
    "LQD_monthly.txt": "d57ede30c65def3f009714c553298a8555d2c38e65e85708437bc966b0b7d43d",
    "SPY_distributions.txt": "63bc1f444a124dd7a96055c40b32f2b0b170f1c4bb3f9b90d14928c879cd247a",
    "SPY_navpairs.txt": "9b9b0585fd3f8110de81c30d3ed0ab4109223c2616ca54df9afdaa8e62c6c305",
    "SPY_monthend_nav.txt": "3de72688586a47b0ff408799b7d34244e56f6b26ca2221d7c9bc78ed9140dc6c",
}


def read_capture(name: str) -> list[list[str]]:
    b = (RAW / name).read_bytes()
    if b.endswith(b"\n"):
        b = b[:-1]
    got = hashlib.sha256(b).hexdigest()
    if got != CAPTURE_SHA[name]:
        sys.exit(f"STOP: capture {name} sha256 {got} != browser-side {CAPTURE_SHA[name]}")
    return [line.split(",") for line in b.decode().split("\n")]


def ymd(s: str) -> str:
    return f"{s[:4]}-{s[4:6]}-{s[6:]}" if len(s) == 8 and s.isdigit() else s


def main() -> int:
    dist, pairs, monthly_tr, month_end_nav = [], [], [], []
    for t in ("IEF", "LQD"):
        for r in read_capture(f"{t}_distributions.txt"):
            rec, ex, pay, tot, inc, st, lt, roc = r
            dist.append({"ticker": t, "ex_date": ymd(ex), "record_date": ymd(rec), "payable_date": ymd(pay),
                         "distribution_per_share": float(tot), "income": float(inc), "st_cap_gain": float(st),
                         "lt_cap_gain": float(lt), "return_of_capital": float(roc)})
        for ex, prev, nav_prev, nav_ex, exdiv in read_capture(f"{t}_navpairs.txt"):
            pairs.append({"ticker": t, "ex_date": ex, "prev_nav_date": prev, "nav_prev": float(nav_prev),
                          "nav_ex": float(nav_ex), "nav_file_ex_dividend": float(exdiv)})
        for d, v in read_capture(f"{t}_monthly.txt"):
            monthly_tr.append({"ticker": t, "month_end": d, "nav_total_return_pct": float(v)})
    for rec, ex, pay, div, st, lt, freq, cusip in read_capture("SPY_distributions.txt"):
        dist.append({"ticker": "SPY", "ex_date": ex, "record_date": rec, "payable_date": pay,
                     "distribution_per_share": float(div), "income": float(div),
                     "st_cap_gain": float(st or 0), "lt_cap_gain": float(lt or 0), "return_of_capital": 0.0})
    for ex, prev, nav_prev, nav_ex in read_capture("SPY_navpairs.txt"):
        pairs.append({"ticker": "SPY", "ex_date": ex, "prev_nav_date": prev, "nav_prev": float(nav_prev),
                      "nav_ex": float(nav_ex), "nav_file_ex_dividend": float("nan")})
    for d, v in read_capture("SPY_monthend_nav.txt"):
        month_end_nav.append({"ticker": "SPY", "nav_date": d, "nav": float(v)})

    dist_df = pd.DataFrame(dist).sort_values(["ticker", "ex_date"])
    pairs_df = pd.DataFrame(pairs).sort_values(["ticker", "ex_date"])
    # Cross-check two official iShares tables: distribution table vs NAV-file ex-dividend column.
    m = dist_df.merge(pairs_df, on=["ticker", "ex_date"], how="outer", indicator=True)
    if (m["_merge"] != "both").any():
        sys.exit("STOP: ex-dates differ between the distribution and NAV captures")
    ish = m[m["ticker"] != "SPY"]
    bad = ish[(ish["distribution_per_share"] - ish["nav_file_ex_dividend"]).abs() > 1e-9]
    if len(bad):
        sys.exit(f"STOP: iShares distribution table and NAV-file ex-dividend column disagree:\n{bad}")
    # The capital-gain columns must not change the total for these funds/dates.
    if (dist_df[["st_cap_gain", "lt_cap_gain", "return_of_capital"]].abs().sum(axis=1) > 0).any():
        sys.exit("STOP: non-income distribution component present; check how 'total' is defined")

    dist_df.to_csv(ROOT / "official_distributions.csv", index=False, float_format="%.6f")
    pairs_df.to_csv(ROOT / "official_nav_exdate_pairs.csv", index=False, float_format="%.6f")
    pd.DataFrame(monthly_tr).to_csv(ROOT / "official_monthly_nav_total_return_ishares.csv", index=False)
    pd.DataFrame(month_end_nav).to_csv(ROOT / "official_month_end_nav_ssga.csv", index=False, float_format="%.6f")

    outputs = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(ROOT.glob("official_*.csv"))}
    provenance = {
        "purpose": "Freeze gate 5 (ETF distribution adjustment) official issuer records",
        "window": {"ex_dates": ["2014-01-01", "2023-02-01"], "months": ["2013-12", "2023-01"]},
        "historical_test_values_stored": False,
        "sources": SOURCES, "retrieved_utc": RETRIEVED,
        "raw_capture_sha256": CAPTURE_SHA, "normalized_output_sha256": outputs,
        "counts": dist_df.groupby("ticker").size().to_dict(),
    }
    (ROOT / "official_records_provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(json.dumps({"counts": provenance["counts"], "outputs": outputs}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
