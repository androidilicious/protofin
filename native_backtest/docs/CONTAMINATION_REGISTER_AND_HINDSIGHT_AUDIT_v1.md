# Contamination register and hindsight audit — draft for team sign-off (v1, 2026-10-28)

**Status: DRAFT.** This document collects what the repositories show about the approaches. It cannot sign itself. A GO record needs each section reviewed, corrected where the team knows more, and signed below.

The protected historical window is 2023-01..2026-08. The primary approaches are the Deterministic Quantitative Model, the Agentic Workflow represented by JEV, and Agentic Causal RAG. The Agent Committee is a within-approach variant.

## 1. Contamination register

| # | Approach | Source of contamination | Evidence in the repositories | Months affected | Mitigation in place | Residual risk | Team review |
|---|---|---|---|---|---|---|---|
| C1 | Deterministic | None from model memory (Ridge, no LLM) | — | — | — | Low | ☐ |
| C2 | Deterministic | Predecessor MVP committed realised returns | `main` deterministic MVP outputs include 2022-12..2026-09 (already disclosed in Stage 2 gate v5) | Protected window | Stage 2 System A is a separate frozen implementation; the evaluator lock keeps the window sealed | Design hindsight possible; see audit H1 | ☐ |
| C3 | Agentic Workflow (JEV) | Unknown model training data | JEV's model version, training cutoff, prompt and recording date are not stored; only parsed answers are saved (`site/data/jev_runs.json`, committed 2026-10-04) | All 272 months, including the protected window | Answers replayed exactly; labelled retrospective | **Cannot be assessed**: the answers were recorded after the fact, by a model of unknown cutoff | ☐ |
| C4 | Agentic Workflow (JEV) and Committee | Era cues in the input | The masked payload names SPY/TLT and shows the cash-yield level; EPU and GPR are today's revised histories | All months | Masking of dates (partial) | The period can be inferred from levels | ☐ |
| C5 | Committee (variant) | gpt-4o training data to October 2023 | OpenAI GPT-4o system card; year probe found 20.4% of guesses within ±1 year vs 13.0% chance, concentrated in 2020–2023 | Development and 2023 protected months | Masking (partial); variant only, outside the primary family | Material for months before November 2023 | ☐ |
| C6 | Causal RAG | Llama 3.1 70B training data to December 2023 (Meta model card) | Model chosen 2026-10-28; not yet run | Development and 2023 protected months | Year-filtered graph vintages; text scan for later events; documents filtered by publication time; quotes must match supplied documents; the no-retrieval diagnostic (secondary) measures memory without evidence | Present for months before 2024; not yet measured | ☐ |
| C7 | All | Data revisions | EPU/GPR revised (C4). Point-in-time status of each macro-surprise vintage is recorded in the Stage 2 audit | As listed | Stage 2 canonical panel and gates | As recorded in Stage 2 | ☐ |

## 2. Hindsight audit

Each item asks whether a design choice could have been informed by protected-window outcomes. The team answers, with names and dates.

| # | Question | What the repositories show | Team answer |
|---|---|---|---|
| H1 | Has anyone on the team seen protected-window performance of any approach? | Yes for the AP2 systems. Their authors scored the full 2004–2026 range: `research/out/backtest_summary.csv` and `research/out/jev_backtest.json`, committed 2026-10-04, and the public backtest pages. The deterministic MVP on `main` committed realised returns for 2022-12..2026-09 | ☐ who, what, when |
| H2 | Was the choice of JEV as the primary Agentic Workflow system informed by those results? | Roles were set on 2026-10-28, after the full-range results above existed. The Committee and JEV development diagnostics do not differ significantly (+0.44 pts, p = 0.72). Analysis, bound (about 0.5 pts net CER if chosen on the window alone) and pre-registered reporting rules: `SELECTION_BIAS_AGENTIC_WORKFLOW_2026-10-28.md` | ☐ rationale recorded, and confirmation that protected-window results did not drive it |
| H3 | Were the primary contrasts, metric (net CER, δ = 2.5), costs, timing and windows fixed before any protected-window scoring by this framework? | Set in `framework_config_v1.json`; the evaluator has never scored a protected month (lock enforced; NO-GO records v1 and v2) | ☐ |
| H4 | Were fitted parameters set on development data only? | Deterministic: frozen Stage 2 v2 configuration (Ω from development errors). Agentic Workflow: no fitted parameters (native settings unchanged). Causal RAG: limits and concepts locked 2026-10-28 before any model run; calibration is walk-forward | ☐ |
| H5 | Were any inputs, prompts or universes changed after viewing results? | Native AP2 prompts, universes and allocators are unchanged (byte-identical vendored code). TLT added to the calendar without moving any Deterministic date | ☐ |
| H6 | Are there other analyses of 2023–2026 performance (slides, notebooks, the October 23 deck) that informed the design? | Not in the repositories | ☐ |

## 3. Sign-off

| Name | Role | Sections reviewed | Decision (accept / accept with changes / reject) | Date | Signature |
|---|---|---|---|---|---|
| | | | | | |
| | | | | | |
| | | | | | |

When signed, add the signers to the GO record's `signed_by` field. The register is then frozen with the GO record.
