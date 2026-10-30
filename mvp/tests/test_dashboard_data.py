"""Data contract for mvp/data/dashboard.json (the only file the dashboard reads)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
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
    assert versions["Causal RAG — With Historical Documents"] == "blocked"
    # Reduced Evidence has now run; it may be "exploratory", and must never be "tested"
    assert versions["Causal RAG — Reduced Evidence"] in ("awaiting_validation", "exploratory")
    assert rag["variants"][2]["name"] == "Policy-path proxy variant" and rag["variants"][2]["status"] == "awaiting_validation"
    assert all(v["status"] == "planned" for v in rag["variants"][3:])
    # nothing untested links to results: the two Causal RAG versions link only to the explanation page, which shows none
    assert all(v["link"] in (None, "rag") for g in shown for v in g["variants"] if v["status"] not in ("tested", "exploratory"))
    # no Causal RAG experiment may be called tested, and results are attached only to experiments that ran
    assert not any(v["status"] == "tested" for v in rag["variants"]) and rag["base"]["status"] != "tested"
    assert all(v["status"] in ("tested", "exploratory") for g in shown for v in g["variants"] if "result" in v)
    assert sum("result" in v for g in shown for v in g["variants"]) == 5
    # an exploratory result must carry its designation so it can never read as a validated one
    for g in shown:
        for v in g["variants"]:
            if v["status"] == "exploratory":
                assert "result" in v and v["designation"] == EXPLORATORY_LABEL
                assert "gates still failed" in v["result"]["headline"] or "gates" in v["result"]["caution"]
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


# Provenance is deliberately technical: these blocks name the committed artifacts a number came from, which is
# the point of them. Everything else the dashboard puts in front of a reader stays free of internal system ids.
PROVENANCE = {"pipeline": ["sources"], "appendix": ["entries", "docs", "configs"], "export": ["contents"], "build": None}


def _display_only(d):
    out = {}
    for k, v in d.items():
        if k == "dev":
            continue
        if k in PROVENANCE:
            fields = PROVENANCE[k]
            if fields is None:
                continue
            v = {kk: vv for kk, vv in v.items() if kk not in fields}
        out[k] = v
    return out


def test_no_internal_labels_in_display_text():
    shown = json.dumps(_display_only(D), ensure_ascii=False)
    assert not re.search(r"\bAP[123]\b|AP2-?[AB]|engineering_mock|\.jsonl", shown)


def test_provenance_blocks_name_real_committed_files():
    """The exemption above is only safe if those blocks really are file paths that exist in the repository."""
    paths = set(sum(D["pipeline"]["sources"].values(), []))
    paths |= {d["path"] for d in D["appendix"]["docs"] + D["appendix"]["configs"]}
    assert paths, "provenance blocks must not be empty"
    for f in sorted(paths):
        assert (ROOT / f).exists(), f"{f} is named as a source but is not in the repository"
    # and the appendix 'where' pointers are data locations or file paths, never prose
    for e in D["appendix"]["entries"]:
        assert e["where"] and " " not in e["where"].replace(" / ", "/"), e["where"]


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


def test_the_information_architecture_is_the_nine_redesigned_sections():
    html = (ROOT / "mvp/index.html").read_text()
    nav = re.findall(r'<a href="#([a-z-]+)" data-route="[a-z-]+">([^<]+)</a>', html)
    assert nav == [("overview", "Overview"), ("replay", "Replay"), ("pipeline", "Pipeline"),
                   ("comparison", "Comparison"), ("signal-value", "Signal Value"), ("sensitivity", "Sensitivity"),
                   ("experiments", "Experiments"), ("causal-rag", "Causal RAG"), ("appendix", "Appendix")]
    js = (ROOT / "mvp/assets/app.js").read_text()
    for v in ("viewOverview", "viewReplay", "viewPipeline", "viewComparison", "viewSignalValue", "viewSensitivity",
              "viewExperiments", "viewCausalRag", "viewAppendix"):
        assert f"function {v}" in js, f"{v} is navigable but not defined"
    assert [s["key"] for s in D["systems"]] == ["det", "jev", "rag"]          # the three approaches are unchanged
    # the per-approach detail pages survive the redesign, reached from Comparison rather than a tab of their own
    assert "if (key) viewApproach(key);" in js and "function viewApproach" in js


def test_redesign_lost_no_section_of_the_previous_dashboard():
    """Every data block the old dashboard displayed is still reachable in the new one."""
    js = (ROOT / "mvp/assets/app.js").read_text()
    for fn in ("phaseStrip", "approachCard", "triangle", "compareTable", "passivePanel", "alikePanel",
               "flowDiagram", "signalsBlock", "limitations", "decompositionBars", "exploratoryPanel",
               "versionsPanel", "demoBlock", "sensitivitySections", "expResult", "methodologyBody"):
        assert f"function {fn}" in js and js.count(fn) > 1, f"{fn} is defined but no longer rendered"
    for key in ("windows", "systems", "variants", "dev", "reproduction", "native_vs_common", "experiments",
                "ap3", "notes", "audit", "signal_value", "sensitivity", "ap3_exploratory", "validation",
                "methodology", "flows", "pipeline", "appendix", "export", "build"):
        assert key in D, f"dashboard.json lost the {key} block"


def test_exploratory_causal_rag_block_is_honest_about_its_state():
    """The exploratory block must carry the failed gates, never claim validation, and show no curve it did not compute."""
    X = D["ap3_exploratory"]
    mode = json.loads((ROOT / "native_backtest/config/ap3_exploratory_mode_v1.json").read_text())
    assert X["label"] == mode["labelling"]["label"] == "EXPLORATORY — RELIABILITY GATES FAILED"
    assert X["identity"] == mode["baseline_identity"] and X["state"] in ("not_run", "partial", "complete_agents", "results")
    assert X["gates_failed"], "the block exists only because gates failed; they must be listed"
    assert set(X["gates_failed"]) <= {"G3a", "G3b"} and X["months_needed"] == 95
    if X["state"] != "results":
        assert X["results"] is None and "wealth" not in X        # no curve before the replay finishes
        assert X["months_done"] < 95
    else:
        assert len(X["wealth"]) == len(X["months"]) == len(D["dev"]["months"])
        assert X["coverage"]["months_scored"] is not None
    # the exploratory results never enter the primary series or the approach cards
    assert "rag" not in D["dev"]["series"] and [s["key"] for s in D["systems"]] == ["det", "jev", "rag"]
    assert D["ap3"]["status"] == "awaiting_validation"


def test_no_experiment_or_approach_is_marked_validated_by_the_exploratory_run():
    cfg = json.loads((ROOT / "native_backtest/config/framework_config_v1.json").read_text())
    st = {v["id"]: v["status"] for g in cfg["research_design"]["within_approach_experiments"]["groups"] for v in g["variants"]}
    # the exploratory run records that it ran, and never promotes it to a validated result
    assert st["AP3-RE"] in ("awaiting_validation", "exploratory") and st["AP3-RE"] != "tested"
    gates = json.loads((ROOT / "native_backtest/config/ap3_reliability_gates_v1.json").read_text())
    assert gates["G3b_testing_agent_fixtures"]["accuracy_min"] == 0.8 and gates["G3a_first_12_months"]["failed_months_max"] == 1


# ---------------------------------------------------------------- forecast-to-allocation sensitivity (transmission)
SENS = json.loads((ROOT / "native_backtest/out/sensitivity/forecast_to_allocation_sensitivity.json").read_text())
SENS_SRC = {"det": "AP1", "jev": "AP2B", "com": "AP2A"}
EXPLORATORY_LABEL = "EXPLORATORY \u2014 RELIABILITY GATES FAILED"


def test_transmission_section_numbers_come_from_the_experiment():
    """Every figure the transmission section shows is the experiment's own output, not a dashboard restatement."""
    S = D["sensitivity"]
    assert S["months"] == SENS["window"]["n_months"] == 46
    assert S["scenarios"] == ["0x", "0.5x", "1x", "2x"]
    assert S["preregistration"] == SENS["preregistration"]
    for k, src in SENS_SRC.items():
        a, got = SENS["approaches"][src], S["systems"][k]
        by, tr = a["performance"]["by_scenario"], a["transmission"]["per_scenario_vs_1x"]
        assert got["universe"] == a["universe"] and got["neutral_weights"] == a["native_neutral_weights"]
        assert got["entry_point"] == a["allocator"]["entry_point"]
        assert got["signal_variance_share"] == pytest.approx(
            SENS["cross_approach"]["per_approach_variance_split"][src]["signal_part_share_of_1x_variance"], abs=5e-7)
        for s in S["scenarios"]:
            g = got["by_scenario"][s]
            assert g["net_cer"] == pytest.approx(by[s]["net_cer"], abs=5e-7)
            assert g["vol"] == pytest.approx(by[s]["annualized_volatility"], abs=5e-7)
            assert g["turnover"] == pytest.approx(by[s]["annualized_one_way_turnover"], abs=5e-5)
            assert g["cost_bp"] == pytest.approx(by[s]["annualized_cost"] * 1e4, abs=5e-4)
            assert g["active_weight"] == pytest.approx(by[s]["mean_half_sum_abs_active"], abs=5e-6)
            assert g["binding_months"] == tr[s]["months_with_any_binding_bound"]
            if s != "1x":
                st = a["statistics"][f"net_cer_{s}_minus_1x"]
                assert g["vs_1x"]["cer_difference"] == pytest.approx(st["point"], abs=5e-7)
                assert g["vs_1x"]["ci95"] == pytest.approx(st["ci95"], abs=5e-7)
    cp = SENS["cross_approach"]["pairwise"]["AP1_vs_AP2B"]
    assert S["similarity"]["corr_1x"] == pytest.approx(cp["monthly_net_return_correlation_1x"], abs=5e-7)
    assert S["similarity"]["corr_0x"] == pytest.approx(cp["monthly_net_return_correlation_0x"], abs=5e-7)
    assert S["similarity"]["corr_signal_parts"] == pytest.approx(cp["monthly_signal_part_correlation"], abs=5e-7)


def test_transmission_section_is_rendered_as_its_own_section():
    js = (ROOT / "mvp/assets/app.js").read_text()
    css = (ROOT / "mvp/index.html").read_text()
    assert "${sensitivitySections()}" in js and "sensitivityCharts();" in js, "defined but never rendered"
    # in the redesign it is its own section, rendered by viewSensitivity and reachable from the nav
    assert "function viewSensitivity" in js and js.index("function viewSensitivity") < js.index("${sensitivitySections()}")
    assert re.search(r'data-route="sensitivity">Sensitivity<', css)
    for cls in ("fas-chain", "fas-where", "fas-funnel", "fas-keep", "fas-corr", "sva-read"):
        assert f".{cls} " in css, f"{cls} has no styling"


def test_transmission_claims_no_significance():
    S = D["sensitivity"]
    assert S["validation"]["any_scenario_statistically_clear"] is False
    for k in S["systems"]:
        for s in ("0x", "0.5x", "2x"):
            lo, hi = S["systems"][k]["by_scenario"][s]["vs_1x"]["ci95"]
            assert lo <= 0 <= hi, f"{k} {s} interval excludes zero; the copy says none does"
        assert S["systems"][k]["by_scenario"]["1x"]["vs_1x"] is None            # nothing is compared with itself
        assert S["systems"][k]["reproduces_1x"] is True                          # 1x reproduces the archived run
    assert S["validation"]["audit_failures"] == 0 and S["validation"]["audit_checks"] >= 300


def test_causal_rag_scenarios_if_computed_stay_exploratory():
    """Causal RAG may now have scenarios, but only ever as a labelled, never-validated diagnostic."""
    S = D["sensitivity"]
    assert S["ap3"]["designation"] == EXPLORATORY_LABEL
    assert S["ap3"]["months_required"] == 95
    if not S["ap3"].get("computed"):
        assert "rag" not in S["systems"] and S["ap3"]["status"].lower().startswith("pending")
        return
    assert "EXPLORATORY" in S["ap3"]["status"] and S["ap3"]["gates_failed"]
    assert "never scaled" in (S["ap3"]["categorical_note"] or "")
    rag = S["systems"]["rag"]
    assert rag["exploratory"] is True and rag["designation"] == S["ap3"]["designation"]
    assert rag["universe"] == ["SPY", "IEF", "LQD"] and rag["reproduces_1x"] is True
    assert rag["posterior_keeps"] is not None and rag["jev_stages"] is None


def test_transmission_keeps_each_approach_in_its_own_native_portfolio():
    S = D["sensitivity"]
    det, jev, com = (S["systems"][k] for k in ("det", "jev", "com"))
    assert det["universe"] == ["SPY", "IEF", "LQD"] and jev["universe"] == ["SPY", "TLT"]
    assert det["neutral_label"] != jev["neutral_label"]
    assert jev["neutral_label"] == com["neutral_label"]                          # same approach family
    assert "black-litterman" not in jev["allocator"].lower(), "JEV must not be routed through the AP1 allocator"
    # JEV's allocator is faithful and its cap never binds; the Deterministic signal dies in the posterior
    assert jev["posterior_keeps"] is None and jev["jev_stages"] is not None
    assert all(jev["by_scenario"][s]["binding_months"] == 0 for s in S["scenarios"])
    assert all(jev["by_scenario"][s]["attenuation"] in (None, 0.0) for s in S["scenarios"])
    assert det["posterior_keeps"] < 0.10 and det["jev_stages"] is None
    assert com["posterior_keeps"] > 0.30 and com["by_scenario"]["2x"]["binding_months"] >= 20


# ---------------------------------------------------------------- interactive pipeline
PIPE = D["pipeline"]


def test_pipeline_covers_every_development_month_with_real_values():
    assert PIPE["months"] == D["dev"]["months"], "the pipeline must cover exactly the development window"
    for k in ("det", "jev"):
        assert set(PIPE[k]) == set(D["dev"]["months"]), f"{k} is missing months"
    assert PIPE["default_month"] in PIPE["months"]


def test_pipeline_stage_values_match_their_archived_sources():
    """Spot-check the trace against the committed artifacts it was read from, not against itself."""
    tr = pd.read_csv(ROOT / "native_backtest/out/sensitivity/ap1_transmission_trace.csv")
    tr = tr[tr["scenario"] == "1x"].set_index("decision_month")
    pred = pd.read_csv(ROOT / "stage2/results/dev_rerun_v4_portfolio_2026-10-27/stage2_predictions.csv")
    pred = pred[pred["system"] == "A"]
    for m in ("2019-03", "2020-02", "2022-12"):
        v, t = PIPE["det"][m], tr.loc[m]
        for a in ("SPY", "IEF", "LQD"):
            assert v["prior"][a] == pytest.approx(t[f"pi_{a}"], abs=5e-7)
            assert v["posterior"][a] == pytest.approx(t[f"mu_bl_{a}"], abs=5e-7)
            assert v["weights"][a] == pytest.approx(t[f"w_{a}"], abs=5e-6)
            p = pred[(pred.decision_month == m) & (pred.asset == a)].iloc[0]
            assert v["forecast"][a] == pytest.approx(p["prediction_excess_return"], abs=5e-7)
            assert v["realized"][a] == pytest.approx(p["actual_excess_return"], abs=5e-7)
    jt = pd.read_csv(ROOT / "native_backtest/out/sensitivity/ap2b_transmission_trace.csv")
    jt = jt[jt["scenario"] == "1x"].set_index("decision_month")
    for m in ("2019-03", "2020-02", "2022-12"):
        v, t = PIPE["jev"][m], jt.loc[m]
        assert v["edge"] == pytest.approx(t["edge"], abs=5e-5)
        assert v["base_edge"] == pytest.approx(t["base_edge"], abs=5e-5)
        assert v["weights"]["SPY"] == pytest.approx(t["w_SPY"], abs=5e-6)
        # the native mechanism holds: edge = baseEdge + confidence x offset
        assert v["edge"] == pytest.approx(v["base_edge"] + v["weighted_offset"], abs=1e-3)
        assert v["weighted_offset"] == pytest.approx(v["confidence"] * v["offset_original"], abs=1e-3)


def test_pipeline_never_reads_the_future_or_invents_causal_rag():
    for k in ("det", "jev"):
        for m, v in PIPE[k].items():
            assert v["decision_date"][:7] <= m[:7] or v["decision_date"][:7] == m, (k, m)
            assert v["entry"] > v["decision_date"], "trading happens after the decision"
            assert v["exit"] > v["entry"] and v["exit"] < "2023-03", (k, m)
            # weights are stored rounded to 5 decimals for size, so fully invested within that rounding
            assert abs(sum(v["weights"].values()) - 1) < 5e-5, "weights are fully invested"
    # the Causal RAG lane is always marked, whether or not it has values
    assert "GATES FAILED" in PIPE["rag_status"]["designation"]
    assert [s["id"] for s in PIPE["stages"]["rag"]] == [s["id"] for s in PIPE["stages"]["det"]]
    assert "Hypothesis" in PIPE["stages"]["rag"][1]["name"]            # its own architecture
    if not PIPE["rag_status"]["available"]:
        assert "rag" not in PIPE, "a lane with no genuine output must carry no month values"
        return
    assert set(PIPE["rag"]) == set(D["dev"]["months"]), "every development month, or none"
    for m, v in PIPE["rag"].items():
        assert v["entry"] > v["decision_date"] and v["exit"] > v["entry"] and v["exit"] < "2023-03", m
        assert abs(sum(v["weights"].values()) - 1) < 5e-5, m
        for h in v["hypotheses"]:
            assert h["status"] in ("Supported", "Contradicted", "Insufficient", None), (m, h["status"])


def test_each_pipeline_keeps_its_native_architecture():
    det, jev = PIPE["stages"]["det"], PIPE["stages"]["jev"]
    assert "Black" in det[3]["what"] and "Black" not in jev[3]["what"], "JEV must not be routed through Black-Litterman"
    assert "capped tilt" in jev[3]["what"]
    assert set(PIPE["det"][PIPE["default_month"]]["weights"]) == {"SPY", "IEF", "LQD"}
    assert set(PIPE["jev"][PIPE["default_month"]]["weights"]) == {"SPY", "TLT"}


# ---------------------------------------------------------------- Download Content package
def test_export_declares_a_working_package_and_its_exclusions():
    X = D["export"]
    assert X["zip_name"] == "BNY_Capstone_Dashboard_Content.zip"
    paths = [c["path"] for c in X["contents"]]
    for need in ("README.txt", "MANIFEST.json", "report/Research_Report.html", "appendix/appendix.html",
                 "data/dashboard.json"):
        assert need in paths, f"the package must contain {need}"
    assert any(p.endswith(".csv") and "performance" in p for p in paths)
    assert any(p.endswith(".csv") and "sensitivity" in p for p in paths)
    assert len(X["excluded"]) >= 4 and any("2023" in e for e in X["excluded"]), "the sealed window must be disclosed"
    assert any("credential" in e.lower() or "token" in e.lower() for e in X["excluded"])
    assert X["report_format"] == "self-contained HTML" and X["report_format_note"]


def test_export_is_built_in_the_page_without_a_network_call():
    js = (ROOT / "mvp/assets/app.js").read_text()
    assert "function makeZip" in js and "0x04034b50" in js, "the ZIP is written in the page"
    assert "function downloadContent" in js and "id=\"dl\"" in (ROOT / "mvp/index.html").read_text()
    assert "Download Content" in (ROOT / "mvp/index.html").read_text()
    for forbidden in ("jszip", "cdn.", "fetch('http", "XMLHttpRequest"):
        assert forbidden not in js.lower().replace("cdn.jsdelivr", ""), f"the export must not depend on {forbidden}"


def test_build_provenance_is_recorded_for_the_manifest():
    B = D["build"]
    assert B["repository"] == "androidilicious/protofin" and B["branch"]
    assert re.fullmatch(r"[0-9a-f]{40}", B["git_commit_at_build"] or "")
    assert re.fullmatch(r"[0-9a-f]{64}", B["release_manifest_sha256"] or "")
    assert "schema" in B["dashboard_schema"] or "2.0" in B["dashboard_schema"]


# ---------------------------------------------------------------- historical backtest replay
def test_replay_is_a_navigable_primary_view_with_three_lanes():
    html = (ROOT / "mvp/index.html").read_text()
    js = (ROOT / "mvp/assets/app.js").read_text()
    nav = re.findall(r'<a href="#([a-z-]+)" data-route="[a-z-]+">([^<]+)</a>', html)
    assert ("replay", "Replay") in nav and nav[1] == ("replay", "Replay"), "Replay sits right after Overview"
    assert "function viewReplay" in js and "view === 'replay') viewReplay()" in js
    assert "const LANES = ['det', 'jev', 'rag']" in js, "all three approaches, always, in one view"
    assert "Historical Backtest Replay" in js and "Playback of recorded results" in js


def test_replay_controls_all_exist():
    js = (ROOT / "mvp/assets/app.js").read_text()
    for ctl in ("rp-play", "rp-restart", "rp-range", "rp-reduced", "data-rp=\"nm\"", "data-rp=\"pm\"",
                "data-rp=\"ns\"", "data-rp=\"ps\"", "data-sp=", "data-mode="):
        assert ctl in js, f"the replay is missing the {ctl} control"
    assert "Play Backtest" in js and "Pause" in js
    for sp in ("0.5", "1", "2", "4"):
        assert f"[{sp}, " in js or f", {sp}," in js or f"{sp}]" in js
    assert "function rpPlay" in js and "function rpPause" in js and "function rpTick" in js


def test_replay_runs_the_development_window_in_order():
    """The replay walks the committed development months, in order, and never past them."""
    assert PIPE["months"] == sorted(PIPE["months"]) == D["dev"]["months"]
    assert PIPE["months"][0] == D["windows"]["development"][0]
    assert PIPE["months"][-1] == D["windows"]["development"][1] < D["windows"]["historical_test"][0]
    assert len(PIPE["months"]) == 46
    # each replayed month has, for both lanes with data, the stage values the lanes display
    for k in ("det", "jev"):
        for m in PIPE["months"]:
            v = PIPE[k][m]
            for f in ("entry", "exit", "turnover", "cost", "net", "weights"):
                assert f in v, (k, m, f)


def test_replay_running_metrics_reproduce_the_committed_result():
    """Net CER to date must be the frozen definition on net EXCESS returns, landing on the committed value."""
    for k in ("det", "jev"):
        x = [PIPE[k][m]["net"] for m in PIPE["months"]]
        mean = sum(x) / len(x)
        var = sum((v - mean) ** 2 for v in x) / (len(x) - 1)
        assert 12 * (mean - 1.25 * var) == pytest.approx(D["dev"]["series"][k]["metrics"]["cer"], abs=5e-6)
        # and growth/drawdown run on the committed total-return wealth
        w = D["dev"]["series"][k]["wealth"]
        assert w[-1] - 1 == pytest.approx(D["dev"]["series"][k]["metrics"]["cumulative_return"], abs=5e-6)
    js = (ROOT / "mvp/assets/app.js").read_text()
    assert "rpExcess" in js and "net CER is defined on net EXCESS" in js, "the running CER must not use total returns"
    assert "to date</b>, not the full-sample result" in js, "running and full-sample figures must be distinguished"


def test_causal_rag_figures_are_marked_wherever_they_appear():
    js = (ROOT / "mvp/assets/app.js").read_text()
    assert "No genuine agent output exists for" in js, "the pending wording must survive for a future rerun"
    X = D["ap3_exploratory"]
    assert X["gates_failed"] and set(X["gates_failed"]) <= {"G3a", "G3b"}
    # Causal RAG must never join the validated series; its curve comes only from the labelled block
    assert "rag" not in D["dev"]["series"], "Causal RAG must not appear as a validated development series"
    assert "const rpSeries = k => { if (k !== 'rag') return S(k);" in js
    # the loud banner was replaced by one quiet marker; it must still appear wherever a Causal RAG number does
    assert "const xtag = () =>" in js and 'class="xmark"' in js
    assert js.count("xtag()") >= 8, "every Causal RAG figure needs its marker"
    assert "did not pass their pre-registered reliability checks" in js, "the marker must explain itself on hover"
    for site in ("rl-h", "cch", "pstage-h", "fas-where", "apx"):
        assert site in js
    if X["state"] == "results":
        assert X["wealth"] and len(X["wealth"]) == len(D["dev"]["months"])
        assert X["metrics"]["cer"] is not None
        assert X["coverage"]["months_scored"] == 46
        # with the banners gone, the Appendix carries the full reason, as a primary entry
        primary = [e for e in D["appendix"]["entries"] if e.get("primary")]
        assert any(e["cat"] == "causal-rag" and "exploratory" in e["title"].lower() for e in primary), \
            "the Appendix must state why every Causal RAG figure is marked"
        full = next(e for e in primary if e["cat"] == "causal-rag")
        for must in ("G3a", "G3b", "not validated evidence", "placebo"):
            assert must in full["what"], must


def test_replay_reflects_the_latest_committed_agent_run():
    """The lane must show the current run's gate values, not a superseded earlier run."""
    bundle = json.loads((ROOT / "native_backtest/out/ap3/qwen3_runs/summary.json").read_text())
    assert bundle["protocol"]["version"] == "1.1", "the imported bundle must be the protocol 1.1 run"
    g = D["ap3_exploratory"]["gates_failed"]
    assert g["G3b"]["accuracy"] == pytest.approx(bundle["gates"]["G3b"]["checks"]["accuracy"]["value"])
    assert g["G3a"]["schema_valid_call_rate"] == pytest.approx(
        bundle["gates"]["G3a"]["checks"]["schema_valid_call_rate"]["value"])
    assert bundle["gates"]["G3a"]["checks"]["failed_months"]["value"] == 0, "run 2 completed every sample month"


def test_replay_preserves_the_rest_of_the_dashboard():
    js = (ROOT / "mvp/assets/app.js").read_text()
    html = (ROOT / "mvp/index.html").read_text()
    routes = [r for r, _ in re.findall(r'<a href="#([a-z-]+)" data-route="([a-z-]+)">', html)]
    for keep in ("overview", "pipeline", "comparison", "signal-value", "sensitivity", "experiments",
                 "causal-rag", "appendix"):
        assert keep in routes, f"the redesign dropped {keep}"
    assert 'id="dl"' in html and "Download Content" in html and "function downloadContent" in js
    assert "function makeZip" in js
