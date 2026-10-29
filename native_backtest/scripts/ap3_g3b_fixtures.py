#!/usr/bin/env python3
"""Gate G3b: the Testing Agent on 30 labelled fixtures (native_backtest/ap3/fixtures/testing_agent_fixtures_v1.json).

Each fixture runs through the full, unchanged Testing Agent (plan prompt, balanced BM25 retrieval, native
causal-rag-mvp assessor with verbatim-quote validation, rubric, three seeds, majority). The status is
compared with the fixture's expected status and the pre-registered G3b criteria
(native_backtest/config/ap3_reliability_gates_v1.json) are checked. The Testing Agent is identical in both
Causal RAG versions, so one G3b run covers both.

  --provider engineering_mock   wiring check only (code-generated responses; the score means nothing)
  --provider hf_endpoint|bedrock  paid: plan only unless --execute and stage-B approval, secrets and cap exist

Usage (repository root):
  python -m native_backtest.scripts.ap3_g3b_fixtures --provider engineering_mock
  python -m native_backtest.scripts.ap3_g3b_fixtures --provider hf_endpoint [--execute]
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from native_backtest.ap3 import engineering_mock, protocol, reliability, runner, testing_agent
from native_backtest.ap3 import llm_client as L
from native_backtest.ap3.graph_vintage import load_concepts
from native_backtest.ap3.mediators import MediatorStore
from native_backtest.scripts import ap3_dev_replay as replay

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "native_backtest/ap3/fixtures/testing_agent_fixtures_v1.json"


def out_dir(provider: str) -> Path:
    base = "engineering_g3b" if provider == "engineering_mock" else "g3b"     # g3b/<provider>: genuine model outputs
    return ROOT / "native_backtest/out/ap3" / base / provider


def run(provider: str) -> dict:
    out = out_dir(provider)
    out.mkdir(parents=True, exist_ok=True)
    client = replay.make_client(provider, "reduced_evidence", out)
    fx = json.loads(FIXTURES.read_text())["fixtures"]
    labels = {k: v["label"] for k, v in load_concepts()["triggers"].items()}
    limits = runner.load_limits()
    empty = MediatorStore({})
    rows = []
    for f in fx:
        trig = {**f["trigger"], "description": labels[f["trigger"]["trigger"]]}
        packet = {"decision_month": f["decision_time"][:7], "decision_time": f["decision_time"], "triggers": [trig]}
        hyp = {"hypothesis_id": f"G3B-{f['id']}", **f["hypothesis"]}
        try:
            t = testing_agent.test_hypothesis(client, packet, hyp, [], [], f["excerpts"], empty, limits, f["decision_time"][:8] + "01")
            got, fail, raw = t["status"], None, None
        except L.ModelOutputError as e:
            t, got, fail, raw = None, "Insufficient", str(e)[:200], getattr(e, "raw_text", None)
        rows.append({"id": f["id"], "category": f["category"], "expected": f["expected_status"], "got": got, "failure": fail,
                     "run_statuses": t["run_statuses"] if t else [], "correct": got == f["expected_status"],
                     "runs": [run_detail(r) for r in t["runs"]] if t else [], "invalid_reply": raw})
    return {"rows": rows, "calls": client.calls}


def run_detail(run: dict) -> dict:
    """Everything needed to see why a fixture got its status. Fixtures are synthetic, so nothing is redacted."""
    plan = run["plan"]
    return {"seed": run["seed"], "status": run["rubric"]["status"],
            "plan": {"supporting_queries": plan["supporting_queries"], "contradicting_queries": plan["contradicting_queries"],
                     "rival_path_id": plan["rival"]["rival_path_id"], "rival_valid": run.get("rival_valid"), "implications": plan["implications"]},
            "retrieved": run["retrieved"], "assessor_called": run.get("assess_meta") is not None,
            "assessments": [{"edge": i["edge_id"], "model_label": i.get("label"), "validated_label": i.get("validated_label"),
                             "valid_supporting": i.get("n_valid_supporting"), "valid_contradicting": i.get("n_valid_contradicting"),
                             "supporting": [{"chunk_id": q.get("chunk_id"), "quote": q.get("quote"), "citation": q.get("citation_status")} for q in i.get("supporting_evidence") or []],
                             "contradicting": [{"chunk_id": q.get("chunk_id"), "quote": q.get("quote"), "citation": q.get("citation_status")} for q in i.get("contradicting_evidence") or []],
                             "conflict_declared": i.get("conflict"), "explanation": i.get("explanation"), "error": i.get("error")} for i in run["assessments"]],
            "rubric": run["rubric"],
            "tokens": {k: (run.get(m) or {}).get("usage") for k, m in (("plan", "plan_meta"), ("assessor", "assess_meta"))},
            "done_reason": {k: (run.get(m) or {}).get("done_reason") for k, m in (("plan", "plan_meta"), ("assessor", "assess_meta"))}}


def score(rows: list) -> dict:
    g = reliability.load_gates()["G3b_testing_agent_fixtures"]
    acc = sum(r["correct"] for r in rows) / len(rows)
    opposite = sum({r["expected"], r["got"]} == {"Supported", "Contradicted"} for r in rows)
    inj = [r for r in rows if r["category"] == "injection"]
    theory = [r for r in rows if r["category"] == "theory_only"]
    checks = {"accuracy": (acc, acc >= g["accuracy_min"]),
              "opposite_direction_errors": (opposite, opposite <= g["opposite_direction_errors_max"]),
              "injection_resisted": (sum(r["got"] != "Supported" for r in inj), all(r["got"] != "Supported" for r in inj)),
              "theory_only_never_supported": (sum(r["got"] == "Supported" for r in theory), all(r["got"] != "Supported" for r in theory))}
    by_cat = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        by_cat[r["category"]][0] += r["correct"]
        by_cat[r["category"]][1] += 1
    return {"checks": {k: {"value": v, "pass": bool(p)} for k, (v, p) in checks.items()}, "pass": all(p for _, p in checks.values()),
            "by_category": {k: f"{a}/{n}" for k, (a, n) in sorted(by_cat.items())}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["engineering_mock", *sorted(replay.FREE_PROVIDERS), *sorted(replay.PROVIDERS)], required=True)
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args(argv)
    mock = a.provider == "engineering_mock"
    if not mock and a.provider not in replay.FREE_PROVIDERS:
        missing = [m for m in replay.prerequisites_b(a.provider, "reduced_evidence") if "does not cover" not in m]
        print(json.dumps({"gate": "G3b", "provider": a.provider, "prerequisites_missing": missing,
                          "will_call_a_paid_model": bool(a.execute and not missing)}, indent=1))
        if not a.execute:
            return 0
        if missing:
            raise replay.NotApproved("not running: " + "; ".join(missing))
    res = run(a.provider)
    summary = {"gate": "G3b", "provider": a.provider, "engineering_mock": mock, "protocol_version": protocol.PROTOCOL_VERSION,
               "protocol_fingerprint": protocol.fingerprint(),
               "meaning": "WIRING CHECK ONLY: mock responses, the score carries no information" if mock else "real-model reliability gate",
               "fixtures": len(res["rows"]), "calls": res["calls"], **score(res["rows"]), "rows": res["rows"]}
    (out_dir(a.provider) / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=1))
    return 0 if (mock or summary["pass"]) else 3      # a failed real-model gate is a non-zero exit


if __name__ == "__main__":
    raise SystemExit(main())
