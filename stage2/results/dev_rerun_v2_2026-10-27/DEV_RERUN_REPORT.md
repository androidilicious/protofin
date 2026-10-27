# Stage 2 development rerun — 2026-10-27

**Window:** development decisions 2019-03 to 2022-12 only (46 months; last holding-period exit 2023-02-01). The historical test (2023-01 to 2026-08) was not run, and no test-window return was computed.
**Systems:** A, B1–B5, B-All × SPY, IEF, LQD = 966 forecasts.
**No tuning:** no parameter, signal, window or convention was changed in response to these results.

## Inputs

| Item | Value |
|---|---|
| Scorer | `stage2/scoring/stage2_backtest.py` (SHA-256 `fb456541…`), canonical reconstruction supplied by the team |
| Run spec | `stage2/scoring/stage2_run_spec_dev_v2.json` (SHA-256 `f8e71991…`) |
| Macro panel | `stage2/data/model_scoring_panel_E4_meanrule.csv` (SHA-256 `459bef98…`), per BUG-2026-10-27-01 |
| Market, signal and risk-free inputs | Data snapshot v2 pins, fetched and hash-verified by `stage2/scoring/fetch_pinned_inputs.py` |
| Unit tests | 12 of 12 pass |

Two spec-level settings, neither of which changes a frozen rule:

1. `allow_close_as_adjusted: true` for all price files. Their `Close` column is the distribution-adjusted series (Open/High/Low are raw).
2. The VIX switch to VIXCLS is set at 2018-12-03, where that file begins. The two VIX files are identical on every overlapping day (2018-12-03 to 2022-12-30); the example spec's 2018-01-02 boundary would leave January–November 2018 without VIX and hard-stop the run.

## Integrity checks

- First development forecast (2019-03): **exactly 48 completed training labels** for every system and asset, decisions 2015-02 to 2019-01, latest training label 2019-01, 11 inner CV folds. The 2019-01 row is retained with retail sales missing (set to 0 only after training-fold scaling).
- Training size grows from 48 to 93 labels across the window.
- All systems share identical scoring dates and identical targets.

## Results (canonical run; positive = better than A)

Normalised pooled squared-error improvement vs A, paired circular block bootstrap (6-month blocks, 5,000 draws, seed 20261027).

| Contrast | Point | 90% interval | Bootstrap share ≤ 0 |
|---|---|---|---|
| **B-All vs A (primary)** | −0.0461 | −0.1253 to +0.0008 (95%: −0.1393 to +0.0010) | 0.764 |
| B1 credit level | +0.0037 | −0.0007 to +0.0105 | 0.066 |
| B2 credit change 3m | −0.0301 | −0.0904 to +0.0048 | 0.744 |
| B3 curve 10y–3m | +0.0032 | −0.0009 to +0.0095 | 0.174 |
| B4 VRP proxy | −0.3844 | −1.0979 to −0.0001 | 0.951 |
| B5 own momentum 12m | −0.0180 | −0.0537 to +0.0043 | 0.851 |

Per-asset metrics for every system are in `stage2_metrics.csv`; every forecast with its selected alpha is in `stage2_predictions.csv`; alpha counts are in `alpha_selection_summary.csv`.

Intercept-only selection: A chose it in 100% of SPY, 98% of LQD and 22% of IEF forecasts. B-All chose it in 98% of IEF, 41% of SPY and 28% of LQD forecasts.

### Reading the results

- B-All is not better than A; the 95% interval includes zero.
- B1 and B3 remain small positives whose 90% intervals include zero.
- B4's 90% interval now lies just below zero. This is one of five uncorrected component diagnostics (Holm within the five would not reject at 5%).
- **Influence:** 99% of B4's loss and all of B-All's loss come from decisions 2020-05 and 2020-06, after the March 2020 VRP extremes entered training. Excluding those months, B-All's average is +0.0006. This is a diagnostic only; winsorisation remains a robustness run and may not replace Primary.

## Differences from the previous development results

Full field-by-field table: `comparison_vs_previous_development.csv`. Three columns separate the effects:

- **saved summary:** `results/stage2_dev_result_summary.json` from the earlier, unsaved scorer;
- **reconstruction, old panel:** this scorer on `model_unbalanced_panel.csv` (diagnostic run in `../dev_rerun_diag_oldpanel_2026-10-27/`);
- **canonical:** this scorer on the corrected panel.

| Field | Saved | Reconstruction, old panel | Canonical |
|---|---|---|---|
| B-All vs A point | −0.0420 | −0.0497 | −0.0461 |
| B-All 95% upper | +0.0121 | +0.0011 | +0.0010 |
| B1 point | +0.0038 | +0.0002 | +0.0037 |
| B2 point | −0.0296 | −0.0351 | −0.0301 |
| B3 point | +0.0032 | −0.0002 | +0.0032 |
| B4 point | −0.3702 | −0.3815 | −0.3844 |
| B5 point | −0.0180 | −0.0226 | −0.0180 |
| A OOS R² IEF | −0.00513 | −0.00005 | −0.00515 |
| B-All OOS R² LQD | −0.0532 | −0.0609 | −0.0607 |

Findings:

1. **The canonical run is far closer to the saved summary than the old-panel run is.** For A, B1, B3 and B5 it agrees within about 0.00003. The earlier development run therefore appears to have already used the mean for the 2019-04 retail-sales cell (as Stage 1 did); the aggregation bug lived in the panel builder but probably did not affect the saved results.
2. **Remaining differences are confined to systems containing credit change (B2) or VRP (B4), and hence B-All.** They point to a difference in how the lost original code built those two signals (candidates: the date used for "three calendar months earlier", or VIX handling in January–November 2018). The canonical scorer follows the frozen definitions; the original cannot be inspected.
3. **The substantive development conclusions are unchanged:** B-All not better than A; credit level and curve small and inconclusive; credit change, momentum and VRP worse; intervals include zero except B4's 90% interval, which now sits just below zero.
4. `development_reproduction_check.json` reports MISMATCH at the scorer's 1e-8 tolerance for both runs. Per the package's rule this is a stop signal for historical scoring until the team formally adopts the canonical reconstruction as the reference.

## What this scorer does not implement

- The Black–Litterman allocator, its frozen Ω rule (estimated from A's development errors) and all secondary portfolio metrics (net return, volatility, Sharpe, drawdown, certainty-equivalent return, turnover, break-even cost) and both portfolio benchmarks.
- Holm adjustment across the primary family (needed once C and D exist).
- Model-scaler `ddof` is not specified in the freeze; the scorer uses `ddof=0`, inherited from Stage 1.
