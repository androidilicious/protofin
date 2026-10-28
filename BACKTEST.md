# Three-approach backtest (branch `backtest`)

This branch adds a shared backtesting framework, native integrations of the Protofin approaches, and an interactive MVP dashboard. The existing Protofin app, the Stage 2 work and every earlier result are unchanged.

| Role | Approach | Status (2026-10-28) |
|---|---|---|
| Primary | Deterministic Quantitative Model | Reproduced natively; development diagnostics |
| Primary | Agentic Workflow, represented by JEV | Reproduced natively (replay of saved answers); development diagnostics |
| Primary | Agentic Causal RAG | Built and tested without a model; **awaiting validation, results unavailable** |
| Within-approach experiment | Agentic Workflow: Committee only | Implemented; development diagnostics, compared only with JEV |
| Within-approach experiment | Agentic Workflow: Committee + JEV | Proposed; not built |
| Secondary experiments | Signal ablations; market-regime experiments; Standard RAG vs Causal RAG | Proposed; not run |

| Start here | |
|---|---|
| Run the dashboard | [`mvp/README.md`](mvp/README.md): `python mvp/run.py serve` |
| Research design (roles, contrasts, metric) | [`native_backtest/config/framework_config_v1.json`](native_backtest/config/framework_config_v1.json) (`research_design`), [`native_backtest/config/system_manifest_v1.csv`](native_backtest/config/system_manifest_v1.csv) |
| What each system's code actually does | [`native_backtest/docs/NATIVE_BEHAVIOUR_AUDIT.md`](native_backtest/docs/NATIVE_BEHAVIOUR_AUDIT.md) |
| Engine, adapters, Causal RAG build | [`native_backtest/README.md`](native_backtest/README.md) |
| Gate status and what blocks the protected historical test | [`native_backtest/docs/GO_NO_GO_2026-10-28.md`](native_backtest/docs/GO_NO_GO_2026-10-28.md) |
| Causal RAG model hosting and cost (awaiting approval) | [`native_backtest/docs/AP3_MODEL_HOSTING_AND_COST.md`](native_backtest/docs/AP3_MODEL_HOSTING_AND_COST.md) |

**Primary metric.** Net CER, the certainty-equivalent return: 12 × (mean monthly net excess return − ½ × 2.5 × its variance), the guaranteed yearly return above cash a risk-averse investor would accept instead of the strategy. It is not a compound annual return.

**Primary comparison.** Net-CER differences among the three primary approaches, Holm-corrected as one family of three. Only Agentic Workflow (JEV) vs Deterministic exists so far; the two Causal RAG contrasts wait for genuine Causal RAG results. The Committee and the secondary experiments never enter this family.

**Timeline.** The primary research timeline begins with the February 2015 macro-data training period. Months 2019-03..2022-12 are development diagnostics. The protected historical test, 2023-01..2026-08, is sealed (decision: NO-GO), so no protected historical results exist.

**Development diagnostics so far:** neither the Deterministic model nor the Agentic Workflow (JEV) beat its own benchmark or the other by a statistically significant margin; nor did the Committee beat JEV. These are diagnostics, not protected historical results.

## Reproducing and verifying

```bash
python mvp/run.py fetch    # restricted inputs, downloaded and hash-checked (not stored in git)
python mvp/run.py build    # regenerates every result; native_backtest/out/ comes back byte-identical
python mvp/run.py check    # project tests, Stage 2 tests, headless-browser dashboard check
sha256sum -c RELEASE_MANIFEST.sha256   # committed results, configs, vendored code
```

Some inputs are not stored in this repository. Each has a manifest with SHA-256 hashes that `fetch` checks:

| Input | Manifest |
|---|---|
| Pinned prices and cash rate | `stage2/reproducibility/stage2_data_snapshot_manifest_v3_2026-10-27.json`; TLT in `native_backtest/config/native_data_manifest_v1.json` |
| Garg & Fetzer claims (no published licence; local research use only) | `native_backtest/config/ap3_claims_manifest_v1.json` |

`mvp/data/dashboard.json` is left out of the release manifest because it records its build time.
