# Official issuer records for freeze gate 5

These records are used only to check that the scorer's adjusted ETF prices include every distribution. The design is in [`../../methodology/Stage2_Dividend_Adjustment_Gate_v1.md`](../../methodology/Stage2_Dividend_Adjustment_Gate_v1.md) and the result in [`../../results/dividend_gate/`](../../results/dividend_gate/).

| File | Contents |
|---|---|
| `raw_capture/*.txt` | Rows extracted from the issuers' published files on 2026-10-28 UTC. Each file's SHA-256 was computed in the browser at extraction and is re-verified by the builder. |
| `official_distributions.csv` | Ex-date, record date, payable date and per-share amount. SPY from State Street; IEF and LQD from iShares. |
| `official_nav_exdate_pairs.csv` | Official NAV on each ex-date and on the previous NAV date. For iShares it also carries the NAV file's own ex-dividend column, which the builder cross-checks against the distribution table. |
| `official_monthly_nav_total_return_ishares.csv` | iShares' published monthly NAV total return (%), 2013-12 to 2023-01. |
| `official_month_end_nav_ssga.csv` | State Street SPY month-end NAV, 2013-12 to 2023-01. |
| `official_records_provenance.json` | Source URLs, SHA-256 of the full downloaded issuer files, retrieval times and output hashes. |

- **Window.** Ex-dates run from 2014-01-01 to 2023-02-01 and months from 2013-12 to 2023-01. No historical-test-period value is stored.
- **Rebuild.** Run `python stage2/scoring/build_dividend_check_inputs.py`.
