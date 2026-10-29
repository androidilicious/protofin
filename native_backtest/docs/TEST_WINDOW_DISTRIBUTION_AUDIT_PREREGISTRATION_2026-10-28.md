# Test-window distribution audit: pre-registration (2026-10-28)

Written and committed **before** any official test-window record is captured or any check is run.

**Approval:** the project lead, 2026-10-28 21:01 ET. Gate 5 (distribution adjustment) is to be run on SPY, IEF, LQD and TLT over the historical evaluation period before the protected backtest opens, as a strictly isolated data-quality audit.

**What the approval does not cover:** opening the protected backtest, incurring paid inference, or bypassing any Causal RAG gate.

## Question

Do the pinned, distribution-adjusted closing prices that the shared evaluator would use in the protected window include every official cash distribution exactly once? This is the same question Stage 2 gate 5 answered for the development period (`stage2/methodology/Stage2_Dividend_Adjustment_Gate_v1.md`).

## Isolation rules

- **No strategy is involved.** No investment strategy, decision record, forecast, portfolio, benchmark, CER, Sharpe or performance comparison is run, read or produced.
  - The audit script imports only the Stage 2 gate code and the market-data loader.
  - It does not import the accounting, benchmark, records, lock or system modules.
- **Inputs are limited to two kinds:**
  - the pinned price files, verified against their recorded SHA-256;
  - the issuers' official records.
- **Outputs are limited to gate statistics:**
  - capture ratios and their intervals;
  - residuals against the official NAV total return, in basis points;
  - distribution sizes;
  - per-date pass, fail or non-decisive status.
- **No return series is saved.** The per-date and per-month adjusted-price and NAV-total-return columns that the gate computes internally are dropped before saving.
- **Separate locations:**
  - script: `native_backtest/scripts/audit_test_window_distributions.py`;
  - official records: `native_backtest/data/test_window_dividend_audit/`;
  - results: `native_backtest/out/data_audit/test_window_gate5/`.
- **Separation from development and selection.** The audit is not used for model development, strategy selection or the benchmark. All of those are already frozen or fixed.

## Window

The protected window covers decision months 2023-01 to 2026-08. Their holding periods run from the 2023-02-01 close (entry) to the 2026-10-01 close (last exit), taken from the evaluation calendar.

| Item | Development gate | This audit |
|---|---|---|
| Ex-dates | 2014-01-01 to 2023-02-01 | **2023-02-02 to 2026-10-01** (the first ex-date not already checked, up to the last price the protected window uses) |
| Months (C3) | 2014-01 to 2023-01 | **2023-01 to 2026-09**. 2023-01 is the base month; it was also covered by the development gate |
| Cumulative (C4) | 2014-01-31 to 2023-01-31 | **2023-01-31 to 2026-09-30**, which is the gate code's existing rule of dropping the first month |
| Price cutoff | 2023-02-01 | **2026-10-01**. No later price is read |

## Official records (same issuers, files and fields as the development gate and its TLT extension)

| Fund | Distributions | Unadjusted reference |
|---|---|---|
| SPY | State Street `spdr-etf-historical-distributions.xlsx` | State Street `navhist-us-en-spy.xlsx` (daily NAV: ex-date pairs and month-end NAVs) |
| IEF (239456), LQD (239566), TLT (239454) | iShares fund download, Distributions sheet | Same file: Historical sheet (daily NAV and its ex-dividend column) and Performance sheet (monthly NAV total return) |

**How the records are captured.**
- The issuer sites cannot be reached from the backtest environment, so the records are read in a browser on the project lead's computer.
- The SHA-256 of each full issuer file and of each extracted capture is computed in the browser at the time of capture.
- Only rows inside the audit window are kept.
- The captures are transcribed into the repository and re-hashed there.
- PDF or file metadata is never used as evidence.

**Consistency checks, as in the development gate.** The run stops on any of these:
- the distribution table and the NAV-file ex-dividend column disagree;
- an ex-date appears in only one table;
- a non-income component is present without being accounted for.

## Criteria (unchanged)

C1–C6 exactly as pre-registered for the development gate. The thresholds are not changed:

| Criterion | Rule |
|---|---|
| C1 | Coverage |
| C2 | Ex-date capture κ in [0.75, 1.25], with a 99% interval excluding 0 and 2 |
| C3 | Monthly capture, same band and interval rule |
| C4 | Cumulative capture in [0.90, 1.10] |
| C5 | Per-date implied distribution from raw High/Low (rounding 0.005; up to 10 trading days on each side) |
| C6 | Per-date NAV check on informative dates (more than 6 robust SD) |

**Implementation.**
- The code is `stage2/scoring/check_dividend_adjustment.py`, imported unchanged; its SHA-256 is recorded in the results.
- Only its window constants (`EX_START`, `LAST_DEV_PRICE`, `MONTHS`) are set for this run.

## Outcomes and exceptions

- **PASS** only if C1–C6 hold for all four funds.
- **Every failure is reported as an exception**, with the criterion, dates and residuals. No data are changed.
- **Prior knowledge about TLT.** In the development period TLT failed C2 alone, which was diagnosed as a turn-of-month price–NAV premium effect, and that disposition is awaiting sign-off. If the same pattern recurs:
  - it is reported as a C2 failure;
  - it is then examined with the same read-only diagnostics: cumulative tracking against the official NAV total return, and C5.
  - The threshold is not relaxed.
- **Material problem.** A problem is material if the evidence shows a distribution omitted, double-counted or mis-sized in the adjusted prices, or if C4 falls outside its band. In that case:
  - work stops;
  - the finding is reported;
  - approval is requested before any change that would affect the frozen evaluation (for example a corrected price file).
- **Recorded for every run:**
  - the price-file hashes;
  - the issuer-file and capture hashes, with retrieval times;
  - the gate-code hash and repository commit;
  - all findings.

These are recorded before the final data freeze.
