# Approach 3 — Qwen3:4B Original Prompt Baseline (exploratory) — 2026-10-29

**The decision.** Run the complete Causal RAG development backtest on the current model and prompts **first**, and investigate reliability afterwards as a separate experiment. This record and `config/ap3_exploratory_mode_v1.json` were written before the run produced anything.

**What this is, and what it is not.**
- It **is** a reproducible end-to-end baseline: genuine Hypothesis Agent and Testing Agent outputs carried through CauseTrace, signal encoding, walk-forward calibration, Black–Litterman allocation and the shared evaluator.
- It is **not** validated. The pre-registered reliability gates G3a and G3b did not pass in run 1, and nothing here says they did. It is not evidence that the agents are reliable, and not evidence that AI adds investment value.

## 1. What is frozen

| | Value |
|---|---|
| Model | `qwen3:4b`, digest `359d7dd4bcda`, served by Ollama on the run machine (localhost only). A documented stand-in for Llama 3.1 70B |
| Prompts | Unchanged, and verified byte-identical to run 1: Hypothesis Agent `SYSTEM`, Testing Agent `PLAN_SYSTEM`, and the vendored assessor's `SYSTEM`, schema and quote validation |
| Limits, rubric, fixtures, gate thresholds | Unchanged, verified byte-identical to run 1 |
| Inference | Temperature 0.0 seed 0 (hypotheses); 0.3 with seeds 1, 2, 3 (testing, 3 runs); thinking off; per-step JSON schema; 32,768-token context |
| Agent protocol | 1.1, fingerprint recorded. 1.1 fixes **harness** defects found in run 1 — the missing final-answer turn, the agent's own replies returned as assistant turns, whole-word graph search, rival-id validation. No prompt, schema, limit, rubric, fixture or threshold is changed |
| Evidence | Reduced Evidence variant; point-in-time filtering for every month |
| Graph | 12 year-filtered vintages, each hashed |
| Windows | Agents 2015-02..2022-12; scored 2019-03..2022-12; protected 2023-01..2026-08 sealed |

Every item above is recorded with its SHA-256 in `config/ap3_exploratory_mode_v1.json` → `frozen_for_reproduction`, together with the code revision.

**Why protocol 1.1 and not run 1's code.** Under run 1's harness the agent never received its final-answer turn, so **every** month ended with no hypotheses. A backtest was impossible, not merely poor. The 1.1 fixes make the loop behave as its own rules already specified; they do not change what the model is asked.

## 2. The exploratory mode

The mode exists so the pipeline can be studied without pretending the gates passed.

**It permits** the development replay and its evaluation to run after a gate failure, when explicitly requested (`--exploratory`, or `AP3_EXPLORATORY=1`).

**It never permits:**
- changing gate definitions, thresholds, prompts, limits, the rubric or the fixtures;
- hiding a failed gate: every output carries the failed gates with their real values;
- scoring any month of the protected window — refused in this mode exactly as in every other;
- use as the confirmatory input: `historical_evaluation` now refuses any Causal RAG decision record carrying the exploratory mark, **even with a signed GO record**;
- treating engineering-mock output as a result, or filling in months that were never run.

Enforcement lives in one module, `native_backtest/ap3/exploratory.py`, so no output can lose the stamp: `stamp()` refuses to run when no gate actually failed, and refuses any month at or after the protected start.

**Exit codes.** `0` all gates passed; **`3` a gate failed** — including an exploratory run that completed the replay, because the gate did fail; anything else is an error. The notebook stops unless the code is 0 or 3.

## 3. Coverage, and what is never invented

A month whose agent fails keeps the system's existing failure policy: Insufficient, zero status features, and the allocator falls back to its prior. That is a recorded decision, not a fabricated one, and it is counted and displayed:

- scored months present, and how many produced at least one hypothesis;
- months with an agent failure, listed;
- hypotheses tested, failed tests, and the status distribution.

A partial replay is **never scored**: calibration needs the full 95-month history, so the import reports how many months exist and stops. No return, weight or forecast is ever estimated for a missing month.

## 4. The quantitative pipeline

Unchanged and native to Approach 3: Hypothesis Agent → CauseTrace → Testing Agent → signal encoding → walk-forward calibration (labels through t−2 only) → Black–Litterman allocation over SPY/IEF/LQD → the shared evaluator (same entry and exit closes, 5 bp per dollar traded, DTB4WK cash, start from cash). Calibration and allocation run at import in the pinned environment, not on the GPU machine, so the numbers do not depend on the notebook's libraries.

Reported, where valid: monthly net returns, cumulative return, net CER, Sharpe, volatility, maximum drawdown, turnover and costs, and the monthly weights.

## 5. Comparison, and its limits

The exploratory result is compared with the Deterministic baseline and JEV on the same 46 development months and the same accounting. Three cautions travel with every comparison:

1. The three approaches hold **different assets** and build portfolios differently, so a difference cannot be attributed to the agents.
2. These are development months, where the approaches were built and checked.
3. The Causal RAG side is **unvalidated**: its own reliability checks failed.

## 6. Dashboard

The Causal RAG page carries a visually distinct panel — dashed amber border, hatched background, a warning tag reading **EXPLORATORY — RELIABILITY GATES FAILED** — listing the failed gates with their real values. Until the replay finishes it shows progress and no curve. The exploratory series never enters the primary comparison, the approach cards or the Overview.

## 7. What comes after

Reliability work is a separate, later experiment, pre-registered in `config/ap3_reliability_followup_preregistration_v1.json`:
- the baseline is **not edited** once its results are seen;
- prompt work uses **separate development fixtures**, never the 30 gate fixtures, which stay a held-out gate run at most once per candidate;
- each candidate is a new protocol version, and enters the primary study only after passing the **original** gates at their **original** thresholds.

## 8. Running it

One action, on a free Kaggle GPU session: Accelerator **GPU T4 x2**, Internet **on**, then **Save Version → Save & Run All**. The notebook resumes if a session ends before 95 months. The GitHub token is passed through an askpass helper and never written into a URL, a `.git/config` or the saved output.

```bash
# on the GPU machine, run by the notebook
python -m native_backtest.scripts.ap3_free_run --stage all --hours 11 --push --exploratory
# afterwards, in the pinned environment
python -m native_backtest.scripts.ap3_free_import      # validates, evaluates and labels; refuses a partial history
python mvp/build_dashboard_data.py
```
