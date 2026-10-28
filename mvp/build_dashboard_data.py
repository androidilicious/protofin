#!/usr/bin/env python3
"""Build mvp/data/dashboard.json, the only data file the dashboard reads.

Every number is recomputed here from the stored decision records through the shared evaluator
(native_backtest/framework), then cross-checked against native_backtest/out/development/
development_evaluation_report.json. Only development months (before the protected window) are
scored; the evaluator's lock refuses anything later. AP3 has no results until paid inference is
approved, so its section carries status, knowledge-graph coverage and a clearly labelled
engineering demo (mock responses) that is never scored.

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

SYSTEMS = {
    "det": {"src": "AP1", "name": "Deterministic Quantitative Model", "short": "Deterministic", "color": "#4f8cff",
            "universe": ["SPY", "IEF", "LQD"], "neutral": {"SPY": 0.45, "IEF": 0.35, "LQD": 0.20},
            "horizon": "1-month forecasts", "assets_label": "US stocks, 7–10y Treasuries, corporate bonds",
            "tagline": "Turns eight economic-data surprises into return forecasts with a statistical model.",
            "steps": ["Measures how far 8 US data releases beat or missed forecasts",
                      "A shrinkage regression (Ridge) turns those surprises into 1-month return forecasts",
                      "Black–Litterman blends the forecasts with a 45/35/20 starting mix"],
            "signals": ["Nonfarm payrolls", "Retail sales", "Industrial production", "ISM manufacturing",
                        "CPI", "Core CPI", "PPI", "Average hourly earnings"],
            "model": "Ridge regression, refit every month on past data only"},
    "com": {"src": "AP2A", "name": "Agentic Workflow — Agent Committee", "short": "Agent Committee", "color": "#f5a524",
            "universe": ["SPY", "TLT"], "neutral": {"SPY": 0.60, "TLT": 0.40},
            "horizon": "12-month views, rebalanced monthly", "assets_label": "US stocks, 20+ year Treasuries",
            "tagline": "Three AI agents debate the market, and a chief investment officer sets the view.",
            "steps": ["An Economist and a Risk Manager each read the same market snapshot",
                      "A CIO agent weighs both and states 12-month return views with a confidence level",
                      "Black–Litterman tilts a 60/40 portfolio toward the views, more when confidence is high"],
            "signals": ["Recent returns and volatility", "Stock–bond correlation and drawdown", "Rate levels and a 10-year rate shock",
                        "Term spread", "Policy and geopolitical uncertainty indexes", "Cash yield"],
            "model": "GPT-4o (saved runs, repeatable settings)"},
    "jev": {"src": "AP2B", "name": "Agentic Workflow — JEV", "short": "JEV", "color": "#2dd4bf",
            "universe": ["SPY", "TLT"], "neutral": {"SPY": 0.60, "TLT": 0.40},
            "horizon": "12-month question, rebalanced monthly", "assets_label": "US stocks, 20+ year Treasuries",
            "tagline": "JEV, an AI decision model, answers whether stocks will beat bonds over 12 months, and its answer tilts the portfolio.",
            "steps": ["JEV sees the same market snapshot as the Committee",
                      "It gives the probability that stocks beat bonds over 12 months, plus a five-way tilt",
                      "The tilt, scaled by JEV's confidence, moves a 60/40 portfolio within 40–80% stocks"],
            "signals": ["Same market snapshot as the Agent Committee"],
            "model": "JEV decision model (saved answers; version not recorded)"},
    "rag": {"src": "AP3", "name": "Agentic Causal RAG", "short": "Causal RAG", "color": "#b79cff",
            "universe": ["SPY", "IEF", "LQD"], "neutral": {"SPY": 0.45, "IEF": 0.35, "LQD": 0.20},
            "horizon": "1-month forecasts", "assets_label": "US stocks, 7–10y Treasuries, corporate bonds",
            "tagline": "Agents propose cause-and-effect hypotheses from economic research and test them against dated evidence.",
            "steps": ["A research knowledge graph suggests how this month's events could move markets",
                      "A Hypothesis Agent proposes testable hypotheses; a Testing Agent checks them against dated documents and market data",
                      "A calibration model turns tested hypotheses into forecasts; Black–Litterman sets the weights"],
            "signals": ["The same 8 data surprises", "Research knowledge graph (papers dated before each year)",
                        "Fed and official documents published before each decision", "Market-reaction data used as tests"],
            "model": "Llama 3.1 70B Instruct (chosen; runs once approved)"},
}
ASSET_NAMES = {"SPY": "US stocks (SPY)", "IEF": "7–10y Treasuries (IEF)", "LQD": "Corporate bonds (LQD)", "TLT": "20+y Treasuries (TLT)"}
ASSET_PLAIN = {"SPY": "stocks", "IEF": "Treasuries", "LQD": "corporate bonds", "TLT": "long Treasuries"}


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


def main() -> int:
    cfg = load_config()
    mk = load_market(cfg)
    prot = cfg["windows"]["protected"][0]
    cost = cfg["costs"]["cost_per_dollar_traded"]
    dev = months_between(*cfg["windows"]["development"])
    ext = months_between("2011-01", "2022-12")
    assert_scoring_allowed(dev + ext, protected_start=prot)
    report = json.loads((REPORTS / "development" / "development_evaluation_report.json").read_text())

    records = {k: read_jsonl(DEC / f"{v['src']}.jsonl") for k, v in SYSTEMS.items() if (DEC / f"{v['src']}.jsonl").exists()}
    out = {"generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "phase": "development",
           "windows": {"training_start": "2015-02", "development": cfg["windows"]["development"],
                       "historical_test": cfg["windows"]["protected"], "historical_test_status": "sealed",
                       "prospective": "starts after the freeze", "extended_agentic_history": ["2011-01", "2022-12"]},
           "assets": ASSET_NAMES, "systems": [], "dev": {"months": [str(m) for m in dev], "series": {}, "benchmarks": {}},
           "extended": {"months": [str(m) for m in ext], "series": {}, "benchmarks": {}}}

    neutral_done = {}
    for key, s in SYSTEMS.items():
        sysd = {k: v for k, v in s.items() if k not in ("src",)}
        sysd["key"] = key
        sysd["has_results"] = key in records
        recs = records.get(key)
        if recs:
            by = {r.decision_month: r for r in recs}
            dev_recs = [by[str(m)] for m in dev]
            sim = simulate_records(dev_recs, mk, dev, cost_per_dollar=cost)
            mb = metric_block(sim)
            # cross-check against the committed development report
            rep = next(x for x in report["common_evaluation_matched_dev"] if x["system"] == s["src"])
            assert abs(rep["absolute"]["cer_delta_2_5"] - mb["cer"]) < 1e-6, f"{key}: CER differs from the development report"
            nkey = "/".join(f"{a}{int(round(w * 100))}" for a, w in s["neutral"].items())
            if nkey not in neutral_done:
                nsim = simulate_records(static_portfolio_records(f"N_{nkey}", s["neutral"], dev_recs), mk, dev, cost_per_dollar=cost)
                neutral_done[nkey] = nsim
                out["dev"]["benchmarks"][nkey] = {"label": mix_label(s["neutral"]),
                                                 "wealth": wealth(nsim), "metrics": metric_block(nsim)}
            vs = M.paired_cer_contrast(sim, neutral_done[nkey])
            out["dev"]["series"][key] = {
                "wealth": wealth(sim), "monthly_net_return": [_r(v) for v in sim["net_total_return"]],
                "weights": {a: [_r(v, 4) for v in sim[f"w_{a}"]] for a in s["universe"]},
                "metrics": mb, "neutral": nkey,
                "vs_neutral": {"cer_difference": _r(vs["cer_difference"]), "ci95": [_r(v) for v in vs["ci95"]], "p": _r(vs["p_two_sided_bootstrap"], 4)}}
            # forecasts and signals by month, human-readable
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
            out["dev"]["series"][key]["forecasts"] = fc
            if key == "com":
                last = dev_recs[-1]
                nd = last.native_detail or {}
                out["dev"]["series"][key]["example"] = {"month": last.decision_month,
                                                        "economist": {"text": (nd.get("economist") or {}).get("text")},
                                                        "risk_manager": {"text": (nd.get("risk") or {}).get("text")},
                                                        "cio_rationale": nd.get("cio")}
            if key in ("com", "jev"):
                ext_recs = [by[str(m)] for m in ext]
                esim = simulate_records(ext_recs, mk, ext, cost_per_dollar=cost)
                out["extended"]["series"][key] = {"wealth": wealth(esim), "metrics": metric_block(esim),
                                                  "weights": {"SPY": [_r(v, 4) for v in esim["w_SPY"]]}}
                if "SPY60/TLT40" not in out["extended"]["benchmarks"]:
                    nsim = simulate_records(static_portfolio_records("N", s["neutral"], ext_recs), mk, ext, cost_per_dollar=cost)
                    out["extended"]["benchmarks"]["SPY60/TLT40"] = {"label": mix_label(s["neutral"]), "wealth": wealth(nsim), "metrics": metric_block(nsim)}
        out["systems"].append(sysd)

    # pairwise contrasts among systems with results (development, descriptive)
    keys = [k for k in SYSTEMS if k in out["dev"]["series"]]
    pw = {}
    sims = {}
    for k in keys:
        by = {r.decision_month: r for r in records[k]}
        sims[k] = simulate_records([by[str(m)] for m in dev], mk, dev, cost_per_dollar=cost)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            c = M.paired_cer_contrast(sims[a], sims[b])
            pw[f"{a}|{b}"] = {"cer_difference": _r(c["cer_difference"]), "ci95": [_r(v) for v in c["ci95"]], "p": _r(c["p_two_sided_bootstrap"], 4)}
    holm = M.holm({k: v["p"] for k, v in pw.items()})
    for k in pw:
        pw[k]["p_holm"] = _r(holm[k]["holm_adjusted_p"], 4)
        pw[k]["significant"] = holm[k]["reject_at_alpha"]
    out["dev"]["pairwise"] = pw

    # native reproduction and the native -> common execution steps
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
        "rag": {"status": "not run", "checks": ["No results until the model run is approved"]}}
    steps = {}
    for key, src in (("com", "AP2A"), ("jev", "AP2B")):
        rows = report["ap2_execution_attribution"][src]["matched_2019-03_to_2022-12"]
        labels = ["As originally scored", "Verified price data", "Trade next trading day", "Shared trading costs", "Shared cash rate"]
        steps[key] = [{"step": labels[i], "cer": _r(r["cer_delta_2_5"]), "ann_excess_return": _r(r["net_annualized_excess_return"]),
                       "sharpe": _r(r["net_sharpe"], 4), "max_drawdown": _r(r["max_drawdown"])} for i, r in enumerate(rows)]
    out["native_vs_common"] = steps

    # AP3: status, knowledge-graph coverage, limits, engineering demo
    man = json.loads((REPORTS / "ap3" / "ap3_library_manifest_v1.json").read_text())
    limits = json.loads((ROOT / "native_backtest" / "ap3" / "limits_v1.json").read_text())
    concepts = json.loads((ROOT / "native_backtest" / "ap3" / "concepts_v1.json").read_text())
    out["ap3"] = {
        "status": "awaiting_model_approval",
        "graph": [{"decision_year": r["decision_year"], "papers": r["papers_kept"], "claims": r["claims_kept"],
                   "links": r["edges"], "pathways": r["n_paths"], "pathways_by_channel": r["paths_by_channel"]} for r in man["libraries"]],
        "graph_rebuild_identical": man["determinism_check"]["identical"],
        "triggers": [v["label"] for v in concepts["triggers"].values()],
        "assets": {a: v["label"] for a, v in concepts["assets"].items()},
        "limits": {"hypotheses_per_month": limits["max_hypotheses_per_month"], "testing_runs": limits["testing_agent"]["runs"],
                   "evidence_per_side": limits["testing_agent"]["chunks_supporting"], "graph_tool_calls": limits["hypothesis_agent"]["max_tool_calls"]},
        "demo": json.loads(DEMO.read_text()) if DEMO.exists() else None}

    sig_vs = [SYSTEMS[k]["short"] for k, v in out["dev"]["series"].items() if v["vs_neutral"]["p"] is not None and v["vs_neutral"]["p"] < 0.05]
    sig_pw = [" vs ".join(SYSTEMS[x]["short"] for x in k.split("|")) for k, v in pw.items() if v["significant"]]
    n_dev = len(dev)
    headline = ("2019–2022: no approach beat its own benchmark or the others by a statistically significant margin. "
                "The real test (2023–2026) is still sealed." if not sig_vs and not sig_pw else
                "2019–2022: statistically significant differences for " + ", ".join(sig_vs + sig_pw) + ". The real test (2023–2026) is still sealed.")
    out["notes"] = {
        "headline": headline,
        "can": ["Each approach was run with its own original code, which reproduced its authors' saved results before any comparison.",
                f"All approaches are scored on the same {n_dev} months, with the same trading costs and cash rate.",
                "How each approach behaved: its returns, risk, worst falls and how its holdings moved."],
        "cannot": ["Which approach is better. Development months are where the approaches were built and checked, so these results are diagnostics, not a test.",
                   f"Small differences. With {n_dev} months, only large gaps could be told apart from chance.",
                   "A controlled comparison. The approaches hold different assets and use different horizons and information.",
                   "Whether AI hindsight helped. The AI models may have seen 2019–2022 market history during training."]}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size/1024:.0f} KB) sha256 {hashlib.sha256(OUT.read_bytes()).hexdigest()[:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
