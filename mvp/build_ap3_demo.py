#!/usr/bin/env python3
"""Build mvp/data/ap3_engineering_demo.json: one month of the AP3 pipeline run with the ENGINEERING MOCK
(no model) on the real 2018 graph vintage and synthetic fixture documents. It shows the shape of the
workflow only. It is labelled as a demo everywhere and is never scored.

Paper titles and graph labels from the claims dataset are not written (the dataset has no published
licence); only counts, years, evidence classes and the project's own concept names are kept.
Usage (repository root): python mvp/build_ap3_demo.py   (needs the claims data fetched locally)
"""
from __future__ import annotations

import collections
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from native_backtest.ap3 import engineering_mock, runner  # noqa: E402
from native_backtest.ap3.engineering_fixtures import FIXTURE_CHUNKS, fixture_mediators  # noqa: E402
from native_backtest.ap3.graph_vintage import build_vintage, load_concepts  # noqa: E402
from native_backtest.ap3.llm_client import EngineeringMockProvider, LLMClient  # noqa: E402

LIB = ROOT / "native_backtest" / "data" / "_external" / "ap3_libraries" / "library_v1.0_vintage2018.json"
OUT = ROOT / "mvp" / "data" / "ap3_engineering_demo.json"


def main() -> int:
    concepts = load_concepts()
    vintage = build_vintage(2018, concepts)
    lib = json.loads(LIB.read_text())
    limits = runner.load_limits()
    packet = runner.build_packet("2019-06", "2019-06-28T20:00:00-04:00", {"CPI": 1.4, "NFP": -0.2}, [], [], concepts, limits)
    with tempfile.TemporaryDirectory() as tmp:
        client = LLMClient(EngineeringMockProvider(engineering_mock.responder), Path(tmp) / "c", Path(tmp) / "calls.jsonl", "mvp-demo")
        rec = runner.run_month(client, packet, vintage, lib, FIXTURE_CHUNKS, fixture_mediators(), pd.Timestamp("2019-06-01"), limits)
    hyps = []
    for h, t in zip(rec["hypothesis_agent"]["hypotheses"], rec["tests"]):
        rr = h.get("research_records", [])
        runs = []
        for r in t["runs"]:
            a = r["assessments"]
            runs.append({"status": r["rubric"]["status"],
                         "supporting_items": r["rubric"]["n_valid_supporting"], "contradicting_items": r["rubric"]["n_valid_contradicting"],
                         "rejected_citations": sum(1 for x in a if x.get("label") and x.get("label") != x.get("validated_label")),
                         "market_tests": [m.get("result") for m in r["mediator_tests"]]})
        hyps.append({"trigger": concepts["triggers"].get(h["trigger"], {}).get("label", h["trigger"]),
                     "channel": h["channel"], "mechanism": h["mechanism"],
                     "predicted": h["predicted_assets"], "graph_paths_cited": len(h.get("paths", {})),
                     "literature_supported": not h.get("literature_unsupported", False),
                     "confidence": h.get("confidence_applied"),
                     "research_records": len(rr), "research_years": sorted({r["year"] for r in rr if r.get("year")}),
                     "evidence_classes": dict(collections.Counter(r.get("evidence_class") or "unlabelled" for r in rr)),
                     "testing_runs": runs, "final_status": t["status"], "run_agreement": t["run_agreement"],
                     "causal_validation": t["causal_validation"]})
    demo = {"label": "Engineering demo — mock responses and synthetic documents, not a result",
            "is_mock": True, "decision_month": packet["decision_month"], "graph_year": rec["graph_vintage"],
            "triggers": [{"event": t["description"], "surprise_z": t.get("surprise_z")} for t in packet["triggers"]],
            "hypotheses": hyps, "signals": rec["status_features"]}
    OUT.write_text(json.dumps(demo, indent=1))
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
