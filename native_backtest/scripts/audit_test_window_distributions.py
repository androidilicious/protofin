#!/usr/bin/env python3
"""Isolated data-quality audit: Stage 2 gate 5 (distribution adjustment) on the protected window's prices.

Pre-registration: native_backtest/docs/TEST_WINDOW_DISTRIBUTION_AUDIT_PREREGISTRATION_2026-10-28.md.

Isolation. This script reads only the pinned price files (verified against their recorded SHA-256) and the
issuers' official records. It imports the Stage 2 gate code unchanged and the market-data loader, and nothing
that touches strategies, decision records, portfolios, benchmarks or scoring. It writes gate statistics only:
capture ratios, residuals against the official NAV total return, distribution sizes and per-date status. The
adjusted-price and NAV return columns the gate computes internally are dropped before anything is saved.

Inputs: native_backtest/data/test_window_dividend_audit/raw_capture/*.txt and capture_manifest.json (issuer-file
and capture SHA-256 computed in the browser at capture, URLs, retrieval times). The criteria (C1-C6) and their
thresholds are those of the development gate; only the window constants are set for this run.

Usage (repository root): python -m native_backtest.scripts.audit_test_window_distributions
Exit code: 0 PASS, 2 FAIL (every failure is listed as an exception; no data are changed).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "stage2" / "scoring"))
import check_dividend_adjustment as gate5  # noqa: E402  (Stage 2 gate code, unchanged)

from native_backtest.framework.market import _abs, load_config, load_market  # noqa: E402

DATA = ROOT / "native_backtest/data/test_window_dividend_audit"
RAW = DATA / "raw_capture"
OUT = ROOT / "native_backtest/out/data_audit/test_window_gate5"
GATE_CODE = ROOT / "stage2/scoring/check_dividend_adjustment.py"
TICKERS = ("SPY", "IEF", "LQD", "TLT")

# Pre-registered window (see the pre-registration document).
EX_START = pd.Timestamp("2023-02-02")
LAST_PRICE = pd.Timestamp("2026-10-01")
MONTHS = pd.period_range("2023-01", "2026-09", freq="M")
MONTH_END_NAV_FROM = pd.Timestamp("2022-12-01")   # SPY month-end NAVs: 2022-12 (base) .. 2026-09

# Columns the gate computes internally that are returns; dropped before saving (isolation rule).
DROP_PER_DATE = ["raw_nav_move_bp", "official_nav_total_return_bp", "adjusted_price_return_bp", "nav_prev", "nav_ex",
                 "raw_prev_low", "raw_prev_high"]
DROP_MONTHLY = ["adjusted_return_bp", "official_nav_total_return_bp"]


def sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read_capture(name: str, manifest: dict) -> list:
    b = (RAW / name).read_bytes()
    if b.endswith(b"\n"):
        b = b[:-1]
    got, want = hashlib.sha256(b).hexdigest(), manifest["captures"][name]["sha256"]
    if got != want:
        raise SystemExit(f"STOP: capture {name} sha256 {got} != browser-side {want}")
    return [line.split(",") for line in b.decode().split("\n") if line]


def ymd(s: str) -> str:
    return f"{s[:4]}-{s[4:6]}-{s[6:]}" if len(s) == 8 and s.isdigit() else s


def build_records(manifest: dict):
    dist, pairs, monthly_tr, month_end_nav = [], [], [], []
    for t in ("IEF", "LQD", "TLT"):
        for rec, ex, pay, tot, inc, st, lt, roc in read_capture(f"{t}_distributions.txt", manifest):
            dist.append({"ticker": t, "ex_date": ymd(ex), "record_date": ymd(rec), "payable_date": ymd(pay),
                         "distribution_per_share": float(tot), "income": float(inc), "st_cap_gain": float(st or 0),
                         "lt_cap_gain": float(lt or 0), "return_of_capital": float(roc or 0)})
        for ex, prev, nav_prev, nav_ex, exdiv in read_capture(f"{t}_navpairs.txt", manifest):
            pairs.append({"ticker": t, "ex_date": ex, "prev_nav_date": prev, "nav_prev": float(nav_prev),
                          "nav_ex": float(nav_ex), "nav_file_ex_dividend": float(exdiv)})
        for d, v in read_capture(f"{t}_monthly.txt", manifest):
            monthly_tr.append({"ticker": t, "month_end": d, "nav_total_return_pct": float(v)})
    for rec, ex, pay, div, st, lt, *_ in read_capture("SPY_distributions.txt", manifest):
        dist.append({"ticker": "SPY", "ex_date": ex, "record_date": rec, "payable_date": pay, "distribution_per_share": float(div),
                     "income": float(div), "st_cap_gain": float(st or 0), "lt_cap_gain": float(lt or 0), "return_of_capital": 0.0})
    for ex, prev, nav_prev, nav_ex in read_capture("SPY_navpairs.txt", manifest):
        pairs.append({"ticker": "SPY", "ex_date": ex, "prev_nav_date": prev, "nav_prev": float(nav_prev), "nav_ex": float(nav_ex),
                      "nav_file_ex_dividend": float("nan")})
    for d, v in read_capture("SPY_monthend_nav.txt", manifest):
        month_end_nav.append({"ticker": "SPY", "nav_date": d, "nav": float(v)})

    dist_df = pd.DataFrame(dist).sort_values(["ticker", "ex_date"]).reset_index(drop=True)
    pairs_df = pd.DataFrame(pairs).sort_values(["ticker", "ex_date"]).reset_index(drop=True)
    stops = []
    m = dist_df.merge(pairs_df, on=["ticker", "ex_date"], how="outer", indicator=True)
    if (m["_merge"] != "both").any():
        stops.append(f"ex-dates differ between the distribution and NAV captures: {m[m['_merge'] != 'both'][['ticker', 'ex_date', '_merge']].to_dict('records')}")
    ish = m[(m["ticker"] != "SPY") & (m["_merge"] == "both")]
    bad = ish[(ish["distribution_per_share"] - ish["nav_file_ex_dividend"]).abs() > 1e-9]
    if len(bad):
        stops.append(f"iShares distribution table and NAV-file ex-dividend column disagree: {bad[['ticker', 'ex_date']].to_dict('records')}")
    if (dist_df[["st_cap_gain", "lt_cap_gain", "return_of_capital"]].abs().sum(axis=1) > 0).any():
        stops.append("non-income distribution component present")
    out_of_window = dist_df[(pd.to_datetime(dist_df.ex_date) < EX_START) | (pd.to_datetime(dist_df.ex_date) > LAST_PRICE)]
    if len(out_of_window):
        stops.append(f"captured ex-dates outside the pre-registered window: {out_of_window[['ticker', 'ex_date']].to_dict('records')}")
    if stops:
        raise SystemExit("STOP: " + " | ".join(stops))

    DATA.mkdir(parents=True, exist_ok=True)
    dist_df.to_csv(DATA / "official_distributions.csv", index=False, float_format="%.6f")
    pairs_df.to_csv(DATA / "official_nav_exdate_pairs.csv", index=False, float_format="%.6f")
    mtr = pd.DataFrame(monthly_tr)
    mtr.to_csv(DATA / "official_monthly_nav_total_return_ishares.csv", index=False)
    men = pd.DataFrame(month_end_nav)
    men.to_csv(DATA / "official_month_end_nav_ssga.csv", index=False, float_format="%.6f")
    normalized = {p.name: sha_file(p) for p in sorted(DATA.glob("official_*.csv"))}
    return dist_df, pairs_df, mtr, men, normalized


def diagnose_c1(sums: list, pairs: pd.DataFrame, manifest: dict) -> list:
    """Read-only diagnosis of C1 'previous NAV date' mismatches, after the gate has run.

    For each mismatch, the official NAV on the scorer's previous trading day is read from a hash-verified diagnostic
    capture of the same issuer file (all rows around the date) and compared with the NAV the gate used. Equal values
    mean the official file only carries the NAV forward onto non-trading days, so the residual the gate computed is
    unaffected. Anything else is left as an unexplained exception."""
    out = []
    diag = manifest.get("diagnostic_captures", {})
    for s in sums:
        for prob in s["C1_coverage"]["problems"]:
            parts = prob.split()
            if "previous trading day" not in prob:
                out.append({"ticker": s["ticker"], "problem": prob, "finding": "not diagnosed"})
                continue
            ex, scorer_prev, official_prev = parts[0], parts[4], parts[-2]
            name = next((k for k, v in diag.items() if v["source"] == s["ticker"]), None)
            if name is None:
                out.append({"ticker": s["ticker"], "problem": prob, "finding": "no diagnostic capture"})
                continue
            b = (RAW / name).read_bytes().rstrip(b"\n")
            if hashlib.sha256(b).hexdigest() != diag[name]["sha256"]:
                raise SystemExit(f"STOP: diagnostic capture {name} hash mismatch")
            nav = {d: (float(v), x) for d, v, x in (line.split(",") for line in b.decode().split("\n"))}
            used = pairs[(pairs.ticker == s["ticker"]) & (pairs.ex_date == pd.Timestamp(ex))].nav_prev.iloc[0]
            between = sorted(d for d in nav if scorer_prev < d < ex)
            same = scorer_prev in nav and abs(nav[scorer_prev][0] - used) < 1e-9 and all(abs(nav[d][0] - used) < 1e-9 for d in between)
            out.append({"ticker": s["ticker"], "ex_date": ex, "scorer_previous_trading_day": scorer_prev,
                        "official_previous_nav_date": official_prev[:10], "official_nav_on_scorer_previous_day": nav.get(scorer_prev, (None,))[0],
                        "nav_used_by_gate": float(used), "official_rows_between": {d: nav[d][0] for d in between},
                        "nav_identical": bool(same), "diagnostic_capture": name,
                        "finding": ("Official file carries the NAV of the scorer's previous trading day forward onto non-trading days "
                                    "(" + ", ".join(between) + "); the NAV used is identical, so the residual is unaffected. Calendar labelling "
                                    "in the official record, not an adjustment problem.") if same else "NAV differs: unexplained exception"})
    return out


def main() -> int:
    manifest = json.loads((RAW / "capture_manifest.json").read_text())
    dist, pairs, mtr, men, normalized = build_records(manifest)
    dist["ex_date"] = pd.to_datetime(dist["ex_date"])
    pairs["ex_date"] = pd.to_datetime(pairs["ex_date"])
    pairs["prev_nav_date"] = pd.to_datetime(pairs["prev_nav_date"])
    mtr["month_end"] = pd.to_datetime(mtr["month_end"])
    men["nav_date"] = pd.to_datetime(men["nav_date"])

    cfg = load_config()
    mk = load_market(cfg)                      # refuses to load if any pinned input differs from its recorded SHA-256
    price_hashes = {}
    gate5.EX_START, gate5.LAST_DEV_PRICE, gate5.MONTHS = EX_START, LAST_PRICE, MONTHS
    per_all, mon_all, sums = [], [], []
    for t in TICKERS:
        adj = mk.prices[t]
        adj = adj[adj.index <= LAST_PRICE]
        seg = _abs(cfg["_prices"][t]["segments"][-1])
        price_hashes[t] = {"file": str(Path(seg["path"]).relative_to(ROOT)), "sha256": sha_file(Path(seg["path"]))}
        f = pd.read_csv(Path(seg["path"]), sep=None, engine="python", parse_dates=["Date"]).set_index("Date")
        f = f[(f.index >= pd.Timestamp(seg["start_inclusive"])) & (f.index <= LAST_PRICE)]
        if not np.allclose(f["Close"].to_numpy(), adj.reindex(f.index).to_numpy(), rtol=0, atol=1e-9):
            raise SystemExit(f"STOP: 2018+ Close for {t} differs from the shared evaluator's series")
        raw = f.rename(columns={"Close": "adj"})[["High", "Low", "adj"]]
        me_nav = men[(men.ticker == t) & (men.nav_date >= MONTH_END_NAV_FROM)]
        monthly = gate5.monthly_official(t, dist, pairs, mtr, me_nav)
        per, mon, s = gate5.check_ticker(t, adj, raw, dist, pairs, monthly)
        per_all.append(per.drop(columns=[c for c in DROP_PER_DATE if c in per.columns]))
        mon_all.append(mon.drop(columns=DROP_MONTHLY))
        sums.append(s)

    OUT.mkdir(parents=True, exist_ok=True)
    pd.concat(per_all).to_csv(OUT / "gate5_by_ex_date.csv", index=False, float_format="%.6f")
    pd.concat(mon_all).to_csv(OUT / "gate5_by_month.csv", index=False, float_format="%.4f")
    exceptions = []
    for s in sums:
        for k in [k for k in s if k.startswith("C")]:
            if not s[k]["pass"]:
                exceptions.append({"ticker": s["ticker"], "criterion": k,
                                   "detail": {x: s[k][x] for x in s[k] if x not in ("pass",)}})
    diagnosis = diagnose_c1(sums, pairs, manifest)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    status = {
        "audit": "Test-window distribution audit (Stage 2 gate 5 criteria C1-C6, unchanged)",
        "preregistration": "native_backtest/docs/TEST_WINDOW_DISTRIBUTION_AUDIT_PREREGISTRATION_2026-10-28.md",
        "isolation": "No strategy, decision record, portfolio, benchmark, CER or performance comparison was run, read or produced. Return columns are dropped before saving.",
        "window": {"ex_dates": [EX_START.date().isoformat(), LAST_PRICE.date().isoformat()], "months": [str(MONTHS[0]), str(MONTHS[-1])],
                   "price_cutoff": LAST_PRICE.date().isoformat()},
        "status": "PASS" if all(s["pass"] for s in sums) else "FAIL",
        "by_ticker": sums, "exceptions": exceptions,
        "exception_diagnosis": diagnosis,
        "diagnosis_note": "Read-only and after the gate: it never changes the gate status, a criterion or a threshold.",
        "versions": {"gate_code": {"file": str(GATE_CODE.relative_to(ROOT)), "sha256": sha_file(GATE_CODE)},
                     "price_files_2018_plus": price_hashes, "official_records": manifest, "normalized_records_sha256": normalized,
                     "repository_head": head},
    }
    (OUT / "gate5_status.json").write_text(json.dumps(status, indent=2, default=float) + "\n")
    for s in sums:
        print(s["ticker"], "PASS" if s["pass"] else "FAIL", {k: s[k]["pass"] for k in s if k.startswith("C")},
              "n_ex", s["n_ex_dates"], "C2", round(s["C2_ex_date_capture"]["kappa"], 3), "C3", round(s["C3_monthly_capture"]["kappa"], 3),
              "C4", round(s["C4_cumulative_capture"]["kappa"], 4))
    print("AUDIT:", status["status"], f"({len(exceptions)} exceptions)")
    return 0 if status["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
