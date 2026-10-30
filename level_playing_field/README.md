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
python -m level_playing_field.run                         # 60/40, both mappings
python -m level_playing_field.run --grid --mapping sign    # 50/50, 60/40, 70/30; one mapping
python -m level_playing_field.collect_1m jev              # re-ask the one-month question (cached); also: committee
python -m pytest -q level_playing_field
```

Inputs: run `stage2/scoring/fetch_pinned_inputs.py` with the Stage 2 v3 and native manifests first (see `native_backtest/README.md`).

## Results (development months 2019-03..2022-12; not protected-window results)

Jev and the committee were re-asked the **one-month** question for every month 2015-02..2026-08 (`collect_1m.py`; 139/139 each, Jev via a local `wrangler dev` caller, the committee on gpt-4o-2024-08-06 at temperature 0). Their original 12-month answers are kept as `*_12M` for comparison.

Two mappings from raw signal to view Q, both identical across approaches:
- **ridge**: Stage 2's Ridge on all of the approach's raw numbers. It may learn any sign, so it can read a reliably wrong signal in reverse.
- **sign**: Q = average + k × (stated view − its mean), k ≥ 0 fitted on past months. The approach's stated direction is never inverted; an anti-predictive signal collapses to the placebo (k = 0). This is the stricter test of "does the approach's own view help".

Net CER at 60/40 (difference vs the static mix, 95% range, p):

| | ridge mapping | sign mapping |
|---|---|---|
| STATIC 60/40 | **4.37%** | **4.37%** |
| PLACEBO | 3.97% (−0.40, p 0.06) | 3.97% (−0.40, p 0.06) |
| DET | 3.93% (−0.44 [−0.94, −0.03], p 0.03) | 3.93% (same: DET has no stated direction, Ridge is its model) |
| JEV (1-month) | 3.28% (−1.08 [−3.61, +0.80], p 0.33) | 3.97% (−0.40, p 0.06): k = 0 almost everywhere, i.e. the placebo |
| COMMITTEE (1-month) | 4.15% (−0.21 [−3.37, +2.03], p 0.94) | 4.13% (−0.24 [−1.11, +0.66], p 0.56) |
| JEV_12M | 3.26% (−1.10) | 3.98% (−0.38) |
| COMMITTEE_12M | 3.41% (−0.96) | 4.00% (−0.36) |

Same ordering at 50/50 and 70/30 (`out/summary.json`).

What this shows:
- **Nothing beats holding the mix.** Every approach, under either mapping and at every mix, has a lower net CER than static 60/40. The placebo alone costs about 0.4 pts: tilting on historical averages plus trading.
- **DET ≈ placebo:** the surprises are ignored for SPY in every month.
- **Jev's view has no usable direction.** Under the sign mapping k = 0, so Jev becomes the placebo. Under the ridge mapping Ridge read Jev in reverse (its tilt correlated −0.16 with next-month SPY in 2015–2019) and that lost 0.7 pts more.
- **The committee's one-month view is the closest to break-even** (−0.21 / −0.24 pts) but with a very wide range (the committee swings SPY 49–80%), so it is indistinguishable from zero.
- **The horizon mattered for the committee, not for Jev:** re-asking the committee for one month improved it from −0.96 to −0.21 under ridge; Jev was unchanged.
- 46 months can only separate large differences; none of these is statistically clear.

## Differences from the native evaluations

- Jev's and the committee's outputs are mapped to Q by the same learned rule (ridge or sign mapping), replacing Jev's fixed ±1.5/±3 point table and the committee's direct 12-month views. Their native results are unchanged in `native_backtest/`.
- Ω comes from each approach's own past validation errors, not from development-window errors.
- Jev and the committee have answers from 2004, but training starts in 2015-02 for everyone. A longer history would need distribution-adjusted prices before 2011 (`framework_config_v1.json`, `pinned_price_validity`) and the macro surprises before 2015.
