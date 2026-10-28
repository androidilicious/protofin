#!/usr/bin/env python3
"""Build mvp/data/dashboard.json, the only data file the dashboard reads.

Research design: three primary approaches - the Deterministic Quantitative Model, the Agentic
Workflow (represented by JEV) and Agentic Causal RAG. The Agent Committee is a within-approach
variant of the Agentic Workflow and appears only in the experiments section.

Every number is recomputed here from the stored decision records through the shared evaluator
(native_backtest/framework) and cross-checked against native_backtest/out/development/
development_evaluation_report.json. Only development months (before the protected window) are
scored; the evaluator's lock refuses anything later. Causal RAG has no results until paid
inference is approved, so its section carries status, research-inventory counts and a clearly
labelled engineering demo (mock responses) that is never scored.

Usage (repository root): python mvp/build_dashboard_data.py
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from native_backtest.framework import metrics as M  # noqa: E402
from native_backtest.framework.accounting import simulate_records, static_portfolio_records  # noqa: E402
from native_backtest.framework.lock import assert_scoring_allowed  # noqa: E402
from native_backtest.framework.market import load_config, load_market, months_between  # noqa: E402
from native_backtest.framework.records import read_jsonl  # noqa: E402

OUT = ROOT / "mvp" / "data" / "dashboard.json"
DEC = ROOT / "native_backtest" / "out" / "decisions"
REPORTS = ROOT / "native_backtest" / "out"
DEMO = ROOT / "mvp" / "data" / "ap3_engineering_demo.json"

RAG_STATUS = "Awaiting validation · results unavailable"

# Display order: the three primary approaches, then the within-approach variant.
SYSTEMS = {
    "det": {"src": "AP1", "role": "primary", "name": "Deterministic Quantitative Model", "short": "Deterministic", "color": "#4f8cff",
            "universe": ["SPY", "IEF", "LQD"], "neutral": {"SPY": 0.45, "IEF": 0.35, "LQD": 0.20},
            "horizon": "1-month forecasts", "assets_label": "US stocks, 7–10y Treasuries, corporate bonds",
            "tagline": "Turns eight economic-data surprises into return forecasts with a statistical model.",
            "steps": ["Measures how far 8 US data releases beat or missed forecasts",
                      "A shrinkage regression (Ridge) turns those surprises into 1-month return forecasts",
                      "Black–Litterman blends the forecasts with a 45/35/20 starting mix"],
            "signals": ["Nonfarm payrolls", "Retail sales", "Industrial production", "ISM manufacturing",
                        "CPI", "Core CPI", "PPI", "Average hourly earnings"],
            "model": "Ridge regression, refit every month on past data only"},
    "jev": {"src": "AP2B", "role": "primary", "name": "Agentic Workflow — JEV", "short": "Agentic Workflow (JEV)", "color": "#2dd4bf",
            "universe": ["SPY", "TLT"], "neutral": {"SPY": 0.60, "TLT": 0.40},
            "horizon": "12-month question, rebalanced monthly", "assets_label": "US stocks, 20+ year Treasuries",
            "tagline": "JEV, an AI decision model, answers whether stocks will beat bonds over 12 months, and its answer tilts the portfolio.",
            "steps": ["JEV reads a snapshot of recent market conditions",
                      "It gives the chance that stocks beat bonds over 12 months, plus a five-way tilt",
                      "The tilt, scaled by JEV's confidence, moves a 60/40 portfolio within 40–80% stocks"],
            "signals": ["Recent returns and volatility", "Stock–bond correlation and drawdown", "Rate levels and a 10-year rate shock",
                        "Term spread", "Policy and geopolitical uncertainty indexes", "Cash yield"],
            "model": "JEV decision model (saved answers; version not recorded)"},
    "rag": {"src": "AP3", "role": "primary", "name": "Agentic Causal RAG", "short": "Causal RAG", "color": "#b79cff",
            "universe": ["SPY", "IEF", "LQD"], "neutral": {"SPY": 0.45, "IEF": 0.35, "LQD": 0.20},
            "horizon": "1-month forecasts", "assets_label": "US stocks, 7–10y Treasuries, corporate bonds",
            "tagline": "Agents propose cause-and-effect hypotheses from economic research and test them against dated evidence.",
            "steps": ["A research knowledge graph suggests how this month's events could move markets",
                      "A Hypothesis Agent proposes testable hypotheses; a Testing Agent checks them against dated documents and market data",
                      "A calibration model turns tested hypotheses into forecasts; Black–Litterman sets the weights"],
            "signals": ["The same 8 data surprises", "Research knowledge graph (papers dated before each year)",
                        "Fed and official documents published before each decision", "Market-reaction data used as tests"],
            "model": "Llama 3.1 70B Instruct (chosen; runs once approved)", "status_label": RAG_STATUS},
    "com": {"src": "AP2A", "role": "variant", "name": "Agentic Workflow — Agent Committee", "short": "Agent Committee", "color": "#f5a524",
            "universe": ["SPY", "TLT"], "neutral": {"SPY": 0.60, "TLT": 0.40},
            "horizon": "12-month views, rebalanced monthly", "assets_label": "US stocks, 20+ year Treasuries",
            "tagline": "A within-approach variant: three AI agents debate the market, and a chief investment officer sets the view.",
            "steps": ["An Economist and a Risk Manager each read the same market snapshot as JEV",
                      "A CIO agent weighs both and states 12-month return views with a confidence level",
                      "Black–Litterman tilts a 60/40 portfolio toward the views, more when confidence is high"],
            "signals": ["Same market snapshot as JEV"],
            "model": "GPT-4o (saved runs, repeatable settings)"},
}
PRIMARY = [k for k, v in SYSTEMS.items() if v["role"] == "primary"]
ASSET_NAMES = {"SPY": "US stocks (SPY)", "IEF": "7–10y Treasuries (IEF)", "LQD": "Corporate bonds (LQD)", "TLT": "20+y Treasuries (TLT)"}
ASSET_PLAIN = {"SPY": "stocks", "IEF": "Treasuries", "LQD": "corporate bonds", "TLT": "long Treasuries"}
KEY_OF = {v["src"]: k for k, v in SYSTEMS.items()}


def mix_label(neutral: dict) -> str:
    return " · ".join(f"{int(round(w * 100))}% {ASSET_PLAIN[a]}" for a, w in neutral.items())


def _r(x, n=6):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(float(x), n)


def wealth(sim: pd.DataFrame, col: str = "net_total_return") -> list:
    return [_r(v) for v in np.cumprod(1.0 + sim[col].to_numpy(float))]


def metric_block(sim: pd.DataFrame) -> dict:
    m = M.metrics(sim)
    return {"months": int(m["n_months"]), "ann_excess_return": _r(m["net_annualized_excess_return"]),
            "volatility": _r(m["annualized_volatility"]), "sharpe": _r(m["net_sharpe"], 4), "cer": _r(m["cer_delta_2_5"]),
            "max_drawdown": _r(m["max_drawdown"]), "turnover": _r(m["annualized_one_way_turnover"], 4),
            "cumulative_return": _r(float(np.prod(1 + sim["net_total_return"].to_numpy(float)) - 1))}


def contrast_block(c: dict) -> dict:
    return {"cer_difference": _r(c["cer_difference"]), "ci95": [_r(v) for v in c["ci95"]], "p": _r(c["p_two_sided_bootstrap"], 4)}


def main() -> int:
    cfg = load_config()
    mk = load_market(cfg)
    prot = cfg["windows"]["protected"][0]
    cost = cfg["costs"]["cost_per_dollar_traded"]
    dev = months_between(*cfg["windows"]["development"])
    assert_scoring_allowed(dev, protected_start=prot)
    report = json.loads((REPORTS / "development" / "development_evaluation_report.json").read_text())
    rows = {x["system"]: x for x in report["common_evaluation_matched_dev"]}

    records = {k: read_jsonl(DEC / f"{v['src']}.jsonl") for k, v in SYSTEMS.items() if (DEC / f"{v['src']}.jsonl").exists()}
    out = {"generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "phase": "development",
           "windows": {"training": [cfg["windows"]["research_timeline_start"], "2019-02"],
                       "development": cfg["windows"]["development"],
                       "historical_test": cfg["windows"]["protected"], "historical_test_status": "sealed",
                       "prospective": "starts after the freeze"},
           "assets": ASSET_NAMES, "primary": PRIMARY, "systems": [], "variants": [],
           "dev": {"months": [str(m) for m in dev], "series": {}, "benchmarks": {}}}

    sims, neutral_sims = {}, {}
    for key, s in SYSTEMS.items():
        sysd = {k: v for k, v in s.items() if k != "src"}
        sysd["key"] = key
        sysd["has_results"] = key in records
        (out["systems"] if s["role"] == "primary" else out["variants"]).append(sysd)
        recs = records.get(key)
        if not recs:
            continue
        by = {r.decision_month: r for r in recs}
        dev_recs = [by[str(m)] for m in dev]
        sim = simulate_records(dev_recs, mk, dev, cost_per_dollar=cost)
        sims[key] = sim
        mb = metric_block(sim)
        rep = rows[s["src"]]
        assert abs(rep["absolute"]["cer_delta_2_5"] - mb["cer"]) < 1e-6, f"{key}: CER differs from the development report"
        nkey = "/".join(f"{a}{int(round(w * 100))}" for a, w in s["neutral"].items())
        if nkey not in neutral_sims:
            nsim = simulate_records(static_portfolio_records(f"N_{nkey}", s["neutral"], dev_recs), mk, dev, cost_per_dollar=cost)
            neutral_sims[nkey] = nsim
            out["dev"]["benchmarks"][nkey] = {"label": mix_label(s["neutral"]), "wealth": wealth(nsim), "metrics": metric_block(nsim)}
        vs = M.paired_cer_contrast(sim, neutral_sims[nkey])
        assert abs(vs["cer_difference"] - rep["vs_own_neutral"]["cer_difference"]) < 1e-9
        series = {"wealth": wealth(sim), "monthly_net_return": [_r(v) for v in sim["net_total_return"]],
                  "weights": {a: [_r(v, 4) for v in sim[f"w_{a}"]] for a in s["universe"]},
                  "metrics": mb, "neutral": nkey, "vs_neutral": contrast_block(vs)}
        fc = []
        for r in dev_recs:
            v = (r.forecast or {}).get("values", {})
            if key == "det":
                fc.append({a: _r(v.get(a), 5) for a in s["universe"]})
            elif key == "com":
                fc.append({"SPY": v.get("SPY"), "TLT": v.get("TLT"), "confidence": (r.confidence or {}).get("applied"),
                           "regime": (r.confidence or {}).get("regime")})
            elif key == "jev":
                fc.append({"p": _r(v.get("p"), 3), "tilt": v.get("choice"), "confidence": _r((r.confidence or {}).get("applied"), 3)})
        series["forecasts"] = fc
        if key == "com":
            nd = dev_recs[-1].native_detail or {}
            series["example"] = {"month": dev_recs[-1].decision_month,
                                 "economist": {"text": (nd.get("economist") or {}).get("text")},
                                 "risk_manager": {"text": (nd.get("risk") or {}).get("text")},
                                 "cio_rationale": nd.get("cio")}
        out["dev"]["series"][key] = series

    # Primary contrasts (one family of three at the freeze) and the within-approach contrast,
    # recomputed and checked against the development report.
    prim_rep = report["primary_contrasts_matched_dev"]
    primary = []
    for pair in prim_rep["family"]:
        x, y = (KEY_OF[p] for p in pair.split("-"))
        item = {"a": x, "b": y, "computed": pair in prim_rep["computed"]}
        if item["computed"]:
            c = M.paired_cer_contrast(sims[x], sims[y])
            assert abs(c["cer_difference"] - prim_rep["computed"][pair]["cer_difference"]) < 1e-12
            item.update(contrast_block(c))
            item["p_bound_full_family"] = _r(prim_rep["computed"][pair]["bonferroni_bound_full_family"], 4)
            # significant if even the full-family bound is below 5%; not significant if the raw p is not;
            # otherwise undecided until the family is complete
            item["significant"] = True if item["p_bound_full_family"] < 0.05 else (False if item["p"] >= 0.05 else None)
        primary.append(item)
    out["dev"]["primary_contrasts"] = {"family_size": prim_rep["family_size_at_freeze"], "items": primary}
    within = []
    for pair, c0 in report["within_approach_contrasts_matched_dev"]["computed"].items():
        x, y = (KEY_OF[p] for p in pair.split("-"))
        c = M.paired_cer_contrast(sims[x], sims[y])
        assert abs(c["cer_difference"] - c0["cer_difference"]) < 1e-12
        within.append({"a": x, "b": y, **contrast_block(c), "significant": c["p_two_sided_bootstrap"] < 0.05})
    out["dev"]["within_contrasts"] = within

    # Native reproduction and the native -> common execution steps
    ap1 = json.loads((REPORTS / "ap1" / "ap1_native_reproduction_report.json").read_text())
    ap2 = json.loads((REPORTS / "ap2" / "ap2_native_reproduction_report.json").read_text())
    out["reproduction"] = {
        "det": {"status": "reproduced" if ap1["stage2_reproduction_check"] == "MATCH" else "differs",
                "checks": [f"Development run matches the saved results ({ap1['n_differences']} differences)",
                           "Output files byte-identical to the committed run"]},
        "com": {"status": "reproduced" if ap2["all_pass"] else "differs",
                "checks": ["All 272 saved committee decisions rebuilt from the cached GPT-4o replies",
                           "Native browser engine and native Python allocator agree on every weight",
                           "Native month-by-month accounting reproduced exactly before 2023"]},
        "jev": {"status": "replayed" if ap2["all_pass"] else "differs",
                "checks": ["All 272 saved JEV decisions reproduced exactly from the saved answers",
                           "Native accounting reproduced exactly before 2023",
                           "Can't be re-run: the model version, prompt and recording tool were not saved"]},
        "rag": {"status": "not run", "checks": ["No results until the model run is approved and validated"]}}
    steps = {}
    labels = ["As originally scored", "Verified price data", "Trade next trading day", "Shared trading costs", "Shared cash rate"]
    for key, src in (("com", "AP2A"), ("jev", "AP2B")):
        rr = report["ap2_execution_attribution"][src]["matched_2019-03_to_2022-12"]
        steps[key] = [{"step": labels[i], "cer": _r(r["cer_delta_2_5"]), "ann_excess_return": _r(r["net_annualized_excess_return"]),
                       "sharpe": _r(r["net_sharpe"], 4), "max_drawdown": _r(r["max_drawdown"])} for i, r in enumerate(rr)]
    out["native_vs_common"] = steps

    # Experiments: within the Agentic Workflow, and secondary experiments (none run yet)
    out["experiments"] = {
        "within": [
            {"key": "com", "name": "Committee only", "status": "implemented",
             "detail": "Three GPT-4o agents (Economist, Risk Manager, CIO) set 12-month views; saved native runs replayed exactly."},
            {"key": "jev", "name": "JEV only", "status": "implemented",
             "detail": "JEV's saved answers replayed exactly. This is the primary Agentic Workflow system."},
            {"key": None, "name": "Committee + JEV", "status": "proposed",
             "detail": "Combine the Committee's views with JEV's answer. The combination rule must be pre-registered; nothing is built or run."}],
        "secondary": [
            {"name": "Signal ablations", "status": "proposed",
             "detail": "Remove one group of inputs at a time to see which signals matter."},
            {"name": "Market-regime experiments", "status": "proposed",
             "detail": "Compare behaviour in calm and stressed markets, with regimes defined before scoring."},
            {"name": "Standard RAG vs Causal RAG", "status": "proposed",
             "detail": "Replace graph-guided retrieval with plain similarity search. Needs genuine Causal RAG results first."}]}

    # Causal RAG: status, research-inventory counts, limits, engineering demo
    man = json.loads((REPORTS / "ap3" / "ap3_library_manifest_v1.json").read_text())
    limits = json.loads((ROOT / "native_backtest" / "ap3" / "limits_v1.json").read_text())
    concepts = json.loads((ROOT / "native_backtest" / "ap3" / "concepts_v1.json").read_text())
    out["ap3"] = {
        "status": "awaiting_validation", "status_label": RAG_STATUS,
        "graph": [{"decision_year": r["decision_year"], "papers": r["papers_kept"], "claims": r["claims_kept"],
                   "links": r["edges"], "pathways": r["n_paths"], "pathways_by_channel": r["paths_by_channel"]} for r in man["libraries"]],
        "graph_rebuild_identical": man["determinism_check"]["identical"],
        "triggers": [v["label"] for v in concepts["triggers"].values()],
        "assets": {a: v["label"] for a, v in concepts["assets"].items()},
        "limits": {"hypotheses_per_month": limits["max_hypotheses_per_month"], "testing_runs": limits["testing_agent"]["runs"],
                   "evidence_per_side": limits["testing_agent"]["chunks_supporting"], "graph_tool_calls": limits["hypothesis_agent"]["max_tool_calls"]},
        "demo": json.loads(DEMO.read_text()) if DEMO.exists() else None}

    n_dev = len(dev)
    sig_vs = [SYSTEMS[k]["short"] for k in PRIMARY if k in out["dev"]["series"] and out["dev"]["series"][k]["vs_neutral"]["p"] < 0.05]
    sig_pw = [f"{SYSTEMS[i['a']]['short']} vs {SYSTEMS[i['b']]['short']}" for i in primary if i["computed"] and i["p"] < 0.05]
    span = f"{dev[0].year}–{dev[-1].year}"
    if not sig_vs and not sig_pw:
        headline = (f"Development diagnostics, {span}: neither the Deterministic model nor the Agentic Workflow (JEV) beat its own "
                    "benchmark or the other by a statistically significant margin. Causal RAG is awaiting validation. "
                    "Protected historical results (2023–2026) are sealed.")
    else:
        headline = (f"Development diagnostics, {span}: statistically significant for " + ", ".join(sig_vs + sig_pw)
                    + ". Causal RAG is awaiting validation. Protected historical results (2023–2026) are sealed.")
    out["notes"] = {
        "headline": headline,
        "can": ["Each approach was run with its own original code, which reproduced its authors' saved results before any comparison.",
                f"The approaches with results are scored on the same {n_dev} development months, with the same trading costs and cash rate.",
                "How each approach behaved: its returns, risk, worst falls and how its holdings moved."],
        "cannot": ["Which approach is better. Development months are where the approaches were built and checked, so these are diagnostics, not protected historical results.",
                   f"Small differences. With {n_dev} months, only large gaps could be told apart from chance.",
                   "A controlled comparison. The approaches hold different assets and use different horizons and information.",
                   "Anything about Causal RAG yet. Its results are unavailable until its model run is approved and validated."]}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size/1024:.0f} KB) sha256 {hashlib.sha256(OUT.read_bytes()).hexdigest()[:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
