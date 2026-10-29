"""Test-window distribution audit: isolation and provenance (no strategy, portfolio or return output)."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "native_backtest/scripts/audit_test_window_distributions.py"
OUT = ROOT / "native_backtest/out/data_audit/test_window_gate5"
RAW = ROOT / "native_backtest/data/test_window_dividend_audit/raw_capture"
FORBIDDEN = ("accounting", "benchmark", "records", "lock", "metrics", "adapters", "ap1", "ap2", "ap3")


def test_audit_imports_no_strategy_or_scoring_code():
    tree = ast.parse(SCRIPT.read_text())
    mods = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module] + \
           [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    assert "native_backtest.framework.market" in mods and "check_dividend_adjustment" in mods
    assert not [m for m in mods if any(f".{f}" in f".{m}" or m.endswith(f) for f in FORBIDDEN)], mods


def test_audit_outputs_hold_no_return_series():
    per = pd.read_csv(OUT / "gate5_by_ex_date.csv")
    mon = pd.read_csv(OUT / "gate5_by_month.csv")
    banned = {"adjusted_price_return_bp", "official_nav_total_return_bp", "raw_nav_move_bp", "adjusted_return_bp", "nav_prev", "nav_ex"}
    assert not banned & set(per.columns) and not banned & set(mon.columns)
    status = json.loads((OUT / "gate5_status.json").read_text())
    text = json.dumps(status).lower()
    assert "cer" not in [k.lower() for k in status] and "portfolio_return" not in text and "sharpe" not in text


def test_captures_match_browser_side_hashes_and_window():
    man = json.loads((RAW / "capture_manifest.json").read_text())
    for name, c in {**man["captures"], **man.get("diagnostic_captures", {})}.items():
        assert hashlib.sha256((RAW / name).read_bytes().rstrip(b"\n")).hexdigest() == c["sha256"], name
    status = json.loads((OUT / "gate5_status.json").read_text())
    assert status["window"] == {"ex_dates": ["2023-02-02", "2026-10-01"], "months": ["2023-01", "2026-09"], "price_cutoff": "2026-10-01"}
    for t in status["by_ticker"]:
        assert "2023-02-02" <= t["first_ex_date"] and t["last_ex_date"] <= "2026-10-01"


def test_criteria_thresholds_are_the_development_gates():
    import sys
    sys.path.insert(0, str(ROOT / "stage2" / "scoring"))
    import check_dividend_adjustment as g
    assert g.KAPPA_BAND == (0.75, 1.25) and g.KAPPA_CUM_BAND == (0.90, 1.10) and g.Z99 == 2.576 and g.INFORMATIVE_SIGMAS == 6.0
    status = json.loads((OUT / "gate5_status.json").read_text())
    assert status["versions"]["gate_code"]["sha256"] == hashlib.sha256((ROOT / "stage2/scoring/check_dividend_adjustment.py").read_bytes()).hexdigest()
    # every exception is listed; every C1 exception has a read-only diagnosis
    c1 = [e for e in status["exceptions"] if e["criterion"] == "C1_coverage"]
    assert len(status["exception_diagnosis"]) == sum(len(e["detail"]["problems"]) for e in c1)
