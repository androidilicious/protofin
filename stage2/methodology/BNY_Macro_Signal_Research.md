# BNY macro-financial signal discovery

Research cutoff: October 26, 2026. Prepared for the Duke MIDS / BNY capstone.

**Recommendation:** test three small extensions to the current quantitative baseline: credit-spread deterioration, a Treasury curve slope, and an implied-minus-realized variance proxy. Keep policy-announcement shocks and inflation composition as the next two research priorities. These are hypotheses worth testing, not demonstrated alpha for this project.

The accompanying inventory contains 20 candidates, with construction status, inputs, sources, dates, reported evidence, historical access, point-in-time requirements, overlap, limitations and Causal RAG use. A proposed feature is explicitly distinguished from a published strategy replication. No backtest was run and no performance of the BNY system was independently verified.

## 1. What could be established about the existing project

| Item | Evidence available in this investigation | What remains unverified |
|---|---|---|
| Quantitative baseline | The user's current description specifies macro surprises, factor construction, Ridge forecasts, allocation and backtesting. Retrieved conversation context describes first-release actual-minus-consensus surprises, growth/inflation factors, expanding-window next-month forecasts and Black–Litterman allocation. | Exact code, factor definitions, estimation windows, hyperparameters and allocation settings. These descriptions are context, not a code audit. |
| Data-source overview | Directly read BNY_Data_Sources_Overview.pptx dated October 20. It covers growth, inflation, policy, financial conditions, market assets, text/events, consensus surprises and portfolio governance. | A coverage slide lists intended sources; it does not prove that all series were downloaded, licensed, stored historically or used in the model. |
| Causal RAG | Visible project conversations describe the July 2023 retail-sales example, E3–E5 pathway, Ordinary/Multi-Query/Graph-Guided retrieval and the incomplete evidence chain. | A production interface from these outputs into the quantitative feature matrix. FinCausal/AVeriTeC pilot evaluations do not validate investment signals. |
| Agent features | Prior discussion proposes one-hot Supported / Contradicted / Insufficient categories interacting with standardized macro surprises. A Testing Agent is discussed. | Neither integration nor a working Testing Agent was established by accessible code. |
| Data files | deterministic_data1.xlsx is named in the project history. | File contents were not retrievable in this session. No row-level inventory, date-span verification or reuse claim is possible. |
| Demo | The supplied URL was attempted through web retrieval and direct HTTP. | Retrieval failed and direct HTTP returned 403. The live app, downloadable assets and source code could not be inspected. |

Project overview: [BNY_Data_Sources_Overview.pptx](https://chatgpt.com/library?file_id=libfile_d089d6f6a2a48191849b502cd5139554&account_id=personal).

The working design below uses the user's monthly MVP requirement. It does not certify that the deployed app implements exactly that design. Prior summaries also mention ANFCI, GPR, a 36-month covariance window, a 45/35/20 benchmark and 33 evaluation months. These are **unverified leads to check**, not settings to copy or performance evidence. If the sample really has only 33 out-of-sample months, it is too short to make strong claims about many macro regimes or competing signals.

## 2. Ranked community and source directory

Rank reflects usefulness for this capstone, not popularity. Community posts supply hypotheses and implementation warnings; primary research supplies the stronger empirical evidence.

| Rank | Resource and direct discussion | Author / date | What it offers and how to use it |
|---|---|---|---|
| 1 | [Macrosynergy: Economic surprises and global asset class returns](https://macrosynergy.com/research/economic-surprises-and-global-asset-class-returns/) | Lasse de la Porte-Simonsen and Ralph Sueppel; July 11, 2026 | Closest conceptual match; detailed point-in-time construction and notebook. Model-based surprises differ from survey consensus, and reported tests are daily. Much underlying JPMaQS data requires access. |
| 2 | [Federal Reserve: Near-term forward spread](https://www.federalreserve.gov/econres/feds/the-near-term-forward-yield-spread-as-a-leading-indicator-a-less-distorted-mirror.htm) and [EBP updates](https://www.federalreserve.gov/econres/notes/feds-notes/updating-the-recession-risk-and-the-excess-bond-premium-20161006.html) | Engstrom and Sharpe; 2018 / revised March 2019. Favara, Gilchrist, Lewis and Zakrajsek; October 6, 2016, updated October 2026 | Precise mechanisms, data and important revision warnings. Stronger basis for economic hypotheses than forum performance screenshots. |
| 3 | [AQR: Time Series Momentum](https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum), [Macro Momentum](https://www.aqr.com/Insights/Research/White-Papers/A-Half-Century-of-Macro-Momentum), [Carry](https://www.aqr.com/Insights/Research/Journal-Article/Carry) | Moskowitz, Ooi and Pedersen; May 2012. Brooks; August 2017. Koijen et al.; February 2018 | Established conventional controls and economic-factor concepts. Do not transfer diversified futures results directly to a small constrained ETF portfolio. |
| 4 | [Portfolio123: Macro Factors](https://community.portfolio123.com/t/macro-factors/70596) | Victor1991; February 17, 2025, replies through June 2026 | Specific credit-spread and Treasury ideas, regional failure and turnover concerns. Useful discovery; not independent validation. |
| 5 | [QuantConnect: Rage Against the Regimes](https://www.quantconnect.com/forum/discussion/14818/rage-against-the-regimes-the-illusion-of-market-specific-strategies/) | Francesco Baldisserri; February 7, 2023; reply by Jared Broad | Concrete regime-model debate and toy implementation. Broad describes look-ahead and poor rolling-selector results. Use to challenge hindsight regime labels, not as proof ML solves timing. |
| 6 | [Quantpedia: Market Timing, Part 2](https://quantpedia.com/avoid-equity-bear-markets-with-a-market-timing-strategy-part-2/) and [revisit](https://quantpedia.com/avoid-equity-bear-markets-with-a-market-timing-strategy-revisiting-our-research/) | Quantpedia research team; March 15 and August 18, 2023; individual byline not established | Explicit real-sales/industrial-production rules. Their own replication shows higher return can accompany worse risk-adjusted performance. Full real-time vintage compliance is not established by a simple one-month observation lag. |
| 7 | [Quantocracy: Macrosynergy feed](https://quantocracy.com/?blog=macrosynergy) and [October 18, 2026 links](https://quantocracy.com/recent-quant-links-from-quantocracy-as-of-10182026/) | Quantocracy editors; aggregator posts through October 2026 | Efficient discovery across research blogs. Follow original authors; an aggregator excerpt is not independent evidence or reproducibility. |
| 8 | [Macrosynergy GitHub](https://github.com/macrosynergy/macrosynergy) and [tutorial notebooks](https://macrosynergy.com/academy/introductory-tutorials/) | Macrosynergy maintainers; active repository, accessed October 26, 2026 | Reusable panel and sequential-learning machinery. Open-source tools do not imply free access to their research datasets. Pin a commit before reproducing work. |
| 9 | [FRBSF US monetary-policy event-study database](https://www.frbsf.org/research-and-insights/data-and-indicators/us-monetary-policy-event-study-database/) | Acosta, Ajello, Bauer, Loria and Miranda-Agrippino; paper December 15, 2025, revised August 27, 2026; data page September 17, 2026 | Public Excel data and R construction code; unusually useful new resource for the capstone's rate-path mechanism. Retrospectively observed event reactions are not automatically delayed alpha. |
| 10 | [Numerai: Supernova data release](https://forum.numer.ai/t/signals-data-v3-0-supernova-release/8354) and [data/tools thread](https://forum.numer.ai/t/free-or-cheap-data-and-tools-for-numerai-signals/350) | ark; displayed post September 1, 2026 (body also references August 28). player1; May 7, 2020 | Valuable ideas on neutralization, incremental contribution and churn. Primarily equity cross-sectional tournament design; do not import its target, scoring or old provider list blindly into macro allocation. |
| 11 | [r/algotrading: Fundamental and economic analysis system](https://www.reddit.com/r/algotrading/comments/nguul3/fundamental_and_economic_analysis_system/) and [macro data APIs](https://www.reddit.com/r/algotrading/comments/zodyr9/what_are_some_of_the_bests_free_apis_for/) | Reddit users; exact authors/dates not reliably exposed in retrieved excerpts | Relevant data-collection discussions, but no reproducible monthly macro alpha was established. Discovery only; dates/authors are unavailable rather than guessed. |
| 12 | [r/quantfinance: Macro factors vs ML](https://www.reddit.com/r/quantfinance/comments/1rwm00e/macro_factors_vs_ml_for_systematic_signals_heres/) | Flyinggrassgeneral; displayed “6mo ago” at retrieval; exact date unavailable | Proposes a CNH/CNY capital-control mechanism. No auditable performance or exact rule. Structural intuition alone does not establish durability; defer for this asset universe. |

Additional particularly useful discussion: [Portfolio123 yield curve thread](https://community.portfolio123.com/t/market-timing-yield-curve/56020), mm123 and PortfolioPerfection, February 23, 2017. A proposed lead offset is explicitly acknowledged as fitted to one recession. This is a practical warning against optimizing the lag of inversion until a backtest looks attractive.

## 3. Evidence assessment and the five recommendations

All rankings below are qualitative research judgments. There is no fabricated numerical score or ranking by published Sharpe ratio. “Incremental” means a plausible information difference, conditional on the uninspected baseline feature list.

| Rank | Candidate | Rationale / evidence | Access and effort | Incremental value and decision |
|---|---|---|---|---|
| 1 | S06: Credit-spread deterioration | Financing and risk-appetite channel; substantial credit literature, but the selected Baa change is a simple new hypothesis. | Publicly viewable BAA10Y; low effort. Full HY OAS history is conditional. | More forward-looking market information than release surprises; possible ANFCI overlap. Test one column first. |
| 2 | S04: Treasury 10y–3m slope | Simple, transparent policy/cycle state. Macro forecasting evidence is stronger than proof of monthly trading performance. | Treasury/FRED; low effort and long history. | First policy-expectation challenger. S05 NTFS is an economically cleaner follow-up, with greater historical data burden. |
| 3 | S08: Variance premium proxy | Peer-reviewed equity-return literature; option prices provide information beyond economic releases. | Free VIX history; requires daily underlying prices. Moderate effort. | Test against both VIX and realized variance, not just against the macro baseline. Exact paper replication is not claimed. |
| 4 | S09: FOMC policy-path surprises | Public 2025–2026 database and explicit event methodology. Excellent connection to rate-path causal hypotheses. | Public data/code; moderate effort; PCA and event overlap audit required. | Event effects are established more directly than next-month continuation. Second wave after simple features. |
| 5 | S10: Supply/demand inflation composition | Gives different meaning to equal headline inflation; strong explanatory fit for Causal RAG. | Public chart data; strict vintage reconstruction can be demanding. | Potentially new information beyond magnitude of surprise. Gate on historical release versions; predictive value remains unproven. |

**What to defer:** EBP, ACM term premium and retrospective inflation decomposition until historical versions are defensible; liquidity until the intervention accounting and full notebook specification are available; CP until an annual-horizon test is justified; carry until instruments and forward/roll data are confirmed. Treat surprise variants, macro momentum, ANFCI, Sahm and GPR as overlap checks rather than automatically adding them all. Use cross-asset price momentum as a conventional control. Do not expand the asset universe to rescue a signal.

Three important contradictory findings:

1. [Goyal, Welch and Zafirov, November 2024](https://doi.org/10.1093/rfs/hhae044) re-examine many published equity-premium predictors through 2021. Their work makes persistence beyond original samples a central hurdle. Economic plausibility and an in-sample regression are insufficient.
2. [Kim, Tse and Wald, 2016](https://www.sciencedirect.com/science/article/abs/pii/S1386418116301379) challenge how much time-series momentum performance comes from the signal rather than volatility scaling. Compare new signals with risk-matched controls.
3. [Engstrom and Sharpe, March 25, 2022](https://www.federalreserve.gov/econres/notes/feds-notes/dont-fear-the-yield-curve-reprise-20220325.html) emphasize that term spreads may reflect investors' existing recession expectations. A predictive curve is not proof that inversion causes recession, nor a rule to leave equities immediately.

Further recent research: [Bie, Diebold, He and Li, August 23, 2024](https://arxiv.org/abs/2408.12863) finds yield-curve macro predictability depends on the rate regime. [Kang, 2026 preprint](https://arxiv.org/abs/2608.07536) studies monthly yield forecasts with macro inputs; its findings concern maturities and curve movements, not a validated ETF alpha. These are methodological leads, not reasons to redesign this Ridge MVP.

## 4. Three concrete implementation experiments

### Shared interface and timing

Add a thin feature adapter to the existing data pipeline. Each record should retain `series_id, observation_date, release_time, available_time, vintage_id, value, source`. A monthly feature record should retain `decision_time, feature_name, raw_value, latest_input_available_time, transformation_version`. Preserve missing values as missing; zero is a valid observation and must not be used for unavailable data.

At decision time c_m, take only input records with available_time <= c_m. If first-release values are needed, preserve them separately from later revisions. FRED API observation/vintage parameters are documented [here](https://fred.stlouisfed.org/docs/api/fred/series_observations.html); an ALFRED vintage still needs an intraday release calendar if the decision occurs near a release. A date-only field does not certify availability before a particular trading hour.

Construct each raw feature deterministically. Fit centering/scaling only on the training sample for that fold. Reuse the existing standardizer and Ridge fitting code once inspected; do not insert a second incompatible scaler. For an expanding-window standardization:

`z_m = (x_m - mean(x_train)) / sd(x_train)`

Use the unchanged baseline transformation if it differs, provided it is fitted without future data. Do not tune lookback, winsorization, sign, threshold or lag against the final evaluation period.

### Experiment A — S06 credit deterioration

**Inputs:** [BAA10Y](https://fred.stlouisfed.org/series/BAA10Y), publication metadata and three completed month-end snapshots. First ask whether the teammate already has an equivalent spread input. Baa-minus-Treasury includes duration and composition effects; it is neither HY OAS nor default-adjusted EBP.

**Raw feature:** let c_m be the latest published BAA10Y known at the decision. Set `x_credit,m = c_m - c_(m-3)` in percentage points, then standardize in training. Positive means wider spreads; Ridge estimates the return coefficient. Do not force a negative equity sign. Widening stress and elevated starting compensation have different economic interpretations.

**Fit:** baseline B versus B + z_credit, per existing asset. Forecast existing next-month returns and use the current optimizer. Optional later robustness: same frozen three-month difference for an authorized HY OAS archive; report it as a different data-series test. FRED's [ICE HY OAS notice](https://fred.stlouisfed.org/series/BAMLH0A0HYM2) limits that series to three years from April 2026, so downloading it today does not establish a long usable sample. BAA10Y also has provider terms; public viewing is not permission to redistribute raw data.

**Extra attribution:** if ANFCI is already in B, require the credit feature to improve predictions conditional on it. Diagnose train-only regression on baseline features and examine remaining residual variation, but do not simultaneously search residualization variants as additional winners.

### Experiment B — S04 curve slope, then S05 challenger

**Inputs:** [T10Y3M](https://fred.stlouisfed.org/series/T10Y3M) or matched DGS10/DGS3MO histories. Reuse any exact series already held. Use the last observation published by c_m; execute afterward using the original execution convention. The example retrieved FRED page updates after the US equity close, demonstrating why observation date alone is insufficient.

**Raw feature:** `x_curve,m = y10_m - y3m_m`. One continuous standardized column; no optimized inversion threshold or recession lead offset.

**Fit:** B versus B + z_curve. Existing policy variables stay in B. A slope can predict medium-term macro conditions yet fail at next-month asset returns; retain that possibility explicitly.

**Follow-up:** only after this test, register NTFS as a replacement challenger to the simple curve feature, not an automatically additional factor. Source definition is a six-quarter-ahead one-quarter forward rate minus the current one-quarter yield. Exact replication requires the source curve and conventions. [Fed nominal curve parameters](https://www.federalreserve.gov/data/nominal-yield-curve.htm) offer a reconstruction route, but exclude bills, are typically posted weekly, and can revise. Use archived estimates with actual posting times or label the result pseudo-real-time. Do not compute a zero-coupon forward from two par yields.

### Experiment C — S08 implied-minus-realized variance proxy

**Inputs:** [Cboe historical VIX](https://www.cboe.com/tradable-products/vix/vix-historical-data), daily S&P 500 price returns and matching close/availability times. Reuse team daily equity prices only if they exist and cover the required period. Monthly returns cannot reconstruct daily realized variance. An ETF alternative must be documented as a proxy with its own start date and return convention.

**Raw feature:** with r_d daily decimal log price returns and d_m the last known synchronized close:

`RV_m = (252/22) * sum(r_(d_m-k)^2, k=0,...,21)`

`x_var,m = (VIX_(d_m)/100)^2 - RV_m`

This is an annualized implied-minus-trailing-realized variance proxy. The ideal variance risk premium subtracts a physical expectation of future variance; a trailing estimate is not the same quantity. Avoid inserting future realized variance as a feature. Richer published implementations use additional variance information.

**Fit:** compare B; B + VIX variance; B + RV; B + x_var. This extra attribution comparison is predeclared, not a search for which volatility transform wins. If x_var fails to add value beyond simple volatility, prefer the simpler variable. Keep the one-month target primary; a later three-month target must be separately registered with overlapping-label controls.

### Components to freeze

Freeze the current asset universe, returns convention, benchmark, train/test dates, forecast target, expanding/rolling convention, Ridge implementation and existing tuning protocol, covariance estimation, Black–Litterman prior/confidence mapping if present, constraints, leverage and cost model. Freeze them **after inspecting the actual implementation**, not from recollected numbers. If an existing defect requires correction, rerun all variants on the corrected baseline and record the change.

Signal discovery selects hypotheses; signal construction generates timestamped columns; Ridge estimates expected returns; allocation converts forecasts into weights. Improving one stage does not automatically establish investment value in the next stage.

## 5. Evaluation that can establish incremental value

1. **Reproduce B first.** Obtain one command and frozen inputs that regenerate saved predictions, weights and metrics. Record commit and data hashes. If real versus synthetic data are mixed, separate them before any empirical claim.
2. **Check feature overlap before any returns test.** Compare exact definitions and training-only correlations/explanatory regressions with existing factors. If the proposed column already exists, mark it duplicate. A new name is not new information.
3. **Register the first experiment family.** B, B+credit, B+curve, B+variance proxy, followed by B+all three as a planned combination. Include the predeclared variance attribution controls and a price-momentum control. Log every variation, including discarded ones. The 20-item directory is a discovery inventory, not permission to run and rank 20 backtests on one holdout.
4. **Walk forward chronologically.** At month m, fit only on examples whose target return has fully completed and become available by c_m. Use the same observations for paired comparisons and report each series' coverage loss. Imputation, scaling, PCA, residualization and tuning all belong inside training folds.
5. **Forecast tests first.** Per asset report paired OOS MSE/MAE and `R2_OOS = 1 - SSE_candidate/SSE_baseline`; use the same evaluation dates. Also compare with an expanding historical-mean return forecast. Report coefficient stability and whether an apparent gain is one crisis month. Directional accuracy is secondary.
6. **Investment tests second.** Through the frozen allocation mapping, report net return, volatility, Sharpe, drawdown, turnover and actual exposure/risk shifts. Compare with B and the unchanged portfolio benchmark. Include matched-risk/passive controls to distinguish forecast gains from a persistent equity underweight or different leverage. Cost sensitivity should use the existing cost assumption and a predeclared higher-cost scenario, not a cost chosen afterward.
7. **Uncertainty and selection.** Use paired loss differences, a serial-dependence-aware block bootstrap and appropriately qualified inference. If formal nested squared-error comparisons are used, consider a Clark–West adjustment with the caveat that penalized refitting complicates its assumptions. Correct for the number of registered candidate tests (e.g., Holm), and describe development selection beyond those tests. A bootstrap does not manufacture independent regimes from 33 observations.
8. **Keep a genuinely untouched test.** A period used to choose these features or inspect previous strategy results is development data. Where possible, evaluate later dates not consulted during selection; otherwise reserve prospective paper-trading months. Require directionally consistent gains across time and assets; do not select a favorable subperiod afterward. Predeclared regime breakdowns are diagnostics, not a selector for the best regime.

**Success criterion:** a consistent, economically interpretable reduction in forward forecast error, followed by a useful improvement after costs under the fixed allocation rules and comparable risk. A higher historical Sharpe alone does not qualify. Report uncertain or null results as such; no promise of statistical significance is appropriate without knowing sample size.

## 6. Agent-only versus Causal RAG comparison

Run the numerical feature tests before introducing a language-model change. Then compare four clearly scoped systems: B; B plus a fixed conventional feature set; that same model plus agent features; that same model plus Causal RAG features. Also compare agent-only reasoning with Causal RAG under the same numerical baseline. Fix the LLM, prompt, output schema, token/retrieval budget and decision dates. Log any difference in documentary access; a no-retrieval agent comparison tests the full RAG package, whereas ordinary RAG versus graph-guided RAG can better isolate causal retrieval structure.

Use the previously discussed one-hot categories, not arbitrary +1/−1 economic scores. Prefer a prespecified mechanism and one small feature block at first: for example, `z_credit * I(label=Supported)` and analogous categories. The Ridge model must learn any predictive mapping. If all three indicators sum to one and their parent feature is also included, use a reference category or state the exact regularized encoding; otherwise the block is redundant. Standardization/regularization must treat the compared variants consistently.

Historical evidence must have been published before the decision. Preserve URLs, publication timestamps, passage hashes, retrieval results and claims supported. Distinguish original publication from a web page's later modification date. Do not retrieve current pages that incorporate the realized outcome. A current LLM may remember later historical events even when retrieval is restricted: use evidence-bound extraction, audit for outcome leakage and ultimately validate prospectively or with a model cutoff preceding the evaluation. Point-in-time retrieval alone cannot eliminate model-knowledge leakage.

RAG can classify mechanisms or uncover contradictory evidence. It cannot prove causality from correlated narratives, convert stated confidence into a calibrated probability or establish that an already-priced event predicts next-month returns. Any evidence-strength score needs independent calibration. A Testing Agent should execute prespecified statistical checks and report effect sizes/uncertainty, not search freely until it finds a profitable mechanism.

## 7. Exact requests for Grace / the Quant MVP owner

| Request | Minimum concrete handoff | Why it is needed |
|---|---|---|
| Reproducible implementation | Repository or source archive, commit, environment lockfile, entry point and configuration | Establish what is implemented and rerun B. Website access alone is insufficient. |
| Dataset and dictionary | deterministic_data1.xlsx plus every actual input file, column dictionary, units, transformations, source and data-realism flag | Establish what the team possesses versus plans to collect; distinguish observed, synthetic and illustrative values. |
| Macro event table | Indicator, observation period, original release time/time zone, first actual, pre-release consensus, consensus capture time, later revisions and vintage/source | Verify surprise construction and publication-time joins; check standardization and sign direction. |
| Complete feature matrix | Decision timestamp, every raw and transformed factor, interaction formula, factor weights and missing-data handling | Establish whether curve, credit, VIX, policy, ANFCI and GPR are already present. |
| Asset return files | Exact tickers/instruments, start/end dates, daily and monthly prices/returns, dividends/rolls/FX convention, cash rate and benchmark | Match forecast targets and build realized variance without approximating daily observations from monthly returns. |
| Forecast protocol | First training month, first OOS month, training window, target maturity, Ridge lambda/search procedure, scaler fit rules and saved monthly predictions | Eliminate leakage and hold the statistical comparison fixed. |
| Portfolio protocol | Prior/benchmark, forecast-to-view conversion, Black–Litterman confidence if used, risk window, constraints, rebalance/execution time and costs | Attribute performance to signals rather than changed allocation choices. |
| Existing archives | Historical curve/spread/VIX files; OAS export coverage; ANFCI/GPR snapshots; Bloomberg export rights and available fields | Decide which inputs are reusable and whether long histories/vintages are available. Bloomberg access must be confirmed, not presumed. |
| Text corpus | Historical documents, original timestamps, archive versions, retrieval cutoff logic and saved agent outputs | Determine whether a fair historical agent/RAG comparison is currently feasible. |
| Existing results | Saved baseline metrics, predictions and weights; all previous signal experiments and periods viewed | Audit claimed results and establish which data are already consumed for selection. |

## 8. Practical order of work

**First handoff:** obtain the code, actual data and feature dictionary; reproduce the baseline and mark overlap in the inventory. This is the gating step, not another literature search.

**First implementation:** add the available-time adapter and three deterministic feature constructors. Begin with BAA10Y and T10Y3M; add the variance proxy once daily equity prices are verified. Keep an audit sample showing the source observation, publication time and final monthly value for each feature.

**First evaluation:** run the registered paired comparisons once using the existing forecasting/allocation design. Retain all null results and coverage differences. A failed or duplicate feature should be dropped rather than tuned repeatedly on the holdout.

**Second wave:** test NTFS as a curve challenger; prepare the public USMPD policy-event feature; build a point-in-time inflation composition panel if historical versions exist. Only then run the matched agent / Causal RAG comparison on a prespecified mechanism. If historical LLM leakage cannot be controlled, use prospective paper forecasts.

The immediate output should be a small, reproducible experiment log with three additions and a frozen baseline, rather than a larger model. The literature supports taking these hypotheses seriously; the team's own out-of-sample evidence must decide whether to keep them.
