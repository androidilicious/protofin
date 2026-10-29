"""AP3 agent reliability report and the pre-registered gate checks (G3a, G4a).

Reads month records produced by runner.run_month (either Causal RAG version) and measures whether the
agents worked as specified: response validity, failures, quote validation, seed agreement, rival testing,
mediator availability and point-in-time safety. Nothing here reads returns or labels.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
GATES = ROOT / "native_backtest/config/ap3_reliability_gates_v1.json"
DIRECTIONAL = ("supported", "contradicted")


def load_gates() -> dict:
    return json.loads(GATES.read_text())


def report(records: List[dict]) -> Dict:
    recs = sorted(records, key=lambda r: r["decision_month"])
    status = collections.Counter()
    agree, conflicts, rivals, failed_tests, n_tests = [], 0, 0, 0, 0
    downgraded, directional, assessor_calls = 0, 0, 0
    med = collections.defaultdict(collections.Counter)
    pools = collections.defaultdict(list)
    pit_violations = []
    lit_unsup, invalid_paths, n_hyp = 0, 0, 0
    failed_months = []
    forced, repeats = 0, 0
    for r in recs:
        ha = r["hypothesis_agent"]
        forced += bool(ha.get("final_answer_forced"))
        repeats += ha.get("duplicate_tool_calls", 0)
        if ha.get("failure"):
            failed_months.append({"month": r["decision_month"], "failure": ha["failure"][:200]})
        for h in ha["hypotheses"]:
            n_hyp += 1
            lit_unsup += bool(h.get("literature_unsupported"))
            invalid_paths += len(h.get("invalid_path_ids", []))
        dt = pd.Timestamp(r["packet"]["decision_time"])
        for t in r["tests"]:
            n_tests += 1
            status[t["status"]] += 1
            if t.get("failure"):
                failed_tests += 1
                continue
            agree.append(t["run_agreement"])
            conflicts += bool(t["conflict"])
            pool = t.get("evidence_pool")
            if pool:
                for k, v in pool["by_kind"].items():
                    pools[k].append(v)
                if pool["latest_available_at"] and pd.Timestamp(pool["latest_available_at"]) >= dt:
                    pit_violations.append({"month": r["decision_month"], "hypothesis": t["hypothesis_id"]})
            for run in t["runs"]:
                rivals += run.get("rival_valid", bool(run["plan"]["rival"].get("rival_path_id")))
                assessor_calls += run.get("assess_meta") is not None
                for it in run["assessments"]:
                    if it.get("label") in DIRECTIONAL:
                        directional += 1
                        downgraded += it.get("validated_label") != it.get("label")
                for m in run["mediator_tests"]:
                    med[m["series"]][m["result"]] += 1
    n_runs = sum(len(t["runs"]) for r in recs for t in r["tests"] if not t.get("failure"))
    return {
        "months": len(recs),
        "months_with_hypotheses": sum(bool(r["hypothesis_agent"]["hypotheses"]) for r in recs),
        "failed_months": failed_months,
        "months_final_answer_forced": forced,          # reported, not gated: the final answer came on the turn after the tool budget
        "repeated_tool_calls": repeats,
        "hypotheses": n_hyp,
        "literature_unsupported_share": (lit_unsup / n_hyp) if n_hyp else None,
        "invalid_path_ids_dropped": invalid_paths,
        "tests": n_tests,
        "failed_tests": failed_tests,
        "status_counts": dict(status),
        "status_shares": {k: v / n_tests for k, v in status.items()} if n_tests else {},
        "mean_seed_agreement": (sum(agree) / len(agree)) if agree else None,
        "unanimous_share": (sum(a == 1 for a in agree) / len(agree)) if agree else None,
        "conflict_share": (conflicts / (n_tests - failed_tests)) if n_tests - failed_tests else None,
        "rival_named_share": (rivals / n_runs) if n_runs else None,
        "assessor_calls": assessor_calls,
        "directional_labels": directional,
        "directional_labels_downgraded_by_quote_validation": downgraded,
        "mediator_results": {k: dict(v) for k, v in sorted(med.items())},
        "evidence_pool_mean_size": {k: sum(v) / len(v) for k, v in pools.items()},
        "point_in_time_violations": pit_violations,
    }


def call_validity(call_log: Path) -> Dict:
    """Schema-valid share per call type from the client's call log (one line per validated response) and
    the failure lines written by the replay."""
    ok, bad = collections.Counter(), collections.Counter()
    if call_log.exists():
        for line in call_log.read_text().splitlines():
            r = json.loads(line)
            kind = r["step"].split("_")[0]
            (bad if r.get("invalid") else ok)[kind] += 1
    kinds = sorted(set(ok) | set(bad))
    return {k: {"valid": ok[k], "invalid": bad[k], "rate": ok[k] / (ok[k] + bad[k])} for k in kinds}


def gate_g4a(rep: Dict, gates: Optional[dict] = None) -> Dict:
    g = (gates or load_gates())["G4a_development_replay"]
    checks = {
        "failed_months_share": (len(rep["failed_months"]) / rep["months"], len(rep["failed_months"]) / rep["months"] <= g["failed_months_share_max"]),
        "failed_tests_share": ((rep["failed_tests"] / rep["tests"]) if rep["tests"] else 0.0,
                               ((rep["failed_tests"] / rep["tests"]) if rep["tests"] else 0.0) <= g["failed_tests_share_max"]),
        "mean_seed_agreement": (rep["mean_seed_agreement"], rep["mean_seed_agreement"] is not None and rep["mean_seed_agreement"] >= g["mean_seed_agreement_min"]),
        "point_in_time_violations": (len(rep["point_in_time_violations"]), len(rep["point_in_time_violations"]) <= g["point_in_time_violations_max"]),
    }
    return {"checks": {k: {"value": v, "pass": bool(p)} for k, (v, p) in checks.items()}, "pass": all(p for _, p in checks.values())}
