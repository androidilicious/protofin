"""Version and fingerprint of the AP3 agent protocol.

A fingerprint is a hash of everything that decides what the agents are asked and how their answers are judged:
- agent code, prompts and schemas;
- tools, limits, concepts, variants and fixtures;
- the vendored assessor and retrieval;
- the month runner and the G3b scorer.

Records and result bundles carry it. A run never reuses results made under a different fingerprint: an earlier
attempt stays in the results branch's history and is not mixed with the new one.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_VERSION = "1.1"   # 1.0 = first real-model run (2026-10-29, ap3-qwen3-runs @ 790a049); 1.1 = fixes after it
FILES = (
    "native_backtest/ap3/hypothesis_agent.py", "native_backtest/ap3/testing_agent.py", "native_backtest/ap3/tools.py",
    "native_backtest/ap3/runner.py", "native_backtest/ap3/evidence_pool.py", "native_backtest/ap3/mediators.py",
    "native_backtest/ap3/library.py", "native_backtest/ap3/encoder.py", "native_backtest/ap3/limits_v1.json",
    "native_backtest/ap3/concepts_v1.json", "native_backtest/ap3/variants_v1.json",
    "native_backtest/ap3/fixtures/testing_agent_fixtures_v1.json", "native_backtest/config/ap3_reliability_gates_v1.json",
    "native_backtest/vendor/causal-rag-mvp_389f826/src/crag/assess.py", "native_backtest/vendor/causal-rag-mvp_389f826/src/crag/retrieval.py",
    "native_backtest/scripts/ap3_g3b_fixtures.py",
)


def fingerprint() -> str:
    h = hashlib.sha256(PROTOCOL_VERSION.encode())
    for f in FILES:
        h.update(f.encode() + b"\0" + hashlib.sha256((ROOT / f).read_bytes()).digest())
    return h.hexdigest()[:16]
