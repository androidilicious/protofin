# Level playing field

Every approach goes through one SPY/TLT pipeline. Only the source of the raw monthly signal differs.

```
raw signal at month-end  →  view Q per fund  →  view uncertainty Ω  →  Black-Litterman around the prior mix  →  weights  →  shared evaluator
(differs per approach)      (same Ridge)        (same rule)            (same settings)                          (same bounds)   (same costs, CER, bootstrap)
```

| Step | Rule (identical for every approach) |
|---|---|
| Raw signal | DET: the 8 macro-surprise z-scores. JEV: P(stocks beat bonds), expected tilt, confidence. COMMITTEE: the CIO's 12-month SPY and TLT views, confidence. PLACEBO: none. |
| View Q | Stage 2's Ridge (frozen alpha grid incl. intercept-only, purged expanding inner CV), trained from 2015-02 on labels through t−2, target = next month's return above cash |
| Ω | mean squared one-step validation error of the chosen alpha, on past months only |
| Black-Litterman | prior mix from `config.json` (default 60/40), P = I, τ = 0.05, δ = 2.5, 36-month Ledoit–Wolf covariance, He–Litterman Σ_BL |
| Weights | bounded mean-variance, bounds = prior ± 20 pts |
| Scoring | `native_backtest/framework`: same calendar, prices, DTB4WK cash, 5 bp per dollar traded, net CER, paired 6-month block bootstrap, Holm |
| Window | development only, 2019-03..2022-12 (46 months); the protected window is never scored |

Controls: **STATIC** is the prior mix rebalanced monthly (no views). **PLACEBO** runs the whole pipeline with Q = historical average, so it shows what the machinery costs on its own.

```
python -m level_playing_field.run          # 60/40
python -m level_playing_field.run --grid   # 50/50, 60/40, 70/30
python -m pytest -q level_playing_field
```

Inputs: run `stage2/scoring/fetch_pinned_inputs.py` with the Stage 2 v3 and native manifests first (see `native_backtest/README.md`).

## Results (development months; not protected-window results)

Net CER, and the difference against the static prior mix (95% bootstrap range, p):

| Prior mix | STATIC | PLACEBO | DET | JEV | COMMITTEE |
|---|---|---|---|---|---|
| 50/50 | 3.31% | 3.05% (−0.26, p 0.35) | 3.01% (−0.30, p 0.27) | 2.40% (−0.91, p 0.33) | 2.56% (−0.75, p 0.50) |
| **60/40** | **4.37%** | 3.97% (−0.40, p 0.06) | 3.93% (−0.44, p 0.03) | 3.26% (−1.10, p 0.15) | 3.41% (−0.96, p 0.33) |
| 70/30 | 5.24% | 4.74% (−0.50, p 0.01) | 4.70% (−0.54, p 0.00) | 3.97% (−1.26, p 0.07) | 4.10% (−1.14, p 0.21) |

Against the placebo (signal value beyond the machinery), 60/40: DET −0.04 pts, JEV −0.71 pts (p 0.32), COMMITTEE −0.56 pts (p 0.54).

What this shows:
- **Same ranking at every mix:** STATIC > PLACEBO ≈ DET > COMMITTEE > JEV. The mix moves every level by about the same amount, so the comparison does not depend on it.
- **No approach beats holding the mix.** Even the placebo loses about 0.4 pts: tilting on historical averages and trading costs money.
- **DET ≈ PLACEBO:** the macro surprises are ignored for SPY in every month and used only lightly for TLT.
- **JEV and COMMITTEE do use their signals** (Ridge picked a data-using alpha for SPY in 45 and 44 of 46 months) and swing SPY between about 50% and 80%, but the swings lost money and doubled turnover.
- Not statistically clear after Holm, and 46 months can only separate large differences.

## Differences from the native evaluations

- Jev's and the committee's outputs are mapped to Q by the same learned Ridge, replacing Jev's fixed ±1.5/±3 point table and the committee's direct 12-month views. Their native results are unchanged in `native_backtest/`.
- Ω comes from each approach's own past validation errors, not from development-window errors.
- Jev and the committee have answers from 2004, but training starts in 2015-02 for everyone. A longer history would need distribution-adjusted prices before 2011 (`framework_config_v1.json`, `pinned_price_validity`) and the macro surprises before 2015.
