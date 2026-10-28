#!/usr/bin/env python3
"""Common evaluation on development months (diagnostic; never confirmatory).

- AP2A/AP2B: native -> common execution attribution (variants V0..V4), extended development
  window 2005-02..2022-12 and the matched window 2019-03..2022-12.
- AP1, AP2A, AP2B on the matched window 2019-03..2022-12 under the common rule: absolute metrics,
  each system against its own native neutral portfolio, and pairwise CER contrasts (Holm).
  AP3 joins when its decisions exist.
- Consistency: the common-rule variant V4 must equal the shared evaluator's own result.

The protected window is enforced: every scored month is checked by framework.lock before use.
Usage: python -m native_backtest.scripts.development_evaluation
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from native_backtest.adapters import execution_attribution as ea
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
        rows.append({"system": s, "universe": "/".join(cfg["systems"][s]["universe"]), "absolute": m_abs,
                     "native_neutral": {"weights": cfg["systems"][s]["native_neutral_weights"], **m_neu},
                     "vs_own_neutral": rel})
    report["common_evaluation_matched_dev"] = rows

    # consistency: V4 == shared evaluator for AP2 on the matched window
    cons = {}
    for s in ("AP2A", "AP2B"):
        v4 = attribution[s]["matched_2019-03_to_2022-12"][-1]
        cons[s] = abs(v4["cer_delta_2_5"] - M.metrics(sims[s])["cer_delta_2_5"])
    report["consistency_v4_vs_shared_evaluator_abs_cer_diff"] = cons

    # 3. Pairwise contrasts (diagnostic)
    pairs = {}
    for x, y in itertools.combinations(("AP1", "AP2A", "AP2B"), 2):
        pairs[f"{x}-{y}"] = M.paired_cer_contrast(sims[x], sims[y])
    holm = M.holm({k: v["p_two_sided_bootstrap"] for k, v in pairs.items()})
    report["pairwise_contrasts_matched_dev"] = {k: {**v, **holm[k]} for k, v in pairs.items()}
    report["comparability_statement"] = (
        "AP1 trades SPY/IEF/LQD on one-month views; AP2A and AP2B trade SPY/TLT on 12-month views, and the "
        "systems read different information. Differences in net CER compare complete strategies, including "
        "asset choice, horizon and information access; they are not a controlled comparison of forecasting "
        "skill. Results relative to each system's native neutral portfolio do not remove these differences.")
    (OUT / "development_evaluation_report.json").write_text(json.dumps(report, indent=1, default=float))
    print(json.dumps({"consistency": cons, "AP2A_matched": attribution["AP2A"]["matched_2019-03_to_2022-12"],
                      "AP2B_matched": attribution["AP2B"]["matched_2019-03_to_2022-12"]}, indent=1, default=float)[:6000])
    for r in rows:
        print(r["system"], {k: round(v, 4) for k, v in r["absolute"].items() if k in ("cer_delta_2_5", "net_sharpe", "annualized_volatility")},
              "vs neutral ΔCER", round(r["vs_own_neutral"]["cer_difference"], 4), [round(x, 4) for x in r["vs_own_neutral"]["ci90"]])
    return 0 if max(cons.values()) < 1e-12 else 1


if __name__ == "__main__":
    raise SystemExit(main())
