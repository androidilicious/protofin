"""AP3 month runner: event packet -> Hypothesis Agent -> Causal RAG -> Testing Agent -> status features.

The forecast (calibration layer) and the weights (allocation) are applied afterwards across months,
walk-forward, because they need completed labels. This module produces the per-month agent record,
which is hashed and stored before any outcome is read.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
_CT = ROOT / "native_backtest/vendor/causetrace_82abe0a"
if str(_CT) not in sys.path:
    sys.path.insert(0, str(_CT))
from causetrace.evidence import edge_evidence  # noqa: E402

from native_backtest.ap3 import hypothesis_agent, testing_agent
from native_backtest.ap3.encoder import status_features
from native_backtest.ap3.graph_vintage import Vintage, load_concepts
from native_backtest.ap3.llm_client import LLMClient
from native_backtest.ap3.mediators import MediatorStore
from native_backtest.ap3.tools import CauseTraceTools

LIMITS = ROOT / "native_backtest/ap3/limits_v1.json"
SURPRISE_TRIGGER = {"NFP": "NFP", "RETAIL_SALES": "RETAIL_SALES", "INDUSTRIAL_PRODUCTION": "INDUSTRIAL_PRODUCTION", "ISM_MANUFACTURING": "ISM_MANUFACTURING",
                    "CPI": "CPI", "CORE_CPI": "CORE_CPI", "PPI": "PPI", "AHE": "AHE"}


def load_limits() -> dict:
    return json.loads(LIMITS.read_text())


def build_packet(decision_month: str, decision_time: str, surprises: Dict[str, float], fomc_events: List[dict], stress_events: List[dict],
                 concepts: dict, limits: dict, mediator_series: Optional[Dict[str, str]] = None) -> dict:
    """Triggers: each macro release whose standardised surprise has |z| >= the locked threshold, each FOMC event in
    the month, and each mediator stress move. Surprise values are the AP1 panel's point-in-time z-scores."""
    trig = []
    for key, z in sorted(surprises.items()):
        if z is not None and pd.notna(z) and abs(float(z)) >= limits["trigger_surprise_abs_z"]:
            trig.append({"trigger": key, "description": concepts["triggers"][key]["label"], "surprise_z": round(float(z), 3),
                         "direction": "above consensus" if z > 0 else "below consensus"})
    for e in fomc_events:
        trig.append({"trigger": "FOMC", "description": concepts["triggers"]["FOMC"]["label"], **e})
    for e in stress_events:
        trig.append({"trigger": "MARKET_STRESS", "description": concepts["triggers"]["MARKET_STRESS"]["label"], **e})
    packet = {"decision_month": decision_month, "decision_time": decision_time, "triggers": trig,
              "all_surprises_z": {k: (None if v is None or pd.isna(v) else round(float(v), 3)) for k, v in sorted(surprises.items())}}
    if mediator_series is not None:   # inventory v2: what each mediator series is (IG_SPREAD is labelled as a proxy)
        packet["mediator_series"] = dict(mediator_series)
    return packet


def research_records(v: Vintage, hyp: dict, limit: int) -> List[dict]:
    """Causal RAG: CauseTrace's research records behind every edge of the cited paths, up to `limit`."""
    out = []
    for p in hyp["paths"].values():
        for s, t in zip(p[:-1], p[1:]):
            if not v.store.has_edge(s, t):
                continue
            ev = edge_evidence(v.store, s, t, limit=limit)
            for r in ev["evidence"]:
                out.append({"edge": f"{s} -> {t}", **{k: r.get(k) for k in ("paper_id", "title", "year", "evidence_class", "causal_inference_method")}})
                if len(out) >= limit:
                    return out
    return out


def rival_candidates(library: dict, hyp: dict, k: int = 5) -> List[dict]:
    cands = [e for e in library["entries"] if e["trigger"] == hyp["trigger"] and e["channel"] != hyp["channel"]]
    cands.sort(key=lambda e: (-e["distinct_papers"], e["hops"], e["path_id"]))
    return cands[:k]


def run_month(client: LLMClient, packet: dict, vintage: Vintage, library: dict, chunks: List[dict], mediators: MediatorStore,
              window_start, limits: Optional[dict] = None) -> Dict[str, Any]:
    limits = limits or load_limits()
    concepts = load_concepts()
    tools = CauseTraceTools(vintage, concepts, budget=limits["hypothesis_agent"]["max_tool_calls"])
    ha = hypothesis_agent.run(client, packet, library, tools, limits)
    tests = []
    for h in ha["hypotheses"]:
        recs = research_records(vintage, h, limits["causal_rag"]["max_research_records_per_hypothesis"])
        h["research_records"] = recs
        tests.append(testing_agent.test_hypothesis(client, packet, h, recs, rival_candidates(library, h), chunks, mediators, limits, window_start))
    feats = status_features(ha["hypotheses"], tests)
    record = {"decision_month": packet["decision_month"], "packet": packet, "graph_vintage": vintage.year,
              "library_sha256": library["library_sha256"], "hypothesis_agent": ha, "tests": tests, "status_features": feats,
              "provider": client.provider.name, "model": client.provider.model, "engineering_mock": client.is_mock}
    record["record_sha256"] = hashlib.sha256(json.dumps(record, sort_keys=True, default=str).encode()).hexdigest()
    return record
