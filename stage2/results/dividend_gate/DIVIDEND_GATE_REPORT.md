# Freeze gate 5 — ETF distribution adjustment: result

**Status: PASS** (all criteria C1–C6 for SPY, IEF and LQD). Run on 2026-10-27/28 UTC against official issuer records. The test design ([`Stage2_Dividend_Adjustment_Gate_v1.md`](../../methodology/Stage2_Dividend_Adjustment_Gate_v1.md)) was committed in `54890df` before this run. No data were changed.

## What was checked

- **Price series:** the spliced adjusted `Close` series that the canonical scorer uses (`stage2_run_spec_dev_v4.json`). Every price is dated on or before 2023-02-01, the last price in the development run.
- **Official records:**
  - SPY distributions and daily NAV from State Street.
  - IEF and LQD distributions, daily NAV and monthly NAV total return from iShares.
  - Details are in [`official_records_provenance.json`](../../data/dividend_check/official_records_provenance.json).
- **Coverage:** every official ex-date from 2014-02 to 2023-02-01 (SPY 36, IEF 109, LQD 109) and every month from 2014-01 to 2023-01.
- **No market closes:** neither issuer publishes historical market closing prices for these years. NAV per share is the official unadjusted reference.
- **Second, NAV-free check on 2018+ files:** these files carry raw Open/High/Low next to the adjusted Close. C5 uses them to infer the distribution from the price series alone.

## Summary

| Ticker | Ex-dates checked | C1 coverage | C2 κ ex-date (99% CI) | C3 κ monthly (99% CI) | C4 κ cumulative | C5 implied D (2018+) | C6 informative NAV dates | Result |
|---|---|---|---|---|---|---|---|---|
| SPY | 36 (2014-03-21 to 2022-12-16) | PASS | 0.924 (0.886–0.962) | 0.991 (0.850–1.132) | 0.997 | 20/20 | 36/36 | **PASS** |
| IEF | 109 (2014-02-03 to 2023-02-01) | PASS | 1.031 (0.865–1.196) | 0.999 (0.808–1.190) | 0.974 | 61/61 | 0/0 | **PASS** |
| LQD | 109 (2014-02-03 to 2023-02-01) | PASS | 1.102 (0.896–1.308) | 0.970 (0.741–1.198) | 0.973 | 61/61 | 0/0 | **PASS** |

κ is the share of the official distribution reflected in the adjusted series. It is 1 when the adjustment is correct, 0 when the series is price-only and 2 when distributions are counted twice.

## Observations

1. **No missing, partial or double adjustment was found.**
   - Monthly κ is 0.97–1.00 and cumulative κ is 0.97–1.00, measured over 2014-01-31 to 2023-01-31. A price-only series would score 0 and a double-counted one 2.
   - The C3 month set includes the 2018-01-02 splice month.
2. **The per-date implied distribution (C5) agrees with the official amount on all 142 tested 2018+ ex-dates.**
   - On 128 of them the implied interval excludes both 0 and twice the official amount: SPY 19/20, IEF 50/61, LQD 59/61.
   - The other 14 have wide intervals and are consistent but not decisive. Most are IEF dates in 2020–2022 with small distributions; 2023-02-01 has only a one-day window after the ex-date because prices are capped at the end of development.
3. **SPY ex-date returns are on average 3.5 bp below NAV total return** (κ 0.92, 99% CI 0.89–0.96, inside the 0.75–1.25 band).
   - C5 shows the adjustment amounts themselves are right. For example, on 2022-03-18 the implied amount is $1.364 against an official $1.366, while the NAV residual is −6.6 bp.
   - The monthly and cumulative κ (0.99 and 1.00) show nothing accumulating.
   - The gap is a market-close vs NAV difference on these quarterly expiration Fridays, not a data issue.
4. **For IEF and LQD a single ex-date can't be judged against NAV.**
   - The robust noise SD of the residual is 7.7 bp for IEF and 18.7 bp for LQD, against average distributions of 15 bp and 26 bp. This is the market-close vs NAV gap: iShares bond NAVs are struck before the market close.
   - So C6 has no informative dates for them. Their per-date evidence is C5, which covers 2018+ only.
   - Their 2014–2017 ex-dates are covered by the aggregate tests C2–C4 and by monthly residuals that behave like mean-reverting premium noise, not permanent steps.
   - **A single missed IEF/LQD distribution before 2018 could not be detected individually.**

## Per-date detail

All 254 ex-dates are in [`dividend_check_by_ex_date.csv`](dividend_check_by_ex_date.csv). It records the official amount, raw NAV move, official NAV total return, adjusted-price return, residual, implied distribution and C5/C6 status for each date. The monthly comparison is in [`dividend_check_by_month.csv`](dividend_check_by_month.csv).

Column definitions:

- **Residual** = adjusted-price return − official NAV total return.
- **Implied distribution** is the distribution inferred from the adjusted-price series alone (C5), as point [interval].

### SPY (all ex-dates)

| Ticker | Ex-date | Official distribution ($) | Raw NAV move (bp) | Official NAV total return (bp) | Adjusted-price return (bp) | Residual (bp) | Implied distribution, no NAV ($) | C5 | C6 |
|---|---|---|---|---|---|---|---|---|---|
| SPY | 2014-03-21 | 0.824610 | -73.1 | -29.2 | -39.7 | -10.6 |  | n/a (pre-2018) | PASS |
| SPY | 2014-06-20 | 0.936690 | -30.5 | 17.2 | 20.0 | 2.8 |  | n/a (pre-2018) | PASS |
| SPY | 2014-09-19 | 0.939190 | -51.3 | -4.7 | -9.9 | -5.1 |  | n/a (pre-2018) | PASS |
| SPY | 2014-12-19 | 1.134920 | -9.4 | 45.5 | 38.9 | -6.5 |  | n/a (pre-2018) | PASS |
| SPY | 2015-03-20 | 0.930810 | 45.2 | 89.6 | 87.4 | -2.3 |  | n/a (pre-2018) | PASS |
| SPY | 2015-06-19 | 1.030070 | -101.3 | -52.8 | -43.3 | 9.6 |  | n/a (pre-2018) | PASS |
| SPY | 2015-09-18 | 1.033430 | -212.5 | -160.7 | -157.7 | 3.1 |  | n/a (pre-2018) | PASS |
| SPY | 2015-12-18 | 1.211550 | -236.2 | -177.1 | -180.3 | -3.3 |  | n/a (pre-2018) | PASS |
| SPY | 2016-03-18 | 1.049604 | -7.6 | 43.7 | 40.9 | -2.8 |  | n/a (pre-2018) | PASS |
| SPY | 2016-06-17 | 1.078442 | -84.2 | -32.4 | -37.0 | -4.6 |  | n/a (pre-2018) | PASS |
| SPY | 2016-09-16 | 1.082068 | -87.8 | -37.5 | -37.0 | 0.6 |  | n/a (pre-2018) | PASS |
| SPY | 2016-12-16 | 1.328930 | -75.9 | -17.3 | -19.8 | -2.5 |  | n/a (pre-2018) | PASS |
| SPY | 2017-03-17 | 1.033118 | -56.5 | -13.2 | -18.4 | -5.2 |  | n/a (pre-2018) | PASS |
| SPY | 2017-06-16 | 1.183108 | -45.7 | 2.8 | 2.3 | -0.5 |  | n/a (pre-2018) | PASS |
| SPY | 2017-09-15 | 1.234574 | -29.8 | 19.6 | 13.0 | -6.6 |  | n/a (pre-2018) | PASS |
| SPY | 2017-12-15 | 1.351333 | 38.9 | 89.8 | 84.2 | -5.6 |  | n/a (pre-2018) | PASS |
| SPY | 2018-03-16 | 1.096775 | -22.7 | 17.2 | 10.8 | -6.4 | 0.747 [0.313, 1.184] | PASS | PASS |
| SPY | 2018-06-15 | 1.245568 | -53.8 | -9.1 | -12.6 | -3.5 | 1.184 [0.863, 1.506] | PASS | PASS |
| SPY | 2018-09-21 | 1.322611 | -48.6 | -3.5 | -9.3 | -5.7 | 1.159 [0.598, 1.725] | PASS | PASS |
| SPY | 2018-12-21 | 1.435429 | -262.8 | -204.8 | -205.2 | -0.4 | 1.943 [1.326, 2.577] | PASS | PASS |
| SPY | 2019-03-15 | 1.233119 | 6.3 | 50.1 | 49.4 | -0.7 | 1.012 [0.528, 1.498] | PASS | PASS |
| SPY | 2019-06-21 | 1.431640 | -60.4 | -12.0 | -14.7 | -2.7 | 1.630 [1.295, 1.968] | PASS | PASS |
| SPY | 2019-09-20 | 1.383619 | -94.3 | -48.3 | -47.2 | 1.1 | 1.349 [0.975, 1.725] | PASS | PASS |
| SPY | 2019-12-20 | 1.569992 | 0.8 | 49.7 | 44.1 | -5.6 | 1.653 [1.485, 1.822] | PASS | PASS |
| SPY | 2020-03-20 | 1.405559 | -487.8 | -429.6 | -431.2 | -1.7 | 1.034 [0.257, 1.861] | PASS | PASS |
| SPY | 2020-06-19 | 1.366242 | -98.2 | -54.4 | -57.2 | -2.8 | 1.297 [0.580, 2.021] | PASS | PASS |
| SPY | 2020-09-18 | 1.339224 | -151.2 | -111.3 | -115.1 | -3.8 | 2.289 [0.864, 3.733] | PASS | PASS |
| SPY | 2020-12-18 | 1.580000 | -76.8 | -34.3 | -39.9 | -5.6 | 1.639 [1.338, 1.943] | PASS | PASS |
| SPY | 2021-03-19 | 1.277788 | -37.7 | -5.0 | -18.8 | -13.7 | 1.207 [0.909, 1.510] | PASS | PASS |
| SPY | 2021-06-18 | 1.375875 | -163.0 | -130.4 | -134.9 | -4.5 | 1.275 [0.956, 1.596] | PASS | PASS |
| SPY | 2021-09-17 | 1.428117 | -122.8 | -90.9 | -97.4 | -6.6 | 1.429 [0.521, 2.345] | PASS | PASS |
| SPY | 2021-12-17 | 1.636431 | -137.2 | -102.1 | -106.4 | -4.3 | 1.734 [1.357, 2.116] | PASS | PASS |
| SPY | 2022-03-18 | 1.366009 | 85.3 | 116.3 | 109.7 | -6.6 | 1.364 [1.260, 1.470] | PASS | PASS |
| SPY | 2022-06-17 | 1.576871 | -20.9 | 22.0 | 21.7 | -0.3 | 1.844 [1.546, 2.147] | PASS | PASS |
| SPY | 2022-09-16 | 1.596398 | -112.4 | -71.5 | -76.4 | -5.0 | 1.200 [0.418, 1.997] | PASS | PASS |
| SPY | 2022-12-16 | 1.781400 | -155.8 | -110.1 | -118.1 | -8.1 | 1.772 [1.490, 2.059] | PASS | PASS |

### IEF and LQD (sample; all dates in the CSV)

| Ticker | Ex-date | Official distribution ($) | Raw NAV move (bp) | Official NAV total return (bp) | Adjusted-price return (bp) | Residual (bp) | Implied distribution, no NAV ($) | C5 | C6 |
|---|---|---|---|---|---|---|---|---|---|
| IEF | 2015-06-01 | 0.169088 | -89.0 | -73.3 | -43.3 | 30.1 |  | n/a (pre-2018) | non-decisive |
| IEF | 2017-12-21 | 0.164141 | -4.0 | 11.6 | 6.9 | -4.6 |  | n/a (pre-2018) | non-decisive |
| IEF | 2019-03-01 | 0.199053 | -50.9 | -31.8 | -33.7 | -1.8 | 0.180 [0.124, 0.236] | PASS | non-decisive |
| IEF | 2020-04-01 | 0.144016 | 28.0 | 39.8 | 40.9 | 1.0 | 0.223 [0.018, 0.428] | PASS | non-decisive |
| IEF | 2021-12-16 | 0.105857 | 21.0 | 30.2 | 28.2 | -2.0 | 0.136 [0.024, 0.249] | PASS | non-decisive |
| IEF | 2022-12-01 | 0.194028 | 97.3 | 117.2 | 109.2 | -7.9 | 0.180 [0.155, 0.206] | PASS | non-decisive |
| IEF | 2023-02-01 | 0.212178 | 52.3 | 73.7 | 71.4 | -2.3 | 0.597 [0.100, 1.096] | PASS | non-decisive |
| LQD | 2015-06-01 | 0.328650 | -101.8 | -74.1 | -54.0 | 20.3 |  | n/a (pre-2018) | non-decisive |
| LQD | 2017-12-21 | 0.254133 | 12.3 | 33.4 | 27.5 | -5.9 |  | n/a (pre-2018) | non-decisive |
| LQD | 2019-03-01 | 0.358431 | -41.6 | -10.7 | -18.2 | -7.6 | 0.359 [0.263, 0.455] | PASS | non-decisive |
| LQD | 2020-04-01 | 0.310037 | -95.6 | -70.3 | -144.4 | -74.8 | 0.376 [0.168, 0.587] | PASS | non-decisive |
| LQD | 2021-12-16 | 0.256407 | 0.3 | 19.7 | -0.9 | -20.5 | 0.297 [0.182, 0.412] | PASS | non-decisive |
| LQD | 2022-12-01 | 0.344008 | 133.9 | 166.1 | 124.5 | -41.0 | 0.365 [0.316, 0.415] | PASS | non-decisive |
| LQD | 2023-02-01 | 0.342062 | 53.3 | 84.2 | 101.1 | 16.7 | 0.903 [0.008, 1.805] | PASS | non-decisive |


## Reproduce

```bash
python stage2/scoring/build_dividend_check_inputs.py      # re-verifies capture hashes, rebuilds official CSVs
python stage2/scoring/check_dividend_adjustment.py --spec stage2/scoring/stage2_run_spec_dev_v4.json
(cd stage2/scoring && python -m pytest -q test_dividend_adjustment.py)
```

## Note on incidental exposure

While locating the issuers' data structures, previews printed some recent values:

- IEF's eleven most recent distribution amounts (ex-dates 2025-12-01 to 2026-10-01).
- Distribution record dates back to 2024 (dates only).
- October 2026 NAVs for IEF and SPY, and SPY premium/discount values for October 2026.

These are income amounts, dates and post-window NAV levels, not scored returns. No 2023-02 to 2026-08 price, return or model output was read or stored.
