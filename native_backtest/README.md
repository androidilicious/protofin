# Native three-approach backtest

Shared evaluation of the Protofin approaches as their code exists in the repositories.

| Role | System | Status |
|---|---|---|
| Primary | Deterministic Quantitative Model (AP1, Stage 2 System A) | Implemented; development diagnostics |
| Primary | Agentic Workflow, represented by JEV (AP2B) | Implemented (native replay); development diagnostics |
| Primary | Agentic Causal RAG (AP3) | Built and tested without a model; awaiting validation, results unavailable |
| Within-approach variant | Agentic Workflow — Agent Committee (AP2A, "Committee only") | Implemented (native replay); development diagnostics, reported only against JEV |
| Within-approach variant | Agentic Workflow — Committee + JEV | Proposed; not built |
| Secondary experiments | Signal ablations; market-regime experiments; Standard RAG vs Causal RAG | Proposed; not run |

Roles, primary contrasts and the primary metric are recorded in `config/framework_config_v1.json` (`research_design`) and `config/system_manifest_v1.csv`. The primary metric is net CER, the certainty-equivalent return: 12 × (mean monthly net excess return − ½ × 2.5 × its variance). It is not a compound annual return.

The primary research timeline begins with the February 2015 macro-data training period. Months 2019-03..2022-12 are development diagnostics; 2023-01..2026-08 is the protected historical test and is sealed: the evaluator refuses to score it without a signed GO record.
The interactive dashboard is in `../mvp/` (`python mvp/run.py serve`).

## Layout

| Path | Contents |
|---|---|
| `docs/NATIVE_BEHAVIOUR_AUDIT.md` | Step 1 audit: what each system's code actually does, conflicts with the earlier proposal |
| `docs/AP3_MODEL_HOSTING_AND_COST.md` | Hosting options and cost estimate for AP3's Llama 3.1 70B agents (awaiting approval) |
| `framework/` | Shared evaluator: decision-record schema, market data and calendar, protected-window lock, accounting, metrics |
| `adapters/ap1_stage2.py` | AP1 decisions from the unchanged Stage 2 scorer |
| `adapters/ap2_native.py`, `adapters/node/ap2_native_replay.mjs` | AP2 native replay: the unchanged site engine run in Node, plus fidelity checks |
| `adapters/execution_attribution.py` | External adapter: native → common execution, one adjustment at a time |
| `vendor/` | Byte-identical copies of native AP2 code and saved outputs, with `PROVENANCE.json` |
| `config/` | Shared evaluation settings and research design (`framework_config_v1.json`), system manifest (`system_manifest_v1.csv`), TLT and claims data manifests |
| `ap3/` | Causal RAG: graph vintages and channel library (CauseTrace code, vendored unchanged), CauseTrace tools, Hypothesis Agent, Testing Agent (causal-rag-mvp assessor logic, model substitution documented), mediator tests, status encoder, calibration (G4c checks), allocation, LLM client (paid providers refuse without approval), engineering mock and fixtures |
| `docs/GO_NO_GO_2026-10-28.md` | Gate status; decision NO-GO; what must happen before GO |
| `docs/TLT_DISTRIBUTION_CHECK_2026-10-28.md`, `scripts/check_tlt_distributions.py`, `data/tlt_dividend_check/` | Freeze gate 5 extended to TLT on official iShares records (result: FAIL on C2 only; team decision needed) |
| `docs/CONTAMINATION_REGISTER_AND_HINDSIGHT_AUDIT_v1.md` | Draft register and audit for team sign-off |
| `ap3/fomc_calendar.py` | FOMC trigger calendar from the team's statement index (vendored, hash-pinned) |
| `ap3/mediator_data.py`, `config/ap3_mediator_manifest_v1.json` | Point-in-time mediator series with availability rules; stress triggers |
| `ap3/corpus.py`, `ap3/corpus_sources_v1.json`, `scripts/ap3_corpus_fetch.py`, `scripts/ap3_corpus_build.py`, `scripts/ap3_corpus_import.py`, `scripts/ap3_corpus_archive.py` | Official-document evidence corpus: resumable cloud fetch, time-stamp from the document, native chunking, canaries, coverage/date/ALFRED/point-in-time checks, versioned archives (Fed + Census validated; BLS blocked: `docs/AP3_CORPUS_STATUS_2026-10-29.md`) |
| `ap3/variants_v1.json`, `ap3/evidence_pool.py` | The two Causal RAG versions (Reduced Evidence; With Historical Documents) and their point-in-time evidence pools (`docs/AP3_CAUSAL_RAG_VERSIONS_2026-10-29.md`) |
| `scripts/ap3_dev_replay.py`, `ap3/reliability.py`, `config/ap3_reliability_gates_v1.json` | Development replay for either version (agents → status features → calibration → G4c → allocation), agent reliability report, pre-registered gates; paid providers refuse without approval |
| `scripts/ap3_g3b_fixtures.py`, `ap3/fixtures/testing_agent_fixtures_v1.json` | Gate G3b: the Testing Agent on 30 labelled fixtures |
| `scripts/ap3_free_run.py`, `scripts/ap3_free_import.py`, `notebooks/ap3_qwen3_free_run.ipynb`, `config/budget_v1.json` | Free real-model run: qwen3:4b served by Ollama on a free Kaggle GPU (documented substitution for Llama 3.1 70B), checkpointed, gated, results branch `ap3-qwen3-runs`; import, calibration and evaluation in the pinned environment; $0 budget enforced (`docs/AP3_FREE_QWEN3_RUN_2026-10-29.md`) |
| `scripts/historical_evaluation.py` | The one-time final historical backtest; refuses without a signed GO record, the opening token, frozen decision hashes and the approved Causal RAG version |
| `docs/RUNBOOK.md` | Reproduce the MVP; run Causal RAG; corpus; paid steps; final historical backtest after GO |
| `scripts/ap3_dev_readiness.py`, `out/ap3/dev_readiness/` | 95-month dry run with the engineering mock; frozen packets; measured prompt sizes |
| `scripts/ap3_inference_budget.py`, `out/ap3/inference_budget_v1.json` | Token and cost estimate by stage |
| `scripts/diagnose_tlt_gate5.py` | TLT gate 5 diagnosis: price vs NAV vs adjustment, materiality |
| `docs/AP3_DEV_READINESS_2026-10-28.md`, `docs/AP3_INFERENCE_BUDGET_PROPOSAL_2026-10-28.md`, `docs/SELECTION_BIAS_AGENTIC_WORKFLOW_2026-10-28.md` | Milestone documents |
| `out/` | Decision records, reproduction reports, development diagnostics (primary contrasts and the within-approach contrast), AP3 library manifest, gate record |
| `tests/` | Framework, native adapters and AP3 tests |

## Reproduce (from the repository root)

```
pip install -r stage2/scoring/requirements-lock.txt
python stage2/scoring/fetch_pinned_inputs.py --manifest stage2/reproducibility/stage2_data_snapshot_manifest_v3_2026-10-27.json
python stage2/scoring/fetch_pinned_inputs.py --manifest native_backtest/config/native_data_manifest_v1.json
python stage2/scoring/stage2_backtest.py --spec stage2/scoring/stage2_run_spec_dev_v4.json --mode development --output-dir native_backtest/out/ap1/stage2_dev_rerun
python -m native_backtest.scripts.build_ap1_decisions
python -m native_backtest.scripts.ap2_native_reproduction
python -m native_backtest.scripts.development_evaluation
python -m native_backtest.scripts.check_tlt_distributions   # gate 5 for TLT; exit 2 means the gate reports FAIL
python stage2/scoring/fetch_pinned_inputs.py --manifest native_backtest/config/ap3_claims_manifest_v1.json --out native_backtest/data/_external   # local use only
python -m native_backtest.scripts.build_ap3_libraries
python -m pytest -q native_backtest/tests
```

Node 22 is required for the AP2 native engine. No step calls a model or the network except the GitHub fetch of pinned inputs.

The same steps run with `python mvp/run.py fetch && python mvp/run.py build && python mvp/run.py check`.
