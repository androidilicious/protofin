# Dashboard redesign — content inventory and destination map (2026-10-29)

Audited before any edit, against `mvp/assets/app.js` at commit `e2b3f5a` (5 tabs, 10 views) and the 19 top-level
keys of `mvp/data/dashboard.json`. **Rule: no scientific content is removed.** Every item below has a destination;
nothing is marked "dropped". The redesign changes presentation and navigation only — no model, result, frozen
configuration, timestamp, accounting rule or statistical interpretation is recomputed or restated.

## Navigation: before → after

| Before (5 tabs) | After (8 sections) |
|---|---|
| Overview | **Overview** (shorter) + **Comparison** (the result tables and curves) |
| Approaches (3 detail views + Committee) | **Pipeline** (new, interactive) + **Comparison** + **Causal RAG** |
| Experiments | **Experiments** (explorer) |
| Signal Value-Added (6 steps) | **Signal Value** (5-step story) + **Sensitivity** (its own section) |
| Methodology | **Appendix** (categorised, searchable) |

## Item-by-item map

| # | Existing content | `dashboard.json` source | Destination |
|---|---|---|---|
| 1 | Research question, phase, headline finding | `notes.headline`, `notes.finding` | Overview — executive summary |
| 2 | Three approach cards, universes, roles | `systems`, `assets` | Overview — approach comparison |
| 3 | Committee as secondary variant | `variants` | Comparison + Experiments (never a fourth approach) |
| 4 | Know / not yet / can / cannot lists | `notes.know/not_yet/can/cannot` | Overview — completed vs pending |
| 5 | Phase strip (train / dev / sealed test / prospective) | `windows`, `methodology.phases` | Overview (compact) + Appendix — conventions |
| 6 | Growth-of-one-dollar curves | `dev.series`, `dev.months` | Comparison — primary chart |
| 7 | Net CER, Sharpe, vol, max drawdown, turnover, cost | `dev.series[*].metrics` | Comparison — headline metrics; full table in Appendix |
| 8 | Common SPY/IEF benchmark and its spec | `dev.common_benchmark`, `methodology.common_benchmark` | Comparison — reference line; spec in Appendix |
| 9 | Passive 60/40 panel, kept separate from the baseline | `dev.benchmarks` | Comparison — separate reference card |
| 10 | Primary contrasts, CIs, p-values, bootstrap | `dev.primary_contrasts` | Comparison — CI bars; full statistics in Appendix |
| 11 | Native-vs-common reconciliation | `native_vs_common` | Appendix — comparability |
| 12 | Reproduction hashes per approach | `reproduction` | Appendix — artifacts and reproducibility |
| 13 | Per-approach flow diagrams (4 stages) | `flows` | **Pipeline** — expanded to 6 stages with real values |
| 14 | Signals and features per approach | `systems[*].signals` | Pipeline — stage 2; detail in Appendix |
| 15 | Per-approach limitations | `systems[*].limitations` | Comparison cards + Appendix |
| 16 | Decomposition bars (native vs common) | `native_vs_common` | Appendix |
| 17 | Experiment groups and statuses | `experiments.groups` | Experiments — explorer |
| 18 | Committee-only vs JEV-only contrast | `experiments.within_contrast` | Experiments — expanded detail |
| 19 | Causal RAG status, graph, triggers, limits | `ap3` | Causal RAG — progress view |
| 20 | Causal RAG two versions | `ap3.versions` | Causal RAG |
| 21 | Causal RAG illustrative demo (labelled) | `ap3.demo` | Causal RAG — kept with its demo label |
| 22 | Exploratory gate-failed panel | `ap3_exploratory` | Causal RAG — exploratory, visually distinct |
| 23 | Validation gate matrix (14 gates × 4) | `validation` | Causal RAG summary + Appendix — full matrix |
| 24 | Portfolio integrity audit | `audit` | Signal Value — opening evidence; detail in Appendix |
| 25 | Signal Value experiments, CER bars, per-system curves | `signal_value.systems` | Signal Value — results |
| 26 | JEV gap attribution (mix vs signals) | `signal_value.gap` | Signal Value — interpretation; bars in Appendix |
| 27 | February 2020 influential month | `signal_value.influential_month` | Signal Value — caveat; detail in Appendix |
| 28 | Signal Value verification checks | `signal_value.checks` | Appendix — validation |
| 29 | Transmission chain, four scenarios | `sensitivity.systems` | **Sensitivity** — own section |
| 30 | Where each signal is lost (3 funnels) | `sensitivity.systems[*]` | Sensitivity — main visual |
| 31 | Scenario tables (CER, vol, turnover, cost, binding) | `sensitivity.systems[*].by_scenario` | Sensitivity — compact chart; full tables in Appendix |
| 32 | Correlation decomposition 0.971 / 0.984 / −0.279 | `sensitivity.similarity` | Sensitivity — interpretation |
| 33 | Sensitivity Causal RAG pending card | `sensitivity.ap3` | Sensitivity + Causal RAG |
| 34 | Rules and settings (14 frozen settings) | `methodology.settings` | Appendix — methodology |
| 35 | Pending methodology decisions | `methodology.pending` | Overview — pending; Appendix — detail |
| 36 | Glossary tooltips | in `app.js` | Retained throughout; collected in Appendix |

## New content (built from existing archived artifacts, nothing invented)

| New | Built from | Note |
|---|---|---|
| Pipeline stage values, AP1 | `stage2/.../stage2_portfolio_bl_diagnostics.csv`, `stage2_predictions.csv`, `model_scoring_panel_E4_meanrule.csv`, `ap1_transmission_trace.csv`, `ap1_scenario_returns.csv` | real archived month |
| Pipeline stage values, AP2B | `out/decisions/AP2B.jsonl`, `ap2b_transmission_trace.csv`, `ap2b_scenario_returns.csv` | real archived month |
| Pipeline stage values, AP3 | — | **no genuine development outputs**: stages shown as the implemented design, values marked pending |
| Appendix index | all of the above | categorised, filterable |
| Download Content package | `dashboard.json` + archived CSV/JSON | manifest discloses anything excluded |

## Excluded from the export, by rule

The sealed historical test window 2023-01..2026-08 (never computed, never exported), GitHub tokens and any
credential, raw claims-data text (redacted at source in the Causal RAG bundles), and files outside the repository.
The export manifest states each exclusion.
