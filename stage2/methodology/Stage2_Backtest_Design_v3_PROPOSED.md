# Stage 2 Backtest Design v3 — PROPOSED amendment (not frozen)

**Project:** Duke MIDS / BNY Macro-Financial Capstone
**Drafted:** 2026-10-27
**Status:** `PROPOSED_NOT_FROZEN` until the team approves the blockers in §13.
**Machine-readable draft:** [`../config/stage2_proposed_config_v3.json`](../config/stage2_proposed_config_v3.json)
**Companion tables:**
- [`stage2_freeze_matrix_v3_proposed.csv`](../config/stage2_freeze_matrix_v3_proposed.csv)
- [`stage2_v2_to_v3_changelog.csv`](../config/stage2_v2_to_v3_changelog.csv)
- [`stage2_system_manifest_v3_proposed.csv`](../config/stage2_system_manifest_v3_proposed.csv)

> **What this document does and does not do**
> - It amends the *design*. It does not touch the v2 freeze: `Stage2_Backtest_Freeze_v2.md`, `stage2_frozen_config_v2.json` and `stage2_signal_manifest_v2.csv` keep the hashes recorded in `stage2_freeze_artifact_hashes_v2.json`.
> - It changes no production code (`stage2/scoring/*.py`).
> - It runs no backtest, opens no test window and tunes nothing.
> - The conventional-signal experiments (B1–B5, B-All) are **paused and archived** ([pause record](Stage2_Conventional_Signals_PAUSE_2026-10-27.md)).

---

## 1. Why v2 is being amended

v2 asked a narrow question: *with Ridge and the allocator held fixed, does changing the feature set improve forecasts?* Its freeze principle was "the only experimental treatment is the signal feature set" (v2 §1).

The revised question is broader:

> **How do different approaches to generating investment views affect forecasting accuracy and portfolio decisions?**

Two of the four approaches (Agent Committee, JEV) are not Ridge models and do not output one-month excess-return forecasts. Under v2's principle they could not be in the experiment at all. v3 therefore changes the experiment's boundaries:

- **Within Ridge-compatible systems** (Approach 1, Approach 3 and its controls), v2's principle still holds exactly. Only the feature set differs.
- **Across approaches,** the view-generation method is the treatment. What is held fixed is everything downstream of the views and everything about data, timing, costs and scoring that can be shared.

Nothing else in v2 changes unless the change log (§11) says so and gives a reason.

## 2. What was inspected and what was found

**Sources inspected:**
- protofin branches `stage2-evaluation-mvp` (v2 freeze, canonical scorer, development results), `main`, `approach-1-committee-black-litterman`, `feature/empirical-view-uncertainty`, `approach-2`, `feature/jev`.
- The CauseTrace repositories `FarnooshMemari/causal-rag-mvp` (head 389f826) and `causal-rag-demo` (5ec2a75).
- The design note *Causal Agentic Macro Portfolio Allocation* (Google Doc, 2026-09-30).

**Also inspected:** the earlier deterministic MVP on `main` (`deterministic-model/deterministic_mvp`: Growth/Inflation surprise signals → expanding Ridge → BL on SPY/IEF/LQD, 1 test file). Its committed `ridge_predictions.csv` holds forecasts *and realised returns* for decision months 2022-12 through 2026-09. This is the concrete basis for treating the 2023–2026 window as partly inspected.

**Not found:** the October 23 class presentation is in none of these places or the shared Drive. The CauseTrace stage list (Knowledge Graph → Hypothesis Agent → Causal RAG → Testing Agent → Quant Model → Allocation) is therefore taken from the team's brief, not from the slides. Each stage was then checked against the code.

Status is classified as follows:

- **Documented:** prose only.
- **Implemented:** code exists.
- **Tested:** automated tests exist.
- **Outputs:** saved run outputs exist.

### 2.1 Architecture comparison (Deliverable 1)

| | **Approach 1 — Deterministic baseline (AP1)** | **Approach 2A — Agent Committee (AP2A)** | **Approach 2B — JEV (AP2B)** | **Approach 3 — CauseTrace / Causal RAG (AP3)** |
|---|---|---|---|---|
| **Actual inputs** | 8 Bloomberg macro-surprise z-scores (first print − median; prior-12-release standardisation, ddof 1; same-month mean). Canonical panel `459bef98…` | **Live:** 7 raw series (^TNX, SPY, TLT, ^IRX, EPU, GPR, FOMC-statement RoBERTa score), about 16 numbers plus date and regime. **Historical replay:** 6 raw series as 16 relative features plus the cash-yield level. The SPY/TLT names and the cash level were re-inserted into the "masked" committee prompts (`scripts/build_backtest_months.py` L47-50) | Per README, the same masked payload as the committee: 17 numbers, including the SPY/TLT names and the cash level. The exact prompt is **not in the repo** | **MVP:** one event (July 2023 advance retail sales, released 2023-08-15). 24-document corpus; 22 fetched; 281 chunks eligible at cutoff. BM25 retrieval with a point-in-time filter. Hand-authored graph: 6 nodes, 5 edges, 2 pathways, equity-only |
| **View-generation model** | Separate Ridge per asset: expanding window; 48-label minimum; inner CV with 1-month purge; frozen alpha grid; t−2 label rule | gpt-4o (alias logged, snapshot not logged), T = 0, seed 42. Economist ∥ Risk Manager → CIO | `typesafe/jev` on Cloudflare Workers AI, answers recorded once. **No calling code, no prompt, no model version** in the repo; the recorder script named in comments never existed | claude-sonnet-5-5 via CLI (alias only; default sampling). The LLM labels each graph edge from retrieved excerpts, then quotes are verified. **No Hypothesis Agent, no Testing Agent, no quant model in code** |
| **View output** | 1-month **excess-return forecasts**, SPY/IEF/LQD, decimal | **12-month total-return %** views for **SPY and TLT**, plus a categorical confidence (High/Medium/Low), converted to excess over ^IRX | **p = P(SPY beats TLT over 12 months)**, plus a distribution over 5 tilt options (+3, +1.5, 0, −1.5, −3 "points", labelled "illustrative, not calibrated"), plus a confidence | Per edge: Supported / Contradicted / Insufficient, with verified quotes. Per pathway: chain status. MVP also has a {−1,0,+1} `code`. **Not per asset, not a forecast** |
| **Allocation** | Frozen Black–Litterman: P = I, τ 0.05, δ 2.5, prior 45/35/20, 36-month Ledoit–Wolf Σ, bounds, Ω from AP1 development errors; 5 bp | Two-asset BL. 60/40 prior, δ 2.5, τ 0.05. Σ: 1-year sample (replay: from 12-month vols and correlation). Ω = c·τΣ with c = 0.5/1/2 by confidence; elevated EPU/GPR lowers confidence one notch. Closed form clipped to **40–80% SPY**; 5 bp | 60/40 BL-prior edge + confidence × Σ(probs × points). Closed-form two-asset weight clipped to **40–80% SPY**. **p is not used.** No Ω. The term "Capped Tilt" does not appear in code | **None** in code. The 2026-09-30 design note proposes passing the Ridge forecasts into "the same constrained portfolio optimizer" |
| **Timing in existing backtests** | Decision 20:00 ET last trading day; execution at next official close | Month-end close, **same-close execution**; yfinance adjusted closes | Month-end close, **same-close execution** | n/a (one event, 10:00 EDT cutoff) |
| **Implementation status** | Implemented; 25 tests; canonical development rerun; data gates PASS; historical window sealed | Orchestration and BL implemented. Parser bug fixed and tested only on `approach-2`. **272 saved monthly CIO outputs** (2004-01..2026-08, gpt-4o, built 2026-10-05; every confidence "Medium"); no committed metrics for the committee strategy. The Python backtest summary uses the *single-call* masked views, not the committee | 272 saved monthly answers (2004-01..2026-08). Browser replay implemented (reproduces saved weights). Evaluation script (Brier, AUC) implemented, **untested**. No tests | Feasibility MVP for retrieval and labelling: 17 unit tests, saved outputs for **1 event × 3 repeats**. Graph frozen "before returns" but authored by an agent that knew post-2023 outcomes; v2 edge E1 redefined after seeing v1 results. **Monthly feature pipeline, Ridge integration and allocation are all proposed only** |
| **Leakage controls present** | Point-in-time panel; t−2 labels; dividend and risk-free gates | Masked single-call replay with year-guess and sign-flip probes (gpt-4o). Probe hits concentrate in 2020–2023 months, which may be recognition or a guessing bias. **The committee prompts themselves are not fully masked.** EPU/GPR are revised vintages | None specific to JEV; same payload caveats | Point-in-time document filter (0 future chunks); no date masking; contamination acknowledged in the README |

**Consequences for the design:**
- Only AP1 currently produces the controlled-experiment interface: monthly one-month excess-return views for SPY/IEF/LQD.
- AP3 is *designed* to produce it, but its monthly pipeline does not exist. "Ridge for Approach 3" is a design decision still to be implemented and verified.
- AP2A could produce it only through a re-specified output schema (§4.1, Blocker B2).
- AP2B cannot produce it without inventing a probability-to-return conversion, which v3 forbids.

## 3. System labels (v2 labels are retired, not reused)

| v3 label | Definition | Relation to v2 |
|---|---|---|
| **AP1** | 8 macro surprises → Ridge → frozen BL | **Identical to v2 System A.** Same features, model, Ω and canonical scorer |
| **AP2A** | Agent Committee as built (SPY/TLT, 12-month views, native BL, 40–80% band) | New. Not v2 C |
| **AP2A-1M** | Same three agents and roles; output schema re-specified to 1-month excess-return views for SPY/IEF/LQD; into the frozen BL | New; **proposed, needs approval (B2)** |
| **AP2B** | JEV as built (p, 5-way tilt, confidence-weighted capped tilt, SPY/TLT, 40–80% band) | New. Not v2 C |
| **AP3** | AP1's 8 columns + 2·N_ch causal-channel indicators → same Ridge → frozen BL | Successor of v2 D ("A + matched Causal-RAG features"), now with a fixed schema |
| **AP3-STD** | Same columns and schema; standard (non-graph) retrieval; matched budget | Successor of v2 C. **A control, not "the agent system"** |
| **AP3-PERM** | AP3 agent columns permuted across months | v2 "Cπ" (permuted labels) |
| AP3-RG | Rewired-graph placebo | v2 "D0" |
| AP3-NR | No-retrieval diagnostic | v2 "C0" |
| AP3-INT | AP3 plus Shock × Signal interactions | New; separate experiment |
| *(paused)* B1–B5, B-All | Conventional signals | **Archived**; must not be run under v3 |

The labels C and D are not used in v3, because v2's README and config defined C differently (JEV vs standard RAG). That ambiguity is resolved by retiring both labels.

## 4. Revised comparison design (Deliverable 4)

### 4.1 Track V — controlled view-quality experiment (**primary**)

**Estimand:** the effect of the view-generation method on (a) one-month forecast accuracy and (b) portfolio outcomes when every view passes through the *same* frozen allocator.

**Shared by every Track V system:**
- universe SPY/IEF/LQD and the decision and execution timing;
- the target (one-month total return minus the DTB4WK cash return);
- the common scoring dates;
- the frozen v2 BL allocator, including Ω estimated once from AP1 development errors (`stage2/config/stage2_omega_from_A_development.json`, `f7e3b9ef…`);
- costs, turnover accounting, benchmarks, metrics and bootstrap.

**Interface a system must produce:** one vector Q_t = (SPY, IEF, LQD) of one-month expected excess returns (decimal) per month-end decision, generated with information available at 20:00 ET.

| System | Track V eligibility |
|---|---|
| AP1 | **Eligible now** |
| AP3, AP3-STD, AP3-PERM | **Eligible by design.** They reuse AP1's Ridge, so they produce Q natively. They need the monthly feature generator built (§12) |
| AP2A-1M | Eligible **only after** re-specification and approval (B2). The 12-month SPY/TLT views can't be divided by 12 or mapped TLT → IEF; that would invent a conversion |
| AP2A, AP2B | **Not eligible.** They are scored in Track N and in their native forecast scores only |

Agent confidence is not used for Ω in the primary Track V run, because using it would make uncertainty calibration a second treatment (rationale from the v2 freeze, §8 there). A secondary Track V run may let AP2A-1M use its own confidence-scaled Ω.

### 4.2 Track N — native-system comparison (**supplementary**)

**Estimand:** realised portfolio performance of each *complete* system: its native views and its native allocation.

**Common protocol** (applied to saved answers where they exist; no new LLM calls are needed to change execution):

- Decisions use information at month-end 20:00 ET.
- Execution is at the **next** official close. Existing replays use same-close execution and must be re-scored.
- Monthly rebalancing.
- 5 bp per dollar traded, with drift-aware turnover.
- Pinned total-return data: SPY/IEF/LQD as in v2. **TLT must be pinned and pass a freeze-gate-5 distribution check before use.**
- Excess returns are scored over DTB4WK, whatever cash rate a system uses internally.
- Identical evaluation months and the same metric set (v2 §10 secondary list).

**Native universes differ.** AP1 and AP3 trade SPY/IEF/LQD; AP2A and AP2B trade SPY/TLT. Raw cross-system Sharpe or CER rankings therefore mix the effect of the decision method with the effect of the investable universe. v3 reports:

- **Primary Track N statistic:** *active* CER = system CER − CER of its own-universe neutral portfolio (AP1/AP3: 45/35/20; AP2A/AP2B: their 60/40 prior), net of identical costs, with block-bootstrap intervals.
- **Descriptive only:** cross-system comparisons of raw metrics. Harmonising native universes is a team decision (B5).

### 4.3 Native forecast scoring (approach-specific; never pooled with Track V metrics)

**AP2B (JEV):** p is a probability, so it is scored as one.

- Score p against the realised event "SPY total return > TLT total return over the next 12 months".
- Metrics: Brier score vs a base rate known at the time, log score, calibration bins and AUC.
- Overlapping 12-month outcomes need 12-month blocks in the bootstrap.
- The 5-way tilt distribution is scored with a ranked probability score against the realised 12-month SPY−TLT spread bucket, but **only if** bucket edges are frozen before scoring. Otherwise it is descriptive.

**AP2A (Committee):** the 12-month SPY/TLT total-return views are scored against realised 12-month returns (MSE vs the time-known historical mean). Horizon and assets differ from Track V, so these numbers are never placed beside Track V MSE.

### 4.4 Recommendation

**Track V is primary** because it is the only design that isolates *view generation*.

**Track N is supplementary** because its differences combine view generation, allocation rule, confidence handling, investable universe and position band.

The recommended minimum change that lets the Agent Committee into the controlled experiment is AP2A-1M: same agents, same roles, new output schema. JEV stays native-only unless the team defines, *before any test data are seen*, a calibrated mapping that it is willing to defend. v3 does not propose one.

## 5. Freeze matrix (Deliverable 2)

The full matrix is in `stage2_freeze_matrix_v3_proposed.csv`. Scopes:

- **ALL:** every system in both tracks.
- **TRACK_V:** systems entering the controlled experiment.
- **RIDGE:** AP1, AP3 and AP3 controls.
- **LLM:** AP2A, AP2A-1M, AP2B, AP3, AP3-STD, AP3-RG, AP3-NR.
- **SPECIFIC:** varies by approach and is documented.

| Item | Scope | v3 value |
|---|---|---|
| Decision timestamp; `available_at <= decision_time` | ALL | v2 unchanged |
| Execution at next official close; one-month holding; monthly rebalancing | ALL | v2 unchanged. Native replays are re-scored |
| Scoring target: total return − DTB4WK accrued | ALL | v2 unchanged |
| Price data: pinned total-return files; distribution check | ALL | v2 unchanged; TLT added for Track N |
| Development / historical / prospective windows | ALL | v2 dates unchanged; evidence tiers added (§8) |
| Costs (5 bp/$), drift-aware turnover | ALL | v2 unchanged |
| Bootstrap (6-month blocks, 5,000, seed 20261027) | ALL | v2 unchanged; 12-month blocks only for overlapping 12-month native scores |
| Data snapshots, hashes, run logs | ALL | v2 unchanged; model-call logs added for LLM |
| Asset universe SPY/IEF/LQD | TRACK_V | v2 unchanged |
| View interface: one-month excess-return Q for 3 assets | TRACK_V | New, written down from v2's implicit interface |
| BL allocator (P = I, τ, δ, prior, Σ, bounds); Ω from AP1 development errors | TRACK_V | v2 unchanged |
| Forecast metrics; Holm family | TRACK_V | v2 metrics unchanged; family redefined (§9) |
| Ridge algorithm, scaling, alpha grid, inner CV, purge, 48-label minimum, t−2 labels | RIDGE | v2 unchanged |
| Feature columns | RIDGE / SPECIFIC | AP1: 8. AP3 and controls: 8 + 2·N_ch |
| Point-in-time corpus snapshot and publication filter | LLM | New; identical for all LLM systems where they use documents |
| Masked-replay rules and probes | LLM | New |
| Model ID, parameters, run count R, seeds | LLM | Identical within AP3/AP3-STD/AP3-RG; logged for all |
| Native allocation (committee BL, JEV tilt), native universe, 40–80% band, native confidence → Ω | SPECIFIC | Preserved as built for Track N |
| Raw input signals | SPECIFIC | May differ; must be point-in-time and logged |

## 6. Approach 1 and 3: what is identical

AP3 and its controls use **exactly** the AP1 pipeline from `stage2_frozen_config_v2.json → forecast_model`:

- separate Ridge per asset, unpenalized intercept, expanding outer window;
- 48-label minimum, monthly refit;
- training-fold scaling (ddof 0), missing → 0 after scaling;
- inner expanding one-step CV with 36-label minimum, 1-month purge, stride 1, MSE loss;
- alpha grid `1e-4 … 1e10, INTERCEPT_ONLY`, ties to stronger shrinkage;
- the t−2 label rule.

Only the columns differ, and the coefficients and selected alphas may differ as a result. The canonical scorer (`stage2_backtest.py`, adopted 2026-10-27) is the reference implementation. Adding the AP3 columns will be an approved code change, not a re-implementation.

## 7. Feature-count and information-budget control plan (Deliverable 5)

### 7.1 Ridge-based systems (Track V): exact model columns after encoding

| System | Role | Columns | Schema |
|---|---|---|---|
| **AP1** | Baseline (= v2 System A, unchanged) | **8** | 8 macro-surprise z-scores (v2 §4) |
| **AP3** | Causal RAG (CauseTrace) | **8 + 2·N_ch = 16** with the proposed N_ch = 4 | AP1's 8 columns + for each causal channel c ∈ {Growth, Inflation, Policy/rates, Risk/credit}: `c_supported` ∈ {0,1}, `c_contradicted` ∈ {0,1}; *Insufficient* is the reference (both 0) |
| **AP3-STD** | Matched standard-RAG control (successor of v2 C) | **16** | Same channel names, same two indicators, same LLM/corpus/cutoff/doc count/token budget/R/seeds; retrieval not guided by the graph |
| **AP3-PERM** | Capacity placebo | **16** | AP3's frozen 8 agent columns with the month index permuted jointly across the 8 columns (M = 200 permutations, seed 20261027). No month may receive labels from within ±3 months of itself, so the placebo can't carry adjacent-month information. No new LLM calls |
| AP3-RG (optional) | Graph-structure placebo (v2 D0) | 16 | Same as AP3 with a rewired graph that keeps node count, edge count and degree sequence |
| AP3-NR (diagnostic) | No retrieval | 16 | LLM labels channels from the prompt alone. This is a contamination probe, not a candidate system |

Encoding rules (frozen with AP3):

1. **Unit of assessment: one (month, channel).** At each decision time the agent labels each channel from the information available then. Per-event outputs (as in the MVP) are aggregated to the month by a predeclared rule. Proposed rule: label the month from all releases and documents in (t−1 decision, t decision], not per event.
2. **Labels.** Three states only: Supported / Contradicted / Insufficient. A fourth state such as "Mixed" or "conflict" would add a column per channel, so it must be decided now (Blocker B4).
3. **Repeated runs.** R = 5 runs per (month, channel). The primary encoding is the majority-vote indicator, with ties counted as Insufficient. Run shares (`share_supported`, `share_contradicted`) are a robustness encoding with the same column count.
4. **No arbitrary scores.** No +1/0/−1 code (the MVP's `code` field is not used), no LLM self-reported confidence, no BM25 score.
5. **No interaction terms in Primary.** The 2026-09-30 design note proposes Shock × AgentSignal terms. With N_ch = 4 that adds 32 columns, giving 48 columns against 48 initial training labels. Interactions are a separate pre-registered experiment (AP3-INT) with its own permutation placebo, never a replacement for AP3.
6. **Same Ridge pipeline as AP1.** Scaling uses training-fold mean/std, ddof = 0, and missing values become 0 after scaling. The same alpha grid, inner CV, purge, 48-label minimum and t−2 label rule apply. Binary columns are scaled like any other column. A column that is constant in a training fold (e.g. a channel never "Contradicted" in the burn-in) gets std = 1 (`fit_scaler`, `stage2_backtest.py:714`). Its centred training values are then all 0, so its Ridge coefficient is exactly 0 and it contributes nothing to that fold's forecast. This is existing scorer behaviour. A unit test for this case must be added before freeze.
7. **Missing months.** If the agent can't run for a month, the channel columns are missing and become 0 after scaling. Missingness is logged, and > 5% missing months is a stop condition.

Why N_ch = 4 and not the MVP graph:

- The MVP graph has 2 equity-only pathways for one retail-sales event, and has no Treasury or credit nodes.
- A Track V feature must be defined every month and be relevant to all three asset models.
- The four channels match the design note's "Growth, Inflation, Policy, Risk" plan. The final list is Blocker B4.

### 7.2 What makes an AP3 improvement attributable to causal reasoning

| Comparison | Isolates | Status |
|---|---|---|
| AP3 vs AP1 | Value of the 8 agent columns over macro surprises alone | Primary H1 |
| AP3 vs AP3-STD | Value of graph-guided ("causal") retrieval at matched columns, corpus, model and budget | Primary H2 |
| AP3 vs AP3-PERM distribution | Whether the AP3 vs AP1 gain exceeds what 8 extra uninformative columns of the same distribution produce under the same Ridge tuning | **Gate on H1**: the AP3 − AP1 loss improvement must exceed the 95th percentile of the 200 placebo improvements |
| AP3 vs AP3-RG | Whether the specific graph matters | Secondary (if built) |
| AP3-NR vs AP3 | How much comes from parametric memory without evidence | Contamination diagnostic only |

A claim that "causal reasoning improved forecasts" needs all three of: H1 significant after Holm, H1 passing the placebo gate, and H2 significant. If only H1 holds, the claim is limited to "LLM evidence features added information". If H1 holds and the gate fails, the result is capacity noise.

### 7.3 Information budget (equal between AP3 and AP3-STD; logged for every LLM system)

The following are frozen and equal between AP3 and AP3-STD:

- documents eligible (same corpus snapshot and cutoff filter);
- retrieved chunks per (month, channel), proposed 4;
- total tokens per call, capped at the same limit;
- calls per (month, channel): R = 5;
- model ID and parameters;
- output schema.

The MVP's ordinary arm used one broad query of 20 chunks in a single call, while its graph arm used 5 × 4 chunks across 5 calls. That gives the arms different call structures, which v3 forbids. AP3-STD must use the same number of calls and chunks per channel, with a non-graph query.

### 7.4 Agent Committee and JEV: inputs vs outputs are counted separately

| | Raw inputs (may differ by approach) | Output views (must match to enter Track V) |
|---|---|---|
| Record for every system | Number and list of input series, documents per decision, tokens, model ID | Number of views, type (expected excess return / probability / tilt), asset coverage, horizon, units, confidence representation |
| Current AP2A | Live: 7 raw series; historical replay: 6 raw series as 17 numbers | 2 views (SPY, TLT), 12-month total return %, categorical confidence |
| Current AP2B | 6 raw series as 17 numbers (per README) | 1 probability (12-month SPY > TLT) + 5-option distribution + confidence; no return views |
| Track V requirement | Point-in-time, logged; no equality required | 3 absolute views (SPY, IEF, LQD), 1-month horizon, decimal excess return over T-bill, one set per month-end decision |
| Native track (N) | As built | As built, documented, never converted |

**Must be equal** inside Track V:

- output type, assets, horizon and cadence;
- the allocator and its Ω;
- costs, dates and scoring.

**May differ:**

- raw inputs, model class and internal reasoning (these are the approach);
- native allocation, in Track N only.

**Needs a separate experiment:**

- equalising the information set across the LLM approaches (a common point-in-time "information packet" study);
- view horizon (12-month vs 1-month);
- the JEV probability-to-return question, which is out of scope unless the team defines a calibrated mapping before any test data are seen.

## 8. Historical LLM leakage protocol (AP2A, AP2B, AP3 and its controls)

Masking reduces explicit cues but does **not** remove contamination. An LLM whose training data cover a period can recall or infer what happened from the context itself (rate levels, a pandemic, named officials) even when dates are hidden. Masking is a mitigation; it is not a remedy, and no historical LLM result is called clean because of it.

### 8.1 Evidence tiers (every LLM output is tagged with exactly one)

| Tier | Definition | Use |
|---|---|---|
| **P — Prospective** | Generated before the decision timestamp it applies to, by frozen code, prompts, corpus snapshot, knowledge graph and model ID, and logged with a timestamp that can't be edited | Clean evidence |
| **R-post — Retrospective, after the model's documented cutoff** | Replayed after the fact for a decision date later than the provider-documented training-data cutoff of the model used | Retrospective; least contaminated historical evidence; still not clean, because undocumented training data and later fine-tuning are possible |
| **R-pre — Retrospective, before the cutoff** | Replayed for a decision date on or before the documented cutoff | Diagnostic only |

AP1 is deterministic and has no LLM tier. Its historical results carry only the disclosure that the 2023–2026 window was partly inspected by the earlier MVP.

**What this means for the models in use today:**

- **gpt-4o** (Agent Committee) has a documented cutoff of October 2023 (OpenAI model documentation, as compiled by third parties; to be confirmed and recorded from the provider page at pinning time). Treating the cutoff month as R-pre, 2023-01..2023-10 would be R-pre and 2023-11..2026-08 R-post (34 decisions). That holds only if the exact snapshot can still be pinned.
- **claude-sonnet-5-5** (CauseTrace MVP) has a training cutoff after the window, so the whole historical window would be R-pre.
- **typesafe/jev** has no recorded model version or cutoff, so its 272 saved answers are R-pre by default.
- The development window (2019-03..2022-12) is R-pre for all of them.

### 8.2 Point-in-time inputs

- Every input row and every document has `available_at` (first publication), and the rule `available_at <= decision_time` is applied in the data-access layer, not in the prompt.
- Macro data are first prints. Consensus is the pre-release Bloomberg median (unchanged from v2).
- The news/policy corpus is a frozen, hashed snapshot. Each document keeps its first-publication timestamp and the version archived at that time. Documents edited later, updated live pages and undated sources are excluded.
- Retrieval indices are filtered per decision date. The same filter applies to every LLM approach.
- EPU/GPR are revised vintages (as `macro_indexes.py` acknowledges). They may stay in the native AP2A/AP2B systems with that disclosure, but they may not enter any Track V system unless point-in-time vintages are obtained.

### 8.3 Masked historical replay (R tiers only)

- Absolute dates in prompts and retrieved text are replaced by relative markers ("current month", "t−1"). Prompts give no calendar year.
- Numeric context (levels, surprises, yields) is kept, since it is the information content. That means the period may still be identifiable, which is why masking is not claimed to remove contamination.
- An unmasked replay of a fixed subsample is run as a diagnostic. Large masked-versus-unmasked differences are reported as evidence of recall.
- Entity masking (names of officials, firms) is optional. If it is used, it is the same for every LLM approach.
- The existing committee replay re-inserted tickers and the cash level after masking. That must be corrected, or disclosed as "partially masked", for any AP2A rerun. The year-guess and sign-flip probes must be run on the prompts actually used. Today they exist only for the single-call gpt-4o payload.

### 8.4 Model identity and run logging (mandatory, all LLM calls)

Each call logs:

- the provider and the exact model ID string;
- the provider snapshot/version date and the provider-documented training-data cutoff;
- temperature, top_p, max tokens and seed (where supported);
- SHA-256 of the system prompt, user prompt and retrieved context;
- the call timestamp (UTC), SHA-256 of the raw response, the parse status, and the run index (1..R).

Caches are keyed by (prompt hash, model ID, parameters) and are append-only. Changing the model ID creates a new system version; it is never a silent substitution.

Today only the requested alias string is logged, for both gpt-4o and claude-sonnet-5-5, and nothing at all is logged for JEV. None of the existing saved LLM outputs meet this standard. They are admissible as R-pre diagnostics only.

### 8.5 Point-in-time knowledge graph (AP3)

- Every node and edge carries a source citation with a publication date.
- For decision date t, only edges whose supporting source was published on or before t may be used.
- Simplest compliant design: freeze one graph built only from literature published before the first training label (2015-02). It is then valid for every date.
- Any edge added later carries its date and is masked out of earlier decisions.
- The graph file is hashed. Rewired-graph placebos keep the node count, the edge count and the degree distribution.
- The MVP graph's authorship (by an agent that knew post-2023 outcomes, with a post-hoc redefinition of edge E1) is disclosed. It is not reused as the AP3 graph.

### 8.6 Testing Agent access limits (AP3)

- The Testing Agent may query only data with `available_at <= decision_time` through the same access layer.
- It may not read realized returns of the holding period it informs, any label after t−2, scoring outputs, evaluation results, or the sealed-window files.
- Any statistic it fits on returns uses labels through t−2 only (the v2 label rule).
- Its queries are logged and audited. A query outside the window invalidates that month's output.
- It may not use the forecast target (SPY/IEF/LQD excess returns) to decide which hypothesis is "supported" at time t.
- The MVP has no Testing Agent, and its assessment step sees only pre-cutoff excerpts. These limits apply to the component when it is built.

### 8.7 Reporting

- Tables report the P, R-post and R-pre tiers separately and never pool them.
- Confirmatory language is reserved for tier P. It is also allowed for tier R-post only if the team approves that tier in advance (Blocker B3).
- All historical LLM results carry the label "retrospective; knowledge-cutoff contamination possible".

## 9. Evaluation, multiplicity and the historical test

### 9.1 Primary family (Track V, forecast accuracy; Holm 5%)

- **H1:** AP3 vs AP1, gated by the AP3-PERM placebo (§7.2).
- **H2:** AP3 vs AP3-STD.
- **H3** *(only if AP2A-1M is approved and frozen before any scoring)*: AP2A-1M vs AP1.

All three use v2's primary loss: the normalized pooled squared-error differential, equal-weighted across SPY/IEF/LQD, normalized by the expanding realized variance through t−2. The paired circular block bootstrap is unchanged. Relative MSPE, OOS R², RMSE and MAE are reported. Directional accuracy and cross-asset ranking accuracy are descriptive.

v2's family {B-All vs A, C vs A, D vs C} is retired:

- B-All vs A is paused.
- C vs A has no v3 counterpart, because standard RAG becomes a control.
- D vs C maps to H2.

### 9.2 Secondary

- Track V portfolio metrics for every Track V system (v2 secondary list and benchmarks).
- Track N active CER and the full native metric set.
- AP2A and AP2B native forecast scores (§4.3).
- AP1 vs the historical-mean forecast benchmark (baseline validity).
- No p-values are emphasised for secondary results. If any are, they are Holm-corrected within their own family.
- Event and regime analysis remains diagnostic only.

### 9.3 Evidence windows

| Window | AP1 | LLM-based systems |
|---|---|---|
| Development 2019-03..2022-12 | Development (already run; canonical) | R-pre for every model above. Build and debug only |
| Historical 2023-01..2026-08 | Retrospective. Partly inspected by the earlier MVP (disclosed) | R-pre or R-post depending on the pinned model's documented cutoff (§8.1) |
| Prospective (first month-end after the v3 freeze and every generator freeze) | Prospective | **P: the only clean LLM evidence** |

### 9.4 Status of the historical test

- The window stays **sealed** (`stage2_historical_test_gate_v5_2026-10-27.json`).
- The v2 readiness record (gate v4) applied to v2's A/B design. v3 retires that design, so v4's "ready for GO decision" is superseded. The v2 data gates themselves (risk-free, dividend adjustment, panel, hashes) remain valid evidence.
- Opening requires all of the following:
  - v3 approved;
  - the AP3 / AP3-STD / AP3-PERM generators (and AP2A-1M if approved) built, tested and frozen with hashed snapshots;
  - TLT pinned and checked for Track N;
  - a single scripted run that scores every system at once.
- Opening AP1 alone earlier is possible but not recommended. It would reveal the window's realized returns while prompts, the graph and the schema are still being designed (B6).
- Power is limited. v2 development (46 months) gave wide intervals. A 34-month R-post window (gpt-4o case) is shorter still. Effect sizes with intervals must lead the reporting.

## 10. Paused conventional-signal research

- B1–B5 and B-All (credit level, credit 3M change, 10Y−3M curve, VRP proxy, 12-month momentum) are paused. Their code, data snapshots, manifests and development results are preserved unchanged as archived supplementary research.
- They will not be run, optimised, selected, ranked or expanded.
- The current scorer computes v2 systems A and B together. No scorer run is needed until the v3 implementation is approved, and the approved implementation will restrict the system list (a proposed, not yet made, code change).
- Details: [pause record](Stage2_Conventional_Signals_PAUSE_2026-10-27.md).

## 11. v2 → v3 change log (Deliverable 3)

Full table: `stage2_v2_to_v3_changelog.csv` (retain / modify / pause / unresolved, each with a reason). Summary:

- **Retain (unchanged):**
  - universe; decision, execution, holding and target;
  - risk-free and price data, with gate-5 and FRED verification;
  - sample windows and the t−2 rule;
  - macro construction and AP1 = A;
  - the entire Ridge procedure;
  - BL parameters and Ω rule (Track V);
  - costs, turnover and benchmarks;
  - forecast loss and normalisation; bootstrap;
  - robustness list (minus paused B items);
  - data-integrity gates; amendment and bug-note policy;
  - canonical scorer and Ω file.
- **Modify:**
  - the freeze principle (§1);
  - system labels (§3);
  - the primary family (§9.1);
  - two tracks (§4) and native scoring (§4.3);
  - evidence tiers and the leakage protocol (§8);
  - an explicit AP3 schema in place of v2's open C/D interface (§7);
  - the prospective-start rule now references v3 generators;
  - historical-test readiness superseded (§9.4).
- **Pause:** B1–B5, B-All, B-specific data gates and robustness items (10Y−2Y, IG OAS, alternative VRP).
- **Unresolved:** see §13.

## 12. Work required before a v3 freeze (none of it done here)

1. **AP3 monthly generator:**
   - point-in-time corpus snapshot (2015-02 onward) with first-publication timestamps;
   - point-in-time 4-channel graph covering SPY/IEF/LQD-relevant channels;
   - monthly assessment, majority-vote encoding and logging;
   - AP3-STD with a matched budget;
   - AP3-PERM permutations;
   - unit tests: column count, encoding, constant-column behaviour, cutoff filter.
2. **Scorer change (after approval):**
   - system list = AP1, AP3, AP3-STD, AP3-PERM (+ AP2A-1M);
   - a feature-file interface for agent columns, with hash checks;
   - no change to Ridge, BL or metrics code paths.
3. **AP2A-1M (if B2 approved):**
   - re-specified output schema;
   - the parser fix carried over from `approach-2`;
   - full model logging and masking corrections;
   - masked-replay probes on the actual prompts.
4. **Track N:**
   - TLT pinning and a distribution check;
   - next-close re-scoring of the AP2A/AP2B saved answers;
   - a recorder with logging for prospective JEV runs (B7).
5. **Model pinning:** exact model snapshot IDs and documented cutoffs recorded (B3).
6. **Prospective logging harness:** outputs generated and hashed before each decision timestamp.

## 13. Blockers that need approval (Deliverable 7)

| # | Decision | Recommendation |
|---|---|---|
| **B1** | Adopt the two-track design: Track V (controlled, same frozen BL) as **primary**; Track N (native systems) as supplementary | Approve |
| **B2** | Bring the Agent Committee into Track V as **AP2A-1M**: same three agents, output re-specified to one-month SPY/IEF/LQD excess-return views, frozen BL and common Ω. The alternative is native-only (no H3) | Approve AP2A-1M **and** keep native AP2A in Track N |
| **B3** | **Evidence standard and model choice for LLM systems.** (a) Prospective-only confirmatory, historical diagnostic. (b) Pin a model whose documented cutoff precedes most of the window (e.g. a still-pinnable gpt-4o snapshot, documented cutoff Oct-2023, giving 34 R-post months), and treat R-post historical months as the pre-registered primary analysis, always labelled retrospective. (c) Accept R-pre historical results as primary. AP3 and AP3-STD must share the model in every option | (b) if a snapshot can be pinned with full logging, otherwise (a). Not (c) |
| **B4** | **AP3 schema:** N_ch = 4 channels (Growth, Inflation, Policy/rates, Risk/credit); 3 states, Insufficient as reference; majority vote of R = 5; monthly unit; no interactions in Primary. This gives 16 columns | Approve, or supply the channel list |
| **B5** | Track N universes: keep native SPY/TLT for AP2A/AP2B (cross-system raw metrics descriptive; active CER primary), or require SPY/IEF/LQD natively | Keep native; report active CER |
| **B6** | Keep the whole historical window sealed until every v3 generator is frozen (single opening), rather than opening AP1 now | Keep sealed |
| **B7** | JEV's 272 saved answers have no prompt, recorder or model version. Accept them as R-pre diagnostics only, and approve building a logged recorder for prospective JEV runs, or drop AP2B from prospective evaluation | Accept as diagnostic; build the recorder |

Until these are decided, the v2 freeze remains the last frozen design. The only change from it is that the B experiments are paused.
