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
import time
import subprocess
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
SIGNAL = ROOT / "native_backtest" / "out" / "signal_value" / "signal_value_v1.json"
SIGNAL_REPORT = "native_backtest/docs/SIGNAL_VALUE_ADDED_2026-10-29.md"

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

EXPLORATORY_LABEL = "EXPLORATORY \u2014 RELIABILITY GATES FAILED"
STATUS_ORDER = ("tested", "exploratory", "awaiting_validation", "planned", "blocked", "paused")
EXP_TEXT = {
    "AP1": ("Base model: 8 economic-data surprises", "det", "The Deterministic model as it runs in the primary comparison."),
    "AP1+B1..B5": ("Add one financial signal at a time", None,
                   "Credit spread, its 3-month change, yield-curve slope, a volatility premium, or 12-month momentum, each added on its own, "
                   "on the development months. Resumed and completed on 29 Oct 2026 after a written decision and a pre-registration."),
    "AP1+B-All": ("All five financial signals together", None,
                  "The only defined signal set: the 8 surprises plus all five financial signals. The pre-declared conventional-signal test."),
    "REG": ("Market regimes", None,
            "Results split by period and by how volatile markets were at the decision date. Both splits were fixed before scoring and use only "
            "information available at each decision."),
    "AP2B": ("JEV only", "jev", "JEV represents the Agentic Workflow in the primary comparison."),
    "AP2A": ("Agent Committee only", "com", "Three AI agents debate; a chief investment officer sets 12-month views. Compared only with JEV."),
    "AP2-COMBO": ("Committee + JEV", None,
                  "Holds the average of what the Committee and JEV each chose: same months, same two funds, no settings to tune. "
                  "The rule was fixed in advance."),
    "AP3": ("Agentic Causal RAG", "rag",
            "Research graph, Hypothesis and Testing Agents, calibration. Its primary version is chosen before the test opens."),
    "AP3-RE": ("Causal RAG — Reduced Evidence", "rag",
               "Same agents and steps; the Testing Agent weighs research findings and market and economic data known at each decision. Built and checked end to end. Its first free real-model run (Qwen3 4B) failed the reliability checks; a rerun with fixes is pending."),
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


def within_approach_results() -> dict:
    """Headline result of each completed within-approach experiment, read from the verified analysis output."""
    f = ROOT / "native_backtest" / "out" / "within_approach" / "within_approach_v1.json"
    if not f.exists():
        return {}
    r = json.loads(f.read_text())
    A, G, C = r["AP1_financial_signals"], r["REG_market_regimes"], r["AP2_committee_plus_jev"]
    sig = lambda s: A["systems"][s]["forecast"]
    best = max(("B1", "B2", "B3", "B4", "B5"), key=lambda s: sig(s)["normalized_pooled_se_improvement"])
    ball = sig("B-All")
    out = {
        "AP1+B1..B5": {
            "headline": "None of the five improves the forecasts",
            "learned": ("Added one at a time to the 8 economic surprises, no financial signal makes the forecasts better by enough to rule out "
                        "chance, and none passes the pre-set robustness rule. Every one of them lowers net CER."),
            "rows": [{"label": f"Largest improvement of the five ({ {'B1': 'credit spread level', 'B2': 'credit spread change', 'B3': 'yield-curve slope', 'B4': 'volatility premium', 'B5': '12-month momentum'}[best] })",
                      "value": _minus(f"{sig(best)['normalized_pooled_se_improvement']:+.4f}"), "note": f"p = {sig(best)['p_two_sided']:.2f}; {A['systems'][best]['holm_within_component_family']['holm_adjusted_p']:.2f} after correcting for the five"},
                     {"label": "Signals that pass the robustness rule", "value": "0 of 5", "note": "needs significance, the same sign in both halves and 2 of 3 assets"},
                     {"label": "Effect on net CER vs the baseline", "value": "all five lower it",
                      "note": _minus(f"from {min(A['systems'][s]['portfolio']['vs_A']['net_cer_difference'] for s in ('B1','B2','B3','B4','B5'))*100:+.2f} to {max(A['systems'][s]['portfolio']['vs_A']['net_cer_difference'] for s in ('B1','B2','B3','B4','B5'))*100:+.2f} pts a year")}]},
        "AP1+B-All": {
            "headline": "The combined signal set does not beat the baseline",
            "learned": ("All five financial signals together make the forecasts slightly worse than the 8 economic surprises alone, well within "
                        "what chance could produce. This was the pre-declared test for conventional signals, and it fails."),
            "rows": [{"label": "Forecast improvement vs the baseline", "value": _minus(f"{ball['normalized_pooled_se_improvement']:+.4f}"),
                      "note": _minus(f"95% range {ball['ci95'][0]:+.4f} to {ball['ci95'][1]:+.4f}; p = {ball['p_two_sided']:.2f}")},
                     {"label": "Net CER", "value": _pcts(A["systems"]["B-All"]["portfolio"]["net_cer"]),
                      "note": _minus(f"{A['systems']['B-All']['portfolio']['vs_A']['net_cer_difference']*100:+.2f} pts vs the baseline's ") + _pcts(A['A_reference']['net_cer'])},
                     {"label": "Signal coverage", "value": "100%", "note": "every signal available in all 46 months, for all three funds"}]},
        "REG": {
            "headline": "Everything earns less after 2019, and none of the approaches is more defensive",
            "learned": ("Split by period and by market volatility at the decision date. All four strategies earn far less per year from 2020 "
                        "onward at two to three times the volatility, and none of them holds up better than the passive portfolio when volatility is already high."),
            "rows": [{"label": "Deterministic net CER, 2019 vs 2020-22",
                      "value": f"{_pcts(G['systems']['det']['R1_date']['2019-03..2019-12']['net_cer'])} → {_pcts(G['systems']['det']['R1_date']['2020-01..2022-12']['net_cer'])}", "note": "10 months, then 36"},
                     {"label": "JEV net CER, 2019 vs 2020-22",
                      "value": f"{_pcts(G['systems']['jev']['R1_date']['2019-03..2019-12']['net_cer'])} → {_pcts(G['systems']['jev']['R1_date']['2020-01..2022-12']['net_cer'])}", "note": "same split"},
                     {"label": "Highest net CER in stressed months", "value": "the passive portfolio",
                      "note": f"{_pcts(G['systems']['passive']['R2_volatility']['stressed (VIX >= 20)']['net_cer'])} across 26 months with VIX at or above 20"}],
            "caution": ("One cell stands out: JEV beats the Deterministic model by "
                        + _minus(f"{G['contrasts']['JEV - Deterministic']['R1_date']['2019-03..2019-12']['net_cer_difference']*100:+.2f}")
                        + " points in 2019 "
                        + f"(p = {G['contrasts']['JEV - Deterministic']['R1_date']['2019-03..2019-12']['p_two_sided_bootstrap']:.2f}), but that is 10 months, "
                        + "one of eight cells, with no correction for looking at several. These splits are diagnostics and never select anything.")},
        "AP2-COMBO": {
            "headline": "The combination lands between its two parts, and beats neither",
            "learned": ("Holding the average of the Committee's and JEV's choices gives a slightly smoother ride than JEV alone, but it trades "
                        "much more, and the extra cost cancels the benefit. Combining the two agentic systems is neither better nor worse than either alone."),
            "rows": [{"label": "Net CER", "value": _pcts(C["metrics"]["combo"]["cer_delta_2_5"]),
                      "note": f"JEV {_pcts(C['metrics']['jev']['cer_delta_2_5'])}, Committee {_pcts(C['metrics']['com']['cer_delta_2_5'])}"},
                     {"label": "vs JEV", "value": _minus(f"{C['comparisons']['vs JEV']['net_cer_difference']*100:+.2f} pts"),
                      "note": f"p = {C['comparisons']['vs JEV']['p_two_sided_bootstrap']:.2f}: not statistically clear"},
                     {"label": "Trading per year", "value": _pcts(C["metrics"]["combo"]["annualized_one_way_turnover"], 0),
                      "note": f"against JEV's {_pcts(C['metrics']['jev']['annualized_one_way_turnover'], 0)}"}]},
    }
    for v in out.values():
        v["months"] = f"{r['months'][2]} development months"
    out.update(ap3_experiment_result())
    return out


def ap3_experiment_result() -> dict:
    """Causal RAG - Reduced Evidence: executed, with its real outcome and the reasons not to read it as skill."""
    ev = ROOT / "native_backtest/out/ap3/qwen3_runs/evaluation/evaluation.json"
    if not ev.exists():
        return {}
    e = json.loads(ev.read_text())
    if not e.get("exploratory"):
        return {}
    m, cov, cal = e["metrics"]["AP3"], e["coverage"], e["calibration"]
    c1 = e["primary_contrasts_development"]["AP3-AP1"]
    own = e["vs_own_benchmark"]
    pl = cal.get("placebo") or {}
    return {"AP3-RE": {
        "headline": "Ran end to end on genuine agent outputs; the gates still failed",
        "learned": ("All 95 agent months produced real qwen3:4b outputs and the 46 development months went through the "
                    "native pipeline. Its net CER is the highest of the three, and none of that is statistically "
                    "supported. The permutation placebo puts the genuine agent features near the bottom of the random "
                    "distribution, so the evidence does not support reading this as forecast skill."),
        "rows": [{"label": "Net CER", "value": _pcts(m["cer_delta_2_5"]),
                  "note": "vs Deterministic " + _minus(f"{c1['cer_difference'] * 100:+.2f} pts")
                          + f", p = {c1['p_two_sided_bootstrap']:.2f}: not statistically clear"},
                 {"label": "vs its own 45/35/20 control", "value": _minus(f"{own['cer_difference']*100:+.2f} pts"),
                  "note": f"p = {own['p_two_sided_bootstrap']:.2f}: not statistically clear"},
                 {"label": "Months with at least one hypothesis",
                  "value": f"{cov['scored_months_with_at_least_one_hypothesis']} of {cov['scored_months_present']}",
                  "note": f"{', '.join(cov['scored_months_without_hypotheses'])} produced none and falls back to its prior"},
                 {"label": "Permutation placebo percentile", "value": f"{pl.get('percentile', float('nan')):.1f}%",
                  "note": f"the genuine features beat only {pl.get('percentile', 0):.1f}% of {pl.get('n', 0):.0f} random relabelings"},
                 {"label": "Trading per year", "value": _pcts(m["annualized_one_way_turnover"], 0),
                  "note": "against the Deterministic model's 46%"}],
        "caution": ("Both pre-registered reliability gates failed (G3b accuracy 0.5667 with 2 opposite-direction "
                    "errors; G3a schema-valid call rate 0.9771). This is a diagnostic of the pipeline, not evidence "
                    "that the agents are reliable or that AI adds investment value."),
        "months": f"{m['n_months']} development months"}}




VS_LABEL = {"AP3-AP1": "vs_deterministic", "AP3-AP2B": "vs_jev"}


def ap3_exploratory_block(cfg: dict, mk, dev, cost: float) -> dict | None:
    """The exploratory (gate-failed) Causal RAG baseline: its real state, and its results once they exist.

    Nothing here is validated. Until the replay finishes the block reports what is still missing; it never shows a
    curve that was not computed from genuine agent outputs."""
    nb = ROOT / "native_backtest"
    mode = json.loads((nb / "config" / "ap3_exploratory_mode_v1.json").read_text())
    bundle = nb / "out" / "ap3" / "qwen3_runs" / "summary.json"
    ev = nb / "out" / "ap3" / "qwen3_runs" / "evaluation" / "evaluation.json"
    out = {"label": mode["labelling"]["label"], "identity": mode["baseline_identity"],
           "why": ("The agents' own reliability checks did not pass, so these outputs are a diagnostic of the pipeline, "
                   "not evidence that the agents are reliable or that AI adds investment value."),
           "model": "Qwen3 4B, free local GPU (a documented stand-in for the planned 70B model)",
           "state": "not_run", "months_done": 0, "months_needed": 95, "gates_failed": {}, "coverage": None, "results": None}
    if bundle.exists():
        b = json.loads(bundle.read_text())
        out["months_done"] = b.get("n_months", 0)
        out["run_date"] = (b.get("written_utc") or "")[:10]
        g = b.get("gates") or {}
        for name, v in g.items():
            if not v.get("pass"):
                out["gates_failed"][name] = {k: kv.get("value") for k, kv in (v.get("checks") or {}).items() if not kv.get("pass")}
        out["state"] = "partial" if out["months_done"] < 95 else "complete_agents"
    if not ev.exists():
        return out
    e = json.loads(ev.read_text())
    if not e.get("exploratory"):                      # only a labelled exploratory evaluation is shown here
        return out
    sim = pd.read_csv(nb / "out" / "ap3" / "qwen3_runs" / "evaluation" / "AP3_common_matched_dev.csv", dtype={"decision_month": str})
    months = sim["decision_month"].tolist()
    assert months == D_MONTHS[:len(months)] if (D_MONTHS := [str(m) for m in dev]) else True
    m = e["metrics"]["AP3"]
    cov = e.get("coverage") or {}
    weights = {a: [_r(v, 4) for v in sim[f"w_{a}"]] for a in ("SPY", "IEF", "LQD") if f"w_{a}" in sim.columns}
    out.update({
        "state": "results",
        "months": months,
        "wealth": wealth(sim),
        "monthly_net_return": [_r(v) for v in sim["net_total_return"]],
        "weights": weights,
        "metrics": {"cer": _r(m["cer_delta_2_5"]), "sharpe": _r(m["net_sharpe"], 4), "volatility": _r(m["annualized_volatility"]),
                    "drawdown": _r(m["max_drawdown"]), "turnover": _r(m["annualized_one_way_turnover"], 4),
                    "total_cost": _r(m["total_cost"], 6), "excess": _r(m["net_annualized_excess_return"]),
                    "cumulative": _r(m.get("cumulative_return"))},
        "coverage": {"months_with_a_hypothesis": cov.get("scored_months_with_at_least_one_hypothesis"),
                     "months_scored": cov.get("scored_months_present"), "agent_failures": cov.get("n_months_with_agent_failure"),
                     "tests": cov.get("tests"), "failed_tests": cov.get("failed_tests"), "status_counts": cov.get("status_counts") or {}},
        "vs": {VS_LABEL.get(k, k): {"cer_difference": _r(v["cer_difference"]), "ci95": [_r(x) for x in v["ci95"]],
                                    "p": _r(v["p_two_sided_bootstrap"], 4)}
               for k, v in (e.get("primary_contrasts_development") or {}).items()},
        "vs_common": {"cer_difference": _r(e["passive_reference"]["vs_reference"]["cer_difference"]),
                      "ci95": [_r(x) for x in e["passive_reference"]["vs_reference"]["ci95"]],
                      "p": _r(e["passive_reference"]["vs_reference"]["p_two_sided_bootstrap"], 4),
                      "cumulative_difference": _r(e["passive_reference"]["vs_reference"]["cumulative_return"]["difference"]),
                      "excess_return_difference": _r(e["passive_reference"]["vs_reference"]["annualized_excess_return_difference"]),
                      "tracking_error": _r(e["passive_reference"]["vs_reference"]["tracking_error_annualized"], 6)},
        "vs_own_neutral": {"cer_difference": _r(e["vs_own_benchmark"]["cer_difference"]),
                           "ci95": [_r(x) for x in e["vs_own_benchmark"]["ci95"]],
                           "p": _r(e["vs_own_benchmark"]["p_two_sided_bootstrap"], 4)},
        "calibration": {
            "intercept_only_share": _r((e["calibration"]["g4c_checks"] or {}).get("intercept_only_share"), 4),
            "calibration_slope": _r((e["calibration"]["g4c_checks"] or {}).get("calibration_slope"), 4),
            "placebo": {k: _r(v, 6) if isinstance(v, (int, float)) else v
                        for k, v in (e["calibration"].get("placebo") or {}).items()}},
    })
    return out



def experiments_block(cfg: dict, within: list) -> dict:
    results = within_approach_results()
    groups = []
    for g in cfg["research_design"]["within_approach_experiments"]["groups"]:
        def item(x):
            name, link, detail = EXP_TEXT[x["id"]]
            assert x["status"] in STATUS_ORDER, x
            out = {"name": name, "status": x["status"], "detail": detail, "link": link}
            if x["id"] in results:
                # results are shown only for experiments that actually ran: validated ones, and the exploratory
                # Causal RAG run whose own result carries its failed-gate designation.
                assert x["status"] in ("tested", "exploratory"), x
                out["result"] = results[x["id"]]
                if x["status"] == "exploratory":
                    out["designation"] = EXPLORATORY_LABEL
            return out
        groups.append({"approach": GROUP_KEY[g["approach"]], "base": item(g["base"]), "variants": [item(v) for v in g["variants"]],
                       **({"blocked_by": g["base"]["blocked_by"]} if "blocked_by" in g["base"] else {})})
    return {"groups": groups, "within_contrast": within[0] if within else None}


def _minus(t: str) -> str:
    return t.replace("-", "\u2212")          # the display minus sign used everywhere else on the dashboard


def _pcts(x, d=2):
    return _minus(f"{x * 100:.{d}f}%")


def free_run_checks() -> list:
    """Status of the free Qwen3 4B run, read from the imported results bundle (never from mock runs)."""
    f = ROOT / "native_backtest" / "out" / "ap3" / "qwen3_runs" / "summary.json"
    if not f.exists():
        return [("Free real-model run (Qwen3 4B on a free GPU): ready, not yet run", False),
                ("95-month run: starts only if the reliability checks pass", False)]
    from native_backtest.ap3 import protocol
    s = json.loads(f.read_text())
    g = s.get("gates", {})
    ok = {k: bool(v.get("pass")) for k, v in g.items()}
    current = (s.get("protocol") or {}).get("fingerprint") == protocol.fingerprint()
    day = s.get("written_utc", "")[:10]
    if all(ok.values()) and ok:
        head = f"Free real-model run (Qwen3 4B, {day}): reliability checks passed; {s['n_months']} of 95 months"
    else:
        why = []
        acc = (g.get("G3b", {}).get("checks", {}).get("accuracy") or {}).get("value")
        if acc is not None and not ok.get("G3b"):
            why.append(f"Testing Agent fixture accuracy {acc:.0%} (80% needed)")
        fm = (g.get("G3a", {}).get("checks", {}).get("failed_months") or {}).get("value")
        if fm is not None and not ok.get("G3a"):
            why.append(f"{fm} of 12 sample months without a final answer")
        head = f"Free real-model run (Qwen3 4B, {day}): {s['n_months']} sample months; reliability checks failed: " + "; ".join(why)
    out = [(head, bool(ok) and all(ok.values()) and s["n_months"] == 95)]
    if not current:
        out.append(("Fixed since that run: the agent never got its final-answer turn, plus graph-search and runner defects; "
                    "rerun on the free GPU pending (same thresholds)", False))
    out.append(("Development results: " + ("available" if s.get("downstream") or (f.parent / "evaluation" / "evaluation.json").exists()
                                           else "after all 95 months, only if the reliability checks pass"), False))
    return out


def ap3_versions() -> dict:
    """The two Causal RAG versions with their genuine status, read from the run and check outputs."""
    nb = ROOT / "native_backtest"
    var = json.loads((nb / "ap3" / "variants_v1.json").read_text())
    eng = nb / "out" / "ap3" / "engineering_replay" / "reduced_evidence" / "summary.json"
    eng = json.loads(eng.read_text()) if eng.exists() else None
    chk = nb / "out" / "ap3" / "corpus_checks_v1.json"
    chk = json.loads(chk.read_text())["summary"] if chk.exists() else None
    # Genuine AP3 results reach the dashboard only through the exploratory block below, which labels them; they are
    # never shown as a validated approach result.
    real = [p for p in (nb / "out" / "ap3" / "dev_replay").glob("*/*/summary.json")] if (nb / "out" / "ap3" / "dev_replay").exists() else []
    if real and not (nb / "out" / "ap3" / "qwen3_runs" / "evaluation" / "evaluation.json").exists():
        raise SystemExit("real AP3 development results exist without an exploratory evaluation: add them deliberately before rebuilding")
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


def ap3_sim() -> pd.DataFrame:
    """The imported exploratory Causal RAG simulation, as the shared evaluator produced it."""
    return pd.read_csv(ROOT / "native_backtest/out/ap3/qwen3_runs/evaluation/AP3_common_matched_dev.csv",
                       dtype={"decision_month": str})


def signal_value_block(sims: dict, neutral_sims: dict) -> dict | None:
    """Secondary analysis: each system against its own portfolio with the signals switched off (development months)."""
    if not SIGNAL.exists() or not {"det", "jev"} <= set(sims):
        return None
    r = json.loads(SIGNAL.read_text())
    mon = pd.read_csv(SIGNAL.parent / "monthly_v1.csv", dtype={"decision_month": str})
    ci = lambda c: {"cer_difference": _r(c["point"] if "point" in c else c["net_cer_difference"]), "ci95": [_r(v) for v in c["ci95"]],
                    "p": _r(c["p_two_sided_bootstrap"], 4), "clear": bool(c["statistically_clear_at_5pct"])}
    out = {"months": r["months"], "report": SIGNAL_REPORT, "systems": {}}
    pairs = [("det", "AP1"), ("jev", "AP2B")]
    if "AP3" in r["systems"] and "rag_exploratory" not in out:
        pairs.append(("rag", "AP3"))          # joins only once its genuine decisions exist; stays labelled
    for key, src in pairs:
        sv = r["systems"][src]
        nkey = "/".join(f"{a}{int(round(w * 100))}" for a, w in sv["no_signal_weights"].items())
        # the analysis and the dashboard must agree month by month on both portfolios
        on_sim = sims.get(key) if key in sims else ap3_sim()
        assert np.abs(mon[f"{src}_ON__net_total_return"].to_numpy() - on_sim["net_total_return"].to_numpy()).max() < 1e-12
        assert np.abs(mon[f"{src}_OFF__net_total_return"].to_numpy() - neutral_sims[nkey]["net_total_return"].to_numpy()).max() < 1e-12
        d, inc = r["decisions"][src], sv["incremental"]
        out["systems"][key] = {
            "no_signal": nkey, "no_signal_label": mix_label(sv["no_signal_weights"]),
            "with": metric_block(on_sim), "without": metric_block(neutral_sims[nkey]),
            "value": ci(inc), "tracking_error": _r(inc["tracking_error_annualised"], 4), "months_ahead": inc["months_active_positive"],
            "tilt_size": _r(d["one_way_tilt_mean"], 4), "extra_turnover": _r(d["turnover_with_minus_without_annualised"], 4),
            "tilt_before_costs": _r(r["attribution_net_cer"]["per_system"][src]["tilts_before_costs"]),
            "extra_costs": _r(r["attribution_net_cer"]["per_system"][src]["extra_costs_from_tilts"]),
            "hit_rate": _r(d["tilt_hit_rate_before_costs"], 3), "direction_changes": d["spy_tilt_direction_changes"],
            "stock_weight_range": _r(d.get("spy_weight_range_across_choices", d.get("spy_weight_range_across_forecast_terciles")), 4),
            "influence": {k: (_r(v) if isinstance(v, float) else v) for k, v in r["influence_leave_one_month_out"][src].items()},
            "active": [_r(v) for v in mon[f"{src}_active_net"]],
            "universe": sv["universe"], "no_signal_weights": sv["no_signal_weights"],
            **({"exploratory": True, "designation": sv["designation"], "note": sv.get("note")}
               if sv.get("exploratory") else {})}
    tp = r["attribution_net_cer"]["two_by_two"]
    q = r["questions"]
    out["gap"] = {"total": ci(q["jev_minus_deterministic_total"]), "mix": ci(q["no_signal_mix_difference"]),
                  "signals": ci(q["q3_jev_vs_deterministic_after_allocation"]),
                  "parts": {"stock": _r(tp["mix_stock_weight_net"]), "bond": _r(tp["mix_bond_sleeve_net"]),
                            "jev": _r(tp["jev_signal_value"]), "det": _r(tp["minus_deterministic_signal_value"])},
                  "signals_without_most_influential_month": _r(r["influence_leave_one_month_out"]["jev_minus_deterministic_signal_value"]["without_most_influential_month"]),
                  "most_influential_month": r["influence_leave_one_month_out"]["jev_minus_deterministic_signal_value"]["most_influential_month"]}
    # rounding: parts shown to 2 decimals need not add up to the rounded total; the tab says so when they do not
    shown = lambda v: round(v * 100, 2)
    out["gap"]["full_precision_residual"] = _r(r["attribution_net_cer"]["two_by_two_residual"], 12)
    out["gap"]["rounded_parts_sum"] = round(sum(shown(v) for v in tp.values()), 2)
    out["gap"]["rounded_total"] = shown(r["attribution_net_cer"]["total_net_cer_difference"])
    # the month that moved JEV's signal value most (leave-one-month-out), read from the analysis's monthly output
    inf = r["influence_leave_one_month_out"]["AP2B"]
    row = mon[mon["decision_month"] == inf["most_influential_month"]].iloc[0]
    assert abs(row["AP2B_active_net"] - (row["AP2B_ON__net_total_return"] - row["AP2B_OFF__net_total_return"])) < 1e-12
    out["influential_month"] = {
        "decision_month": inf["most_influential_month"], "entry": row["entry_date"], "exit": row["exit_date"],
        "jev_spy_weight": _r(row["AP2B_ON__w_SPY"], 4), "no_signal_spy_weight": _r(row["AP2B_OFF__w_SPY"], 4),
        "jev_active_return": _r(row["AP2B_active_net"]), "spy_return": _r(row["asset_return_SPY"], 4), "tlt_return": _r(row["asset_return_TLT"], 4),
        "jev_active_sum_all_months": _r(mon["AP2B_active_net"].sum()),
        "value_with": _r(inf["full"]), "value_without": _r(inf["without_most_influential_month"]),
        "only_month_that_flips_the_sign": inf["months_whose_removal_flips_the_sign"] == 1}
    nat, bh = r["sensitivities"]["jev_native_engine"], r["sensitivities"]["buy_and_hold_no_signal"]
    out["checks"] = {"native_jev_value": ci(nat["incremental"]), "buy_and_hold": {k: ci(bh[s]["incremental"]) for k, s in (("det", "AP1"), ("jev", "AP2B"))},
                     "independent_checks": json.loads((SIGNAL.parent / "independent_check_v1.json").read_text())["checks"],
                     "reproduces_previous": all(v["max_abs_difference"] == 0.0 for v in r["reproduces_previous_results"].values())}
    return out


def sensitivity_block() -> dict | None:
    """Forecast-to-allocation sensitivity: how far each allocator moves when its own view is rescaled."""
    f = ROOT / "native_backtest" / "out" / "sensitivity" / "forecast_to_allocation_sensitivity.json"
    if not f.exists():
        return None
    r = json.loads(f.read_text())
    audit = ROOT / "native_backtest" / "out" / "sensitivity" / "audit_forecast_to_allocation.json"
    scen = ["0x", "0.5x", "1x", "2x"]
    keys = (("det", "AP1"), ("jev", "AP2B"), ("com", "AP2A"))
    out = {"months": r["window"]["n_months"], "scenarios": scen, "labels": r["scenarios"],
           "report": "native_backtest/docs/FORECAST_TO_ALLOCATION_SENSITIVITY_2026-10-29.md",
           "preregistration": r["preregistration"], "systems": {}}
    for key, src in keys:
        a = r["approaches"][src]
        by, tr, vp = a["performance"]["by_scenario"], a["transmission"]["per_scenario_vs_1x"], a["view_pipeline"]
        rows = {}
        for s in scen:
            rows[s] = {
                "net_cer": _r(by[s]["net_cer"]), "vol": _r(by[s]["annualized_volatility"]),
                "sharpe": _r(by[s]["net_sharpe"], 4), "turnover": _r(by[s]["annualized_one_way_turnover"], 4),
                "cost_bp": _r(by[s]["annualized_cost"] * 1e4, 3), "max_dd": _r(by[s]["max_drawdown"]),
                "active_weight": _r(by[s]["mean_half_sum_abs_active"], 5),
                "intermediate_change": _r(tr[s]["mean_abs_intermediate_weight_change_vs_1x"], 5),
                "final_change": _r(tr[s]["mean_abs_final_weight_change_vs_1x"], 5),
                "attenuation": None if tr[s]["mean_constraint_attenuation_share"] is None else _r(tr[s]["mean_constraint_attenuation_share"], 5),
                "binding_months": tr[s]["months_with_any_binding_bound"],
                "vs_1x": None if s == "1x" else {
                    "cer_difference": _r(a["statistics"][f"net_cer_{s}_minus_1x"]["point"]),
                    "ci95": [_r(v) for v in a["statistics"][f"net_cer_{s}_minus_1x"]["ci95"]],
                    "p": _r(a["statistics"][f"net_cer_{s}_minus_1x"]["p_two_sided_bootstrap"], 4)}}
        ctrl = a["performance"]["by_scenario"]["control:native_neutral_static"]
        out["systems"][key] = {
            "universe": a["universe"], "neutral_weights": a["native_neutral_weights"],
            "neutral_label": mix_label(a["native_neutral_weights"]),
            "allocator": a["allocator"]["kind"], "entry_point": a["allocator"]["entry_point"],
            "bounds": a["allocator"]["bounds"], "role": a["role"],
            "by_scenario": rows, "control_net_cer": _r(ctrl["net_cer"]),
            "zero_equals_control": bool(a["zero_scenario_checks"].get("equals_native_neutral", False)),
            "reproduces_1x": bool(a["reproduction_of_1x"]["within_tolerance"]),
            "signal_variance_share": _r(r["cross_approach"]["per_approach_variance_split"][src]["signal_part_share_of_1x_variance"], 6),
            "where_attenuated": vp["kind"],
            "posterior_keeps": None if vp["kind"].startswith("pre-allocator") else _r(vp["mean_share_of_the_view_the_posterior_keeps"], 5),
            "view_vs_prior_bp": None if vp["kind"].startswith("pre-allocator") else _r(vp["mean_abs_view_minus_prior_bp"], 3),
            "jev_stages": None if not vp["kind"].startswith("pre-allocator") else {
                "largest_tilt": vp["stage_1_largest_available_tilt_points"],
                "weighted_offset": _r(vp["stage_2_mean_abs_probability_weighted_offset_points"], 4),
                "share_of_largest": _r(vp["stage_2_share_of_largest_tilt"], 4),
                "confidence": _r(vp["stage_3_mean_confidence"], 4),
                "signal_points": _r(vp["stage_3_mean_abs_confidence_weighted_offset_points"], 4),
                "equilibrium_edge": _r(vp["mean_abs_equilibrium_edge_points"], 4),
                "share_of_edge": _r(vp["signal_as_share_of_equilibrium_edge"], 5)}}
    cp = r["cross_approach"]["pairwise"]["AP1_vs_AP2B"]
    out["similarity"] = {"corr_1x": _r(cp["monthly_net_return_correlation_1x"], 6),
                         "corr_0x": _r(cp["monthly_net_return_correlation_0x"], 6),
                         "corr_signal_parts": _r(cp["monthly_signal_part_correlation"], 6),
                         "corr_det_vs_committee_1x": _r(r["cross_approach"]["pairwise"]["AP1_vs_AP2A"]["monthly_net_return_correlation_1x"], 6),
                         **({"corr_det_vs_rag_1x": _r(r["cross_approach"]["pairwise"]["AP1_vs_AP3"]["monthly_net_return_correlation_1x"], 6),
                             "corr_det_vs_rag_0x": _r(r["cross_approach"]["pairwise"]["AP1_vs_AP3"]["monthly_net_return_correlation_0x"], 6)}
                            if "AP1_vs_AP3" in r["cross_approach"]["pairwise"] else {})}
    a3 = r["approaches"]["AP3"]
    computed = "performance" in a3
    out["ap3"] = {"status": a3["status"], "computed": computed,
                  "months_available": a3.get("months_available") or a3.get("agent_months"),
                  "months_required": a3.get("months_required", 95),
                  "blockers": a3.get("blockers") or [],
                  "gates_failed": a3.get("gates_failed") or {},
                  "caveat": a3.get("caveat"), "categorical_note": a3.get("categorical_note"),
                  "designation": a3.get("designation") or a3.get("designation_if_run_on_current_outputs")}
    if computed:
        out["systems"]["rag"] = {
            "universe": a3["universe"], "neutral_weights": a3["native_neutral_weights"],
            "neutral_label": mix_label(a3["native_neutral_weights"]),
            "allocator": a3["allocator"]["kind"], "entry_point": a3["allocator"]["entry_point"],
            "bounds": a3["allocator"]["bounds"], "role": a3["role"],
            "exploratory": True, "designation": a3["designation"],
            "by_scenario": {s: {
                "net_cer": _r(a3["performance"]["by_scenario"][s]["net_cer"]),
                "vol": _r(a3["performance"]["by_scenario"][s]["annualized_volatility"]),
                "sharpe": _r(a3["performance"]["by_scenario"][s]["net_sharpe"], 4),
                "turnover": _r(a3["performance"]["by_scenario"][s]["annualized_one_way_turnover"], 4),
                "cost_bp": _r(a3["performance"]["by_scenario"][s]["annualized_cost"] * 1e4, 3),
                "max_dd": _r(a3["performance"]["by_scenario"][s]["max_drawdown"]),
                "active_weight": _r(a3["performance"]["by_scenario"][s]["mean_half_sum_abs_active"], 5),
                "intermediate_change": _r(a3["transmission"]["per_scenario_vs_1x"][s]["mean_abs_intermediate_weight_change_vs_1x"], 5),
                "final_change": _r(a3["transmission"]["per_scenario_vs_1x"][s]["mean_abs_final_weight_change_vs_1x"], 5),
                "attenuation": (None if a3["transmission"]["per_scenario_vs_1x"][s]["mean_constraint_attenuation_share"] is None
                                else _r(a3["transmission"]["per_scenario_vs_1x"][s]["mean_constraint_attenuation_share"], 5)),
                "binding_months": a3["transmission"]["per_scenario_vs_1x"][s]["months_with_any_binding_bound"],
                "vs_1x": (None if s == "1x" else {
                    "cer_difference": _r(a3["statistics"][f"net_cer_{s}_minus_1x"]["point"]),
                    "ci95": [_r(v) for v in a3["statistics"][f"net_cer_{s}_minus_1x"]["ci95"]],
                    "p": _r(a3["statistics"][f"net_cer_{s}_minus_1x"]["p_two_sided_bootstrap"], 4)})}
                for s in scen},
            "control_net_cer": _r(a3["performance"]["by_scenario"]["control:native_neutral_static"]["net_cer"]),
            "zero_equals_control": bool(a3["zero_scenario_checks"].get("equals_native_neutral", False)),
            "reproduces_1x": bool(a3["reproduction_of_1x"]["within_tolerance"]),
            "signal_variance_share": _r((r["cross_approach"]["per_approach_variance_split"].get("AP3") or {}).get("signal_part_share_of_1x_variance"), 6),
            "where_attenuated": a3["view_pipeline"]["kind"],
            "posterior_keeps": _r(a3["view_pipeline"].get("mean_share_of_the_view_the_posterior_keeps"), 5),
            "view_vs_prior_bp": _r(a3["view_pipeline"].get("mean_abs_view_minus_prior_bp"), 3),
            "jev_stages": None}
    out["validation"] = {"audit_checks": json.loads(audit.read_text())["n_checks"] if audit.exists() else None,
                         "audit_failures": json.loads(audit.read_text())["n_failed"] if audit.exists() else None,
                         "any_scenario_statistically_clear": False}
    for key, _ in keys:
        for s in scen:
            v = out["systems"][key]["by_scenario"][s]["vs_1x"]
            if v and (v["ci95"][0] > 0 or v["ci95"][1] < 0) and v["p"] < 0.05:
                out["validation"]["any_scenario_statistically_clear"] = True
    return out



# ---------------------------------------------------------------- interactive pipeline (genuine archived values)
PIPE_AP1 = ROOT / "native_backtest/out/sensitivity/ap1_transmission_trace.csv"
PIPE_AP2B = ROOT / "native_backtest/out/sensitivity/ap2b_transmission_trace.csv"
PIPE_RET = ROOT / "native_backtest/out/sensitivity"
STAGE2 = ROOT / "stage2/results/dev_rerun_v4_portfolio_2026-10-27"
MACRO = ROOT / "stage2/data/model_scoring_panel_E4_meanrule.csv"
MACRO_Z = ["nfp_z", "retail_sales_z", "industrial_production_z", "ism_manufacturing_z",
           "cpi_z", "core_cpi_z", "ppi_z", "ahe_z"]
MACRO_LABEL = {"nfp_z": "Payrolls", "retail_sales_z": "Retail sales", "industrial_production_z": "Industrial production",
               "ism_manufacturing_z": "ISM manufacturing", "cpi_z": "CPI", "core_cpi_z": "Core CPI",
               "ppi_z": "PPI", "ahe_z": "Average hourly earnings"}
TILTS = ["strong_equities", "lean_equities", "neutral", "lean_bonds", "strong_bonds"]
TILT_LABEL = {"strong_equities": "Strong equities", "lean_equities": "Lean equities", "neutral": "Neutral",
              "lean_bonds": "Lean bonds", "strong_bonds": "Strong bonds"}


AP3_RUN = ROOT / "native_backtest/out/ap3/qwen3_runs"
AP3_TRACE = ROOT / "native_backtest/out/sensitivity/ap3_transmission_trace.csv"
STATUSES = ("Supported", "Contradicted", "Insufficient")


def ap3_pipeline_months(months: list) -> dict:
    """Per-month Causal RAG stage values, from the genuine agent records and the imported evaluation.

    Returns {} unless the full 95-month agent replay exists AND its evaluation has been produced, so a partial or
    unevaluated run never yields replay values."""
    ev = AP3_RUN / "evaluation"
    need = [AP3_RUN / "summary.json", ev / "evaluation.json", ev / "predictions.csv", ev / "AP3_common_matched_dev.csv"]
    if not all(f.exists() for f in need) or not AP3_TRACE.exists():
        return {}
    summary = json.loads((AP3_RUN / "summary.json").read_text())
    if summary.get("n_months") != summary.get("target_months"):
        return {}
    pred = pd.read_csv(ev / "predictions.csv", dtype={"decision_month": str})
    sim = pd.read_csv(ev / "AP3_common_matched_dev.csv", dtype={"decision_month": str}).set_index("decision_month")
    tr = pd.read_csv(AP3_TRACE, dtype={"decision_month": str})
    tr = tr[tr["scenario"] == "1x"].set_index("decision_month")
    A = ("SPY", "IEF", "LQD")
    out = {}
    for m in months:
        f = AP3_RUN / "months" / f"{m}.json"
        if not f.exists() or m not in sim.index or m not in tr.index:
            continue
        j = json.loads(f.read_text())
        pm = pred[pred["decision_month"] == m]
        if pm.empty:
            continue
        by = {a: pm[pm["asset"] == a].iloc[0] for a in A if not pm[pm["asset"] == a].empty}
        one = next(iter(by.values()))
        t, rr = tr.loc[m], sim.loc[m]
        hyp = j.get("hypotheses") or []
        counts = {st: sum(1 for h in hyp if h.get("status") == st) for st in STATUSES}
        ev_rows = j.get("event") or []
        calls = len(((j.get("hypothesis_agent") or {}).get("tool_calls")) or [])
        sf = j.get("status_features") or {}
        out[m] = {
            "decision_date": str(j.get("decision_time", ""))[:10], "info_cutoff": str(j.get("decision_time", "")),
            "graph_vintage": j.get("graph_vintage"),
            "entry": str(rr["entry_date"]), "exit": str(rr["exit_date"]),
            "triggers": [{"trigger": e.get("trigger"), "description": e.get("description"),
                          "direction": e.get("direction"), "z": _r(e.get("surprise_z"), 4)} for e in ev_rows],
            "evidence_calls": calls,
            "hypotheses": [{"id": h.get("id"), "trigger": h.get("trigger"), "channel": h.get("channel"),
                            "status": h.get("status"), "confidence": h.get("confidence_stated"),
                            "mechanism": h.get("mechanism"),
                            "assets": {a: h.get("predicted_assets", {}).get(a) for a in A}} for h in hyp],
            "status_counts": counts, "n_hypotheses": len(hyp),
            "status_features": {a: {k: _r(v, 3) for k, v in (sf.get(a) or {}).items()} for a in A},
            "fit": {"n_train": int(one["n_train"]), "alpha": str(one["alpha"]),
                    "intercept_only": str(one["alpha"]) == "INTERCEPT_ONLY"},
            "forecast": {a: _r(float(v["prediction_excess_return"]), 6) for a, v in by.items()},
            "prior": {a: _r(float(t[f"pi_{a}"]), 6) for a in A},
            "posterior": {a: _r(float(t[f"mu_bl_{a}"]), 6) for a in A},
            "w_unconstrained": {a: _r(float(t[f"w_unconstrained_{a}"]), 5) for a in A},
            "weights": {a: _r(float(t[f"w_{a}"]), 5) for a in A},
            "pretrade": {a: _r(float(rr[f"pretrade_w_{a}"]), 5) for a in A},
            "binding": ("" if pd.isna(t["bounds_binding"]) else str(t["bounds_binding"])),
            "turnover": _r(float(rr["one_way_turnover"]), 5), "cost": _r(float(rr["cost"]), 6),
            "gross": _r(float(rr["gross_excess_return"]), 6), "net": _r(float(rr["net_excess_return"]), 6),
            "rf": _r(float(rr["rf_return"]), 6)}
    return out


def _row(df, month, **where):
    d = df[df["decision_month"] == month]
    for k, v in where.items():
        d = d[d[k] == v]
    return None if d.empty else d.iloc[0]


def pipeline_block(sims: dict) -> dict | None:
    """One stage-by-stage trace per development month, from the archived artifacts of each native pipeline.

    Nothing here is recomputed or invented: every number is read from a committed artifact, and a stage an
    architecture does not have (or has not run) is reported as absent rather than filled in."""
    if not PIPE_AP1.exists() or not PIPE_AP2B.exists():
        return None
    a1 = pd.read_csv(PIPE_AP1); a1 = a1[a1["scenario"] == "1x"]
    a2 = pd.read_csv(PIPE_AP2B); a2 = a2[a2["scenario"] == "1x"]
    r1 = pd.read_csv(PIPE_RET / "ap1_scenario_returns.csv"); r1 = r1[r1["scenario"] == "1x"]
    r2 = pd.read_csv(PIPE_RET / "ap2b_scenario_returns.csv"); r2 = r2[r2["scenario"] == "1x"]
    pred = pd.read_csv(STAGE2 / "stage2_predictions.csv"); pred = pred[pred["system"] == "A"]
    macro = pd.read_csv(MACRO); macro["month"] = macro["month"].astype(str)
    jev = {d.decision_month: d for d in read_jsonl(DEC / "AP2B.jsonl")}
    months = sorted(a1["decision_month"].astype(str).unique())

    det, jv = {}, {}
    for m in months:
        t, rr = _row(a1, m), _row(r1, m)
        pm = pred[pred["decision_month"] == m]
        mz = macro[macro["month"] == m]
        if t is None or rr is None or pm.empty or mz.empty:
            continue
        mz = mz.iloc[0]
        by_asset = {a: pm[pm["asset"] == a].iloc[0] for a in ("SPY", "IEF", "LQD") if not pm[pm["asset"] == a].empty}
        one = next(iter(by_asset.values()))
        det[m] = {
            "decision_date": str(one["decision_date"]), "entry": str(one["entry_date"]), "exit": str(one["exit_date"]),
            "surprises": [{"k": k, "label": MACRO_LABEL[k], "z": _r(float(mz[k]), 4)} for k in MACRO_Z if pd.notna(mz[k])],
            "n_macro_available": int(mz["n_macro_available"]),
            "fit": {"n_train": int(one["n_train"]), "n_features": int(one["n_features"]),
                    "alpha": str(one["alpha"]), "intercept_only": str(one["alpha"]) == "INTERCEPT_ONLY",
                    "latest_train_month": str(one["latest_train_month"])},
            "forecast": {a: _r(float(v["prediction_excess_return"]), 6) for a, v in by_asset.items()},
            "prior": {a: _r(float(t[f"pi_{a}"]), 6) for a in ("SPY", "IEF", "LQD")},
            "posterior": {a: _r(float(t[f"mu_bl_{a}"]), 6) for a in ("SPY", "IEF", "LQD")},
            "w_unconstrained": {a: _r(float(t[f"w_unconstrained_{a}"]), 5) for a in ("SPY", "IEF", "LQD")},
            "weights": {a: _r(float(t[f"w_{a}"]), 5) for a in ("SPY", "IEF", "LQD")},
            "pretrade": {a: _r(float(rr[f"pretrade_w_{a}"]), 5) for a in ("SPY", "IEF", "LQD")},
            "binding": ("" if pd.isna(t["bounds_binding"]) else str(t["bounds_binding"])),
            "turnover": _r(float(rr["one_way_turnover"]), 5), "cost": _r(float(rr["cost"]), 6),
            "gross": _r(float(rr["gross_excess_return"]), 6), "net": _r(float(rr["net_excess_return"]), 6),
            "rf": _r(float(rr["rf_return"]), 6),
            "realized": {a: _r(float(v["actual_excess_return"]), 6) for a, v in by_asset.items()}}
    for m in months:
        t, rr, d = _row(a2, m), _row(r2, m), jev.get(m)
        if t is None or rr is None or d is None:
            continue
        f = d.forecast["values"]
        jv[m] = {
            "decision_date": str(d.decision_time)[:10], "info_cutoff": str(d.info_cutoff),
            "entry": str(rr["entry_date"]), "exit": str(rr["exit_date"]),
            "regime": ("" if pd.isna(t["regime"]) else str(t["regime"])),
            "probs": [{"k": k, "label": TILT_LABEL[k], "p": _r(float(f["probs"].get(k, 0.0)), 4)} for k in TILTS],
            "choice": str(f["choice"]), "choice_label": TILT_LABEL.get(str(f["choice"]), str(f["choice"])),
            "p_stocks_beat_bonds": _r(float(f["p"]), 4),
            "offset_original": _r(float(t["offset_original"]), 4), "weighted_offset": _r(float(t["weighted_offset"]), 4),
            "confidence": _r(float(t["confidence"]), 4), "conf_applied": _r(float(t["conf_applied"]), 4),
            "base_edge": _r(float(t["base_edge"]), 4), "edge": _r(float(t["edge"]), 4),
            "w_unconstrained": {"SPY": _r(float(t["w_unconstrained_SPY"]), 5)},
            "weights": {a: _r(float(t[f"w_{a}"]), 5) for a in ("SPY", "TLT")},
            "pretrade": {a: _r(float(rr[f"pretrade_w_{a}"]), 5) for a in ("SPY", "TLT")},
            "binding": ("" if pd.isna(t["bounds_binding"]) else str(t["bounds_binding"])),
            "turnover": _r(float(rr["one_way_turnover"]), 5), "cost": _r(float(rr["cost"]), 6),
            "gross": _r(float(rr["gross_excess_return"]), 6), "net": _r(float(rr["net_excess_return"]), 6),
            "rf": _r(float(rr["rf_return"]), 6)}

    ridge = pred.groupby("alpha").size().to_dict()
    stages = {
        "det": [
            {"id": "data", "name": "Historical data", "what": "8 US macro releases against the forecasts that preceded them, plus credit spreads, the yield curve, a variance-risk proxy and 12-month momentum.",
             "out": "A point-in-time panel ending at the decision date."},
            {"id": "signal", "name": "Signal generation", "what": "Each release becomes a standardised surprise (z-score) using only data available before the decision.",
             "out": "8 standardised surprises."},
            {"id": "forecast", "name": "Forecasting", "what": "Ridge regression, refit every month on past months only, with the penalty chosen by inner cross-validation. It may choose the intercept alone.",
             "out": "A one-month expected excess return per asset."},
            {"id": "alloc", "name": "Portfolio allocation", "what": "Black\u2013Litterman: the forecast enters as the view q against the equilibrium prior \u03c0; the posterior \u03bc_BL feeds a bounded fully invested optimiser.",
             "out": "Target weights for SPY, IEF and LQD."},
            {"id": "trade", "name": "Trades & returns", "what": "Weights are traded at the entry close against the drifted pre-trade weights, at 5 bp per dollar traded, and held to the exit close.",
             "out": "Turnover, cost and the month's realised return."},
            {"id": "eval", "name": "Performance evaluation", "what": "Net of cost and the cash rate, the month joins the 46-month development series scored by the shared evaluator.",
             "out": "Net excess return, and its place in net CER, volatility and drawdown."}],
        "jev": [
            {"id": "data", "name": "Historical data", "what": "The point-in-time market and macro context available at the decision cut-off.",
             "out": "The month's context packet for the agent."},
            {"id": "signal", "name": "Signal generation", "what": "The agent answers with a probability over five tilt choices, a probability that stocks beat bonds, and its own confidence.",
             "out": "A five-way distribution, a choice and a confidence."},
            {"id": "forecast", "name": "Forecasting", "what": "The distribution is averaged into one offset in points of edge, then multiplied by the agent's confidence.",
             "out": "A signal-induced edge contribution."},
            {"id": "alloc", "name": "Portfolio allocation", "what": "edge = baseEdge + confidence x offset drives the native capped tilt; the stock weight is clipped to 40-80%.",
             "out": "Target weights for SPY and TLT."},
            {"id": "trade", "name": "Trades & returns", "what": "The same shared evaluator: traded at the entry close against drifted weights at 5 bp per dollar traded.",
             "out": "Turnover, cost and the month's realised return."},
            {"id": "eval", "name": "Performance evaluation", "what": "Net of cost and the cash rate, scored on the same 46 development months as every other approach.",
             "out": "Net excess return, and its place in net CER, volatility and drawdown."}],
        "rag": [
            {"id": "data", "name": "Historical data", "what": "Point-in-time evidence: the CauseTrace knowledge graph filtered to the decision year, and the research library.",
             "out": "An evidence pool with no post-decision material."},
            {"id": "signal", "name": "Hypothesis & testing agents", "what": "The Hypothesis Agent proposes causal pathways; the Testing Agent assesses each against retrieved evidence as Supported, Contradicted or Insufficient.",
             "out": "Assessed hypotheses with citations."},
            {"id": "forecast", "name": "Signal encoding & forecasting", "what": "Categorical assessments are encoded as status features and calibrated, walk-forward, into a numerical view.",
             "out": "A calibrated numerical view."},
            {"id": "alloc", "name": "Portfolio allocation", "what": "The native Causal RAG allocation over SPY, IEF and LQD.",
             "out": "Target weights."},
            {"id": "trade", "name": "Trades & returns", "what": "The same shared evaluator and costs as the other approaches.",
             "out": "Turnover, cost and realised return."},
            {"id": "eval", "name": "Performance evaluation", "what": "Scored on the same development months, once the reliability gates pass.",
             "out": "Net excess return and the development metrics."}]}
    rag = ap3_pipeline_months(months)
    return {
        "months": months, "stages": stages, "det": det, "jev": jv, **({"rag": rag} if rag else {}),
        "default_month": "2020-02" if "2020-02" in det else (months[0] if months else None),
        "ridge_alpha_counts": {str(k): int(v) for k, v in ridge.items()},
        "ridge_intercept_only_share": _r(ridge.get("INTERCEPT_ONLY", 0) / max(1, int(pred.shape[0])), 4),
        "rag_status": ({"available": True,
                 "reason": "Genuine qwen3:4b agent outputs that did NOT pass the pre-registered reliability gates.",
                 "designation": "EXPLORATORY \u2014 RELIABILITY GATES FAILED"} if rag else
                {"available": False,
                 "reason": "No genuine Causal RAG outputs exist for the development window, so no stage values are shown.",
                 "designation": "EXPLORATORY \u2014 RELIABILITY GATES FAILED"}),
        "sources": {
            "det": ["stage2/data/model_scoring_panel_E4_meanrule.csv",
                    "stage2/results/dev_rerun_v4_portfolio_2026-10-27/stage2_predictions.csv",
                    "native_backtest/out/sensitivity/ap1_transmission_trace.csv",
                    "native_backtest/out/sensitivity/ap1_scenario_returns.csv"],
            "jev": ["native_backtest/out/decisions/AP2B.jsonl",
                    "native_backtest/out/sensitivity/ap2b_transmission_trace.csv",
                    "native_backtest/out/sensitivity/ap2b_scenario_returns.csv"],
            **({"rag": ["native_backtest/out/ap3/qwen3_runs/months",
                        "native_backtest/out/ap3/qwen3_runs/evaluation/predictions.csv",
                        "native_backtest/out/sensitivity/ap3_transmission_trace.csv",
                        "native_backtest/out/ap3/qwen3_runs/evaluation/AP3_common_matched_dev.csv"]} if rag else {})}}



# ---------------------------------------------------------------- appendix index and build provenance
DOCS = [
    ("Portfolio Integrity Audit", "native_backtest/docs/PORTFOLIO_INTEGRITY_AUDIT_2026-10-29.md", "validation"),
    ("Signal Value-Added", "native_backtest/docs/SIGNAL_VALUE_ADDED_2026-10-29.md", "experiments"),
    ("Forecast-to-Allocation Sensitivity", "native_backtest/docs/FORECAST_TO_ALLOCATION_SENSITIVITY_2026-10-29.md", "experiments"),
    ("Within-Approach Experiments", "native_backtest/docs/WITHIN_APPROACH_EXPERIMENTS_2026-10-29.md", "experiments"),
    ("Causal RAG run diagnosis", "native_backtest/docs/AP3_QWEN3_RUN1_DIAGNOSIS_2026-10-29.md", "causal-rag"),
    ("Causal RAG exploratory baseline", "native_backtest/docs/AP3_EXPLORATORY_BASELINE_2026-10-29.md", "causal-rag"),
    ("Causal RAG exploratory backtest", "native_backtest/docs/AP3_EXPLORATORY_BACKTEST_2026-10-29.md", "causal-rag"),
    ("Dashboard redesign inventory", "native_backtest/docs/DASHBOARD_REDESIGN_INVENTORY_2026-10-29.md", "artifacts"),
]
CONFIGS = [
    ("Framework configuration", "native_backtest/config/framework_config_v1.json", "methodology"),
    ("Sensitivity pre-registration", "native_backtest/config/forecast_to_allocation_sensitivity_preregistration_v1.json", "experiments"),
    ("Causal RAG exploratory mode", "native_backtest/config/ap3_exploratory_mode_v1.json", "causal-rag"),
    ("Causal RAG reliability follow-up", "native_backtest/config/ap3_reliability_followup_preregistration_v1.json", "causal-rag"),
]
APPENDIX_CATS = [
    ("methodology", "Methodology & formulas"),
    ("data", "Data & sources"),
    ("portfolio", "Portfolio & accounting"),
    ("statistics", "Statistics & uncertainty"),
    ("experiments", "Experiment configurations"),
    ("validation", "Validation & reliability"),
    ("causal-rag", "Causal RAG"),
    ("artifacts", "Artifacts & reproducibility"),
]


def _sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def build_block() -> dict:
    """What this data build was made from. The git commit is the one the build ran against; the release-manifest
    digest is content-addressed, so it identifies the repository state exactly whatever the commit turns out to be."""
    def git(*a):
        try:
            r = subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, timeout=10)
            return r.stdout.strip() if r.returncode == 0 else None
        except Exception:
            return None
    return {"generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "repository": "androidilicious/protofin", "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
            "git_commit_at_build": git("rev-parse", "HEAD"),
            "git_commit_note": "the commit this data was built against; the publishing commit is its child",
            "release_manifest_sha256": _sha(ROOT / "RELEASE_MANIFEST.sha256"),
            "dashboard_schema": "2.0 (redesigned information architecture)"}


def appendix_block(out: dict) -> dict:
    """A categorised index over the detail that the main sections link into. Entries point at data already in this
    file, or at a committed document; nothing is duplicated here."""
    e = []
    add = lambda cat, title, what, where, **kw: e.append({"cat": cat, "title": title, "what": what, "where": where, **kw})
    X = None
    add("methodology", "Frozen rules and settings", f"{len(out['methodology']['settings'])} settings fixed before scoring: windows, costs, risk aversion, bootstrap, universes.", "methodology.settings")
    add("methodology", "Research phases and windows", "Training/burn-in, development, the sealed historical test and the prospective window.", "methodology.phases")
    add("methodology", "Pending methodology decisions", "Choices not yet made, and what each blocks.", "methodology.pending")
    add("methodology", "Common benchmark specification", "The single SPY/IEF reference used to compare approaches with different universes.", "methodology.common_benchmark")
    add("data", "Asset universes", "What each approach holds and why the universes are not interchangeable.", "assets")
    add("data", "Pipeline input sources", "The committed artifacts every pipeline stage value is read from.", "pipeline.sources")
    add("data", "Signals and features per approach", "The inputs each approach is allowed to use.", "systems[*].signals")
    add("portfolio", "Accounting and transaction costs", "Target weights traded at the entry close against drifted pre-trade weights, 5 bp per dollar traded, first month from cash.", "methodology.settings")
    add("portfolio", "Native vs common benchmark reconciliation", "How each approach's own benchmark relates to the shared one.", "native_vs_common")
    add("portfolio", "Portfolio weights by month", "Target, pre-trade and realised weights for every development month.", "pipeline.det / pipeline.jev")
    add("statistics", "Primary contrasts with intervals", "Point estimates, 95% intervals and bootstrap p-values for the headline comparisons.", "dev.primary_contrasts")
    add("statistics", "Bootstrap methodology", "Paired circular block bootstrap, 6-month blocks, 5,000 replications, seed 20261027, delta 2.5.", "methodology.settings")
    add("statistics", "Full performance metric table", "Net CER, annualised return, volatility, Sharpe, maximum drawdown, turnover and cost for every series.", "dev.series")
    add("statistics", "Sensitivity scenario statistics", "Every scenario against 1x, with intervals and p-values.", "sensitivity.systems[*].by_scenario[*].vs_1x")
    add("experiments", "Within-approach experiment results", "Each tested variation, its contrast and its interval.", "experiments")
    add("experiments", "Signal Value-Added detail", "Counterfactuals, attribution, the influential month and the verification checks.", "signal_value")
    add("experiments", "Forecast-to-allocation detail", "View pipelines, attenuation shares, binding constraints and the correlation decomposition.", "sensitivity")
    add("validation", "Portfolio integrity audit", "An independent rebuild of every monthly return from raw prices.", "audit")
    add("validation", "Validation gate matrix", f"{len(out['validation']['gates'])} gates across the approaches, with current status.", "validation.gates")
    add("validation", "Signal Value verification checks", "The checks run before the signal-value results were read.", "signal_value.checks")
    add("causal-rag", "Reliability gate specifications", "G3a and G3b thresholds, unchanged, and their current measured values.", "ap3_exploratory.gates_failed")
    X = out["ap3_exploratory"]
    gates = "; ".join(f"{g} ({', '.join(f'{k.replace(chr(95), chr(32))} {v}' for k, v in c.items())})"
                      for g, c in (X.get("gates_failed") or {}).items())
    add("causal-rag", "Why every Causal RAG figure is marked exploratory",
        (f"Its agents did not pass the two pre-registered reliability gates: {gates}. The thresholds were set "
         "before the run and were not changed. Every Causal RAG number in this dashboard is therefore a "
         "diagnostic of the pipeline, not validated evidence that the agents are reliable or that AI adds "
         "investment value. No contrast involving it is statistically clear, and its permutation placebo places "
         "the genuine agent features near the bottom of the random distribution."),
        "ap3_exploratory", primary=True)
    add("causal-rag", "Exploratory backtest results", "The 46-month development result from genuine agent outputs, with every contrast and its interval.", "ap3_exploratory.metrics / ap3_exploratory.vs")
    add("causal-rag", "Agent coverage and assessments", "Months with a hypothesis, the month without one, tests run and failed, and the Supported/Contradicted/Insufficient counts.", "ap3_exploratory.coverage")
    add("causal-rag", "Calibration and placebo diagnostics", "Intercept-only share, calibration slope and the permutation placebo that argues against predictive content.", "ap3_exploratory.calibration")
    add("causal-rag", "Per-month agent records", "Every hypothesis, its trigger, mechanism, stated confidence and the Testing Agent's verdict, by month.", "pipeline.rag")
    add("causal-rag", "Signal value against its own control", "Causal RAG with its assessments switched off, on the same 45/35/20 portfolio, dates, prices and costs.", "signal_value.systems.rag")
    add("causal-rag", "Sensitivity scenarios", "Its 0x/0.5x/1x/2x scenarios through its own Black-Litterman allocator.", "sensitivity.systems.rag")
    add("causal-rag", "Exploratory mode", "What the gate-failed diagnostic mode permits, and what it never permits.", "ap3_exploratory")
    add("causal-rag", "Knowledge graph and triggers", "The CauseTrace graph vintage, its nodes and the trigger set.", "ap3.graph / ap3.triggers")
    add("causal-rag", "Two candidate versions", "Reduced Evidence and Full Evidence, and what still separates them.", "ap3.versions")
    add("artifacts", "Reproduction checks", "Each approach reproduced its authors' saved results before any comparison.", "reproduction")
    add("artifacts", "Build provenance", "Branch, commit and the content-addressed release-manifest digest for this data build.", "build")
    for t, f, c in DOCS:
        add(c, t, "Full research report in the repository.", f, doc=True)
    for t, f, c in CONFIGS:
        add(c, t, "Committed configuration.", f, config=True)
    return {"categories": [{"id": i, "label": l} for i, l in APPENDIX_CATS], "entries": e,
            "docs": [{"title": t, "path": f, "cat": c} for t, f, c in DOCS],
            "configs": [{"title": t, "path": f, "cat": c} for t, f, c in CONFIGS]}


def export_block() -> dict:
    """What the Download Content package contains, and what it deliberately leaves out."""
    return {
        "zip_name": "BNY_Capstone_Dashboard_Content.zip",
        "report_format": "self-contained HTML",
        "report_format_note": ("A browser page cannot reliably produce a PDF without a print dialog, so the report is "
                               "a single self-contained HTML file that opens in any browser and prints to PDF."),
        "contents": [
            {"path": "README.txt", "what": "What the package is and how it was produced."},
            {"path": "MANIFEST.json", "what": "Dashboard version, source commit, generation date, included experiments, validation status and exclusions."},
            {"path": "report/Research_Report.html", "what": "The complete research report: overview, approaches, every experiment, results, detailed tables and the appendix."},
            {"path": "data/dashboard.json", "what": "The full dashboard dataset, exactly as the page reads it."},
            {"path": "data/performance_metrics.csv", "what": "Net CER, annualised return, volatility, Sharpe, maximum drawdown, turnover and cost per series."},
            {"path": "data/monthly_returns.csv", "what": "Monthly net and gross excess returns for every development month and series."},
            {"path": "data/portfolio_weights.csv", "what": "Target, pre-trade and realised weights per approach and month."},
            {"path": "data/signals_and_forecasts.csv", "what": "Macro surprises, ridge forecasts, agent probabilities, offsets, confidence and edges by month."},
            {"path": "data/sensitivity_scenarios.csv", "what": "Every approach and scenario: weights response, net CER, volatility, turnover, cost, binding months and intervals."},
            {"path": "data/within_approach_experiments.csv", "what": "Each tested variation, its status, contrast and interval."},
            {"path": "data/reliability_and_status.csv", "what": "Reliability gates, their thresholds, measured values and coverage."},
            {"path": "appendix/appendix.html", "what": "The complete organised appendix."},
            {"path": "appendix/appendix_index.csv", "what": "Every appendix entry with its category and where the underlying data lives."}],
        "excluded": [
            "The protected historical test window 2023-01..2026-08: never computed, never scored, never exported.",
            "GitHub tokens and any credential: none exist in the dashboard data.",
            "Raw claims-data text from the Causal RAG bundles: redacted at source before anything was committed.",
            "Causal RAG development backtest results: they do not exist yet, so none are included.",
            "Chart images: charts are redrawn in the HTML report from the same data rather than exported as pictures."]}


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
        "rag": {"status": "not run", "checks": ["No results until a real model run passes its reliability checks"]}}
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
                    "Anything about Causal RAG: its first free real-model run failed the reliability checks; a rerun with fixes is pending.",
                    "A controlled comparison: assets, horizons and information differ by design."],
        "can": ["Each approach was run with its own original code, which reproduced its authors' saved results before any comparison.",
                f"The approaches with results are scored on the same {n_dev} development months, with the same trading costs and cash rate.",
                "How each approach behaved: its returns, risk, worst falls and how its holdings moved."],
        "cannot": ["Which approach is better. Development months are where the approaches were built and checked, so these are diagnostics, not protected historical results.",
                   f"Small differences. With {n_dev} months, only large gaps could be told apart from chance.",
                   "A controlled comparison. The approaches hold different assets and use different horizons and information.",
                   "Anything about Causal RAG yet. Its results are unavailable until a real model run passes its reliability checks."]}
    out["audit"] = audit_block(sims)
    out["signal_value"] = signal_value_block(sims, neutral_sims)
    out["sensitivity"] = sensitivity_block()
    out["ap3_exploratory"] = ap3_exploratory_block(cfg, mk, dev, cost)
    out["validation"] = validation_block()
    out["methodology"] = methodology_block(cfg)
    out["flows"] = FLOWS
    out["pipeline"] = pipeline_block(sims)
    out["build"] = build_block()
    out["appendix"] = appendix_block(out)
    out["export"] = export_block()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size/1024:.0f} KB) sha256 {hashlib.sha256(OUT.read_bytes()).hexdigest()[:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
