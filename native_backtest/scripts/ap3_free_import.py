#!/usr/bin/env python3
"""Import the free qwen3:4b Causal RAG results from the results branch and evaluate them (pinned environment).

1. Reads the redacted results bundle from branch `ap3-qwen3-runs` (written by the free GPU notebook) into
   native_backtest/out/ap3/qwen3_runs/.
2. Validates it: genuine model outputs only (never the engineering mock), the pinned model, development months
   only (2015-02..2022-12; the protected window is refused), complete status features, and the record hash chain.
   An EXPLORATORY bundle (config/ap3_exploratory_mode_v1.json) is accepted with its failed gates intact: the
   evaluation then carries the exploratory banner, every decision record is marked, and nothing is presented as
   validated. The gates themselves and their thresholds are unchanged.
3. When all 95 months exist and gates G3b and G3a passed, or the bundle is exploratory: AP3's walk-forward calibration, G4c checks and
   Black-Litterman allocation for 2019-03..2022-12, decision records (out/decisions/AP3_qwen3_reduced_evidence.jsonl),
   and the shared evaluation on the same months as the Deterministic baseline and JEV: net CER and supporting
   metrics, the two Causal RAG contrasts, and the passive 60/40 reference. Labelled throughout as development
   diagnostics of a documented model substitution (qwen3:4b for Llama 3.1 70B).

Usage (repository root): python -m native_backtest.scripts.ap3_free_import [--from-dir <bundle dir>]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "native_backtest/out/ap3/qwen3_runs"
DECISIONS = ROOT / "native_backtest/out/decisions/AP3_qwen3_reduced_evidence.jsonl"
AGENT_MONTHS = ("2015-02", "2022-12")
BRANCH = "ap3-qwen3-runs"
MODEL = "qwen3:4b@359d7dd4bcda"
ASSETS = ("SPY", "IEF", "LQD")


class ImportError_(RuntimeError):
    pass


def fetch_branch() -> Path:
    tmp = Path(tempfile.mkdtemp())
    r = subprocess.run(["git", "fetch", "-q", "origin", f"{BRANCH}:refs/remotes/origin/{BRANCH}"], cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        raise ImportError_(f"results branch {BRANCH} not found: the free GPU notebook has not pushed results yet")
    arc = subprocess.run(["git", "archive", f"origin/{BRANCH}", "qwen3_runs"], cwd=ROOT, capture_output=True)
    if arc.returncode != 0:
        raise ImportError_("results branch has no qwen3_runs folder")
    subprocess.run(["tar", "-x", "-C", str(tmp)], input=arc.stdout, check=True)
    return tmp / "qwen3_runs"


def validate(src: Path) -> dict:
    from native_backtest.framework.market import months_between
    allowed = {str(m) for m in months_between("2015-02", "2022-12")}
    months = {}
    for f in sorted((src / "months").glob("*.json")):
        j = json.loads(f.read_text())
        m = j["month"]
        if m not in allowed:
            raise ImportError_(f"{m} is outside the development months (the protected window is never imported)")
        if j.get("engineering_mock") is not False or j.get("provider") != "ollama_local" or j.get("model") != MODEL:
            raise ImportError_(f"{m}: not a genuine output of the pinned model ({j.get('provider')}, {j.get('model')})")
        sf = j["status_features"]
        if set(sf) != set(ASSETS) or any(set(sf[a]) != {"F_S", "F_C", "F_I"} for a in ASSETS):
            raise ImportError_(f"{m}: incomplete status features")
        months[m] = j
    s = json.loads((src / "summary.json").read_text())
    chain = hashlib.sha256("".join(months[m]["record_sha256"] for m in sorted(months)).encode()).hexdigest()
    if chain != s["records_chain_sha256"]:
        raise ImportError_("record hash chain does not match the bundle summary")
    return {"months": months, "summary": s}


def coverage(months: dict, score_months: list) -> dict:
    """What the genuine outputs actually contain. A month whose agent failed keeps its failure marker and its
    zero status features (the existing failure policy); nothing is invented for it, and it is counted here."""
    agent_fail, no_hyp, tests, failed_tests, status = [], [], 0, 0, {}
    for m, j in sorted(months.items()):
        ha = j.get("hypothesis_agent") or {}
        if ha.get("failure"):
            agent_fail.append({"month": m, "failure": ha["failure"][:160]})
        hyps = j.get("hypotheses") or []
        if not hyps:
            no_hyp.append(m)
        for h in hyps:
            tests += 1
            if h.get("test_failure"):
                failed_tests += 1
            status[h.get("status")] = status.get(h.get("status"), 0) + 1
    scored = [m for m in score_months if m in months]
    usable = [m for m in scored if (months[m].get("hypotheses") or [])]
    return {"agent_months_present": len(months), "agent_months_expected": 95,
            "scored_months_present": len(scored), "scored_months_expected": len(score_months),
            "scored_months_with_at_least_one_hypothesis": len(usable),
            "scored_months_without_hypotheses": sorted(set(scored) - set(usable)),
            "months_with_agent_failure": agent_fail, "n_months_with_agent_failure": len(agent_fail),
            "tests": tests, "failed_tests": failed_tests, "status_counts": status,
            "note": ("A month without hypotheses still has a decision: the existing failure policy gives it zero status "
                     "features, so the allocator falls back to its prior. That is disclosed here, never hidden, and no "
                     "return is invented for any month.")}


def evaluate(months: dict, summary: dict, explor: bool = False) -> dict:
    """Calibration, allocation and the shared evaluation (development window only)."""
    from native_backtest.framework import benchmark as B
    from native_backtest.framework import metrics as M
    from native_backtest.framework.accounting import simulate_records, static_portfolio_records
    from native_backtest.framework.lock import assert_scoring_allowed
    from native_backtest.framework.market import decision_time_iso, load_config, load_market, months_between
    from native_backtest.framework.records import DecisionRecord, read_jsonl, write_jsonl
    from native_backtest.scripts import ap3_dev_replay as rp

    cfg = load_config()
    score = months_between(*rp.SCORE_MONTHS)
    assert_scoring_allowed(score, protected_start=cfg["windows"]["protected"][0])
    if explor:
        from native_backtest.ap3 import exploratory as X
        X.assert_development_only([str(m) for m in score], cfg["windows"]["protected"][0])
    out = BUNDLE / "evaluation"
    out.mkdir(parents=True, exist_ok=True)
    recs = {m: {"status_features": j["status_features"]} for m, j in months.items()}
    ds = rp.downstream(recs, out, mock=False)                  # writes predictions.csv and weights.json
    w = json.loads((out / "weights.json").read_text())
    pred = pd.read_csv(out / "predictions.csv")
    mk = load_market(cfg)
    dec = []
    for m in [str(x) for x in score]:
        day = mk.decision_dates[pd.Period(m, "M")]
        q = pred[pred["decision_month"] == m].set_index("asset")["prediction_excess_return"]
        dec.append(DecisionRecord(system_id="AP3", decision_month=m, decision_time=decision_time_iso(day), info_cutoff=decision_time_iso(day),
                                  universe=ASSETS, target_weights={a: float(w[m][a]) for a in ASSETS},
                                  generation={"mode": "live_native", "model": MODEL, "variant": "reduced_evidence",
                                              "model_substitution": "qwen3:4b for meta-llama/Llama-3.1-70B-Instruct (documented)",
                                              "records_chain_sha256": summary["records_chain_sha256"],
                                              **({"exploratory": True, "validated": False,
                                                  "gates_failed": sorted((summary.get("exploratory") or {}).get("gates_failed", {}))}
                                                 if explor else {})},
                                  forecast={"horizon_months": 1, "kind": "expected_excess_return_decimal", "values": {a: float(q[a]) for a in ASSETS}}))
    write_jsonl(dec, DECISIONS)
    cost = cfg["costs"]["cost_per_dollar_traded"]
    sims = {"AP3": simulate_records(dec, mk, score, cost_per_dollar=cost)}
    for s in ("AP1", "AP2B"):
        sel = [r for r in read_jsonl(ROOT / f"native_backtest/out/decisions/{s}.jsonl") if r.decision_month in {str(x) for x in score}]
        sims[s] = simulate_records(sel, mk, score, cost_per_dollar=cost)
    neutral = static_portfolio_records("AP3_NEUTRAL", cfg["systems"]["AP3"]["native_neutral_weights"], dec)
    sims["AP3_NEUTRAL"] = simulate_records(neutral, mk, score, cost_per_dollar=cost)
    bench = B.simulate(cfg, mk, score, dec)
    contrasts = {"AP3-AP1": M.paired_cer_contrast(sims["AP3"], sims["AP1"]), "AP3-AP2B": M.paired_cer_contrast(sims["AP3"], sims["AP2B"])}
    res = {"status": "DEVELOPMENT DIAGNOSTIC of a documented model substitution (qwen3:4b), not a protected historical result",
           "coverage": coverage(months, [str(m) for m in score]),
           "months": [str(score[0]), str(score[-1]), len(score)],
           "metrics": {"AP3": {**M.metrics(sims["AP3"]), "cumulative_return": B.cumulative_return(sims["AP3"])}},
           "vs_own_benchmark": M.paired_cer_contrast(sims["AP3"], sims["AP3_NEUTRAL"]),
           "primary_contrasts_development": contrasts,
           "passive_reference": {"vs_reference": B.relative(sims["AP3"], bench, cfg),
                                 "decomposition": B.decomposition(sims["AP3"], sims["AP3_NEUTRAL"], bench, cfg["metrics"]["cer_delta"])},
           "calibration": ds}
    if explor:
        from native_backtest.ap3 import exploratory as X
        res = X.stamp(res, (summary.get("gates") or {}), months=[str(m) for m in score], protected_start=cfg["windows"]["protected"][0])
        res["baseline_identity"] = X.load_mode()["baseline_identity"]
        res["frozen_for_reproduction"] = summary.get("frozen_for_reproduction") or X.freeze()
        res["status"] = X.STATUS
    sims["AP3"].to_csv(out / "AP3_common_matched_dev.csv", index=False)
    (out / "evaluation.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    return res


def main(argv=None) -> int:
    from native_backtest.ap3 import exploratory as X
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-dir", type=Path, help="a downloaded bundle folder instead of the results branch")
    a = ap.parse_args(argv)
    src = a.from_dir or fetch_branch()
    v = validate(src)
    if BUNDLE.exists():
        shutil.rmtree(BUNDLE)
    shutil.copytree(src, BUNDLE)
    s = v["summary"]
    gates = {g: x.get("pass") for g, x in s.get("gates", {}).items()}
    explor = X.is_exploratory(s)
    report = {"months": len(v["months"]), "gates": gates, "cost_usd": s.get("cost_usd"),
              "exploratory": bool(explor), "label": X.LABEL if explor else None}
    complete = len(v["months"]) == 95
    passed = bool(gates.get("G3b") and gates.get("G3a"))
    if complete and (passed or explor):
        res = evaluate(v["months"], s, explor=explor)
        report["evaluation"] = res["status"]
        report["coverage"] = res["coverage"]
    elif not complete:
        report["evaluation"] = (f"not run: {len(v['months'])} of 95 agent months present. The replay resumes where it "
                                "stopped; a partial set is never scored, because calibration needs the full history.")
    else:
        report["evaluation"] = ("not run: a reliability gate failed and this bundle does not carry the exploratory "
                                "banner. Re-run with --exploratory to produce a labelled diagnostic.")
    (BUNDLE / "import_report.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
