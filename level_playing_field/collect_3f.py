"""Three-fund level field (SPY / IEF / LQD, the Stage 2 universe): build the masked month block, then ask the
committee and Jev the one-month question for every month 2015-02..2026-08, once, and save it.

    python -m level_playing_field.collect_3f months                                   # masked blocks (no model)
    python -m level_playing_field.collect_3f committee --env ../protofin/.env         # gpt-4o, temperature 0
    python -m level_playing_field.collect_3f jev --url http://127.0.0.1:8799            # local `wrangler dev` caller
    python -m level_playing_field.collect_3f export                                   # rebuild data/*_3f.json

The block uses the same features and wording as the SPY/TLT block (research/masked_replay.py), extended to three
funds; only relative numbers, no dates, no levels. Every raw reply is cached in raw/*_3f.jsonl.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
VENDOR = ROOT / "native_backtest" / "vendor" / "protofin_approach-2_ce063b8"
sys.path.insert(0, str(VENDOR))
import committee  # noqa: E402  (unchanged approach-2 orchestration and view parser)

FIRST, LAST = "2015-02", "2026-08"
FUNDS = ("SPY", "IEF", "LQD")
RAW, DATA = HERE / "raw", HERE / "data"
MONTHS_FILE = DATA / "months_3f.json"
MODEL = "gpt-4o"
LOOKBACK = 252 * 10
_lock = threading.Lock()
NUM = r"([-+]?\d+(?:\.\d+)?)"


# ------------------------------------------------------------------ masked month blocks
def load_data():
    import yfinance as yf
    import macro_indexes
    px = yf.download(list(FUNDS) + ["^TNX", "^IRX"], start="2002-07-01", auto_adjust=True, progress=False)["Close"].rename(columns={"^TNX": "TNX", "^IRX": "IRX"})
    px[["TNX", "IRX"]] = px[["TNX", "IRX"]].ffill()
    px = px.dropna()
    pct = macro_indexes.regime_series(macro_indexes.load_all())[["EPU_pctl", "GPR_pctl"]].reindex(px.index, method="ffill")
    return px.join(pct)


def features(df, d):
    h = df.loc[:d]
    r = h[list(FUNDS)].pct_change().dropna().iloc[-252:]
    ret = lambda s, n: float((s.iloc[-1] / s.iloc[-n - 1] - 1) * 100)
    look = h.iloc[-LOOKBACK:]
    rank = lambda s, v: float((s < v).mean() * 100)
    f = {a: {"1m": ret(h[a], 21), "3m": ret(h[a], 63), "12m": ret(h[a], 252), "vol": float(r[a].std() * np.sqrt(252) * 100)} for a in FUNDS}
    f["SPY"]["dd"] = float((h["SPY"].iloc[-1] / h["SPY"].iloc[-252:].max() - 1) * 100)
    c = r.corr()
    nan = lambda v: None if np.isnan(v) else float(v)
    return {"f": f, "corr": {"SPY-IEF": float(c.loc["SPY", "IEF"]), "SPY-LQD": float(c.loc["SPY", "LQD"]), "IEF-LQD": float(c.loc["IEF", "LQD"])},
            "cash_pctl": rank(look["IRX"], h["IRX"].iloc[-1]), "long_pctl": rank(look["TNX"], h["TNX"].iloc[-1]),
            "shock_bps": float((h["TNX"].iloc[-1] - h["TNX"].iloc[-63:].mean()) * 100), "curve_bps": float((h["TNX"].iloc[-1] - h["IRX"].iloc[-1]) * 100),
            "epu_pctl": nan(h["EPU_pctl"].iloc[-1]), "gpr_pctl": nan(h["GPR_pctl"].iloc[-1]), "rf_pct": float(h["IRX"].iloc[-1])}


def ordinal(n):
    n = int(round(n))
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def payload_text(x):
    p = lambda v: "n/a" if v is None else f"{ordinal(v)} percentile of the last 10 years"
    f = x["f"]
    line = lambda a, extra="": f"{a} returns: 1-month {f[a]['1m']:+.1f}%, 3-month {f[a]['3m']:+.1f}%, 12-month {f[a]['12m']:+.1f}%; 12-month volatility {f[a]['vol']:.0f}%{extra}.\n"
    return ("SPY is a broad US equity index fund. IEF is a 7-10 year US Treasury bond fund. LQD is a US investment-grade corporate bond fund. "
            "All figures are point-in-time.\n"
            + line("SPY", f"; drawdown from 12-month high {f['SPY']['dd']:.1f}%") + line("IEF") + line("LQD")
            + f"12-month correlations: SPY-IEF {x['corr']['SPY-IEF']:+.2f}, SPY-LQD {x['corr']['SPY-LQD']:+.2f}, IEF-LQD {x['corr']['IEF-LQD']:+.2f}.\n"
            f"Short-term cash rate: {p(x['cash_pctl'])}. Long-term government yield: {p(x['long_pctl'])}; "
            f"it moved {x['shock_bps']:+.0f} bps versus its 3-month average; term spread (long minus cash) {x['curve_bps']:+.0f} bps.\n"
            f"Economic policy uncertainty: {p(x['epu_pctl'])}. Geopolitical risk: {p(x['gpr_pctl'])}.\n"
            f"Cash yield for the excess-return comparison: {x['rf_pct']:.2f}%.")


def build_months():
    df = load_data()
    s = df.index.to_series()
    ends = list(s.groupby(s.index.to_period("M")).last().values)
    out = []
    for d in ends:
        d = pd.Timestamp(d)
        if not (FIRST <= str(d.date())[:7] <= LAST):
            continue
        x = features(df, d)
        out.append({"as_of": str(d.date()), "payload": payload_text(x), "shock_bps": round(x["shock_bps"], 1)})
    DATA.mkdir(exist_ok=True)
    MONTHS_FILE.write_text(json.dumps({"built": pd.Timestamp.utcnow().isoformat(timespec="seconds"), "funds": FUNDS, "months": out}), encoding="utf-8")
    print(f"{len(out)} months {out[0]['as_of']}..{out[-1]['as_of']}")
    print(next(m["payload"] for m in out if m["as_of"].startswith("2019-03")))


def months():
    return json.loads(MONTHS_FILE.read_text(encoding="utf-8"))["months"]


# ------------------------------------------------------------------ committee prompts for three funds (one-month question)
RULES = ("Expected returns are TOTAL returns over the NEXT MONTH only (about 21 trading days), in percent (e.g. 0.8 or -0.5), "
         "judged against one month of the cash yield above (the annual cash yield divided by 12): below that is a bearish view.\n")
UNIVERSE = "SPY (US equities), IEF (7-10 year US Treasuries) and LQD (US investment-grade corporate bonds)"


def prompts_3f(m):
    shock = f"long-term government yield moved {m['shock_bps']:+.0f} bps versus its 3-month average"
    data = f"Point-in-time data (use only this; do not assume facts not given):\n{m['payload']}\nRate-shock signal: {shock}\n"
    nums = lambda pre: "".join(f"{pre}{a}_Return_Percent: [number]\n" for a in FUNDS)
    economist = (f"You are the chief macro economist at a large asset manager, advising an allocation between {UNIVERSE}. "
                 "Give your own independent view; no one else's opinion is available to you.\n" + data + RULES +
                 "Format EXACTLY like this (no markdown):\nEconomist_View: [2 concise sentences arguing a specific macro view]\n" + nums("Economist_"))
    risk = (f"You are the head of risk at a bank's investment arm, reviewing an allocation between {UNIVERSE}. Focus on downside, tail risk, "
            "and what could go wrong. Give your own independent view; no one else's opinion is available to you.\n" + data + RULES +
            "Format EXACTLY like this (no markdown):\nRisk_View: [2 concise sentences on the key risks and what they imply]\n" + nums("Risk_"))
    cio = ("You are the chief investment officer. Two colleagues have given independent views on the same data. "
           f"Weigh them, resolve disagreements, and decide the inputs for a Black-Litterman allocation between {UNIVERSE}.\n" + data + RULES +
           "Confidence describes how much the evidence justifies deviating from a neutral 45/35/20 stance, not how strongly anyone argued.\n\n"
           "Economist (independent): {ECONOMIST_VIEW}\nRisk manager (independent): {RISK_VIEW}\n\n"
           "Format EXACTLY like this (no markdown):\nCIO_Decision: [2 sentence synthesis naming where you sided with whom and why]\n"
           "Grounding_Summary: [1 sentence naming the specific data points that drove this decision]\n"
           + "".join(f"{a}_Expected_Return_Percent: [number]\n" for a in FUNDS) + "CIO_Confidence: [High, Medium, or Low]\n")
    return {"economist": economist, "risk": risk, "cio": cio}


def parse_cio_3f(raw):
    text = re.sub(r"\*\*|__|`", "", raw or "")
    out, problems = {}, []
    for a in FUNDS:
        m = re.search(rf"{a}[_ ]?(?:Expected[_ ]?)?Return[_ ]?Percent\s*[:=]?\s*{NUM}", text, re.I)
        v = float(m.group(1)) if m else None
        if v is None or not -50 <= v <= 50:
            problems.append(f"{a} missing or implausible")
            v = None
        out[a] = v
    c = re.search(r"CIO[_ ]?Confidence\s*[:=]?\s*(High|Medium|Low)", text, re.I)
    out["confidence"] = c.group(1).capitalize() if c else None
    if not out["confidence"]:
        problems.append("confidence missing")
    d = re.search(r"CIO[_ ]?Decision\s*:\s*(.*)", text, re.I)
    out["cio"] = d.group(1).strip() if d else None
    return out, problems


# ------------------------------------------------------------------ Jev questions for three funds
JEV_Q = {
    "spy_beats_ief": {"type": "noul", "instructions": "Over the NEXT MONTH, will SPY (US equities) deliver a higher total return than IEF (7-10 year US Treasuries)?",
                      "criteria": {"true": "SPY outperforms IEF over the next month", "false": "IEF outperforms or matches SPY over the next month"}},
    "lqd_beats_ief": {"type": "noul", "instructions": "Over the NEXT MONTH, will LQD (US investment-grade corporate bonds) deliver a higher total return than IEF (7-10 year US Treasuries)?",
                      "criteria": {"true": "LQD outperforms IEF over the next month", "false": "IEF outperforms or matches LQD over the next month"}},
    "best_fund": {"type": "choice", "instructions": "Which of the three funds will deliver the highest total return over the NEXT MONTH, given only this data?",
                  "criteria": {"SPY": "US equities (SPY) will return the most next month", "IEF": "7-10 year US Treasuries (IEF) will return the most next month",
                               "LQD": "US investment-grade corporate bonds (LQD) will return the most next month"}},
}


def read_jev(raw):
    a = raw["result"]["answers"]
    probs = {k: float(v) for k, v in (a["best_fund"].get("probabilities") or {}).items()}
    return {"p_spy_ief": float(a["spy_beats_ief"]["noul"]), "p_lqd_ief": float(a["lqd_beats_ief"]["noul"]), "best": a["best_fund"].get("choice"),
            "probs": {f: probs.get(f, 0.0) for f in FUNDS}, "confidence": float(a["best_fund"].get("confidence", 0.0))}


# ------------------------------------------------------------------ runners (cached, resumable)
def cache(path):
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


def run_committee(env_path, workers, per_minute):
    from dotenv import load_dotenv
    from openai import OpenAI
    load_dotenv(env_path, override=True)
    client = OpenAI(base_url="https://api.openai.com/v1", max_retries=8)
    path = RAW / "committee_3f.jsonl"
    todo = [m for m in months() if m["as_of"] not in cache(path)]
    print(f"committee: {len(todo)} months ({len(todo) * 3} calls)", flush=True)
    nxt = [0.0]

    def pace():
        with _lock:
            now = time.time(); start = max(now, nxt[0]); nxt[0] = start + 60.0 / per_minute
        time.sleep(max(0.0, start - now))

    def chat(prompt):
        r = client.chat.completions.create(model=MODEL, messages=[{"role": "user", "content": prompt}], temperature=0.0, seed=42, max_tokens=350)
        return r.choices[0].message.content or ""

    def one(m):
        pace()
        o = committee.run_committee(prompts_3f(m), chat)
        append(path, {"as_of": m["as_of"], "model": MODEL, "temperature": 0.0, "seed": 42, "horizon_months": 1,
                      "economist_raw": o["economist_raw"], "risk_raw": o["risk_raw"], "cio_raw": o["cio_raw"]})

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, f in enumerate(as_completed([ex.submit(one, m) for m in todo]), 1):
            try:
                f.result()
            except Exception as exc:
                print("failed:", str(exc)[:200], flush=True)
            if i % 20 == 0:
                print(f"{i}/{len(todo)}", flush=True)


def run_jev(url, workers):
    path = RAW / "jev_3f.jsonl"
    todo = [m for m in months() if m["as_of"] not in cache(path)]
    print(f"jev: {len(todo)} months", flush=True)

    def one(m):
        body = json.dumps({"state": m["payload"], "questions": JEV_Q}).encode()
        err = None
        for attempt in range(5):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST"), timeout=120) as r:
                    j = json.loads(r.read())
                if j.get("raw", {}).get("state") == "Completed":
                    append(path, {"as_of": m["as_of"], "horizon_months": 1, "ms": j.get("ms"), "raw": j["raw"]})
                    return
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


def export():
    n = len(months())
    com = {}
    for as_of, r in sorted(cache(RAW / "committee_3f.jsonl").items()):
        fields, problems = parse_cio_3f(r["cio_raw"])
        com[as_of] = {"economist": committee.parse_view(r["economist_raw"], "economist"), "risk": committee.parse_view(r["risk_raw"], "risk"), "cio": fields, "problems": problems}
    (DATA / "committee_3f.json").write_text(json.dumps({"model": MODEL, "temperature": 0.0, "horizon_months": 1, "funds": FUNDS, "months": com}), encoding="utf-8")
    jev = {as_of: read_jev(r["raw"]) for as_of, r in sorted(cache(RAW / "jev_3f.jsonl").items())}
    (DATA / "jev_3f.json").write_text(json.dumps({"model": "typesafe/jev", "horizon_months": 1, "funds": FUNDS, "months": jev}), encoding="utf-8")
    print(f"committee {len(com)}/{n} (unusable {sum(1 for v in com.values() if v['problems'])}), jev {len(jev)}/{n}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["months", "committee", "jev", "export"])
    ap.add_argument("--env", default=str(ROOT.parent / "protofin" / ".env"))
    ap.add_argument("--url", default="http://127.0.0.1:8799")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--per-minute", type=float, default=11.0)
    a = ap.parse_args(argv)
    RAW.mkdir(exist_ok=True)
    if a.what == "months":
        return build_months()
    if a.what == "committee":
        run_committee(a.env, a.workers, a.per_minute)
    elif a.what == "jev":
        run_jev(a.url, a.workers)
    export()


if __name__ == "__main__":
    main()
