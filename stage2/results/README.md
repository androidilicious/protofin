# Stage 2 results

| Path | Status | Contents |
|---|---|---|
| `dev_rerun_v2_2026-10-27/` | **Canonical** development forecast results | Predictions with selected alphas, metrics, contrasts, comparison with the superseded summary, `DEV_RERUN_REPORT.md` |
| `dev_rerun_v4_portfolio_2026-10-27/` | **Canonical** development portfolio results (diagnostic; Ω uses the same window) | Same forecasts (byte-identical) plus Black–Litterman weights, portfolio returns, metrics and frozen Ω |
| `dev_rerun_diag_oldpanel_2026-10-27/` | Diagnostic only | Canonical scorer on the superseded panel, used to separate reconstruction effects from BUG-2026-10-27-01 |
| `stage2_dev_result_summary.json` | **Superseded** | Output of the unsaved original scorer; kept unchanged as a historical record. Do not cite. |
| `stage2_historical_test_gate_*.json` | Gate records | The newest version is authoritative |
| `dividend_gate/` | Freeze gate 5: **PASS** | Distribution-adjustment check against State Street and iShares records: per-ex-date and per-month tables, status JSON, report |

The historical test (2023-01 to 2026-08) has not been run.
