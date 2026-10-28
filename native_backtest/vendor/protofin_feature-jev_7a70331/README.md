# Protofin

An AI investment committee inside a rule-based allocator. Two large-language-model personas give independent views on the macro picture, a CIO persona synthesises them, and Black-Litterman plus a constrained optimizer turn that into a stock/bond split. Every step is measurable, every input has full point-in-time history, and the public demo runs entirely in the browser with no API key anywhere.

- **Live demo:** https://protofin.pages.dev
- **Live backtest:** https://protofin.pages.dev/backtest-live.html
- **Static backtest report:** https://protofin.pages.dev/backtest.html
- **How a decision is made, step by step, in plain language:** [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md), or filled in live from any saved run at https://protofin.pages.dev/how.html
- **Design note:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

Duke × BNY CIO Office project, prototype stage, September 2026.

---

## What the pipeline does

| Step | What happens | Where |
| --- | --- | --- |
| 1. Market data | 10-year yield, 13-week T-bill (cash), SPY and TLT daily prices; 1-year covariance | `signals.py` via yfinance |
| 2. Rate shock | 10Y yield minus its 3-month average, in basis points | `signals.py` |
| 3. Uncertainty regime | Economic Policy Uncertainty (Baker-Bloom-Davis) and Geopolitical Risk (Caldara-Iacoviello) as 30-day means ranked against 10 years; *elevated* if either is in its top decile or both in the top quintile | `macro_indexes.py` |
| 4. Policy text | Latest FOMC statement scored hawkish/dovish by an FOMC-RoBERTa classifier | `news_pipeline.py` |
| 5. Committee | Economist and risk manager give independent views in parallel; the CIO reads both and sets 12-month return views plus a confidence label | `committee.py` |
| 6. Blend | Views become excess returns over cash and are blended with the 60/40 equilibrium prior; confidence scales view uncertainty; an elevated regime lowers confidence one notch, never raises it | `allocation.py` |
| 7. Allocate | Exact long-only, fully invested optimum inside a 40–80% SPY band | `allocation.py` |

Headlines (Google News, FinBERT-scored, LLM-classified) are shown on the dashboard but **never enter the decision**, because they have no archive and could not be backtested. The rule throughout: the live system and the backtests consume the same inputs.

### The committee, precisely

Three prompts, three calls, no shared context between the first two.

- **Macro economist**, chief economist at an asset manager. Sees the data, returns a view and its own SPY/TLT numbers.
- **Risk manager**, head of risk at a bank's investment arm. Same data, own view, own numbers. Neither persona sees the other.
- **CIO**. Receives both replies verbatim, says whom it sided with and why, and returns the numbers that feed Black-Litterman: `SPY_Expected_Return_Percent`, `TLT_Expected_Return_Percent`, `CIO_Confidence`.

Saved gpt-4o runs make the first two calls concurrently. The in-browser model can only generate one reply at a time, so there the two views are still independent but execute back to back; the page says which case it is. A malformed CIO reply is rejected and the 60/40 prior is used alone; nothing is ever silently substituted. The dashboard's **Prompt & flow** button shows the exact prompts, the raw replies, and a diagram of the execution.

---

## Running it locally

```
pip install -r requirements.txt          # CPU torch is enough; see requirements.txt
cp .env.example .env                     # put your OPENAI_API_KEY in .env (git-ignored)
python news_pipeline.py --backfill       # once: scores FOMC statements 2008+ (~500 MB model download)
python server.py                         # http://127.0.0.1:5000
```

Node.js 18+ is only needed to rebuild the flow diagram (`docs/build_flow_diagram.py`); without it the dashboard uses the committed one.

**Prototype mode** (default, `PROTOTYPE_MODE=1`): every click is a fresh run, no cache, no stored holding, the optimizer target is applied directly. `PROTOTYPE_MODE=0` restores the stability controls: an evidence-fingerprint cache, a 2pp no-trade band and a 10pp move cap against the previous holding. The backtester always has them available.

Other switches in `.env`: `LLM_MODEL` (default `gpt-4o`), `HEADLINES_MODE` (`off` | `display` | `decide`), `FOMC_MODEL`.

---

## The public site

`site/` is a static build of the same dashboard with the whole decision running in the browser. It is deployed as an independent Cloudflare Pages app.

- **Signals** come from `site/data/signals.json`, built by `scripts/build_signals.py`: market data, shock, regime, FOMC stance, the three committee prompts, and the stored committee replies with their timings. The GitHub Action in `.github/workflows/build-signals.yml` refreshes this file in the repo on weekday evenings; it needs no secrets.
- **Saved runs** live in `site/data/runs/<id>.json` with `index.json` as the list. Each `deploy.cmd` adds one; the page lets visitors pick any of them. `signals.json` is always the latest.
- **Committee providers**: *Saved run* replays the stored gpt-4o replies with their real relative timing; *In-browser model* runs Qwen 2.5 or Llama 3.2 locally through WebLLM (needs WebGPU, about 0.4–1 GB downloaded once, nothing leaves the visitor's machine).
- **Math**: `site/js/allocation.js` is a line-for-line port of `allocation.py`, checked against Python to 1e-16. `site/js/pipeline.js` orchestrates the committee and parses replies with the same rules as `committee.py`.
- **Themes**: light and dark, toggle in the header, `?theme=light`, remembered per device.
- **URL options**: `?provider=browser`, `?run=<id>`, `?theme=light`, `?autorun=1`, `?show=prompt`.

### Deploying

```
npx wrangler login      # once; opens the browser
deploy.cmd              # rebuilds signals + a fresh committee run from the local .env, then publishes site/
```

`wrangler.toml` names the project (`protofin`) and the output folder. Deploys happen from a laptop, so the only credential anywhere is Wrangler's local login.

### Where secrets live

| Secret | Where | Who can read it |
| --- | --- | --- |
| Your OpenAI key, used for local runs and to record the saved committee replies | `.env` on your machine, git-ignored | Only the local scripts |
| The same key, for the live-backtest endpoint only | Cloudflare Pages secret `OPENAI_API_KEY`, set with `npx wrangler pages secret put` | Only `functions/api/committee.js`. It accepts a month index, builds the prompts itself from the committed month data, runs the three persona calls, and returns replies and timings. Rate-limited per visitor address (60 months/day, 12/minute) and site-wide (300 months/day, sized to the free KV write quota) with KV counters; limits are `[vars]` in `wrangler.toml` |
| GitHub | Nothing | The workflow references no secrets |
| Visitors | Nothing | Saved runs need no key; the live endpoint spends the site's budget within the limits above |

---

## Evaluation

### Backtest harness (Python, daily resolution)

```
python research/backtest.py --start 2004-01-01 --rebalance M --cost-bps 5
python research/backtest_chart.py      # research/out/backtest_report.html
```

Strategies on identical dates, prices, covariance windows and costs, through the same `allocation.py`: fixed 60/40; prior only with the trade policy; a placeholder rate-shock rule; the same rule with the EPU/GPR confidence gate; LLM views logged by the live server (a forward test); and, with `--views-file`, the masked-replay views below. Historical LLM views are never simulated with a current model on unmasked data.

### Masked replay (leakage-controlled)

```
python research/masked_replay.py --dry-run --limit 2     # inspect payloads, no API calls
python research/masked_replay.py                          # ~600 calls, resume-safe cache
python research/masked_skill.py                           # forecast-skill check
```

A current model has read the history it would be forecasting. The masked replay shows it one payload per month built only from relative and rank features: returns, volatilities, correlation, percentile ranks of rates and of the uncertainty indexes, basis-point changes. No dates, tickers, levels or headlines. Two probes test the mask: a year-guess call on every payload (chance ≈ 13% within one year) and a sign-flip mirror test on every sixth month. Results are in `research/out/masked_replay_summary.json` and `masked_views.csv`.

Findings from the September 2026 run, 273 months: the mask held except for the 2008 crisis; the model showed a persistent bullish tilt (flipped data only half-flipped its view) and no forecast skill (correlation −0.05 with the realised 12-month spread). In the backtest the AI views returned 8.08% a year against 8.30% for fixed 60/40 with four times the turnover; the EPU/GPR gate recovered most of the gap; the trade policy alone matched 60/40 with a quarter of the trades.

### Live backtest (browser, monthly resolution)

`scripts/build_backtest_months.py` writes `site/data/backtest_months.json`: per month since 2004, the masked payload, the three persona prompts, sigma, cash rate, regime, the realised next-month returns, and the saved gpt-4o view. `site/js/livebacktest.js` steps through the months and decides with one of three committees: the saved gpt-4o views (instant replay), a **live gpt-4o committee through the site's rate-limited endpoint** (economist and risk manager concurrently, then the CIO, about 5 s a month), or the in-browser model (needs WebGPU; small models are often unusable and are retried once with a compact prompt). Each decision is scored on the following month and the page animates growth-of-100 against fixed 60/40 and prior-only with a weights track, a per-month committee panel and a decision log.

### Other checks

- `research/allocation_sensitivity.py`: why clip-and-renormalize was replaced (it could flip 100/0 to 0/100 on a 0.02-point forecast change).
- `research/fomc_validation.py`: the hawkishness index tracks the Fed's stance but has near-zero correlation with same-day yield moves, i.e. it is a stance measure, not a surprise measure.

---

## Repository map

| Path | Purpose |
| --- | --- |
| `server.py` | Flask backend for the local dashboard (`/api/run_pipeline`) |
| `mvp_dashboard.html` | Dashboard source; `site/index.html` is generated from it |
| `signals.py` | Data collection and prompt building shared by the server and the site builder |
| `committee.py` | Persona prompts, tolerant parsers, parallel orchestration |
| `allocation.py` | Black-Litterman, constrained optimizer, trade policy (shared with the backtester) |
| `macro_indexes.py` | EPU and GPR download, percentile ranks, uncertainty regime |
| `news_pipeline.py` | FOMC statement archive and hawkishness index; headlines for display |
| `scripts/build_signals.py` | Builds `site/data/signals.json` and the saved-runs archive |
| `scripts/build_backtest_months.py` | Builds the monthly masked payloads for the live backtest |
| `site/` | Static site: `index.html`, `backtest-live.html`, `backtest.html`, `js/`, `data/` |
| `research/` | Backtester, masked replay, skill and validation scripts; `out/` holds the paid replay results |
| `docs/` | Flow diagram spec and builder, architecture note, screenshot |
| `deploy.cmd`, `wrangler.toml` | One-command publish to Cloudflare Pages |
| `.github/workflows/build-signals.yml` | Weekday signals refresh, no secrets |
| `data/news/fomc_index.csv` | Derived FOMC hawkishness index, committed so a clone works without the classifier |
| `app.py`, `cli_app.py` | Earlier prototypes, kept for reference |

Git-ignored: `.env`, root `state/` and `runs/`, downloaded data under `data/` (except the FOMC index), large regenerable backtest outputs, and the machine-specific `.claude/`, `.cursor/`, `.commandcode/`, `.agent/` symlink folders. The archify renderer under `.agents/skills/archify` is committed without its examples and tests.

---

## Known limitations

- The rate shock is a yield deviation, not an identified monetary surprise; it needs an expectations baseline (for example fed funds futures) to become one.
- Confidence is self-reported by the model and not yet calibrated against realised forecast errors.
- The covariance matrix is a trailing 1-year sample estimate without shrinkage.
- EPU and GPR are published as revised histories, so backtests on them are point-in-time in construction but not in data vintage.
- Google News has no archive; FOMC statements are the only text input with full history. GDELT is wired in as an archive source but its public endpoint throttles.
- Two assets only; the optimizer uses the exact two-asset closed form.
- The in-browser models are small and drift from the output format more often than gpt-4o; the parsers tolerate this, and rejected replies fall back to the prior and are shown verbatim.

## Jev (experimental, `/jev/`)

`site/jev/` replays the answers of TypeSafe's Jev model (`typesafe/jev`, a decision model on Cloudflare Workers AI) for every month since January 2004, recorded once and saved in `site/data/jev_runs.json` (source: `research/out/jev_backtest.json`). Each month Jev saw the same masked payload as the committee and answered two typed questions: the probability that stocks beat bonds over 12 months, and a five-way tilt with a confidence. The tilt adds up to ±3 points to the 60/40 baseline's stock-over-bond edge, weighted by that confidence, then the same optimizer and 40–80% band apply. The page calls no model.

`python research/jev_eval.py` scores the answers against realised 12-month outcomes: no forecasting skill (AUC 0.52, direction right 56% vs 69% for always favouring stocks, and confidence inversely related to accuracy). Kept as a demonstration; the ±1.5/±3 points are illustrative, not calibrated.
