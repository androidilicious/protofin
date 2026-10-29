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

from native_backtest.framework import benchmark as B  # noqa: E402
from native_backtest.framework import metrics as M  # noqa: E402
from native_backtest.framework.accounting import simulate_records, static_portfolio_records  # noqa: E402
from native_backtest.framework.lock import assert_scoring_allowed  # noqa: E402
from native_backtest.framework.market import load_config, load_market, months_between  # noqa: E402
from native_backtest.framework.records import read_jsonl  # noqa: E402

OUT = ROOT / "mvp" / "data" / "dashboard.json"
DEC = ROOT / "native_backtest" / "out" / "decisions"
REPORTS = ROOT / "native_backtest" / "out"
DEMO = ROOT / "mvp" / "data" / "ap3_engineering_demo.json"
AUDIT = ROOT / "native_backtest" / "out" / "audit" / "portfolio_integrity_v1.json"
AUDIT_REPORT = "native_backtest/docs/PORTFOLIO_INTEGRITY_AUDIT_2026-10-29.md"

RAG_STATUS = "Awaiting validation · results unavailable"

# Display order: the three primary approaches, then the within-approach variant.
SYSTEMS = {
    "det": {"src": "AP1", "role": "primary", "name": "Deterministic Quantitative Model", "short": "Deterministic", "color": "#4f8cff",
            "universe": ["SPY", "IEF", "LQD"], "neutral": {"SPY": 0.45, "IEF": 0.35, "LQD": 0.20},
            "horizon": "1-month forecasts", "assets_label": "US stocks, 7–10y Treasuries, corporate bonds",
            "tagline": "Turns eight economic-data surprises into return forecasts with a statistical model.",
            "summary": "A statistical model turns 8 economic-data surprises into 1-month forecasts.",
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
            "summary": "JEV, an AI decision model, makes a 12-month stocks-versus-bonds call that tilts a 60/40 portfolio.",
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
            "summary": "AI agents propose cause-and-effect hypotheses from research and test them on dated evidence.",
            "steps": ["A research knowledge graph suggests how this month's events could move markets",
                      "A Hypothesis Agent proposes testable hypotheses; a Testing Agent checks them against dated documents and market data",
                      "A calibration model turns tested hypotheses into forecasts; Black–Litterman sets the weights"],
            "signals": ["The same 8 data surprises", "Research knowledge graph (papers dated before each year)",
                        "Fed and official documents published before each decision", "Market-reaction data used as tests"],
            "model": "Qwen3 4B, free (stands in for Llama 3.1 70B)", "status_label": RAG_STATUS},
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

STATUS_ORDER = ("tested", "awaiting_validation", "planned", "blocked", "paused")
EXP_TEXT = {
    "AP1": ("Base model: 8 economic-data surprises", "det", "The Deterministic model as it runs in the primary comparison."),
    "AP1+B1..B5": ("Add one financial signal at a time", None,
                   "Credit spread, its 3-month change, yield-curve slope, a volatility premium, or 12-month momentum, each added on its own. "
                   "Built and run on development months, then put on hold by a team decision on 27 Oct 2026; its results are archived and not reported."),
    "AP1+B-All": ("All five financial signals together", None,
                  "The only defined signal set: the 8 surprises plus all five financial signals. On hold with the single-signal runs."),
    "REG": ("Market regimes", None,
            "Results split into calm and stressed periods. Regimes must be defined before scoring, using only information available at each decision."),
    "AP2B": ("JEV only", "jev", "JEV represents the Agentic Workflow in the primary comparison."),
    "AP2A": ("Agent Committee only", "com", "Three AI agents debate; a chief investment officer sets 12-month views. Compared only with JEV."),
    "AP2-COMBO": ("Committee + JEV", None, "Combines the Committee's views with JEV's answer. The combination rule must be fixed before any test month is seen."),
    "AP3": ("Agentic Causal RAG", "rag",
            "Research graph, Hypothesis and Testing Agents, calibration. Its primary version is chosen before the test opens."),
    "AP3-RE": ("Causal RAG — Reduced Evidence", "rag",
               "Same agents and steps; the Testing Agent weighs research findings and market and economic data known at each decision. Built and checked end to end; its free real-model run (Qwen3 4B on a free GPU) is ready to start."),
    "AP3-HD": ("Causal RAG — With Historical Documents", "rag",
               "The reduced-evidence version plus official Fed, BLS and Census documents published before each decision. Built; waits for the BLS documents, which this cloud environment cannot download."),
    "AP3-RE-PROXY": ("Policy-path proxy variant", "rag",
                     "Sensitivity check for the missing fed funds futures: a clearly labelled stand-in (2-year Treasury yield minus the 4-week bill rate). Never replaces the frozen design."),
    "AP3-RE-vs-HD": ("Do historical documents help?", None,
                     "Compares the two versions on development months: does adding historical text improve Causal RAG? Secondary; never in the primary comparison."),
    "AP3-STD": ("Standard RAG vs Causal RAG", None,
                "Swaps graph-guided retrieval for plain similarity search, keeping the model, documents and budget the same. Needs Causal RAG results first."),
    "AP3-NR/RG/PERM/MED": ("Ablations and placebo checks", None,
                           "No retrieval at all (tests what the model remembers), a scrambled research graph, shuffled agent signals, and raw market data without causal routing."),
    "AP3-VAR": ("Model and calibration variants", None, "Alternative model settings or calibration methods. To be defined and fixed in advance; kept to a few."),
}
GROUP_KEY = {"Deterministic Quantitative Model": "det", "Agentic Workflow": "jev", "Agentic Causal RAG": "rag"}


def experiments_block(cfg: dict, within: list) -> dict:
    groups = []
    for g in cfg["research_design"]["within_approach_experiments"]["groups"]:
        def item(x):
            name, link, detail = EXP_TEXT[x["id"]]
            assert x["status"] in STATUS_ORDER, x
            return {"name": name, "status": x["status"], "detail": detail, "link": link}
        groups.append({"approach": GROUP_KEY[g["approach"]], "base": item(g["base"]), "variants": [item(v) for v in g["variants"]],
                       **({"blocked_by": g["base"]["blocked_by"]} if "blocked_by" in g["base"] else {})})
    return {"groups": groups, "within_contrast": within[0] if within else None}


def free_run_checks() -> list:
    """Status of the free Qwen3 4B run, read from the imported results bundle (never from mock runs)."""
    f = ROOT / "native_backtest" / "out" / "ap3" / "qwen3_runs" / "summary.json"
    if not f.exists():
        return [("Free real-model run (Qwen3 4B on a free GPU): ready, not yet run", False),
                ("95-month run: starts only if the reliability checks pass", False)]
    s = json.loads(f.read_text())
    g = {k: v.get("pass") for k, v in s.get("gates", {}).items()}
    gates_txt = ", ".join(f"{k} {'passed' if v else 'failed'}" for k, v in sorted(g.items())) or "pending"
    return [(f"Free real-model run (Qwen3 4B): {s['n_months']} of 95 months; checks: {gates_txt}", s["n_months"] == 95 and all(g.values())),
            ("Development results: " + ("available" if s.get("downstream") or (f.parent / "evaluation" / "evaluation.json").exists() else "after all 95 months"), False)]


def ap3_versions() -> dict:
    """The two Causal RAG versions with their genuine status, read from the run and check outputs."""
    nb = ROOT / "native_backtest"
    var = json.loads((nb / "ap3" / "variants_v1.json").read_text())
    eng = nb / "out" / "ap3" / "engineering_replay" / "reduced_evidence" / "summary.json"
    eng = json.loads(eng.read_text()) if eng.exists() else None
    chk = nb / "out" / "ap3" / "corpus_checks_v1.json"
    chk = json.loads(chk.read_text())["summary"] if chk.exists() else None
    real = [p for p in (nb / "out" / "ap3" / "dev_replay").glob("*/*/summary.json")] if (nb / "out" / "ap3" / "dev_replay").exists() else []
    if real:
        raise SystemExit("real AP3 development results exist: add them to the dashboard deliberately before rebuilding")
    eng_ok = bool(eng and eng["months"] == 95 and not eng["testing_agent_reliability"]["point_in_time_violations"])
    docs = chk["documents"] if chk else 0
    bls = len(chk["families_missing"]) if chk else 3
    base = ["Research findings from papers published before each year", "Market and economic data as known at 8 p.m. on decision day"]
    items = [
        {"key": "re", "label": var["variants"]["reduced_evidence"]["label"], "short": "Reduced evidence", "status": "awaiting_validation",
         "evidence": base,
         "checks": [("Built: same agents, retrieval, testing, calibration and allocation", True),
                    (f"Checked end to end on {eng['months'] if eng else 0} development months with demo responses", eng_ok),
                    ("No information later than the decision time reached the agents", eng_ok),
                    *free_run_checks()]},
        {"key": "hd", "label": var["variants"]["historical_documents"]["label"], "short": "With historical documents", "status": "blocked",
         "evidence": base + ["Official Fed, BLS and Census documents published before each decision"],
         "checks": [("Built: the reduced-evidence version plus official documents", True),
                    (f"{docs} Fed and Census documents downloaded and validated", bool(chk and not chk["build_errors"] and chk["point_in_time_pass"])),
                    (f"BLS documents ({bls} release families) blocked from this cloud environment", False),
                    ("Real model runs (after the BLS documents)", False)]},
    ]
    for it in items:
        it["checks"] = [{"text": t, "done": d} for t, d in it["checks"]]
    return {"items": items, "primary": var["primary_version"]["selected"],
            "primary_note": "Which version represents Causal RAG is decided before the historical test opens, from development checks only."}


def validation_block() -> dict:
    v = json.loads((ROOT / "native_backtest" / "config" / "validation_status_v1.json").read_text())
    return {"as_of": v["as_of"], "decision": v["decision"], "columns": v["columns"],
            "gates": [{"name": g["name"], "cells": g["cells"]} for g in v["gates"]]}


COMMON_RULES = [
    ("Same dates", "Decided at 8 p.m. New York time on the last trading day of each month, like every approach"),
    ("Monthly rebalancing", "Back to 60/40 at the next trading day's close; weights drift with returns during the month"),
    ("Same trading cost", "0.05% of every dollar traded; the first month starts from cash"),
    ("Dividends included", "Prices adjusted for every distribution (total return), from the same verified data"),
    ("Same return accounting", "Monthly return after costs, minus the 4-week Treasury bill rate over the same days")]


def common_block(cfg: dict) -> dict:
    b = cfg["common_benchmark"]
    return {"id": b["id"], "label": b.get("display_label", b["label"]), "formal_label": b["label"], "weights": b["weights"], "status": b["status"],
            "status_label": "Frozen" if b["status"] == "frozen" else "Awaiting freeze approval",
            "instruments": b["instruments"], "rules": [{"name": n, "text": t} for n, t in COMMON_RULES],
            "not_neutral": "A secondary passive investment reference, not the research baseline, not a fourth approach, not a neutral portfolio and not a measure of model skill: no corporate bonds, no long-term Treasuries and no cash.",
            "data_checks": "Both funds passed the dividend-adjustment data check."}


def methodology_block(cfg: dict) -> dict:
    w = cfg["windows"]
    return {
        "common_benchmark": common_block(cfg),
        "phases": [
            {"key": "train", "name": "Training", "from": w["research_timeline_start"], "to": "2019-02", "what": "Models learn; nothing scored"},
            {"key": "dev", "name": "Development", "from": w["development"][0], "to": w["development"][1], "what": "Diagnostics shown here"},
            {"key": "test", "name": "Historical test", "from": w["protected"][0], "to": w["protected"][1], "what": "Sealed until the freeze",
             "overlap": {"from": "2023-01", "to": "2023-12", "label": "2023: secondary period, reported separately"}},
            {"key": "live", "name": "Live", "from": None, "to": None, "what": "After the freeze"}],
        "pending": [
            "Choose which Causal RAG version represents the approach, before the historical test opens.",
            "Decide whether to resume the paused signal experiments."],
        "settings": [
            {"icon": "calendar", "name": "Decision time", "value": "8 p.m. New York time, last trading day of each month", "status": "frozen"},
            {"icon": "arrow", "name": "Trading", "value": "Next trading day's close; held one month", "status": "frozen"},
            {"icon": "cost", "name": "Trading cost", "value": "0.05% of every dollar traded", "status": "frozen"},
            {"icon": "cash", "name": "Cash rate", "value": "4-week Treasury bill", "status": "frozen"},
            {"icon": "window", "name": "Evaluation periods", "value": "Development Mar 2019 – Dec 2022; primary test Jan 2024 – Aug 2026; 2023 reported separately; all of 2023–2026 sealed until GO", "status": "frozen"},
            {"icon": "target", "name": "Primary metric", "value": "Net CER (certainty-equivalent return)", "status": "frozen", "tip": "cer"},
            {"icon": "chart", "name": "Supporting metrics", "value": "Sharpe ratio, worst fall, volatility, cumulative return, turnover, results against the passive reference", "status": "frozen"},
            {"icon": "scale", "name": "Significance test", "value": "Resampled blocks of months; the three comparisons judged together", "status": "frozen", "tip": "significance"},
            {"icon": "target", "name": "Research baseline", "value": "Deterministic Quantitative Model; comparisons: JEV vs baseline, Causal RAG vs baseline, Causal RAG vs JEV", "status": "frozen", "tip": "baseline"},
            {"icon": "bench", "name": "Passive portfolio reference", "value": "60% SPY / 40% IEF, rebalanced monthly; a secondary investment reference", "status": "frozen", "tip": "commonbench"},
            {"icon": "bench", "name": "Own benchmarks", "value": "Each approach's own fixed starting mix; shown in its details as a secondary check", "status": "design", "tip": "benchmark"},
            {"icon": "clock", "name": "Point-in-time data", "value": "Only information public before each decision", "status": "design"},
            {"icon": "refresh", "name": "Walk-forward", "value": "Refit monthly on past data (Deterministic); replay (JEV); walk-forward calibration (Causal RAG)", "status": "design", "tip": "walkforward"},
            {"icon": "assets", "name": "Assets and horizon", "value": "Stocks, Treasuries, corporate bonds over 1 month; or stocks and long Treasuries over 12 months", "status": "design"}],
    }


FLOWS = {
    "det": [
        {"kind": "data", "label": "Economic surprises", "text": "How far 8 US releases (jobs, retail sales, industrial production, ISM, CPI, core CPI, PPI, hourly earnings) beat or missed forecasts."},
        {"kind": "model", "label": "Ridge regression", "text": "A linear model, refit every month on past months only, turns the surprises into return forecasts. It shrinks weak signals toward zero."},
        {"kind": "output", "label": "1-month forecasts", "text": "Expected return above cash for stocks, Treasuries and corporate bonds next month."},
        {"kind": "alloc", "label": "Black–Litterman", "text": "Starts from 45% stocks, 35% Treasuries, 20% corporate bonds and tilts toward the forecasts, within fixed limits."}],
    "jev": [
        {"kind": "data", "label": "Market snapshot", "text": "Recent returns, volatility, rates, the term spread, uncertainty indexes and the cash yield, with calendar dates removed."},
        {"kind": "agent", "label": "JEV decision model", "text": "An AI model answers one question each month: will stocks beat bonds over the next 12 months? Its saved answers are replayed exactly."},
        {"kind": "output", "label": "Probability and tilt", "text": "The chance stocks win, a five-way tilt and a confidence level."},
        {"kind": "alloc", "label": "Capped tilt", "text": "Moves a 60% stocks, 40% long-Treasury portfolio between 40% and 80% stocks, more when JEV is confident."}],
    "rag": [
        {"kind": "data", "label": "Event packet", "text": "This month's data surprises, Fed meetings and large market moves, all public before 8 p.m. on decision day."},
        {"kind": "store", "label": "Knowledge graph", "text": "Cause-and-effect findings from economics papers. Each year sees only papers published before it."},
        {"kind": "agent", "label": "Hypothesis Agent", "text": "Proposes up to 6 testable hypotheses a month about how the events could move markets, citing research pathways."},
        {"kind": "tool", "label": "CauseTrace graph search", "text": "CauseTrace: the tools the agent uses to search the graph for pathways and pull the research behind each link."},
        {"kind": "agent", "label": "Testing Agent", "text": "Tries to disprove each hypothesis three times against the evidence available at the time and a rival explanation. Too little evidence means Insufficient, never support."},
        {"kind": "model", "label": "Calibration", "text": "Learns from past months only how much Supported and Contradicted hypotheses moved returns, and turns them into forecasts."},
        {"kind": "alloc", "label": "Black–Litterman", "text": "Same allocation as the Deterministic model: a 45/35/20 starting mix tilted toward the forecasts."}],
    "com": [
        {"kind": "data", "label": "Market snapshot", "text": "The same snapshot JEV reads, with calendar dates removed."},
        {"kind": "agent", "label": "Economist + Risk Manager", "text": "Two AI agents write independent views of the outlook."},
        {"kind": "agent", "label": "Chief investment officer", "text": "A third agent weighs both and sets 12-month return views with a confidence level."},
        {"kind": "alloc", "label": "Black–Litterman", "text": "Tilts a 60/40 portfolio toward the views, more when confidence is high."}],
}


def audit_block(sims: dict) -> dict | None:
    """Optional diagnostic: why the JEV and Deterministic curves look alike (independent integrity audit)."""
    if not AUDIT.exists() or not {"det", "jev"} <= set(sims):
        return None
    a = json.loads(AUDIT.read_text())
    det, jev = sims["det"]["net_total_return"].to_numpy(), sims["jev"]["net_total_return"].to_numpy()
    S, X = a["similarity"], a["decomposition"]["spread_by_design_vs_decisions"]
    # The audit rebuilt every return independently; the dashboard's own returns must give the same correlation.
    assert len(a["monthly"]["months"]) == len(det) and max(abs(x - (j - d)) for x, j, d in zip(a["monthly"]["spread"], jev, det)) < 1e-12 and abs(float(np.corrcoef(det, jev)[0, 1]) - S["corr_monthly_net"]) < 1e-12, "audit and dashboard returns differ"
    ev = a["reconciliation"]["vs_shared_evaluator"]
    return {"verdict": a["verdict"], "findings": len(a["findings"]),
            "max_abs_diff_net_return": max(ev[k]["max_abs_diff_net_return"] for k in ("AP1", "AP2B")),
            "corr_monthly_net": _r(S["corr_monthly_net"], 4), "corr_own_mixes": _r(S["corr_own_benchmarks"], 4),
            "corr_decisions": _r(S["corr_active_vs_own_benchmark"], 4), "same_direction": _r(S["direction_agreement_share"], 4),
            "months_gap_gt_1pt": S["spread_jev_minus_det"]["months_abs_gt_1pp"], "tracking_error": _r(S["spread_jev_minus_det"]["tracking_error_annualised"], 4),
            "share_from_mixes": _r(X["share_of_spread_variance_from_benchmarks"], 3), "share_from_decisions": _r(X["share_of_spread_variance_from_decisions"], 3),
            "spread": [_r(j - d) for j, d in zip(jev, det)], "report": AUDIT_REPORT}


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

    cbrep = report["common_benchmark_matched_dev"]
    cb_rows = {x["system"]: x for x in cbrep["systems"]}
    sims, neutral_sims, common = {}, {}, None
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
        if common is None:
            common = B.simulate(cfg, mk, dev, dev_recs)
            cb = cbrep["benchmark"]
            assert abs(M.metrics(common)["cer_delta_2_5"] - cb["cer_delta_2_5"]) < 1e-12, "common benchmark differs from the development report"
            out["dev"]["common_benchmark"] = {**common_block(cfg), "wealth": wealth(common), "metrics": metric_block(common)}
        rel = B.relative(sim, common, cfg)
        att = B.decomposition(sim, neutral_sims[nkey], common, cfg["metrics"]["cer_delta"])
        r0 = cb_rows[s["src"]]
        assert abs(rel["cer_difference"] - r0["vs_common"]["cer_difference"]) < 1e-12
        assert all(abs(att[k] - r0["decomposition"][k]) < 1e-12 for k in att)
        series = {"wealth": wealth(sim), "monthly_net_return": [_r(v) for v in sim["net_total_return"]],
                  "weights": {a: [_r(v, 4) for v in sim[f"w_{a}"]] for a in s["universe"]},
                  "metrics": mb, "neutral": nkey, "vs_neutral": contrast_block(vs),
                  "vs_common": {**contrast_block(rel), "cumulative_difference": _r(rel["cumulative_return"]["difference"]),
                                "excess_return_difference": _r(rel["annualized_excess_return_difference"]),
                                "tracking_error": _r(rel["tracking_error_annualized"])},
                  "decomposition": {"total": _r(att["total_vs_common"]), "decisions": _r(att["active_decisions"]), "mix": _r(att["benchmark_mix_difference"])}}
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
        "rag": {"status": "not run", "checks": ["No results until its real model run is done and validated"]}}
    steps = {}
    labels = ["As originally scored", "Verified price data", "Trade next trading day", "Shared trading costs", "Shared cash rate"]
    for key, src in (("com", "AP2A"), ("jev", "AP2B")):
        rr = report["ap2_execution_attribution"][src]["matched_2019-03_to_2022-12"]
        steps[key] = [{"step": labels[i], "cer": _r(r["cer_delta_2_5"]), "ann_excess_return": _r(r["net_annualized_excess_return"]),
                       "sharpe": _r(r["net_sharpe"], 4), "max_drawdown": _r(r["max_drawdown"])} for i, r in enumerate(rr)]
    out["native_vs_common"] = steps

    # Within-approach experiments, grouped by approach (framework_config research_design), in plain words.
    out["experiments"] = experiments_block(cfg, within)

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
        "demo": json.loads(DEMO.read_text()) if DEMO.exists() else None,
        "versions": ap3_versions()}

    n_dev = len(dev)
    sig_vs = [SYSTEMS[k]["short"] for k in PRIMARY if k in out["dev"]["series"] and out["dev"]["series"][k]["vs_neutral"]["p"] < 0.05]
    sig_pw = [f"{SYSTEMS[i['a']]['short']} vs {SYSTEMS[i['b']]['short']}" for i in primary if i["computed"] and i["p"] < 0.05]
    span = f"{dev[0].year}–{dev[-1].year}"
    if not sig_vs and not sig_pw:
        headline = (f"Development diagnostics, {span}: the Agentic Workflow (JEV) is not statistically different from the Deterministic "
                    "research baseline. Causal RAG is awaiting validation. Protected historical results (2023–2026) are sealed.")
        finding = "No clear difference from the baseline"
    else:
        headline = (f"Development diagnostics, {span}: statistically significant for " + ", ".join(sig_vs + sig_pw)
                    + ". Causal RAG is awaiting validation. Protected historical results (2023–2026) are sealed.")
        finding = "Significant: " + ", ".join(sig_vs + sig_pw)
    out["notes"] = {
        "headline": headline,
        "finding": finding,
        "know": ["Both approaches with results reproduce their authors' saved results exactly.",
                 f"On {n_dev} development months, JEV's difference from the Deterministic baseline is within what chance could produce.",
                 "Every approach is scored on the same months, trading costs and cash rate."],
        "not_yet": ["Whether AI improves on the baseline: the historical test (Jan 2024 – Aug 2026 primary) is still sealed.",
                    "Anything about Causal RAG: its free real-model run has not been done yet.",
                    "A controlled comparison: assets, horizons and information differ by design."],
        "can": ["Each approach was run with its own original code, which reproduced its authors' saved results before any comparison.",
                f"The approaches with results are scored on the same {n_dev} development months, with the same trading costs and cash rate.",
                "How each approach behaved: its returns, risk, worst falls and how its holdings moved."],
        "cannot": ["Which approach is better. Development months are where the approaches were built and checked, so these are diagnostics, not protected historical results.",
                   f"Small differences. With {n_dev} months, only large gaps could be told apart from chance.",
                   "A controlled comparison. The approaches hold different assets and use different horizons and information.",
                   "Anything about Causal RAG yet. Its results are unavailable until its real model run is done and validated."]}
    out["audit"] = audit_block(sims)
    out["validation"] = validation_block()
    out["methodology"] = methodology_block(cfg)
    out["flows"] = FLOWS
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size/1024:.0f} KB) sha256 {hashlib.sha256(OUT.read_bytes()).hexdigest()[:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
