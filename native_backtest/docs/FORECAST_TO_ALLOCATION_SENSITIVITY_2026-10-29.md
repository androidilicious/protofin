# Forecast-to-Allocation Sensitivity Experiment — 2026-10-29

**Status: DEVELOPMENT DIAGNOSTIC — not a confirmatory result.**
Pre-registered in `native_backtest/config/forecast_to_allocation_sensitivity_preregistration_v1.json` (v1.0,
committed `d641933`, before any scenario was run). Window: development decision months **2019-03..2022-12 (46
months)**. The protected window 2023-01..2026-08 was never opened, never scored, and was not used to choose
anything. Additional cost: **$0**.

---

## Summary

Each approach's investment view was rescaled at the one point where a number enters its native allocator,

> adjusted view = prior view + λ × (original view − prior view),   λ ∈ {0, 0.5, 1, 2}

and the native allocator then did everything else. Nothing was changed except the strength of the view.

**The three architectures attenuate their signals in three different places.**

| | Deterministic | JEV | Committee (secondary) |
|---|---|---|---|
| View the allocator receives, vs its own prior | 35.5 bp a month | 0.25 edge points | 479.1 bp a month |
| Share of that view the allocator passes on | **3.6%** (BL posterior) | 100% (linear in the edge) | **42.4%** (BL posterior) |
| Resulting active position at 1× | 2.07 pp | 1.59 pp | **10.97 pp** |
| Months a position limit binds (of 46) | 1 | **0** | 7 |
| Constraint attenuation at 2× | 1.7% | **0.0%** | **35.1%** |
| Signal's share of monthly return variance | **0.17%** | **0.56%** | 10.16% |

- **The Deterministic model's signal is destroyed inside Black–Litterman, not by its position limits.** Its
  views are large — 35.5 bp a month away from the allocator's own equilibrium — but Ω, estimated from the
  model's own out-of-sample errors, is so large relative to τΣ that the posterior keeps only **3.6%** of them.
  A 35.5 bp view arrives at the optimizer as a 1.3 bp deviation. The 20–70 / 15–60 / 10–40 bounds bind in
  **1 month of 46** and are essentially irrelevant.
- **JEV's allocator is perfectly faithful; its signal was already tiny before it got there.** The capped tilt
  transmits the edge linearly with **zero** constraint attenuation at every λ including 2×, and the ±20 pp cap
  never binds. But the view is shrunk twice upstream: the five-way tilt distribution is averaged into a single
  offset that is 22.1% of the largest available tilt, and that offset is then multiplied by a mean confidence of
  0.325, leaving a signal worth **4.8% of the equilibrium edge**.
- **The Committee is the one architecture where the position limit does the attenuating.** Its posterior keeps
  42.4% of a much larger view, producing a 10.97 pp active position; at 2× the ±20 pp cap clips **35.1%** of the
  proposed response and binds in 21 of 46 months.
- **Stronger signals did not reliably improve anything.** Net CER rose with λ for JEV (4.37 → 4.67 → 4.95) and
  fell for the Deterministic model at 2× (3.67 → 3.56); the Committee peaked at 1× (5.11) and dropped sharply at
  2× (3.98) as the cap bound and turnover rose 22%. **No scenario difference clears 5% in 46 months.** Every
  interval straddles zero.
- **The 0.971 correlation between Deterministic and JEV is a baseline-exposure correlation, not forecast
  agreement.** Their *signal-free* 0× portfolios correlate at **0.9837** — higher than their 1× series — while
  their *signal parts* correlate at **−0.279**. The forecasts mildly disagree; the portfolios barely act on them.

The transmission and attenuation findings are exact, deterministic properties of the allocators. The performance
consequences are not statistically supported. This experiment measures **signal transmission**, not signal
predictive quality.

---

## 1. Where a view enters each native allocator

| Approach | Entry point | Prior view | Original view | Transformation |
|---|---|---|---|---|
| Deterministic (AP1) | `stage2/scoring/stage2_portfolio.py::bl_posterior(sigma, q, omega_diag)`, argument `q` | π_t = δ Σ_t w_eq, w_eq = 45/35/20 | `prediction_excess_return`, System A | q_t(λ) = π_t + λ(q_t − π_t) |
| JEV (AP2B) | `livebacktest.js`: `edge = baseEdge + confidence × offset` | baseEdge = (π₀−π₁)×100 | confidence × offset (points of edge) | offset_t(λ) = λ × offset_t |
| Committee (AP2A) | `allocation.js::allocate` → `blPosterior(pi, sigma, q, confidence)` | π = equilibriumPrior(Σ) | (viewsTotalPct − rf)/100 | q_t(λ) = π_t + λ(q_t − π_t) |

JEV is **not** routed through the Deterministic model's Black–Litterman path. It has its own mechanism:

```
x = ( (edge/100)/δ + S₁₁ − S₀₁ ) / ( S₀₀ + S₁₁ − 2S₀₁ ),    w_SPY = clip(x, 0.40, 0.80)
```

Nothing else moved in any scenario: not the macro observations, the saved agent answers, the covariances, the
confidence levels, the regime confidence gate, τ, δ, Ω, the position limits, the costs or the accounting. Every
scenario was evaluated through the one shared evaluator
(`native_backtest/framework/accounting.simulate_records`, 5 bp per dollar traded against drifted weights,
first month from cash).

### Implementation note on the two JavaScript engines

The native engines were run unchanged through `native_backtest/adapters/node/ap2_sensitivity.mjs`, which rescales
the saved monthly answer and then calls the engine's own `decide()`. Outcome fields (`r_spy`, `r_tlt`, `next`)
are deleted from every month object before `decide()` is called, so a decision cannot read a realised return.
For the Committee the harness converts the scaled excess view back to the total-return percent the native
allocator expects, `viewsTotalPct(λ) = 100·q(λ) + rf`, so that no engine code is modified.

---

## 2. Pre-declared checks

### 1× reproduces what was already archived

| Approach | Quantity | Max absolute difference | Tolerance |
|---|---|---|---|
| Deterministic | π vs archived `pi_*` | 9.91e-17 | 1e-10 |
| Deterministic | μ_BL vs archived `mu_bl_*` | 9.70e-17 | 1e-10 |
| Deterministic | weights vs archived `w_*` | 1.22e-15 | 1e-10 |
| Deterministic | net excess return vs Stage 2's own simulation | 1.67e-16 | 1e-10 |
| JEV | weights vs archived `AP2B.jsonl` | **0.0** | 1e-10 |
| JEV | net excess return vs archived decisions | **0.0** | 1e-10 |
| Committee | weights vs archived `AP2A.jsonl` | 1.11e-16 | 1e-10 |

The Deterministic check is the stronger one: the covariances were rebuilt from the Stage 2 scorer's own
`build_targets` output (Ledoit–Wolf, 36 labels through t−2, macro start 2015-02), and the shared evaluator's net
excess returns match Stage 2's own portfolio simulation to 1.7e-16.

### 0× is signal-neutral — and is *not* the same thing as the native no-signal control

| Approach | 0× adjusted view | 0× weights vs native neutral | Reading |
|---|---|---|---|
| Deterministic | exactly π (μ_BL − π ≤ 1.3e-18) | **max 1.706 pp, mean 0.981 pp** | λ=0 is the native allocator with no incremental view, **not** the static 45/35/20 portfolio |
| JEV | signal-induced edge exactly 0 | 1.1e-16 | λ=0 **is** the 60/40 control |
| Committee | exactly π | 1.1e-16 | λ=0 **is** the 60/40 control |

The Deterministic difference was pre-declared and is legitimate, not an error. At λ=0 the posterior mean is
exactly the allocator's own equilibrium π, but the optimizer maximises against **Σ_post = Σ + M** while π was
defined as δΣw_eq. Those are different quadratic problems, so the optimum sits near the 45/35/20 equilibrium
without being equal to it. Nothing was corrected; three references are reported side by side:

| Deterministic reference | Net CER (pp a year) |
|---|---|
| Static 45/35/20 (the frozen no-signal control) | 3.774 |
| **0× — the native allocator, no incremental view** | **3.636** |
| `BENCH_HISTMEAN_ALLOCATOR` — same allocator, historical-mean views | 3.603 |
| 1× — the model's own views | 3.665 |

This decomposes a number reported earlier. The Signal Value-Added study measured Deterministic 1× against the
static control at **−0.109 pp** and could not separate its parts. It now separates: **−0.138 pp** comes from the
allocator's own prior-only behaviour (the Σ + M effect above), and **+0.029 pp** from the model's views. The
total is unchanged; the attribution is new. Neither part is statistically distinguishable from zero.

---

## 3. Results by signal strength

All figures: 46 development months, net of 5 bp per dollar traded. CER in percentage points a year; weights in
percentage points; turnover annualised one-way; cost annualised in basis points.

### Deterministic Quantitative Model

| Scenario | Net CER | Ann. excess | Vol | Sharpe | Max DD | Turnover | Cost (bp) | Active wt | Dev from 1× |
|---|---|---|---|---|---|---|---|---|---|
| 0× Neutral | 3.636 | 5.233 | 11.30 | 0.463 | −18.42 | 0.269 | 2.69 | 1.472 | 2.743 |
| 0.5× Weaker | 3.665 | 5.293 | 11.41 | 0.464 | −18.51 | 0.364 | 3.64 | 1.251 | 1.327 |
| **1× Original** | **3.665** | **5.325** | **11.52** | **0.462** | **−18.60** | **0.456** | **4.56** | **2.073** | — |
| 2× Stronger | 3.557 | 5.280 | 11.74 | 0.450 | −18.79 | 0.554 | 5.54 | 4.164 | 2.455 |
| *control: static 45/35/20* | 3.774 | 5.431 | 11.51 | 0.472 | −18.53 | 0.269 | 2.69 | — | — |
| *control: historical-mean allocator* | 3.603 | 5.264 | 11.52 | 0.457 | −18.60 | 0.288 | 2.88 | — | — |

### Agentic Workflow — JEV

| Scenario | Net CER | Ann. excess | Vol | Sharpe | Max DD | Turnover | Cost (bp) | Active wt | Dev from 1× |
|---|---|---|---|---|---|---|---|---|---|
| 0× Neutral | 4.365 | 6.804 | 13.97 | 0.487 | −23.96 | 0.302 | 3.02 | 0.000 | 1.586 |
| 0.5× Weaker | 4.527 | 6.909 | 13.80 | 0.500 | −23.89 | 0.280 | 2.80 | 0.793 | 0.793 |
| **1× Original** | **4.675** | **7.007** | **13.66** | **0.513** | **−23.82** | **0.333** | **3.33** | **1.586** | — |
| 2× Stronger | 4.946 | 7.198 | 13.42 | 0.536 | −23.70 | 0.483 | 4.83 | 3.171 | 1.586 |
| *control: static 60/40* | 4.365 | 6.804 | 13.97 | 0.487 | −23.96 | 0.302 | 3.02 | — | — |

JEV's response is exactly linear: the active position is 0.793, 1.586 and 3.171 pp at 0.5×, 1× and 2×. Its
volatility *falls* as the signal strengthens (13.97 → 13.42), so in this sample the tilt was risk-reducing.

### Agent Committee (secondary within-approach variant)

| Scenario | Net CER | Ann. excess | Vol | Sharpe | Max DD | Turnover | Cost (bp) | Active wt | Dev from 1× |
|---|---|---|---|---|---|---|---|---|---|
| 0× Neutral | 4.365 | 6.804 | 13.97 | 0.487 | −23.96 | 0.302 | 3.02 | 0.000 | 10.972 |
| 0.5× Weaker | 4.850 | 7.031 | 13.21 | 0.532 | −23.67 | 0.726 | 7.26 | 6.135 | 4.837 |
| **1× Original** | **5.114** | **7.214** | **12.96** | **0.557** | **−23.63** | **1.130** | **11.30** | **10.972** | — |
| 2× Stronger | 3.975 | 6.016 | 12.78 | 0.471 | −23.60 | 1.378 | 13.78 | 15.569 | 4.597 |

The Committee's response is clearly sub-linear from 1× to 2×: doubling the view adds only 4.60 pp to the active
position (against 10.97 pp from 0× to 1×) because the cap intercepts it, while turnover rises 22% and cost by
2.5 bp a year. Its net CER falls 1.14 pp.

### Statistics — nothing clears 5%

Paired circular block bootstrap, 6-month blocks, 5,000 replications, seed 20261027, δ = 2.5. Every scenario and
control is resampled on the same block draws.

| Comparison (net CER, pp a year) | Deterministic | JEV | Committee |
|---|---|---|---|
| 0× − 1× | −0.029 [−0.332, +0.330] p 0.84 | −0.309 [−1.384, +0.482] p 0.59 | −0.749 [−4.079, +2.082] p 0.67 |
| 0.5× − 1× | +0.000 [−0.151, +0.181] p 0.97 | −0.148 [−0.684, +0.247] p 0.61 | −0.264 [−1.627, +0.984] p 0.70 |
| 2× − 1× | −0.109 [−0.560, +0.264] p 0.63 | +0.271 [−0.511, +1.327] p 0.63 | −1.139 [−2.630, +0.193] p 0.10 |
| 1× − own no-signal control | −0.109 [−0.307, +0.035] p 0.17 | +0.309 [−0.482, +1.384] p 0.59 | +0.749 [−2.082, +4.079] p 0.67 |

Intervals are 95% percentile intervals. **No comparison in this table excludes zero.** The closest are the
Deterministic 0.5× against its static control (p 0.055) and the Committee's 2× against its own 1× (p 0.096);
neither is treated as a finding. Four scenarios for each of three allocators were examined, no multiplicity
correction is applied, and none of these comparisons is confirmatory.

---

## 4. Where the signal is attenuated

### Transmission, per month, against 1×

Forecast change → intermediate (unconstrained) weight change → final constrained weight change. The intermediate
stage is the native allocator's own: for the Deterministic model it is the optimizer's all-free candidate (the
fully invested optimum with the bounds ignored, verified in tests to equal the native optimizer whenever no bound
binds); for the two JavaScript engines it is the engine's own unclipped fully invested SPY weight. No
intermediate stage was invented.

| Approach | Scenario | Δ view vs 1× | Δ intermediate wt | Δ final wt | Constraint attenuation | Months with a binding bound |
|---|---|---|---|---|---|---|
| Deterministic | 0× | 35.53 bp | 2.832 pp | 2.743 pp | 0.36% | 0 |
| Deterministic | 0.5× | 17.76 bp | 1.416 pp | 1.327 pp | 0.71% | 0 |
| Deterministic | 1× | — | — | — | — | 1 (IEF lower) |
| Deterministic | 2× | 35.53 bp | 2.832 pp | 2.455 pp | 1.66% | 3 |
| JEV | 0× | 0.2505 pts | 1.586 pp | 1.586 pp | **0.00%** | 0 |
| JEV | 0.5× | 0.1253 pts | 0.793 pp | 0.793 pp | **0.00%** | 0 |
| JEV | 1× | — | — | — | — | **0** |
| JEV | 2× | 0.2505 pts | 1.586 pp | 1.586 pp | **0.00%** | 0 |
| Committee | 0× | 479.12 bp | 12.392 pp | 10.972 pp | 4.22% | 0 |
| Committee | 0.5× | 239.56 bp | 6.196 pp | 4.837 pp | 8.17% | 1 |
| Committee | 1× | — | — | — | — | 7 (4 lower, 3 upper) |
| Committee | 2× | 479.12 bp | 12.392 pp | **4.597 pp** | **35.12%** | **21** (11 upper, 10 lower) |

No month fell below the 1e-6 ratio floor, so no ratio was formed on a tiny denominator and none had to be flagged.

### The decisive stage, per architecture

**Deterministic — the Black–Litterman posterior.** Mean |q − π| is 35.53 bp a month; mean |μ_BL − π| is
**1.29 bp**. The posterior keeps a mean of **3.6%** (median 4.2%) of the view. The weight on the view is
τΣ against Ω, and Ω here is the sample variance of System A's own out-of-sample forecast errors — large, because
the forecasts are noisy. The allocator is doing exactly what Black–Litterman is supposed to do with an unreliable
view: almost ignore it. The position limits play no part.

**JEV — upstream of the allocator.** There is no posterior step. The shrinkage happens when the answer is built:

| Stage | Value | Share kept |
|---|---|---|
| Largest available tilt | 3.000 points | — |
| Probability-weighted offset | 0.664 points | 22.1% of the largest tilt |
| × mean confidence 0.325 | **0.251 points** | 37.8% of the previous stage |
| Equilibrium edge for scale | 5.172 points | signal is **4.8%** of it |

The allocator then transmits that linearly and without clipping: 0.0626 of a percentage point of SPY weight per
edge point. The engine is a faithful amplifier of an already-tiny number.

**Committee — the position limit.** Its Ω is `c(confidence) × τΣ`, proportional to τΣ rather than estimated from
errors, so the posterior keeps a mean of **42.4%** (median exactly 0.500, which is the Medium-confidence case
Ω = τΣ). That produces a large intermediate response, and the ±20 pp cap then does the attenuating: 4.2% at 0×,
35.1% at 2×, binding in 21 of 46 months at 2×.

### Local sensitivity around 1×

Symmetric difference between the 2× and 0.5× scenarios, per month:

| Approach | Weight change per unit of view | Weight change per unit of λ |
|---|---|---|
| Deterministic | 0.00071 pp per bp (median 0.00062) | 2.45 pp |
| JEV | 0.0625 pp per edge point (median 0.0705) | 1.59 pp |
| Committee | 0.00023 pp per bp (median 0.00013) | 6.29 pp |

The per-unit figures are not comparable across the two view units (basis points of expected excess return against
points of edge). Within the two Black–Litterman allocators they are: the Committee moves **one third** as much
weight per basis point of view as the Deterministic model, because its views are an order of magnitude larger and
its cap truncates the response.

---

## 5. Why Deterministic and JEV move together

| Pair | 1× returns | 0× returns | Native no-signal controls | Signal parts |
|---|---|---|---|---|
| Deterministic vs JEV | **0.9711** | **0.9837** | 0.9825 | **−0.2791** |
| Deterministic vs Committee | 0.9039 | 0.9837 | 0.9825 | −0.2252 |
| JEV vs Committee | 0.9705 | 1.0000 | 1.0000 | +0.8502 |

The signal part is each approach's 1× monthly net excess return minus its own 0× series.

| Approach | Vol 1× | Vol 0× | Vol of the signal part | Signal share of 1× variance | corr(1×, own 0×) |
|---|---|---|---|---|---|
| Deterministic | 11.52% | 11.30% | 0.48% | **0.17%** | 0.9993 |
| JEV | 13.66% | 13.97% | 1.02% | **0.56%** | 0.9975 |
| Committee | 12.96% | 13.97% | 4.13% | 10.16% | 0.9556 |

Against the mechanisms the research question listed:

- **Similar baseline market exposure — supported, and it is the dominant mechanism.** Each approach's 1× series
  is 99.9% / 99.8% correlated with its own signal-free 0× series, and the two 0× series are correlated at 0.9837.
  The observed 0.9711 is essentially the correlation of two similar static stock/bond mixes.
- **Forecasts that agree — not supported.** The signal parts correlate at **−0.279**. The forecasts mildly
  *disagree*, which is why the 1× correlation (0.9711) is *lower* than the 0× correlation (0.9837). Signal
  disagreement pushes the series apart; there is just very little of it.
- **Capped or constrained responses — not the mechanism for these two.** The Deterministic bounds bind in 1 month
  of 46; JEV's cap binds in none. Constraint attenuation is 0.4% and 0.0%.
- **Different signals producing small active positions — supported.** 2.07 pp and 1.59 pp of active weight, worth
  0.17% and 0.56% of return variance.
- **Not attributable to Black–Litterman.** JEV does not use the Deterministic model's allocator. Its attenuation
  is upstream and arithmetically unrelated. Two different architectures arrive at small active positions by two
  different routes, and that coincidence — not a shared allocator — is what produces the similarity.

**The Committee is the internal control that confirms the diagnosis.** Same approach family, same SPY/TLT
universe, same 60/40 neutral portfolio, same cap. Its signal transmits (42.4% posterior retention, 10.97 pp
active, 10.16% of variance) — and its correlation with the Deterministic model falls to **0.9039**. When a signal
actually reaches the portfolio, the similarity breaks. That is direct evidence that the 0.9711 reflects weak
transmission rather than a structural inevitability.

---

## 6. Would stronger transmission help?

Not establishable from this sample, and the three approaches point in different directions.

- JEV's net CER rises monotonically with λ (4.365 → 4.527 → 4.675 → 4.946) while its volatility falls, which
  looks like a signal carrying some information that the engine barely uses. The 2× − 1× difference is
  +0.271 pp with a 95% interval of [−0.511, +1.327].
- The Deterministic model's net CER is flat to 1× and *falls* at 2× (−0.109 pp), and every scenario sits below
  its static control.
- The Committee's net CER peaks at 1× and falls 1.139 pp at 2×, where the cap binds in 21 of 46 months and
  annualised cost rises from 11.30 bp to 13.78 bp.

Costs rise with λ in all three (Deterministic 2.69 → 5.54 bp; JEV 3.02 → 4.83 bp; Committee 3.02 → 13.78 bp), so
stronger transmission is certainly more expensive and only sometimes better. **Transmission is not quality.** A
portfolio can respond strongly to an uninformative view, and a useful view can be attenuated to nothing; this
experiment measures only the second half of that sentence. Whether these views carry information is the Signal
Value-Added study's question, and its answer there was also not statistically clear.

---

## 7. Causal RAG — Pending Genuine Agent Outputs

No scenario was run, and none was estimated, substituted or simulated.

- Genuine qwen3:4b outputs cover **12 of the 95** required months (2015-02..2016-01).
- Both pre-registered reliability gates fail: **G3a** schema-valid call rate 0.9771 against a 0.98 floor (the
  shortfall is entirely the vendored CauseTrace assessor at 0.9401); **G3b** accuracy 0.5667 against 0.80 with 2
  opposite-direction errors against a limit of 1.
- There is therefore no calibrated numerical view series for the 46 development months, which is what a
  sensitivity scenario needs.

The machinery is approach-agnostic and ready: it needs a per-month calibrated numerical view, the allocator's own
prior, and the native weights produced. When genuine outputs for the development window exist, the same scenarios
run unchanged — and any analysis built on gate-failed outputs keeps the designation
**EXPLORATORY — RELIABILITY GATES FAILED**.

Supported, Contradicted and Insufficient are categories, not magnitudes. They will never be multiplied. Scaling
applies only downstream of calibration, to the numerical view.

**Blockers:** 83 of 95 development-replay months are not yet run on the free GPU; the assessor's schema validity;
the Testing Agent's contradicted-fixture accuracy (1 of 9).

---

## 8. Validation

**Independent audit** — `native_backtest/scripts/audit_forecast_to_allocation.py` rebuilds the headline numbers
importing only `numpy` and `pandas`: neither the experiment script nor the evaluation framework. It re-derives the
portfolio accounting from the pinned adjusted closes and the pinned bill series on the published entry and exit
dates (drift, costs, gross and net returns, risk-free), recomputes every metric, re-runs the block bootstrap from
its own sampler, re-derives the transformation algebra, the attenuation ratios, the posterior-retention shares and
the correlations, and checks the 1× reproduction against the archived artifacts.

**357 checks, 0 failures.** Result: `native_backtest/out/sensitivity/audit_forecast_to_allocation.json`.

**Automated tests** — `native_backtest/tests/test_forecast_to_allocation.py` (17 tests): the transformation is the
pre-registered affine blend; the Deterministic intermediate stage equals the native optimizer whenever no bound
binds; 1× reproduces the archived results within 1e-10; 0× is signal-neutral and is *compared with* rather than
assumed equal to each native control; the native position limits hold in every scenario and binding months are
recorded; no trace carries a realised-return column and the harness deletes the outcome fields before `decide()`;
the accounting and costs are internally consistent and start from cash; the protected window appears nowhere;
each approach keeps its own distinct entry point, universe and neutral portfolio, and JEV is not routed through
Black–Litterman; Causal RAG is never reported as computed; no result is called statistically clear without an
interval that excludes zero; and the release manifest still verifies, so nothing frozen moved.

---

## 9. Limitations

1. 46 development months. The intervals are wide and **none of these comparisons is confirmatory**.
2. Four scenarios for each of three allocators were examined. No multiplicity correction is applied and no
   bootstrap p-value here is a claim of significance.
3. The 2× scenario is a counterfactual diagnostic stress test. It is not a recommendation, and no multiplier was
   selected on any criterion.
4. This experiment measures signal transmission, not signal predictive quality.
5. The approaches hold different assets (SPY/IEF/LQD against SPY/TLT) with different neutral portfolios and risk
   structures. Weight responses are comparable only in relative terms, and the two view units (basis points of
   expected excess return, points of edge) are not interchangeable.
6. The Committee is a secondary within-approach variant, not a primary approach.
7. Ω for the Deterministic model is the frozen diagonal estimated from System A's development out-of-sample
   errors. The 3.6% posterior retention is a property of that frozen choice, and a different Ω convention would
   give a different retention; the convention was not varied here because it is frozen.
8. Causal RAG is absent for the reasons in §7.

---

## 10. Reproducing this

```bash
# 1. pinned inputs (SHA-256 verified)
python mvp/run.py fetch

# 2. the experiment: scenarios, native engines, tracing, statistics
python -m native_backtest.scripts.forecast_to_allocation

# 3. the independent rebuild (numpy and pandas only)
python -m native_backtest.scripts.audit_forecast_to_allocation

# 4. the tests
python -m pytest native_backtest/tests/test_forecast_to_allocation.py -q
```

Outputs land in `native_backtest/out/sensitivity/`:
`forecast_to_allocation_sensitivity.json` (the full report), `{ap1,ap2b,ap2a}_transmission_trace.csv` (every
month, every scenario, view through weights), `{ap1,ap2b,ap2a}_scenario_returns.csv` (the evaluated series),
`{ap2b,ap2a}_native_scenarios.json` (the raw native-engine output), `audit_forecast_to_allocation.json`.

Fixed inputs: pre-registration v1.0; archived Deterministic run
`stage2/results/dev_rerun_v4_portfolio_2026-10-27`; vendored engines
`protofin_feature-jev_7a70331` and `protofin_approach-2_ce063b8`; frozen Ω from
`stage2_omega_from_A_development.json`; bootstrap 6-month blocks, 5,000 replications, seed 20261027, δ = 2.5.
