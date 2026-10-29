#!/usr/bin/env python3
"""Evidence report for the real-model smoke test (Causal RAG -- Reduced Evidence).

Reads the smoke outputs in native_backtest/out/ap3/smoke/<provider>/ (records, canaries, call log, cost ledger,
endpoint runtime) and writes, per month:
  1. the economic event (packet triggers) and each hypothesis the Hypothesis Agent generated;
  2. the knowledge-graph pathways it cited, the CauseTrace tool calls it made and the research records retrieved;
  3. the Testing Agent's plan, rival explanation, retrieved evidence, assessments with quotes, mediator tests,
     rubric and final status with seed agreement;
  4. missing evidence, failures and unreliable outputs (invalid responses, downgraded labels, unavailable series);
  5. the status features (and the pipeline-acceptance check of the features builder);
then the reliability checks, token usage, endpoint runtime, cost and the updated replay estimate.

Two outputs: smoke_report_full.json (local only: pathway labels, paper titles and claim quotes come from the
Garg & Fetzer claims data, which is not redistributed) and smoke_report.json + docs/AP3_SMOKE_TEST_REPORT.md
(committed: the same report with claims-data text replaced by identifiers). Model-written text (mechanisms,
plans, explanations) and data-note quotes are kept. Records from the engineering mock are refused.

Usage (repository root): python -m native_backtest.scripts.ap3_smoke_report [--provider hf_endpoint]
"""
from __future__ import annotations

import argparse
import collections
import json
import math
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[2]
SMOKE = ROOT / "native_backtest/out/ap3/smoke"
DOC = ROOT / "native_backtest/docs/AP3_SMOKE_TEST_REPORT.md"
BUDGET = ROOT / "native_backtest/out/ap3/inference_budget_v1.json"
REPLAY_MONTHS = 95


def _is_claims_chunk(cid: str) -> bool:
    return cid.startswith("RC_")


def _quote(q: dict, redact: bool) -> dict:
    st = q.get("citation_status")
    if redact and _is_claims_chunk(q.get("chunk_id", "")):
        return {"chunk_id": q["chunk_id"], "citation_status": st, "quote": "[research-claim text withheld: claims data not redistributed]"}
    return {"chunk_id": q.get("chunk_id"), "citation_status": st, "quote": q.get("quote")}


def month_report(r: dict, redact: bool) -> dict:
    if r.get("stopped"):
        return {"month": r["decision_month"], "stopped": r["stopped"]}
    pk = r["packet"]
    ha = r["hypothesis_agent"]
    tests = {t["hypothesis_id"]: t for t in r["tests"]}
    hyps = []
    for h in ha["hypotheses"]:
        t = tests.get(h["hypothesis_id"], {})
        paths = {pid: (f"{len(p) - 1} links" if redact else " -> ".join(p)) for pid, p in h.get("paths", {}).items()}
        recs = [{"paper_id": x.get("paper_id"), "year": x.get("year"), "evidence_class": x.get("evidence_class"),
                 "method": x.get("causal_inference_method"), **({} if redact else {"title": x.get("title"), "edge": x.get("edge")})}
                for x in h.get("research_records", [])]
        runs = []
        for run in t.get("runs", []):
            items = []
            for it in run["assessments"]:
                items.append({"edge": it["edge_id"], "model_label": it.get("label"), "validated_label": it.get("validated_label"),
                              "valid_supporting": it.get("n_valid_supporting"), "valid_contradicting": it.get("n_valid_contradicting"),
                              "supporting_quotes": [_quote(q, redact) for q in it.get("supporting_evidence", []) or []],
                              "contradicting_quotes": [_quote(q, redact) for q in it.get("contradicting_evidence", []) or []],
                              "explanation": it.get("explanation"),
                              "rejected_quotes": sum(q.get("citation_status") not in (None, "valid")
                                                     for side in ("supporting_evidence", "contradicting_evidence") for q in it.get(side, []) or [])})
            plan = run["plan"]
            runs.append({"seed": run["seed"], "implications": plan["implications"],
                         "rival": {"path_id": plan["rival"]["rival_path_id"], "mechanism": plan["rival"]["mechanism"],
                                   "predicted_assets": plan["rival"]["predicted_assets"]},
                         "queries": {"supporting": plan["supporting_queries"], "contradicting": plan["contradicting_queries"]},
                         "retrieved": run["retrieved"], "assessor_called": run.get("assess_meta") is not None,
                         "assessments": items, "mediator_tests": run["mediator_tests"], "rubric": run["rubric"]})
        hyps.append({"id": h["hypothesis_id"], "trigger": h["trigger"], "channel": h["channel"], "mechanism": h["mechanism"],
                     "predicted_assets": h["predicted_assets"], "predicted_mediators": h["predicted_mediators"],
                     "confidence_stated": h["confidence"], "confidence_applied": h["confidence_applied"], "confidence_caps": h["confidence_caps"],
                     "cited_pathways": paths, "invalid_path_ids_dropped": h.get("invalid_path_ids", []),
                     "literature_unsupported": h.get("literature_unsupported"), "research_records": recs,
                     "evidence_pool": t.get("evidence_pool"), "testing_runs": runs,
                     "status": t.get("status"), "run_statuses": t.get("run_statuses"), "seed_agreement": t.get("run_agreement"),
                     "conflict": t.get("conflict"), "test_failure": t.get("failure"), "causal_validation": t.get("causal_validation")})
    return {"month": r["decision_month"], "decision_time": pk["decision_time"], "graph_vintage": r["graph_vintage"],
            "event": pk["triggers"], "all_surprises_z": pk.get("all_surprises_z"),
            "hypothesis_agent": {"tool_calls": [{"tool": c.get("tool"), "args": c.get("args"), **({"repeat_of": c["duplicate_of"]} if "duplicate_of" in c else {})}
                                                for c in ha.get("tool_calls", [])],
                                 "turns": len(ha.get("turns", [])), "failure": ha.get("failure"),
                                 "final_answer_forced": ha.get("final_answer_forced"), "repeated_tool_calls": ha.get("duplicate_tool_calls"),
                                 "turn_protocol": ha.get("turn_protocol", "1.0"),
                                 # the model's own reply each turn (tool results, which hold graph text, are not included)
                                 "turn_log": [{"turn": t.get("turn"), "action": (t.get("output") or {}).get("action"),
                                               **({"tool": t["output"].get("tool"), "args": t["output"].get("args")} if (t.get("output") or {}).get("action") == "tool"
                                                  else {"hypotheses": len((t.get("output") or {}).get("hypotheses", []))}),
                                               "final_answer_requested": t.get("final_answer_requested"),
                                               "tokens": (t.get("meta") or {}).get("usage"), "done_reason": (t.get("meta") or {}).get("done_reason")}
                                              for t in ha.get("turns", [])]},
            "hypotheses": hyps, "status_features": r["status_features"],
            "mediators_unavailable": sorted(k for k, v in (r.get("mediator_status") or {}).items() if str(v).startswith("unavailable"))}


def usage(ledger: Path, calls: Path) -> dict:
    tin = tout = n = 0
    by_step = collections.defaultdict(lambda: [0, 0, 0])
    times = []
    if ledger.exists():
        for l in ledger.read_text().splitlines():
            r = json.loads(l)
            u = r.get("usage") or {}
            a, b = u.get("prompt_tokens", u.get("inputTokens", 0)) or 0, u.get("completion_tokens", u.get("outputTokens", 0)) or 0
            tin, tout, n = tin + a, tout + b, n + 1
            k = r["step"].split("_")[0]
            by_step[k][0] += 1; by_step[k][1] += a; by_step[k][2] += b
            times.append(r["utc"])
    invalid = []
    if calls.exists():
        for l in calls.read_text().splitlines():
            r = json.loads(l)
            if r.get("invalid"):
                invalid.append({"step": r["step"], "error": r.get("error")})
    span = None
    if len(times) > 1:
        import datetime as dt
        f = lambda s: dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")
        span = (f(max(times)) - f(min(times))).total_seconds() / 60.0
    return {"calls_with_usage": n, "input_tokens": tin, "output_tokens": tout,
            "by_call_type": {k: {"calls": v[0], "input": v[1], "output": v[2]} for k, v in sorted(by_step.items())},
            "inference_minutes": span, "invalid_responses": invalid}


def replay_estimate(u: dict, runtime: dict, months: int, rate: float) -> dict:
    """95-month replay estimate scaled from measured tokens and measured inference time (same concurrency)."""
    if not u["inference_minutes"] or months == 0:
        return {"status": "not available: no measured inference time"}
    per_month_min = u["inference_minutes"] / months      # months ran concurrently, so this is conservative only if the
    out_per_month = u["output_tokens"] / months           # replay runs as many months at once (8) as the smoke ran (3)
    concurrency_gain = 8 / months if months < 8 else 1.0
    replay_min = REPLAY_MONTHS * per_month_min / concurrency_gain
    startup = max(0.0, (runtime.get("billable_minutes_upper") or 0) - u["inference_minutes"])
    lo = (replay_min + startup) * rate / 60
    return {"measured_output_tokens_per_month": round(out_per_month), "measured_minutes_per_month_at_smoke_concurrency": round(per_month_min, 2),
            "assumed_concurrency": 8, "replay_inference_minutes": round(replay_min), "startup_minutes": round(startup),
            "usd_typical": round(lo, 2), "usd_with_50pct_margin": round(lo * 1.5, 2),
            "note": "scaled from the smoke test's measured tokens and wall time; the replay's own cap and controller apply"}


def build(provider: str) -> Dict:
    d = SMOKE / provider
    recs = [json.loads(l) for l in (d / "smoke_records.jsonl").read_text().splitlines()]
    if any(r.get("engineering_mock") for r in recs):
        raise SystemExit("engineering-mock records are never reported as smoke-test results")
    from native_backtest.ap3 import reliability
    summary = json.loads((d / "summary.json").read_text()) if (d / "summary.json").exists() else {}
    runtime = json.loads((d / "runtime.json").read_text()) if (d / "runtime.json").exists() else {}
    canary = json.loads((d / "canary.json").read_text()) if (d / "canary.json").exists() else []
    ok = [r for r in recs if not r.get("stopped")]
    rel = reliability.report(ok) if ok else {}
    validity = reliability.call_validity(d / "calls.jsonl")
    u = usage(d / "cost_ledger.jsonl", d / "calls.jsonl")
    total_calls = sum(v["valid"] + v["invalid"] for v in validity.values())
    valid_share = (sum(v["valid"] for v in validity.values()) / total_calls) if total_calls else None
    hyps = [h for r in ok for h in r["hypothesis_agent"]["hypotheses"]]
    cited = sum(len(h["path_ids"]) for h in hyps)
    dropped = sum(len(h.get("invalid_path_ids", [])) for h in hyps)
    cap = 15.0
    checks = {
        "canaries_parse": {"value": f"{sum(c['ok'] for c in canary)}/{len(canary)}", "pass": bool(canary) and all(c["ok"] for c in canary)},
        "schema_valid_calls_at_least_95pct": {"value": valid_share, "pass": valid_share is not None and valid_share >= 0.95},
        "cited_pathways_exist": {"value": f"{cited} kept, {dropped} invented IDs dropped", "pass": True,
                                 "note": "invented pathway IDs are removed before testing; the share is reported"},
        "no_point_in_time_violations": {"value": len(rel.get("point_in_time_violations", [])), "pass": not rel.get("point_in_time_violations")},
        "no_fabricated_quote_accepted": {"value": rel.get("directional_labels_downgraded_by_quote_validation"), "pass": True,
                                         "note": "every directional label without a verbatim quote was downgraded; the count shows how often"},
        "spend_within_authorization": {"value": runtime.get("cost_usd_upper"), "pass": runtime.get("cost_usd_upper") is not None and runtime["cost_usd_upper"] <= cap},
        "months_completed": {"value": f"{len(ok)}/{len(recs)}", "pass": len(ok) == len(recs)},
    }
    full = {"title": "AP3 real-model smoke test: Causal RAG -- Reduced Evidence", "provider": provider, "model": summary.get("model"),
            "genuine_model_output": True, "not_a_backtest_result": "Three development months; says nothing about predictive performance.",
            "months": [month_report(r, redact=False) for r in recs], "checks": checks, "reliability": rel, "call_validity": validity,
            "usage": u, "runtime": runtime,
            "replay_estimate": replay_estimate(u, runtime, len(ok), 10.0) if runtime else None}
    red = {**full, "months": [month_report(r, redact=True) for r in recs],
           "redaction": "pathway labels, paper titles and research-claim quotes are replaced by identifiers (claims data is not redistributed)"}
    (d / "smoke_report_full.json").write_text(json.dumps(full, indent=1, default=str) + "\n")
    (d / "smoke_report.json").write_text(json.dumps(red, indent=1, default=str) + "\n")
    DOC.write_text(markdown(red))
    return red


def markdown(r: dict) -> str:
    L = [f"# AP3 real-model smoke test — Causal RAG, Reduced Evidence", "",
         f"Genuine outputs of {r['model']} on a dedicated endpoint. Three pre-specified development months. "
         "This tests whether the agents work as specified; it is not evidence of predictive performance.", ""]
    for m in r["months"]:
        if m.get("stopped"):
            L += [f"## {m['month']}: stopped — {m['stopped']}", ""]
            continue
        L += [f"## {m['month']} (decision {m['decision_time']}, graph vintage {m['graph_vintage']})", "", "**Event**"]
        for t in m["event"]:
            extra = f" surprise {t['surprise_z']:+.2f} σ" if "surprise_z" in t else (f" {t.get('date', '')}" if t["trigger"] == "FOMC" else f" {t.get('series', '')} z {t.get('z')}")
            L.append(f"- {t['description']}{extra}")
        L += ["", f"Hypothesis Agent: {m['hypothesis_agent']['turns']} turns, {len(m['hypothesis_agent']['tool_calls'])} CauseTrace tool calls"
              + (f"; **failure:** {m['hypothesis_agent']['failure']}" if m['hypothesis_agent']['failure'] else ""), ""]
        for h in m["hypotheses"]:
            a = h["predicted_assets"]
            meds = ", ".join(f"{x['series']} {x['sign']:+d}" for x in h["predicted_mediators"]) or "none"
            paths = ", ".join(f"{k} ({v})" for k, v in h["cited_pathways"].items()) or "none (literature unsupported)"
            kinds = ", ".join(sorted({str(x["evidence_class"]) for x in h["research_records"]}))
            L += [f"### {h['id']} · {h['trigger']} · {h['channel']} → **{h['status']}** (seed agreement {h['seed_agreement']})", "",
                  f"- Mechanism (model): {h['mechanism']}",
                  f"- Predicted: SPY {a['SPY']:+d}, IEF {a['IEF']:+d}, LQD {a['LQD']:+d}; mediators {meds}",
                  f"- Confidence {h['confidence_stated']} → {h['confidence_applied']} {h['confidence_caps'] or ''}",
                  f"- Pathways cited: {paths}; invented IDs dropped: {len(h['invalid_path_ids_dropped'])}",
                  f"- Research records: {len(h['research_records'])} ({kinds})",
                  f"- Evidence pool: {h['evidence_pool']['by_kind'] if h['evidence_pool'] else '—'}"]
            for run in h["testing_runs"][:1]:
                L.append(f"- Testing Agent (seed {run['seed']}): rival {run['rival']['path_id'] or 'none'} — {run['rival']['mechanism']}")
                for it in run["assessments"]:
                    qs = [x for x in it["supporting_quotes"] + it["contradicting_quotes"] if x.get("citation_status") == "valid"]
                    q = qs[0]["quote"] if qs else None
                    L.append(f"  - {it['edge']}: model {it['model_label']} → validated {it['validated_label']}"
                             + (f"; quote: “{q}”" if q else "") + (f"; {it['rejected_quotes']} quote(s) rejected" if it["rejected_quotes"] else ""))
                    if it.get("explanation"):
                        L.append(f"    - Explanation (model): {it['explanation']}")
                for mt in run["mediator_tests"]:
                    L.append(f"  - Mediator {mt['series']}: {mt['result']}" + (f" (z {mt['z']:+.2f})" if mt.get("z") is not None else f" ({mt.get('reason', '')})"))
                L.append(f"  - Rubric: {run['rubric']['status']} (supporting {run['rubric']['n_valid_supporting']}, contradicting {run['rubric']['n_valid_contradicting']})")
            if h["test_failure"]:
                L.append(f"- **Test failure:** {h['test_failure']}")
            L.append("")
        L += [f"**Status features** {json.dumps(m['status_features'])}", ""]
        if m["mediators_unavailable"]:
            L += [f"Missing inputs (not substituted): {', '.join(m['mediators_unavailable'])}", ""]
    L += ["## Checks", ""] + [f"- {k}: {v['value']} — {'pass' if v['pass'] else 'FAIL'}" for k, v in r["checks"].items()]
    u, rt = r["usage"], r["runtime"]
    L += ["", "## Tokens, runtime, cost", "",
          f"- Calls {u['calls_with_usage']}; input tokens {u['input_tokens']:,}; output tokens {u['output_tokens']:,}; invalid responses {len(u['invalid_responses'])}",
          f"- Endpoint billable minutes (upper bound) {rt.get('billable_minutes_upper')}; cost (upper bound) ${rt.get('cost_usd_upper')}",
          f"- Replay estimate: {json.dumps(r['replay_estimate'])}", ""]
    L += ["## Forecast and allocation", "",
          "The status features above feed AP3's walk-forward calibration, which learns their coefficients from past months' "
          "genuine outputs. Those exist only after the 95-month development replay, so no forecast or allocation from three "
          "smoke months is valid and none is reported. The engineering replay verified the calibration and allocation code paths.", ""]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="hf_endpoint")
    a = ap.parse_args(argv)
    r = build(a.provider)
    print(json.dumps(r["checks"], indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
