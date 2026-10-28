#!/usr/bin/env python3
"""AP3 development-readiness dry run (no model, no paid inference).

Builds the real inputs for every AP3 development month 2015-02..2022-12 (95 decisions) and pushes
them through the full agent pipeline with the ENGINEERING MOCK in place of the model:

- event packets from the point-in-time macro-surprise panel, the FOMC calendar and mediator stress
  triggers (only data with available_at <= the 20:00 ET decision time);
- the year-filtered research graph vintage and pathway library for each decision year;
- the pinned mediator store for the Testing Agent's market tests;
- no evidence corpus yet (not built), so assessor calls are skipped and every test is Insufficient.

Outputs (native_backtest/out/ap3/dev_readiness/):
- ap3_packets_v1.jsonl   the 95 frozen event packets (inputs only; no outcome is read), hashed;
- readiness_report.json  per-component status, input checks, and measured prompt sizes per call type,
                         which feed the inference cost estimate.
Mock outputs are never results: every record is marked engineering_mock and none is stored or scored.

Inventory v2 (--inventory v2) uses the validated mediator inventory (vintage-aware availability, BEI5Y,
the labelled IG-spread proxy, one-source VIX) and writes ap3_packets_v2.jsonl and readiness_report_v2.json
next to the v1 files, which stay as they are. v2 packets carry a mediator_series block that says what each
series is. Trigger counts remain provisional until FF_FUTURES_6M is supplied or dropped.

Usage (repository root; needs `python mvp/run.py fetch` incl. claims data):
  python -m native_backtest.scripts.ap3_dev_readiness [--inventory v1|v2]
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import statistics
import tempfile
from pathlib import Path

import pandas as pd

from native_backtest.ap3 import engineering_mock, fomc_calendar, mediator_data, runner, testing_agent
from native_backtest.ap3.graph_vintage import build_vintage, load_concepts
from native_backtest.ap3.llm_client import EngineeringMockProvider, LLMClient
from native_backtest.framework.lock import assert_scoring_allowed
from native_backtest.framework.market import decision_time_iso, load_config, load_market, months_between

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "stage2/data/model_scoring_panel_E4_meanrule.csv"
PANEL_SHA = "459bef989561aa66f32eccc6d0758ff15b8d50fbd3cdea51b5eced8f0fa456b1"
LIBS = ROOT / "native_backtest/data/_external/ap3_libraries"
OUT = ROOT / "native_backtest/out/ap3/dev_readiness"
SURPRISE_COLS = {"NFP": "nfp_z", "RETAIL_SALES": "retail_sales_z", "INDUSTRIAL_PRODUCTION": "industrial_production_z",
                 "ISM_MANUFACTURING": "ism_manufacturing_z", "CPI": "cpi_z", "CORE_CPI": "core_cpi_z", "PPI": "ppi_z", "AHE": "ahe_z"}
# Size model for one evidence chunk: the native causal-rag-mvp chunker targets ~170 words (hard max 260).
CHUNK_WORDS_TYPICAL, CHUNK_WORDS_MAX = 170, 260


class SizeRecorder:
    """Wraps the mock provider and records the size of every request (characters)."""

    def __init__(self, inner):
        self.inner, self.name, self.model, self.is_mock = inner, inner.name, inner.model, True
        self.rows = []

    def complete(self, req):
        text, meta = self.inner.complete(req)
        self.rows.append({"step": req.step.split("_")[0] + "_" + req.step.split("_")[1] if req.step.startswith("hypothesis") else req.step.split("_")[0],
                          "step_full": req.step, "system_chars": len(req.system), "user_chars": len(req.user)})
        return text, meta


def load_panel() -> pd.DataFrame:
    if hashlib.sha256(PANEL.read_bytes()).hexdigest() != PANEL_SHA:
        raise SystemExit("macro panel does not match its pinned SHA-256")
    return pd.read_csv(PANEL).set_index("month")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", choices=["v1", "v2"], default="v1")
    inv = ap.parse_args(argv).inventory
    cfg = load_config()
    mk = load_market(cfg)
    months = months_between("2015-02", "2022-12")
    assert_scoring_allowed(months, protected_start=cfg["windows"]["protected"][0])  # inputs only, but keep the same guard
    concepts, limits = load_concepts(), runner.load_limits()
    panel = load_panel()
    dd = {m: mk.decision_dates[m] for m in months}
    fomc = fomc_calendar.events_by_decision_month(dd)
    store, med_status = mediator_data.load_store(include_pending_substitutes=True, inventory=inv)
    med_labels = None
    if inv != "v1":
        lab = mediator_data.labels(inv)
        med_labels = {k: lab[k] + ("" if k in store.series else " [no data in this run]") for k in limits["mediators"]["series"]}

    OUT.mkdir(parents=True, exist_ok=True)
    packets, checks, per_month = [], collections.Counter(), []
    vintages, libraries = {}, {}
    rec_provider = SizeRecorder(EngineeringMockProvider(engineering_mock.responder))
    assessor_sizes, plan_users = [], []
    with tempfile.TemporaryDirectory() as tmp:
        client = LLMClient(rec_provider, Path(tmp) / "cache", Path(tmp) / "calls.jsonl", "ap3-dev-readiness (engineering mock)")
        for m in months:
            day = pd.Timestamp(dd[m])
            dtime = pd.Timestamp(decision_time_iso(day))
            row = panel.loc[str(m)]
            surprises = {k: (None if pd.isna(row[c]) else float(row[c])) for k, c in SURPRISE_COLS.items()}
            ms = pd.Timestamp(m.start_time)
            stress = mediator_data.stress_events(store, ms, dtime, limits["mediators"]["trigger_daily_z"])
            for e in stress:  # every stress input must have been public by the decision time
                a = mediator_data.visible_available_at(store, e["series"], e["date"], dtime)
                checks["stress_available_before_decision"] += int(a <= dtime)
                checks["stress_checked"] += 1
            fevents = [{"date": e["date"], "release": e["release"]} for e in fomc[m]]
            checks["fomc_before_decision"] += sum(pd.Timestamp(e["date"]) <= day for e in fomc[m])
            checks["fomc_checked"] += len(fomc[m])
            packet = runner.build_packet(str(m), decision_time_iso(day), surprises, fevents, stress, concepts, limits, med_labels)
            packets.append(packet)
            year = m.year
            if year not in vintages:
                vintages[year] = build_vintage(year - 1, concepts)
                libraries[year] = json.loads((LIBS / f"library_v1.0_vintage{year - 1}.json").read_text())
            lib = libraries[year]
            n_before = len(rec_provider.rows)
            rec = runner.run_month(client, packet, vintages[year], lib, [], store, ms, limits)
            assert rec["engineering_mock"] is True
            # size model for the assessor call (skipped in this run because no corpus exists yet)
            for h, t in zip(rec["hypothesis_agent"]["hypotheses"], rec["tests"]):
                plan = t["runs"][0]["plan"]
                edges = testing_agent._edges_for("H", h["trigger"], h["mechanism"], h["predicted_assets"]) + \
                    (testing_agent._edges_for("R", h["trigger"], plan["rival"]["mechanism"], plan["rival"]["predicted_assets"]) if plan["rival"]["rival_path_id"] else [])
                for words in (CHUNK_WORDS_TYPICAL, CHUNK_WORDS_MAX):
                    fake = [{"doc_id": f"SIZE{i}", "chunk_id": f"SIZE{i}#c000", "available_at_et": packet["decision_time"], "text": " ".join(["wordx"] * words)}
                            for i in range(limits["testing_agent"]["chunks_supporting"] * 3)]
                    assessor_sizes.append({"words": words, "user_chars": len(testing_agent.assessor_prompt(packet, edges, fake)),
                                           "system_chars": len(testing_agent.native_assess.SYSTEM)})
            trig_counts = collections.Counter(t["trigger"] if t["trigger"] in ("FOMC", "MARKET_STRESS") else "MACRO_SURPRISE" for t in packet["triggers"])
            per_month.append({"month": str(m), "decision_time": packet["decision_time"], "graph_vintage": year - 1,
                              "triggers": dict(trig_counts), "n_triggers": len(packet["triggers"]),
                              "library_entries_for_triggers": sum(1 for e in lib["entries"] if e["trigger"] in {t["trigger"] for t in packet["triggers"]}),
                              "mock_calls": len(rec_provider.rows) - n_before})

    pk = OUT / f"ap3_packets_{inv}.jsonl"
    pk.write_text("".join(json.dumps(p, sort_keys=True) + "\n" for p in packets))
    rows = pd.DataFrame(rec_provider.rows)
    size = {}
    for step, g in rows.groupby("step"):
        size[step] = {"calls_in_mock_run": int(len(g)), "system_chars": int(g.system_chars.median()),
                      "user_chars_median": int(g.user_chars.median()), "user_chars_p90": int(g.user_chars.quantile(0.9)),
                      "user_chars_max": int(g.user_chars.max())}
    turn0 = rows[rows.step_full.str.endswith("turn_0")].user_chars.reset_index(drop=True)
    turn1 = rows[rows.step_full.str.endswith("turn_1")].user_chars.reset_index(drop=True)
    tool_growth = (turn1 - turn0[: len(turn1)]).dropna()
    asz = pd.DataFrame(assessor_sizes)
    ntr = [p["n_triggers"] for p in per_month]
    report = {
        "status": "DRY RUN with the engineering mock: no model was called and no output is a result",
        **({"inventory": inv, "provisional": "trigger counts are provisional until FF_FUTURES_6M is supplied (Bloomberg) or dropped"} if inv != "v1" else {}),
        "months": [str(months[0]), str(months[-1])], "n_months": len(months),
        "components": {
            "macro_surprise_panel": f"pinned {PANEL_SHA[:12]}…; 8 series; point-in-time z-scores",
            "fomc_calendar": f"{sum(len(v) for v in fomc.values())} events assigned to {len(months)} months",
            "mediators": med_status,
            "graph_vintages_and_libraries": f"{len(vintages)} decision years ({min(vintages)}-{max(vintages)}), vintage = decision year - 1",
            "evidence_corpus": "NOT BUILT: official-document acquisition needs network access to federalreserve.gov, bls.gov and census.gov (see AP3_READINESS)",
            "model": "not called (engineering mock); paid inference not approved",
        },
        "input_checks": {"stress_inputs_public_before_decision": f"{checks['stress_available_before_decision']}/{checks['stress_checked']}",
                         "fomc_events_on_or_before_decision_day": f"{checks['fomc_before_decision']}/{checks['fomc_checked']}",
                         "packets_sha256": hashlib.sha256(pk.read_bytes()).hexdigest()},
        "triggers_per_month": {"mean": round(statistics.mean(ntr), 2), "median": statistics.median(ntr), "max": max(ntr),
                               "months_without_trigger": sum(1 for x in ntr if x == 0)},
        "prompt_sizes_chars": size,
        "hypothesis_tool_result_growth_chars": {"median": int(tool_growth.median()) if len(tool_growth) else None,
                                                "p90": int(tool_growth.quantile(0.9)) if len(tool_growth) else None},
        "assessor_prompt_size_model_chars": {f"{w}_words_per_chunk": {"user_chars_median": int(g.user_chars.median()), "user_chars_max": int(g.user_chars.max()),
                                                                     "system_chars": int(g.system_chars.iloc[0])} for w, g in asz.groupby("words")},
        "per_month": per_month,
    }
    (OUT / ("readiness_report.json" if inv == "v1" else f"readiness_report_{inv}.json")).write_text(json.dumps(report, indent=1, default=str) + "\n")
    print(json.dumps({k: report[k] for k in ("input_checks", "triggers_per_month", "prompt_sizes_chars", "hypothesis_tool_result_growth_chars",
                                             "assessor_prompt_size_model_chars")}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
