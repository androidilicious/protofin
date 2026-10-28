# Protofin Backtest — interactive MVP

A dashboard that compares four investment approaches, each run as its own code works, under one set of scoring rules:

| In the dashboard | What it is | Results shown |
|---|---|---|
| Deterministic Quantitative Model | 8 macro surprises → Ridge → Black–Litterman (SPY/IEF/LQD) | Development 2019-03..2022-12 |
| Agentic Workflow — Agent Committee | Economist + Risk Manager → CIO (GPT-4o, saved runs) → Black–Litterman (SPY/TLT) | Development, plus 2011–2022 history |
| Agentic Workflow — JEV | TypeSafe JEV's saved answers → capped tilt (SPY/TLT) | Development, plus 2011–2022 history |
| Agentic Causal RAG | Knowledge graph → Hypothesis Agent → CauseTrace → Testing Agent → forecast → allocation | **None yet**: waiting for model-spend approval; a labelled demo shows the workflow |

The 2023-01..2026-08 historical test is **sealed**. Nothing in this MVP scores it.

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
python mvp/run.py check            # 51 project tests + 25 Stage 2 tests + headless-browser dashboard check
```

`build` is deterministic: rerunning it leaves every file under `native_backtest/out/` byte-identical. Only the dashboard file's build timestamp changes.

## Using the dashboard

- **Overview** — the four approaches, growth of $1, a metric scoreboard with the best value per row marked, allocations over time, and what the results do and do not show.
- **Approaches** — a side-by-side summary, then one page per approach: how it works, development results against its own benchmark, its signals and forecasts, weights, faithfulness checks and limitations. Expandable sections hold the detail.
- **Timeline** — training, development, the sealed historical test and live tracking, and the two stages of checking (native reproduction, then common evaluation).
- **How it's scored** — the shared rules, what stays each approach's own, and why this is not a controlled comparison.
- Every term with an **i** has a one-sentence explanation on hover, focus or tap.

## Data contract

The dashboard reads one file, `mvp/data/dashboard.json`, built by `mvp/build_dashboard_data.py` from the decision records in `native_backtest/out/decisions/` through the shared evaluator (`native_backtest/framework/`). Its tests are in `mvp/tests/test_dashboard_data.py`:

- the four display names, with no internal codes;
- only months before 2023-01;
- every metric equal to the committed development report;
- Causal RAG without results, and its demo marked `is_mock: true`;
- no text from the claims dataset.

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
