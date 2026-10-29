# Runbook: reproduce the MVP, run Causal RAG, and (after GO) the final historical backtest

All commands run from the repository root on branch `backtest`. Requirements: Python 3.11+, Node 22, git, and network access to GitHub and PyPI. Steps marked **paid** or **protected** need the explicit approvals named in the step.

## 1. Reproduce the MVP

```bash
git clone -b backtest https://github.com/androidilicious/protofin.git && cd protofin
pip install -r stage2/scoring/requirements-lock.txt pyarrow jsonschema playwright requests beautifulsoup4 pypdf
python mvp/run.py serve        # dashboard at http://127.0.0.1:8000 from the committed results
python mvp/run.py fetch        # pinned inputs, every SHA-256 verified (claims data: local use only, git-ignored)
python mvp/run.py build        # AP1 rerun, AP2 replay, shared evaluation, AP3 graph libraries, dashboard data
python mvp/run.py check        # all tests + headless-browser check of 40 views (desktop/phone, light/dark)
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

## 4. Real-model validation (paid; approvals A and B)

Every paid step refuses to run unless all of these exist:
- an approval record in `native_backtest/config/approvals/`;
- `AP3_ALLOW_PAID_INFERENCE=1`;
- the provider's secrets as environment secrets;
- a hard spending cap enforced by `CostGuard`.

Without `--execute`, each command only prints its plan.

```bash
# A: smoke test (3 pre-specified months, Reduced Evidence). Approved 2026-10-29: hf_endpoint, $15 total.
python -m native_backtest.scripts.ap3_hf_endpoint                       # plan: endpoint spec, deadlines, worst case of every failure mode
AP3_ALLOW_PAID_INFERENCE=1 python -m native_backtest.scripts.ap3_smoke_test --provider hf_endpoint --execute
python -m native_backtest.scripts.ap3_smoke_report                      # evidence report (redacted copy committed)
python -m native_backtest.scripts.ap3_hf_endpoint --delete              # only if a run was killed: deletes the recorded endpoint

# B: gates G3a/G3b and the 95-month development replay. Separate approval record ap3_inference_approval_B.json:
#    {"stage": "B", "provider": "hf_endpoint", "variants": ["reduced_evidence"], "cap_usd": <cap>, "approved_by": ..., "date": ...}
python -m native_backtest.scripts.ap3_g3b_fixtures --provider hf_endpoint --execute
python -m native_backtest.scripts.ap3_dev_replay --variant reduced_evidence --provider hf_endpoint --months 2015-02,2016-01 --execute   # G3a
python -m native_backtest.scripts.ap3_dev_replay --variant reduced_evidence --provider hf_endpoint --execute                          # G4a + calibration
```

The smoke test runs under one controller (`scripts/ap3_hf_endpoint.py`), which creates the endpoint and records the time just before creation. It then:
1. Deletes the endpoint if the configuration Hugging Face echoes back lacks the pinned revision, image, instance or container arguments.
2. Deletes it if it is not running after 40 minutes, or if it reports a failure.
3. Sends requests only while the endpoint reports "running", with no wake-up of a scaled-to-zero endpoint.
4. Stops new calls at 65 minutes and deletes the endpoint at 68 minutes.
5. Deletes it when the run ends or is interrupted.

At $10/hour, billed per minute, the bounds are:
- $11.83 while the controller runs;
- $14.17 if the controller process dies mid-run, because the endpoint scales to zero after 15 idle minutes.

One case is not bounded by our code: the process dies during initialisation and Hugging Face never finishes initialising. Then `--delete` or the Hugging Face console stops it.

Before the paid run, the environment needs:
- `HF_TOKEN` as an environment secret, able to manage Inference Endpoints and read the gated repository;
- the Llama 3.1 licence accepted;
- billing enabled on the Hugging Face account;
- network access to `huggingface.co`, `api.endpoints.huggingface.cloud` and the endpoint host (`*.endpoints.huggingface.cloud`).


## 5. The full-evidence version (after the corpus checks pass)

```bash
python -m native_backtest.scripts.ap3_dev_replay --variant historical_documents --provider hf_endpoint --execute   # approval B must list the variant
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
