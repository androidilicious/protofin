# Conventional-signal experiments: PAUSED and archived (2026-10-27)

**Decision:** the Stage 2 conventional-signal experiments are on hold, effective immediately. They are no longer part of the primary experiment. The proposed v3 design ([`Stage2_Backtest_Design_v3_PROPOSED.md`](Stage2_Backtest_Design_v3_PROPOSED.md)) compares view-generation approaches 1, 2A, 2B and 3.

## What is paused

| v2 system | Signal |
|---|---|
| B1 | Credit spread level (BAA10Y) |
| B2 | Credit spread 3-month change |
| B3 | 10Y−3M Treasury slope |
| B4 | VRP proxy (VIX²/12 − 22-day realized variance) |
| B5 | Own-asset 12-month momentum |
| B-All | A + all five (v2 primary conventional contrast) |

The B-specific robustness items are paused with them: 10Y−2Y curve, IG OAS, alternative VRP. So is v2 data-integrity gate 3 (BAA10Y / curve / VIX snapshots), which concerns their inputs.

## Rules while paused

- **Do not run, optimise, select, rank or expand** these signals or any variant of them.
- **Do not delete, move or edit** their code, data, manifests or results. They are preserved as archived supplementary research, and their hashes in the existing ledgers stay valid.
- The B systems will not be scored in the 2023-01..2026-08 historical window.
- The existing development results stay as recorded. They are supplementary and development-only, and are not cited as evidence for or against any v3 approach. That includes B-All, B2 and B4 not beating A.
- The canonical scorer still lists `("A", "B1", "B2", "B3", "B4", "B5", "B-All")` in `SYSTEMS` (`stage2/scoring/stage2_backtest.py:77`), and a development run computes them together with A.
  - No scorer run is needed until the v3 implementation is approved.
  - Restricting the system list is a proposed code change for that implementation; it is not made here.
  - If the scorer is run before then, for example to re-verify reproduction, the B outputs are by-products and must not be inspected, ranked or reported.

## Where the archived material lives (unchanged)

| Artifact | Location |
|---|---|
| Definitions | `stage2/config/stage2_frozen_config_v2.json` → `system_B_primary_signals`, `system_B_runs`; `stage2/config/stage2_signal_manifest_v2.csv`; `stage2/methodology/Stage2_Backtest_Freeze_v2.md` §5 |
| Research background | `stage2/methodology/BNY_Macro_Signal_Research.md`; `stage2/signal_research/BNY_Macro_Signal_Inventory.{csv,xlsx}` |
| Input snapshots | `signal_credit_spread`, `signal_yield_curve`, `signal_vix_pre2018`, `signal_vix_2018plus` in `stage2/reproducibility/stage2_data_snapshot_manifest_v3_2026-10-27.json` (fetched into `stage2/data/_pinned/`, not republished) |
| Feature code | `stage2/scoring/stage2_backtest.py` (`SYSTEMS`, `B_FEATURES`, `build_vrp`, signal panel construction) |
| Development results | `stage2/results/dev_rerun_v2_2026-10-27/`, `dev_rerun_v4_portfolio_2026-10-27/`, `dev_rerun_diag_oldpanel_2026-10-27/`; superseded `stage2_dev_result_summary.json` |
| Hash records | `stage2/reproducibility/stage2_master_prescore_hash_ledger_v5_2026-10-27.json` |

## Resuming

Resuming any B experiment requires all three of the following:

- a written, versioned decision;
- a separate pre-registration;
- no exposure to historical-window results for these signals.

It may not be resumed because of results seen in the v3 experiment.
