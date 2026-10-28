# Agentic Causal RAG (AP3): development readiness — 2026-10-28

**Status: not yet ready for the development replay.** Everything that does not need the model or the official-document corpus is built, and it runs end to end on the real inputs for all 95 development months. One input source is missing. Two approvals are needed.

| Blocker | What it is | What resolves it |
|---|---|---|
| 1 | The official-document corpus has not been acquired | The fetcher is built and checked against the live index pages; the sandbox cannot reach the agencies' hosts |
| 2 | Paid inference is not approved | `AP3_INFERENCE_BUDGET_PROPOSAL_2026-10-28.md` |
| 3 | Two of seven mediator series are missing, and a third uses a substitute | BEI5Y, FF_FUTURES_6M; IG_SPREAD substitute |

The engineering-mock dry run (`native_backtest/scripts/ap3_dev_readiness.py`) built the real packets and pushed them through both agents for 2015-02..2022-12. No model was called. Nothing it produced is a result.

## Component status

| Component | Status | Evidence |
|---|---|---|
| Event packets | **Ready** | 95 packets frozen in `out/ap3/dev_readiness/ap3_packets_v1.jsonl` (SHA-256 `3b3f56ff…`). Triggers: 238 macro surprises (\|z\| ≥ 1, from the pinned Stage 2 panel), 67 FOMC events, 245 market-stress triggers (one per series per month). Mean 5.8 triggers a month, max 13; 2 months have none |
| Point-in-time inputs | **Ready** | 245/245 stress inputs public before the 20:00 ET decision; 67/67 FOMC events on or before the decision day; surprise panel hash-pinned |
| FOMC calendar | **Ready** | Team statement index vendored byte-identically (approach-2 @ ce063b8); assignment rule tested |
| Research graph vintages and pathway libraries | **Ready** | 8 decision years 2015–2022, vintage = decision year − 1; byte-identical rebuild (determinism check) |
| CauseTrace tools, Hypothesis Agent | **Ready (mock-tested)** | Tool loop, schemas, path validation, confidence caps exercised on every month |
| Testing Agent (causal-rag-mvp assessor logic) | **Ready (mock-tested), no evidence yet** | Planning, rivals, mediator tests and rubric exercised; assessor calls skipped because the corpus is empty |
| Mediator series | **Partial** | Pinned with `available_at` rules: UST2Y, UST10Y (FRED DGS2/DGS10, new pins), SLOPE_10Y3M, VIX. IG_SPREAD: BAA10Y as a substitute, **pending team approval**. BEI5Y: needs a pinned T5YIE copy. FF_FUTURES_6M: needs a Bloomberg export, or approval to drop or proxy it |
| Evidence corpus pipeline | **Ready, not populated** | `ap3/corpus.py`, `corpus_sources_v1.json`, `scripts/ap3_corpus_fetch.py`, `scripts/ap3_corpus_build.py`. Time-stamping from the documents themselves; native chunker; canaries; audit; tests |
| Evidence corpus data | **Blocked: acquisition** | See below |
| Calibration, encoder, allocation | **Ready** | Tested on synthetic panels; walk-forward |
| Model client | **Ready, locked** | Bedrock and DeepInfra providers refuse to run without approval and credentials; every call cached and logged |

## The corpus: what is verified and what is blocked

The fetcher's sources were checked against the live official pages through the browser on your computer: index pages, URL patterns, release-time lines and counts.

| Family | Verified |
|---|---|
| FOMC statements | URL pattern; printed release times (2:00 p.m. scheduled; 10:00 a.m. and 5:00 p.m. for the March 2020 unscheduled statements) |
| FOMC minutes | 8 a year on the 2015–2020 historical pages, with release dates; 46 with release dates on the 2021–2026 calendar page |
| BLS Employment Situation, CPI, PPI | Archive indexes list 12 a year for 2015–2024; the embargo line ("8:30 a.m. (EST) …") parses on 2015 and 2019 releases |
| Fed G.17 industrial production | Release dates listed; release pages resolve |
| Census advance retail sales | Historical page lists `adv<yymm>.pdf` through August 2026; the release line on page 1 is checked at build time |

About 900 documents (roughly 150–250 MB raw) are needed for 2015-01..2026-09. The fetcher is polite (one request every 2 s) and logs every response with its SHA-256. A full run takes about 30–40 minutes.

**What unblocks it (your choice, either one):**

1. **Allow the agencies' hosts for this environment:** `www.federalreserve.gov`, `www.bls.gov`, `www.census.gov`, `www2.census.gov`, plus `fred.stlouisfed.org` for BEI5Y. Then `python -m native_backtest.scripts.ap3_corpus_fetch` runs here.
2. **Acquire through the browser on your computer.** The browser fetches the same official URLs and saves one archive file (about 200 MB) to a folder you choose. I then copy it here with your folder permission. This needs your explicit approval for the download.

## Remaining AP3 steps once unblocked

1. Fetch and build the corpus. Run the point-in-time audit with canaries over all 95 decision times.
2. Decide the three mediator items (IG_SPREAD substitute, BEI5Y source, FF_FUTURES_6M).
3. Run the paid smoke test: 3 months, then G3a, 12 months. This calibrates the token estimate with real usage.
4. Run G3b: Testing Agent fixtures (30 labelled cases).
5. Run G4a/G4b: the 95-month development replay, the human audit (κ ≥ 0.6) and the calibration checks.
