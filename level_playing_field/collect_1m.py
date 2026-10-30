"""Ask the committee and Jev the ONE-MONTH question for every month from 2015-02 to 2026-08, once, and save it.

Same masked payloads as the original 12-month runs (vendored approach-2 backtest_months.json); only the
horizon in the question changes, so every approach forecasts the same thing the evaluator scores:
next month's return.

    python -m level_playing_field.collect_1m committee --env ../protofin/.env    # gpt-4o, temperature 0
    python -m level_playing_field.collect_1m jev --url http://127.0.0.1:8799       # local `wrangler dev` caller
    python -m level_playing_field.collect_1m export                              # rebuild data/*.json from the caches

Every raw reply is cached in raw/*.jsonl, so a crash or rate limit loses nothing and nothing is asked twice.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
VENDOR = ROOT / "native_backtest" / "vendor" / "protofin_approach-2_ce063b8"
sys.path.insert(0, str(VENDOR))
import committee  # noqa: E402  (the unchanged approach-2 committee: prompts, parsers, orchestration)

FIRST, LAST = "2015-02", "2026-08"
RAW = HERE / "raw"
DATA = HERE / "data"
MODEL = "gpt-4o"
_lock = threading.Lock()

RULES_12M = ("Expected returns are TOTAL returns over the next 12 months, in percent (e.g. 7.5 or -2.0), "
             "judged against the cash yield above: below cash is a bearish view.\n")
RULES_1M = ("Expected returns are TOTAL returns over the NEXT MONTH only (about 21 trading days), in percent "
            "(e.g. 0.8 or -0.5), judged against one month of the cash yield above (the annual cash yield divided by 12): "
            "below that is a bearish view.\n")

TILT_OFFSET = {"strong_equities": 3, "lean_equities": 1.5, "neutral": 0, "lean_bonds": -1.5, "strong_bonds": -3}
JEV_QUESTIONS_1M = {
    "stocks_beat_bonds": {
        "type": "noul",
        "instructions": "Over the NEXT MONTH, will SPY (US equities) deliver a higher total return than TLT (long US Treasuries)?",
        "criteria": {"true": "SPY outperforms TLT over the next month", "false": "TLT outperforms or matches SPY over the next month"},
    },
    "tilt": {
        "type": "choice",
        "instructions": "Relative to a neutral 60% equities / 40% long Treasuries portfolio, how should the equity share be tilted for the next month, given only this data?",
        "criteria": {
            "strong_equities": "Clear evidence equities will beat long Treasuries by a wide margin next month",
            "lean_equities": "Some evidence equities will beat long Treasuries next month",
            "neutral": "No reliable edge either way; stay at 60/40",
            "lean_bonds": "Some evidence long Treasuries will beat equities next month",
            "strong_bonds": "Clear evidence long Treasuries will beat equities by a wide margin next month",
        },
    },
}


def months():
    allm = json.loads((VENDOR / "site" / "data" / "backtest_months.json").read_text(encoding="utf-8"))["months"]
    return [m for m in allm if FIRST <= m["as_of"][:7] <= LAST]


def prompts_1m(m):
    shock = f"long-term government yield moved {m['shock_bps']:+.0f} bps versus its 3-month average"
    p = committee.build_prompts(m["payload"], shock)
    for k in p:
        assert RULES_12M in p[k], "approach-2 prompt wording changed; refusing to guess"
        p[k] = p[k].replace(RULES_12M, RULES_1M)
    return p


def load_cache(path):
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            out[r["as_of"]] = r
    return out


def append(path, rec):
    with _lock, open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


# ------------------------------------------------------------------ committee (gpt-4o, temperature 0)
def run_committee(env_path, workers, per_minute):
    from dotenv import load_dotenv
    from openai import OpenAI
    load_dotenv(env_path, override=True)
    client = OpenAI(max_retries=8)
    cache_path = RAW / "committee_1m.jsonl"
    cache = load_cache(cache_path)
    todo = [m for m in months() if m["as_of"] not in cache]
    print(f"committee: {len(todo)} months to ask ({len(todo) * 3} calls), {len(cache)} cached", flush=True)
    nxt = [0.0]

    def pace():
        with _lock:
            now = time.time(); start = max(now, nxt[0]); nxt[0] = start + 60.0 / per_minute
        time.sleep(max(0.0, start - now))

    def chat(prompt):
        r = client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": prompt}], temperature=0.0, seed=42, max_tokens=300)
        return r.choices[0].message.content or ""

    def one(m):
        pace()
        out = committee.run_committee(prompts_1m(m), chat)
        rec = {"as_of": m["as_of"], "model": MODEL, "temperature": 0.0, "seed": 42, "horizon_months": 1,
               "economist_raw": out["economist_raw"], "risk_raw": out["risk_raw"], "cio_raw": out["cio_raw"]}
        append(cache_path, rec)
        return rec

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, f in enumerate(as_completed([ex.submit(one, m) for m in todo]), 1):
            try:
                f.result()
            except Exception as exc:
                print("failed:", str(exc)[:160], flush=True)
            if i % 20 == 0:
                print(f"{i}/{len(todo)}", flush=True)


# ------------------------------------------------------------------ Jev (typesafe/jev via a local wrangler dev caller)
def run_jev(url, workers):
    cache_path = RAW / "jev_1m.jsonl"
    cache = load_cache(cache_path)
    todo = [m for m in months() if m["as_of"] not in cache]
    print(f"jev: {len(todo)} months to ask, {len(cache)} cached", flush=True)

    def one(m):
        body = json.dumps({"state": m["payload"], "questions": JEV_QUESTIONS_1M}).encode()
        for attempt in range(5):
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    j = json.loads(r.read())
                if "raw" in j and j["raw"].get("state") == "Completed":
                    rec = {"as_of": m["as_of"], "horizon_months": 1, "ms": j.get("ms"), "raw": j["raw"]}
                    append(cache_path, rec)
                    return rec
                err = j
            except Exception as exc:
                err = str(exc)
            time.sleep(3 * 2 ** attempt)
        raise RuntimeError(f"{m['as_of']}: {str(err)[:200]}")

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, f in enumerate(as_completed([ex.submit(one, m) for m in todo]), 1):
            try:
                f.result()
            except Exception as exc:
                print("failed:", str(exc)[:200], flush=True)
            if i % 20 == 0:
                print(f"{i}/{len(todo)}", flush=True)


def read_jev(raw):
    a = raw["result"]["answers"]
    p = float(a["stocks_beat_bonds"]["noul"])
    t = a["tilt"]
    probs = {k: float(v) for k, v in (t.get("probabilities") or {}).items()}
    offset = sum(TILT_OFFSET.get(k, 0) * v for k, v in probs.items()) if probs else TILT_OFFSET.get(t.get("choice"), 0)
    return {"p": p, "choice": t.get("choice"), "probs": probs, "confidence": float(t.get("confidence", abs(2 * p - 1))), "offset": offset}


def export():
    DATA.mkdir(exist_ok=True)
    com = load_cache(RAW / "committee_1m.jsonl")
    out = {}
    for as_of, r in sorted(com.items()):
        fields, problems = committee.parse_cio(r["cio_raw"])
        out[as_of] = {"economist": committee.parse_view(r["economist_raw"], "economist"), "risk": committee.parse_view(r["risk_raw"], "risk"),
                      "cio": fields, "problems": problems}
    (DATA / "committee_1m.json").write_text(json.dumps({"model": MODEL, "temperature": 0.0, "horizon_months": 1, "months": out}), encoding="utf-8")
    jev = load_cache(RAW / "jev_1m.jsonl")
    jout = {as_of: read_jev(r["raw"]) for as_of, r in sorted(jev.items())}
    (DATA / "jev_1m.json").write_text(json.dumps({"model": "typesafe/jev", "horizon_months": 1, "months": jout}), encoding="utf-8")
    n = len(months())
    print(f"committee {len(out)}/{n} (unusable {sum(1 for v in out.values() if v['problems'])}), jev {len(jout)}/{n}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["committee", "jev", "export"])
    ap.add_argument("--env", default=str(ROOT.parent / "protofin" / ".env"))
    ap.add_argument("--url", default="http://127.0.0.1:8799")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--per-minute", type=float, default=11.0)
    a = ap.parse_args(argv)
    RAW.mkdir(exist_ok=True)
    if a.what == "committee":
        run_committee(a.env, a.workers, a.per_minute)
    elif a.what == "jev":
        run_jev(a.url, a.workers)
    export()


if __name__ == "__main__":
    main()
