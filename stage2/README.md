# Stage 2 — Signal Evaluation

> **Status update, 2026-10-27**
> - **A v3 redesign is proposed and not yet frozen.** Stage 2 now compares view-generation approaches: 1 (deterministic Ridge), 2A (Agent Committee), 2B (JEV) and 3 (CauseTrace / Causal RAG). See [methodology/Stage2_Backtest_Design_v3_PROPOSED.md](methodology/Stage2_Backtest_Design_v3_PROPOSED.md).
> - **The conventional-signal experiments (B1–B5, B-All) are paused** and archived unchanged ([pause record](methodology/Stage2_Conventional_Signals_PAUSE_2026-10-27.md)).
> - The v2 freeze below remains the last frozen design until v3 is approved.
> - The historical test stays sealed (gate v5).

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

## Canonical Scorer

The reconstructed scorer in [`scoring/`](scoring/) and its development rerun are the **canonical Stage 2 reference** from 2026-10-27 ([adoption record](methodology/Stage2_Canonical_Scorer_Adoption_2026-10-27.md)). The original development scorer was never saved and cannot be reproduced byte-for-byte; the canonical rerun supersedes the earlier results, in particular for B2, B4 and B-All.

## Current Development Result (canonical)

Normalised pooled squared-error improvement vs A (positive = better), 46 development months, 90% bootstrap interval:

| System | Point | 90% interval |
|---|---|---|
| **B-All (primary)** | −0.046 | −0.125 to +0.001 |
| B1 credit level | +0.004 | −0.001 to +0.011 |
| B2 credit change | −0.030 | −0.090 to +0.005 |
| B3 curve | +0.003 | −0.001 to +0.010 |
| B4 VRP | −0.384 | −1.098 to −0.0001 |
| B5 momentum | −0.018 | −0.054 to +0.004 |

- B-All did not outperform A; nearly all of its shortfall, and of B4's, comes from decisions 2020-05 and 2020-06.
- Portfolio layer (secondary, diagnostic in development): weights stay near 45/35/20 and no B system beats A or the static 45/35/20 portfolio on CER.

> These are development results.
> They are **not** evidence that B1 or B3 should replace B-All.

Details: [`results/dev_rerun_v2_2026-10-27/DEV_RERUN_REPORT.md`](results/dev_rerun_v2_2026-10-27/DEV_RERUN_REPORT.md) and [`results/dev_rerun_v4_portfolio_2026-10-27/`](results/dev_rerun_v4_portfolio_2026-10-27/). The earlier [`results/stage2_dev_result_summary.json`](results/stage2_dev_result_summary.json) is superseded.

## Current Status

- ✅ Methodology frozen
- ✅ Data snapshot / hashes created (snapshot v3)
- ✅ Canonical scorer adopted; development rerun completed
- ✅ Black–Litterman portfolio layer implemented ([conventions](methodology/Stage2_Portfolio_Conventions_v1.md))
- ✅ ETF distribution adjustment verified against State Street / iShares records ([freeze gate 5](results/dividend_gate/DIVIDEND_GATE_REPORT.md))
- 🔒 Historical test still locked: every required gate passes; the GO decision is with the team (see the latest `results/stage2_historical_test_gate_*.json`)
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
| `config/` | Frozen experimental settings, including the frozen Black–Litterman Ω |
| `scoring/` | Canonical Stage 2 scorer, portfolio layer, run specs, input fetcher and tests |
| `bug_notes/` | Implementation bug notes |
| `methodology/` | Experiment design, methodological review, portfolio conventions, scorer adoption |
| `data/` | Model-ready data used in the quantitative pipeline ([data README](data/README.md)) |
| `notebooks/` | Data construction and backtesting code |
| `signal_research/` | Research behind conventional signal selection |
| `results/` | Predictions and evaluation results |
| `reproducibility/` | Hashes and freeze records |

## Important Caveat

The historical 2023–2026 evaluation must **not** be opened until every gate in the latest `results/stage2_historical_test_gate_*.json` passes. The late-2025 macro gap is resolved: those months are kept with unreleased indicators missing ([BUG-2026-10-27-01](bug_notes/BUG-2026-10-27-01_same_month_aggregation.md)).

No performance claims should be made about the historical test. It has not been run.
