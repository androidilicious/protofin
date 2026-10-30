# Protofin backtest: does AI improve on a deterministic model?

Duke MIDS × BNY CIO Office capstone. This branch (`backtest`) adds a shared, point-in-time backtesting framework, native integrations of the Protofin approaches, and an interactive dashboard. The existing Protofin app, the Stage 2 work and every earlier result are unchanged.

**Live dashboard:** published as a Claude artifact (link in the project hand-off). Locally: `python mvp/run.py serve`.

## Research design

| Role | Approach | What it is |
|---|---|---|
| **Research baseline** | Deterministic Quantitative Model | 8 economic-data surprises → walk-forward Ridge → 1-month forecasts → Black–Litterman (SPY/IEF/LQD) |
| Primary | Agentic Workflow, represented by JEV | An AI decision model's saved monthly answers → capped tilt around 60/40 stocks-versus-bonds (SPY/IEF/LQD) |
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

## Status (2026-10-30)

| | State |
|---|---|
| Deterministic (baseline) | Reproduced byte-for-byte natively; development results |
| JEV | Reproduced natively (272/272 saved answers); development results |
| Agent Committee | Reproduced natively; development results, compared only with JEV |
| Causal RAG — Reduced Evidence | **Run complete.** All 95 agent months replayed on **qwen3:4b on a free Kaggle GPU** (2,726 calls, $0; documented substitution for Llama 3.1 70B). Both reliability checks still fail (G3b 56.7% against 80% and 2 opposite-direction errors; G3a 97.7% schema-valid against 98%, 0 failed months), so the 46-month portfolio backtest is reported as an **exploratory diagnostic** of the pipeline, never as evidence of investment skill (`docs/AP3_EXPLORATORY_BACKTEST_2026-10-29.md`) |
| Causal RAG — With Historical Documents | Built. 474 Fed and Census documents validated; BLS documents (≤ 435) blocked from the cloud environment |
| Policy-path proxy variant | Built as a separately documented sensitivity variant for the missing fed funds futures; engineering-tested |
| Historical test | Sealed. `historical_evaluation.py` refuses to run without a signed GO record |

## Development results, March 2019 – December 2022 (46 months)

These are diagnostics on development months, not protected historical results.

| | Net CER | Sharpe | Worst fall | Volatility | Cumulative | Turnover |
|---|---|---|---|---|---|---|
| Deterministic (baseline) | 3.67% | 0.46 | −18.6% | 11.5% | 24.3% | 46% |
| JEV | 5.04% | 0.54 | −19.5% | 13.6% | 33.0% | 32% |
| Causal RAG (exploratory) | 5.12% | 0.61 | −18.7% | 10.8% | 30.8% | 106% |
| Agent Committee (within-approach) | 5.73% | 0.61 | −19.2% | 12.7% | 35.6% | 113% |
| Passive 60% SPY / 40% IEF (reference) | 4.98% | 0.55 | −18.8% | 12.9% | 32.0% | 28% |

All four now hold the same three funds. The Agentic Workflow's allocation was re-expressed from SPY/TLT onto SPY/IEF/LQD on 30 October under a committed pre-registration, without re-running anything: see [`native_backtest/docs/COMMON_UNIVERSE_RESPECIFICATION_2026-10-30.md`](native_backtest/docs/COMMON_UNIVERSE_RESPECIFICATION_2026-10-30.md), which measures that step on its own (+0.36 pts for JEV, +0.62 for the Committee).

- **JEV − Deterministic:** +1.37 pts net CER per year, 95% range −0.73 to +3.58, p = 0.20. Not statistically clear.
- **Causal RAG − Deterministic:** +1.46 pts, −0.29 to +4.75, p = 0.47. Not statistically clear, and exploratory.
- **Causal RAG − JEV:** +0.08 pts, −3.35 to +4.56, p = 0.98. The two agentic approaches are indistinguishable; before they were put on the same assets this gap read +0.45 pts.
- **Committee − JEV:** +0.69 pts, 95% range −1.00 to +2.45, p = 0.44. Not statistically clear.

**Within-approach experiments (completed 29 Oct 2026).** Pre-registered first, development months only, none in the primary family.
- **Conventional financial signals (B1..B5, B-All):** resumed after a written decision and pre-registration. The pre-declared B-All contrast is **−0.046** normalised pooled squared-error improvement (95% −0.139 to +0.001, p = 0.47): no improvement. No component is significant after Holm correction, none passes the robustness rule, and all five lower net CER.
- **Market regimes:** all four strategies earn far less from 2020 onward at two to three times the volatility; diagnostic only.
- **Committee + JEV:** net CER 5.41%, between JEV (5.04%) and the Committee (5.73%); clear against neither.

Report: [`native_backtest/docs/WITHIN_APPROACH_EXPERIMENTS_2026-10-29.md`](native_backtest/docs/WITHIN_APPROACH_EXPERIMENTS_2026-10-29.md).

**Do the signals add value?** Each approach is compared with its own portfolio with the forecasts switched off. These are within-approach counterfactuals, not new approaches: same assets, starting mix, monthly rebalancing, costs and cash.
- **Deterministic signals:** −0.11 pts net CER (95% range −0.31 to +0.03, p = 0.17).
- **JEV signals:** +0.15 pts (−0.47 to +0.98, p = 0.77). The gain depends on one month, the February 2020 decision.
- **JEV − Deterministic after accounting for their portfolios:** +0.26 pts (−0.41 to +1.22, p = 0.64).
- **Where JEV's +1.37 pts lead comes from:** +1.12 pts is the starting portfolio alone — its 60% stock weight against the Deterministic model's 45%. Now that both hold the same two bond funds in the same proportion, the bond-composition term is exactly zero. JEV's own signals add +0.15 pts and the Deterministic signals' small loss accounts for the remaining +0.11 pts.

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
