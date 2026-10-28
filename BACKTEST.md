# Four-system backtest (branch `backtest`)

This branch adds a shared backtesting framework, native integrations of all four Protofin approaches, and an interactive MVP dashboard. The existing Protofin app, the Stage 2 work and every earlier result are unchanged.

| Start here | |
|---|---|
| Run the dashboard | [`mvp/README.md`](mvp/README.md): `python mvp/run.py serve` |
| What each system's code actually does | [`native_backtest/docs/NATIVE_BEHAVIOUR_AUDIT.md`](native_backtest/docs/NATIVE_BEHAVIOUR_AUDIT.md) |
| Engine, adapters, Causal RAG build | [`native_backtest/README.md`](native_backtest/README.md) |
| Gate status and what blocks the historical test | [`native_backtest/docs/GO_NO_GO_2026-10-28.md`](native_backtest/docs/GO_NO_GO_2026-10-28.md) |
| Causal RAG model hosting and cost (awaiting approval) | [`native_backtest/docs/AP3_MODEL_HOSTING_AND_COST.md`](native_backtest/docs/AP3_MODEL_HOSTING_AND_COST.md) |

**Status (2026-10-28):** development-phase MVP.

- The Deterministic model, the Agent Committee and JEV are reproduced natively and evaluated on matching development months (2019-03..2022-12).
- Agentic Causal RAG is built and tested without a model and waits for approval of paid inference.
- The 2023–2026 historical test is sealed (decision: NO-GO).

**Development result:** no approach beat its own neutral benchmark by a statistically significant margin, and no difference between approaches was significant. These are diagnostics, not a test.

## Reproducing and verifying

```bash
python mvp/run.py fetch    # restricted inputs, downloaded and hash-checked (not stored in git)
python mvp/run.py build    # regenerates every result; native_backtest/out/ comes back byte-identical
python mvp/run.py check    # 51 project tests, 25 Stage 2 tests, headless-browser dashboard check
sha256sum -c RELEASE_MANIFEST.sha256   # committed results, configs, vendored code
```

Some inputs are not stored in this repository. Each has a manifest with SHA-256 hashes that `fetch` checks:

| Input | Manifest |
|---|---|
| Pinned prices and cash rate | `stage2/reproducibility/stage2_data_snapshot_manifest_v3_2026-10-27.json`; TLT in `native_backtest/config/native_data_manifest_v1.json` |
| Garg & Fetzer claims (no published licence; local research use only) | `native_backtest/config/ap3_claims_manifest_v1.json` |

`mvp/data/dashboard.json` is left out of the release manifest because it records its build time.
