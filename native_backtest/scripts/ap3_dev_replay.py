#!/usr/bin/env python3
"""AP3 development replay for one Causal RAG version: agents -> status features -> calibration -> allocation.

Runs the 95 AP3 development decisions 2015-02..2022-12 on the frozen v2 event packets:

  Hypothesis Agent (graph-informed, CauseTrace tools) -> Causal RAG research records -> Testing Agent
  (plan, balanced retrieval from the version's evidence pool, native assessor with quote validation,
  mediator tests, rubric, three seeds) -> status features F^S, F^C, F^I

then, walk-forward with labels through t-2 only, AP3's calibration layer (Ridge on the 8 macro surprises
plus the three status features), the G4c reliability checks, and Black-Litterman allocation with AP3's own
Omega, for the development scoring months 2019-03..2022-12. The protected window (2023-01 on) is refused by
the evaluator's lock before anything is read.

Versions (native_backtest/ap3/variants_v1.json): reduced_evidence | historical_documents. They differ only in
the Testing Agent's evidence pool.

Providers
  engineering_mock  code-generated responses; checks the whole pipeline end to end. Outputs go to
                    out/ap3/engineering_replay/<variant>/, are marked engineering_mock, carry no market
                    information, and are never scored or shown as performance.
  hf_endpoint       Llama 3.1 70B Instruct on the dedicated endpoint (pinned revision) } paid: refused unless
  bedrock           Llama 3.1 70B Instruct on Amazon Bedrock                          } approval record B,
                    AP3_ALLOW_PAID_INFERENCE=1, secrets and a hard cap are all present.

Resumable: each month's agent record is stored as soon as it exists (hashed, before any label is read);
a rerun skips months already recorded for the same packet, provider and model.

Usage (repository root):
  python -m native_backtest.scripts.ap3_dev_replay --variant reduced_evidence --provider engineering_mock
  python -m native_backtest.scripts.ap3_dev_replay --variant reduced_evidence --provider hf_endpoint          # plan only
  python -m native_backtest.scripts.ap3_dev_replay --variant reduced_evidence --provider hf_endpoint --execute
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

from native_backtest.ap3 import calibration, engineering_mock, evidence_pool, mediator_data, protocol, reliability, runner
from native_backtest.ap3 import llm_client as L
from native_backtest.ap3.allocation import omega_from_development_errors, weights_for_months
from native_backtest.ap3.encoder import ASSETS
from native_backtest.ap3.graph_vintage import build_vintage, load_concepts
from native_backtest.framework.lock import assert_scoring_allowed
from native_backtest.framework.market import decision_time_iso, load_config, load_market, months_between

ROOT = Path(__file__).resolve().parents[2]
SMOKE = ROOT / "native_backtest/config/ap3_smoke_test_v1.json"
LIBS = ROOT / "native_backtest/data/_external/ap3_libraries"
CHUNKS = ROOT / "native_backtest/data/_corpus/chunks.jsonl"
CORPUS_CHECKS = ROOT / "native_backtest/out/ap3/corpus_checks_v1.json"
APPROVAL_B = ROOT / "native_backtest/config/approvals/ap3_inference_approval_B.json"
PANEL = ROOT / "stage2/data/model_scoring_panel_E4_meanrule.csv"
PANEL_SHA = "459bef989561aa66f32eccc6d0758ff15b8d50fbd3cdea51b5eced8f0fa456b1"
SURPRISE_COLS = {"NFP": "nfp_z", "RETAIL_SALES": "retail_sales_z", "INDUSTRIAL_PRODUCTION": "industrial_production_z",
                 "ISM_MANUFACTURING": "ism_manufacturing_z", "CPI": "cpi_z", "CORE_CPI": "core_cpi_z", "PPI": "ppi_z", "AHE": "ahe_z"}
AGENT_MONTHS = ("2015-02", "2022-12")
SCORE_MONTHS = ("2019-03", "2022-12")
PROVIDERS = {"hf_endpoint": L.HFEndpointProvider, "bedrock": L.BedrockProvider}
FREE_PROVIDERS = {"ollama": L.OllamaProvider}     # free local inference (qwen3:4b, documented model substitution)
ENV = {"bedrock": ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"), "hf_endpoint": ("HF_TOKEN", "AP3_HF_ENDPOINT_URL", "AP3_MODEL_REVISION")}


class NotApproved(RuntimeError):
    pass


def out_dir(variant: str, provider: str) -> Path:
    if provider == "engineering_mock":
        return ROOT / "native_backtest/out/ap3/engineering_replay" / variant
    return ROOT / "native_backtest/out/ap3/dev_replay" / variant / provider


def load_packets() -> Dict[str, dict]:
    cfg = json.loads(SMOKE.read_text())["packets"]
    p = ROOT / cfg["file"]
    if hashlib.sha256(p.read_bytes()).hexdigest() != cfg["sha256"]:
        raise SystemExit("frozen v2 packets do not match their pinned SHA-256")
    return {json.loads(l)["decision_month"]: json.loads(l) for l in p.read_text().splitlines()}


def load_corpus(allow_incomplete: bool) -> List[dict]:
    """Official-document chunks for the historical-documents version. The corpus must have passed its checks;
    an incomplete corpus is accepted only for engineering runs (allow_incomplete)."""
    if not CHUNKS.exists() or not CORPUS_CHECKS.exists():
        raise SystemExit("official-document corpus not built: run ap3_corpus_fetch, then ap3_corpus_import --from-fetch-log")
    checks = json.loads(CORPUS_CHECKS.read_text())["summary"]
    if not checks["pass"] and not allow_incomplete:
        raise SystemExit(f"corpus checks have not passed (missing families: {checks.get('families_missing')}); "
                         "the historical-documents version runs only on a complete, validated corpus")
    return [json.loads(l) for l in CHUNKS.read_text().splitlines()]


def prerequisites_b(provider: str, variant: str) -> List[str]:
    missing = []
    if L.paid_budget_usd() <= 0:
        missing.append("budget: the project budget for paid inference is $0 (config/budget_v1.json)")
    if not APPROVAL_B.exists():
        missing.append(f"approval record {APPROVAL_B.relative_to(ROOT)} (written only after explicit approval of stage B)")
    else:
        a = json.loads(APPROVAL_B.read_text())
        if a.get("stage") != "B" or a.get("provider") != provider:
            missing.append(f"approval record is for stage {a.get('stage')} / {a.get('provider')}, not B / {provider}")
        if variant not in a.get("variants", []):
            missing.append(f"approval record does not cover the {variant} version")
        if not a.get("cap_usd"):
            missing.append("approval record has no spending cap")
    if os.environ.get("AP3_ALLOW_PAID_INFERENCE") != "1":
        missing.append("AP3_ALLOW_PAID_INFERENCE=1")
    missing += [f"environment secret {v}" for v in ENV[provider] if not os.environ.get(v)]
    return missing


def make_client(provider: str, variant: str, out: Path) -> L.LLMClient:
    if provider == "engineering_mock":
        return L.LLMClient(L.EngineeringMockProvider(engineering_mock.responder), out / "cache", out / "calls.jsonl",
                           f"ap3-dev-replay {variant} (ENGINEERING MOCK)")
    if provider in FREE_PROVIDERS:
        prov = FREE_PROVIDERS[provider]()
        (out / "provenance.json").write_text(json.dumps(prov.verify(), indent=1, default=str) + "\n")
        return L.LLMClient(prov, out / "cache", out / "calls.jsonl", f"ap3-dev-replay {variant} ({provider}, free)")
    a = json.loads(APPROVAL_B.read_text())
    smoke = json.loads(SMOKE.read_text())
    pricing = dict(smoke["providers"][provider]["pricing_for_guard"])
    state = ROOT / "native_backtest/out/ap3/smoke/hf_endpoint/endpoint.json"
    if pricing["mode"] == "hourly" and state.exists():
        pricing["started_utc"] = json.loads(state.read_text())["created_utc"]
    guard = L.CostGuard(float(a["cap_usd"]), out / "cost_ledger.jsonl", pricing)
    return L.LLMClient(PROVIDERS[provider](), out / "cache", out / "calls.jsonl", f"ap3-dev-replay {variant} ({provider})", guard=guard)


def run_agents(variant: str, provider: str, months: List[str], workers: int, allow_incomplete_corpus: bool,
               deadline: float | None = None, max_parallel_tests: int = 1) -> Dict[str, dict]:
    """Runs (or resumes) the months. A month already recorded for the same packet, model and version is reused; with
    a deadline (epoch seconds) no new month starts after it, and months not started are simply absent."""
    out = out_dir(variant, provider)
    (out / "records").mkdir(parents=True, exist_ok=True)
    client = make_client(provider, variant, out)
    packets = load_packets()
    concepts, limits = load_concepts(), runner.load_limits()
    spec = evidence_pool.load_variants()["variants"][variant]
    inventory = spec.get("mediator_inventory", "v2")
    store, med_status = mediator_data.load_store(include_pending_substitutes=True, inventory=inventory)
    labels = mediator_data.labels(inventory)
    if inventory != "v2":          # sensitivity variant: the agents are told which series is a proxy
        for m, pk in packets.items():
            ms = dict(pk.get("mediator_series", {}))
            ms.update({k: labels[k] for k in ms if k in labels and labels[k].startswith("PROXY")})
            packets[m] = {**pk, "mediator_series": ms}
    corpus_chunks = load_corpus(allow_incomplete_corpus) if variant == "historical_documents" else None
    pool = evidence_pool.EvidencePool(variant, store, labels, {k: v["label"] for k, v in concepts["triggers"].items()}, limits, corpus_chunks)
    vintages: Dict[int, object] = {}
    libraries: Dict[int, dict] = {}
    for m in months:
        y = int(m[:4])
        if y not in vintages:
            vintages[y] = build_vintage(y - 1, concepts)
            libraries[y] = json.loads((LIBS / f"library_v1.0_vintage{y - 1}.json").read_text())

    def packet_sha(m):
        return hashlib.sha256(json.dumps(packets[m], sort_keys=True).encode()).hexdigest()

    fp = protocol.fingerprint()

    def one(m):
        f = out / "records" / f"{m}.json"
        if f.exists():     # reused only if made from the same packet, model, variant and agent protocol
            r = json.loads(f.read_text())
            if (r.get("packet_sha256") == packet_sha(m) and r.get("model") == client.provider.model and r.get("variant") == variant
                    and r.get("protocol_fingerprint") == fp):
                return r
        if deadline is not None and time.time() > deadline:
            return None
        y = int(m[:4])
        rec = runner.run_month(client, packets[m], vintages[y], libraries[y], [], store, pd.Timestamp(m + "-01"), limits, evidence=pool,
                               max_parallel_tests=max_parallel_tests)
        rec["packet_sha256"] = packet_sha(m)
        rec["protocol_fingerprint"] = fp
        rec["mediator_status"] = med_status
        f.write_text(json.dumps(rec, sort_keys=True, default=str) + "\n")
        return rec

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        recs = list(ex.map(one, months))
    return {r["decision_month"]: r for r in recs if r is not None}


def features_frame(records: Dict[str, dict]) -> pd.DataFrame:
    if hashlib.sha256(PANEL.read_bytes()).hexdigest() != PANEL_SHA:
        raise SystemExit("macro panel does not match its pinned SHA-256")
    panel = pd.read_csv(PANEL).set_index("month")
    rows = []
    for m, r in sorted(records.items()):
        for a in ASSETS:
            row = {"month": pd.Period(m, "M"), "asset": a}
            for c in calibration.MACRO:          # the AP1 panel's frozen surprise columns, unchanged
                v = panel.loc[m, c]
                # Stage 2 no-release rule: a missing surprise stays missing (scaled to 0 inside the fit). The only
                # missing value in 2015-02..2022-12 is 2019-01 retail sales (shutdown; no January release).
                if pd.isna(v) and not (m == "2019-01" and c == "retail_sales_z"):
                    raise SystemExit(f"macro surprise {c} missing for {m}")
                row[c] = float(v)
            row.update(r["status_features"][a])
            rows.append(row)
    return pd.DataFrame(rows).set_index(["month", "asset"])


def labels_frame(months: List[pd.Period]) -> pd.DataFrame:
    import stage2_backtest as s2
    mk = load_market(load_config())
    tg = s2.build_targets(mk.prices, mk.calendar, mk.decision_dates, mk.dtb4wk, months)
    lab = tg.pivot(index="decision_month", columns="asset", values="actual_excess_return")[list(ASSETS)]
    lab.index = pd.PeriodIndex(lab.index, freq="M")
    return lab.sort_index()


def downstream(records: Dict[str, dict], out: Path, mock: bool) -> dict:
    """Calibration (walk-forward), G4c checks and allocation for the development scoring months.
    For engineering-mock records this only checks that the plumbing runs; nothing is reported as performance."""
    cfg = load_config()
    score = months_between(*SCORE_MONTHS)
    assert_scoring_allowed(score, protected_start=cfg["windows"]["protected"][0])
    feats = features_frame(records)
    if not set(calibration.MACRO) <= set(feats.columns):
        raise SystemExit("calibration columns missing")
    labels = labels_frame(sorted(set(feats.index.get_level_values("month"))))
    pred = calibration.walk_forward(feats, labels, score)
    checks = {"intercept_only_share": calibration.intercept_only_share(pred),
              "sign_stability": calibration.sign_stability(pred),
              "calibration_slope": calibration.calibration_slope(pred, labels)}
    omega = omega_from_development_errors(pred, labels, [str(m) for m in score])
    w = weights_for_months(pred, labels, [str(m) for m in score], omega)
    tag = "ENGINEERING MOCK - plumbing check only, not a result" if mock else "development (permitted window)"
    res = {"kind": tag, "score_months": [str(score[0]), str(score[-1])], "n_predictions": int(len(pred)),
           "g4c_checks": checks, "omega_diag": {a: float(omega[i]) for i, a in enumerate(ASSETS)},
           "weights_sum_ok": all(abs(sum(v.values()) - 1) < 1e-8 for v in w.values())}
    if not mock:
        pred.to_csv(out / "predictions.csv", index=False)
        (out / "weights.json").write_text(json.dumps(w, indent=1) + "\n")
        res["placebo"] = calibration.permutation_placebo(feats, labels, score)
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=sorted(evidence_pool.load_variants()["variants"]), required=True)
    ap.add_argument("--provider", choices=["engineering_mock", *sorted(FREE_PROVIDERS), *sorted(PROVIDERS)], required=True)
    ap.add_argument("--execute", action="store_true", help="paid providers: run (default: plan only)")
    ap.add_argument("--months", default=",".join(AGENT_MONTHS), help="first,last agent month")
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--allow-incomplete-corpus", action="store_true", help="engineering runs only")
    a = ap.parse_args(argv)
    cfg = load_config()
    months = [str(m) for m in months_between(*a.months.split(","))]
    assert_scoring_allowed([pd.Period(m, "M") for m in months], protected_start=cfg["windows"]["protected"][0])
    mock = a.provider == "engineering_mock"
    if a.allow_incomplete_corpus and not mock:
        raise SystemExit("--allow-incomplete-corpus is for engineering runs only")
    if not mock and a.provider not in FREE_PROVIDERS:
        missing = prerequisites_b(a.provider, a.variant)
        print(json.dumps({"variant": a.variant, "provider": a.provider, "months": [months[0], months[-1], len(months)],
                          "prerequisites_missing": missing, "will_call_a_paid_model": bool(a.execute and not missing)}, indent=1))
        if not a.execute:
            return 0
        if missing:
            raise NotApproved("not running: " + "; ".join(missing))
    out = out_dir(a.variant, a.provider)
    recs = run_agents(a.variant, a.provider, months, a.workers or (1 if mock else 4), a.allow_incomplete_corpus)
    if any(r["engineering_mock"] != mock for r in recs.values()):
        raise SystemExit("record provenance does not match the provider")
    rel = reliability.report(list(recs.values()))
    summary = {"variant": a.variant, "variant_label": evidence_pool.load_variants()["variants"][a.variant]["label"],
               "provider": a.provider, "engineering_mock": mock, "months": len(recs),
               **({"corpus": "INCOMPLETE corpus allowed for this engineering run only"} if a.allow_incomplete_corpus else {}),
               "records_sha256": hashlib.sha256("".join(recs[m]["record_sha256"] for m in sorted(recs)).encode()).hexdigest(),
               "testing_agent_reliability": rel}
    if len(recs) == len(months_between(*AGENT_MONTHS)):
        summary["downstream"] = downstream(recs, out, mock)
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "testing_agent_reliability"}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
