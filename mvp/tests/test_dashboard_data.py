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
REPORT_ROWS = {x["system"]: x for x in REPORT["common_evaluation_matched_dev"]}
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
    assert {v["name"]: v["status"] for v in aw["variants"]} == {"Agent Committee only": "tested", "Committee + JEV": "tested"}
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
    # the Deterministic experiments were resumed and completed on 2026-10-29 (pre-registered first)
    assert {v["name"]: v["status"] for v in det["variants"]} == {"Add one financial signal at a time": "tested",
                                                                 "All five financial signals together": "tested", "Market regimes": "tested"}
    assert rag["base"]["status"] == "awaiting_validation"
    versions = {v["name"]: v["status"] for v in rag["variants"][:2]}
    assert versions == {"Causal RAG — Reduced Evidence": "awaiting_validation", "Causal RAG — With Historical Documents": "blocked"}
    assert rag["variants"][2]["name"] == "Policy-path proxy variant" and rag["variants"][2]["status"] == "awaiting_validation"
    assert all(v["status"] == "planned" for v in rag["variants"][3:])
    # nothing untested links to results: the two Causal RAG versions link only to the explanation page, which shows none
    assert all(v["link"] in (None, "rag") for g in shown for v in g["variants"] if v["status"] != "tested")
    # no Causal RAG experiment may be called tested, and results are attached only to experiments that ran
    assert not any(v["status"] == "tested" for v in rag["variants"]) and rag["base"]["status"] != "tested"
    assert all(v["status"] == "tested" for g in shown for v in g["variants"] if "result" in v)
    assert sum("result" in v for g in shown for v in g["variants"]) == 4
    V = D["ap3"]["versions"]
    assert V["primary"] is None and [i["key"] for i in V["items"]] == ["re", "hd"]
    assert not any(c["done"] for i in V["items"] for c in i["checks"] if "real-model" in c["text"].lower() or "Real model" in c["text"])
    assert "secondary" not in D["experiments"]


def test_methodology_and_validation_blocks():
    m = D["methodology"]
    assert [p["key"] for p in m["phases"]] == ["train", "dev", "test", "live"]
    assert m["phases"][0]["from"] == "2015-02" and m["phases"][2]["from"] == "2023-01" and m["phases"][2]["to"] == "2026-08"
    assert not any("2024" in t for t in m["pending"])                           # the window split is decided (config v1.5)
    ev = {x["name"]: x for x in m["settings"]}["Evaluation periods"]
    assert "Jan 2024 – Aug 2026" in ev["value"] and "2023 reported separately" in ev["value"] and ev["status"] == "frozen"
    assert {x["name"]: x for x in m["settings"]}["Primary metric"]["status"] == "frozen"
    assert CFG["windows"]["historical_test"]["primary"] == ["2024-01", "2026-08"] and CFG["windows"]["protected"] == ["2023-01", "2026-08"]
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


# ---------------------------------------------------------------- common benchmark
def test_common_benchmark_is_one_spy_ief_reference_awaiting_freeze():
    cb = D["dev"]["common_benchmark"]
    assert cb["weights"] == {"SPY": 0.6, "IEF": 0.4} == CFG["common_benchmark"]["weights"]
    assert cb["label"] == "Passive Portfolio Reference — 60% SPY / 40% IEF"
    assert cb["formal_label"] == "60% US Equities / 40% Intermediate-Term Treasuries"
    assert cb["status"] == "frozen" and cb["status_label"] == "Frozen"
    assert len(cb["wealth"]) == len(D["dev"]["months"])
    rep = REPORT["common_benchmark_matched_dev"]["benchmark"]
    assert abs(cb["metrics"]["cer"] - rep["cer_delta_2_5"]) < 1e-6
    assert "not a neutral portfolio" in cb["not_neutral"] and "skill" in cb["not_neutral"] and len(cb["rules"]) == 5


@pytest.mark.parametrize("key", ["det", "jev", "com"])
def test_vs_common_and_decomposition_match_the_report(key):
    s = D["dev"]["series"][key]
    row = {r["system"]: r for r in REPORT["common_benchmark_matched_dev"]["systems"]}[SRC[key]]
    assert abs(s["vs_common"]["cer_difference"] - row["vs_common"]["cer_difference"]) < 1e-6
    a = s["decomposition"]
    assert abs(a["total"] - a["decisions"] - a["mix"]) < 2e-6           # exact up to display rounding
    assert abs(a["decisions"] - s["vs_neutral"]["cer_difference"]) < 2e-6   # decisions part = vs own benchmark
    assert "cumulative_return" in s["metrics"]


def test_common_benchmark_leaves_primary_contrasts_unchanged():
    gaps = REPORT["common_benchmark_matched_dev"]["check_primary_gaps_unchanged"]
    assert gaps and max(gaps.values()) < 1e-12
    # the primary family is still the three pairwise approach contrasts, with no benchmark in it
    assert all("COMMON" not in p for p in REPORT["primary_contrasts_matched_dev"]["family"])


def test_causal_rag_has_no_benchmark_comparison():
    assert "rag" not in D["dev"]["series"]
    row = {r["system"]: r for r in REPORT["common_benchmark_matched_dev"]["systems"]}["AP3"]
    assert "vs_common" not in row and row["status"].startswith("pending")


def test_deterministic_is_the_research_baseline_and_contrasts_are_unchanged():
    rd = CFG["research_design"]
    assert rd["research_baseline"]["system"] == "AP1"
    assert CFG["primary_contrasts"] == [["AP2B", "AP1"], ["AP3", "AP1"], ["AP3", "AP2B"]] and CFG["metrics"]["multiplicity"] == "Holm"
    items = D["dev"]["primary_contrasts"]["items"]
    assert [(i["a"], i["b"]) for i in items] == [("jev", "det"), ("rag", "det"), ("rag", "jev")]
    assert items[0]["computed"] and not items[1]["computed"] and not items[2]["computed"]
    # the passive reference is not an approach and keeps its frozen numbers
    assert all(s["key"] != "passive" for s in D["systems"]) and CFG["common_benchmark"]["status"] == "frozen"
    assert "fourth approach" in CFG["research_design"]["passive_reference"]


def test_similarity_diagnostic_comes_from_the_independent_audit():
    """The optional 'why do the curves look alike' view: verdict and numbers from the integrity audit, spread from the dashboard's own returns."""
    A = D["audit"]
    audit = json.loads((ROOT / "native_backtest/out/audit/portfolio_integrity_v1.json").read_text())
    assert A["verdict"] == audit["verdict"] == "no implementation error found" and A["findings"] == 0
    assert A["max_abs_diff_net_return"] < 1e-12
    assert A["corr_monthly_net"] == round(audit["similarity"]["corr_monthly_net"], 4)
    assert abs(A["corr_decisions"]) < 0.1 < A["corr_own_mixes"]
    det, jev = D["dev"]["series"]["det"]["monthly_net_return"], D["dev"]["series"]["jev"]["monthly_net_return"]
    assert len(A["spread"]) == len(D["dev"]["months"]) == len(det)
    assert all(abs(s - (j - d)) <= 2e-6 for s, j, d in zip(A["spread"], jev, det))
    assert abs(A["share_from_mixes"] + A["share_from_decisions"] - 1) < 2e-3


def test_signal_value_section_matches_the_analysis_and_earlier_results():
    """'Do the signals actually add value?': numbers from the signal value analysis, which reproduces the report exactly."""
    V = D["signal_value"]
    r = json.loads((ROOT / "native_backtest/out/signal_value/signal_value_v1.json").read_text())
    for key, src in (("det", "AP1"), ("jev", "AP2B")):
        s, prev = V["systems"][key], REPORT_ROWS[src]["vs_own_neutral"]
        assert s["value"]["cer_difference"] == round(prev["cer_difference"], 6) and s["value"]["p"] == round(prev["p_two_sided_bootstrap"], 4)
        assert s["value"]["clear"] is False and s["no_signal"] == D["dev"]["series"][key]["neutral"]
        assert abs(s["with"]["cer"] - s["without"]["cer"] - s["value"]["cer_difference"]) < 2e-6
        assert len(s["active"]) == len(D["dev"]["months"])
    g = V["gap"]
    assert abs(sum(g["parts"].values()) - g["total"]["cer_difference"]) < 5e-6
    assert abs(g["mix"]["cer_difference"] + g["signals"]["cer_difference"] - g["total"]["cer_difference"]) < 2e-6
    assert g["total"]["cer_difference"] == round(r["questions"]["jev_minus_deterministic_total"]["point"], 6)
    assert V["checks"]["reproduces_previous"] is True and V["checks"]["independent_checks"] >= 200
    assert [s["key"] for s in D["systems"]] == ["det", "jev", "rag"]      # no extra primary approach


def test_signal_value_tab_numbers_match_the_reports():
    """Every headline number of the Signal Value-Added tab, as displayed (rounded), equals the verified analysis and
    appears in the two canonical reports."""
    V, A = D["signal_value"], D["audit"]
    r = json.loads((ROOT / "native_backtest/out/signal_value/signal_value_v1.json").read_text())
    p2 = lambda x: round(x * 100, 2)
    shown = {"det": (3.67, 3.77, -0.11, 0.17, (-0.31, 0.03)), "jev": (4.67, 4.37, 0.31, 0.59, (-0.48, 1.38))}
    for key, src in (("det", "AP1"), ("jev", "AP2B")):
        s, want = V["systems"][key], shown[key]
        assert (p2(s["with"]["cer"]), p2(s["without"]["cer"]), p2(s["value"]["cer_difference"]), round(s["value"]["p"], 2)) == want[:4]
        assert tuple(p2(x) for x in s["value"]["ci95"]) == want[4] and s["value"]["ci95"][0] < 0 < s["value"]["ci95"][1]
        assert abs(s["value"]["cer_difference"] - r["systems"][src]["incremental"]["net_cer_difference"]) < 5e-7
    g = V["gap"]
    assert (p2(g["total"]["cer_difference"]), p2(g["mix"]["cer_difference"]), p2(g["signals"]["cer_difference"])) == (1.01, 0.59, 0.42)
    assert {k: p2(v) for k, v in g["parts"].items()} == {"stock": 1.39, "bond": -0.79, "jev": 0.31, "det": 0.11}
    assert g["rounded_parts_sum"] == 1.02 and g["rounded_total"] == 1.01 and g["full_precision_residual"] == 0.0   # flagged on the tab
    im = V["influential_month"]
    assert im["decision_month"] == "2020-02" and (p2(im["value_with"]), p2(im["value_without"])) == (0.31, -0.18) and im["only_month_that_flips_the_sign"]
    assert (round(A["corr_monthly_net"], 3), round(A["corr_own_mixes"], 3)) == (0.971, 0.983)
    sva = (ROOT / "native_backtest/docs/SIGNAL_VALUE_ADDED_2026-10-29.md").read_text()
    for t in ("−0.11 pts", "+0.31 pts", "−0.18 pts", "+0.59 pts", "+0.42 pts", "+1.39 pts", "−0.79 pts", "+1.01 pts",
              "−0.31 pts to +0.03 pts", "−0.48 pts to +1.38 pts", "3.67%", "3.77%", "4.67%", "4.37%"):
        assert t in sva, t
    audit = (ROOT / "native_backtest/docs/PORTFOLIO_INTEGRITY_AUDIT_2026-10-29.md").read_text()
    assert "0.9712" in audit and "0.9826" in audit


def test_signal_value_tab_series_come_from_the_analysis():
    """The tab's charts use the development months only, and its with/without growth curves reproduce the analysis's
    own monthly returns (no hand-made series)."""
    import pandas as pd
    V = D["signal_value"]
    mon = pd.read_csv(ROOT / "native_backtest/out/signal_value/monthly_v1.csv", dtype={"decision_month": str})
    assert D["dev"]["months"] == mon["decision_month"].tolist() and (D["dev"]["months"][0], D["dev"]["months"][-1], len(D["dev"]["months"])) == ("2019-03", "2022-12", 46)
    for key, src in (("det", "AP1"), ("jev", "AP2B")):
        s = V["systems"][key]
        with_w = (1 + mon[f"{src}_ON__net_total_return"]).cumprod().tolist()
        without_w = (1 + mon[f"{src}_OFF__net_total_return"]).cumprod().tolist()
        assert max(abs(a - b) for a, b in zip(D["dev"]["series"][key]["wealth"], with_w)) < 1e-6
        assert max(abs(a - b) for a, b in zip(D["dev"]["benchmarks"][s["no_signal"]]["wealth"], without_w)) < 1e-6
        assert len(s["active"]) == 46 and s["universe"] == list(s["no_signal_weights"])
    im = V["influential_month"]
    i = D["dev"]["months"].index(im["decision_month"])
    assert V["systems"]["jev"]["active"][i] == im["jev_active_return"] and abs(sum(V["systems"]["jev"]["active"]) - im["jev_active_sum_all_months"]) < 1e-5
    row = mon.iloc[i]
    assert (im["entry"], im["exit"]) == (row["entry_date"], row["exit_date"]) and abs(im["spy_return"] - row["asset_return_SPY"]) < 5e-5
    assert V["systems"]["det"]["no_signal_weights"] == {"SPY": 0.45, "IEF": 0.35, "LQD": 0.2} and V["systems"]["jev"]["no_signal_weights"] == {"SPY": 0.6, "TLT": 0.4}


def test_signal_value_is_a_separate_top_level_tab():
    html = (ROOT / "mvp/index.html").read_text()
    nav = re.findall(r'<a href="#([a-z-]+)" data-route="[a-z-]+">([^<]+)</a>', html)
    assert nav == [("overview", "Overview"), ("approaches", "Approaches"), ("experiments", "Experiments"),
                   ("signal-value", "Signal Value-Added"), ("methodology", "Methodology")]
    js = (ROOT / "mvp/assets/app.js").read_text()
    assert "view === 'signal-value') viewSignalValue()" in js and "function signalValuePanel" not in js    # not a section of Experiments
    assert [s["key"] for s in D["systems"]] == ["det", "jev", "rag"]                                      # the three approaches are unchanged
