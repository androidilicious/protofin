# Freeze gate 5: ETF distribution adjustment — test design (v1, 2026-10-27)

Written and committed **before** the gate checks were run. Only one look preceded it: a quick comparison of IEF ex-date returns with official NAV moves, done to see whether NAV-based checks could separate adjusted from price-only series. It showed that a single ex-date for a monthly bond fund can't be judged against NAV because of noise. That is why the gate below combines aggregate NAV tests with a per-date test that uses no NAV.

## Question

Do the daily prices used by the canonical scorer (the spliced `Close` series in `stage2_run_spec_dev_v4.json`) include every cash distribution, with nothing missing and nothing counted twice? The check covers every price the development run uses.

## Official records (issuer only)

| Ticker | Distributions | Unadjusted reference |
|---|---|---|
| SPY | State Street `spdr-etf-historical-distributions.xlsx` | State Street `navhist-us-en-spy.xlsx` (daily NAV) |
| IEF | iShares fund page / fund download (Distributions; Historical "Ex-Dividends") | iShares fund download: daily NAV per share, monthly NAV total return |
| LQD | iShares fund download (Distributions; Historical "Ex-Dividends") | as IEF |

- Neither issuer publishes historical **market** closing prices for 2014–2023. The State Street premium/discount file covers only about the last 2.4 years. The unadjusted official reference is therefore NAV per share.
- Captures were limited to ex-dates 2014-01-01 to 2023-02-01 and months to 2023-01. No historical-test-period value is stored.
- Provenance (URLs, file and capture hashes, retrieval times) is in `stage2/data/dividend_check/official_records_provenance.json`.

## Definitions

For ex-date *E* with previous trading day *P*, official distribution *D*, official NAV *N*, and scorer adjusted price *A*:

- `a = log(A_E / A_P)` is the scorer's adjusted return.
- `p = log(N_E / N_P)` is the raw (price-only) NAV move.
- `y = log(1 + D / N_E)` is the distribution's contribution to NAV total return.
- `r = a − p − y` is the residual against the official NAV total return. It is 0 if the adjustment is correct, −y if the series is price-only, and +y if the distribution is counted twice. A nonzero residual also contains noise from the change in the market premium to NAV.
- The capture ratio is `κ = mean(a − p) / mean(y)`. It is 1 when the adjustment is correct, 0 when the series is price-only and 2 when distributions are counted twice.

## Criteria

Each must hold for SPY, IEF and LQD.

**C1 — Coverage.**
- Every official ex-date in the window is a trading day of the scorer's series.
- The scorer's previous trading day equals the issuer's previous NAV date.
- Every month from 2014-01 to 2023-01 is present.

**C2 — Ex-date capture.**
- κ (ex-dates) lies in [0.75, 1.25].
- Its 99% interval (κ ± 2.576·SE) excludes 0 and 2.

**C3 — Monthly capture.**
- Calendar-month adjusted returns, measured between the last trading days of each month, are compared with the official monthly NAV total returns. For iShares these are published directly. For SPY they are computed from month-end NAVs, with distributions reinvested at the ex-date NAV.
- κ_m = mean(a_m − p_m)/mean(y_m), where y_m is the summed distribution contribution in the month. κ_m lies in [0.75, 1.25].
- Its 99% interval excludes 0 and 2.
- This is the horizon the scorer actually uses, and it covers the 2018-01-02 splice month.

**C4 — Cumulative capture.**
- Σ(a_m − p_m)/Σ y_m from 2014-01-31 to 2023-01-31 lies in [0.90, 1.10].

**C5 — Per-date implied distribution (no NAV).**
- Applies to the 2018+ price files, which carry raw (unadjusted) Open/High/Low next to the adjusted Close.
- The adjustment factor F = A/raw close is constant between ex-dates. Each day bounds it: F ∈ [A/High, A/Low]. Each bound is widened by 0.005/A to allow for two-decimal rounding.
- Intersecting the bounds over up to 10 trading days before *E* (and after the previous ex-date), and up to 10 trading days from *E* (and before the next ex-date), gives intervals for F_before and F_after.
- The implied distribution fraction is 1 − F_before/F_after. It must overlap the official fraction D/C_P, with C_P ∈ [Low_P, High_P].
- An empty intersection means F was not constant, so an unexplained adjustment occurred. It fails.
- The 2014–2017 file has adjusted OHLC and no raw prices, so C5 can't be applied there. C2–C4 and C6 cover that period.

**C6 — Per-date NAV check where informative.**
- σ̂ is the robust standard deviation (1.4826·MAD) of r across the ticker's ex-dates.
- An ex-date is informative if y > 6σ̂, meaning the correct, price-only and double hypotheses are more than 6σ̂ apart.
- On every informative ex-date, r must be closer to 0 than to −y or +y.

The gate is **PASS** only if C1–C6 hold for all three tickers. Any failure is a discrepancy: work stops, no data is changed, and the result is reported. Dates that are not informative under C6 are listed as non-decisive, not as passes.

## Automation

- `stage2/scoring/build_dividend_check_inputs.py` re-verifies every capture hash and writes the normalized official CSVs.
- `stage2/scoring/check_dividend_adjustment.py` runs C1–C6 and writes `stage2/results/dividend_gate/`.
- `stage2/scoring/test_dividend_adjustment.py` has two kinds of test. Synthetic tests confirm each criterion rejects price-only and double-counted series. A real-data test asserts the gate result whenever the inputs are present.
