# Portfolio return and backtest integrity audit: Deterministic vs JEV — 2026-10-29

**Question.** On the dashboard, the Deterministic model and the Agentic Workflow (JEV) have very similar growth curves, with the same peaks, drawdowns and turning points. Is that economically justified, or is it a calculation, data or display error?

**Answer.** They are independent implementations that produce similar returns, and no calculation or display error was found. An independent reconstruction from the raw files matches the backtest to about 1e-16, and the dashboard matches it to within its 6-decimal rounding.

The similarity is structural. Both systems hold near-static balanced portfolios dominated by the same stock fund (SPY), with bond sleeves that move together. Their decisions are almost uncorrelated:
- monthly net-return correlation: **0.9712**;
- correlation of their two fixed starting mixes alone, with no forecasting at all: **0.9826**;
- correlation of their decisions (each system's return minus its own fixed mix): **-0.0165**.

No result was changed.

Reproduce: `python -m native_backtest.scripts.audit_portfolio_integrity`. The outputs are `native_backtest/out/audit/portfolio_integrity_v1.json` (all numbers below at full precision) and `reconstruction_v1.csv` (month by month); the regression tests are in `native_backtest/tests/test_portfolio_integrity.py`.

## 1. Independent reconstruction

**Independence.** The audit script imports none of the project's market, accounting, adapter or Stage 2 code; a test checks this.

**Inputs and rules:**
- **Prices:** it parses the raw pinned price files (`stage2/data/_pinned/market_price_{SPY,IEF,LQD,TLT}_2018plus.tsv`, adjusted `Close`, SHA-256 checked).
- **Cash rate:** the 4-week Treasury bill file (`DTB4WK`, SHA-256 checked).
- **Calendar:** the common trading days of all four funds.
- **Decision date:** the last common trading day of the month, at 20:00 ET.
- **Entry:** the close of the first common trading day after month-end.
- **Exit:** the close of the first common trading day after the next month-end.
- **Weights:** read directly from each system's decision-record file (`out/decisions/AP1.jsonl`, `AP2B.jsonl`).

**Formulas** (month *t*, target weights *w*, drifted pre-trade weights *p*, asset total returns *r*):
- r(a,t) = AdjClose(a, exit) / AdjClose(a, entry) − 1
- cost(t) = 0.0005 × Σ|w − p|; the first month starts from cash
- net(t) = Σ w·r − cost(t); excess(t) = net(t) − rf(t)
- p(t+1) = w(1+r) / Σ w(1+r)
- rf = (1 + r28)^(days/28) − 1, with r28 = (d·28/360)/(1 − d·28/360), using the DTB4WK quote at entry
- wealth = Π(1 + net)
- net CER = 12·(mean(excess) − 1.25·var(excess))

**Reconciliation:**

| Compared with | Deterministic | JEV | Passive 60/40 |
|---|---|---|---|
| Shared evaluator, max \|Δ net return\| | 9.9e-17 | 9.5e-17 | 9.9e-17 |
| Shared evaluator, max \|Δ weight\| / \|Δ cash return\| | 0.0e+00 / 1.0e-16 | 5.6e-17 / 1.0e-16 | 0.0e+00 / 1.0e-16 |
| Shared evaluator, identical months and entry/exit dates | True | True | True |
| Stage 2 saved System A, max \|Δ net return\| | 9.9e-17 | — | — |
| Dashboard growth-of-$1 curve, max \|Δ\| | 5.0e-07 | 4.8e-07 | 5.0e-07 |
| Dashboard curve equals the other system's? | False | False | — |

The dashboard stores values rounded to 6 decimals, so differences up to 5e-7 are rounding. Turnover and Sharpe are stored to 4 decimals, giving differences up to 4.0e-05. The Deterministic curve is System A of the unchanged Stage 2 scorer, matching its canonical saved run.

## 2. How similar, and in what sense

| Measure (46 development months, 2019-03..2022-12) | Value |
|---|---|
| Correlation of monthly net returns | 0.9712 |
| Correlation of monthly returns above cash | 0.9711 |
| Correlation of returns above the passive 60/40 reference | 0.4584 |
| Correlation of active returns vs each system's own fixed mix (Det 45/35/20 SPY/IEF/LQD; JEV 60/40 SPY/TLT) | -0.0165 |
| Correlation of the two fixed mixes themselves | 0.9826 |
| JEV − Deterministic monthly spread: mean / standard deviation | +0.140 pts / 1.066 pts |
| Tracking error between them (annualised) | 3.69% |
| Largest monthly spread (JEV behind / ahead) | -2.75 pts / +2.47 pts |
| Months with \|spread\| > 0.5 / 1 / 2 points | 30 / 15 / 3 |
| Months with the same return direction | 89.1% |
| Correlation of growth-curve *levels* (not evidence of dependence) | 0.9935 |

## 3. The decisions

| | Deterministic | JEV |
|---|---|---|
| Stock (SPY) weight: mean (min–max), standard deviation | 45.1% (41.5%–50.8%), 1.40% | 59.6% (51.3%–62.6%), 2.44% |
| Bond weights: mean | IEF 34.0%, LQD 20.9% | TLT 40.4% |
| Own fixed starting mix | 45% SPY / 35% IEF / 20% LQD | 60% SPY / 40% TLT |
| Average distance from that mix (half the sum of absolute weight differences) | 2.07% | 1.59% |
| Distinct monthly weight vectors | 46 of 46 | 46 of 46 |
| Forecasts | 46 distinct 1-month forecasts | JEV's 12-month calls |

- **JEV's choices.** Its weights follow its answers in the right direction:
  - "lean equities", 27 months, average SPY 61.0%;
  - "lean bonds", 17 months, 57.7%;
  - "strong bonds", 2 months, 56.9%.
- **Size of tilts.** Both systems tilt little.
  - JEV adds confidence × offset to a stock-minus-bond edge before solving for the SPY weight (vendored engine `livebacktest.js`; bounds 40–80% SPY in `allocation.js`). Its reported confidence averages 0.32 (range 0.18–0.61) and its offsets lie between −2.0 and +0.9 points, so its SPY weight stays within 51.3%–62.6%.
  - The Deterministic model's monthly return forecasts vary little (standard deviation 0.17% for SPY, 0.26% for IEF, 0.13% for LQD), so its Black–Litterman weights stay near 45/35/20.
- **Independence of decisions.** The correlation of their month-to-month stock-weight changes is +0.0017.
- **Persistent difference.** JEV always holds more stocks: +14.5 pts on average (range +5.7 pts to +18.1 pts). It also holds longer-duration bonds (TLT, against IEF and LQD).

## 4. Exposures

| | Deterministic | JEV |
|---|---|---|
| Correlation with SPY / IEF / LQD / TLT | 0.94 / 0.29 / 0.87 / 0.29 | 0.87 / 0.41 / 0.87 / 0.45 |
| Share of monthly return variance explained by SPY alone (R²) | 87.4% | 75.3% |
| Share explained by the funds it holds (R²) | 99.91% | 99.62% |

**Asset volatilities and correlations:**
- Annualised volatility: SPY 21.1%, TLT 16.2%, LQD 10.3%, IEF 7.8%.
- Correlations: IEF and TLT 0.94; SPY and LQD 0.67; SPY and IEF -0.05; SPY and TLT -0.05.

After removing SPY from both return series, their residuals still correlate 0.91. The bond sleeves move together too: IEF and TLT are both Treasury duration, and LQD moves with both stocks and Treasuries.

## 5. Why the curves look alike: decomposition

Each system's return splits exactly into three parts: its average fixed weights times the asset returns, its month-to-month tilts, and costs. A part's share of variance is its covariance with the total divided by the total's variance, so the shares add up to 100% and a part that offsets the rest has a negative share.

| Share of each system's return variance | Deterministic | JEV |
|---|---|---|
| Average fixed weights | 100.6% | 101.7% |
| Month-to-month tilts (forecast or agent decisions) | -0.5% | -1.7% |
| Transaction costs | -0.03% | -0.01% |
| Of which the stock leg | 77.1% | 79.3% |
| Cumulative contribution of the tilts / of costs | -0.45 pts / -0.17 pts | +1.00 pts / -0.13 pts |

The monthly spread JEV − Deterministic splits the same way:

| Source of the spread | Share of its variance | Cumulative (sum of monthly) |
|---|---|---|
| Different stock weight (JEV ≈ 60% vs ≈ 45%) | 31.2% | +7.90 pts |
| Different bonds (TLT vs IEF + LQD) | 68.7% | -1.50 pts |
| Transaction costs | 0.07% | +0.05 pts |
| *Alternatively:* the two fixed starting mixes | 88.4% | +5.26 pts |
| *Alternatively:* the two systems' decisions | 11.6% | +1.18 pts |

**What this shows.** Both systems behave like balanced portfolios whose decisions move their weights only a few percentage points. In each, the average fixed weights account for essentially all of the month-to-month return variation, and the stock leg alone for about three quarters. They share the same stock fund and hold bonds that move together, so their months rise and fall together, which gives similar peaks, drawdowns and turning points.

**Where they differ.** The gap between them comes mostly from different fixed allocations (more stocks and longer bonds in JEV), and only about a tenth from their decisions. This is a decomposition of variance, not a causal attribution.

## 6. Error checks

| Check | Result |
|---|---|
| One strategy's weights or returns reused by another | No: distinct weight series; JEV and Committee weights differ; no month with identical returns (0) |
| Cached outputs or file mappings | Dashboard series *det* = AP1 decisions and *jev* = AP2B decisions, each matching its own reconstruction and not the other's |
| Benchmark assignments | Own mixes as configured: Deterministic 45/35/20 SPY/IEF/LQD, JEV 60/40 SPY/TLT; the passive reference is 60/40 SPY/IEF |
| Date alignment and look-ahead | 0 problems. Decisions are dated the last common trading day; information cutoffs are at or before the decision time; JEV's answers are dated on or before the decision date; entry is the next trading day |
| Adjusted prices and dividends | All four funds use the distribution-adjusted close from the same source; SPY 2019 total return from the files is 31.22% (S&P 500 price-only about 28.9%), so distributions are included. TLT: 14.1%, 18.1%, −4.6%, −31.2% in 2019–2022. TLT's documented gate 5 deviation (C2, a turn-of-month price–NAV premium effect, materiality −0.02 pts net CER) is still awaiting team sign-off; it is unrelated to the similarity. Calendar-year returns for all funds are in the JSON |
| Rebalancing and costs | Drift-aware: 0.05% of dollars traded against the drifted weights; the first month starts from cash. Reproduced exactly, including by a hand-checked test |
| Scaling, normalisation, compounding | Weights sum to 1 and are never negative; wealth is the product of (1 + net), the same in the evaluator, the dashboard and the reconstruction |
| Chart duplication or mislabelling | None: each line draws its own system's series; labels match keys |
| Dashboard values vs source | Within 6-decimal display rounding (table in section 1) |

**Observation, not an error.** The December 2022 development decision is held from 2023-01-03 to 2023-02-01, by the frozen timing rule. Protected decisions start with January 2023 and are held from February, so no month is scored twice.

## 7. Conclusion

The two backtests are separate implementations, with separate decision files, code paths and weights, that are both computed correctly. Their curves look alike because both are near-static balanced portfolios: about half (Deterministic) or 60% (JEV) in the same S&P 500 fund, the rest in bonds that move together. Their forecasting systems tilt those portfolios only slightly and in uncorrelated ways.

The similarity is a property of the designs, which use small, confidence-scaled tilts around a balanced starting mix. It is not a data or accounting artefact, so no result was changed. The research comparison remains the difference in net CER, which is unaffected by this similarity.
