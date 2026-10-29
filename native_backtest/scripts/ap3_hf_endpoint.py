#!/usr/bin/env python3
"""Dedicated Hugging Face endpoint for AP3 (Llama 3.1 70B Instruct): plan, create, pause, delete.

Default is --plan: prints the exact endpoint configuration and the cost arithmetic, and contacts nothing.
--create, --pause and --delete call the Hugging Face API and are allowed only when:
  - native_backtest/config/approvals/ap3_inference_approval_A.json exists for provider hf_endpoint (written only
    after the project lead's explicit approval), and
  - HF_TOKEN is set as an environment secret (never in chat or git).
--create records the creation time in native_backtest/out/ap3/smoke/hf_endpoint/endpoint.json; the smoke runner's
cost guard counts every minute from that moment (initialisation is billed).

Safeguards, in order:
  1. CostGuard in the runner: stops before any call once elapsed time x hourly rate could pass the cap.
  2. The runner pauses the endpoint when it finishes, fails or hits the cap, and a watchdog thread pauses it at the
     cap even if a request hangs.
  3. The endpoint itself has min replicas 0 and scales to zero after 15 minutes without requests.

Usage (repository root):
  python -m native_backtest.scripts.ap3_hf_endpoint            # plan only
  python -m native_backtest.scripts.ap3_hf_endpoint --create   # after approval
  python -m native_backtest.scripts.ap3_hf_endpoint --pause | --delete
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "native_backtest/config/ap3_smoke_test_v1.json"
STATE = ROOT / "native_backtest/out/ap3/smoke/hf_endpoint/endpoint.json"


def spec() -> dict:
    return json.loads(CONFIG.read_text())["providers"]["hf_endpoint"]["endpoint_spec"]


def approved() -> bool:
    cfg = json.loads(CONFIG.read_text())
    p = ROOT / cfg["approval_record"]
    return p.exists() and json.loads(p.read_text()).get("provider") == "hf_endpoint" and bool(os.environ.get("HF_TOKEN"))


def create() -> dict:
    from huggingface_hub import HfApi

    e = spec()
    ep = HfApi(token=os.environ["HF_TOKEN"]).create_inference_endpoint(
        e["name"], repository=e["repository"], revision=e["revision"], framework="pytorch", task="text-generation",
        vendor=e["vendor"], region=e["region"], accelerator="gpu", instance_type=e["instance_type"], instance_size=e["instance_size"],
        min_replica=e["min_replica"], max_replica=e["max_replica"], scale_to_zero_timeout=e["scale_to_zero_timeout_minutes"],
        custom_image={"url": e["image"], "health_route": "/health", "port": 8000, "env": e["env"]}, env=e["env"], type="protected")
    state = {"name": ep.name, "url": ep.url, "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "spec": e}
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1) + "\n")
    return state


def pause(delete: bool = False) -> str:
    from huggingface_hub import HfApi

    api = HfApi(token=os.environ["HF_TOKEN"])
    name = json.loads(STATE.read_text())["name"] if STATE.exists() else spec()["name"]
    ep = api.get_inference_endpoint(name)
    (ep.delete if delete else ep.pause)()
    return f"{'deleted' if delete else 'paused'} {name}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--create", action="store_true")
    g.add_argument("--pause", action="store_true")
    g.add_argument("--delete", action="store_true")
    a = ap.parse_args(argv)
    cfg = json.loads(CONFIG.read_text())
    if not (a.create or a.pause or a.delete):
        print(json.dumps({"endpoint_spec": spec(), "cost_estimate": cfg["providers"]["hf_endpoint"]["cost_estimate"],
                          "will_contact_hugging_face": False}, indent=1))
        return 0
    if not approved():
        raise SystemExit("not approved: needs the stage-A approval record for hf_endpoint and HF_TOKEN as an environment secret")
    print(json.dumps(create(), indent=1) if a.create else pause(delete=a.delete))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
