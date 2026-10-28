# Freeze gate 5 extended to TLT: result, diagnosis and proposed resolution — 2026-10-28

TLT is held by the primary Agentic Workflow (JEV) and by its Committee variant. Gate 5 checks that the pinned, distribution-adjusted prices include every official distribution exactly once. Stage 2 ran it for SPY, IEF and LQD. This run applies the same criteria, C1–C6, to TLT, with the Stage 2 code imported unchanged (`stage2/scoring/check_dividend_adjustment.py`).

**Result under the pre-registered criteria: FAIL, on C2 only.** This record stands. The criteria were not changed after seeing the result.

**Diagnosis: the C2 miss comes from the ETF's premium to NAV moving at the turn of the month, not from the dividend adjustment.** Three tests that measure the adjustment directly all pass:

- The cumulative gap between adjusted prices and the official NAV total return is 0.01% over nine years. An adjustment error of the size C2 implies would have accumulated to 6.1%.
- C5 matches the official amount on all 61 ex-dates where raw prices exist.
- Re-scoring on the official NAV total return changes JEV's development net CER by −0.02 points.

**Proposed resolution (team decision):** accept the TLT prices with the C2 deviation documented, and pre-register an NAV-based robustness re-score before the protected window opens.

## 1. Inputs

- **Official records.** iShares' fund download for TLT (portfolioId 239454), read in a browser on 2026-10-28 (20:33 and 21:17 UTC; same file, SHA-256 `8a1ae8e2…5b003`, 2,546,273 bytes).
  - Extracted:
    - the Distributions, Historical NAV (ex-date pairs) and monthly NAV total-return rows for ex-dates 2014-01-01..2023-02-01 and months 2013-12..2023-01;
    - the full daily NAV history 2013-12-31..2023-02-01 (2,288 days, in three parts).
  - Every extract's SHA-256 was computed in the browser and is re-verified by the scripts.
  - No historical-test-period value is stored.
- **Prices.** The shared evaluator's TLT series, cut at 2023-02-01, the last development price. Before 2018 it is the scaled distribution-adjusted Close; from 2018 it is the adjusted Close, with raw High/Low available for C5.
- **Code.**
  - `native_backtest/scripts/check_tlt_distributions.py` runs the gate.
  - `native_backtest/scripts/diagnose_tlt_gate5.py` runs the diagnosis.
  - Outputs are in `native_backtest/out/tlt_dividend_gate/`.

## 2. Gate result (pre-registered criteria)

| Criterion | What it tests | TLT | Pass rule | Result |
|---|---|---|---|---|
| C1 coverage | Every official ex-date is a trading day with matching previous NAV date | 109/109 | all | PASS |
| C2 ex-date capture | (adjusted price move − NAV price move) / distribution, on ex-dates | κ = 1.29, 99% CI 0.95–1.63 | κ in 0.75–1.25, CI excludes 0 and 2 | **FAIL** |
| C3 monthly capture | Same, month by month | κ = 1.00 | as C2 | PASS |
| C4 cumulative capture | Total over 2014-02..2023-01 | κ = 0.98 | 0.90–1.10 | PASS |
| C5 implied distribution (2018+) | Raw vs adjusted prices imply each official amount | 61/61 | all | PASS |
| C6 informative NAV dates | Ex-dates where the distribution exceeds 6 noise SDs | 0 informative | no failures | PASS (non-decisive) |

## 3. Diagnosis

**What C2 measures.** On an ex-date, C2's numerator is the adjusted market-price move minus the official NAV move.

- On a day *without* a distribution, the adjustment factor is constant, so that difference is purely the **change in the ETF's premium/discount to NAV**. Closing price and NAV are struck differently: the NAV uses evaluated bond prices, the close is the last ETF trade.
- On an ex-date the difference is that premium change **plus** any adjustment error.
- C2 attributes all of it to the adjustment.

**Daily residuals, 2014-01..2023-02, from the official daily NAV.**

| Days | n | Mean residual | SD | t |
|---|---|---|---|---|
| All days | 2,287 | 0.0 bp | 27.0 bp | 0.0 |
| Ex-dates | 109 | **+5.6 bp** | 26.6 bp | 2.2 |
| Ex-dates on the first trading day of the month | 100 | +6.2 bp | 27.5 bp | 2.3 |
| Ex-dates mid-month (December) | 9 | −1.1 bp | 10.3 bp | −0.3 |
| First trading day of the month with **no** distribution (Januaries) | 10 | +4.7 bp | 19.7 bp | 0.7 |
| All other days | 2,168 | −0.3 bp | 27.0 bp | −0.5 |
| Day after an ex-date | 108 | −1.7 bp | 22.7 bp | −0.8 |

Lag-1 autocorrelation of the daily residual is −0.48. That is the signature of price/NAV timing noise: a premium that opens up one day closes the next.

**Interpretation.**

1. The C2 excess (+5.6 bp per ex-date, κ − 1 = 0.29) is the size of the premium move on ordinary month-start days. TLT's regular ex-dates are the first trading day of each month.
   - On first trading days *without* a distribution the premium also rises, by +4.7 bp (n = 10, so not significant on its own).
   - The mid-month December ex-dates show no excess (−1.1 bp).
   - The excess therefore follows the calendar day, not the distribution.
2. A real adjustment error would not reverse. Missing or double-counted distributions would accumulate in the price series.
   - The cumulative gap between the adjusted close and the official NAV total-return index ends at **+0.01%** after nine years. At the C2 excess, an adjustment error would have reached **6.1%**.
   - The gap stays within the premium band throughout. Its extremes are −5.2% and +1.2% during the 2020 dislocation and −1.6% in 2022; in every other year it stays within ±0.85%.
3. Where raw prices allow a direct test (2018+, C5), the adjusted series embeds exactly the official amount on all 61 ex-dates. Yet C2 on those same dates is 1.37.
4. Summing the ex-day and next-day residuals lowers the estimate to 1.21. This is consistent with partial reversal of the premium move.

**Conclusion.** C2 fails because its estimator is biased by a turn-of-month premium effect in TLT that the gate's design did not anticipate. The gate was calibrated on SPY, IEF and LQD, which have lower duration and smaller premium moves. The adjustment itself is complete and correct to within 0.01% over 2014–2023.

**Materiality.** JEV and the Committee were re-scored on development months (2019-03..2022-12) with TLT returns from the official NAV total-return index, which removes the premium entirely:

| | Net CER, market prices | Net CER, NAV total return | Difference | vs own benchmark, difference |
|---|---|---|---|---|
| Agentic Workflow (JEV) | 4.675% | 4.656% | −0.02 pts | −0.0002 pts |
| Agent Committee (variant) | 5.114% | 5.076% | −0.04 pts | −0.02 pts |

## 4. Proposed resolution

This proposal does not relax or re-tune the threshold, and it does not re-label the result.

1. **Record.** Gate 5 for TLT remains **FAIL on C2** under the pre-registered rule. The deviation, the diagnosis above and its evidence are attached to the freeze record.
2. **Disposition (for team approval).** Accept the pinned TLT prices for the primary backtest. The decisive property, that every distribution is included exactly once, is verified directly by C5 (2018+) and by cumulative tracking against the official NAV total return (2014–2023). The C2 shortfall is explained by a measured calendar effect in the premium.
3. **Pre-registered robustness check (before the window opens).**
   - For the Agentic Workflow (JEV) and its Committee variant, the protected-window results will also be reported with TLT returns from iShares' official NAV total return.
   - If the primary net-CER contrast involving JEV changes sign, or its Holm-adjusted p-value crosses 0.05, between the two price sources, the result is reported as price-source-sensitive.
   - This adds a check; it does not replace the primary price source.
4. **Gate design for future assets (version 2, prospective only).** Estimate C2 net of the same-calendar-day premium move, using first trading days without a distribution as the control. Keep the existing C2 alongside. This applies only to assets added after the change, never retroactively to TLT.

If the team prefers stronger evidence before accepting, the alternative is to obtain pre-2018 raw TLT prices so that C5 also covers 2014–2017, then re-run.
