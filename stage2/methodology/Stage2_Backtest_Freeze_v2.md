# Stage 2 Backtest Freeze v2.0

**Project:** Duke MIDS / BNY Macro-Financial Capstone  
**Freeze date:** 2026-10-27  
**Status:** Methodology frozen; new market/signal source files must be snapshotted and hashed before the first scored run.

## 1. Freeze principle

The **only experimental treatment is the signal feature set**. The asset universe, target, timing, model class, training rule, hyperparameter procedure, allocator, transaction-cost accounting, benchmarks, scoring dates, and evaluation metrics are held fixed.

After a scored Stage-2 test result is viewed, no frozen parameter may be changed unless the version is incremented and **every system is rerun**. A genuine implementation bug may be fixed only with a written bug note; all affected prior outputs are invalidated.

## 2. Frozen universe and timing

- Assets: **SPY, IEF, LQD**
- Decision snapshot: **20:00 ET on the last trading day of each month**
- Any feature must satisfy `available_at <= decision_time`.
- Execute/rebalance at the **official close of the first trading day after the decision**.
- Hold until the official close of the first trading day after the next month-end decision.
- Target: asset **total return** over the exact holding interval minus the **1-month T-bill cash return** accrued over the same dates.
- At decision month `t`, training may use only completed labels through **`t-2`**.

This timing deliberately removes same-close trading and prevents the still-unfinished `t-1` holding-period return from leaking into training.

## 3. Frozen sample

- Balanced same-definition macro history begins: **2015-02**
- Initial 48 completed training labels: decision months **2015-02 through 2019-01**
- First scored forecast: **2019-03**
- Development decisions: **2019-03 through 2022-12**
- Historical pseudo-OOS test decisions: **2023-01 through 2026-08**
- Prospective evidence begins at the first month-end for which the complete A/B/C/D signal-generation artifacts and this config were frozen *before* the decision timestamp.

The 2019-2022 period is development because it has already influenced architecture/method decisions. It is not called a final test.

## 4. System A — frozen baseline

**A = 8 macro surprise features only:**

1. NFP
2. Retail Sales
3. Industrial Production
4. ISM Manufacturing
5. CPI
6. Core CPI
7. PPI Final Demand
8. AHE Total Private

Primary A **does not include** reconstructed policy 3M/6M, ANFCI, or GPR. This keeps the baseline aligned with the Stage-1 balanced architecture and avoids introducing revision/provenance issues into the baseline.

Macro construction:

- Surprise = first-print actual − Bloomberg median consensus.
- Standardize each release using the **prior 12 releases only**; current release excluded.
- Sample standard deviation (`ddof=1`).
- If an indicator has multiple releases in one calendar month, use their **mean z-score**.
- No-release month remains missing until model scaling; after training-only scaling, missing = **0**.
- **No winsorization in Primary.** `[-3,+3]` winsorization is robustness only.

## 5. System B — frozen conventional signals

Five predeclared conventional features:

1. **Credit spread level** — Baa corporate yield minus 10Y Treasury level.
2. **Credit spread 3M change** — current level minus three calendar months earlier.
3. **10Y−3M Treasury curve slope**.
4. **VRP proxy** — `VIX²/12 − trailing 22-trading-day realized variance`, with both terms in monthly percent-squared units.
5. **Own-asset 12M momentum** — trailing 12-month excess total return for the asset being forecast.

Runs:

- `B1 = A + credit level`
- `B2 = A + credit 3M change`
- `B3 = A + 10Y−3M`
- `B4 = A + VRP`
- `B5 = A + 12M momentum`
- **`B-All = A + all five`**

`B-All vs A` is the **predeclared primary conventional-signal contrast**. The five component runs are attribution diagnostics; the best-looking component may not be selected after the test and relabeled as “System B.”

## 6. Systems C and D — frozen backtest treatment interface

- `C = A + standard timestamped RAG agent features`
- `D = A + matched Causal-RAG agent features`

C and D must hold constant: LLM version, prompt/output schema, corpus, document timestamp filter, embedding model, document count, token budget, run count/seeds, and the entire backtest engine. Only retrieval structure is the intended C-vs-D treatment.

Categorical agent outputs use **Insufficient as the reference state**, with explicit Supported and Contradicted indicators. No arbitrary `+1/-1` score and no uncalibrated LLM confidence is treated as a probability.

Historical C/D dates before a defensible model-knowledge-cutoff boundary are diagnostic. Prospective post-freeze results are the cleanest C/D evidence.

Recommended controls:
- `Cπ`: permuted C labels — high priority.
- `D0`: random/rewired graph placebo — high priority if implementation bandwidth permits.
- `C0`: no-retrieval diagnostic.
- Mechanical-label A′: optional robustness.

## 7. Frozen forecast model

- Separate **Ridge** model for SPY, IEF, LQD.
- Unpenalized intercept.
- Expanding outer window.
- Minimum **48 completed labels**.
- Refit monthly.
- Scaling fitted only on finite observed values in the current training fold.
- Missing standardized feature = 0 only after scaling.

Inner CV:
- Expanding one-step-ahead.
- Minimum 36 completed labels.
- **1-month purge** between inner training and validation.
- Validation stride = 1 month.
- Loss = MSE.
- Scaling is refit inside every fold.

Frozen alpha candidates:

`1e-4, 1e-2, 1, 1e2, 1e4, 1e6, 1e8, 1e10, INTERCEPT_ONLY`

Ties choose the **more strongly regularized** candidate.

## 8. Frozen allocation and costs

Forecast evidence is primary; portfolio evidence is secondary.

Allocator remains **Black–Litterman**:

- `P = I`
- `Q = Ridge excess-return forecasts`
- `tau = 0.05`
- risk-aversion `delta = 2.5`
- prior weights = **45% SPY / 35% IEF / 20% LQD**
- covariance = trailing **36-month Ledoit–Wolf** covariance of realized excess returns.
- Long-only, fully invested.
- Bounds:
  - SPY 20–70%
  - IEF 15–60%
  - LQD 10–40%

For the historical test, `Ω` is estimated from **System A development-period OOS forecast errors**, then frozen and shared by A/B/C/D. This prevents a different uncertainty calibration from becoming an unintended second treatment.

Transaction cost:
- **5 bps per dollar traded**.
- `traded_notional = Σ|target_weight − drifted_pretrade_weight|`
- cost = `0.0005 × traded_notional`
- reported one-way turnover = `0.5 × traded_notional`
- turnover is drift-aware.
- The same cost accounting applies to dynamic benchmarks.

## 9. Frozen benchmarks

Forecast benchmark:
- Expanding historical mean excess return using completed labels only through `t-2`.

Portfolio benchmarks:
1. Historical-mean forecasts sent through the **same allocator and costs**.
2. **45/35/20 monthly-rebalanced** portfolio with the same cost accounting.

## 10. Frozen evaluation

### Primary
Forecast accuracy, not portfolio Sharpe.

Main confirmatory contrasts:
1. **B-All vs A**
2. **C vs A**
3. **D vs C**

Forecast outputs:
- normalized pooled squared-error differential
- Relative MSPE
- OOS R²
- RMSE
- MAE
- directional accuracy (descriptive)

For pooled loss, asset squared errors are normalized by an expanding realized-return variance available through `t-2`, then SPY/IEF/LQD receive equal weight.

Uncertainty:
- paired circular moving-block bootstrap
- 6-month blocks
- 5,000 replications
- seed `20261027`
- resample months jointly across the three assets
- report both 90% and 95% intervals

Multiplicity:
- Holm 5% correction across the three main contrasts.
- B1–B5 component tests are attribution diagnostics; if p-values are highlighted, Holm-correct within that five-test family.

### Secondary portfolio metrics
- net annualized excess return
- annualized volatility
- net Sharpe
- maximum drawdown
- certainty-equivalent return (`delta=2.5`)
- turnover
- break-even transaction cost

Event/regime analysis is **diagnostic only** and may not be used after the fact to select a winning signal.

## 11. Robustness only — not allowed to replace Primary after seeing results

- macro winsorization at ±3
- prior-24-release macro standardization
- MAD/robust scaling
- 36 or 60 minimum training labels
- rolling 60-month estimation
- 10Y−2Y curve
- IG OAS instead of BAA10Y
- alternative expected-variance VRP
- costs of 0/2/10/25 bps
- alternative execution day
- alternative bootstrap block length

## 12. Data-integrity gates before first scored run

The methodology is frozen now. The first scored run is blocked until:

1. Exact daily total-return files for SPY/IEF/LQD are snapshotted and hashed.
2. The risk-free source is snapshotted and hashed.
3. BAA10Y / Treasury curve / VIX inputs are snapshotted and hashed.
4. Every feature has an `available_at` field or an auditable availability rule.
5. ETF total returns are unit-tested for distribution/ex-date handling against a trusted source.
6. All systems are forced onto identical common scoring dates.
7. A run log records this config hash plus every data-file hash.

No performance-dependent change is permitted while satisfying these gates.

## 13. Source artifact hashes at methodology freeze

```json
{
  "deterministic_data2 - Oct26.xlsx": "fc0d9996c7a5752810f65fa1f6bdc49a80eacc45557711278c4405cdada6e220",
  "deterministic_data2_model_panels_COPY.xlsx": "38c84b8055271c5ae24e3ae663b01dbb58c1499285ac9bdcc47d62af8fc411a1",
  "build_model_ready_panels.ipynb": "c8149f5f12fb1b1013de1fefd87004fbcf41daddbdfdddbe5b417bbcc3acf315",
  "stage1_backtest_config.json": "5151ff0c87dfc907dcf323fa3e61704e994871a1255cafa7946fab330499d8fb",
  "BACKTEST_DESIGN.md": "b31b9e9e163b5cb6839304360e104ac2fc09467a5638908776ebdb9d3bf797d8",
  "Stage2_Methodological_Review.pdf": "93490c0c17a2474bce836fa796dde60cd5a36978881625b11c076172d75a9807",
  "Pasted markdown(10).md": "6e65a0963475c8204a27f6da7a71288026d9a541f96cc239659d7fd7dde26f9f"
}
```

The machine-readable configuration is in `stage2_frozen_config_v2.json`; the signal manifest is in `stage2_signal_manifest_v2.csv`.
