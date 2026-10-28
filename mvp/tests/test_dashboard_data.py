"""Data contract for mvp/data/dashboard.json (the only file the dashboard reads)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
D = json.loads((ROOT / "mvp" / "data" / "dashboard.json").read_text())
REPORT = json.loads((ROOT / "native_backtest/out/development/development_evaluation_report.json").read_text())
SRC = {"det": "AP1", "com": "AP2A", "jev": "AP2B"}


def test_four_systems_with_display_names():
    names = [s["name"] for s in D["systems"]]
    assert names == ["Deterministic Quantitative Model", "Agentic Workflow — Agent Committee", "Agentic Workflow — JEV", "Agentic Causal RAG"]


def test_no_internal_labels_in_display_text():
    shown = json.dumps({k: v for k, v in D.items() if k not in ("dev", "extended")}, ensure_ascii=False)
    assert not re.search(r"\bAP[123]\b|AP2-?[AB]|engineering_mock|\.jsonl", shown)


def test_only_development_months_are_scored():
    months = D["dev"]["months"] + D["extended"]["months"]
    assert max(months) < D["windows"]["historical_test"][0] == "2023-01"
    assert D["windows"]["historical_test_status"] == "sealed"
    for s in D["dev"]["series"].values():
        assert len(s["wealth"]) == len(D["dev"]["months"]) == 46


@pytest.mark.parametrize("key", ["det", "com", "jev"])
def test_numbers_match_the_development_report(key):
    rep = next(x for x in REPORT["common_evaluation_matched_dev"] if x["system"] == SRC[key])
    m = D["dev"]["series"][key]["metrics"]
    assert m["cer"] == pytest.approx(rep["absolute"]["cer_delta_2_5"], abs=1e-6)
    assert m["sharpe"] == pytest.approx(rep["absolute"]["net_sharpe"], abs=1e-4)
    assert m["max_drawdown"] == pytest.approx(rep["absolute"]["max_drawdown"], abs=1e-6)
    assert D["dev"]["series"][key]["vs_neutral"]["cer_difference"] == pytest.approx(rep["vs_own_neutral"]["cer_difference"], abs=1e-6)


def test_causal_rag_has_no_results_and_demo_is_labelled():
    rag = next(s for s in D["systems"] if s["key"] == "rag")
    assert rag["has_results"] is False and "rag" not in D["dev"]["series"]
    demo = D["ap3"]["demo"]
    assert demo is None or (demo["is_mock"] is True and "not a result" in demo["label"])
    if demo:
        assert all("title" not in h for h in demo["hypotheses"])  # no claims-dataset text


def test_weights_sum_to_one():
    for s in D["dev"]["series"].values():
        cols = list(s["weights"].values())
        for i in range(len(cols[0])):
            assert sum(c[i] for c in cols) == pytest.approx(1.0, abs=2e-4)


def test_plain_language_labels():
    """Benchmarks, models and notes read in plain words (usability review)."""
    for b in list(D["dev"]["benchmarks"].values()) + list(D["extended"]["benchmarks"].values()):
        assert not re.search(r"\b(SPY|TLT|IEF|LQD)\b", b["label"]), b["label"]
    shown = json.dumps([D["systems"], D["notes"], D["reproduction"], D["native_vs_common"]], ensure_ascii=False)
    assert not re.search(r"TypeSafe|temperature|spending approval|Native replay|\brace\b", shown)
    assert D["notes"]["headline"].startswith("2019–2022") and "sealed" in D["notes"]["headline"]
