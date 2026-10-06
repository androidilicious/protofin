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
