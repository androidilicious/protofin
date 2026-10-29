# Common benchmark: specification, rationale and freeze record (2026-10-28)

**Benchmark:** 60% US Equities / 40% Intermediate-Term Treasuries (SPY/IEF), rebalanced monthly. ID `COMMON_60_40_SPY_IEF`.

**Status: FROZEN** on 2026-10-28 on the project lead's approval (`framework_config_v1.json` v1.4 → `common_benchmark.status = frozen`; approval record `native_backtest/config/approvals/common_benchmark_freeze_2026-10-28.json`). The approval covers this specification and its reporting rules only. It does not open the protected window, approve paid inference or bypass any Causal RAG gate.

**Protected window:** sealed. Nothing below uses a month at or after 2023-01. The benchmark was chosen before the window was opened. It will not be optimised or changed on the basis of protected-window results; once the window opens it cannot change at all.

**Frozen specification hashes (SHA-256):**
- Fingerprint: `fffd92b9731598385353749424b643e83ffbf0567403624cea7e170a75741aed`. It covers the benchmark's own fields (ID, weights, rebalancing, rules, role, decomposition) plus the shared settings it inherits (calendar, timing, costs, metrics), and ignores status and notes. The evaluator refuses to use the benchmark if the fingerprint no longer matches the approval record (`framework/benchmark.spec`).
- Complete frozen `common_benchmark` block: `7312e1881b208bf7d4420c6be1ebef65e3db1a0f4f7015698f2ef27cd6263642`.
- The proposal's fingerprint was `2fecfe0f…c848`. At the freeze only the wording of the role and of the decomposition field changed, as the approval required ("common passive reference"; "accounting decomposition, not a causal attribution"). Weights, rules and every inherited setting are identical, so no number changed.

## 1. What it is for

- **One reference line for all three primary approaches** (Deterministic Quantitative Model, Agentic Workflow represented by JEV, Agentic Causal RAG). It answers: *how did each approach perform relative to the same reference portfolio?*
- **It belongs to the evaluation and display layer only.** It never feeds any approach's forecasts, signals, universe, horizon, weights or decisions.
- **It does not change the primary analysis.** It is not in the primary hypothesis family, which stays the three pairwise net-CER contrasts with Holm correction, and it does not redefine the primary endpoint (net CER).
- **Comparisons with it are secondary and descriptive.**
- **It leaves every difference between approaches unchanged.** For any two approaches A and B, (A − common) − (B − common) = A − B. This is checked numerically for every computed primary contrast (§5, check 8).
- **It is a common passive reference, not a fully neutral portfolio and not a direct measure of model skill.** It holds no corporate credit, no long-duration Treasuries and no cash.

## 2. Exact rules

| Item | Rule |
|---|---|
| Instruments | SPY (SPDR S&P 500 ETF Trust: US large-cap equities); IEF (iShares 7–10 Year Treasury Bond ETF: intermediate-term US Treasuries) |
| Weights | 60% SPY, 40% IEF; long-only; fully invested; no cash |
| Evaluation dates | Identical to the approaches': decision at 20:00 ET on the last common trading day of each month (SPY, IEF, LQD and TLT calendars) |
| Rebalancing frequency | Monthly, back to 60/40 |
| Execution timing | At the close of the first common trading day after month-end; held to the next such close. Weights drift with realised returns in between |
| Transaction costs | 5 bp per dollar traded (the shared rate). Dollars traded = Σ\|target weight − drifted pre-trade weight\|. The first month starts from cash (1.0 traded). Under the shared convention (Stage 2 conventions 6–8), the cost is deducted from that month's return |
| Dividends | Distribution-adjusted closing prices from the pinned, hash-verified inputs (total return). No separate dividend cash flows |
| Return calculation | Monthly net total return = Σ wᵢ·(Pᵢ,exit / Pᵢ,entry − 1) − cost. Excess return = net total return − DTB4WK accrued over the same holding period |
| Metrics | The shared evaluator's: net CER (δ = 2.5), Sharpe, maximum drawdown, volatility and turnover, plus cumulative return |
| Relative statistics (descriptive) | Paired net-CER difference with the shared block bootstrap (6-month blocks, 5,000 replications, seed 20261027); differences in annualised excess return and Sharpe; cumulative-return difference; tracking error |
| Accounting decomposition (not a causal attribution) | CER(approach) − CER(common) = [CER(approach) − CER(own native benchmark)], labelled **decisions**, + [CER(own native benchmark) − CER(common)], labelled **benchmark mix**. An exact identity |

**Implementation:**
- `native_backtest/framework/benchmark.py`: specification check, simulation through the shared `accounting.simulate_records`, relative statistics, the accounting decomposition, the fingerprint and the freeze guard.
- `scripts/development_evaluation.py`: section `common_benchmark_matched_dev`.
- `scripts/common_benchmark_checks.py`: the accounting checks in §5.

## 3. Why this benchmark

**Selection.** On 2026-10-28 the project lead chose 60/40 SPY/IEF over the first proposal, 60/40 SPY/TLT, for two reasons:
- **Data validation.** SPY and IEF both passed Stage 2 gate 5 (distribution adjustment, criteria C1–C6). TLT's gate 5 result (FAIL on C2, preserved and diagnosed) is still awaiting team sign-off, so the main reference line does not depend on it.
- **Interest-rate sensitivity.** IEF's bonds are closer in duration to the bond sleeve of a conventional 60/40 than TLT's 20+ year Treasuries.

**What was seen before the choice.** Development-period figures (2019-03..2022-12) for three candidates: 60/40 SPY/TLT, 60/40 SPY/IEF and 45/35/20 SPY/IEF/LQD. No protected-window data. The SPY/TLT draft was committed earlier the same day (`08580a2`, marked proposed and not frozen) and was replaced before any result against it entered the evaluation report or the dashboard.

**Why no fixed mix can be neutral.** The approaches hold different assets:
- Deterministic and Causal RAG trade SPY/IEF/LQD.
- JEV and its Committee variant trade SPY/TLT.
- This benchmark overlaps the first universe. The decomposition shows the size of the resulting mix term rather than hiding it.

## 4. Development results (2019-03..2022-12, 46 months; diagnostics, not protected historical results)

**Common benchmark:** net CER 4.98%; Sharpe 0.55; maximum drawdown −18.8%; volatility 12.9%; cumulative return 32.0%; turnover 28% a year (monthly rebalancing of drift).

**Each approach against the benchmark** (CER values in percentage points per year):

| | Net CER | vs common: ΔCER (95% range; p) | Decisions (vs own benchmark) | Benchmark mix (own vs common) | Cumulative return vs common | Tracking error |
|---|---|---|---|---|---|---|
| Deterministic Quantitative Model | 3.67% | −1.31 (−3.12 to +0.37; 0.13) | −0.11 | −1.21 | −7.7 pts | 2.2% |
| Agentic Workflow (JEV) | 4.67% | −0.31 (−4.96 to +4.60; 0.89) | +0.31 | −0.61 | −0.8 pts | 4.1% |
| Agent Committee (within-approach variant) | 5.11% | +0.13 (−5.59 to +6.77; 1.00) | +0.75 | −0.61 | +0.7 pts | 6.3% |
| Agentic Causal RAG | — | pending: no genuine model decisions; nothing is simulated | | | | |

**Reading:**
- No approach differs from the common benchmark by a statistically clear margin.
- For the Deterministic model, the benchmark-mix term (45/35/20 SPY/IEF/LQD against 60/40 SPY/IEF) is −1.21 of the −1.31 pts gap; the decisions term is −0.11. This is an accounting split, not a statement of cause.
- For JEV, the benchmark-mix term is −0.61 pts: the difference between its own 60/40 SPY/TLT mix and 60/40 SPY/IEF over 2019–22.
- The primary contrast is unchanged: JEV − Deterministic = +1.01 pts (95% range −3.42 to +5.27; p 0.63), with the same value whichever benchmark is subtracted.

**Sensitivity to the cost rate** (information only): the benchmark's net CER is 5.01% at 0 bp, 4.98% at 5 bp and 4.95% at 10 bp.

## 5. Specification and accounting checks (`out/development/common_benchmark_checks.json`): all pass

| # | Check | Result |
|---|---|---|
| 1 | Specification is valid: long-only, sums to 1, assets on the evaluation calendar, monthly rebalancing at the shared entry close; after the freeze, its fingerprint matches the approval record | Pass (re-run after the freeze) |
| 2 | SPY and IEF passed Stage 2 gate 5, C1–C6 (price data to 2023-02-01) | Pass |
| 3 | Pinned SPY, IEF and DTB4WK inputs match their recorded SHA-256 | Pass |
| 4 | Decision months, entry dates and exit dates are identical to every approach's (first 2019-03: 2019-04-01 → 2019-05-01; last 2022-12: 2023-01-03 → 2023-02-01) | Pass |
| 5 | The path is the same whichever approach's records supply the dates | Pass (difference 0) |
| 6 | An independent re-implementation from raw prices (dollar holdings, not the shared simulator) reproduces every monthly return, cost and turnover | Pass (max difference 3.5e-18) |
| 7 | First month starts from cash: 1.0 traded; cost 5 bp | Pass |
| 8 | Subtracting the benchmark leaves every primary contrast unchanged | Pass (difference 0) |
| 9 | vs-common = decisions + benchmark mix, exactly, for every approach (accounting identity) | Pass |
| 10 | No month at or after the protected window is read; the evaluator lock is enforced | Pass |

**Tests:** spec validation, shared-accounting equivalence, independent re-implementation, exact decomposition, fingerprint and freeze-guard behaviour (`native_backtest/tests/test_framework.py`), plus the dashboard data contract (`mvp/tests/test_dashboard_data.py`).

## 6. Methodological implications

1. **Not a direct measure of model skill.** A gap to the common benchmark combines two accounting terms: the approach against its own native benchmark ("decisions") and its native benchmark against the common one ("benchmark mix"). The comparison with each approach's own native benchmark is kept in its details as a secondary diagnostic.
2. **Not neutral.**
   - Deterministic and Causal RAG can hold both benchmark assets.
   - JEV cannot hold IEF.
   - The mix term depends on the period: it reflects how intermediate Treasuries and corporate bonds performed against long Treasuries, so in the protected window it may have either sign.
3. **Universe and horizon differences remain.** One reference line does not remove differences in assets, horizons or information. The comparability statement in the development report still applies.
4. **No change to the primary analysis.**
   - The primary endpoint, the three pairwise contrasts, the Holm family, windows, costs and metrics are unchanged.
   - The development report's existing sections hold identical values; only the configuration-driven `research_design` changed while the decision was pending.
5. **Data validation for the test window.**
   - Gate 5 covered prices to 2023-02-01.
   - The pinned prices extend to 2026-10-21, but the distribution check has not been run on test-window prices for any asset. This applies to SPY, IEF, LQD and TLT alike, so to every approach, not only the benchmark.
   - The "Verified prices and cash rate" item in the validation status refers to the development period.
   - **Approved on 2026-10-28** as an isolated data-quality audit before opening: pre-registration `TEST_WINDOW_DISTRIBUTION_AUDIT_PREREGISTRATION_2026-10-28.md`; results in `TEST_WINDOW_DISTRIBUTION_AUDIT_2026-10-28.md`.

## 7. Approval (2026-10-28, 21:01 ET)

The project lead approved:

1. **The frozen specification** in §2 as the single common benchmark for the three primary approaches: a common passive reference, not a fully neutral portfolio or a direct measure of model skill. All original strategies, native benchmarks and pre-registered primary pairwise comparisons are preserved.
2. **The reporting rules:**
   - one common-benchmark line on the main dashboard;
   - native-benchmark comparisons in the detailed views;
   - the decisions / benchmark-mix split shown and described as an accounting decomposition, not a causal attribution;
   - results against the benchmark reported whatever they show;
   - the clean, visual-first design kept.
3. **The test-window distribution audit** (§6.5), as a strictly isolated data-quality check.

**Recorded:**
- Approver, time, conditions, rationale, full specification, inherited settings and both hashes are in `native_backtest/config/approvals/common_benchmark_freeze_2026-10-28.json`.
- The accounting checks were re-run under the frozen specification; all pass.
- Any change now needs a new configuration version, a documented reason and a new approval. None is allowed once the protected window has been opened.

## 8. Reporting amendment (2026-10-28, 21:36 ET)

**Requested by the project lead.** The Deterministic Quantitative Model is the primary research baseline. The research question is whether the AI-based approaches improve on it. The primary comparisons are unchanged:
- JEV − Deterministic;
- Causal RAG − Deterministic;
- Causal RAG − JEV.

They form one Holm family of three.

**What changed: labels and display only.**
- This portfolio is shown as **Passive Portfolio Reference — 60% SPY / 40% IEF**. It is a secondary investment reference, not the research baseline and not a fourth approach.
- On the main chart it is an optional dashed line, off by default.
- Its comparison ("does a strategy beat a simple 60/40 portfolio?") is shown separately from the research comparison ("does an AI approach improve on the Deterministic baseline?").

**What did not change:**
- weights, rules, accounting and historical calculations;
- the fingerprint, still `fffd92b9…1aed`;
- the native-benchmark comparisons;
- the sealed window.

**Records:**
- `native_backtest/config/approvals/common_benchmark_reporting_amendment_2026-10-28.json`;
- `framework_config_v1.json` v1.6: `common_benchmark.display_label`, `reporting`, `reporting_amendments`, and `research_design.research_baseline`.

