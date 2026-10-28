# Audit of the backtest-plan diagram against the `backtest` branch (2026-10-28)

The diagram is treated as a conceptual reference. Each element was checked against the frozen Stage 2 methodology (`stage2/methodology/Stage2_Backtest_Freeze_v2.md`, `stage2/config/stage2_frozen_config_v2.json`), the native framework (`native_backtest/config/framework_config_v1.json`, `system_manifest_v1.csv`), the code and tests, the MVP and the GO/NO-GO record.

**Status classes**

| Class | Meaning |
|---|---|
| **Tested** | Implemented and tested |
| **Awaiting validation** | Implemented, awaiting validation |
| **Planned** | Planned, not yet implemented |
| **Blocked** | Blocked by an external dependency |
| **Paused** | Implemented, then put on hold by a recorded team decision. Not a planned item; resuming it needs a new decision |

## 1. Implemented / Missing / Needs correction

### Panel 1: the primary backtest

| Diagram element | What the branch has | Class | Verdict |
|---|---|---|---|
| Three primary approaches | `research_design.primary_approaches` = Deterministic, Agentic Workflow (JEV), Causal RAG; three primary contrasts, one Holm family; MVP shows exactly three; tests enforce all of this | Deterministic and JEV: Tested. Causal RAG: Awaiting validation | Correct |
| Deterministic: "rule-based model … Black–Litterman" | Ridge regression on 8 macro-surprise z-scores; expanding window refit monthly on labels through t−2 (minimum 48); Black–Litterman, 45/35/20 prior | Tested (native rerun byte-identical) | **Correct the wording.** It is a statistical model with fixed rules, not a rule-based model |
| JEV: "LLM-based strategists … 12-month views" | One AI decision model, asked monthly whether stocks beat bonds over 12 months: probability, five-way tilt, confidence. Its 272 saved answers are replayed exactly; its model version, prompt and recorder were not saved | Tested (replay only; cannot be re-created) | **Correct the wording.** "Strategists" describes the Agent Committee |
| Causal RAG: "knowledge graph, hypothesis testing, LLM agents" | Graph vintages, Hypothesis Agent with CauseTrace tools, Testing Agent, mediator tests, calibration, Black–Litterman. Run end to end only with the engineering mock | Awaiting validation. Blocked by inference approval, the evidence corpus and fed funds futures data | Correct. The MVP must not imply any result |
| Time period "2011-01 to 2026-08" | The research timeline starts 2015-02. 2011-01..2015-01 appears only as an Agentic Workflow native-fidelity diagnostic, outside the timeline and the dashboard | — | **Needs correction** (§2) |
| Test "2024-01 to 2026-08" | Frozen protected window **2023-01..2026-08**, one window | — | **Mismatch with the frozen methodology; decision needed** (§2) |
| Monthly decision dates (last trading day) | 20:00 ET on the last *common* trading day of the month | Tested, frozen | Add 20:00 ET |
| Execution at the next day's close | Close of the first common trading day after month-end; held to the next such close | Tested, frozen | Correct |
| Transaction cost 5 bp per dollar traded | 0.0005 per dollar traded, drift-aware, starting from cash, also charged to the benchmarks | Tested, frozen | Correct |
| Cash: 4-week T-bill (DTB4WK) | DTB4WK quote at entry, accrued over the exact calendar days | Tested, frozen | Correct |
| "Compound Annual Return (CER)" | Net CER = **certainty-equivalent return** = 12 × (mean monthly net excess − ½ × 2.5 × variance) | Tested | **Needs correction**: CER is not a compound annual return |
| Sharpe, maximum drawdown, volatility, turnover | Computed by the shared evaluator | Tested | Label them as secondary metrics |
| Benchmark-relative results | Each approach against its own static mix (45/35/20 or 60/40), using a paired bootstrap | Tested | Note that the benchmarks differ by approach |
| *(missing)* Significance testing | Paired circular block bootstrap (6-month blocks, 5,000 replications, seed 20261027); Holm across the three primary contrasts | Tested | **Missing from the diagram** |
| *(missing)* Point-in-time controls | Evaluator lock on the protected window; `available_at` on every AP3 input; graph vintages; vintage-aware mediators | Tested (AP3 inputs: Awaiting validation) | **Missing from the diagram** |
| *(missing)* Development vs protected vs prospective | Development 2019-03..2022-12 = diagnostics; protected window sealed; prospective after the freeze | Tested | **Missing from the diagram** |

### Panel 2: within-approach experiments (secondary; never in the primary family)

| Diagram element | What the branch has | Class | Verdict |
|---|---|---|---|
| Deterministic base model (8 macro surprises) | Stage 2 System A = AP1 | Tested | Correct |
| "Individual signals: add one signal at a time" | Stage 2 B1–B5: Baa−10Y level, its 3-month change, 10Y−3M slope, VRP proxy, 12-month momentum. Code and development runs exist. **Paused and archived on 2026-10-27**: not to be run, ranked or reported, and not scored in the protected window | **Paused** | Show as paused. Resuming them as a within-approach experiment needs a team decision |
| "Signal sets (e.g. 3, 5, 8 signals)" | No such design exists. The only defined set is B-All = the 8 macro surprises + all five financial signals (also paused) | — | **Needs correction** |
| "Market regimes (pre/post 2020, high/low volatility)" | Proposed; no regime definitions are registered | **Planned** | Define regimes before scoring, from information available at each decision. A date split is fine; a volatility regime needs a lagged, pre-set threshold. Regimes apply to every approach's results |
| Agentic Workflow: Agent Committee only | 272 native runs reproduced exactly; development diagnostics; compared only with JEV | Tested | Correct |
| Agentic Workflow: JEV only | The primary Agentic Workflow system | Tested (replay only) | Correct |
| Agentic Workflow: Committee + JEV | No combination rule; nothing built | **Planned** | The rule must be pre-registered before any protected month is seen |
| Causal RAG: full Causal RAG | As above | Awaiting validation; blocked | Must not appear as run |
| Causal RAG: Standard RAG | Defined in the v3 proposal: graph routing replaced by flat similarity, everything else matched (model, corpus, budget, runs) | **Planned** (needs genuine Causal RAG results first) | Correct |
| Causal RAG: "ablation tests (graph, testing agent …)" | The v3 proposal defines specific controls: no retrieval (contamination probe), rewired graph, permuted agent columns (capacity placebo), raw mediators without causal routing. "Remove the testing agent" is not a defined ablation | **Planned** | **Needs correction**: replace with the defined controls |
| Causal RAG: "model variants (settings, calibration)" | Not defined. One model is chosen (Llama 3.1 70B, temperature 0); calibration is walk-forward and fixed | **Planned** (to be defined) | Keep the set small and pre-register it |

## 2. Timeline, and the PPI and AHE question

**Frozen dates** (Stage 2 freeze §3, `stage2_frozen_config_v2.json` `sample`, `framework_config_v1.json` `windows`, evaluator lock, GO record v2):

| Phase | Frozen | Your list | Match |
|---|---|---|---|
| Training / burn-in | 2015-02..2019-01 for the 48 initial labels; the first scored forecast is 2019-03, so the shown phase runs Feb 2015 – Feb 2019 | Feb 2015 – Feb 2019 | Yes |
| Development and walk-forward validation | 2019-03..2022-12 | Mar 2019 – Dec 2022 | Yes |
| 2023 | Part of the protected historical test | Secondary period with contamination limits | **No** |
| Protected retrospective test | 2023-01..2026-08, one sealed window | Jan 2024 – Aug 2026 | **No** |
| Prospective | After the freeze | After the freeze | Yes |

**The 2023 / 2024 split is not in any frozen file. I have not changed it.**

The rationale is consistent with the contamination register:
- Llama 3.1 training data runs to December 2023.
- GPT-4o's runs to October 2023.
- JEV's cutoff is unknown.

Adopting the split changes the protected test, so it needs your explicit approval and must be written into the freeze before GO. Consequences:
- The primary window shrinks from 44 to 32 months, so intervals are about 17% wider (√(44/32)).
- 2023 needs a stated role: reported descriptively, or as its own family.
- One common window must apply to all three primary contrasts.

The MVP shows the frozen window, marks 2023 as "model-knowledge overlap", and lists the split as "proposed, awaiting decision".

**PPI and AHE: no evidence that the start must move to 2016.**
- The BLS made PPI Final Demand the headline index with the January 2014 data, released in February 2014 ([BLS TED, 2014-02-27](https://www.bls.gov/opub/ted/2014/ted_20140227.htm); [PPI release, 2014-02-19](https://www.bls.gov/news.release/archives/ppi_02192014.htm)). The panel's first PPI surprise is 2015-02, twelve months later.
- All-employee average hourly earnings were published experimentally from 2008 and officially from 2010 ([BLS Monthly Labor Review, March 2010](https://www.bls.gov/opub/mlr/2010/03/art4full.pdf)). The panel's first AHE surprise is 2011-03.
- From 2015-02 both definitions are constant. That is why the freeze calls 2015-02 the start of "balanced same-definition macro history".
- **Caveat.** The panel's construction code and raw consensus and actual values are not in the repository (only z-scores, pinned by hash). So the standardisation rule (apparently a 12-release history) and any consensus-source change during 2015 cannot be checked from code.
- **Recommendation.** Keep 2015-02 and obtain the panel builder or source export to close this check. A later start would change the Deterministic model's frozen training sample and needs approval.

## 3. Shared settings: frozen, awaiting approval, or different by design

| Setting | Status | Where |
|---|---|---|
| Decision at 20:00 ET, last common trading day; execution at the next common trading day's close; one-month holding | **Frozen, shared** | Stage 2 freeze; `framework_config.timing`; enforced by the evaluator |
| 5 bp per dollar traded, drift-aware, also on benchmarks | **Frozen, shared** | `costs` |
| Cash DTB4WK, exact-day accrual | **Frozen, shared** | `timing.cash` |
| Development 2019-03..2022-12; protected 2023-01..2026-08; lock with signed GO and token | **Frozen, shared** | `windows`; `framework/lock.py` |
| Net CER (δ = 2.5) primary; Sharpe, volatility, maximum drawdown, turnover, excess return secondary | **Implemented; awaiting final approval**. The Stage 2 freeze makes *forecast accuracy* primary and allocation secondary. JEV and the Committee produce no 1-month return forecasts, so the three-approach framework uses net CER | `research_design.primary_metric` |
| Paired block bootstrap (6 months, 5,000, seed); Holm over the three primary contrasts | **Frozen, shared** | `metrics` |
| Benchmark-relative comparison (each approach vs its own static mix) | **Implemented, shared method; benchmarks differ by design** | development report `vs_own_neutral` |
| Primary family of three, roles of JEV and the Committee | **Implemented; awaiting sign-off** with the GO record (selection-bias rules drafted) | `research_design`; selection-bias document |
| Point-in-time controls | **Shared principle; implementation differs by design**. Deterministic: point-in-time macro panel, labels through t−2. Agentic Workflow: masked inputs, but outputs recorded after the fact (contamination C3). Causal RAG: `available_at` filters, graph vintages, vintage-aware mediators | Code; contamination register |
| Walk-forward | **Differs by design**. Deterministic: monthly refit, expanding window. Agentic Workflow: nothing fitted (replay). Causal RAG: walk-forward calibration and year−1 graph vintages | Code |
| Assets, horizon, information, allocator, benchmark mix | **Differ by design**: SPY/IEF/LQD at 1 month vs SPY/TLT at 12 months; 45/35/20 vs 60/40 | `system_manifest_v1.csv` |
| TLT price check (gate 5) | **FAIL preserved**; NAV robustness analysis to be pre-registered; disposition awaiting team sign-off | `TLT_DISTRIBUTION_CHECK_2026-10-28.md` |

## 4. Components and safeguards the diagram leaves out

1. **Which metric is primary.** The Stage 2 freeze (forecast accuracy) and the three-approach framework (net CER) need one signed choice for the GO record.
2. **Causal RAG placebo controls.** Permuted columns (proposed as a gate on any Causal RAG gain), rewired graph, and no retrieval (contamination probe). They are in the v3 proposal but in neither the diagram nor the framework config until this change.
3. **JEV's protected-window answers were recorded in October 2026** by a model of unknown cutoff (contamination C3). JEV cannot run prospectively without its prompt and model (prospective gate 7).
4. **Selection bias from choosing JEV after full-range results existed.** Bound about 0.5 points of net CER; reporting rules drafted.
5. **Statistical power.** Development intervals for paired net-CER differences were about ±4 points. Pre-register that "not significant" means "not enough evidence", and report the minimum detectable effect for 44 (or 32) months.
6. **Cost and timing sensitivity.** Costs of 0/2/10/25 bp and an alternative execution day are in the Stage 2 robustness list. Apply them to all three approaches as secondary analyses.
7. **Ex-ante regime definitions**, and a **pre-registered Committee + JEV rule**.
8. **Prospective data feeds.**
   - Deterministic: live consensus surprises. The consensus source is not in the repository.
   - Causal RAG: a live document feed and the futures export.
   - JEV: none available.
9. **The paused Stage 2 signal experiments must not be reported.**
10. **Mock separation.** Already enforced: the evaluator refuses engineering-mock records, and the MVP labels the demo.
11. **The October 23 deck has not been reviewed** against the implementation (architecture check pending).

## 5. Exact changes

**Made in this change (non-methodological):**
- `framework_config_v1.json` (1.1 → 1.2): `research_design.within_approach_experiments` grouped by approach with status classes, matching §1. The scoring settings are unchanged.
- `system_manifest_v1.csv`: specific rows for the paused signal additions, regimes, Standard RAG, the Causal RAG controls and model/calibration variants, replacing the generic ablation row.
- `native_backtest/config/validation_status_v1.json`: the GO/NO-GO gate matrix in machine-readable form, used by the MVP.
- MVP:
  - The four sections (Overview, Approaches, Experiments, Methodology).
  - Experiments grouped by approach, with the status classes above.
  - Timeline from February 2015, with 2023 marked and the split flagged as proposed.
  - CER as certainty-equivalent return.
  - Settings tagged frozen / awaiting approval / by design.
  - No winner markers.
  - Development, sealed, unavailable and demo kept visually distinct.

**Needs your decision (not changed):**
1. The 2023 / Jan 2024 split of the protected window.
2. Net CER vs forecast accuracy as the primary metric.
3. Whether to resume the paused signal experiments as Deterministic within-approach experiments.
4. Regime definitions.
5. The Committee + JEV rule.
6. The Causal RAG control set and any model/calibration variants.
7. Keeping the 2015-02 start (recommended).

## 6. Challenges, completed

| Approach | Challenges | Mitigation in place / still needed |
|---|---|---|
| Deterministic | Signal stability across periods. Data-definition consistency: PPI Final Demand from 2014, all-employee AHE from 2010, so the panel starts 2015-02. Short training history (48 labels). Original Stage 2 scorer not saved (the reconstruction matches the base model). Same-month aggregation bug fixed. Ω estimated from development errors (development portfolios carry look-ahead in Ω) | Byte-identical native rerun; panel pinned by hash; walk-forward with t−2 labels; robustness list. Needed: the panel builder for the PPI/AHE check |
| Agentic Workflow (JEV) | Original model, prompt and recorder missing: replay only, no re-creation, no prospective run. Protected-window answers recorded after the fact. Contamination (unknown cutoff; era cues in inputs; revised EPU/GPR). Different universe (SPY/TLT) and 12-month horizon. Selection bias. TLT price check FAIL (C2). Hand-set tilt sizes | Exact replay; native-to-shared attribution; contamination register and selection-bias rules (unsigned); TLT diagnosis. Needed: TLT sign-off, register signatures, JEV access or a re-implementation decision for the prospective phase |
| Causal RAG | Historical evidence corpus not acquired (agency sites unreachable from the sandbox; browser workflow being prepared). Market data: fed funds futures pending; IG spread is a proxy. Model access: paid inference not approved; Llama 3.1 may be retired by providers. Validation: smoke run, fixtures, 95-month replay, human audit (κ ≥ 0.6), calibration. Contamination in 2023 (Llama data to December 2023) | Graph vintages; `available_at` filters; quote checks; three test runs; ALFRED-validated mediators; $5 smoke-test configuration ready. Needed: approvals, corpus, futures export, gates |
| All | Freeze and GO/NO-GO: contamination register and hindsight audit signatures; TLT disposition; Causal RAG gates; deck review; hashing and a second-machine dry run; signed GO record | GO record v2 = NO-GO; evaluator lock in force |

## 7. Remaining tasks, in priority order

1. **Decisions** (§5): window split, primary metric, TLT disposition, and Causal RAG inference approval A ($5 smoke test).
2. **Causal RAG data:**
   - Evidence corpus via the browser-assisted workflow.
   - Bloomberg fed funds futures export, then importer, inventory re-run and packets v3.
3. **Causal RAG validation:** smoke test, then approval B, then fixtures, 95-month development replay, human audit and calibration checks.
4. **Pre-registration of the secondary experiments:**
   - Committee + JEV rule.
   - Regimes.
   - Causal RAG controls (including the permutation gate).
   - Decision on the paused signals.
   - Cost and timing sensitivity.
   - Minimum detectable effect.
5. **Sign-offs and review:** contamination register and hindsight audit, selection-bias rules, October 23 deck review.
6. **Freeze:** hash everything, dry-run on a second machine, sign the GO record, then open the window once.
7. **Prospective plan:** data feeds per approach, and the JEV access decision.
