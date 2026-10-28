# Freeze gate 5 extended to TLT — 2026-10-28

TLT is held by the primary Agentic Workflow (JEV) and by its Committee variant. Gate 5 checks that the pinned, distribution-adjusted prices include every official distribution. Stage 2 ran it for SPY, IEF and LQD. This run applies the same criteria, C1–C6, to TLT with the Stage 2 code imported unchanged (`stage2/scoring/check_dividend_adjustment.py`).

**Result under the pre-registered criteria: FAIL, on C2 only.** Every other criterion passes. The direct test of the adjustment, C5, passes on all 61 ex-dates where raw prices exist. A team decision is needed (below).

## Inputs

- **Official records.** iShares' fund download for TLT (portfolioId 239454), read in a browser on 2026-10-28 20:33 UTC. The file's SHA-256 is `8a1ae8e2…5b003` (2,546,273 bytes).
  - The Distributions, Historical NAV and monthly NAV total-return rows were extracted for ex-dates 2014-01-01..2023-02-01 and months 2013-12..2023-01.
  - The SHA-256 of each extract was computed in the browser and is re-verified by `native_backtest/scripts/check_tlt_distributions.py`.
  - No historical-test-period value is stored.
- **Records:**
  - `native_backtest/data/tlt_dividend_check/` — the 109 distributions, 109 NAV ex-date pairs and 110 monthly NAV total returns.
  - The distribution table and the NAV file's ex-dividend column agree on every date.
- **Prices:**
  - The shared evaluator's TLT series, cut at 2023-02-01, the last development price.
  - Before 2018 it is the scaled distribution-adjusted Close.
  - From 2018 it is the adjusted Close, with raw High/Low available for C5.

## Results

| Criterion | What it tests | TLT | Pass rule | Result |
|---|---|---|---|---|
| C1 coverage | Every official ex-date is a trading day with matching previous NAV date | 109/109 | all | PASS |
| C2 ex-date capture | (adjusted price move − NAV price move) / distribution, on ex-dates | κ = 1.29, 99% CI 0.95–1.63 | κ in 0.75–1.25, CI excludes 0 and 2 | **FAIL** (point estimate just above 1.25) |
| C3 monthly capture | Same, month by month | κ = 1.00, CI 0.68–1.32 | as C2 | PASS |
| C4 cumulative capture | Total over 2014-02..2023-01 | κ = 0.98 | 0.90–1.10 | PASS |
| C5 implied distribution (2018+) | Raw vs adjusted prices imply each official amount | 61/61 | all | PASS |
| C6 informative NAV dates | Ex-dates where the distribution exceeds 6 noise SDs | 0 informative | no failures | PASS (non-decisive) |

The full output is in `native_backtest/out/tlt_dividend_gate/`.

## Why C2 misses

The day-level residual has an SD of about 27 bp, against an average distribution of 19 bp. This residual is the gap between the ETF's closing-price move and its NAV move; the NAV uses evaluated bond prices, not the ETF's own trades. It is noise in the test, not evidence about the adjustment:

- Where the adjustment can be tested directly (2018+, C5), the adjusted series embeds exactly the official amount on all 61 ex-dates. Yet C2 on those same dates is 1.37.
- Pre-2018, C2 is 1.21, inside the band.
- The median-based ratio is 1.10.
- Monthly and cumulative capture are 1.00 and 0.98.

The C2 band was set for SPY, IEF and LQD, whose ex-date residuals are smaller. Their C2 values were 0.92, 1.03 and 1.10. TLT has about twice IEF's duration.

## Decision needed (team)

1. **Accept TLT with a documented deviation.** C5 is the decisive test where raw prices exist, and C3/C4 confirm capture at monthly and cumulative horizons. Record the C2 result as noise-limited.
2. **Or tighten the evidence first.** Obtain raw TLT prices before 2018 so that C5 also covers 2014–2017, then re-run.

Either way, the criteria are not changed after seeing the result. This record stands as a FAIL under the pre-registered rule until the team decides.
