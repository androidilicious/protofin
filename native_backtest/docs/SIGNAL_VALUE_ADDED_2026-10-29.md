# Signal value-added and portfolio attribution: Deterministic and JEV — 2026-10-29

**Research question.** Do the forecasting signals improve investment outcomes beyond what each system's own underlying portfolio would achieve without them?

**Scope.** Development months only, March 2019 – December 2022 (46 decision months). These are development diagnostics, not protected historical results; the historical test window stays sealed. The three primary approaches are unchanged: the Deterministic Quantitative Model (research baseline), the Agentic Workflow (JEV) and Agentic Causal RAG. The no-signal portfolios below are within-approach counterfactuals, not new approaches, and the frozen passive 60% SPY / 40% IEF portfolio remains a separate investment reference.

**Units.** Levels such as net CER, returns and volatility are percentages (%). Differences between two portfolios are **percentage points (pts)**.

## Answers

| Question | Observed | 95% range | p | Statistically clear? |
|---|---|---|---|---|
| 1. Do the Deterministic model's signals beat its own no-signal portfolio (45/35/20 SPY/IEF/LQD)? | −0.11 pts net CER | −0.31 pts to +0.03 pts | 0.17 | no |
| 2. Do JEV's signals beat its own no-signal portfolio (60/40 SPY/TLT)? | +0.31 pts net CER | −0.48 pts to +1.38 pts | 0.59 | no |
| 3. Does JEV beat the Deterministic model once their different portfolios are accounted for? (JEV's signal value minus the Deterministic model's) | +0.42 pts net CER | −0.43 pts to +1.63 pts | 0.51 | no |
| *For reference:* JEV − Deterministic as reported (primary contrast, unchanged) | +1.01 pts | −3.42 pts to +5.27 pts | 0.63 | no |

**Question 1: the Deterministic signals.** They lowered net CER slightly, by 0.11 pts. They lose money even before trading costs (−0.09 pts net CER), and the extra trading they cause costs a further 0.02 pts. The loss is not statistically clear.

**Question 2: the JEV signals.** They raised net CER by 0.31 pts, which is well within chance (p = 0.59).
- The gain rests on one month. The February 2020 decision was held through the March 2020 crash, with JEV 5.3 pts under its 60% stock weight.
- Without that month, JEV's signal value is −0.18 pts.
- JEV's answers were recorded after the fact by a model of unknown training cutoff (contamination register C3, C4), so this month cannot be assumed free of hindsight.

**Question 3: JEV against the Deterministic model.** The observed JEV − Deterministic gap is +1.01 pts net CER. It splits exactly into two parts:
- **The two no-signal portfolios:** +0.59 pts, about 59% of the gap.
  - JEV's higher stock weight (60% vs 45%) adds +1.39 pts.
  - JEV's long-term Treasuries (TLT) in place of the Deterministic IEF + LQD bond sleeve subtract 0.79 pts.
- **The signals:** +0.42 pts, about 41% of the gap. This is JEV's +0.31 pts plus +0.11 pts from not having the Deterministic model's negative signal value.

Neither part is statistically clear. Without the February 2020 decision (held through the March 2020 crash), the signal part becomes −0.09 pts.

**Conclusion.** On the development months, neither system's signals add measurable investment value over its own no-signal portfolio.
- **Most of the gap is allocation.** JEV's higher net CER comes mostly from its allocation, chiefly the larger stock weight, partly offset by its longer-duration bonds.
- **The rest is mostly one month.** The remainder comes from a small signal effect concentrated in one crash month.
- **No evidence of AI alpha.** These results give no evidence that the Agentic Workflow adds alpha. They also cannot rule out a modest effect: with 46 months, only large differences could be told apart from chance.

## 1. The signal-disabled portfolios

| | Deterministic — no signal | JEV — no signal |
|---|---|---|
| Assets | SPY, IEF, LQD (unchanged) | SPY, TLT (unchanged) |
| Weights | 45% / 35% / 20%: the frozen native neutral weights; Stage 2's Black–Litterman prior | 60% / 40%: the frozen native neutral weights; JEV's equilibrium weight |
| What is switched off | The model's forecasts and the tilts they produce | JEV's tilt (its answer's offset) |
| Rebalancing | **Monthly, back to the fixed weights**, at each entry close, like the strategy | **Monthly, back to the fixed weights**, like the strategy |
| Same as the strategy | Decision dates, entry and exit closes, adjusted prices with distributions, DTB4WK cash, start from cash, 5 bp per dollar traded against the drifted weights | Same |

**Why monthly rebalancing.** It is the frozen convention in three places, so no new rule is introduced:
- the shared evaluator's own-benchmark contrast (`framework_config` → `native_neutral_weights`);
- Stage 2's `BENCH_STATIC_45_35_20`;
- the native JEV engine's own `fixed` and `prior` benchmarks.

Buy-and-hold drift is reported only as a labelled sensitivity (section 8).

**Checked in the systems' own code:**
- **Deterministic.** Stage 2's saved `BENCH_STATIC_45_35_20` run equals the no-signal portfolio month by month (largest difference 1e-16), and its saved System A run equals the strategy. A Black–Litterman allocation with the views simply removed would not hold exactly 45/35/20, because the posterior uncertainty term moves it toward minimum variance. The frozen Stage 2 reference is therefore the static prior, and that is what is used.
- **JEV.** The unchanged native JEV engine was run with JEV's tilt switched off (offset 0).
  - It holds 60% SPY in every month, to within 2e-16.
  - Its value path equals the engine's own fixed 60/40 benchmark to within 2e-15.
  - With the tilt switched on, it reproduces the decision records exactly.

The engine was stepped only up to 2022-12-30.

## 2. With and without signals

| | Deterministic, with signals | Deterministic, without | Difference | JEV, with signals | JEV, without | Difference |
|---|---|---|---|---|---|---|
| Net CER (primary metric) | 3.67% | 3.77% | −0.11 pts | 4.67% | 4.37% | +0.31 pts |
| Average return above cash, per year | 5.32% | 5.43% | −0.11 pts | 7.01% | 6.80% | +0.20 pts |
| Cumulative return, 46 months | 24.27% | 24.78% | −0.51 pts | 31.18% | 29.96% | +1.23 pts |
| Sharpe ratio | 0.462 | 0.472 | −0.010 | 0.513 | 0.487 | +0.026 |
| Worst fall (maximum drawdown) | −18.60% | −18.53% | −0.08 pts | −23.82% | −23.96% | +0.14 pts |
| Volatility, per year | 11.52% | 11.51% | +0.01 pts | 13.66% | 13.97% | −0.31 pts |
| Turnover, per year (one-way) | 45.6% | 26.9% | +18.7 pts | 33.3% | 30.2% | +3.1 pts |
| Trading costs, total over 46 months | 0.175% | 0.103% | +0.072 pts | 0.128% | 0.116% | +0.012 pts |

## 3. Incremental value and its uncertainty

Each system is compared with its own no-signal portfolio using the frozen paired circular block bootstrap (6-month blocks, 5,000 draws, seed 20261027).

| | Deterministic | JEV |
|---|---|---|
| Incremental net CER (signals − no signals) | −0.11 pts | +0.31 pts |
| 95% range | −0.31 pts to +0.03 pts | −0.48 pts to +1.38 pts |
| 90% range | −0.27 pts to +0.02 pts | −0.38 pts to +1.22 pts |
| Two-sided p | 0.17 | 0.59 |
| Observed direction | lower with signals | higher with signals |
| Statistically supported at 5% | no | no |
| Average active return, per year | −0.11 pts | +0.20 pts |
| Tracking error vs own no-signal portfolio, per year | 0.35% | 1.02% |
| Information ratio | −0.30 | +0.20 |
| Months the signals did better | 18 of 46 | 17 of 46 |

**Observed vs supported.**
- An *observed* improvement is the point estimate.
- A *statistically supported* improvement needs a 95% range that excludes zero, which equals p < 0.05 here.

Neither system meets that.

These within-approach contrasts are diagnostics outside the pre-registered primary family, and the p-values are unadjusted. None is significant even before adjustment. The incremental CERs and their ranges are exactly the "vs own benchmark" results already in the development report: they are reproduced, not replaced.

## 4. JEV vs Deterministic: what explains the gap

All splits below are exact accounting identities on the same 46 months. They describe where the numbers come from; they are not causal attributions.

**Two-by-two view (net of costs).** The four portfolios are each system with and without its signals. The gap splits into the two no-signal portfolios plus the two systems' signal values:

| Part | Net CER | Share of the gap | 95% range | p |
|---|---|---|---|---|
| More stocks (60% vs 45% SPY) | +1.39 pts | 137% | −1.60 pts to +4.20 pts | 0.34 |
| Different bonds (TLT vs IEF + LQD) | −0.79 pts | −79% | −5.96 pts to +4.71 pts | 0.76 |
| *Subtotal: the no-signal portfolios* | *+0.59 pts* | *59%* | *−3.58 pts to +4.27 pts* | *0.74* |
| JEV's signal value | +0.31 pts | 31% | −0.48 pts to +1.38 pts | 0.59 |
| Minus the Deterministic signal value | +0.11 pts | 11% | | |
| *Subtotal: the signals (question 3)* | *+0.42 pts* | *41%* | *−0.43 pts to +1.63 pts* | *0.51* |
| **Total: JEV − Deterministic** | **+1.01 pts** | 100% | −3.42 pts to +5.27 pts | 0.63 |

The parts add up to the total exactly (residual 0e+00). Ranges come from one joint bootstrap, with every part computed on the same resampled months.

**Splitting stocks from bonds.** The stock and bond parts are a Shapley average over two hybrid mixes:
- JEV's 60% stocks with the Deterministic bonds;
- the Deterministic 45% stocks with TLT.

The order matters:

| Order | Stock weight | Bond sleeve |
|---|---|---|
| Stocks first | +1.12 pts | −0.53 pts |
| Bonds first | +1.65 pts | −1.06 pts |

In either order, the stock weight is the larger and positive part.

**Four-part view.** This splits out the four sources requested: baseline mix, model tilts, trading costs and interactions.

| Part | Net CER |
|---|---|
| 1a. Baseline mix: stock weight, before costs | +1.38 pts |
| 1b. Baseline mix: bond sleeve, before costs | −0.79 pts |
| 2a. JEV's tilts, before costs (on their own) | +0.19 pts |
| 2b. Minus the Deterministic tilts, before costs (on their own) | +0.09 pts |
| 3. Trading costs, all: rebalancing the mixes −0.003 pts, extra trading caused by tilts +0.015 pts | +0.012 pts |
| 4. Interaction: how the tilts' returns move with the system's own mix (risk effect) | +0.12 pts |
| **Total** | **+1.01 pts** (residual 1e-17) |

How the tilt terms are defined: for each system, CER(mix + tilts) − CER(mix) = 12·mean(tilt return) − 6δ·var(tilt return) − 12δ·cov(mix, tilt return), with δ = 2.5. The first two terms are the tilts on their own (rows 2a and 2b); the last is the interaction (row 4).

JEV's interaction is positive (+0.12 pts): its tilts tended to move against its mix, which lowered volatility. The trading-cost row slightly favours JEV, because the Deterministic model trades more.

**Average return above cash.** On average return the split is linear: exact month by month, with no risk term and no interaction. Per year:

| Part | Average return above cash |
|---|---|
| Stock weight | +1.88 pts |
| Bond sleeve | −0.51 pts |
| JEV's tilts | +0.21 pts |
| Minus the Deterministic tilts | +0.09 pts |
| Trading costs | +0.012 pts |
| **Total** | **+1.68 pts** (largest monthly residual 9e-18) |

**Why JEV's CER lead is smaller than its return lead.** JEV earns +1.68 pts a year more on average, but leads by only +1.01 pts in net CER. The difference is the CER risk penalty on JEV's higher volatility, almost all of it from the extra stocks and the long-duration bonds.

**Is JEV's higher CER mainly its greater stock exposure and different bond duration, rather than its forecasts?** Mostly, yes.
- The two no-signal portfolios account for +0.59 pts of the +1.01 pts gap.
- The stock weight alone is worth +1.39 pts, more than the whole gap, while the long-duration bonds take away 0.79 pts.
- The forecasts account for +0.42 pts. That part is not statistically clear and depends on one month (section 6).

## 5. Do the signals change the decisions?

| | Deterministic | JEV |
|---|---|---|
| Average size of the tilt (half the sum of absolute weight differences) | 2.1 pts | 1.6 pts |
| Largest tilt | 20.0 pts (2020-05: IEF at its 15% floor) | 8.7 pts (2019-05) |
| Stock tilt: standard deviation; range | 1.4 pts; −3.5 pts to +5.8 pts | 2.4 pts; −8.7 pts to +2.6 pts |
| Months over / under the no-signal stock weight | 26 / 20 | 26 / 20 |
| Changes of direction (of 45 possible) | 7 | 7 (answer side: 7) |
| Months with a stock tilt of 2 pts or more / 5 pts or more | 4 / 1 | 12 / 3 |
| Months at a weight limit | 1 | 0 |
| How much forecast variation reaches the weights | Black–Litterman keeps only 3–5% of each forecast's departure from equilibrium (SPY 3.1%, IEF 4.2%, LQD 4.7%), because the frozen forecast-error variance is large | Confidence (average 0.32) keeps 38% of the answer's offset; offsets used −2.0 to +0.9 of a possible ±3 points; each applied point moves SPY by about 6.6 pts |
| Do different forecasts give different portfolios? | Average stock weight by forecast third: 43.8% / 45.4% / 46.2%, a 2.4 pts range | Average stock weight by answer: lean equities 61.0%, lean bonds 57.7%, strong bonds 56.9%, a 4.1 pts range |
| Extra turnover from the signals, per year | +18.7 pts | +3.1 pts |
| Months the tilt made money, before costs | 39% | 35% |
| Correlation of the stock tilt with stocks' next-month return over the bonds | −0.15 | +0.12 |
| Tilt return per year: from the average tilt / from month-to-month timing (ex post) | +0.03 pts / −0.12 pts | −0.06 pts / +0.26 pts |

**What the table shows.**
- **Both systems' signals move the portfolio, but only a little.** Different forecasts lead to stock weights only 2–4 points apart.
- **The Deterministic model.** It changes the portfolio mostly within its bonds (IEF ↔ LQD), and its stock tilts were wrongly timed.
- **JEV.** Its small gain comes from timing, not from a steady underweight in stocks: its average underweight of 0.4 pts cost a little. It made money before costs in only 35% of months, so a few large months carry the result.

## 6. When did the signals add value?

Below: the sum of monthly active returns, signals minus no signals. In brackets: the months the signals did better, out of all months in the group. All splits are descriptive and the groups are small.

| | 2019 (Mar–Dec) | 2020 | 2021 | 2022 |
|---|---|---|---|---|
| Deterministic | −0.07 pts (3/10) | −0.41 pts (3/12) | +0.11 pts (7/12) | −0.03 pts (5/12) |
| JEV | −0.77 pts (2/10) | +1.35 pts (3/12) | −0.17 pts (6/12) | +0.37 pts (6/12) |

| | Volatile at decision (SPY 63-day volatility ≥ 20%) | Calm at decision | SPY fell that month (known only afterwards) | SPY rose that month |
|---|---|---|---|---|
| Deterministic | −0.31 pts (5/16) | −0.09 pts (13/30) | −0.50 pts (5/18) | +0.09 pts (13/28) |
| JEV | −0.36 pts (6/16) | +1.13 pts (11/30) | +2.04 pts (6/18) | −1.26 pts (11/28) |

**Dependence on single months.** This is a leave-one-month-out test: each month is dropped in turn and the result recomputed.

| | Full result | Most influential month | Without it | Range when dropping each month in turn |
|---|---|---|---|---|
| Deterministic signal value | −0.11 pts | 2020-05 | −0.24 pts | −0.24 pts to −0.04 pts |
| JEV signal value | +0.31 pts | 2020-02 | −0.18 pts | −0.18 pts to +0.49 pts |
| JEV − Deterministic signal value | +0.42 pts | 2020-02 | −0.09 pts | −0.09 pts to +0.62 pts |

**JEV's gain comes from one month.**
- **The month.** JEV's February 2020 decision was 5.3 pts under its 60% stock weight. That portfolio was held from 2 March to 1 April 2020, while SPY fell 19.9% and TLT rose 8.7%.
- **Its weight in the result.** That month gave JEV +1.52% over its no-signal portfolio. That is more than its total over all 46 months (+0.78% summed), and it is the only month whose removal reverses the sign of JEV's signal value.
- **Hindsight risk.** JEV's answers were recorded after the fact by a model whose training cutoff is unknown, and the masked inputs contain era cues (contamination register `CONTAMINATION_REGISTER_AND_HINDSIGHT_AUDIT_v1.md`, items C3 and C4). The best-known market event in the sample is exactly where hindsight would help. This does not show contamination, but the month cannot be treated as clean evidence of forecasting skill.

The Deterministic model's single best month was May 2020, its largest tilt (IEF to 15%, LQD to 34%). Even with that month, its signal value stays negative.

## 7. Do the signals cover their costs?

| | Deterministic | JEV |
|---|---|---|
| Tilt return before costs, per year | −0.087 pts | +0.206 pts |
| Extra trading cost from the tilts, per year | −0.019 pts | −0.003 pts |
| After costs | −0.106 pts | +0.203 pts |
| Break-even cost per dollar traded (Stage 2 convention 14) | not defined: no CER gain at zero cost | 545 bp (actual cost: 5 bp) |

- **The Deterministic tilts** lose before costs, so no cost level would make them worthwhile. The frozen Stage 2 result says the same: "not defined: no CER gain at zero cost".
- **JEV's tilts** trade little, so on these months their small gain is far above their cost. But that gain is not statistically clear, and it depends on one month.

## 8. Sensitivities

| | Deterministic | JEV |
|---|---|---|
| Main result (monthly-rebalanced no-signal portfolio, shared accounting) | −0.11 pts (p 0.17) | +0.31 pts (p 0.59) |
| Native JEV engine: trade at the decision close, 5 bp per unit of SPY turnover, native returns and cash; tilt switched off in the engine | — | +0.22 pts, 95% range −0.40 pts to +1.01 pts (p 0.59); net CER 4.14% with vs 3.92% without |
| Buy-and-hold no-signal portfolio, never rebalanced (not the frozen convention) | −0.05 pts, 95% range −0.76 pts to +0.74 pts (p 0.90); stocks drift to 54% | +0.40 pts, 95% range −0.75 pts to +2.09 pts (p 0.61); stocks drift to 71% |
| Same allocator fed naive historical-mean forecasts (Stage 2's frozen `BENCH_HISTMEAN_ALLOCATOR`) | Deterministic minus naive: +0.06 pts, 95% range −0.07 pts to +0.27 pts (p 0.70) | — |

The conclusions hold under every convention: no signal effect is statistically clear, and JEV's sign stays positive while the Deterministic model's stays near zero or negative.

## 9. Validation

- **Previously reported results reproduced exactly (difference 0.0):**
  - both incremental CERs, with their ranges and p-values (the development report's "vs own benchmark");
  - both no-signal net CERs;
  - the JEV − Deterministic primary contrast.

  No earlier result was found to be wrong, so nothing is corrected or replaced.
- **Independent rebuild.** `audit_signal_value.py` rebuilds everything from the raw prices, the cash file and the decision records, without the project's accounting, metrics or Stage 2 code, and with its own bootstrap. That covers all portfolios, metrics, bootstrap ranges and p-values, both attributions, the decision diagnostics, the regimes, the leave-one-out test and the sensitivities. 212 checks pass; the largest difference is 4.8e-13, within the 1e-12 tolerance.
- **Point in time.** 92 decision records were checked, with 0 problems:
  - decisions are dated on the last trading day of the month;
  - information cutoffs are at or before the decision time;
  - JEV's answers are dated on or before the decision date.

  The volatility regime uses only prices up to the decision close. The no-signal portfolios use no information.
- **Tests.** `native_backtest/tests/test_signal_value.py` covers:
  - signals switched off and nothing else changed;
  - the native engines' switch-off;
  - unchanged universes;
  - shared dates and cash;
  - costs, turnover and rebalancing from drift;
  - the buy-and-hold sensitivity;
  - distinct return series;
  - exact reconciliation of every attribution;
  - exact reproduction of earlier results;
  - the joint bootstrap equalling the frozen paired bootstrap;
  - the CER identity on a hand-checked example;
  - byte-identical reruns;
  - the independence of the rebuild.
- **Safeguards.** No frozen configuration, decision record or earlier output was changed. The protected window was not scored, no model was called, and the tilts, parameters and rules were not tuned on these results.

## 10. What this does not show

- **Development months only.** These 46 months are where the approaches were built and checked. The confirmatory test, January 2024 – August 2026, is still sealed.
- **Low power.**
  - Against its own no-signal portfolio, JEV's tracking error is 1.02% a year, and the Deterministic model's is 0.35%.
  - Over 46 months, only very large signal effects could be distinguished from chance.
  - A null result is not proof that a signal is worthless.
- **Not causal.** The attribution is arithmetic. A different but equally valid split, such as the other order of the stock and bond steps, gives different shares; both orders are shown.
- **Different forecast horizons.** JEV forecasts 12 months ahead but is scored month by month, like every approach.
- **Causal RAG** has no results yet and is not part of this analysis.

## Reproduce

```bash
python -m native_backtest.scripts.signal_value_added   # writes native_backtest/out/signal_value/ (byte-identical on rerun)
python -m native_backtest.scripts.audit_signal_value   # independent rebuild; non-zero exit on any mismatch
python -m pytest native_backtest/tests/test_signal_value.py
```

`python mvp/run.py build` runs both scripts and stops on any mismatch.
