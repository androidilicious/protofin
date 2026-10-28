# Selection bias from choosing JEV as the primary Agentic Workflow system — 2026-10-28

**Issue.** On 2026-10-28, JEV was designated the primary system of the Agentic Workflow approach, and the Agent Committee became a within-approach variant. By then, both systems' complete historical replays, 2004–2026 (including the protected window 2023-01..2026-08), had already been computed and published by their authors. If the choice was influenced, even partly, by how the two looked over that period, the Agentic Workflow's retrospective result in the protected window is biased in JEV's favour. This document records the exposure, bounds the bias, and fixes, before the window opens, how retrospective and prospective results will be reported.

## 1. What was available, and when

| Date | What existed | Where |
|---|---|---|
| 2026-09 (README: "September 2026 run, 273 months") | Committee full-range replay with a published summary: 8.08% a year vs 8.30% for fixed 60/40, with four times the turnover. This summary covers 2004–2026, including the protected window | `README.md` on `main` and `approach-2` |
| 2026-10-04 | Committee and JEV full-range outputs and backtests committed | `approach-2 @ ce063b8`: `site/data/committee_runs.json`, `site/data/jev_runs.json`, `research/out/backtest_summary.csv`, `research/out/jev_backtest.json`; public pages `backtest.html`, `backtest-live.html`, `/jev/` |
| 2026-10-28 | Shared framework: protected window never scored (lock enforced; NO-GO records v1, v2). Development diagnostics only: Committee − JEV = +0.44 pts net CER (95% range −1.85 to +2.90, p = 0.72) | `native_backtest/out/development/` |
| 2026-10-28 | JEV designated the primary Agentic Workflow system | research-design update, `framework_config_v1.json` (`research_design`) |

This analysis did not open the JEV full-range file, the Committee backtest summary or the public backtest pages, so as not to add exposure. The Committee's full-range headline in the README is visible to anyone reading the repository. Who saw which results before the choice is for the team to record in the hindsight audit (items H1 and H2).

## 2. Why it matters, and how large it could be

Choosing one of several candidates partly on how they performed over a period, then evaluating the chosen one on that same period, inflates the expected result (the winner's curse). Here there are two candidates. They read the same masked market snapshot and trade the same assets around the same 60/40 benchmark, so their returns are highly correlated, and that limits the inflation.

**Bound.** If the choice had been made *only* on protected-window net CER, the expected inflation of the chosen system over the average of the two is about 0.40 × SD of the difference between them: E[max] − mean = σ_D / √(2π) for two candidates. On the 46 development months, that difference has a standard error of about 1.2 percentage points of net CER. A similar 44-month protected window gives an expected inflation of **about 0.5 pts of net CER**. That is an upper bound for selection on that window alone. It is smaller if the choice rested on other grounds; JEV is the approach-2 deliverable, and the Committee's model leaves the API on 2027-01-14.

Even so, 0.5 pts is the same order as the Agentic Workflow's development edge over its own benchmark (+0.31 pts). A retrospective protected-window advantage of that size could therefore be selection rather than skill.

## 3. Retrospective and prospective evidence are kept distinct

| | Retrospective (historical replay) | Prospective (live) |
|---|---|---|
| Months | Development 2019-03..2022-12 (diagnostics) and the protected window 2023-01..2026-08 (scored once, after GO) | Decisions after the freeze |
| How decisions were made | Saved outputs replayed (JEV, Committee) or re-run by frozen code (Deterministic, Causal RAG), after the outcomes were known | Generated and timestamped before the outcome, by frozen code, prompts, corpus and model ID, in a hash-chained log |
| Known exposures | Model training data covers the period (gpt-4o to Oct 2023, Llama 3.1 to Dec 2023, JEV unknown); era cues in inputs; authors' prior inspection of 2023–2026; **selection of JEV after that inspection**; design hindsight | Provider or model changes (checked with canary prompts) |
| What it can establish | How the frozen systems would have behaved historically, with disclosed biases. **Not** out-of-sample skill | Out-of-sample performance |
| Language in reports | "retrospective", "historical replay"; every JEV result carries the selection note below | "prospective", "live" |

Retrospective and prospective results are never pooled, never shown in one series, and never summarised by one number.

## 4. Pre-registered reporting rules (fixed before the window opens)

1. **Both variants, always together.** Every protected-window result for the Agentic Workflow shows JEV (primary) and the Committee (variant) side by side, scored identically.
2. **Selection note.** Every retrospective JEV result is labelled: "Agentic Workflow represented by JEV; the representative was chosen after full-range 2004–2026 replays of JEV and the Committee had been published. Retrospective; selection-exposed."
3. **Selection-robust sensitivity.** The primary contrasts involving the Agentic Workflow are also reported with the Agentic Workflow represented by:
   - the **less favourable** of JEV and the Committee in that window;
   - the **equal-weight average** of their monthly portfolio returns. This is an analysis device, not the proposed Committee + JEV system.

   If a primary conclusion holds for JEV but not under both alternatives, it is reported as selection-sensitive.
4. **Bound reported.** The ~0.5 pt selection bound (§2), recomputed on the protected window's actual Committee − JEV variability, is printed next to every retrospective Agentic Workflow contrast.
5. **No promotion from retrospective results.** A retrospective JEV advantage, over the Committee or over another approach, is not reported as evidence of superior skill.

## 5. Consequence for the prospective phase

The prospective test is the clean answer to this bias, but **neither Agentic Workflow system can currently run prospectively in native form**:

- JEV has no recorder, stored prompt or credentials in the repository, and its model version is unknown.
- The Committee's gpt-4o leaves the API on 2027-01-14.

Before the prospective phase, the team must either obtain pinned, logged access to the JEV model with its prompt, or record that the Agentic Workflow will be evaluated prospectively in a re-implemented (non-native) form, reported as a new version. This is added to the GO/NO-GO list as a prospective-phase gate. It does not block the retrospective GO.
