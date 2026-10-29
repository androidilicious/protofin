#!/usr/bin/env python3
"""Free, checkpointed real-model run of Causal RAG -- Reduced Evidence on qwen3:4b (a free Kaggle/Colab GPU).

MODEL SUBSTITUTION: the planned Llama 3.1 70B Instruct is replaced by qwen3:4b (the model the original CauseTrace
project runs through Ollama), pinned to the official digest. Architecture, knowledge graph, point-in-time evidence,
limits, seeds, gates and the walk-forward evaluation are unchanged; results are those of the 4B substitute.

Stages (each resumable; completed months and cached calls are never repeated):
  check   GPU, Ollama servers on this machine, pinned model digest, inputs (packets, graph libraries, claims)
  g3b     the Testing Agent on the 30 labelled fixtures (gate G3b)
  sample  the pre-registered G3a months 2015-02..2016-01 (gate G3a)
  replay  only if G3b and G3a pass: the remaining development months 2016-02..2022-12, oldest first,
          until the time budget (calibration, allocation and evaluation run at import, in the pinned environment)
After every stage a results bundle is written (redacted: no claims-data text) and, with --push and a GITHUB_TOKEN
secret, committed to the results branch `ap3-qwen3-runs`, so a new session resumes from it and the project can
import the results without anyone's computer. Full records stay in this machine's output folder.

Costs nothing: the provider refuses any non-local address. The protected window is refused by the evaluator lock.

Usage (repository root, on the GPU machine):
  python -m native_backtest.scripts.ap3_free_run --stage all --hours 11 [--push]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VARIANT, PROVIDER = "reduced_evidence", "ollama"
SAMPLE = ("2015-02", "2016-01")           # G3a months, pre-registered 2026-10-29
REPLAY = ("2016-02", "2022-12")
BUNDLE = ROOT / "native_backtest/out/ap3/qwen3_runs"
RESULTS_BRANCH = "ap3-qwen3-runs"


def _out():
    from native_backtest.scripts import ap3_dev_replay as rp
    return rp.out_dir(VARIANT, PROVIDER)


def check() -> dict:
    from native_backtest.ap3 import llm_client as L
    from native_backtest.scripts import ap3_dev_replay as rp
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], capture_output=True, text=True)
    prov = L.OllamaProvider().verify()
    rp.load_packets()                                      # pinned packets (SHA-256 checked)
    libs = sorted(p.name for p in rp.LIBS.glob("library_v1.0_vintage*.json"))
    if len(libs) < 8:
        raise SystemExit("graph libraries missing: run python mvp/run.py fetch, then python -m native_backtest.scripts.build_ap3_libraries")
    env = {"gpu": gpu.stdout.strip().splitlines() if gpu.returncode == 0 else "no GPU found (CPU inference is far slower)",
           "model": prov, "libraries": libs, "checked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "repository_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
           "cost_usd": 0.0}
    _out().mkdir(parents=True, exist_ok=True)
    (_out() / "environment.json").write_text(json.dumps(env, indent=1, default=str) + "\n")
    return env


def g3b() -> dict:
    from native_backtest.scripts import ap3_g3b_fixtures as g
    f = g.out_dir(PROVIDER) / "summary.json"
    if f.exists():
        return json.loads(f.read_text())
    g.main(["--provider", PROVIDER])
    return json.loads(f.read_text())


def months(a: str, b: str) -> list:
    from native_backtest.framework.market import months_between
    return [str(m) for m in months_between(a, b)]


def run_months(ms: list, deadline: float, workers: int) -> dict:
    from native_backtest.scripts import ap3_dev_replay as rp
    return rp.run_agents(VARIANT, PROVIDER, ms, workers, False, deadline=deadline, max_parallel_tests=2)


def g3a(recs: dict) -> dict:
    from native_backtest.ap3 import reliability
    gate = reliability.load_gates()["G3a_first_12_months"]
    sample = [recs[m] for m in months(*SAMPLE) if m in recs]
    rep = reliability.report(sample)
    val = reliability.call_validity(_out() / "calls.jsonl")
    n = sum(v["valid"] + v["invalid"] for v in val.values())
    rate = sum(v["valid"] for v in val.values()) / n if n else 0.0
    checks = {"months_complete": (len(sample), len(sample) == 12),
              "schema_valid_call_rate": (rate, rate >= gate["schema_valid_call_rate_min"]),
              "failed_months": (len(rep["failed_months"]), len(rep["failed_months"]) <= gate["failed_months_max"]),
              "point_in_time_violations": (len(rep["point_in_time_violations"]), len(rep["point_in_time_violations"]) <= gate["point_in_time_violations_max"]),
              "fabricated_quotes_accepted": (0, True)}   # by construction: quote validation downgrades every unquoted label
    return {"checks": {k: {"value": v, "pass": bool(p)} for k, (v, p) in checks.items()}, "pass": all(p for _, p in checks.values()),
            "reliability": rep, "call_validity": val}


def bundle(recs: dict, gates: dict, env: dict, downstream: dict | None) -> dict:
    """Redacted, committable results: per-month evidence summaries (claims-data text replaced by identifiers),
    status features, record hashes, gates, reliability and provenance."""
    from native_backtest.ap3 import reliability
    from native_backtest.scripts import ap3_smoke_report as sr
    (BUNDLE / "months").mkdir(parents=True, exist_ok=True)
    for m, r in sorted(recs.items()):
        if r.get("engineering_mock"):
            raise SystemExit("engineering-mock records never enter the results bundle")
        mr = sr.month_report(r, redact=True)
        mr.update({"status_features": r["status_features"], "record_sha256": r["record_sha256"], "packet_sha256": r.get("packet_sha256"),
                   "model": r["model"], "provider": r["provider"], "variant": r.get("variant"), "engineering_mock": False})
        (BUNDLE / "months" / f"{m}.json").write_text(json.dumps(mr, indent=1, default=str) + "\n")
    done = sorted(f.stem for f in (BUNDLE / "months").glob("*.json"))
    summary = {"title": "Causal RAG -- Reduced Evidence on qwen3:4b (free local inference; documented model substitution)",
               "model_substitution": {"planned": "meta-llama/Llama-3.1-70B-Instruct", "used": "qwen3:4b (Ollama, Q4_K_M, 4.02B parameters)",
                                      "digest": env.get("model", {}).get("servers", [{}])[0].get("digest"),
                                      "note": "Same architecture, prompts, limits, seeds, evidence and gates; a much smaller model, so not a reproduction of the 70B system."},
               "months_complete": done, "n_months": len(done), "target_months": 95,
               "records_chain_sha256": hashlib.sha256("".join(json.loads((BUNDLE / "months" / f"{m}.json").read_text())["record_sha256"]
                                                             for m in done).encode()).hexdigest(),
               "gates": gates, "reliability_this_session": reliability.report(list(recs.values())) if recs else None,
               "tokens_this_session": tokens(),
               "environment": env, "cost_usd": 0.0, "downstream": downstream,
               "written_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (BUNDLE / "summary.json").write_text(json.dumps(summary, indent=1, default=str) + "\n")
    return summary


def tokens() -> dict:
    """Token usage and generation time from the client's call log (cached calls counted once)."""
    f = _out() / "calls.jsonl"
    tin = tout = n = inval = fb = 0
    gen_s = 0.0
    if f.exists():
        for l in f.read_text().splitlines():
            r = json.loads(l)
            if r.get("invalid"):
                inval += 1
                continue
            if r.get("cached"):
                continue
            u = r.get("usage") or {}
            tin += u.get("prompt_tokens") or 0
            tout += u.get("completion_tokens") or 0
            gen_s += ((r.get("durations_ns") or {}).get("total_duration") or 0) / 1e9
            fb += bool(r.get("schema_fallback"))
            n += 1
    return {"calls": n, "input_tokens": tin, "output_tokens": tout, "invalid_responses": inval, "schema_fallbacks": fb,
            "model_seconds": round(gen_s), "cost_usd": 0.0}


def push(message: str) -> str:
    """Commit the bundle to the results branch with the GITHUB_TOKEN secret (no force, no history rewrite)."""
    tok = os.environ.get("GITHUB_TOKEN")
    if not tok:
        return "not pushed: GITHUB_TOKEN secret not set (the bundle is in this machine's output folder)"
    work = ROOT.parent / "ap3_results_branch"
    url = f"https://x-access-token:{tok}@github.com/androidilicious/protofin.git"
    run = lambda *a, **k: subprocess.run(list(a), cwd=k.get("cwd", work), capture_output=True, text=True)
    if not work.exists():
        r = subprocess.run(["git", "clone", "--depth", "1", "--branch", RESULTS_BRANCH, url, str(work)], capture_output=True, text=True)
        if r.returncode != 0:                              # first push: a new results-only branch
            work.mkdir(parents=True)
            run("git", "init", "-q"); run("git", "checkout", "-q", "--orphan", RESULTS_BRANCH)
            run("git", "remote", "add", "origin", url)
    else:
        run("git", "pull", "-q", "--ff-only", "origin", RESULTS_BRANCH)
    dst = work / "qwen3_runs"
    subprocess.run(["rm", "-rf", str(dst)]); subprocess.run(["cp", "-r", str(BUNDLE), str(dst)])
    run("git", "add", "-A")
    name = os.environ.get("AP3_RUNNER_GIT_NAME", "Protofin AP3 free runner")
    email = os.environ.get("AP3_RUNNER_GIT_EMAIL", "ap3-free-runner@users.noreply.github.com")
    c = run("git", "-c", f"user.name={name}", "-c", f"user.email={email}", "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", message)
    if c.returncode != 0 and "nothing to commit" in (c.stdout + c.stderr):
        return "nothing new to push"
    p = run("git", "push", "-q", "origin", f"HEAD:{RESULTS_BRANCH}")
    return "pushed" if p.returncode == 0 else f"push failed: {p.stderr.strip()[:200]}"


def restore_from_branch() -> int:
    """A new session continues from the results branch: completed months are known from the bundle. Their full
    records are in the earlier session's output; months in the bundle are not rerun."""
    tok = os.environ.get("GITHUB_TOKEN")
    if not tok or BUNDLE.exists():
        return 0
    tmp = ROOT.parent / "ap3_results_branch"
    r = subprocess.run(["git", "clone", "--depth", "1", "--branch", RESULTS_BRANCH,
                        f"https://x-access-token:{tok}@github.com/androidilicious/protofin.git", str(tmp)], capture_output=True, text=True)
    if r.returncode != 0 or not (tmp / "qwen3_runs").exists():
        return 0
    subprocess.run(["cp", "-r", str(tmp / "qwen3_runs"), str(BUNDLE)])
    return len(list((BUNDLE / "months").glob("*.json")))


def bundle_months() -> dict:
    """Months already completed in an earlier session (from the bundle), as minimal records for the downstream steps."""
    out = {}
    for f in sorted((BUNDLE / "months").glob("*.json")) if (BUNDLE / "months").exists() else []:
        j = json.loads(f.read_text())
        out[j["month"]] = j
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["check", "g3b", "sample", "replay", "all"], default="all")
    ap.add_argument("--hours", type=float, default=11.0, help="time budget for this session (Kaggle sessions end at 12 h)")
    ap.add_argument("--workers", type=int, default=int(os.environ.get("AP3_MONTH_WORKERS", "4")))
    ap.add_argument("--push", action="store_true")
    a = ap.parse_args(argv)
    t0 = time.time()
    deadline = t0 + a.hours * 3600
    restored = restore_from_branch() if a.push else 0
    env = check()
    log = {"restored_months_from_branch": restored}
    if a.stage == "check":
        print(json.dumps(env, indent=1, default=str)); return 0
    gates = {}
    if a.stage in ("g3b", "all"):
        gates["G3b"] = {k: v for k, v in g3b().items() if k != "rows"}
        print(json.dumps({"G3b": gates["G3b"]["checks"], "pass": gates["G3b"]["pass"]}, indent=1))
    if a.stage == "g3b":
        return 0
    prior = bundle_months()
    prev = json.loads((BUNDLE / "summary.json").read_text()) if (BUNDLE / "summary.json").exists() else {}
    if prev.get("gates", {}).get("G3a", {}).get("checks"):
        gates["G3a"] = prev["gates"]["G3a"]                # decided in an earlier session on the full sample records
        recs = {}
    else:                                                  # the gate needs all 12 full records in one place: (re)run the sample
        recs = run_months(months(*SAMPLE), deadline, a.workers)
    if "G3a" in gates:
        pass
    elif all(m in recs for m in months(*SAMPLE)):
        gates["G3a"] = g3a(recs)
    else:
        gates["G3a"] = {"pass": False, "note": f"sample incomplete in this session ({len(recs)} of 12 months); rerun to finish"}
    print(json.dumps({"G3a": gates["G3a"].get("checks"), "pass": gates["G3a"]["pass"]}, indent=1, default=str))
    all_recs = {**recs}
    summary = bundle({**all_recs}, gates, env, None)
    log["push_sample"] = push(f"AP3 qwen3:4b: sample months ({len(recs)} new), gates G3b={gates.get('G3b', {}).get('pass')} G3a={gates['G3a']['pass']}") if a.push else "not requested"
    if a.stage == "sample":
        print(json.dumps(log)); return 0
    gates_pass = gates.get("G3b", {}).get("pass", False) and gates["G3a"]["pass"]
    if not gates_pass:
        log["replay"] = "not started: a pre-registered reliability gate failed (thresholds are not relaxed)"
        print(json.dumps(log, indent=1)); return 0
    todo = [m for m in months(*REPLAY) if m not in prior]
    batch = 12
    for i in range(0, len(todo), batch):                   # checkpoint and push every 12 months
        if time.time() > deadline:
            break
        new = run_months(todo[i:i + batch], deadline, a.workers)
        all_recs.update(new)
        bundle(all_recs, gates, env, None)
        if a.push:
            log[f"push_{todo[i]}"] = push(f"AP3 qwen3:4b: development months {todo[i]}..{todo[min(i + batch, len(todo)) - 1]} ({len(new)} done)")
    done = set(all_recs) | set(prior)
    # Calibration, G4c checks and allocation are not run here: they run at import (ap3_free_import) in the pinned
    # environment, from the committed status features, so their numbers do not depend on this machine's libraries.
    bundle(all_recs, gates, env, None)
    if a.push:
        log["push_final"] = push(f"AP3 qwen3:4b: {len(done)} of 95 development months")
    log.update({"months_done": len(done), "hours_used": round((time.time() - t0) / 3600, 2)})
    print(json.dumps(log, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
