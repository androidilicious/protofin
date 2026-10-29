#!/usr/bin/env python3
"""Refresh RELEASE_MANIFEST.sha256: SHA-256 of the committed results, configurations, approval records and
vendored code, verifiable with `sha256sum -c RELEASE_MANIFEST.sha256`.

Keeps every file already listed (in its order) and appends the files in ADD that are not yet listed. Files that
no longer exist are reported and dropped. mvp/data/dashboard.json is never listed (it records its build time).

Usage (repository root): python -m native_backtest.scripts.release_manifest [--check]
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "RELEASE_MANIFEST.sha256"
ADD = [
    "native_backtest/ap3/variants_v1.json",
    "native_backtest/ap3/fixtures/testing_agent_fixtures_v1.json",
    "native_backtest/config/ap3_reliability_gates_v1.json",
    "native_backtest/config/approvals/ap3_inference_approval_A.json",
    "native_backtest/data/ap3_corpus/fetch_manifest_v1.json",
    "native_backtest/data/ap3_corpus/archive_manifest_v1.json",
    "native_backtest/out/ap3/corpus_manifest_v1.json",
    "native_backtest/out/ap3/corpus_checks_v1.json",
    "native_backtest/out/ap3/engineering_replay/reduced_evidence/summary.json",
    "native_backtest/out/ap3/engineering_g3b/engineering_mock/summary.json",
    "native_backtest/config/budget_v1.json",
    "native_backtest/notebooks/ap3_qwen3_free_run.ipynb",
    "native_backtest/out/audit/portfolio_integrity_v1.json",
    "native_backtest/out/audit/reconstruction_v1.csv",
    "native_backtest/out/signal_value/signal_value_v1.json",
    "native_backtest/out/signal_value/monthly_v1.csv",
    "native_backtest/out/signal_value/independent_check_v1.json",
    "native_backtest/out/signal_value/jev_native_signal_on_off_engine.json",
    "native_backtest/out/ap3/qwen3_runs/summary.json",
    "native_backtest/out/ap3/qwen3_runs/import_report.json",
    "native_backtest/out/within_approach/within_approach_v1.json",
    "native_backtest/out/within_approach/regime_labels_v1.csv",
    "native_backtest/out/within_approach/committee_plus_jev_weights_v1.csv",
    "native_backtest/out/decisions/AP2_COMBO.jsonl",
    "native_backtest/config/within_approach_preregistration_v1.json",
    "native_backtest/config/ap3_exploratory_mode_v1.json",
    "native_backtest/config/ap3_reliability_followup_preregistration_v1.json",
]
NEVER = {"mvp/data/dashboard.json"}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def entries() -> list:
    return [l.split("  ", 1)[1] for l in MANIFEST.read_text().splitlines() if l.strip()]


def check() -> list:
    bad = []
    for l in MANIFEST.read_text().splitlines():
        h, f = l.split("  ", 1)
        p = ROOT / f
        if not p.exists() or sha(p) != h:
            bad.append(f)
    return bad


def refresh() -> dict:
    files = [f for f in entries() if f not in NEVER]
    files += [f for f in ADD if f not in files and f not in NEVER]
    gone = [f for f in files if not (ROOT / f).exists()]
    keep = [f for f in files if f not in gone]
    MANIFEST.write_text("".join(f"{sha(ROOT / f)}  {f}\n" for f in keep))
    return {"files": len(keep), "dropped_missing": gone}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.check:
        bad = check()
        print("OK" if not bad else "FAILED: " + ", ".join(bad))
        return 0 if not bad else 1
    print(refresh())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
