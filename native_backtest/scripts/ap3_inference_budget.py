#!/usr/bin/env python3
"""AP3 inference budget from measured prompt sizes (no model is called).

Reads the prompt sizes measured by the development-readiness dry run
(native_backtest/out/ap3/dev_readiness/readiness_report.json), combines them with the locked AP3 limits
and stated assumptions for what the dry run cannot measure (real tool-result sizes, real output lengths,
number of turns and hypotheses), and prices each stage for the candidate providers.

Writes native_backtest/out/ap3/inference_budget_v1.json.
Usage: python -m native_backtest.scripts.ap3_inference_budget
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "native_backtest/out/ap3/dev_readiness/readiness_report.json"
LIMITS = ROOT / "native_backtest/ap3/limits_v1.json"
OUT = ROOT / "native_backtest/out/ap3/inference_budget_v1.json"

# USD per 1M tokens (input, output). Third-party compilations checked 2026-10-28; confirm on the provider's page before purchase.
PRICES = {"Amazon Bedrock (meta.llama3-1-70b-instruct-v1:0)": (0.72, 0.72),
          "DeepInfra (meta-llama/Meta-Llama-3.1-70B-Instruct)": (0.40, 0.40)}

SCENARIOS = {
    # chars per token: Llama 3 tokenizer on English/JSON prompts; 3.5 central, 3.0 conservative (more tokens)
    "typical": {"chars_per_token": 3.5, "ha_turns": 6, "tool_growth_chars": 2000, "ha_base": "user_chars_median",
                "ha_tool_out": 80, "ha_final_out": 1500, "hyps": 4, "plan_extra_chars": 1700, "plan_out": 600,
                "assess_words": "170_words_per_chunk", "assess_out": 1000},
    "upper": {"chars_per_token": 3.0, "ha_turns": 16, "tool_growth_chars": 6200, "ha_base": "user_chars_p90",
              "ha_tool_out": 150, "ha_final_out": 2000, "hyps": 6, "plan_extra_chars": 3200, "plan_out": 2000,
              "assess_words": "260_words_per_chunk", "assess_out": 2000},
}


def per_month(rep: dict, lim: dict, s: dict) -> dict:
    ps, asz = rep["prompt_sizes_chars"], rep["assessor_prompt_size_model_chars"][s["assess_words"]]
    cpt, cap = s["chars_per_token"], lim["tokens"]["max_input_tokens_per_call"]
    ha_sys, ha_base = ps["hypothesis_turn"]["system_chars"], ps["hypothesis_turn"][s["ha_base"]]
    ha_in = sum(min(cap, (ha_sys + ha_base + k * s["tool_growth_chars"]) / cpt) for k in range(s["ha_turns"]))
    ha_out = (s["ha_turns"] - 1) * s["ha_tool_out"] + s["ha_final_out"]
    runs = lim["testing_agent"]["runs"]
    plan_in = (ps["testing"]["system_chars"] + ps["testing"]["user_chars_median"] + s["plan_extra_chars"]) / cpt
    assess_in = min(cap, (asz["system_chars"] + asz["user_chars_median"]) / cpt)
    t_in = s["hyps"] * runs * (plan_in + assess_in)
    t_out = s["hyps"] * runs * (s["plan_out"] + s["assess_out"])
    calls = s["ha_turns"] + s["hyps"] * runs * 2
    return {"calls": calls, "input_tokens": round(ha_in + t_in), "output_tokens": round(ha_out + t_out),
            "hypothesis_agent": {"input": round(ha_in), "output": round(ha_out)},
            "testing_agent": {"input": round(t_in), "output": round(t_out)}}


def main() -> int:
    rep, lim = json.loads(REPORT.read_text()), json.loads(LIMITS.read_text())
    active = rep["n_months"] - rep["triggers_per_month"]["months_without_trigger"]
    out = {"basis": "prompt sizes measured by the AP3 development-readiness dry run (engineering mock), plus the assumptions listed",
           "assumptions": SCENARIOS, "prices_usd_per_million_tokens": PRICES, "per_month": {}, "stages": {}}
    for name, s in SCENARIOS.items():
        out["per_month"][name] = per_month(rep, lim, s)
    m = out["per_month"]
    fixtures = {"calls": 30 * 3 * 2}
    stages = {
        "1_connectivity_and_canary": {"what": "5 fixed canary prompts at temperature 0; checks credentials, model ID and JSON output", "months": 0,
                                      "fixed": {"input_tokens": 5 * 2000, "output_tokens": 5 * 500}},
        "2_smoke_test_3_months": {"what": "3 decision months (quiet 2015-03, typical 2019-06, stressed 2020-03): end-to-end parse, citations, tool use", "months": 3},
        "3_G3a_12_month_smoke_run": {"what": "12 months to confirm the locked limits (turns, hypotheses, tokens) before the replay", "months": 12},
        "4_G3b_testing_agent_fixtures": {"what": "30 labelled fixtures x 3 runs (plan + assessor)", "months": 0,
                                         "fixed_by_scenario": True},
        "5_development_replay_95_months": {"what": "full AP3 development replay 2015-02..2022-12 (G4a/G4b)", "months": active},
        "6_contingency_one_full_rerun": {"what": "one allowed version change: repeat stages 3-5 once", "months": 12 + active, "fixtures_again": True},
    }
    for key, st in stages.items():
        row = {"what": st["what"]}
        for name, s in SCENARIOS.items():
            if "fixed" in st:
                tin, tout = st["fixed"]["input_tokens"], st["fixed"]["output_tokens"]
            else:
                tin = st["months"] * m[name]["input_tokens"]
                tout = st["months"] * m[name]["output_tokens"]
                if st.get("fixed_by_scenario") or st.get("fixtures_again"):
                    pm = per_month(rep, lim, s)
                    per_fix_in = (pm["testing_agent"]["input"] / s["hyps"])  # one hypothesis, 3 runs
                    per_fix_out = (pm["testing_agent"]["output"] / s["hyps"])
                    tin += round(30 * per_fix_in)
                    tout += round(30 * per_fix_out)
            row[name] = {"input_tokens": int(tin), "output_tokens": int(tout),
                         "usd": {p: round(tin / 1e6 * pr[0] + tout / 1e6 * pr[1], 2) for p, pr in PRICES.items()}}
        out["stages"][key] = row
    tot = {}
    for name in SCENARIOS:
        tin = sum(v[name]["input_tokens"] for v in out["stages"].values())
        tout = sum(v[name]["output_tokens"] for v in out["stages"].values())
        tot[name] = {"input_tokens": tin, "output_tokens": tout,
                     "usd": {p: round(tin / 1e6 * pr[0] + tout / 1e6 * pr[1], 2) for p, pr in PRICES.items()}}
    out["total_through_development_replay_with_contingency"] = tot
    out["prospective_per_month"] = {name: {"usd": {p: round(m[name]["input_tokens"] / 1e6 * pr[0] + m[name]["output_tokens"] / 1e6 * pr[1], 3)
                                                   for p, pr in PRICES.items()}} for name in SCENARIOS}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({"per_month": m, "stages": {k: {n: v[n]["usd"] for n in SCENARIOS} for k, v in out["stages"].items()},
                      "total": tot}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
