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

Net CER at 60/40 (difference vs the static mix, 95% range, p). Covariance: 36-month sample covariance (see below).

| | ridge mapping | sign mapping |
|---|---|---|
| STATIC 60/40 | 4.37% | 4.37% |
| PLACEBO | 3.86% (-0.51 [-1.03, -0.10], p 0.01) | 3.86% (-0.51 [-1.03, -0.10], p 0.01) |
| DET | 3.82% (-0.54 [-1.05, -0.15], p 0.00) | 3.82% (-0.54 [-1.05, -0.15], p 0.00) |
| JEV (1-month) | 3.19% (-1.18 [-3.60, +0.65], p 0.25) | 3.86% (-0.51 [-1.03, -0.10], p 0.01) |
| COMMITTEE (1-month) | 4.07% (-0.30 [-3.62, +2.05], p 0.90) | 3.97% (-0.40 [-1.09, +0.28], p 0.25) |
| JEV_12M | 3.07% (-1.30 [-3.34, +0.09], p 0.08) | 3.86% (-0.50 [-1.04, -0.08], p 0.01) |
| COMMITTEE_12M | 3.25% (-1.11 [-3.53, +0.60], p 0.27) | 3.88% (-0.48 [-1.04, -0.03], p 0.03) |

Same ordering at 50/50 and 70/30 (`out/summary.json`).

What this shows:
- **Nothing beats holding the mix.** Every approach, under either mapping and at every mix, has a lower net CER than static 60/40.
- **The machinery alone costs about half a point.** The placebo (historical-average views) loses 0.51 pts a year with p 0.01: the tilts carry no information. It trades no more than static (0.31× vs 0.30× a year), so the loss is the tilting, not the cost.
- **DET ≈ placebo:** the surprises are ignored for SPY in every month.
- **Jev's view has no usable direction.** Under the sign mapping it is the placebo. Under the ridge mapping Ridge read Jev in reverse and lost a further 0.7 pts.
- **The committee is the closest** (−0.30 ridge, −0.40 sign) and beats the placebo through its bond calls, but its range includes zero.
- 46 months can only separate large differences.

## Causal RAG (exploratory)

`CAUSAL_RAG` uses the saved 95-month run from Farnoosh's branch (`data/causal_rag_qwen3.json`: qwen3:4b free stand-in model, reliability gates G3a and G3b failed). Its signal per fund is the net predicted direction of its Supported, Contradicted and Insufficient chains; its IEF signal stands in for TLT. It goes through the same view rule, Ω, Black-Litterman and scoring, and is kept out of the primary Holm family. At 60/40: −0.52 pts vs static with the direction kept (the same as the placebo: k = 0 for both funds in most months), −1.33 pts (p 0.00) when it may be read freely.

## Three-fund set: SPY / IEF / LQD at 45/35/20 (`config_3f.json`)

The deterministic model's and Causal RAG's own universe, with Stage 2's bounds (SPY 20–70, IEF 15–60, LQD 10–40) and Ledoit–Wolf covariance. `collect_3f.py` builds the three-fund masked block and re-asked Jev (139/139) and the gpt-4o committee (139/139) about the three funds; Causal RAG needs no stand-in. Outputs in `out3/`.

| 45/35/20, direction kept | Net CER | vs static |
|---|---|---|
| STATIC | 3.77% | — |
| PLACEBO | 3.18% | −0.59 (p 0.04) |
| DET | 3.18% | −0.59 (p 0.01) |
| JEV | 3.09% | −0.69 (p 0.00) |
| COMMITTEE | 2.75% | −1.03 (p 0.03) |
| CAUSAL_RAG (exploratory) | 3.11% | −0.66 (p 0.01) |

Every range sits below zero. With the plain sample covariance (IEF–LQD correlation about 0.7) the optimizer overreacted and every approach lost about twice as much, so Ledoit–Wolf is kept for three funds.

## Covariance: why the sample estimate

The first runs used Ledoit–Wolf, as Stage 2 does for three assets. With two assets it shrank 40–100% toward equal variances and zero correlation (fully in 11 of 46 months), erasing the SPY–TLT negative correlation (−0.25 in March 2019). Two assets over 36 months is three numbers to estimate, so the plain sample covariance is used (`"covariance": "sample"` in `config.json`; `"ledoit_wolf"` remains available). The ranking did not change; the placebo's cost rose from 0.40 to 0.51 pts and the committee's gap widened from −0.24 to −0.40 (sign mapping).

## Differences from the native evaluations

- Jev's and the committee's outputs are mapped to Q by the same learned rule (ridge or sign mapping), replacing Jev's fixed ±1.5/±3 point table and the committee's direct 12-month views. Their native results are unchanged in `native_backtest/`.
- Ω comes from each approach's own past validation errors, not from development-window errors.
- Jev and the committee have answers from 2004, but training starts in 2015-02 for everyone. A longer history would need distribution-adjusted prices before 2011 (`framework_config_v1.json`, `pinned_price_validity`) and the macro surprises before 2015.
