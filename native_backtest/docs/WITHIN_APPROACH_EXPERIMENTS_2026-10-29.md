# Within-approach experiments completed — 2026-10-29

**What this is.** The within-approach experiments of the Deterministic Quantitative Model and the Agentic Workflow, run to completion. They were pre-registered in [`within_approach_preregistration_v1.json`](../config/within_approach_preregistration_v1.json) (SHA-256 `8b9a84b123fa4148…`), which was written and pushed **before** any of these results was computed.

**Scope.** Development months only, 2019-03 to 2022-12 (46 months). These are development diagnostics, not protected historical results; the protected window 2023-01..2026-08 was not scored. None of these experiments enters the primary Holm family of three. No frozen configuration, experiment definition or earlier result was changed, and nothing was tuned on these results. Cost: $0.

**Reproduce:** `python -m native_backtest.scripts.within_approach_experiments` → `native_backtest/out/within_approach/within_approach_v1.json`.

## Summary

| Experiment | Status before | Status now | Result |
|---|---|---|---|
| Deterministic: one financial signal at a time (B1..B5) | Paused | **Tested** | No component improves forecasts significantly; none is robust |
| Deterministic: all five financial signals (B-All) | Paused | **Tested** | The confirmatory contrast is negative: −0.0461, p 0.47 |
| Deterministic: market regimes | Planned | **Tested** | Diagnostic splits computed; one nominally significant 10-month cell, flagged |
| Agentic Workflow: Committee + JEV | Planned | **Tested** | Lies between its components; differs from neither significantly |
| Causal RAG (all seven) | Awaiting validation / blocked / planned | **Unchanged** | Genuine results need a passing real-model run; see section 5 |

## 1. Why each experiment was pending

| Experiment | Recorded reason | Resolved by |
|---|---|---|
| B1..B5, B-All | Paused on 2026-10-27 when the research design moved to comparing view-generation approaches. The pause record requires three things to resume: a written versioned decision, a separate pre-registration, and no exposure to historical-window results for these signals. | All three met: the project lead's written instruction of 2026-10-29, the pre-registration, and the B systems have never been scored in the protected window. The resumption is not based on anything seen in the v3 experiment. |
| Market regimes | Planned only: the frozen evaluation calls it a predeclared diagnostic, so the regime definitions had to be fixed **before** results were viewed. They had not been written down. | Both splits fixed in the pre-registration, each using only information available at the decision time. |
| Committee + JEV | Planned only: the combination rule had to be fixed before any test month was seen, and it had not been defined. | The rule was pre-registered: the equal-weight average of the two saved SPY target weights, with no parameters. |
| Causal RAG — Reduced Evidence | Awaiting validation: its first real-model run (qwen3:4b, 2026-10-29) failed both pre-registered reliability gates. | Not resolved. The pipeline defects are fixed; the run must be repeated on the free GPU. |
| Causal RAG — With Historical Documents | Blocked: BLS returns HTTP 403 to this environment, so about 435 of roughly 909 documents are missing. | Not resolved; re-verified today (section 5). |
| Policy-path proxy variant | Awaiting validation: it is a sensitivity variant of the above and needs the same real-model run. | Not resolved. |
| The four remaining Causal RAG experiments | Planned: each needs validated Causal RAG results first. | Not resolved. |

**Bloomberg inputs.** None of the experiments in this document needs one. The financial signals use only free public series already pinned in the Stage 2 snapshot manifest: FRED BAA10Y (credit spread), FRED T10Y3M (slope), CBOE VIX and SPY prices (VRP proxy), and the assets' own returns (momentum). The project's one Bloomberg dependency is fed funds futures for the Causal RAG mediator `FF_FUTURES_6M`, which is unrelated to these experiments and already has a separately labelled proxy variant (section 5).

## 2. Deterministic: do conventional financial signals improve the forecasts?

**Setup.** Each system is the frozen 8-surprise baseline A plus one financial signal, or all five. Definitions, code and inputs are unchanged (`stage2_frozen_config_v2.json`, `stage2_signal_manifest_v2.csv`, `stage2_backtest.py`). Walk-forward Ridge with purged expanding inner cross-validation, point-in-time features, the same decision and execution calendar and the same costs as the baseline.

**Reproduction gate.** The scorer was re-run from the canonical development spec into a new folder. Every shared output file is **byte-identical** to the archived 2026-10-27 run, and the scorer's own check against the saved summary is `MATCH` with 0 differences. The bootstrap used below was then recomputed independently and reproduces the scorer's published point estimates and intervals exactly (largest difference 0).

**Primary measure.** The frozen normalised pooled squared-error improvement against A: for each asset and month, the squared forecast error divided by the expanding realised-return variance known through t−2, averaged equally across SPY, IEF and LQD. **Positive means better than the baseline.** Uncertainty: the frozen paired circular block bootstrap (6-month blocks, 5,000 draws, seed 20261027); the p-value is two-sided.

| System | Improvement vs A | 95% interval | p | Holm p (component family) | Assets improved | Same sign in both halves | Robust? |
|---|---|---|---|---|---|---|---|
| B1 credit spread level | +0.0037 | −0.0010 to +0.0118 | 0.13 | 0.53 | 3/3 | no | no |
| B2 credit spread 3-month change | −0.0301 | −0.0953 to +0.0050 | 0.51 | 0.89 | 1/3 | yes | no |
| B3 10Y−3M Treasury slope | +0.0032 | −0.0013 to +0.0107 | 0.35 | 0.89 | 1/3 | no | no |
| B4 VRP proxy | −0.3844 | −1.1470 to +0.0003 | 0.10 | 0.49 | 1/3 | yes | no |
| B5 own-asset 12-month momentum | −0.0180 | −0.0582 to +0.0046 | 0.30 | 0.89 | 2/3 | yes | no |
| B-All all five together | −0.0461 | −0.1393 to +0.0010 | 0.47 | — | 1/3 | no | no |

- **The confirmatory contrast fails.** B-All, the predeclared conventional system, is **−0.0461**: worse than the baseline, not better, and not statistically distinguishable from it (p 0.47).
- **No component improves significantly.** The two positive components, B1 (+0.0037) and B3 (+0.0032), have raw p-values of 0.13 and 0.35, and 0.53 and 0.89 after Holm correction within the five-component family.
- **None is robust** under the pre-registered rule, which requires significance, the same sign in both halves and at least 2 of 3 assets improved. Every system fails at least the first condition.
- **The VRP proxy is the worst** at −0.3844, driven by the first half (see below).

**Stability across the two pre-registered halves** (improvement vs A):

| System | 2019-03..2020-12 | 2021-01..2022-12 |
|---|---|---|
| B1 credit spread level | +0.007879 | −0.000061 |
| B2 credit spread 3-month change | −0.062869 | −1.9e−05 |
| B3 10Y−3M Treasury slope | +0.006772 | −9.9e−06 |
| B4 VRP proxy | −0.800827 | −0.002748 |
| B5 own-asset 12-month momentum | −0.036872 | −0.000617 |
| B-All all five together | −0.096400 | +3.9e−05 |

Every system's effect is concentrated in the first half, which contains the 2020 market dislocation; in the second half all six are smaller by two to four orders of magnitude. B4's −0.8008 in the first half is a single-period effect, not a stable property.

**Portfolio level.** The same forecasts through the same frozen Black–Litterman allocator and the same costs. The baseline A's net CER is 3.67%.

| System | Net CER | vs A | 95% interval | p | Sharpe | Turnover | Break-even cost vs A |
|---|---|---|---|---|---|---|---|
| B1 credit spread level | 3.59% | −0.07 pts | −0.28 pts to +0.06 pts | 0.62 | 0.456 | 30.4% | not defined: no CER gain at zero cost |
| B2 credit spread 3-month change | 3.26% | −0.40 pts | −1.25 pts to +0.02 pts | 0.40 | 0.428 | 43.0% | not defined: no CER gain at zero cost |
| B3 10Y−3M Treasury slope | 3.60% | −0.07 pts | −0.28 pts to +0.06 pts | 0.56 | 0.456 | 29.4% | not defined: no CER gain at zero cost |
| B4 VRP proxy | 3.17% | −0.50 pts | −1.49 pts to −0.00 pts | 0.04 | 0.420 | 44.2% | not defined: no CER gain at zero cost |
| B5 own-asset 12-month momentum | 3.39% | −0.28 pts | −0.86 pts to +0.02 pts | 0.55 | 0.439 | 39.6% | not defined: no CER gain at zero cost |
| B-All all five together | 3.46% | −0.20 pts | −0.63 pts to +0.03 pts | 0.39 | 0.445 | 36.0% | not defined: no CER gain at zero cost |

Every financial signal **lowers** net CER relative to the baseline, and no break-even cost is defined for any of them, because none produces a CER gain even at zero trading cost. The one nominally significant cell is B4 at −0.50 pts (p 0.04); it is a harm, not a benefit, it is a secondary metric, and it is uncorrected for the six systems tested, so it should not be read as a precise effect size.

**Signal coverage.** All five signals are available for every scored asset-month, so no result is driven by missing data:

| Signal | Asset-months available | Coverage |
|---|---|---|
| credit_level | 138 of 138 | 100% |
| credit_change_3m | 138 of 138 | 100% |
| curve_10y_3m | 138 of 138 | 100% |
| vrp_proxy | 138 of 138 | 100% |
| own_asset_momentum_12m | 138 of 138 | 100% |

**Economic reading.** On these 46 months, conventional financial signals add nothing to the eight macro surprises. The baseline is already close to an intercept-only forecast, and the extra regressors mostly add estimation noise: they move the allocator's weights without improving the forecasts, so they cost turnover and return. This is a development-window result on a short sample; it does not prove these signals are uninformative in general.

## 3. Deterministic: market regimes

Both splits were fixed in advance and use only information available at the 20:00 ET decision. **Diagnostic only**: by the frozen evaluation rule, a regime result never selects or tunes anything.

**Net CER by regime (months in brackets).**

| | 2019-03..2019-12 | 2020-01..2022-12 |
|---|---|---|
| Deterministic | 12.38% (10) | 1.24% (36) |
| JEV | 16.06% (10) | 1.52% (36) |
| Agent Committee | 16.02% (10) | 2.09% (36) |
| Passive 60/40 reference | 12.37% (10) | 2.91% (36) |

| | Calm (VIX < 20) | Stressed (VIX ≥ 20) |
|---|---|---|
| Deterministic | 1.84% (20) | 5.02% (26) |
| JEV | 3.48% (20) | 5.51% (26) |
| Agent Committee | 3.20% (20) | 6.51% (26) |
| Passive 60/40 reference | 1.44% (20) | 7.66% (26) |

**Within-regime contrasts.**

| Contrast | Regime | Difference | p |
|---|---|---|---|
| JEV - Deterministic | 2019-03..2019-12 | +3.67 pts | 0.01 |
| JEV - Deterministic | 2020-01..2022-12 | +0.28 pts | 0.91 |
| JEV - Deterministic | calm (VIX < 20) | +1.65 pts | 0.52 |
| JEV - Deterministic | stressed (VIX >= 20) | +0.49 pts | 0.90 |
| Committee - JEV | 2019-03..2019-12 | −0.04 pts | 0.91 |
| Committee - JEV | 2020-01..2022-12 | +0.57 pts | 0.78 |
| Committee - JEV | calm (VIX < 20) | −0.28 pts | 0.87 |
| Committee - JEV | stressed (VIX >= 20) | +1.00 pts | 0.66 |

- **Everything is weaker after 2019.** All four strategies earn far less per year from 2020 onward, at two to three times the volatility.
- **One cell is nominally significant and should not be over-read.** JEV − Deterministic in 2019-03..2019-12 is +3.67 pts with p 0.01, on **10 months**. It is one of eight regime cells, with no multiplicity correction, in a diagnostic that is pre-registered as never being used to select anything. The same contrast over the full development window is +1.01 pts with p 0.63.
- **The passive reference does best in stressed months** (7.66%), so none of the strategies shows a defensive advantage when volatility is already high at the decision date.

## 4. Agentic Workflow: Committee + JEV

**Can they be combined at all?** Checked month by month, and all 46 months pass every check:

| Check | Result |
|---|---|
| Same universe (SPY/TLT) | 46/46 |
| Same decision dates, matching the shared calendar | 46/46 |
| Information cutoff at or before the decision time (no look-ahead) | 46/46 |
| Combined weight inside the native 40–80% SPY band | 46/46 |

Both systems decide on the same month-end dates, for the same two assets, on the same 12-month horizon, with 16:00 ET information cutoffs before the 20:00 ET decision. Their **forecasts** are in different units (the Committee's expected returns versus JEV's probability and tilt), so combining the forecasts would require inventing a conversion. The pre-registered rule therefore combines the **portfolios**: the equal-weight average of the two SPY target weights, with no parameters to fit.

The two components' stock weights differ by 10.1% on average and correlate 0.62; the combination holds 59.2% stocks on average, between 45.6% and 70.7%.

| | Net CER | Sharpe | Volatility | Worst fall | Turnover | Cumulative |
|---|---|---|---|---|---|---|
| **Committee + JEV** | 4.93% | 0.539 | 13.21% | −23.57% | 68.4% | 32.02% |
| JEV only | 4.67% | 0.513 | 13.66% | −23.82% | 33.3% | 31.18% |
| Agent Committee only | 5.11% | 0.557 | 12.96% | −23.63% | 113.0% | 32.68% |
| Its own 60/40 SPY/TLT benchmark | 4.37% | 0.487 | 13.97% | −23.96% | 30.2% | 29.96% |

| Comparison | Net CER difference | 95% interval | p | Statistically clear? |
|---|---|---|---|---|
| Committee + JEV vs JEV | +0.26 pts | −0.90 pts to +1.51 pts | 0.68 | no |
| Committee + JEV vs Committee | −0.18 pts | −1.39 pts to +0.94 pts | 0.77 | no |
| Committee + JEV vs its own 60/40 SPY/TLT benchmark | +0.57 pts | −1.17 pts to +2.72 pts | 0.61 | no |

**Reading.** The combination sits between its two components, as averaging two weight series must. It beats JEV by +0.26 pts and trails the Committee by +0.18 pts, neither clearly. Its volatility and worst fall are slightly lower than JEV's, which is the usual effect of averaging two imperfectly correlated weight series, but it inherits the Committee's higher turnover (68.4% a year against JEV's 33.3%), and the trading cost eats most of the diversification gain. On this sample, combining the two agentic systems is neither better nor worse than either alone.

## 5. Causal RAG: what is still missing

No Causal RAG experiment produced an investment result, and none is marked tested. Mock outputs and the failed run's outputs are not used as results.

| Experiment | Status | Precise blocker | Minimum action | Completion path |
|---|---|---|---|---|
| Reduced Evidence | Awaiting validation | The first real-model run (qwen3:4b, 2026-10-29) failed both pre-registered gates: G3b 53% fixture accuracy against 80% required, and 12 of 12 sample months with no final answer. | Re-run the Kaggle notebook with a new GitHub token. | Pipeline defects are already fixed (agent protocol 1.1). If both gates pass, the 95-month replay runs in the same session and `ap3_free_import` produces development results. |
| With Historical Documents | Blocked | BLS returns **HTTP 403** to this environment for all three release families; about 435 of roughly 909 documents are missing. Re-verified today: `www.bls.gov` 403, `download.bls.gov` unreachable. | A decision between the four documented options. | Options 1–3 in `AP3_CORPUS_STATUS_2026-10-29.md`; option 4 below. |
| Policy-path proxy variant | Awaiting validation | Needs the same passing real-model run, and it is a labelled sensitivity variant of the above, never a silent replacement. | As for Reduced Evidence. | Runs alongside the base version once it passes. |
| Do historical documents help? | Planned | Needs **both** versions' results; the corpus is incomplete. | Unblock BLS, then a passing run of both. | Compare the two versions on development months. |
| Standard RAG vs Causal RAG | Planned | Needs Causal RAG results to compare against. | A passing real-model run. | Swap graph-guided retrieval for plain similarity search, same model, documents and budget. |
| Ablations and placebo checks | Planned | Same. | Same. | No retrieval, rewired graph, permuted agent columns, raw mediators. |
| Model and calibration variants | Planned | Same, and the variants are not yet defined; they must be fixed in advance. | Same, plus a written definition. | Pre-register a small set, then run. |

**The fed funds futures input.** `FF_FUTURES_6M` is the one Bloomberg dependency. It is required and has not been silently replaced: the clearly labelled sensitivity variant uses the 2-year Treasury yield minus the 4-week bill rate as a stand-in, reported separately from the base version. Free alternatives were investigated today and **none can be reached from this environment**: the gateway denies CME, the Atlanta Fed's market probability tracker, the New York Fed and FRED. They are candidates for a network that allows them, but each would change the pre-specified source and would have to be recorded as a deviation.

**A fourth BLS option, free and worth trying.** The free Kaggle GPU session already has open internet, and a Causal RAG rerun is pending there anyway. Running `python -m native_backtest.scripts.ap3_corpus_fetch --families bls_employment_situation,bls_cpi,bls_ppi` as a **separate cell after** the gated run would show at zero cost whether BLS answers that network. It records the URL, SHA-256 and timestamps exactly as the existing fetcher does, so provenance is unchanged. BLS may still refuse a cloud address, so this is a test, not a solution.

## 6. Validation

- **Reproduction:** every shared output of the new Stage 2 run is byte-identical to the archived 2026-10-27 run, and the scorer's own check against the saved summary is MATCH.
- **Independent recomputation:** the bootstrap used here is implemented separately from the scorer and reproduces its published point estimates, 90% and 95% intervals and one-sided probabilities exactly (largest difference 0).
- **No look-ahead:** the Committee + JEV checks confirm matching decision dates and information cutoffs before the decision time in all 46 months; the regime labels use the VIX close at the decision date.
- **Nothing frozen changed:** no experiment definition, window, cost, metric, contrast or benchmark was altered; the statuses in `framework_config_v1.json` were updated to version 1.8 with a change-log entry, leaving every other setting untouched.
- **Tests:** `native_backtest/tests/test_within_approach.py`.
- **Safeguards:** the protected window was not scored, no model was called, and cost was $0.

## 7. What these results do not show

- **Development only.** These 46 months are where the approaches were built and checked. The confirmatory historical test, January 2024 – August 2026, remains sealed.
- **Low power.** With 46 months, only large effects can be separated from chance. None of these null results proves a signal is worthless.
- **Diagnostics, not selection.** The regime splits and the component signals are attribution diagnostics. No system was chosen, relabelled or tuned on any of these numbers.
