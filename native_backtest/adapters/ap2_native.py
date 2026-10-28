"""AP2 adapters: Agent Committee (AP2A) and JEV (AP2B), native replay.

Native behaviour is executed, not re-implemented: the vendored, byte-identical site engine
(site/js/livebacktest.js with its allocation.js) is run in Node for every saved month. Python code
here only (1) cross-checks those native outputs against the native Python allocator, the native
parser and the authors' saved logs, (2) replicates the native execution assumptions so they can be
compared with the common evaluation rule, and (3) writes decision records for the shared evaluator.

Nothing here calls a model. Committee outputs are the saved gpt-4o runs; JEV outputs are the saved
typesafe/jev answers, whose model, prompt and recorder are not in the repository.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from native_backtest.framework.market import Market, close_time_iso, decision_time_iso
from native_backtest.framework.records import DecisionRecord

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / "native_backtest" / "vendor"
A2 = VENDOR / "protofin_approach-2_ce063b8"
FJ = VENDOR / "protofin_feature-jev_7a70331"
HARNESS = ROOT / "native_backtest" / "adapters" / "node" / "ap2_native_replay.mjs"
OUT = ROOT / "native_backtest" / "out" / "ap2"

OUTCOME_KEYS = ("r_spy", "r_tlt", "next")
COMMITTEE_PROVENANCE = {
    "model": "gpt-4o (OpenAI alias, not pinned to a dated snapshot)",
    "model_pretraining_cutoff": "2023-10 (OpenAI GPT-4o system card)",
    "temperature": 0.0, "seed": 42, "calls_per_decision": 3,
    "generated_at": "2026-10-05T02:58:36Z",
    "generator": "research/run_saved_committee.py @ approach-2 ce063b8",
    "prompts": "rebuilt from site/data/backtest_months.json prompts; raw replies cached in research/out/committee_cache.jsonl",
    "post_hoc_generation": True,
}
JEV_PROVENANCE = {
    "model": "typesafe/jev on Cloudflare Workers AI (README); version undocumented",
    "model_pretraining_cutoff": "unknown",
    "generated_at": "unknown (committed 2026-10-27)",
    "generator": "scripts/build_jev_runs.py — referenced but NOT present in the repository",
    "prompts": "NOT stored; README says the same masked payload as the committee and two typed questions",
    "raw_replies": "NOT stored; parsed fields only",
    "post_hoc_generation": True,
    "reproducibility": "replay of saved answers only; the answers cannot be regenerated",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_node(engine_dir: Path, job: str, mode: str, out: Path, last_as_of: Optional[str] = None) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["node", str(HARNESS), f"--engine={engine_dir}", f"--job={job}", f"--mode={mode}", f"--out={out}"]
    if last_as_of:
        cmd.append(f"--last-as-of={last_as_of}")
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return json.loads(out.read_text())


def load_native_months(strip_outcomes: bool = True) -> List[dict]:
    months = json.loads((A2 / "site/data/backtest_months.json").read_text())["months"]
    if strip_outcomes:
        months = [{k: v for k, v in m.items() if k not in OUTCOME_KEYS} for m in months]
    return months


def _import_native(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(f"native_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------------------------
# Native fidelity checks (decision level: no outcomes are read)
# --------------------------------------------------------------------------------------------

def check_committee_against_native_python(js_rows: List[dict]) -> dict:
    """The native Python allocator must give the same SPY weight as the native JS engine."""
    alloc = _import_native("allocation", A2 / "allocation.py")
    months = {m["as_of"]: m for m in load_native_months()}
    diffs = []
    for r in js_rows:
        m = months[r["as_of"]]
        views = r["views"]
        d = alloc.allocate(np.array(m["sigma"]), views, r["conf_applied"], m["rf_pct"], None)
        diffs.append(abs(d["target_spy"] - r["w_spy"]))
    return {"months": len(diffs), "max_abs_diff_w_spy": float(max(diffs)), "pass": bool(max(diffs) < 1e-12)}


def check_committee_reparse() -> dict:
    """Re-parse every cached deterministic raw CIO reply with the native parser; it must equal the saved fields."""
    committee = _import_native("committee", A2 / "committee.py")
    runs = json.loads((A2 / "site/data/committee_runs.json").read_text())["months"]
    cache = [json.loads(l) for l in (A2 / "research/out/committee_cache.jsonl").read_text().splitlines() if l.strip()]
    det = [c for c in cache if float(c.get("temperature", -1)) == 0.0]
    mism = []
    for c in det:
        parsed = committee.parse_cio(c["cio_raw"])
        saved = runs[c["as_of"]]["cio"]
        p = parsed[0] if isinstance(parsed, tuple) else parsed
        got = (p.get("spy_q"), p.get("tlt_q"), p.get("confidence")) if isinstance(p, dict) else None
        exp = (saved["spy_q"], saved["tlt_q"], saved["confidence"])
        if got != exp:
            mism.append({"as_of": c["as_of"], "parsed": got, "saved": exp})
    return {"deterministic_cached_replies": len(det), "saved_months": len(runs), "mismatches": mism[:5], "n_mismatches": len(mism),
            "pass": len(det) == len(runs) and not mism}


def check_jev(js_featurejev: List[dict], js_approach2: List[dict]) -> dict:
    """JEV: native engine on its own branch vs approach-2 engine vs the authors' saved log weights."""
    log = json.loads((FJ / "research/out/jev_backtest.json").read_text())["log"]
    saved_w = {r["as_of"]: r["w"] for r in log}          # decision weights only; outcome fields ignored
    a = {r["as_of"]: r["w_spy"] for r in js_featurejev}
    b = {r["as_of"]: r["w_spy"] for r in js_approach2}
    d_branch = max(abs(a[k] - b[k]) for k in a)
    d_saved = max(abs(a[k] - saved_w[k]) for k in a)
    return {"months": len(a), "max_abs_diff_feature_jev_vs_approach2": d_branch, "max_abs_diff_vs_saved_log": d_saved,
            "pass": d_branch < 1e-12 and d_saved < 1e-12}


# --------------------------------------------------------------------------------------------
# Decision records for the shared evaluator
# --------------------------------------------------------------------------------------------

def build_records(system_id: str, js_rows: List[dict], market: Market) -> Tuple[List[DecisionRecord], dict]:
    months = {m["as_of"]: m for m in load_native_months()}
    if system_id == "AP2A":
        runs = json.loads((A2 / "site/data/committee_runs.json").read_text())["months"]
        source_files = {p: _sha(A2 / p) for p in ("site/data/committee_runs.json", "site/data/backtest_months.json", "site/js/livebacktest.js", "site/js/allocation.js")}
        prov = dict(COMMITTEE_PROVENANCE)
    else:
        runs = json.loads((FJ / "site/data/jev_runs.json").read_text())["months"]
        source_files = {p: _sha(FJ / p) for p in ("site/data/jev_runs.json", "site/data/backtest_months.json", "site/js/livebacktest.js", "site/js/allocation.js")}
        prov = dict(JEV_PROVENANCE)
    recs, date_mismatch = [], []
    for r in js_rows:
        as_of = pd.Timestamp(r["as_of"])
        month = as_of.to_period("M")
        day = market.decision_dates.get(month)
        if day is None or day.normalize() != as_of.normalize():
            date_mismatch.append({"month": str(month), "native_as_of": r["as_of"], "framework_decision_day": None if day is None else day.date().isoformat()})
        dec_day = day if day is not None else as_of
        w = float(r["w_spy"])
        native = runs[r["as_of"]]
        if system_id == "AP2A":
            forecast = {"horizon_months": 12, "kind": "expected_total_return_pct", "values": {"SPY": native["cio"]["spy_q"], "TLT": native["cio"]["tlt_q"]}}
            conf = {"reported": r["conf_reported"], "applied": r["conf_applied"], "regime": r["regime"]}
            detail = {"economist": native["economist"], "risk": native["risk"], "cio": native["cio"]["cio"], "problems": native.get("problems", [])}
        else:
            forecast = {"horizon_months": 12, "kind": "p_stocks_beat_bonds_and_tilt", "values": {"p": native["p"], "choice": native["choice"], "probs": native["probs"], "offset": native["offset"]}}
            conf = {"reported": native["confidence"], "applied": native["confidence"]}
            detail = None
        recs.append(DecisionRecord(
            system_id=system_id,
            decision_month=str(month),
            decision_time=decision_time_iso(dec_day),
            info_cutoff=close_time_iso(as_of),
            universe=["SPY", "TLT"],
            target_weights={"SPY": w, "TLT": 1.0 - w},
            generation={"mode": "saved_native_replay", "native_as_of": r["as_of"], "engine": "site/js/livebacktest.js (node, unchanged)",
                        "source_files_sha256": source_files, **prov},
            forecast=forecast, confidence=conf, native_detail=detail,
        ))
    return recs, {"date_mismatches": date_mismatch}


# --------------------------------------------------------------------------------------------
# Native execution assumptions (for reproduction and for comparison with the common rule)
# --------------------------------------------------------------------------------------------

def native_execution_replica(weights: Dict[str, float], last_as_of: str, cost_bps: float = 5.0) -> pd.DataFrame:
    """Python replica of LiveBacktest.step(): same-close trade, 5 bp per unit of SPY-weight change,
    start at 60/40 with no cost, native returns r_spy/r_tlt and native cash. Development months only."""
    raw = json.loads((A2 / "site/data/backtest_months.json").read_text())["months"]
    rows, nav, w_prev = [], 1.0, 0.60
    cost = cost_bps / 1e4
    for m in raw:
        if m["as_of"] > last_as_of:
            break
        t = weights[m["as_of"]]
        turn = abs(t - w_prev)
        if turn > 1e-9:
            nav *= 1 - turn * cost
        ret = t * m["r_spy"] + (1 - t) * m["r_tlt"]
        nav *= 1 + ret
        rows.append({"as_of": m["as_of"], "w": t, "ret": ret, "nav": nav, "rf_month": (1 + m["rf_pct"] / 100) ** (1 / 12) - 1, "turn": turn})
        w_prev = t * (1 + m["r_spy"]) / (1 + ret)
    return pd.DataFrame(rows)
