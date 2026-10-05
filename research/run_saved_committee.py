"""Run the three-persona committee ONCE, locally, for every month in site/data/backtest_months.json
and save the answers. The public site only replays these files; it never calls a model.

    python research/run_saved_committee.py              # everything (resumes from the cache)
    python research/run_saved_committee.py --limit 3    # first 3 months, to check
    python research/run_saved_committee.py --export     # rebuild the site files from the cache, no calls

Per month:
  * 1 deterministic run (temperature 0)            -> site/data/committee_runs.json  (backtest page)
  * N stochastic runs (temperature 0.2, default 5) -> site/data/stochastic_runs.json (uncertainty page)
Each run is economist ∥ risk manager -> CIO, i.e. 3 calls. The key comes from the local .env.
Every reply is cached in research/out/committee_cache.jsonl, so a crash or a rate limit loses nothing.
"""
import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
import committee  # noqa: E402

MONTHS = os.path.join(BASE, "site", "data", "backtest_months.json")
CACHE = os.path.join(BASE, "research", "out", "committee_cache.jsonl")
OUT_DET = os.path.join(BASE, "site", "data", "committee_runs.json")
OUT_STO = os.path.join(BASE, "site", "data", "stochastic_runs.json")
MODEL = os.environ.get("LLM_MODEL", "gpt-4o")
STOCHASTIC_TEMPERATURE = 0.2
_lock = threading.Lock()


def load_cache():
    recs = {}
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:   # blank or half-written last line
                    continue
                recs[(r["as_of"], r["r"])] = r
    return recs


def chat(client, prompt, temperature, seed, retries=7):
    for attempt in range(retries):
        try:
            r = client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": prompt}],
                                               temperature=temperature, seed=seed, max_tokens=300)
            return r.choices[0].message.content or ""
        except Exception as exc:  # back off on rate limits and transient errors
            if attempt == retries - 1:
                raise
            time.sleep(min(120, 4 * 2 ** attempt))


_next_start = [0.0]


def pace(seconds):
    """Space run starts evenly so the account's tokens-per-minute limit is not hit (retries waste more)."""
    with _lock:
        now = time.time()
        start = max(now, _next_start[0])
        _next_start[0] = start + seconds
    time.sleep(max(0.0, start - now))


def run_one(client, month, r, gap=0.0):
    """r = -1 is the deterministic run; r >= 0 are the stochastic samples."""
    pace(gap)
    temperature, seed = (0.0, 42) if r < 0 else (STOCHASTIC_TEMPERATURE, 1000 + r)
    out = committee.run_committee(month["prompts"], lambda p: chat(client, p, temperature, seed))
    rec = {"as_of": month["as_of"], "r": r, "model": MODEL, "temperature": temperature, "seed": seed,
           "economist_raw": out["economist_raw"], "risk_raw": out["risk_raw"], "cio_raw": out["cio_raw"]}
    with _lock:
        with open(CACHE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    return rec


def export(months, cache, n):
    det, sto = {}, {}
    for m in months:
        d = cache.get((m["as_of"], -1))
        if d:
            fields, problems = committee.parse_cio(d["cio_raw"])
            det[m["as_of"]] = {"economist": committee.parse_view(d["economist_raw"], "economist"),
                               "risk": committee.parse_view(d["risk_raw"], "risk"),
                               "cio": fields, "problems": problems}
        runs = []
        for r in range(n):
            s = cache.get((m["as_of"], r))
            if s:
                fields, problems = committee.parse_cio(s["cio_raw"])
                runs.append({"spy_q": fields["spy_q"], "tlt_q": fields["tlt_q"], "confidence": fields["confidence"],
                             "valid": not problems, "cio": fields["cio"]})
        if runs:
            sto[m["as_of"]] = runs
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for path, body in ((OUT_DET, {"built": stamp, "model": MODEL, "temperature": 0.0, "months": det}),
                       (OUT_STO, {"built": stamp, "model": MODEL, "temperature": STOCHASTIC_TEMPERATURE, "n": n, "months": sto})):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(body, fh)
    print(f"deterministic months: {len(det)} | stochastic months: {len(sto)} "
          f"(complete: {sum(1 for v in sto.values() if len(v) == n)}) of {len(months)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--n", type=int, default=5, help="stochastic runs per month")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--runs-per-minute", type=float, default=11.0, help="~2,400 tokens per run; 11 fits a 30k TPM limit")
    ap.add_argument("--export", action="store_true", help="only rebuild the site files from the cache")
    args = ap.parse_args()
    months = json.load(open(MONTHS, encoding="utf-8"))["months"]
    cache = load_cache()
    if not args.export:
        from dotenv import load_dotenv
        from openai import OpenAI
        load_dotenv(os.path.join(BASE, ".env"))
        client = OpenAI(max_retries=8)   # the client waits as long as the rate-limit headers ask
        # deterministic runs for every month first, then the stochastic samples month by month
        todo = [(m, r) for rs in ([-1], range(args.n)) for m in months[:args.limit] for r in rs if (m["as_of"], r) not in cache]
        print(f"{len(todo)} committee runs to do ({len(todo) * 3} calls), {len(cache)} cached", flush=True)
        done = failed = 0
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(run_one, client, m, r, 60.0 / args.runs_per_minute) for m, r in todo]
            for f in as_completed(futs):
                try:
                    rec = f.result()
                    cache[(rec["as_of"], rec["r"])] = rec
                except Exception as exc:
                    failed += 1
                    print("failed:", str(exc)[:160], flush=True)
                done += 1
                if done % 50 == 0:
                    print(f"{done}/{len(todo)}", flush=True)
        print(f"done; failed {failed}", flush=True)
    export(months, cache, args.n)


if __name__ == "__main__":
    main()
