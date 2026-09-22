"""Route 3: masked historical replay of the LLM committee with leakage probes.

Every month since 2004 the model sees a payload built ONLY from relative and rank features
(returns, vols, correlation, percentile ranks, basis-point changes). No dates, tickers,
price levels, yield levels or headlines. Two checks measure whether the mask holds:

  probe   a separate call asks the model to guess the calendar year from the masked payload.
          Chance level over 2004-2026 is ~13% within +/-1 year; a much higher hit rate means
          the payload still identifies the episode and the replay is contaminated.
  mirror  on every k-th month the signs of returns, drawdown and rate change are flipped.
          A leak-free reasoner should flip its view roughly symmetrically; asymmetry means it
          recognized the episode from the unflipped numbers.

Outputs (research/out/):
  masked_views.csv          date, spy_q, tlt_q (TOTAL 12m returns = excess + cash), confidence,
                            probe_year, probe_error, rationale   -> feed to backtest.py --views-file
  masked_replay_cache.jsonl every model reply (resume-safe; delete to redo)
  masked_replay_summary.json probe and mirror statistics

Usage:
  python research/masked_replay.py --dry-run --limit 2       # print payloads, no API calls
  python research/masked_replay.py --limit 5                  # small paid run
  python research/masked_replay.py                            # full run (~300 + ~50 calls)
  python research/masked_replay.py --mask coarse              # bucketed numbers, weaker signal
"""
import argparse
import concurrent.futures as cf
import json
import os
import re
import sys
import threading

import numpy as np
import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import macro_indexes  # noqa: E402

load_dotenv()
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "research", "out")
CACHE = os.path.join(OUT, "masked_replay_cache.jsonl")
MODEL = os.getenv("LLM_MODEL", "gpt-4o")
START = "2004-01-01"
MIRROR_EVERY = 6         # mirror test on every 6th month
LOOKBACK = 252 * 10      # trailing window for percentile ranks (trading days)
NUMBER = re.compile(r"[-+]?\d+(?:\.\d+)?")
_lock = threading.Lock()


# ------------------------------------------------------------------ features
def load_data():
    px = yf.download(["SPY", "TLT", "^TNX", "^IRX"], start="2002-07-01", auto_adjust=True,
                     progress=False)["Close"].rename(columns={"^TNX": "TNX", "^IRX": "IRX"})
    px[["TNX", "IRX"]] = px[["TNX", "IRX"]].ffill()
    px = px.dropna()
    idx = macro_indexes.load_all()
    pct = macro_indexes.regime_series(idx)[["EPU_pctl", "GPR_pctl"]]
    pct = pct.reindex(px.index, method="ffill")
    return px.join(pct)


def month_ends(index, start):
    s = index[index >= pd.Timestamp(start)].to_series()
    return list(s.groupby(s.index.to_period("M")).last().values)


def pct_rank(series, value):
    return float((series < value).mean() * 100)


def features(df, d):
    """Point-in-time relative features as of date d (uses rows <= d only)."""
    h = df.loc[:d]
    if len(h) < 260:
        return None
    a, b = h["SPY"], h["TLT"]
    r = h[["SPY", "TLT"]].pct_change().dropna().iloc[-252:]
    ret = lambda s, n: float((s.iloc[-1] / s.iloc[-n - 1] - 1) * 100)
    look = h.iloc[-LOOKBACK:]
    return {
        "a_1m": ret(a, 21), "a_3m": ret(a, 63), "a_12m": ret(a, 252),
        "b_1m": ret(b, 21), "b_3m": ret(b, 63), "b_12m": ret(b, 252),
        "a_vol": float(r["SPY"].std() * np.sqrt(252) * 100),
        "b_vol": float(r["TLT"].std() * np.sqrt(252) * 100),
        "corr": float(r.corr().iloc[0, 1]),
        "a_dd": float((a.iloc[-1] / a.iloc[-252:].max() - 1) * 100),
        "cash_pctl": pct_rank(look["IRX"], h["IRX"].iloc[-1]),
        "long_pctl": pct_rank(look["TNX"], h["TNX"].iloc[-1]),
        "long_shock_bps": float((h["TNX"].iloc[-1] - h["TNX"].iloc[-63:].mean()) * 100),
        "curve_bps": float((h["TNX"].iloc[-1] - h["IRX"].iloc[-1]) * 100),
        "epu_pctl": float(h["EPU_pctl"].iloc[-1]) if not np.isnan(h["EPU_pctl"].iloc[-1]) else None,
        "gpr_pctl": float(h["GPR_pctl"].iloc[-1]) if not np.isnan(h["GPR_pctl"].iloc[-1]) else None,
        "rf_pct": float(h["IRX"].iloc[-1]),   # NOT shown to the model; used to convert views
    }


def mirror(f):
    m = dict(f)
    for k in ("a_1m", "a_3m", "a_12m", "b_1m", "b_3m", "b_12m", "long_shock_bps"):
        m[k] = -f[k]
    m["a_dd"] = 0.0 if f["a_dd"] < -0.5 else f["a_dd"]   # a mirrored rally has no drawdown
    return m


def coarsen(f):
    c = dict(f)
    for k in ("a_1m", "a_3m", "a_12m", "b_1m", "b_3m", "b_12m", "a_dd"):
        c[k] = round(f[k] / 5) * 5
    for k in ("a_vol", "b_vol"):
        c[k] = round(f[k] / 5) * 5
    for k in ("cash_pctl", "long_pctl", "epu_pctl", "gpr_pctl"):
        c[k] = None if f[k] is None else round(f[k] / 10) * 10
    for k in ("long_shock_bps", "curve_bps"):
        c[k] = round(f[k] / 25) * 25
    c["corr"] = round(f["corr"] * 4) / 4
    return c


def ordinal(n):
    n = int(round(n))
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def payload_text(f):
    p = lambda v: "n/a" if v is None else f"{ordinal(v)} percentile of the last 10 years"
    return (
        "Asset A is a broad equity index fund. Asset B is a long-maturity government bond fund. "
        "All figures are point-in-time.\n"
        f"Asset A returns: 1-month {f['a_1m']:+.1f}%, 3-month {f['a_3m']:+.1f}%, 12-month {f['a_12m']:+.1f}%; "
        f"12-month volatility {f['a_vol']:.0f}%; drawdown from 12-month high {f['a_dd']:.1f}%.\n"
        f"Asset B returns: 1-month {f['b_1m']:+.1f}%, 3-month {f['b_3m']:+.1f}%, 12-month {f['b_12m']:+.1f}%; "
        f"12-month volatility {f['b_vol']:.0f}%.\n"
        f"12-month correlation between A and B: {f['corr']:+.2f}.\n"
        f"Short-term cash rate: {p(f['cash_pctl'])}. Long-term government yield: {p(f['long_pctl'])}; "
        f"it moved {f['long_shock_bps']:+.0f} bps versus its 3-month average; "
        f"term spread (long minus cash) {f['curve_bps']:+.0f} bps.\n"
        f"Economic policy uncertainty: {p(f['epu_pctl'])}. Geopolitical risk: {p(f['gpr_pctl'])}."
    )


VIEW_PROMPT = """You are an investment committee. Using ONLY the data below, give 12-month expected returns for two assets, stated as EXCESS return over the cash rate, in percent.
{payload}

Format EXACTLY like this (no markdown):
Rationale: [2 sentences naming the data points that drive the view]
A_Excess_Return_Percent: [number]
B_Excess_Return_Percent: [number]
Confidence: [High, Medium, or Low]
"""

PROBE_PROMPT = """The following market snapshot is real but anonymized. Which calendar year between 2004 and 2026 is it most likely from?
{payload}

Answer with a single four-digit year only."""


# ------------------------------------------------------------------ model
def call(client, prompt, max_tokens, retries=6):
    import time
    for attempt in range(retries):
        try:
            r = client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": prompt}],
                                               temperature=0.0, seed=42, max_tokens=max_tokens)
            return r.choices[0].message.content or ""
        except Exception as exc:
            if "429" not in str(exc) and "rate" not in str(exc).lower() or attempt == retries - 1:
                raise
            time.sleep(5 * 2 ** attempt)   # 5, 10, 20, 40, 80, 160 s


def parse_view(text):
    """Regex over the whole reply, so single-line replies parse too."""
    out = {"rationale": None, "a": None, "b": None, "confidence": None}
    m = re.search(r"Rationale:\s*(.*?)\s*A_Excess_Return_Percent:", text, re.S)
    out["rationale"] = m.group(1).strip() if m else None
    for lab, k in (("A_Excess_Return_Percent:", "a"), ("B_Excess_Return_Percent:", "b")):
        m = re.search(re.escape(lab) + r"\s*([-+]?\d+(?:\.\d+)?)", text)
        out[k] = float(m.group(1)) if m else None
    m = re.search(r"Confidence:\s*(High|Medium|Low)", text, re.I)
    out["confidence"] = m.group(1).capitalize() if m else None
    out["ok"] = out["a"] is not None and out["b"] is not None and out["confidence"] is not None \
        and -50 <= out["a"] <= 50 and -50 <= out["b"] <= 50
    return out


def load_cache():
    done = {}
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                done[(rec["date"], rec["kind"], rec["mask"])] = rec
    return done


def save(rec):
    with _lock:
        with open(CACHE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--mask", default="fine", choices=["fine", "coarse"])
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    df = load_data()
    dates = [pd.Timestamp(d) for d in month_ends(df.index, START)]
    if args.limit:
        dates = dates[:: max(1, len(dates) // args.limit)][: args.limit]

    tasks = []   # (date, kind, features)
    for i, d in enumerate(dates):
        f = features(df, d)
        if f is None:
            continue
        f2 = coarsen(f) if args.mask == "coarse" else f
        tasks.append((d, "view", f2))
        tasks.append((d, "probe", f2))
        if i % MIRROR_EVERY == 0:
            tasks.append((d, "mirror", mirror(f2)))

    if args.dry_run:
        for d, kind, f in tasks[:4]:
            print(f"\n=== {d.date()} [{kind}] (model never sees the date) ===")
            print(payload_text(f))
        print(f"\n{len(tasks)} calls would be made for {len(dates)} months (mask={args.mask})")
        return

    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    done = load_cache()
    todo = [(d, k, f) for d, k, f in tasks if (str(d.date()), k, args.mask) not in done]
    print(f"{len(tasks)} calls total, {len(todo)} to run, {len(done)} cached")

    def work(item):
        d, kind, f = item
        prompt = (PROBE_PROMPT if kind == "probe" else VIEW_PROMPT).format(payload=payload_text(f))
        try:
            text = call(client, prompt, 20 if kind == "probe" else 200)
            rec = {"date": str(d.date()), "kind": kind, "mask": args.mask, "raw": text,
                   "rf_pct": f["rf_pct"]}
            if kind == "probe":
                m = re.search(r"(20\d\d)", text)
                rec["probe_year"] = int(m.group(1)) if m else None
            else:
                rec.update(parse_view(text))
            save(rec)
            return rec
        except Exception as exc:
            return {"date": str(d.date()), "kind": kind, "error": str(exc)}

    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        for n, rec in enumerate(ex.map(work, todo), 1):
            if "error" in rec:
                print("ERROR", rec["date"], rec["kind"], rec["error"][:120])
            if n % 25 == 0:
                print(f"  {n}/{len(todo)} done")

    # ---------------- assemble outputs
    done = load_cache()
    for rec in done.values():                      # re-parse with the current parser
        if rec["kind"] in ("view", "mirror") and rec.get("raw") is not None:
            rec.update(parse_view(rec["raw"]))
    rows, probe_err, probe_hit, mirror_pairs = [], [], [], []
    for d in dates:
        k = str(d.date())
        v = done.get((k, "view", args.mask))
        p = done.get((k, "probe", args.mask))
        m = done.get((k, "mirror", args.mask))
        if p and p.get("probe_year"):
            err = abs(p["probe_year"] - d.year)
            probe_err.append(err)
            probe_hit.append(err <= 1)
        if v and v.get("ok"):
            rows.append({"date": k, "spy_q": round(v["a"] + v["rf_pct"], 2), "tlt_q": round(v["b"] + v["rf_pct"], 2),
                         "spy_excess": v["a"], "tlt_excess": v["b"], "confidence": v["confidence"],
                         "probe_year": p.get("probe_year") if p else None, "actual_year": d.year,
                         "rationale": v["rationale"]})
            if m and m.get("ok"):
                mirror_pairs.append((v["a"], m["a"], v["b"], m["b"]))

    views = pd.DataFrame(rows)
    views.to_csv(os.path.join(OUT, "masked_views.csv"), index=False)

    summary = {"model": MODEL, "mask": args.mask, "months": len(dates), "valid_views": len(views),
               "probe": {"n": len(probe_err),
                         "hit_within_1y_%": round(100 * float(np.mean(probe_hit)), 1) if probe_hit else None,
                         "chance_within_1y_%": round(100 * 3 / 23, 1),
                         "mean_abs_year_error": round(float(np.mean(probe_err)), 2) if probe_err else None,
                         "chance_mean_abs_year_error": round(float(np.mean([abs(y - g) for y in range(2004, 2027) for g in range(2004, 2027)])), 2)}}
    if mirror_pairs:
        mp = np.array(mirror_pairs)
        corr = lambda x, y: round(float(np.corrcoef(x, y)[0, 1]), 3) if len(x) >= 3 and x.std() > 0 and y.std() > 0 else None
        summary["mirror"] = {"n": len(mp),
                             "corr_A_orig_vs_flipped": corr(mp[:, 0], mp[:, 1]),
                             "corr_B_orig_vs_flipped": corr(mp[:, 2], mp[:, 3]),
                             "mean_A_orig_plus_flipped": round(float((mp[:, 0] + mp[:, 1]).mean()), 2),
                             "mean_B_orig_plus_flipped": round(float((mp[:, 2] + mp[:, 3]).mean()), 2),
                             "note": "corr near -1 and sums near 0 mean symmetric, leak-free reasoning"}
    if len(views):
        summary["views"] = {"mean_spy_excess": round(float(views.spy_excess.mean()), 2),
                            "mean_tlt_excess": round(float(views.tlt_excess.mean()), 2),
                            "confidence_counts": views.confidence.value_counts().to_dict()}
    with open(os.path.join(OUT, "masked_replay_summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
