# Test-window distribution audit: result (2026-10-28)

**Pre-registration:** `TEST_WINDOW_DISTRIBUTION_AUDIT_PREREGISTRATION_2026-10-28.md` (commit `814fcd2`, pushed before any record was captured).
**Script:** `native_backtest/scripts/audit_test_window_distributions.py`.
**Results:** `native_backtest/out/data_audit/test_window_gate5/`.

## Formal result

**FAIL on C1 (coverage) only, on one date.** Every other criterion passes for all four funds.

**The exception.**
- IEF, LQD and TLT go ex-dividend on 2024-04-01.
- The official iShares NAV file dates the previous NAV 2024-03-31 (a Sunday). The scorer's previous trading day is 2024-03-28: 2024-03-29 was Good Friday, when the NYSE was closed.
- C1 requires the two dates to be equal, so it fails.

**Diagnosis (read-only, after the gate).**
- A hash-verified capture of the same official files shows the 2024-03-28 NAV repeated unchanged on 2024-03-29 and 2024-03-31, for all three funds.
- So the NAV the gate used is exactly the NAV of the scorer's previous trading day. The ex-date residual is unaffected:
  - IEF −8.7 bp (C6 PASS);
  - LQD +1.8 bp (non-decisive);
  - TLT +0.5 bp (non-decisive).
- C5, the check that uses no NAV, passes on that date for all three funds.

**Materiality.** Under the pre-registered definition this is **not material**. Nothing shows a distribution omitted, double-counted or mis-sized, and C4 is inside its band for every fund. It is calendar labelling in the official record, not an adjustment problem in the prices.

**What was not changed:** no price, threshold or criterion. The formal FAIL stands as recorded.

**Disposition (2026-10-28).** The project lead accepted the non-material treatment in principle, subject to the team's documented sign-off. The formal result and all evidence stay as recorded. The TLT development-period FAIL is unaffected and also awaits team sign-off.

## Results by fund (ex-dates 2023-02-02 to 2026-10-01; months 2023-01 to 2026-09)

| Fund | Ex-dates | C1 coverage | C2 ex-date κ (99% range) | C3 monthly κ (99% range) | C4 cumulative κ | C5 implied distribution | C6 informative dates |
|---|---|---|---|---|---|---|---|
| SPY | 15 | Pass | 0.970 (0.834–1.107) | 1.009 (0.774–1.244) | 1.005 | 15/15 | 2 of 2 pass |
| IEF | 44 | **Exception** (2024-04-01 label) | 0.957 (0.912–1.001) | 0.998 (0.948–1.048) | 0.994 | 44/44 | 44 of 44 pass |
| LQD | 44 | **Exception** (2024-04-01 label) | 1.008 (0.898–1.119) | 0.995 (0.877–1.114) | 0.984 | 44/44 | none informative |
| TLT | 44 | **Exception** (2024-04-01 label) | 1.011 (0.928–1.095) | 0.974 (0.877–1.071) | 0.986 | 44/44 | 2 of 2 pass |

**Thresholds (unchanged):**
- C2 and C3: κ in [0.75, 1.25], with a 99% range excluding 0 and 2.
- C4: in [0.90, 1.10].

**TLT.** C2 passes in the test window: κ 1.011, against 1.29 in the development period. The turn-of-month premium effect diagnosed there does not recur here. The development-period FAIL and its pending disposition are unaffected.

## Isolation

- **No strategy was run.** No investment strategy, decision record, forecast, portfolio, benchmark, CER, Sharpe or performance comparison was run, read or produced.
  - The script imports only the Stage 2 gate code and the market-data loader. A test checks this.
- **Saved outputs are gate statistics only:**
  - capture ratios and ranges;
  - residuals against the official NAV total return;
  - distribution sizes;
  - per-date status.
- **No return series is saved.** The gate's internal return columns are dropped before saving. A test checks this too.
- **Separation from development and selection.** The audit was kept apart from model development, strategy selection and the benchmark. All of those were frozen or fixed beforehand.

## Data versions and hashes

**Pinned prices (2018+ segment)**, verified against the configuration's recorded hashes:

| Fund | SHA-256 |
|---|---|
| SPY | `c3e8f068…618d` |
| IEF | `78dc6605…221d` |
| LQD | `21d2db30…e37c` |
| TLT | `fdecb0c3…3e52e` |

No price after 2026-10-01 was read.

**Official issuer files** (SHA-256 of the bytes as served, computed in the browser), retrieved 2026-10-29 01:11–01:15 UTC:

| File | SHA-256 | Note |
|---|---|---|
| iShares IEF | `474992dd…7283` | |
| iShares LQD | `dae49621…d914` | |
| iShares TLT | `a8d576b4…54ba5` | |
| State Street distributions | `6b65cbf9…6320` | Byte-identical to the development gate's copy |
| State Street SPY NAV history | `8721bbcc…6aa9` | |

**Captures:**
- 12 window captures and 3 diagnostic captures, each hashed in the browser and re-verified in the repository.
- Manifest: `native_backtest/data/test_window_dividend_audit/raw_capture/capture_manifest.json`.

**Normalised records:**

| File | SHA-256 |
|---|---|
| `official_distributions.csv` | `d07d5a3f…0e93` |
| `official_nav_exdate_pairs.csv` | `fb1ba570…23c0` |
| `official_monthly_nav_total_return_ishares.csv` | `e0bc8190…0996` |
| `official_month_end_nav_ssga.csv` | `b8a208e7…1617` |

**Gate code:** `stage2/scoring/check_dividend_adjustment.py` `534858dd…1381`, unchanged. Only its window constants were set for the run.

**Results** (final run at commit `0abe558`; an earlier run on the uncommitted script gave byte-identical CSVs):

| File | SHA-256 |
|---|---|
| `gate5_status.json` | `a0658144…dae39` |
| `gate5_by_ex_date.csv` | `11961089…3921` |
| `gate5_by_month.csv` | `fa712753…a3d9` |

**One change after pre-registration.** The read-only C1 diagnosis step was added to the script after the exception appeared. It runs after the gate and cannot change its status, criteria or thresholds. The gate part of the script is as pre-registered.

## Corrections required

None. No price file needs to change, so nothing that would affect the frozen evaluation was altered, and no approval for a correction is needed.
