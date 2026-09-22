"""Forecast-skill check for the masked replay views (run after masked_replay.py).

Compares the model's view spread (SPY excess minus TLT excess) with the realized 12-month
SPY-minus-TLT return that followed each decision date. Windows overlap, so the t-statistic
uses an effective sample of N/12 and is only a rough guide.
"""
import os

import numpy as np
import pandas as pd
import yfinance as yf

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
HORIZON_DAYS = 252


def main():
    v = pd.read_csv(os.path.join(OUT, "masked_views.csv"), parse_dates=["date"]).set_index("date")
    px = yf.download(["SPY", "TLT"], start="2003-12-01", auto_adjust=True, progress=False)["Close"]
    rows = []
    for d, r in v.iterrows():
        h = px.loc[d:]
        if len(h) <= HORIZON_DAYS:
            continue
        f = (h.iloc[HORIZON_DAYS] / h.iloc[0] - 1) * 100
        rows.append({"date": d, "view_spread": r.spy_excess - r.tlt_excess, "real_spread": f["SPY"] - f["TLT"]})
    df = pd.DataFrame(rows)
    n = len(df)
    ic = df.view_spread.corr(df.real_spread)
    t = ic * np.sqrt(max(n / 12 - 2, 1)) / np.sqrt(1 - ic ** 2)
    hit = float(((df.view_spread > 0) == (df.real_spread > 0)).mean())
    base = float((df.real_spread > 0).mean())
    bear = df[df.view_spread <= 0]
    print(f"decisions with a realized 12m outcome: {n}")
    print(f"correlation view spread vs realized spread: {ic:+.3f} (rank {df.view_spread.corr(df.real_spread, method='spearman'):+.3f}), rough t {t:+.2f}")
    print(f"sign hit rate {hit*100:.1f}% vs always-SPY baseline {base*100:.1f}%")
    print(f"months bearish on SPY vs TLT: {len(bear)}; realized spread after those {bear.real_spread.mean():+.1f}% vs all {df.real_spread.mean():+.1f}%")
    df.to_csv(os.path.join(OUT, "masked_skill.csv"), index=False)


if __name__ == "__main__":
    main()
