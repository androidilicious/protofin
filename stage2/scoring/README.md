# Stage 2 Scoring Code — Canonical Reconstruction

This package reconstructs the **Stage 2 A/B forecast scorer** from the frozen Stage-2 methodology, frozen config, signal manifest, saved development summary, and the existing Stage-1 implementation.

## Status: adopted canonical reference (2026-10-27)

This scorer and its development rerun are the **canonical Stage 2 reference implementation and results** ([adoption record](../methodology/Stage2_Canonical_Scorer_Adoption_2026-10-27.md)). It is a reconstruction: the earlier development scorer was run but never saved, so it cannot be reproduced byte-for-byte. The canonical rerun supersedes `../results/stage2_dev_result_summary.json`, in particular for B2, B4 and B-All.

The historical test is locked by default.

## Reproduce the canonical development run

From the repository root:

```bash
python stage2/scoring/fetch_pinned_inputs.py --manifest stage2/reproducibility/stage2_data_snapshot_manifest_v3_2026-10-27.json
python stage2/scoring/build_dtb4wk_combined.py
python stage2/scoring/stage2_backtest.py --spec stage2/scoring/stage2_run_spec_dev_v4.json --mode development --output-dir <dir>
(cd stage2/scoring && python -m pytest -q)
```

`development_reproduction_check.json` must report MATCH against `results/dev_rerun_v2_2026-10-27/stage2_result_summary.json`. A MISMATCH is a stop signal.

## Portfolio layer

`stage2_portfolio.py` implements the frozen Black–Litterman allocator, both portfolio benchmarks and all secondary metrics. Details the freeze leaves open are fixed in [`../methodology/Stage2_Portfolio_Conventions_v1.md`](../methodology/Stage2_Portfolio_Conventions_v1.md), written before any portfolio result was computed. Historical mode loads the frozen Ω from `../config/stage2_omega_from_A_development.json` via `stage2_run_spec_historical_v4.json`.

## Freeze gate 5: distribution adjustment

`check_dividend_adjustment.py` checks that the adjusted prices include every official distribution, using State Street (SPY) and iShares (IEF, LQD) records. The records are under `../data/dividend_check/` and are rebuilt by `build_dividend_check_inputs.py`. `test_dividend_adjustment.py` runs the check automatically. Result: PASS ([report](../results/dividend_gate/DIVIDEND_GATE_REPORT.md)).

The sections below are the reconstruction notes supplied with the package. The risk-free provenance issue they mention was resolved by data snapshots v2 and v3, which pin DTB4WK.

## What this implements

- Assets: SPY, IEF, LQD
- System A: 8 macro surprise features
- B1–B5: each conventional signal added separately
- B-All: all five conventional signals together
- Decision snapshot: month-end, 20:00 ET
- Execution: first trading-day close after month-end
- Exit: first trading-day close after the next month-end
- Target: exact-period asset total return minus 1-month T-bill cash return
- Training labels: only through `t-2`
- Separate Ridge per asset
- Expanding training window
- Training-fold-only feature scaling
- Missing feature values become 0 **only after scaling**
- Expanding one-step inner CV with one-month purge
- Frozen alpha grid, including `INTERCEPT_ONLY`
- Development: 2019-03 through 2022-12
- Historical pseudo-OOS: 2023-01 through 2026-08, locked until an explicit GO gate
- Primary forecast metrics and paired circular moving-block bootstrap
- SHA-256 run manifest

## Critical panel rule

Use the **calendar-complete same-definition panel**, i.e. `model_unbalanced_panel.csv` filtered from 2015-02 onward.

The name “unbalanced” is historical from Stage 1. For Stage 2, this file is needed because it retains months in which one or more releases did not occur.

Example: `2019-01` must stay in the sample even though Retail Sales is missing. The scorer must **not** delete that month and must **not** backfill the later Retail Sales release. The missing feature is transformed to 0 only after the scaler is fitted on the available training values.

This gives the first 2019-03 forecast exactly 48 completed training labels from 2015-02 through 2019-01.

## Risk-free rule

The saved development result explicitly records **FRED DTB4WK** (4-week T-bill, bank-discount basis):

1. take the quote available at the period start;
2. convert the quoted 28-day discount yield to an effective 28-day return;
3. accrue over the exact number of calendar days in the holding period.

The 12-month momentum cash leg rolls the same rule month-end to month-end.

There is currently a provenance inconsistency: an earlier data snapshot manifest lists `DGS1MO`, while the successful development run records `DTB4WK`. **Do not open the historical test until this is reconciled and the final DTB4WK snapshot is hashed.**

## One operational convention that needs audit

The frozen Stage-2 files say model features are scaled using training-fold mean/std, but they do not state the `ddof` for this model scaler. The saved Stage-1 implementation used population standard deviation (`ddof=0`). This reconstruction preserves that convention.

This is different from the macro-surprise construction itself, where the frozen method explicitly uses `ddof=1` over the prior 12 releases.

## Run development first

Copy `stage2_run_spec.example.json` to a local run spec and replace the placeholder paths with the immutable source files.

```bash
python stage2_backtest.py \
  --spec stage2_run_spec.json \
  --mode development \
  --output-dir stage2_dev_reconstruction
```

Expected outputs:

- `stage2_predictions.csv`
- `stage2_metrics.csv`
- `stage2_result_summary.json`
- `stage2_feature_availability.csv`
- `run_hash_manifest.json`
- `development_reproduction_check.json`
- `run_report.json`

`development_reproduction_check.json` must be inspected before anything else.

If it says `MISMATCH`, stop. Do not change parameters to make the result look better. Audit the source snapshots, 2019-01 handling, risk-free series, price construction, and any implementation convention.

## Historical lock

Historical mode requires **both**:

1. the gate file to contain a recognized GO status; and
2. the explicit token `CONFIRM_HISTORICAL_TEST_GO`.

Example only after the team approves the final freeze:

```bash
python stage2_backtest.py \
  --spec stage2_run_spec.json \
  --mode historical \
  --historical-approval-token CONFIRM_HISTORICAL_TEST_GO \
  --output-dir stage2_historical_run
```

With the current `SEALED_NOT_SCORED` gate, this command intentionally fails.

## What is not built here

The Black-Litterman portfolio layer, originally left out of the reconstruction, has since been added in `stage2_portfolio.py` (see "Portfolio layer" above); its open conventions are documented rather than inferred from the earlier MVP.

The JEV standard-RAG and Causal-RAG signal generators are not built here. When they are ready, they should feed the same frozen downstream scoring logic.

## Tests

```bash
pytest -q test_stage2_backtest.py
```

The tests cover the January month-arithmetic bug, the 48-label burn-in, missing-value handling, inner-CV purge, DTB4WK conversion, calendar-month retention, historical lock, and deterministic bootstrap behavior.
