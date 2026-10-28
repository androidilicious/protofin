#!/usr/bin/env python3
"""AP2 native reproduction (Committee and JEV) — development months only.

1. Native decisions for every saved month, from the unchanged site engine run in Node, with outcome
   fields removed from its inputs.
2. Decision-level fidelity: native JS vs native Python allocator; native parser re-parse of the
   cached raw CIO replies; JEV vs the authors' saved weights.
3. Performance-level reproduction under NATIVE execution assumptions, decision months up to
   2022-12 only: the native engine's own step() vs this package's replica, month by month.
   Native full-span summaries are NOT recomputed, because they include the protected window.
4. Decision records for the shared evaluator.

Usage: python -m native_backtest.scripts.ap2_native_reproduction
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from native_backtest.adapters import ap2_native as a
from native_backtest.framework.market import load_config, load_market
from native_backtest.framework.records import write_jsonl

OUT = a.OUT
LAST_DEV_AS_OF = "2022-12-30"   # decision month 2022-12, the last development month


def main() -> int:
    cfg = load_config()
    mk = load_market(cfg)
    report = {"last_development_as_of": LAST_DEV_AS_OF}

    js = {
        "AP2A": a.run_node(a.A2 / "site/js", "decisions", "committee", OUT / "committee_decisions_native_js.json")["rows"],
        "AP2B": a.run_node(a.FJ / "site/js", "decisions", "jev", OUT / "jev_decisions_native_js_featurejev.json")["rows"],
    }
    jev_a2 = a.run_node(a.A2 / "site/js", "decisions", "jev", OUT / "jev_decisions_native_js_approach2.json")["rows"]

    report["decision_fidelity"] = {
        "AP2A_js_vs_native_python_allocator": a.check_committee_against_native_python(js["AP2A"]),
        "AP2A_native_parser_reparse_of_cached_raw_replies": a.check_committee_reparse(),
        "AP2B_vs_saved_log_and_branches": a.check_jev(js["AP2B"], jev_a2),
    }

    perf = {}
    for sid, eng, mode in (("AP2A", a.A2, "committee"), ("AP2B", a.FJ, "jev")):
        nat = a.run_node(eng / "site/js", "native-dev", mode, OUT / f"{sid}_native_dev_engine.json", last_as_of=LAST_DEV_AS_OF)
        weights = {r["as_of"]: r["w_spy"] for r in js[sid]}
        rep = a.native_execution_replica(weights, LAST_DEV_AS_OF)
        eng_nav = np.array([r["nav_live"] for r in nat["log"]])
        eng_w = np.array([r["w"] for r in nat["log"]])
        perf[sid] = {
            "months": int(len(rep)), "first_as_of": rep["as_of"].iloc[0], "last_as_of": rep["as_of"].iloc[-1],
            "max_abs_diff_nav": float(np.max(np.abs(eng_nav - rep["nav"].to_numpy()))),
            "max_abs_diff_weight": float(np.max(np.abs(eng_w - rep["w"].to_numpy()))),
            "native_engine_summary_dev_only": nat["summary"]["live"],
            "native_fixed_60_40_summary_dev_only": nat["summary"]["fixed"],
        }
        perf[sid]["pass"] = perf[sid]["max_abs_diff_nav"] < 1e-12 and perf[sid]["max_abs_diff_weight"] < 1e-15
        rep.to_csv(OUT / f"{sid}_native_execution_replica_dev.csv", index=False)
    report["native_performance_reproduction_dev"] = perf

    files = {}
    for sid in ("AP2A", "AP2B"):
        recs, info = a.build_records(sid, js[sid], mk)
        files[sid] = {"path": f"native_backtest/out/decisions/{sid}.jsonl",
                      "sha256": write_jsonl(recs, Path(a.ROOT / "native_backtest/out/decisions" / f"{sid}.jsonl")),
                      "records": len(recs), "first": recs[0].decision_month, "last": recs[-1].decision_month,
                      "months_before_pinned_prices": [d["month"] for d in info["date_mismatches"]]}
    report["decision_files"] = files
    report["all_pass"] = all(v["pass"] for v in report["decision_fidelity"].values()) and all(v["pass"] for v in perf.values())
    (OUT / "ap2_native_reproduction_report.json").write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps({k: (v if k != "decision_files" else {s: {kk: vv for kk, vv in f.items() if kk != 'months_before_pinned_prices'} for s, f in v.items()}) for k, v in report.items()}, indent=1, default=str)[:4000])
    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
