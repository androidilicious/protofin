# Deterministic Quant Baseline MVP

This MVP implements the quantitative baseline described in the proposal and deliberately excludes RAG, LLMs, and agents.

## What runs with the supplied workbook

The signal engine:

1. Reads all eight macro release and reference-sheet pairs.
2. Joins release dates to reference periods without duplicating delayed releases.
3. Calculates `actual - survey median` surprises.
4. Standardizes each surprise using only the prior historical forecast-error distribution (12 prior releases minimum).
5. Aggregates four Growth and four Inflation indicators by monthly decision date.
6. Adds 3-month and 6-month policy levels, changes, and the 6m-minus-3m policy-path slope.
7. Writes data-quality checks and the latest usable signal.

The supplied workbook does **not** contain ANFCI, GPR, or realized returns for U.S. Equity, U.S. Treasury, and IG Credit. Without a supplemental file, the program reports `signal_only` and does not create a misleading forecast or backtest. A reproducible online-data path is now included and produces `supplemental_monthly.csv` from ANFCI, official GPR, and adjusted SPY/IEF/LQD histories.

## What activates after the five missing columns are supplied

Add a monthly CSV following `supplemental_monthly_template.csv`. Return values must be monthly decimal total returns, so 1% is `0.01`.

The full pipeline then:

- Builds Growth × ANFCI, Inflation × ANFCI, Growth × GPR, and Inflation × GPR interactions.
- Forecasts each asset's next-month return with expanding-window Ridge regression.
- Selects Ridge penalties only from past observations.
- Measures MAE, RMSE, and directional accuracy.
- Uses Ridge forecasts as Black–Litterman views.
- Estimates view uncertainty from prior out-of-sample forecast errors.
- Computes long-only, bounded, turnover-aware weights for Equity, Treasury, and IG Credit.
- Reports transaction-cost-adjusted portfolio performance.

## Online source timing and limitations

- ANFCI uses the last weekly observation assumed published by month-end, with a five-calendar-day lag from its Friday observation date.
- Monthly GPR is shifted to the following decision month.
- SPY, IEF, and LQD returns use month-end dividend-adjusted closes.
- ANFCI and GPR are latest revised histories. A formal locked test should use archived real-time vintages.
- IEF represents the 7–10 year Treasury segment rather than the entire Treasury market.

See `data_sources.csv` for the exact source URLs and transformations.

## Run

From this directory:

```bash
python3 src/deterministic_mvp.py \
  --workbook ../deterministic_data1.xlsx \
  --output-dir outputs
```

With supplemental data:

```bash
python3 src/deterministic_mvp.py \
  --workbook ../deterministic_data1.xlsx \
  --supplemental supplemental_monthly.csv \
  --output-dir outputs
```

Refresh and prepare the public supplemental sources:

```bash
python3 src/prepare_online_data.py \
  --raw-dir data/raw \
  --output supplemental_monthly.csv \
  --sources data_sources.csv \
  --download
```

Run tests:

```bash
python3 -m unittest discover -s tests -v
```

## Reproducible backtest runs

From the repository root, use the project virtual environment and a separate run directory:

```bash
.venv/bin/python deterministic-model/deterministic_mvp/src/deterministic_mvp.py \
  --workbook "/path/to/updated.xlsx" \
  --supplemental deterministic-model/deterministic_mvp/supplemental_monthly.csv \
  --as-of 2026-10-26 \
  --cost-bps 5 \
  --output-dir runs/deterministic-oct26/updated
```

`--as-of` defaults to today's date in New York. Only calendar months strictly before
that date's month enter signals, training, and evaluation. For example, October 26
uses data through September 30; November 1 admits October. This prevents partial
current-month releases or market returns from being presented as a completed month.
It does not reconstruct the historical vintages of a revised source.

The importer uses raw payroll releases rather than the manually copied cleaned tab,
recognizes both formatted Excel dates and numeric serial dates in the Bloomberg
exports, and sorts releases before historical standardization. Missing actuals or
consensus estimates remain unavailable and are counted in `data_quality.csv`.
Growth and Inflation still average available components, so the component counts
must be inspected when comparing periods with different coverage.

The simulator starts with endowed holdings (no initial purchase fee). Before each
rebalance, previous holdings drift according to realized asset returns. One-way
turnover is `0.5 * sum(abs(target - drifted_holdings))`. Costs are deducted from
wealth before applying the holding-period return: `(1 - cost) * (1 + gross) - 1`.
The same cost rate and timing apply to each rebalanced comparison. Buy-and-hold
starts at 45/35/20 and drifts without subsequent trades. Prior-only uses the same
covariance, bounds, grid and turnover penalty with equilibrium returns and no
Ridge views. Equal weight rebalances monthly. All comparisons share scored dates.
Missing intermediate outcomes or gaps after allocation begins raise an error
instead of silently omitting a holding period.

`portfolio_backtest.csv` records decision and outcome months, pretrade and target
weights, asset returns, turnover, costs, and comparison returns. The final decision
may have no outcome; `evaluated=false` distinguishes it and metrics exclude it.
`benchmark_comparison.csv` reports the five portfolios on identical dates.
`run_summary.json` records the cutoff, cost rate, and SHA-256 hashes of the workbook,
supplemental CSV and model code. Keep copies of those inputs alongside each run.

This is an **idealized month-end-close baseline**: the model consumes month-end
data and assumes execution at that close. It does not yet implement a tradable
delay or slippage model. Daily execution data are needed for that sensitivity.
ANFCI/GPR still use revised histories. The reported `sharpe_zero_rf` is the existing
annualized geometric return / annualized volatility ratio, not a cash-adjusted
Sharpe estimate. These limitations must accompany any performance comparison.

## MVP assumptions to lock before formal evaluation

- Decision date: calendar month-end; only releases observed by that date enter the signal.
- Growth and Inflation composites: equal-weight mean of available standardized component surprises.
- Standardization: expanding standard deviation of prior raw surprises; 12 prior releases required.
- Benchmark weights: 45% Equity, 35% Treasury, 20% IG Credit.
- Allocation bounds: Equity 20–70%, Treasury 15–60%, IG Credit 10–40%.
- Black–Litterman `tau`: 0.05; risk aversion: 2.5.
- Covariance window: trailing 36 monthly returns.
- Portfolio transaction cost: 5 bps per unit of one-way turnover.
- Optimizer turnover penalty: 0.5 basis points of utility per unit of one-way turnover.

These are transparent MVP defaults, not proposal facts. Freeze or revise them before opening a locked test set.

## Generated files

- `clean_releases.csv`: audit-ready event-level release data and point-in-time z-scores.
- `surprise_signals.csv`: monthly component, Growth, and Inflation surprise signals.
- `latest_surprise_signal.json`: latest model-ready surprise state.
- `monthly_features.csv`: monthly macro and policy feature panel.
- `data_quality.csv`: source and pipeline checks.
- `latest_signal.json`: latest complete macro/policy signal.
- `run_summary.json`: execution status and data gap summary.
- With supplemental data: model dataset, Ridge predictions, forecast metrics, portfolio backtest, portfolio metrics, latest forecast, and latest allocation.
