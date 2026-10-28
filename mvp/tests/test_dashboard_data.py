"""Data contract for mvp/data/dashboard.json (the only file the dashboard reads)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
D = json.loads((ROOT / "mvp" / "data" / "dashboard.json").read_text())
REPORT = json.loads((ROOT / "native_backtest/out/development/development_evaluation_report.json").read_text())
CFG = json.loads((ROOT / "native_backtest/config/framework_config_v1.json").read_text())
SRC = {"det": "AP1", "com": "AP2A", "jev": "AP2B"}


def test_exactly_three_primary_approaches():
    names = [s["name"] for s in D["systems"]]
    assert names == ["Deterministic Quantitative Model", "Agentic Workflow — JEV", "Agentic Causal RAG"]
    assert all(s["role"] == "primary" for s in D["systems"]) and D["primary"] == ["det", "jev", "rag"]
    # the primary family in the config is the same three approaches
    assert [p["system"] for p in CFG["research_design"]["primary_approaches"]] == ["AP1", "AP2B", "AP3"]


def test_committee_is_a_within_approach_variant():
    assert [v["name"] for v in D["variants"]] == ["Agentic Workflow — Agent Committee"]
    assert D["variants"][0]["role"] == "variant"
    groups = {g["approach"]: g for g in D["experiments"]["groups"]}
    assert list(groups) == ["det", "jev", "rag"]
    aw = groups["jev"]
    assert aw["base"]["name"] == "JEV only" and aw["base"]["status"] == "tested"
    assert {v["name"]: v["status"] for v in aw["variants"]} == {"Agent Committee only": "tested", "Committee + JEV": "planned"}
    # the Committee never enters the primary family
    fam = REPORT["primary_contrasts_matched_dev"]["family"]
    assert fam == ["AP2B-AP1", "AP3-AP1", "AP3-AP2B"] and not any("AP2A" in f for f in fam)
    assert [(c["a"], c["b"]) for c in D["dev"]["within_contrasts"]] == [("com", "jev")]
    assert (D["experiments"]["within_contrast"]["a"], D["experiments"]["within_contrast"]["b"]) == ("com", "jev")


def test_experiment_statuses_match_the_research_design():
    """Every within-approach experiment carries one status class; nothing proposed or paused is shown as run."""
    cfg_groups = CFG["research_design"]["within_approach_experiments"]["groups"]
    shown = D["experiments"]["groups"]
    assert len(cfg_groups) == len(shown) == 3
    for c, g in zip(cfg_groups, shown):
        assert [v["status"] for v in c["variants"]] == [v["status"] for v in g["variants"]]
        assert c["base"]["status"] == g["base"]["status"]
    det, rag = shown[0], shown[2]
    assert {v["status"] for v in det["variants"]} == {"paused", "planned"}          # signal experiments are on hold
    assert rag["base"]["status"] == "awaiting_validation" and all(v["status"] == "planned" for v in rag["variants"])
    assert all(v["link"] is None for g in shown for v in g["variants"] if v["status"] != "tested")
    assert "secondary" not in D["experiments"]


def test_methodology_and_validation_blocks():
    m = D["methodology"]
    assert [p["key"] for p in m["phases"]] == ["train", "dev", "test", "live"]
    assert m["phases"][0]["from"] == "2015-02" and m["phases"][2]["from"] == "2023-01" and m["phases"][2]["to"] == "2026-08"
    assert any("2024" in t and "proposed" in t for t in m["pending"])           # the window split is flagged, not applied
    assert {x["status"] for x in m["settings"]} <= {"frozen", "approval", "design"}
    v = D["validation"]
    assert v["decision"] == "NO-GO" and v["columns"] == ["det", "jev", "rag", "com"]
    assert all(set(g["cells"]) == {"det", "jev", "rag", "com"} for g in v["gates"])
    assert all(c["status"] in {"pass", "review", "pending", "blocked", "na"} for g in v["gates"] for c in g["cells"].values())
    assert not any(g["cells"]["rag"]["status"] == "pass" for g in v["gates"] if "smoke" in g["name"] or "replay" in g["name"])


def test_no_internal_labels_in_display_text():
    shown = json.dumps({k: v for k, v in D.items() if k != "dev"}, ensure_ascii=False)
    assert not re.search(r"\bAP[123]\b|AP2-?[AB]|engineering_mock|\.jsonl", shown)


def test_only_development_months_are_scored():
    assert "extended" not in D
    assert max(D["dev"]["months"]) < D["windows"]["historical_test"][0] == "2023-01"
    assert D["windows"]["historical_test_status"] == "sealed"
    assert D["windows"]["training"][0] == "2015-02"
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


def test_primary_contrasts_match_the_report():
    items = D["dev"]["primary_contrasts"]["items"]
    assert D["dev"]["primary_contrasts"]["family_size"] == 3
    done = [i for i in items if i["computed"]]
    assert [(i["a"], i["b"]) for i in done] == [("jev", "det")]
    assert done[0]["cer_difference"] == pytest.approx(REPORT["primary_contrasts_matched_dev"]["computed"]["AP2B-AP1"]["cer_difference"], abs=1e-6)
    assert [(i["a"], i["b"]) for i in items if not i["computed"]] == [("rag", "det"), ("rag", "jev")]


def test_causal_rag_awaiting_validation_and_demo_is_labelled():
    rag = next(s for s in D["systems"] if s["key"] == "rag")
    assert rag["has_results"] is False and "rag" not in D["dev"]["series"]
    assert rag["status_label"] == D["ap3"]["status_label"] == "Awaiting validation · results unavailable"
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
    for b in D["dev"]["benchmarks"].values():
        assert not re.search(r"\b(SPY|TLT|IEF|LQD)\b", b["label"]), b["label"]
    shown = json.dumps([D["systems"], D["variants"], D["notes"], D["reproduction"], D["native_vs_common"], D["experiments"], D["flows"],
                        D["methodology"], D["validation"]], ensure_ascii=False)
    assert not re.search(r"TypeSafe|temperature|spending approval|Native replay|\brace\b|[Cc]ompound annual", shown)
    assert D["notes"]["headline"].startswith("Development diagnostics") and "sealed" in D["notes"]["headline"]


def test_cer_is_defined_as_certainty_equivalent_return():
    assert "certainty-equivalent return" in CFG["research_design"]["primary_metric"]
    js = (ROOT / "mvp" / "assets" / "app.js").read_text()
    assert "Net CER = Certainty-Equivalent Return" in js and "It is not a compound annual return" in js
