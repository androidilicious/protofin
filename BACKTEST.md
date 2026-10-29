# Protofin backtest: does AI improve on a deterministic model?

Duke MIDS × BNY CIO Office capstone. This branch (`backtest`) adds a shared, point-in-time backtesting framework, native integrations of the Protofin approaches, and an interactive dashboard. The existing Protofin app, the Stage 2 work and every earlier result are unchanged.

**Live dashboard:** published as a Claude artifact (link in the project hand-off). Locally: `python mvp/run.py serve`.

## Research design

| Role | Approach | What it is |
|---|---|---|
| **Research baseline** | Deterministic Quantitative Model | 8 economic-data surprises → walk-forward Ridge → 1-month forecasts → Black–Litterman (SPY/IEF/LQD) |
| Primary | Agentic Workflow, represented by JEV | An AI decision model's saved monthly answers → capped tilt around 60/40 (SPY/TLT) |
| Primary | Agentic Causal RAG | Knowledge graph → Hypothesis Agent → CauseTrace → Testing Agent → calibration → Black–Litterman (SPY/IEF/LQD) |
| Within-approach experiment | Agent Committee (Agentic Workflow) | Three AI agents set 12-month views; compared only with JEV |
| Secondary reference | Passive Portfolio Reference: 60% SPY / 40% IEF | Frozen; a passive investment reference, not the research baseline |

- **Primary comparisons:** JEV − Deterministic, Causal RAG − Deterministic and Causal RAG − JEV. Each is a net-CER difference with a block bootstrap (6-month blocks, 5,000 draws), forming one Holm family of three.
- **Primary metric:** Net CER, the certainty-equivalent return: 12 × (mean monthly net excess return − ½ × 2.5 × its variance). It is not a compound annual return.
- **Supporting metrics:** Sharpe ratio, worst fall, volatility, cumulative return and turnover.
- **Timeline:**
  - training starts February 2015;
  - development runs March 2019 – December 2022;
  - the protected historical test (2023-01..2026-08) is **sealed**, with the primary test January 2024 – August 2026 and 2023 reported separately.

## Status (2026-10-29)

| | State |
|---|---|
| Deterministic (baseline) | Reproduced byte-for-byte natively; development results |
| JEV | Reproduced natively (272/272 saved answers); development results |
| Agent Committee | Reproduced natively; development results, compared only with JEV |
| Causal RAG — Reduced Evidence | Built; engineering-tested end to end on all 95 development months with mock responses (never shown as results). Real-model run on **qwen3:4b on a free Kaggle GPU** ($0; documented substitution for Llama 3.1 70B). **Run 1 failed both reliability checks** (G3b 53% vs 80%; G3a 12/12 months without a final answer); harness defects were found and fixed (protocol 1.1; prompts and thresholds unchanged). By the project lead's decision of 29 Oct the full development backtest now runs **first** in a labelled **exploratory (gate-failed)** mode, with reliability work to follow as a separate experiment (`docs/AP3_EXPLORATORY_BASELINE_2026-10-29.md`) |
| Causal RAG — With Historical Documents | Built. 474 Fed and Census documents validated; BLS documents (≤ 435) blocked from the cloud environment |
| Policy-path proxy variant | Built as a separately documented sensitivity variant for the missing fed funds futures; engineering-tested |
| Historical test | Sealed. `historical_evaluation.py` refuses to run without a signed GO record |

## Development results, March 2019 – December 2022 (46 months)

These are diagnostics on development months, not protected historical results.

| | Net CER | Sharpe | Worst fall | Volatility | Cumulative | Turnover |
|---|---|---|---|---|---|---|
| Deterministic (baseline) | 3.67% | 0.46 | −18.6% | 11.5% | 24.3% | 46% |
| JEV | 4.67% | 0.51 | −23.8% | 13.7% | 31.2% | 33% |
| Agent Committee (within-approach) | 5.11% | 0.56 | −23.6% | 13.0% | 32.7% | 113% |
| Passive 60% SPY / 40% IEF (reference) | 4.98% | 0.55 | −18.8% | 12.9% | 32.0% | 28% |
| Causal RAG | not run yet: free real-model run pending | | | | | |

- **JEV − Deterministic:** +1.01 pts net CER per year, 95% range −3.42 to +5.27, p = 0.63. Not statistically clear.
- **Committee − JEV:** +0.44 pts, 95% range −1.85 to +2.90, p = 0.72. Not statistically clear.

**Within-approach experiments (completed 29 Oct 2026).** Pre-registered first, development months only, none in the primary family.
- **Conventional financial signals (B1..B5, B-All):** resumed after a written decision and pre-registration. The pre-declared B-All contrast is **−0.046** normalised pooled squared-error improvement (95% −0.139 to +0.001, p = 0.47): no improvement. No component is significant after Holm correction, none passes the robustness rule, and all five lower net CER.
- **Market regimes:** all four strategies earn far less from 2020 onward at two to three times the volatility; diagnostic only.
- **Committee + JEV:** net CER 4.93%, between JEV (4.67%) and the Committee (5.11%); clear against neither.

Report: [`native_backtest/docs/WITHIN_APPROACH_EXPERIMENTS_2026-10-29.md`](native_backtest/docs/WITHIN_APPROACH_EXPERIMENTS_2026-10-29.md).

**Do the signals add value?** Each approach is compared with its own portfolio with the forecasts switched off. These are within-approach counterfactuals, not new approaches: same assets, starting mix, monthly rebalancing, costs and cash.
- **Deterministic signals:** −0.11 pts net CER (95% range −0.31 to +0.03, p = 0.17).
- **JEV signals:** +0.31 pts (−0.48 to +1.38, p = 0.59). The gain depends on one month, the February 2020 decision; without it the figure is −0.18 pts.
- **JEV − Deterministic after accounting for their portfolios:** +0.42 pts (−0.43 to +1.63, p = 0.51).
- **Where JEV's +1.01 pts lead comes from:** +0.59 pts comes from the two no-signal portfolios. The larger stock weight adds +1.39 pts and the long Treasuries take away 0.79 pts.

None of these is statistically clear. Report: [`native_backtest/docs/SIGNAL_VALUE_ADDED_2026-10-29.md`](native_backtest/docs/SIGNAL_VALUE_ADDED_2026-10-29.md).

## Run it

```bash
git clone -b backtest https://github.com/androidilicious/protofin.git && cd protofin
pip install -r stage2/scoring/requirements-lock.txt pyarrow jsonschema playwright requests beautifulsoup4 pypdf huggingface_hub
python mvp/run.py serve     # dashboard at http://127.0.0.1:8000 from the committed results
python mvp/run.py fetch     # pinned inputs, SHA-256 verified (claims data: local research use only, never committed)
python mvp/run.py build     # regenerates every result; native_backtest/out/ comes back byte-identical
python mvp/run.py check     # all tests + headless-browser check of 44 views (desktop/phone, light/dark)
sha256sum -c RELEASE_MANIFEST.sha256
```

The rest of the procedures are in [`native_backtest/docs/RUNBOOK.md`](native_backtest/docs/RUNBOOK.md):
- the Causal RAG engineering runs;
- the cloud corpus download and validation;
- the free real-model run on a Kaggle GPU (qwen3:4b; `docs/AP3_FREE_QWEN3_RUN_2026-10-29.md`); paid providers refuse while the budget is $0;
- the final historical backtest after GO.

Environment variables are listed in [`.env.example`](.env.example). No secret is stored in the repository.

## Deploying the dashboard

The dashboard is a static site, `mvp/index.html` + `mvp/assets/` + `mvp/data/dashboard.json`. It needs no backend, since every number is precomputed by `python mvp/run.py build`. Any static host works:

| Option | How | Notes |
|---|---|---|
| Claude artifact (current) | Published from the same three files | Shareable link; no account needed to view |
| Cloudflare Pages | `npx wrangler pages deploy mvp --project-name protofin-backtest` | Needs a Cloudflare account token. Use a separate project: the existing `protofin` project serves `site/` from `main` |
| GitHub Pages | Serve `mvp/` from a branch or Actions | Private repositories need a paid GitHub plan; do not make the repository public to use it |
| Local | `python mvp/run.py serve` | |

The dashboard contains development results, statuses and explanations only. It contains no pipeline code, licensed data, credentials or protected results.

## Where things are

| Path | Contents |
|---|---|
| [`native_backtest/`](native_backtest/README.md) | Shared evaluator, native adapters, Causal RAG (agents, evidence pools, corpus, reliability gates), scripts, tests |
| [`native_backtest/docs/GO_NO_GO_2026-10-28.md`](native_backtest/docs/GO_NO_GO_2026-10-28.md) | Gate status and what blocks the protected test |
| [`native_backtest/docs/AP3_CAUSAL_RAG_VERSIONS_2026-10-29.md`](native_backtest/docs/AP3_CAUSAL_RAG_VERSIONS_2026-10-29.md) | The Causal RAG versions, reliability gates, cost of model runs |
| [`native_backtest/docs/AP3_QWEN3_RUN1_DIAGNOSIS_2026-10-29.md`](native_backtest/docs/AP3_QWEN3_RUN1_DIAGNOSIS_2026-10-29.md) | First free real-model run of Causal RAG: why both gates failed, which were pipeline defects (fixed) and which the model's, what to rerun |
| [`native_backtest/docs/AP3_CORPUS_STATUS_2026-10-29.md`](native_backtest/docs/AP3_CORPUS_STATUS_2026-10-29.md) | Evidence corpus: counts, reconciliation, storage, BLS options |
| [`native_backtest/docs/AP3_EXPLORATORY_BASELINE_2026-10-29.md`](native_backtest/docs/AP3_EXPLORATORY_BASELINE_2026-10-29.md) | The exploratory (gate-failed) Causal RAG baseline: what is frozen, what the mode permits and forbids, coverage rules, and the follow-up plan |
| [`native_backtest/docs/WITHIN_APPROACH_EXPERIMENTS_2026-10-29.md`](native_backtest/docs/WITHIN_APPROACH_EXPERIMENTS_2026-10-29.md) | The within-approach experiments: why each was pending, the financial-signal results, market regimes, Committee + JEV, and what still blocks Causal RAG |
| [`native_backtest/docs/SIGNAL_VALUE_ADDED_2026-10-29.md`](native_backtest/docs/SIGNAL_VALUE_ADDED_2026-10-29.md) | Signals vs each approach's own no-signal portfolio; reconciled breakdown of the JEV − Deterministic gap; independent rebuild |
| [`native_backtest/docs/PORTFOLIO_INTEGRITY_AUDIT_2026-10-29.md`](native_backtest/docs/PORTFOLIO_INTEGRITY_AUDIT_2026-10-29.md) | Independent rebuild of the Deterministic, JEV and passive returns; why the Deterministic and JEV curves look alike (no calculation error) |
| [`mvp/`](mvp/README.md) | Dashboard frontend, data builder and its tests |
| `stage2/` | The validated Stage 2 scorer the Deterministic model runs on |

## Data and licensing

Some inputs are not stored in this repository. `fetch` downloads them and checks their SHA-256:

| Input | Manifest |
|---|---|
| Pinned prices and cash rate | `stage2/reproducibility/stage2_data_snapshot_manifest_v3_2026-10-27.json`; TLT in `native_backtest/config/native_data_manifest_v1.json` |
| Garg & Fetzer claims (no published licence; local research use only) | `native_backtest/config/ap3_claims_manifest_v1.json` |
| Official-document corpus (US government, public domain) | `native_backtest/data/ap3_corpus/fetch_manifest_v1.json`, re-fetched with `ap3_corpus_fetch` |
| Bloomberg fed funds futures (licensed; not committed) | `native_backtest/config/bloomberg_ff_futures_request_v1.json` |

`mvp/data/dashboard.json` is left out of the release manifest because it records its build time.
