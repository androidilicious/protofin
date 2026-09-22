"""Does the FOMC hawkishness index measure what it claims?

Check: on statement days, a more hawkish statement (relative to the previous one) should coincide
with a rise in short/medium Treasury yields that day. Yahoo's 5-year yield (^FVX) is used because
FRED is unreachable from this network; the 2-year would be the textbook choice.

    python news_pipeline.py --backfill && python research/fomc_validation.py
"""
import os

import numpy as np
import pandas as pd
import yfinance as yf

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(BASE, "data", "news", "fomc_index.csv")


def main():
    idx = pd.read_csv(INDEX, parse_dates=["date"]).sort_values("date")
    idx["change"] = idx["score"].diff()
    y = yf.download(["^FVX", "^TNX"], start="2007-06-01", auto_adjust=True, progress=False)["Close"].ffill()
    rows = []
    for _, r in idx.iterrows():
        d = r["date"]
        after = y.loc[d:]
        before = y.loc[:d - pd.Timedelta(days=1)]
        if len(after) == 0 or len(before) == 0:
            continue
        d0 = after.index[0]
        if (d0 - d).days > 3:
            continue
        rows.append({"date": d, "score": r["score"], "change": r["change"],
                     "fvx_bps": (after["^FVX"].iloc[0] - before["^FVX"].iloc[-1]) * 100,
                     "tnx_bps": (after["^TNX"].iloc[0] - before["^TNX"].iloc[-1]) * 100})
    df = pd.DataFrame(rows).dropna()
    n = len(df)
    for col in ("fvx_bps", "tnx_bps"):
        c_level = df["score"].corr(df[col])
        c_change = df["change"].corr(df[col])
        t = c_change * np.sqrt(n - 2) / np.sqrt(1 - c_change ** 2)
        print(f"{col}: corr with hawkishness level {c_level:+.3f}, with change vs previous statement {c_change:+.3f} (t={t:+.2f}, n={n})")
    hawk = df[df["change"] > 0.05]
    dove = df[df["change"] < -0.05]
    print(f"statements turning more hawkish (n={len(hawk)}): mean 5y move {hawk.fvx_bps.mean():+.1f} bps")
    print(f"statements turning more dovish  (n={len(dove)}): mean 5y move {dove.fvx_bps.mean():+.1f} bps")
    print(f"index range {idx.score.min():+.2f} to {idx.score.max():+.2f}; most hawkish {idx.loc[idx.score.idxmax(),'date'].date()}, most dovish {idx.loc[idx.score.idxmin(),'date'].date()}")
    df.to_csv(os.path.join(BASE, "research", "out", "fomc_validation.csv"), index=False)


if __name__ == "__main__":
    main()
