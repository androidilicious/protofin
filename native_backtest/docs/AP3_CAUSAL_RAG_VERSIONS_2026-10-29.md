# Agentic Causal RAG: two versions — 2026-10-29

Agentic Causal RAG (AP3) remains one of the three primary approaches. It now has two versions that differ in one respect only: the evidence the Testing Agent may retrieve.

| | Causal RAG — Reduced Evidence | Causal RAG — With Historical Documents |
|---|---|---|
| Hypothesis Agent, CauseTrace graph tools, year-filtered graph vintages | same | same |
| Causal RAG research records behind the cited pathways | same | same |
| Testing Agent: plan, rival, balanced BM25 retrieval, native causal-rag-mvp assessor, verbatim-quote validation, mediator tests, rubric, 3 seeds, majority | same | same |
| Status features, calibration (walk-forward Ridge), Black–Litterman allocation | same | same |
| Model, limits (`limits_v1.json`), seeds, decision time | same | same |
| **Evidence pool** | research claims + point-in-time data notes | the same pool **plus** official Fed, BLS and Census documents published before each decision |
| Status | Implemented; engineering-tested on all 95 development months; real-model validation needs approval | Implemented; engineering-tested; waits for the BLS documents |

Neither version silently replaces the originally specified system. The With Historical Documents version **is** the originally specified full-evidence system. The Reduced Evidence version exists because the full corpus is not yet complete. Both are configured in `native_backtest/ap3/variants_v1.json`, and the evidence pools are built in `native_backtest/ap3/evidence_pool.py`.

## Reduced-evidence pool

Every excerpt carries `available_at`. The pool builder refuses any excerpt at or after the decision time (20:00 ET) and any canary.

- **Research claims.** The CauseTrace research records behind the hypothesis's cited pathways and behind the candidate rival pathways. They come from the graph vintage, which keeps only papers dated before the decision year. The native assessor counts general theory as insufficient. These excerpts can therefore ground or contradict a mechanism, but they cannot show it operating in the decision month.
- **Month-to-date data notes.** The change in each mediator series since the month start, with its z-score against same-length changes over the previous 36 months. This uses the mediator test's own computation.
- **Release-window data notes.** For each macro or FOMC trigger, the change in each mediator series from the close before the release to the latest value visible at the decision time.
  - Release dates come from the ALFRED vintage record of each agency's headline series. FOMC dates come from the calendar.
  - ISM has no official-source release record, so it gets no release-window notes.
  - A window with no close visible after the release yields no note.
- **Macro surprise notes.** One note per release in the AP1 point-in-time panel. Missing values produce no note.
- **Exclusions.**
  - Notes for the series a hypothesis itself predicts are left out of that hypothesis's pool, because the deterministic mediator test already judges them. This avoids counting the same data twice.
  - Asset returns are never included.
  - `FF_FUTURES_6M` has no data until the Bloomberg export arrives. It yields no note, and its mediator test reports it as unavailable. Nothing is substituted for it.

## Sensitivity variant: policy-path proxy for the missing fed funds futures

`FF_FUTURES_6M` needs a licensed Bloomberg export. In the frozen specification it stays **unavailable**, and nothing is substituted.

A separately documented variant, `reduced_evidence_policy_proxy`, replaces it with a labelled proxy:
- **Definition:** the 2-year Treasury yield minus the 4-week Treasury bill rate (DGS2 − DTB4WK, percentage points). Both series are already pinned and hash-checked.
- **Availability:** each value is usable only once both inputs are published.
- **Labelling:** the agents' packet and the data notes call it a proxy.
- **What it measures:** the market-expected policy path, plus a term premium. It is not fed funds futures.

The variant has been wiring-checked on 6 development months with mock responses. It is never the primary version unless explicitly approved.

## How the Testing Agent avoids fabricated support

- The plan prompt, assessor prompt, schemas and rubric are unchanged.
- A directional label without a verbatim quote on its side is downgraded to insufficient.
  - In the engineering run, all 279 of the mock's fabricated quotes were rejected.
- "Supported" needs a validated supporting quote plus one more valid item (a second quote or a consistent mediator).
- A three-way split across the seeds counts as Insufficient.
- Invalid model output is logged. A month whose Hypothesis Agent fails gets no hypotheses (all status features 0). A hypothesis whose test fails is Insufficient and flagged as a failure, never Supported.
- Known property: with little textual evidence, the unchanged rubric makes Supported rarer than Contradicted. A single inconsistent mediator move can contradict a hypothesis, while support always needs a validated quote. This asymmetry is kept as specified and reported.

## Reliability gates (pre-registered 2026-10-29, before any real-model output)

The thresholds are in `native_backtest/config/ap3_reliability_gates_v1.json`, and the same thresholds apply to both versions. None of them uses investment performance.

| Gate | Criterion |
|---|---|
| G3a (first 12 months) | ≥ 98% schema-valid calls; ≤ 1 failed month; 0 fabricated quotes accepted; 0 point-in-time violations |
| G3b (30 labelled fixtures, `ap3/fixtures/testing_agent_fixtures_v1.json`) | accuracy ≥ 80%; ≤ 1 Supported/Contradicted reversal; all 3 injection cases resisted; theory-only cases never Supported |
| G4a (95-month replay) | failed months ≤ 5%; failed tests ≤ 5%; mean seed agreement ≥ 0.67; 0 point-in-time violations |
| G4b (human audit) | κ ≥ 0.6 on 40 stratified outcomes, two raters |
| G4c (calibration) | walk-forward without look-ahead; intercept-only share, sign stability, calibration slope and placebo reported, not used for selection |

## Choosing the primary version

The project lead approves the choice before the protected window opens. It is recorded in `native_backtest/config/approvals/ap3_primary_version.json` as `{"version": "<reduced_evidence|historical_documents>", "approved_by": ..., "date": ..., "basis": ...}`. The GO record must name the same version, and `historical_evaluation.py` refuses to run otherwise.

- **Recommended rule.** The With Historical Documents version is primary if its corpus passes the corpus checks and the version passes G3a, G3b, G4a and G4b. Otherwise the Reduced Evidence version is primary if it passes them.
- **Development performance.** Both versions' development results are reported but are not a selection criterion. Protected results are never used.
- **Secondary experiment.** Comparing the two versions on development months answers whether historical textual evidence helps. It is within-approach only.

## What is implemented, validated, pending, blocked

| Item | State |
|---|---|
| Evidence pools, variant config, runner integration, failure handling | Implemented; 40 AP3 tests pass |
| Reduced Evidence, 95 development months, engineering mock end to end (agents → calibration → G4c → allocation) | Ran; 0 point-in-time violations; wiring only, **not a result** |
| With Historical Documents, 6 months on the partial corpus, engineering mock | Ran; wiring only, **not a result** |
| G3b fixtures and runner | Implemented; mock run checks wiring only |
| Real-model smoke test, G3a, G3b, 95-month replays, human audit | **Blocked: paid-inference approval** |
| Official-document corpus | Fed and Census: 474 documents validated. BLS: **blocked** (`AP3_CORPUS_STATUS_2026-10-29.md`) |
| `FF_FUTURES_6M` mediator | **Blocked: Bloomberg export** (no proxy without approval) |

## Model and cost

The project budget for paid inference is **$0**, and the paid plan (a Hugging Face endpoint for Llama 3.1 70B) was withdrawn on 2026-10-29 before anything was created or billed.

Real-model runs use **qwen3:4b**, the model the original CauseTrace project uses, on a free Kaggle GPU. This is a documented model substitution: the architecture, evidence, prompts, limits, seeds and gates are unchanged, but the model is much smaller. The record, workflow and resource estimates are in `AP3_FREE_QWEN3_RUN_2026-10-29.md`.
