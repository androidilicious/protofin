# Runbook: reproduce the MVP, run Causal RAG, and (after GO) the final historical backtest

All commands run from the repository root on branch `backtest`. Requirements: Python 3.11+, Node 22, git, and network access to GitHub and PyPI. Steps marked **paid** or **protected** need the explicit approvals named in the step.

## 1. Reproduce the MVP

```bash
git clone -b backtest https://github.com/androidilicious/protofin.git && cd protofin
pip install -r stage2/scoring/requirements-lock.txt pyarrow jsonschema playwright requests beautifulsoup4 pypdf
python mvp/run.py serve        # dashboard at http://127.0.0.1:8000 from the committed results
python mvp/run.py fetch        # pinned inputs, every SHA-256 verified (claims data: local use only, git-ignored)
python mvp/run.py build        # AP1 rerun, AP2 replay, shared evaluation, AP3 graph libraries, dashboard data
python mvp/run.py check        # all tests + headless-browser check of 44 views (desktop/phone, light/dark)
```

## 2. Causal RAG without paid inference

```bash
# Engineering run of the full pipeline (mock responses; checks wiring only, never a result)
python -m native_backtest.scripts.ap3_dev_replay --variant reduced_evidence --provider engineering_mock
python -m native_backtest.scripts.ap3_g3b_fixtures --provider engineering_mock
```

## 3. Historical-document corpus (cloud only; no personal computer)

```bash
python -m native_backtest.scripts.ap3_corpus_fetch                      # resumable; official sources; logs URL, SHA-256, time
python -m native_backtest.scripts.ap3_corpus_import --from-fetch-log    # build + coverage, date, ALFRED and point-in-time checks
python -m native_backtest.scripts.ap3_corpus_archive pack --out <dir>   # deterministic ZIPs + archive manifest
# or restore the validated archives instead of fetching again:
gh release download ap3-corpus-v1.0-partial --repo androidilicious/protofin --dir <dir>
python -m native_backtest.scripts.ap3_corpus_archive restore --zips <dir>
python -m native_backtest.scripts.ap3_corpus_import --from-fetch-log
```

The fetch needs `www.federalreserve.gov`, `www.census.gov`, `www2.census.gov` and `www.bls.gov` reachable. BLS currently refuses this environment (`docs/AP3_CORPUS_STATUS_2026-10-29.md`).

## 4. Real-model validation, free (qwen3:4b on a free GPU, $0)

The project budget for paid inference is $0 (`config/budget_v1.json`), and every paid provider refuses. Real-model runs use **qwen3:4b**, the model the original CauseTrace uses, as a documented substitute for Llama 3.1 70B. It is served by Ollama on the notebook's own GPU. Details are in `docs/AP3_FREE_QWEN3_RUN_2026-10-29.md`.

```bash
# On a free Kaggle GPU (notebook native_backtest/notebooks/ap3_qwen3_free_run.ipynb does all of this):
python -m native_backtest.scripts.ap3_free_run --stage all --hours 11 --push
#   check -> G3b fixtures -> G3a sample (2015-02..2016-01) -> replay 2016-02..2022-12 only if both gates pass;
#   resumable; a redacted results bundle is committed to branch ap3-qwen3-runs after every 12 months

# Here (pinned environment): import, validate, calibrate, allocate, evaluate, refresh the dashboard
python -m native_backtest.scripts.ap3_free_import
python mvp/build_dashboard_data.py
```

The paid path (`ap3_smoke_test`, `ap3_hf_endpoint`, approval records A/B) stays in the code for reference. It refuses to run while the budget is $0.

## 5. The full-evidence version (after the corpus checks pass)

```bash
python -m native_backtest.scripts.ap3_dev_replay --variant historical_documents --provider ollama   # free, on the GPU notebook, once the corpus is complete
```

Then:
1. Run the human audit (G4b, κ ≥ 0.6).
2. Compare the two versions on development months. This is a secondary experiment.
3. The project lead records the primary version in `native_backtest/config/approvals/ap3_primary_version.json`, using development checks only.

## 6. Final historical backtest (protected; only after a signed GO)

1. Freeze:
   - Build the decision records for 2023-01..2026-08 for AP1, AP2B, AP2A and AP3 (the approved version) into `native_backtest/out/decisions/`.
   - Record their SHA-256 in the GO record together with `ap3_primary_version`, `decision: "GO"` and `signed_by`.
   - Building records reads inputs only. Nothing is scored.
2. Check readiness without scoring:

   ```bash
   python -m native_backtest.scripts.historical_evaluation --check
   ```
3. Open the window once:

   ```bash
   python -m native_backtest.scripts.historical_evaluation --go-record <signed GO record> --token <opening token>
   ```

   - **Primary:** 2024-01..2026-08.
   - **Secondary:** 2023 is reported separately.
   - **Primary contrasts:** JEV − Deterministic, Causal RAG − Deterministic and Causal RAG − JEV, in net CER with one Holm family of three.
   - **Passive Portfolio Reference (60% SPY / 40% IEF):** reported with its accounting decomposition.
   - **Committee vs JEV:** reported separately.

   The script refuses if any prerequisite is missing or any decision file differs from its frozen hash.
