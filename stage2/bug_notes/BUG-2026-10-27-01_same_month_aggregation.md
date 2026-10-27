# BUG-2026-10-27-01 — Same-month macro releases: last release kept instead of the frozen mean

**Filed:** 2026-10-27 19:34 UTC, before any rerun
**Classification:** implementation bug fix under Freeze v2 §1 (bug-fix exception). No frozen parameter changes; config version stays 2.0.
**Status:** fix applied to the scoring panel; development rerun pending the canonical Stage 2 scorer.

## Frozen rule

Freeze v2 §4 and `stage2_frozen_config_v2.json` → `macro_feature_construction.monthly_aggregation`:

> Mean if multiple releases of the same indicator occur in one calendar month.

Freeze v2 §4 also says a no-release month "remains missing until model scaling; after training-only scaling, missing = 0".

## Defect

`notebooks/build_model_ready_panels.ipynb`, cell 4, collapses each release series to one value per calendar month by keeping the release with the **latest date** (`if ym not in monthly or dt > monthly[ym][0]`). It does not average same-month releases.

Stage 1 (`stage1_macro_panel_snapshot.csv`) applied the mean correctly, so Stage 1 and the Stage 2 panel disagreed in one development-window cell.

## Cells affected (2015-02 onward)

| Decision month | Indicator | Releases in month | Old z (last) | Corrected z (mean) | Window |
|---|---|---|---|---|---|
| 2019-04 | Retail sales | 2 | 1.382 | 0.358 | Development |
| 2025-12 | Industrial production | 2 | 0.088 | 0.022 | Historical test |
| 2026-01 | PPI | 2 | 1.135 | 0.734 | Historical test |
| 2026-04 | Retail sales | 2 | 1.080 | 0.758 | Historical test |

All other cells are unchanged: rebuilding from the source workbook reproduces the committed unbalanced panel to 1e-15 elsewhere.

## Related correction: incomplete months restored as rows

`model_balanced_panel.csv` kept only months where all eight indicators (and both policy features) were observed, which removed four calendar months: 2019-01 (retail sales not released; 2018–19 shutdown), 2025-10, 2025-11 and 2025-12 (2025 shutdown). Dropping rows contradicts the frozen no-release rule above. The corrected panel keeps every calendar month from 2015-02, leaves unreleased indicators missing, and records the release count per indicator.

How the previous development run treated 2019-01 is not recorded in the repository; the rerun removes the ambiguity.

## Corrected panel

- File: `data/model_scoring_panel_E4_meanrule.csv` — 140 rows, 2015-02 to 2026-09
- SHA-256: `459bef989561aa66f32eccc6d0758ff15b8d50fbd3cdea51b5eced8f0fa456b1`
- Built from `deterministic_data2_policy_extended_COPY.xlsx` (SHA-256 `646659645244e6d6ed478ab82f75c62fc8f8b0c112c1021d75b9afd8e77e57d1`) with the notebook's surprise and 12-release standardisation logic unchanged, except for the mean aggregation and row retention.
- Months with fewer than eight indicators: 2019-01 (7), 2025-10 (3), 2025-11 (5), 2025-12 (5).

## Basis for the fix

The correction follows from the frozen text and the official release calendars alone. It was identified and written before any rerun and without reference to any test-window result.

## Consequences

1. `results/stage2_dev_result_summary.json` (SHA-256 `710e1ae649d0ca6b2eac72fae98e6276d4554477703d08d4242efa8405cfb890`) is superseded once the rerun completes. It is kept for comparison, not deleted.
2. All seven systems (A, B1–B5, B-All) are rerun on development decisions 2019-03 to 2022-12 with the canonical scorer, the corrected panel and data snapshot v2.
3. The historical test (2023-01 to 2026-08) stays sealed.
4. No tuning, signal change or parameter change follows from the rerun.

## Addendum after the development rerun (2026-10-27, 21:10 UTC)

The rerun used the canonical scorer (`stage2/scoring/stage2_backtest.py`) on the corrected panel; see `results/dev_rerun_v2_2026-10-27/DEV_RERUN_REPORT.md`.

- Every 2019-03 forecast trains on exactly 48 labels (2015-02 to 2019-01), with 2019-01 retained and retail sales missing.
- A diagnostic run of the same scorer on the old panel shows the fix changes 292 of 966 forecasts, mostly by less than 1e-6, starting with decision 2019-09.
- The corrected-panel run reproduces the saved development summary for A, B1, B3 and B5 within about 0.00003, while the old-panel run does not. The saved development run therefore appears to have used the mean for the 2019-04 cell already; this bug most likely affected the panel file, not the saved results.
- Remaining differences from the saved summary are confined to B2, B4 and B-All and are not caused by this bug.
