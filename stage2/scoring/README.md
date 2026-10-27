# Stage 2 Scoring Code — Canonical Reconstruction

This package reconstructs the **Stage 2 A/B forecast scorer** from the frozen Stage-2 methodology, frozen config, signal manifest, saved development summary, and the existing Stage-1 implementation.

## Important status

This is the **canonical reconstructed implementation**, not a claim that we recovered the exact temporary code that produced the earlier development run. That earlier code was executed but was not saved as a standalone file.

For that reason, the first job of this scorer is to rerun **development only** and compare the new output against the saved `stage2_dev_result_summary.json`. A mismatch is a **hard audit signal**. It must not be tuned away after looking at the historical test.

The historical test is locked by default.

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

## What is not reconstructed here

The Black-Litterman portfolio layer is secondary evidence and is **not** implemented in this reconstruction. The frozen files record the high-level allocator parameters, but the available artifacts do not fully specify every computational convention from the earlier MVP. Inventing those details would reduce reproducibility rather than improve it.

The JEV standard-RAG and Causal-RAG signal generators are also not built here. When they are ready, they should feed the same frozen downstream scoring logic.

## Tests

```bash
pytest -q test_stage2_backtest.py
```

The tests cover the January month-arithmetic bug, the 48-label burn-in, missing-value handling, inner-CV purge, DTB4WK conversion, calendar-month retention, historical lock, and deterministic bootstrap behavior.
