# Stage 2 Data

## Data strategy

Each data source has one job in the experiment:

| Data | Role |
|---|---|
| Macro releases (8 indicators) | Baseline economic surprises (actual − consensus) |
| SPY / IEF / LQD | Asset returns and forecast targets |
| BAA10Y | Credit conditions (credit spread level and change) |
| T10Y3M | Yield curve |
| VIX + SPY returns | Variance risk premium (VRP) |
| DTB4WK | Risk-free return (turns asset returns into excess returns) |
| Future JEV and Causal-RAG outputs | Alternative signal sources, added on top of the same baseline |

The baseline and targets stay the same. Only the added signals change between systems.

## Files

| File | Type | Purpose |
|---|---|---|
| `model_balanced_panel.csv` | Model-ready | Monthly panel where all 8 macro surprises are available (2015 onward), plus policy-rate features |
| `model_unbalanced_panel.csv` | Model-ready | Longer panel (2001 onward); macro features enter as they become available, tracked by `era_id` |
| `stage1_macro_panel_snapshot.csv` | Snapshot | Frozen macro surprise z-scores used in the Stage-1 backtest |
| `stage1_market_returns_snapshot.csv` | Snapshot | Frozen monthly SPY / IEF / LQD returns and 1-month T-bill return used in the Stage-1 backtest |

The source workbook these panels were built from (raw Bloomberg release and consensus data) is **not** included in this repository. Its hash is recorded in `../reproducibility/`, and `../notebooks/build_model_ready_panels.ipynb` shows how the panels were built.

## External / Withheld Dependencies

These source files are **not committed**:

| File | Why not committed | Needed by |
|---|---|---|
| `deterministic_data2 - Oct26.xlsx` | Bloomberg data (restricted) | `policy_rate_validation.ipynb` |
| `deterministic_data2_policy_extended_COPY.xlsx` | Bloomberg data (restricted) | `build_model_ready_panels.ipynb` |
| `deterministic_data2_model_panels_COPY.xlsx` | Bloomberg data (restricted) | None (workbook copy of the model panels) |
| `fed_funds_futures_history_2000_2023Aug.csv` | External public archive, not part of this snapshot | `policy_rate_validation.ipynb` |

- **Reviewing:** the committed model-ready CSVs are enough to review the Stage-2 experiment and the current backtest results.
- **Full reproduction:** rebuilding the data pipeline from scratch requires the withheld source files above.

## Rules

- **Missing values stay missing.** Do not fill, zero out, or drop months silently. A missing macro release means "not released yet" and must stay that way.
- **Point-in-time availability matters.** A feature can only be used for a decision month if it was actually published before that decision. No look-ahead.
- **Snapshots are frozen.** Do not edit them. If data changes, create a new snapshot and record its hash.
