#!/usr/bin/env python3
"""Common evaluation on development months (diagnostic; never confirmatory).

Research design (framework_config_v1.json, research_design): three primary approaches
- Deterministic Quantitative Model (AP1), Agentic Workflow represented by JEV (AP2B) and
Agentic Causal RAG (AP3) - plus the Agent Committee (AP2A) as a within-approach variant of
the Agentic Workflow.

- AP2A/AP2B: native -> common execution attribution (variants V0..V4) on the matched window
  2019-03..2022-12, and on 2011-01..2022-12 as a native-fidelity check only.
- Every implemented system on the matched window under the common rule: absolute metrics and
  each system against its own native neutral portfolio.
- Primary contrasts: pairwise net-CER differences among the primary approaches, one Holm family
  of three at the freeze. Contrasts with AP3 are pending until AP3 has genuine decisions.
- Within-approach contrast: Committee only vs JEV only, reported separately.
- Common benchmark (framework_config "common_benchmark"; evaluation layer only, secondary and
  descriptive): every system against the same fixed reference portfolio on the same dates, with the
  exact accounting decomposition (not a causal attribution) into decisions (vs its own native benchmark)
  and benchmark mix (own native benchmark vs the common one). It never enters the primary family.
- Consistency: the common-rule variant V4 must equal the shared evaluator's own result.

The protected window is enforced: every scored month is checked by framework.lock before use.
Usage: python -m native_backtest.scripts.development_evaluation
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from native_backtest.adapters import execution_attribution as ea
from native_backtest.framework import benchmark as B
from native_backtest.framework import metrics as M
from native_backtest.framework.accounting import simulate_records, static_portfolio_records
from native_backtest.framework.lock import assert_scoring_allowed
from native_backtest.framework.market import load_config, load_market, months_between
from native_backtest.framework.records import read_jsonl

ROOT = Path(__file__).resolve().parents[2]
DEC = ROOT / "native_backtest/out/decisions"
OUT = ROOT / "native_backtest/out/development"


def main() -> int:
    cfg = load_config()
    mk = load_market(cfg)
    prot = cfg["windows"]["protected"][0]
    cost = cfg["costs"]["cost_per_dollar_traded"]
    OUT.mkdir(parents=True, exist_ok=True)
    report = {"status": "DEVELOPMENT DIAGNOSTIC — not a confirmatory result", "protected_window_start": prot}

    matched = months_between(*cfg["windows"]["development"])
    extended = months_between(*cfg["windows"]["extended_development_ap2"])
    assert_scoring_allowed(matched + extended, protected_start=prot)

    recs = {s: read_jsonl(DEC / f"{s}.jsonl") for s in ("AP1", "AP2A", "AP2B")}

    # 1. AP2 execution attribution
    attribution = {}
    for s in ("AP2A", "AP2B"):
        w = {r.generation["native_as_of"]: r.target_weights["SPY"] for r in recs[s]}
        attribution[s] = {"extended_2011-01_to_2022-12": ea.run_variants(w, mk, extended),
                          "matched_2019-03_to_2022-12": ea.run_variants(w, mk, matched)}
    report["ap2_execution_attribution"] = attribution

    # 2. Common evaluation, matched window
    sims, rows = {}, []
    for s in ("AP1", "AP2A", "AP2B"):
        sel = [r for r in recs[s] if r.decision_month in {str(m) for m in matched}]
        sims[s] = simulate_records(sel, mk, matched, cost_per_dollar=cost)
        neutral = static_portfolio_records(f"{s}_NEUTRAL", cfg["systems"][s]["native_neutral_weights"], sel)
        sims[f"{s}_NEUTRAL"] = simulate_records(neutral, mk, matched, cost_per_dollar=cost)
        sims[s].to_csv(OUT / f"{s}_common_matched_dev.csv", index=False)
    for s in ("AP1", "AP2A", "AP2B"):
        m_abs = M.metrics(sims[s])
        m_neu = M.metrics(sims[f"{s}_NEUTRAL"])
        rel = M.paired_cer_contrast(sims[s], sims[f"{s}_NEUTRAL"])
        rows.append({"system": s, "role": cfg["systems"][s]["role"], "universe": "/".join(cfg["systems"][s]["universe"]), "absolute": m_abs,
                     "native_neutral": {"weights": cfg["systems"][s]["native_neutral_weights"], **m_neu},
                     "vs_own_neutral": rel})
    report["common_evaluation_matched_dev"] = rows

    # 2b. Common benchmark, matched window (secondary, descriptive; not part of the primary family)
    spec = B.spec(cfg)
    delta = cfg["metrics"]["cer_delta"]
    tmpl = [r for r in recs["AP1"] if r.decision_month in {str(m) for m in matched}]
    bench = B.simulate(cfg, mk, matched, tmpl)
    bench.to_csv(OUT / f"{spec['id']}_matched_dev.csv", index=False)
    cb_rows = []
    for s in ("AP1", "AP2B", "AP2A"):
        cb_rows.append({"system": s, "role": cfg["systems"][s]["role"],
                        "absolute": {**M.metrics(sims[s]), "cumulative_return": B.cumulative_return(sims[s])},
                        "native_benchmark": {"weights": cfg["systems"][s]["native_neutral_weights"],
                                             "cumulative_return": B.cumulative_return(sims[f"{s}_NEUTRAL"])},
                        "vs_common": B.relative(sims[s], bench, cfg),
                        "decomposition": B.decomposition(sims[s], sims[f"{s}_NEUTRAL"], bench, delta)})
    cb_rows.append({"system": "AP3", "role": cfg["systems"]["AP3"]["role"] if "AP3" in cfg["systems"] else "primary",
                    "status": "pending: no genuine model decisions yet; nothing is simulated"})
    report["common_benchmark_matched_dev"] = {
        "status": spec["status"], "id": spec["id"], "label": spec["label"], "weights": spec["weights"], "rules": spec["rules"],
        "role": spec["role"], "decomposition_rule": spec["decomposition"],
        "benchmark": {**M.metrics(bench), "cumulative_return": B.cumulative_return(bench)},
        "systems": cb_rows,
        "note": "Secondary and descriptive. Subtracting one common benchmark leaves every difference between approaches unchanged; "
                "the pre-registered pairwise net-CER contrasts below remain the primary comparison."}

    # consistency: V4 == shared evaluator for AP2 on the matched window
    cons = {}
    for s in ("AP2A", "AP2B"):
        v4 = attribution[s]["matched_2019-03_to_2022-12"][-1]
        cons[s] = abs(v4["cer_delta_2_5"] - M.metrics(sims[s])["cer_delta_2_5"])
    report["consistency_v4_vs_shared_evaluator_abs_cer_diff"] = cons

    # 3. Primary contrasts (one Holm family of three at the freeze) and the within-approach contrast
    available = set(recs)
    primary, pending = {}, []
    for x, y in cfg["primary_contrasts"]:
        if x in available and y in available:
            primary[f"{x}-{y}"] = M.paired_cer_contrast(sims[x], sims[y])
        else:
            pending.append(f"{x}-{y}")
    family = len(cfg["primary_contrasts"])
    for k, v in primary.items():
        v["bonferroni_bound_full_family"] = min(1.0, family * v["p_two_sided_bootstrap"])
    report["primary_contrasts_matched_dev"] = {
        "family": [f"{x}-{y}" for x, y in cfg["primary_contrasts"]], "family_size_at_freeze": family,
        "multiplicity": "Holm over the full family once every contrast exists; until then the Bonferroni bound over the full family is reported (Holm-adjusted p cannot exceed it).",
        "computed": primary, "pending_no_decisions": pending}
    vc = {r["system"]: r["vs_common"]["cer_difference"] for r in cb_rows if "vs_common" in r}
    report["common_benchmark_matched_dev"]["check_primary_gaps_unchanged"] = {
        k: abs((vc[k.split("-")[0]] - vc[k.split("-")[1]]) - v["cer_difference"]) for k, v in primary.items()}
    within = {}
    for x, y in cfg["within_approach_contrasts"]:
        within[f"{x}-{y}"] = M.paired_cer_contrast(sims[x], sims[y])
    report["within_approach_contrasts_matched_dev"] = {
        "approach": "Agentic Workflow", "note": cfg["within_approach_contrasts_note"], "computed": within}
    report["research_design"] = cfg["research_design"]
    report["comparability_statement"] = (
        "AP1 (and AP3) trade SPY/IEF/LQD on one-month views; AP2B (JEV) and its within-approach variant AP2A trade "
        "SPY/TLT on 12-month views, and the systems read different information. Differences in net CER compare complete strategies, including "
        "asset choice, horizon and information access; they are not a controlled comparison of forecasting "
        "skill. Results relative to each system's native neutral portfolio do not remove these differences.")
    (OUT / "development_evaluation_report.json").write_text(json.dumps(report, indent=1, default=float))
    print(json.dumps({"consistency": cons, "AP2A_matched": attribution["AP2A"]["matched_2019-03_to_2022-12"],
                      "AP2B_matched": attribution["AP2B"]["matched_2019-03_to_2022-12"]}, indent=1, default=float)[:6000])
    for r in rows:
        print(r["system"], {k: round(v, 4) for k, v in r["absolute"].items() if k in ("cer_delta_2_5", "net_sharpe", "annualized_volatility")},
              "vs neutral ΔCER", round(r["vs_own_neutral"]["cer_difference"], 4), [round(x, 4) for x in r["vs_own_neutral"]["ci90"]])
    gaps = report["common_benchmark_matched_dev"]["check_primary_gaps_unchanged"]
    for r in cb_rows:
        if "decomposition" in r:
            a = r["decomposition"]
            print(r["system"], "vs common ΔCER", round(a["total_vs_common"], 4), "= decisions", round(a["active_decisions"], 4),
                  "+ benchmark mix", round(a["benchmark_mix_difference"], 4))
    return 0 if max(cons.values()) < 1e-12 and max(gaps.values(), default=0) < 1e-12 else 1


if __name__ == "__main__":
    raise SystemExit(main())
