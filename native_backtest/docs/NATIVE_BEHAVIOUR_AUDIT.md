# Native-behaviour audit (Step 1) — 2026-10-28

Read-only audit of the code each system actually runs. Repositories are cited at the commits inspected.
Nothing in this file changes any system; it records what each one does today.

> **Roles (updated 2026-10-28).** The primary comparison has three approaches: the Deterministic Quantitative Model (AP1), the Agentic Workflow represented by JEV (AP2B) and Agentic Causal RAG (AP3). The Agent Committee (AP2A) is a within-approach variant of the Agentic Workflow, compared only with JEV. The audit below describes native behaviour and applies to every system regardless of role; where it says "all four", it means every implemented system is scored under the same shared rules.

| System | Repository @ commit | Code inspected |
|---|---|---|
| AP1 | `androidilicious/protofin` @ `stage2-evaluation-mvp` 7ed45f8 | `stage2/scoring/stage2_backtest.py` (system A), `stage2_portfolio.py`, `stage2/config/stage2_frozen_config_v2.json`, `stage2_omega_from_A_development.json` |
| AP1 predecessor | `protofin` @ `main` b3a7100 (= `deterministic-model` f643f89); `fix/deterministic-backtest` 3bacab8 | `deterministic-model/deterministic_mvp/src/*.py`, tests, outputs |
| AP2-A Committee | `protofin` @ `approach-2` ce063b8 (most complete; `main` and `approach-1-committee-black-litterman` lack the parser fix) | `committee.py`, `allocation.py`, `macro_indexes.py`, `signals.py`, `stochastic_views.py`, `research/run_saved_committee.py`, `scripts/build_backtest_months.py`, `site/data/*.json`, `research/out/*` |
| AP2-B JEV | `protofin` @ `feature/jev` 7a70331 (decision math identical on `approach-2`) | `site/js/livebacktest.js`, `site/js/allocation.js`, `research/jev_eval.py`, `site/data/jev_runs.json`, `research/out/jev_backtest.json` |
| AP3 | `claireoh-duke/causetrace` @ 82abe0a; `FarnooshMemari/causal-rag-mvp` @ 389f826; `FarnooshMemari/causal-rag-demo` @ 5ec2a75 | all modules, configs, tests |

## 1. Native-behaviour matrix

| | AP1 (Stage 2 System A) | AP2-A Agent Committee | AP2-B JEV | AP3 Agentic Causal RAG |
|---|---|---|---|---|
| Inputs | 8 Bloomberg macro surprises, z = (s − mean of prior 12) / sd of prior 12; canonical panel `model_scoring_panel_E4_meanrule.csv` | Historical replay: masked relative features for SPY/TLT (1/3/12-month returns, 12-month vol, correlation, drawdown, rate percentiles, 10Y shock in bp, term spread, EPU and GPR percentiles) plus the cash-yield level; tickers SPY/TLT named. No macro surprises; no FOMC score in replay (live mode adds a FOMC-RoBERTa hawkishness score) | Same masked payload as the Committee (per README; the JEV prompt itself is not stored) | Not implemented end to end |
| Tools / retrieval | None | **None** — no tools, no function calling, no RAG; features pasted into the prompt | None known | CauseTrace: graph path search over Garg & Fetzer claims; causal-rag-mvp: BM25 over a timestamped one-event corpus |
| Model calls | None (Ridge) | OpenAI `gpt-4o` (unpinned alias), temperature 0, seed 42, max_tokens 300; 3 calls: Economist ∥ Risk Manager → CIO. Optional stochastic mode (T 0.2, 5 runs) saved for 18 months only | `typesafe/jev` on Cloudflare Workers AI; version and training cutoff undocumented; no client code in the repo | CauseTrace: local Ollama `qwen3:4b` for question parsing and explanations; causal-rag-mvp assessor: `claude` CLI, `claude-sonnet-5-5` (default sampling) |
| Output | One-month expected excess return per asset (decimal) | SPY and TLT expected **total** return over 12 months (%), confidence High/Medium/Low (all 272 saved runs say Medium) | P(stocks beat bonds over 12 months), five-way tilt probabilities, confidence, offset | Per-edge status supported / contradicted / insufficient with validated quotes (one event); no forecast |
| Horizon / rebalancing | 1 month / monthly | 12-month views / monthly | 12-month question / monthly | — |
| Universe | SPY, IEF, LQD | SPY, TLT | SPY, TLT | — |
| Allocator | BL: prior 45/35/20, τ 0.05, δ 2.5, P = I, fixed Ω from development errors, Ledoit–Wolf Σ on 36 monthly excess returns, exact enumeration within SPY 20–70%, IEF 15–60%, LQD 10–40% | BL: prior 60/40, δ 2.5, τ 0.05, P = I, Ω = c·τΣ with c = 0.5/1/2 for High/Medium/Low; confidence lowered one notch when EPU or GPR ≥ 90th pct or both ≥ 80th; Σ = 252-day daily sample covariance ×252; exact two-asset optimum clipped to SPY 40–80%. Replay applies no trade band | Capped tilt: edge = (Π_SPY − Π_TLT)·100 + confidence × offset, offsets strong/lean equities +3/+1.5, neutral 0, lean/strong bonds −1.5/−3; two-asset closed form with the same Σ and δ; SPY clipped to 40–80%. No regime gate | — |
| Decision timing | 20:00 ET last trading day; executed next trading day's close | Month-end close `as_of`; executed at the same close in the native replay | Same as Committee | — |
| Costs (native) | 5 bp per dollar traded, drift-aware, starts from cash | 5 bp per unit of SPY-weight change (= 2.5 bp per dollar traded), drift-aware | Same as Committee | — |
| Historical record | Development 2019-03..2022-12 scored; 2023-01..2026-08 sealed | 272 saved deterministic runs 2004-01-30..2026-08-31, generated 2026-10-05; raw replies cached, no prompts or timestamps; already scored by its authors over the full range | 272 saved answers 2004-01-30..2026-08-31; parsed fields only; already scored over the full range | causal-rag-mvp: one event (July 2023 retail sales) |
| Runs here | Yes | Replay of saved runs: yes. Live: no (OpenAI unreachable, no key) | Replay only. Live: no (no recorder, prompt or credentials) | Graph and BM25 code run; agents, forecast and allocation do not exist |

**AP1 identity.** Two deterministic implementations exist. The original MVP (`main`) uses 15 features (growth and inflation composites, policy-rate levels and changes, ANFCI, GPR, interactions), total-return targets, labels through t−1, sample Σ, a time-varying Ω and a turnover-penalised grid optimiser. Stage 2 System A uses the 8 individual surprises and differs in almost every estimation detail. This build treats **Stage 2 System A as AP1**, because AP1 has been defined throughout as "the 8 macro surprises → Ridge → allocation" and System A is the verified, frozen implementation of that. The MVP is recorded as AP1's predecessor and is not altered.

## 2. Conflicts between the proposed methodology and native behaviour

| # | Proposed methodology | Native behaviour | Classification | Resolution in this build |
|---|---|---|---|---|
| 1 | All systems on SPY/IEF/LQD | AP2-A and AP2-B trade SPY/TLT | Would materially alter AP2 | **Not adopted.** Each system runs on its native universe |
| 2 | One-month views | AP2-A and AP2-B use 12-month views, rebalanced monthly | Would materially alter AP2 | **Not adopted** |
| 3 | Committee re-run on Llama 3.1 70B | Native model gpt-4o | Would materially alter AP2-A | **Not adopted.** Saved native gpt-4o runs are used |
| 4 | 8 macro surprises added to every agent | Committee replay has no surprises | Would materially alter AP2-A | **Not adopted** |
| 5 | Shared prior 45/35/20, shared bounds, Ledoit–Wolf Σ | AP2: 60/40 prior, SPY 40–80%, 252-day sample Σ | Would materially alter AP2 | **Not adopted.** Native allocators run unchanged |
| 6 | Committee R = 3 at T = 0.3 | Native: one deterministic run, T = 0, seed 42 | Would materially alter AP2-A | **Not adopted** |
| 7 | Execution at the next trading day's close | AP2 native replay trades at the decision close | Shared evaluation setting (does not change any decision) | **Adopted for all four**; native same-close results are reproduced separately as a fidelity check |
| 8 | 5 bp per dollar traded | AP2 native 2.5 bp per dollar traded | Shared evaluation setting | **Adopted for all four**; native cost convention reproduced in the fidelity check |
| 9 | Pinned, gate-verified prices | AP2 native uses Yahoo adjusted closes | Shared data | **Adopted**; TLT must be pinned and distribution-checked (new) |
| 10 | Sealed 2023-01..2026-08 | AP2 authors already scored that window | Disclosure | Window stays sealed in the shared framework; prior inspection disclosed |
| 11 | Llama 3.1 70B for AP3 agents | AP3 agents do not exist; causal-rag-mvp assessor defaults to Claude Sonnet 5.5 | **Requires approval** (model choice, spending, network access) | Llama 3.1 70B Instruct chosen (2026-10-28); spending, credentials and network access still awaiting approval. The causal-rag-mvp assessor's logic is reused unchanged; its model is substituted, which is documented and not claimed identical |

## 3. Comparability

AP1 and AP3 trade SPY/IEF/LQD on one-month views. AP2-A and AP2-B trade SPY/TLT on 12-month views. A comparison of net CER across these systems is a comparison of **complete strategies, including their choice of assets and horizon**. It is not a controlled comparison of forecasting skill, because TLT has roughly twice IEF's duration and no credit exposure. Results will therefore also report each system against its own neutral portfolio (45/35/20 for AP1 and AP3, 60/40 SPY/TLT for AP2), so the asset-choice effect can be seen separately.

## 4. Point-in-time and contamination findings (disclosed, not altered)

- **AP2-A:** gpt-4o's pretraining data runs to October 2023 (OpenAI GPT-4o system card), so 2004–2023 decisions are inside its training data. The alias was not pinned. The replay payload names SPY/TLT and shows the cash-yield level, which can reveal the era. EPU/GPR are revised histories. The year probe (masked payload without the cash yield) found 20.4% within ±1 year vs 13.0% chance, concentrated in 2020–2023.
- **AP2-B:** model, version, cutoff and recording date unknown; prompt and raw replies not stored.
- **AP1:** the deterministic MVP on `main` committed realised returns for 2022-12..2026-09 (already disclosed in gate v5).
- **Prospective limits:** gpt-4o leaves the OpenAI API on 2027-01-14, and JEV has no live access in the repository, so neither AP2 system can be run prospectively in native form beyond what is saved.
