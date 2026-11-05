# Corrected primary model v1

The primary capstone specification is `corrected-primary-v1`, recorded in
`primary_spec.json`. Its numerical pipeline begins with the existing clipping-only
candidate and adds explicit policy history and variation requirements. The
original 23.99% result is an **unstable diagnostic comparison**, not the final
corrected result. `clip_only` remains an isolated comparison, not an alias for
the corrected primary.

## Fixed rules

- Keep the existing Growth/Inflation surprises, ANFCI/GPR, policy-path fields
  and existing surprise-by-risk interactions; add no signal or learner.
- Train on completed one-month total-return targets, starting February 2015,
  with at least 36 completed outer targets. Inner chronological folds embargo
  incomplete targets at their own decision cutoffs.
- Within each fold, fill missing inputs with training medians (zero only for
  wholly missing columns), clip training and validation/current inputs to that
  training fold's 1st/99th percentiles, then center/scale on clipped training
  rows with population standard deviation. Never cap targets or forecasts.
- Before enabling a policy feature, require at least **12 distinct original
  source snapshots**, **three distinct values at 0.01-percentage-point resolution**,
  observed-only standard deviation of at least **0.01 percentage points**, and
  processed training standard deviation of at least **0.01 percentage points**.
  Each source date counts once per feature. Median fills and carried-forward-only
  rows do not create observed history. Original source dates after their historical
  decision cutoff cannot enter. These checks are refit within every tuning fold.
- Distinct values use NumPy's `rint(value / 0.01)` bins; thresholds are inclusive.
  Twelve snapshots and one-basis-point resolution/variation are fixed engineering
  safeguards, not validated optimal thresholds. They were recorded before this
  new rule's development run and were not searched to maximize returns.
- Unsupported or numerically constant features have both training and prediction
  columns zeroed, so their fitted contributions are exactly zero.
- Retain Ridge penalties `[0.01, 0.1, 1, 10, 100]`, per-asset chronological MSE
  tuning and deterministic tie order. Targets remain monthly decimal returns.
- Rebuild the corrected model's entire prior-error history from its first
  forecast. BL waits for 12 completed errors and uses their sample variance;
  it does not inherit error estimates from the unstable original model.
- Retain 36-month covariance, BL τ 0.05/risk aversion 2.5, initial 45/35/20 mix,
  bounds 20–70/15–60/10–40%, 1% grid, optimizer turnover penalty 0.00005 and
  5bp per dollar traded. Preserve continuous drifted holdings, next-trading-close
  execution and multiplicative transaction costs. Exact parameters are in JSON.

## Evaluation and freeze

The corrected model is chosen for its numerical rules, not because it beats
the original return. Report all results, including lower returns or poor forecasts.

The first fixed-rule rerun covers **44 common holdings, May 2019–December 2022**:

| Version | Net total return | Daily max drawdown | Average monthly turnover |
| --- | ---: | ---: | ---: |
| Corrected primary v1 | 12.63% | −24.21% | 19.73% |
| Historical mean → BL | 14.59% | −22.12% | 2.15% |
| Fixed 45/35/20 | 16.59% | −21.30% | 2.34% |
| Fixed 60/40 | 22.82% | −21.19% | 2.47% |
| SPY only | 38.88% | −33.72% | 0.00% |
| Clipping-only diagnostic | 13.32% | −21.84% | 17.30% |
| Original unstable diagnostic | 23.99% | −21.42% | 10.74% |

The corrected maximum absolute raw forecast is **4.32%**, with **0/171** forecasts
above the 20% warning threshold over all 57 forecast months and **0/132** on
portfolio dates. All recorded numerical acceptance checks pass. However, on the
44 portfolio dates, OOS R² against the matched historical mean is **−0.053 for
SPY, −0.307 for IEF and −0.070 for LQD**; the longer forecast sample is also
negative for all three. MAE also exceeds the mean for each asset in both samples.
Thus **no asset meets the predefined descriptive predictive-improvement rule**.

The corrected allocation reaches at least one bound in 30/44 months (68.18%).
Its higher turnover and deeper drawdown show that correcting numerical instability
does not automatically improve portfolio quality. These outcomes were accepted
without changing the thresholds or restoring the unstable original forecast.

Use both the full matched forecast sample (including allocation warm-up) and the
common portfolio-date sample. Per asset, report MAE, RMSE, OOS R² versus the same-date
expanding historical mean, largest absolute forecast and the count above 20%.
Calendar-year checks and policy activation reasons remain visible. For a descriptive
forecast-improvement claim, require OOS R² > 0 and MAE no worse than the mean in
**both** cohorts. This does not establish statistical significance or independence.

Compare corrected portfolios with expanding mean through BL, fixed 45/35/20,
60/40, SPY and prior-only BL on identical continuous dates. Keep clipping-only
and the original as labeled diagnostics. Report net return, daily drawdown,
turnover, costs, allocation-bound frequency and calendar years.

Numerical acceptance requires finite forecasts, reconciled feature contributions,
zero disabled-feature contributions, prior-only target/preprocessing/error timing,
reconciled allocations/costs, and zero 20% warning flags in both development
cohorts. A failure is reported and blocks freezing; it never silently triggers a
forecast cap, a benchmark fallback or a threshold search.

`primary_freeze.json` records the successful development run, chosen specification,
code/data/dependency fingerprints, environment and claim outcomes. The freeze
command creates a new record exclusively; rerunning verifies an existing record
instead of overwriting it. Source/spec/input mismatches block a development rerun
and site packaging until handled as a separately documented new version.

The primary was selected after prior development diagnostics. Freezing it now
does not make those results independent evidence. No January 2023-onward holding
month is evaluated by these commands. Before a separately authorized reserved
evaluation, confirm whether the team has inspected that period, verify the freeze,
and commit to reporting outcomes without retuning. Revised macro histories and
assumed availability lags remain a separate limitation.

## Reproduce and verify

Use the Python environment recorded in the freeze and `requirements-primary.txt`.
From `deterministic_mvp`:

```sh
python3 src/research_backtest.py
python3 src/corrected_primary.py freeze
python3 src/corrected_primary.py verify-freeze
node site/scripts/build-research.mjs "$PWD/research/outputs"
python3 -m unittest discover -s tests -p 'test_research*.py' -v
python3 -m unittest discover -s tests -p 'test_corrected_primary.py' -v
node site/scripts/test-research-stability.mjs
```

The separate Model Comparison experiment is refreshed for shared-code fingerprints;
its information set and estimator rules are unchanged. The legacy MVP command/page
remains an explicitly labeled archive. It is not the corrected primary entry point.
