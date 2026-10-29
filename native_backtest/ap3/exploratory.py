"""Exploratory (gate-failed) development backtest mode for Causal RAG.

The pre-registered reliability gates G3a and G3b, and their thresholds, are unchanged and are still evaluated and
reported exactly as before. This mode does one thing: on an explicit request it lets the **development** replay and
its downstream evaluation proceed although a gate failed, so the full pipeline can be studied end to end. It is a
diagnostic, never a validation.

Rules enforced here, not left to the caller:
- the request must be explicit (a flag or AP3_EXPLORATORY=1); it is never the default;
- the window must lie inside the development window: the protected window can never be opened this way;
- every output carries the exploratory banner, the failed gates and their real values;
- engineering-mock output is never admitted (checked where records are read);
- nothing is fabricated: months without genuine agent output stay absent and are reported as missing coverage.

The confirmatory historical evaluation refuses outright if any Causal RAG input carries this banner.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Dict, Iterable, Optional

ROOT = Path(__file__).resolve().parents[2]
MODE_FILE = ROOT / "native_backtest/config/ap3_exploratory_mode_v1.json"
LABEL = "EXPLORATORY — RELIABILITY GATES FAILED"
STATUS = ("EXPLORATORY DIAGNOSTIC of a documented model substitution (qwen3:4b): the pre-registered reliability gates "
          "G3a and/or G3b did not pass, so these outputs are not validated agent results and are not evidence of "
          "investment performance. Development months only; the protected window stays sealed.")


class NotExploratory(RuntimeError):
    pass


def enabled(flag: bool = False) -> bool:
    return bool(flag or os.environ.get("AP3_EXPLORATORY") == "1")


def load_mode() -> dict:
    return json.loads(MODE_FILE.read_text())


def failed_gates(gates: Dict[str, dict]) -> Dict[str, dict]:
    """The gates that did not pass, with the checks that failed and their real values."""
    out = {}
    for name, g in (gates or {}).items():
        if g.get("pass"):
            continue
        out[name] = {"pass": False,
                     "failed_checks": {k: v.get("value") for k, v in (g.get("checks") or {}).items() if not v.get("pass")},
                     "note": g.get("note")}
    return out


def assert_development_only(months: Iterable[str], protected_start: str) -> None:
    bad = sorted(m for m in months if str(m) >= protected_start)
    if bad:
        raise NotExploratory(f"the exploratory mode never scores the protected window: {bad[0]}..{bad[-1]} "
                             f"is at or after {protected_start}")


def stamp(obj: dict, gates: Dict[str, dict], *, months: Optional[Iterable[str]] = None, protected_start: Optional[str] = None) -> dict:
    """Attach the exploratory banner to an output. Raises if no gate actually failed (the mode would be pointless)
    or if any month lies in the protected window."""
    fg = failed_gates(gates)
    if not fg:
        raise NotExploratory("no reliability gate failed: run the normal gated path instead")
    if months is not None and protected_start is not None:
        assert_development_only(months, protected_start)
    obj = dict(obj)
    obj["exploratory"] = {
        "label": LABEL, "status": STATUS,
        "gates_failed": fg,
        "gate_thresholds_unchanged": True,
        "validated": False,
        "usable_for_protected_window": False,
        "mode_record": str(MODE_FILE.relative_to(ROOT)),
        "requested_explicitly": True,
    }
    return obj


def is_exploratory(obj: dict) -> bool:
    return bool(isinstance(obj, dict) and obj.get("exploratory"))


# ----------------------------------------------------------------- freeze record
def _sha_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def freeze() -> dict:
    """Exactly what this experiment runs: model, prompts, inference settings, code revision, graph vintages and
    evidence inputs. Recorded so the run can be reproduced and so any later change is visible."""
    from native_backtest.ap3 import hypothesis_agent, llm_client, protocol, runner, testing_agent
    from native_backtest.ap3.testing_agent import native_assess

    limits = runner.load_limits()
    libs = sorted((ROOT / "native_backtest/data/_external/ap3_libraries").glob("library_v1.0_vintage*.json"))
    rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return {
        "model": {"name": llm_client.OLLAMA_MODEL, "digest_prefix": llm_client.OLLAMA_DIGEST_PREFIX,
                  "served": "Ollama on the run machine (localhost only); documented substitution for Llama 3.1 70B"},
        "prompts_sha256": {
            "hypothesis_agent.SYSTEM": _sha_text(hypothesis_agent.SYSTEM),
            "testing_agent.PLAN_SYSTEM": _sha_text(testing_agent.PLAN_SYSTEM),
            "assessor.SYSTEM (causal-rag-mvp, unchanged)": _sha_text(native_assess.SYSTEM),
        },
        "prompts_unchanged_since_run_1": True,
        "inference": {"temperature_hypothesis": limits["hypothesis_agent"]["temperature"], "seed_hypothesis": limits["hypothesis_agent"]["seed"],
                      "temperature_testing": limits["testing_agent"]["temperature"], "seeds_testing": limits["testing_agent"]["seeds"],
                      "runs_testing": limits["testing_agent"]["runs"], "thinking_mode": False, "structured_output": "per-step JSON schema",
                      "num_ctx": int(os.environ.get("AP3_OLLAMA_NUM_CTX", "32768")),
                      "max_tool_calls": limits["hypothesis_agent"]["max_tool_calls"], "max_turns": limits["hypothesis_agent"]["max_turns"]},
        "limits_sha256": _sha_file(ROOT / "native_backtest/ap3/limits_v1.json"),
        "agent_protocol": {"version": protocol.PROTOCOL_VERSION, "fingerprint": protocol.fingerprint(),
                           "note": "1.1 fixes harness defects found in run 1 (the final-answer turn, the agent's own "
                                   "replies returned as assistant turns, whole-word graph search, rival-id validation). "
                                   "The agent prompts, schemas, limits, rubric, fixtures and gate thresholds are unchanged."},
        "evidence": {"variant": "reduced_evidence", "variants_sha256": _sha_file(ROOT / "native_backtest/ap3/variants_v1.json"),
                     "point_in_time": "evidence and mediators are filtered to the decision time for every month"},
        "graph": {"vintages": [p.name for p in libs], "libraries_sha256": {p.name: _sha_file(p)[:16] for p in libs}},
        "windows": {"agent_months": ["2015-02", "2022-12"], "scored_months": ["2019-03", "2022-12"],
                    "protected": "2023-01..2026-08, sealed"},
        "code_revision": rev.stdout.strip() if rev.returncode == 0 else None,
        "cost_usd": 0.0,
    }
