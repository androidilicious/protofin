# Protofin Backtest — interactive MVP

A dashboard that compares three investment approaches, each run as its own code works, under one set of scoring rules:

| In the dashboard | What it is | Results shown |
|---|---|---|
| Deterministic Quantitative Model | 8 macro surprises → Ridge → Black–Litterman (SPY/IEF/LQD) | Development diagnostics 2019-03..2022-12 |
| Agentic Workflow — JEV | JEV's saved answers → capped tilt around 60/40 (SPY/TLT) | Development diagnostics 2019-03..2022-12 |
| Agentic Causal RAG | Knowledge graph → Hypothesis Agent → CauseTrace → Testing Agent → forecast → allocation | **Awaiting validation · results unavailable**; a labelled demo shows the workflow |

The **Experiments** section holds the within-approach (secondary) experiments, grouped by approach, each with a status: Tested, Awaiting validation, Planned, Blocked or Paused.
- **Deterministic:** the 8-surprise base model (tested); adding financial signals one at a time or all together (paused by team decision, results archived and not shown); market regimes (planned).
- **Agentic Workflow:** JEV only (tested; the primary system), Agent Committee only (tested; compared only with JEV), Committee + JEV (planned).
- **Causal RAG:** the approach (awaiting validation; its primary version is chosen before the test opens), Causal RAG — Reduced Evidence (built and engineering-tested; real model runs await approval), Causal RAG — With Historical Documents (built; waits for the BLS documents), whether historical documents help, Standard RAG vs Causal RAG, ablations and placebo checks, model and calibration variants (planned).

The 2023-01..2026-08 protected historical test is **sealed**. Nothing in this MVP scores it, and every number shown is a development diagnostic.

## Run it locally

Requirements: Python 3.13 (3.11+ works), Node 22 (for the Committee/JEV native replay engine), git, and network access to GitHub and PyPI.

```bash
git clone -b backtest https://github.com/androidilicious/protofin.git
cd protofin
pip install -r stage2/scoring/requirements-lock.txt pyarrow jsonschema   # add playwright to run the browser check
python mvp/run.py serve            # dashboard at http://127.0.0.1:8000 using the committed results
```

The committed `mvp/data/dashboard.json` is enough to open the dashboard. To regenerate everything from source:

```bash
python mvp/run.py fetch            # pinned price, cash-rate and claims inputs from GitHub; every SHA-256 verified
python mvp/run.py build            # AP1 rerun, AP2 native replay + reproduction, common evaluation, AP3 graph libraries, dashboard data
python mvp/run.py check            # project tests + Stage 2 tests + headless-browser dashboard check
```

`build` is deterministic: rerunning it leaves every file under `native_backtest/out/` byte-identical. Only the dashboard file's build timestamp changes.

## Using the dashboard

- **Overview** — the research question first: does AI improve on the Deterministic baseline? The Deterministic Quantitative Model is marked as the research baseline. Shown: the verdict, the timeline, one card per approach (net CER and, for the AI approaches, the difference from the baseline with its range), the three research comparisons (JEV − Deterministic, Causal RAG − Deterministic, Causal RAG − JEV; pending where Causal RAG has no results), findings, growth of $1 (toggle: versus the baseline), key metrics, and a separate passive investment comparison against the Passive Portfolio Reference — 60% SPY / 40% IEF, which is also an optional dashed line on the chart. Nothing is marked as a winner.
- **Approaches** — one tab per approach: an interactive flow diagram, results with the research comparison (versus the Deterministic baseline; the baseline page lists the comparisons against it), the passive 60/40 reference with its accounting split, the approach's own benchmark as a secondary check, forecasts, holdings, the reproduction check and limitations. Causal RAG shows its two versions with their real build and validation status, its validation progress and the research inputs it will use, plus a clearly labelled demo.
- **Experiments** — the within-approach experiments described above, the Committee vs JEV comparison, and a short pointer to the signal value analysis.
- **Signal Value-Added** — a short research story in five steps:
  1. **Observation:** the Deterministic and JEV curves look alike (monthly return correlation 0.971; their no-signal portfolios alone 0.983); the integrity audit found no calculation or charting error.
  2. **Experiments:** each approach against its own portfolio with the forecasting signal switched off.
  3. **Results:** net CER with and without signals, growth of $1, and the incremental net CER with its 95% interval and p-value; both intervals include zero.
  4. **Explanation:** JEV's +1.01-point lead split into its no-signal portfolio (+0.59) and signals (+0.42), as accounting attribution, not causality, plus the February 2020 sensitivity check.
  5. **Takeaway:** the conclusion and its limits.

  Every number and series comes from `native_backtest/out/signal_value/` and `native_backtest/out/audit/` through the build.
- **Methodology** — the timeline (2023 marked as overlapping the AI models' training data; open decisions listed), rules and settings tagged Frozen, Needs approval or Differs by design, the passive portfolio reference (mix, the five rules it shares with the backtest, and its freeze status), the validation-status matrix, and expandable details on net CER, statistics and safeguards.
- Every term with an **i** has a one-sentence explanation on hover, focus or tap.

**Net CER** is the certainty-equivalent return: 12 × (mean monthly net excess return − ½ × 2.5 × its variance). It is not a compound annual return.

## Data contract

The dashboard reads one file, `mvp/data/dashboard.json`, built by `mvp/build_dashboard_data.py` from the decision records in `native_backtest/out/decisions/` through the shared evaluator (`native_backtest/framework/`). Its tests are in `mvp/tests/test_dashboard_data.py`:

- exactly three primary approaches, with the Committee only as a within-approach variant;
- only development months (before 2023-01), with the timeline starting February 2015;
- every metric and contrast equal to the committed development report;
- Causal RAG awaiting validation with no results, and its demo marked `is_mock: true`;
- CER defined as the certainty-equivalent return;
- experiment statuses identical to `research_design` in `native_backtest/config/framework_config_v1.json`, and the validation matrix taken from `native_backtest/config/validation_status_v1.json`;
- no internal codes and no text from the claims dataset.

## What is real and what is a demo

- All performance numbers come from real decisions: the Stage 2 scorer for the Deterministic model, and the approaches' own saved runs replayed by their own code for the Committee and JEV.
- The Causal RAG research-graph statistics are real; they are computed from the claims data at a pinned commit.
- The Causal RAG "one month, step by step" panel is an **engineering demo**: canned responses and synthetic documents, labelled on screen. It can never be scored; the evaluator refuses mock records.

## Not in this repository (and why)

| Item | Why | How to get it |
|---|---|---|
| Pinned price copies (`stage2/data/_pinned/`) | Third-party copies are not republished | `python mvp/run.py fetch` (hash-checked) |
| Garg & Fetzer claims data and AP3 graph libraries (`native_backtest/data/_external/`) | The source publishes no licence: local research use only | `python mvp/run.py fetch`, then `build` |
| Model credentials | Secrets are never committed | Environment secrets, after approval |

## Still blocked

See `native_backtest/docs/GO_NO_GO_2026-10-28.md`. In short:

- Causal RAG needs approved model spending, credentials and network access.
- It also needs the official-document corpus and the remaining market series.
- TLT needs its issuer distribution check.
- The team still has to sign the contamination register and the hindsight audit, and review the October 23 deck.

Full procedures, including the paid model runs and the final historical backtest after approval: `native_backtest/docs/RUNBOOK.md`.
