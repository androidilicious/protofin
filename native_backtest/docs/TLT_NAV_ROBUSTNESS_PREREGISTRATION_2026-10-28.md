# TLT: official-NAV robustness analysis, pre-registration (2026-10-28)

**Status.**
- The project lead supports the proposed resolution in principle (2026-10-28), **subject to team sign-off**.
- This document fixes the robustness analysis before the protected window is opened. It changes nothing in the primary backtest.

## What stays as it is

1. **Gate 5 for TLT stays FAIL on C2:**
   - Distribution-day ratio κ = 1.29, 99% interval 0.95–1.63, against the pre-registered band 0.75–1.25.
   - The threshold is unchanged, and the result is not relabelled.
   - The diagnosis is attached to the freeze record: a turn-of-month price–NAV premium effect, with cumulative tracking against the official NAV total return within 0.01% over 2014–2023, and C5 passing 61/61 (`TLT_DISTRIBUTION_CHECK_2026-10-28.md`).
2. **The primary backtest keeps the pinned, distribution-adjusted market closing prices as the executable prices.** Official NAV is **never** used as an executable price in the primary backtest, because NAV is not a price at which the fund could be traded.
3. Decisions, weights, timing, costs and cash are identical in both analyses. Only the TLT return series differs.

## The robustness analysis

| Item | Pre-registered choice |
|---|---|
| Systems | Agentic Workflow (JEV), the primary system holding TLT; Agent Committee variant reported alongside |
| Windows | Development 2019-03..2022-12 (already computed in the diagnosis: JEV −0.02, Committee −0.04 points of net CER). Protected window: only after the signed GO, in the same run that scores the primary results |
| Substitution | Each month's TLT holding-period return (entry close to exit close) is replaced by the official iShares NAV total return over the same two dates: NAV change plus each distribution, reinvested at the ex-date NAV. Everything else is unchanged |
| Outputs | Net CER of JEV and of the Committee under both price sources. The primary contrasts that involve JEV (Agentic Workflow − Deterministic; Causal RAG − Agentic Workflow) under both sources, with paired bootstrap intervals and Holm-adjusted p-values computed exactly as in the primary analysis |
| Decision rule | The primary result is reported as **price-source-sensitive** if, between the two price sources, either primary contrast involving JEV changes sign or its Holm-adjusted p-value crosses 0.05. Otherwise it is reported as robust to the TLT price source |
| Reporting | Both sets of numbers are published together. The primary result is always the one on market prices; the NAV result never replaces it |

## Data needed before GO

The official daily NAV capture covers 2013-12-31..2023-02-01 (2,288 days, three hash-verified parts). The protected-window check needs NAV and distributions through 2026-09-30.
- They will be captured the same way, from iShares in the browser, with SHA-256 recorded per part.
- This must happen **before** the window is opened.
- This is public fund data, not a strategy result, so capturing it does not touch the protected window.

## Sign-off

| Name | Role | Decision on the TLT disposition and this pre-registration | Date |
|---|---|---|---|
| | Project lead | Supports in principle (2026-10-28) | 2026-10-28 |
| | | | |
