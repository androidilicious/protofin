#!/usr/bin/env python3
"""AP3 approval stage A: canary prompts and a 3-month smoke test on real Llama 3.1 70B Instruct.

Default is --plan: it prints the plan, the cost estimate and which prerequisites are missing, and makes
no call. --execute runs only when all of these hold:
  - native_backtest/config/approvals/ap3_inference_approval_A.json exists, names the provider, and its cap
    does not exceed the configured cap (it is written only after the project lead's explicit approval);
  - AP3_ALLOW_PAID_INFERENCE=1 and the provider's credentials are set as environment secrets;
  - the provider is a real model (mock providers are refused: this folder holds real outputs only).
A CostGuard stops the run before any call that could take spending past the cap.

Outputs (native_backtest/out/ap3/smoke/<provider>/): canary.json, smoke_records.jsonl, cost_ledger.jsonl,
calls.jsonl, summary.json. Smoke records are not decision records and are never scored.

Usage (repository root):
  python -m native_backtest.scripts.ap3_smoke_test --provider bedrock            # plan only
  python -m native_backtest.scripts.ap3_smoke_test --provider bedrock --execute  # after approval
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import pandas as pd

from native_backtest.ap3 import llm_client as L

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "native_backtest/config/ap3_smoke_test_v1.json"
LIBS = ROOT / "native_backtest/data/_external/ap3_libraries"
OUT = ROOT / "native_backtest/out/ap3/smoke"
PROVIDERS = {"bedrock": L.BedrockProvider, "hf_endpoint": L.HFEndpointProvider}
ENV = {"bedrock": ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"), "hf_endpoint": ("HF_TOKEN", "AP3_HF_ENDPOINT_URL", "AP3_MODEL_REVISION")}


class NotApproved(RuntimeError):
    pass


def load_config() -> dict:
    return json.loads(CONFIG.read_text())


def cap(cfg: dict, provider: str) -> float:
    """Stage-A spending cap for the provider (provider-level cap if set, else the global one)."""
    return float(cfg["providers"][provider].get("cap_usd", cfg["cap_usd"]))


def prerequisites(cfg: dict, provider: str) -> list:
    """Every reason the paid run may not start. Empty means it may."""
    missing = []
    ap = ROOT / cfg["approval_record"]
    if not ap.exists():
        missing.append(f"approval record {cfg['approval_record']} (written only after explicit approval)")
    else:
        a = json.loads(ap.read_text())
        if a.get("stage") != "A" or a.get("provider") != provider:
            missing.append(f"approval record is for stage {a.get('stage')} / provider {a.get('provider')}, not A / {provider}")
        if float(a.get("cap_usd", 1e9)) > cap(cfg, provider):
            missing.append("approved cap exceeds the configured cap")
    if os.environ.get("AP3_ALLOW_PAID_INFERENCE") != "1":
        missing.append("AP3_ALLOW_PAID_INFERENCE=1")
    missing += [f"environment secret {v}" for v in ENV[provider] if not os.environ.get(v)]
    p = cfg["providers"][provider]["pricing_for_guard"]
    if p["mode"] == "hourly" and "<" in p.get("started_utc", "<"):
        missing.append("endpoint start time (pricing_for_guard.started_utc)")
    pk = ROOT / cfg["packets"]["file"]
    if not pk.exists() or hashlib.sha256(pk.read_bytes()).hexdigest() != cfg["packets"]["sha256"]:
        missing.append("v2 packets matching their SHA-256")
    years = {int(m[:4]) for m in cfg["months"]}
    missing += [f"graph library for {y}" for y in sorted(years) if not (LIBS / f"library_v1.0_vintage{y - 1}.json").exists()]
    return missing


def estimate(cfg: dict, provider: str) -> dict:
    budget = json.loads((ROOT / "native_backtest/out/ap3/inference_budget_v1.json").read_text())
    p = cfg["providers"][provider]["pricing_for_guard"]
    txt = json.dumps(budget)
    out = {"months": len(cfg["months"]), "canary_calls": len(cfg["canary"]), "cap_usd": cap(cfg, provider), "pricing_for_guard": p}
    if p["mode"] == "tokens":
        per = budget["per_month"]
        out["per_month"] = per
        out["stages_from_budget"] = {k: budget["stages"][k] for k in ("1_connectivity_and_canary", "2_smoke_test_3_months") if k in budget["stages"]}
        out["note"] = "token estimate from the inference budget (typical and upper scenarios); the guard enforces the cap on measured usage"
    else:
        out["note"] = f"billed by the hour: the cap allows {cap(cfg, provider) / p['usd_per_hour'] * 60:.0f} minutes of endpoint time including start-up"
    out["budget_file_sha256"] = hashlib.sha256(txt.encode()).hexdigest()
    return out


def run(provider: str, cfg: dict) -> dict:
    from native_backtest.ap3 import mediator_data, runner
    from native_backtest.ap3.graph_vintage import build_vintage, load_concepts

    prov = PROVIDERS[provider]()
    if getattr(prov, "is_mock", False):
        raise NotApproved("the smoke folder holds real model outputs only")
    out = OUT / provider
    out.mkdir(parents=True, exist_ok=True)
    guard = L.CostGuard(cap(cfg, provider), out / "cost_ledger.jsonl", cfg["providers"][provider]["pricing_for_guard"])
    client = L.LLMClient(prov, out / "cache", out / "calls.jsonl", f"ap3-smoke-A ({provider})", max_calls=cfg["max_calls"], guard=guard)
    canary = []
    for c in cfg["canary"]:
        req = L.Request(step=f"canary_{c['id']}", system=c["system"], user=c["user"], schema=c["schema"], temperature=0.0, seed=0, max_tokens=60)
        try:
            obj, meta = client.complete_json(req)
            canary.append({"id": c["id"], "ok": True, "reply": obj, "cache_key": meta["cache_key"]})
        except L.BudgetExceeded:
            raise
        except Exception as e:  # a wrong or unparseable reply is a smoke-test finding, not a crash
            canary.append({"id": c["id"], "ok": False, "error": str(e)[:300]})
    (out / "canary.json").write_text(json.dumps(canary, indent=1) + "\n")
    packets = {json.loads(l)["decision_month"]: json.loads(l) for l in (ROOT / cfg["packets"]["file"]).read_text().splitlines()}
    concepts, limits = load_concepts(), runner.load_limits()
    store, _ = mediator_data.load_store(include_pending_substitutes=True, inventory="v2")
    recs = []
    with (out / "smoke_records.jsonl").open("w", encoding="utf-8") as f:
        for m in cfg["months"]:
            y = int(m[:4])
            lib = json.loads((LIBS / f"library_v1.0_vintage{y - 1}.json").read_text())
            rec = runner.run_month(client, packets[m], build_vintage(y - 1, concepts), lib, [], store, pd.Timestamp(m + "-01"), limits)
            assert rec["engineering_mock"] is False
            rec["record_kind"] = "smoke_test_not_a_decision_record"
            f.write(json.dumps(rec, sort_keys=True, default=str) + "\n")
            recs.append(rec)
    summary = {"provider": provider, "model": prov.model, "calls": client.calls, "spent_usd": round(guard.spent(), 4), "cap_usd": cap(cfg, provider),
               "canary_ok": sum(c["ok"] for c in canary), "months": cfg["months"],
               "hypotheses": {r["decision_month"]: len(r["hypothesis_agent"]["hypotheses"]) for r in recs}}
    (out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=sorted(PROVIDERS), required=True)
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config()
    missing = prerequisites(cfg, a.provider)
    plan = {"stage": "A", "provider": a.provider, "status": cfg["status"], "estimate": estimate(cfg, a.provider),
            "prerequisites_missing": missing, "will_call_a_paid_model": bool(a.execute and not missing)}
    print(json.dumps(plan, indent=1))
    if not a.execute:
        return 0
    if missing:
        raise NotApproved("not running: " + "; ".join(missing))
    print(json.dumps(run(a.provider, cfg), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
