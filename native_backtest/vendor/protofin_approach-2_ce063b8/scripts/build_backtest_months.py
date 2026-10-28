"""Build site/data/backtest_months.json: one masked, point-in-time payload per month since 2004
for the live in-browser backtest, plus the saved gpt-4o masked views for instant replay.

Masked = only relative numbers (returns, vols, correlation, percentile ranks, bps changes); no dates,
names, levels or headlines, so a model with knowledge of history cannot recognise the episode.
Each month carries: the three persona prompts (economist, risk, CIO), sigma, cash rate, regime,
the realised next-month SPY/TLT returns (to score the decision), and the saved gpt-4o view if any.

    python scripts/build_backtest_months.py
"""
import json
import os
import sys

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "research"))
import committee  # noqa: E402
import masked_replay as mr  # noqa: E402

OUT = os.path.join(BASE, "site", "data", "backtest_months.json")
SAVED = os.path.join(BASE, "research", "out", "masked_views.csv")


def main():
    df = mr.load_data()
    dates = [pd.Timestamp(d) for d in mr.month_ends(df.index, mr.START)]
    saved = {}
    if os.path.exists(SAVED):
        sv = pd.read_csv(SAVED, parse_dates=["date"])
        saved = {str(r.date.date()): {"spy_q": float(r.spy_q), "tlt_q": float(r.tlt_q), "confidence": str(r.confidence)} for r in sv.itertuples()}
    months = []
    for i, d in enumerate(dates):
        f = mr.features(df, d)
        if f is None:
            continue
        nxt = dates[i + 1] if i + 1 < len(dates) else None
        if nxt is None:
            continue
        r_spy = float(df.loc[nxt, "SPY"] / df.loc[d, "SPY"] - 1)
        r_tlt = float(df.loc[nxt, "TLT"] / df.loc[d, "TLT"] - 1)
        va, vb, corr = f["a_vol"] / 100, f["b_vol"] / 100, f["corr"]
        sigma = [[va * va, corr * va * vb], [corr * va * vb, vb * vb]]
        payload = mr.payload_text(f).replace(
            "Asset A is a broad equity index fund. Asset B is a long-maturity government bond fund.",
            "SPY is a broad US equity index fund. TLT is a long-maturity US Treasury bond fund.")
        payload = payload.replace("Asset A", "SPY").replace("Asset B", "TLT").replace("between A and B", "between SPY and TLT") + f"\nCash yield for the excess-return comparison: {f['rf_pct']:.2f}%."
        shock = f"long-term government yield moved {f['long_shock_bps']:+.0f} bps versus its 3-month average"
        prompts = committee.build_prompts(payload, shock)
        pct = lambda v: None if v is None else round(float(v), 1)
        epu_p, gpr_p = pct(f["epu_pctl"]), pct(f["gpr_pctl"])
        elevated = (max([p for p in (epu_p, gpr_p) if p is not None] or [0]) >= 90) or (epu_p is not None and gpr_p is not None and min(epu_p, gpr_p) >= 80)
        months.append({
            "i": len(months), "as_of": str(d.date()), "next": str(nxt.date()),
            "rf_pct": round(f["rf_pct"], 3), "sigma": sigma, "regime": "elevated" if elevated else "normal",
            "epu_pctl": epu_p, "gpr_pctl": gpr_p, "shock_bps": round(f["long_shock_bps"], 1),
            "a_12m": round(f["a_12m"], 2), "b_12m": round(f["b_12m"], 2), "a_dd": round(f["a_dd"], 2),
            "r_spy": round(r_spy, 6), "r_tlt": round(r_tlt, 6),
            "prompts": prompts, "payload": payload,
            "saved": saved.get(str(d.date())),
        })
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"built": pd.Timestamp.utcnow().isoformat(timespec="seconds"), "months": months,
                   "note": "masked point-in-time payloads; realised next-month returns included for scoring"}, fh)
    print(f"{len(months)} months -> {OUT} ({os.path.getsize(OUT) // 1024} KB); saved gpt-4o views for {sum(1 for m in months if m['saved'])}")


if __name__ == "__main__":
    main()
