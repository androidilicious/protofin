#!/usr/bin/env python3
"""Build AP1 decision records from a development run of the unchanged Stage 2 scorer, and check that
the run reproduces the saved canonical development results byte for byte.

Usage: python -m native_backtest.scripts.build_ap1_decisions [--run-dir native_backtest/out/ap1/stage2_dev_rerun]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from native_backtest.adapters.ap1_stage2 import build_records_from_stage2_run
from native_backtest.framework.market import load_config, load_market
from native_backtest.framework.records import write_jsonl

ROOT = Path(__file__).resolve().parents[2]
SAVED = ROOT / "stage2/results/dev_rerun_v4_portfolio_2026-10-27"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", type=Path, default=ROOT / "native_backtest/out/ap1/stage2_dev_rerun")
    args = ap.parse_args()
    check = json.loads((args.run_dir / "development_reproduction_check.json").read_text())
    same = {f: hashlib.sha256((args.run_dir / f).read_bytes()).digest() == hashlib.sha256((SAVED / f).read_bytes()).digest()
            for f in ("stage2_portfolio_returns.csv", "stage2_predictions.csv", "stage2_portfolio_metrics.csv")}
    recs = build_records_from_stage2_run(args.run_dir, load_market(load_config()))
    h = write_jsonl(recs, ROOT / "native_backtest/out/decisions/AP1.jsonl")
    rep = {"stage2_reproduction_check": check.get("status"), "n_differences": check.get("n_differences"),
           "byte_identical_to_saved": same, "records": len(recs), "first": recs[0].decision_month, "last": recs[-1].decision_month, "sha256": h}
    (ROOT / "native_backtest/out/ap1/ap1_native_reproduction_report.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1))
    return 0 if rep["stage2_reproduction_check"] == "MATCH" and all(same.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
