# Adoption of the canonical Stage 2 scorer and development results

**Date:** 2026-10-27
**Decision:** The reconstructed scorer in `stage2/scoring/` and its development rerun are the **canonical Stage 2 reference implementation and results** from this date. Methodology (Freeze v2.0) is unchanged.

## What is adopted

| Item | File | SHA-256 (first 16) |
|---|---|---|
| Forecast scorer | `scoring/stage2_backtest.py` | `537c282cef5ab7a8` |
| Portfolio layer | `scoring/stage2_portfolio.py` | `5675f25024187248` |
| Portfolio conventions | `methodology/Stage2_Portfolio_Conventions_v1.md` | `29a61dc8cfea1c4f` |
| Development run spec | `scoring/stage2_run_spec_dev_v4.json` | `58fa0f249c8685d1` |
| Historical run spec (locked) | `scoring/stage2_run_spec_historical_v4.json` | `bbc79b5ef974d7d6` |
| Frozen Ω for the historical test | `config/stage2_omega_from_A_development.json` | `f7e3b9ef0b6cb1e7` |
| Canonical development forecast results | `results/dev_rerun_v2_2026-10-27/` (summary `7c5b5c52dd957336`) | — |
| Canonical development portfolio results | `results/dev_rerun_v4_portfolio_2026-10-27/` (portfolio metrics `2c837e4d76479b3a`) | — |

Full hashes are in the latest master ledger in `reproducibility/`.

## Why

The scorer that produced `results/stage2_dev_result_summary.json` was run but never saved, so it **cannot be reproduced byte-for-byte**. The team supplied a reconstruction built from the frozen methodology. On identical inputs and the corrected macro panel, the reconstruction matches the saved summary for A, B1, B3 and B5 within about 0.00003, but differs for B2 (credit change), B4 (VRP) and B-All. The original code cannot be inspected, so the cause cannot be confirmed; the reconstruction follows the frozen signal definitions.

## Supersession

- `results/stage2_dev_result_summary.json` is **superseded** for every system and, in particular, for B2, B4 and B-All. It stays in the repository unchanged as a historical record and must not be cited as a current result.
- The canonical development forecast results are in `results/dev_rerun_v2_2026-10-27/`; the v4 run reproduces them byte-for-byte and adds the portfolio layer.

## Changes made during reconstruction and adoption (no methodology change)

1. Macro panel: `data/model_scoring_panel_E4_meanrule.csv` (BUG-2026-10-27-01).
2. Risk-free: DTB4WK extended to 2026-10-01 (data snapshot v3); development outputs unchanged.
3. Run spec: VIX switch to VIXCLS on 2018-12-03 (where that file begins; the two VIX files agree exactly where they overlap); price files' `Close` declared distribution-adjusted.
4. Scorer: portfolio layer added; development comparison helper accepts both `BAll` and `B-All` keys. Forecast outputs are byte-identical before and after.

## Rules from here

- Any development rerun must reproduce `results/dev_rerun_v2_2026-10-27/stage2_result_summary.json` (MATCH at 1e-8, as the v4 spec checks). A mismatch is a stop signal.
- Any change to the adopted files requires a version increment, a written note and a rerun of every system.
- The historical test remains sealed until every gate in the latest `results/stage2_historical_test_gate_*.json` passes.
