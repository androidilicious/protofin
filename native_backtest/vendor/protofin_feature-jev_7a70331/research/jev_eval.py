"""Evaluate Jev's typed answers from research/out/jev_backtest.json against realised 12-month outcomes.

    python research/jev_eval.py
Checks: calibration, Brier skill vs base rate, AUC, and whether confidence separates good from bad calls.
Base rate is computed on data BEFORE each month (expanding window) so the comparison is fair.
"""
import json, os
import numpy as np

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
log = json.load(open(os.path.join(BASE, "research", "out", "jev_backtest.json"), encoding="utf-8"))["log"]
months = json.load(open(os.path.join(BASE, "site", "data", "backtest_months.json"), encoding="utf-8"))["months"]

rows = []
for i, r in enumerate(log):
    if i + 12 > len(months) or "jev" not in r:
        continue
    a = np.prod([1 + months[k]["r_spy"] for k in range(i, i + 12)]); b = np.prod([1 + months[k]["r_tlt"] for k in range(i, i + 12)])
    rows.append((r["as_of"], r["jev"]["p"], r["jev"]["confidence"], r["jev"]["choice"], 1.0 if a > b else 0.0, (a - b) * 100))
p = np.array([x[1] for x in rows]); c = np.array([x[2] for x in rows]); y = np.array([x[4] for x in rows]); spread = np.array([x[5] for x in rows])
n = len(y)
# base rate known at the time: share of past 12m windows where stocks won (first 24 months use 0.5)
past = np.array([y[:max(0, k - 12)].mean() if k - 12 >= 24 else 0.5 for k in range(n)])

brier = np.mean((p - y) ** 2); brier_base = np.mean((past - y) ** 2); brier_half = np.mean((0.5 - y) ** 2)
order = np.argsort(p); ranks = np.empty(n); ranks[order] = np.arange(1, n + 1)
pos = y == 1; auc = (ranks[pos].sum() - pos.sum() * (pos.sum() + 1) / 2) / (pos.sum() * (~pos).sum())
print(f"months scored: {n} | stocks actually beat bonds in {y.mean()*100:.0f}% of 12m windows")
print(f"Brier: Jev {brier:.3f} | base rate known at the time {brier_base:.3f} | coin flip 0.250   (lower is better)")
print(f"Brier skill vs base rate: {(1 - brier / brier_base) * 100:+.1f}%   (positive = Jev adds information)")
print(f"AUC: {auc:.2f}   (0.50 = no ranking ability)")
print(f"hit rate p>0.5: {((p > 0.5) == (y == 1)).mean()*100:.1f}% | always-stocks: {y.mean()*100:.1f}%")
print("\ncalibration (said -> happened):")
for lo, hi in ((0, .45), (.45, .5), (.5, .55), (.55, .6), (.6, 1.01)):
    m = (p >= lo) & (p < hi)
    if m.sum(): print(f"  said {lo:.2f}-{min(hi,1):.2f}: n={m.sum():3d}  mean said {p[m].mean():.2f}  stocks won {y[m].mean():.2f}")
print("\nconfidence (does it separate good calls?):")
for name, m in (("low", c < np.quantile(c, 1/3)), ("mid", (c >= np.quantile(c, 1/3)) & (c < np.quantile(c, 2/3))), ("high", c >= np.quantile(c, 2/3))):
    print(f"  {name:4s} conf {c[m].mean():.2f}: n={m.sum():3d}  hit rate {(((p[m] > .5) == (y[m] == 1)).mean())*100:.1f}%")
print("\ncorrelation of P(stocks beat bonds) with realised 12m spread:", f"{np.corrcoef(p, spread)[0,1]:+.3f}")
