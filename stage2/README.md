# Stage 2 — Signal Evaluation

## Goal

We are building a controlled experiment to compare three approaches for generating financial signals:

1. Conventional / literature-based signals
2. Agent-generated signals using JEV
3. Causal-RAG-generated signals

All three feed the same quantitative forecasting pipeline.

**Only the signal-generation approach changes.** The forecasting model, assets, timing, target, validation procedure, and evaluation metrics stay fixed.

## Baseline

System A uses eight macroeconomic surprise features:

- NFP
- Retail Sales
- Industrial Production
- ISM Manufacturing
- CPI
- Core CPI
- PPI
- Average Hourly Earnings

Together they cover growth, consumption, production, business activity, inflation, and labor conditions.

## Conventional Signals

System B adds five literature-motivated financial signals:

- Credit Spread Level
- 3-Month Credit Spread Change
- 10Y–3M Yield Curve
- Variance Risk Premium (VRP)
- 12-Month Own-Asset Momentum

We test them in two ways.

### Individual attribution tests

| System | Features |
|---|---|
| B1 | A + Credit Spread Level |
| B2 | A + Credit Spread Change |
| B3 | A + Yield Curve |
| B4 | A + VRP |
| B5 | A + Momentum |

These show which individual signals help or hurt.

### Main conventional system

**B-All = A + all five signals**

B-All vs A is the main conventional-signal comparison.

Individual results must **not** be used to cherry-pick a new definition of System B after seeing performance.

## Assets

- SPY (US equities)
- IEF (US Treasuries)
- LQD (investment-grade credit)

## Forecast Model

The same model is used for every system:

- Ridge regression, one model per asset
- Expanding-window training
- Feature scaling fit on training data only
- Walk-forward validation (no random train/test split)

## Evaluation Windows

| Window | Period | Use |
|---|---|---|
| Development | Mar 2019 – Dec 2022 | Diagnostics and development only, not confirmatory claims |
| Historical pseudo-OOS test | Jan 2023 – Aug 2026 | **Not yet opened** 🔒 |

## Current Development Result

- Credit Spread Level showed a small positive point estimate.
- Yield Curve showed a small positive point estimate.
- Credit Spread Change and Momentum were weaker.
- VRP was substantially weaker.
- B-All did not outperform A in the development period.
- Confidence intervals generally include zero.

> These are development results.
> They are **not** evidence that B1 or B3 should replace B-All.

Details: [`results/stage2_dev_result_summary.json`](results/stage2_dev_result_summary.json)

## Current Status

- ✅ Methodology frozen
- ✅ Data snapshot / hashes created
- ✅ Development backtest completed
- 🔒 Historical test still locked
- ⬜ JEV approach not yet evaluated
- ⬜ Causal-RAG approach not yet evaluated
- ⬜ MVP not yet built

## Experiment Roadmap

```
A   Macro baseline
↓
B   Conventional signals
↓
C   JEV / agent-generated signals
↓
D   Causal-RAG signals
```

Primary questions:

| Comparison | Question |
|---|---|
| B vs A | Do conventional signals add predictive value? |
| C vs A/B | Do agent-generated signals add predictive information? |
| D vs C | Does causal retrieval add value beyond standard agent/RAG signals? |

## File Guide

| Folder | Purpose |
|---|---|
| `config/` | Frozen experimental settings |
| `methodology/` | Experiment design and methodological review |
| `data/` | Model-ready data used in the quantitative pipeline ([data README](data/README.md)) |
| `notebooks/` | Data construction and backtesting code |
| `signal_research/` | Research behind conventional signal selection |
| `results/` | Predictions and evaluation results |
| `reproducibility/` | Hashes and freeze records |

## Important Caveat

The historical 2023–2026 evaluation should **not** be opened until the remaining macro-data availability issue is resolved (decision months 2025-10 to 2025-12 are missing from the accessible macro panel; see [`results/stage2_historical_test_gate_2026-10-27.json`](results/stage2_historical_test_gate_2026-10-27.json)).

No performance claims should be made about the historical test. It has not been run.
