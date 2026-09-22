# Protofin MVP: LLM views inside a constrained Black-Litterman allocator

A single-page dashboard that runs one pipeline end to end:

1. **Data ingestion** (Yahoo Finance): 10-year Treasury yield, SPY and TLT price history. The single Yahoo headline is kept only for comparison; the news layer below replaces it.
   **Policy text** (`news_pipeline.py`): the latest FOMC statement from the Fed's archive, scored hawkish/dovish by an FOMC-RoBERTa classifier. This is in the decision because it is archived since 2008 and therefore backtestable.
   **Headlines** (display only by default): macro headlines from Google News RSS scored by FinBERT plus an LLM structured extraction with quotes. They have no archive, so `HEADLINES_MODE=display` keeps them off the view, the fingerprint and the allocation; `decide` puts them in for demos; `off` skips the fetch.
2. **Rate-shock signal**: current 10Y yield minus its 3-month average, in basis points.
   **Uncertainty regime**: the Baker-Bloom-Davis Economic Policy Uncertainty index (EPU) and the Caldara-Iacoviello Geopolitical Risk index (GPR), as 30-day means ranked against 10 years of history. The regime is *elevated* when either index is in its top decile or both are in their top quintile.
3. **Agent debate** (OpenAI): Economist, Risk Manager and CIO produce 12-month return forecasts for SPY and TLT plus a confidence label.
4. **Black-Litterman posterior**: the forecasts are converted to excess returns over the 13-week T-bill yield and blended with a 60/40 equilibrium prior; confidence scales the view uncertainty. An elevated uncertainty regime downgrades the reported confidence one notch before it is used. It never upgrades it.
5. **Constrained allocation**: a long-only, fully invested mean-variance optimum inside a 40–80% SPY tilt band.

**Prototype mode** (default, `PROTOTYPE_MODE=1`): every click is a fresh run. There is no evidence cache, no stored holding, and the optimizer target is applied directly. Set `PROTOTYPE_MODE=0` to restore the stability controls below (fingerprint cache, 2pp no-trade band, 10pp move cap). The backtester always has them available.

## Run

```
pip install -r requirements.txt          # torch CPU build is enough, see requirements.txt
cp .env.example .env                     # then put your OPENAI_API_KEY in .env (git-ignored)
python news_pipeline.py --backfill       # once: scores FOMC statements 2008+ (downloads ~500 MB of model weights)
python server.py
```

Open <http://127.0.0.1:5000> and click **Initialize Pipeline**. Node.js 18+ is needed only for the diagram rebuild (`docs/build_flow_diagram.py`); without it the dashboard still runs and shows the last committed diagram.

### What is git-ignored

`.env`, `state/`, `runs/`, downloaded data under `data/` (except the derived FOMC index), the large regenerable backtest outputs, and the machine-specific `.claude/`, `.cursor/`, `.commandcode/`, `.agent/` symlink folders. The vendored archify renderer under `.agents/skills/archify` is committed without its examples and tests.

## Files

| Path | Purpose |
| --- | --- |
| `server.py` | Flask backend and the whole pipeline (`/api/run_pipeline`) |
| `mvp_dashboard.html` | Dashboard served at `/` |
| `state/last_allocation.json` | Last decision, keyed by an evidence fingerprint |
| `runs/pipeline_log.jsonl` | One line per run with every intermediate stage, the prompt and the raw LLM reply |
| `allocation.py` | Allocation math shared by the server and the backtester |
| `macro_indexes.py` | Downloads and caches the daily EPU and GPR indexes, computes percentile ranks and the uncertainty regime |
| `news_pipeline.py` | FOMC statement archive and hawkishness index, live macro headlines with FinBERT sentiment, LLM structured extraction; `--backfill` builds `data/news/fomc_index.csv` |
| `research/fomc_validation.py` | Checks the hawkishness index against same-day yield moves on FOMC days |
| `data/` | Cached index files, refreshed daily |
| `docs/protofin-pipeline.workflow.json`, `docs/build_flow_diagram.py` | Archify diagram of the pipeline. The dashboard pulls the rendered SVG inline (shadow DOM, no iframe) on the left and lights each step while its values appear on the right; the builder rewrites node labels and cards from the last run and the server runs it in the background after every run |
| `research/backtest.py` | Backtest harness: fixed 60/40, prior only, rule views, logged LLM views on identical data and costs |
| `research/backtest_chart.py` | Renders `research/out/backtest_report.html` from the backtest CSVs |
| `research/allocation_sensitivity.py` | Offline diagnostic showing why clip-and-normalize was replaced |
| `app.py`, `cli_app.py` | Earlier Streamlit and CLI prototypes, kept for reference |

## Stability controls (off in prototype mode)

- **Evidence fingerprint.** If the market data and headline are unchanged, the endpoint returns the stored decision without calling the LLM. Use **Force re-run** (or `?force=1`) to bypass.
- **View validation.** Missing or implausible forecasts are rejected and the prior is used alone. Nothing is silently substituted.
- **Constrained optimizer.** Replaces the old clip-then-renormalize step, which could flip 100/0 to 0/100 on a 0.02-point forecast change (see `research/allocation_sensitivity.py`).
- **Trade policy.** Targets within 2pp of the current holding are held. Larger moves are capped at 10pp per new-evidence run.

Policy constants live in `allocation.py`. Set `LLM_MODEL` in `.env` to change the model and `HEADLINES_MODE` (`off`, `display`, `decide`) to control whether headlines enter the decision. The rule: the live pipeline and the backtest consume the same inputs, all of which have full point-in-time history.

## Backtesting

```
python research/backtest.py --start 2004-01-01 --rebalance M --cost-bps 5
python research/backtest_chart.py      # writes research/out/backtest_report.html
```

Five strategies run on identical dates, prices, covariance windows and costs, through the same `allocation.py` code the dashboard uses: fixed 60/40, prior only with the trade policy, a placeholder rate-shock rule, the same rule with the EPU/GPR confidence gate, and the LLM views recorded in the run log (a forward test that grows with every live run). Add `logged_llm_gated` to `--strategies` to gate the logged views too. Historical LLM views are deliberately not simulated: there is no point-in-time news archive, and a current model has read the history it would be forecasting.

## Masked historical replay (leakage-controlled LLM test)

```
python research/masked_replay.py --dry-run --limit 2     # inspect payloads, no API calls
python research/masked_replay.py                          # ~600 calls, resume-safe cache
python research/backtest.py --views-file research/out/masked_views.csv \
    --strategies fixed_60_40,prior_only,masked_llm,masked_llm_gated
python research/backtest_chart.py
```

A current model has read the history it would be forecasting, so a plain replay is contaminated. The masked replay shows the model one payload per month built only from relative and rank features: returns, volatilities, correlation, percentile ranks of rates and of the EPU and GPR indexes, and basis-point changes. No dates, tickers, levels or headlines. Two probes measure whether the mask holds: a year-guess call on every payload (chance is about 13 percent within one year) and a sign-flip mirror test on every sixth month (a leak-free reasoner flips its view symmetrically). Results are in `research/out/masked_replay_summary.json`. This tests the model's quantitative judgment and the allocation rules; it cannot test the news channel the live system uses.

## Known limitations

- The rate-shock signal is a yield deviation, not an identified monetary surprise. It needs an expectations baseline to become one.
- Google News RSS has no archive and no research license, so headline features exist only from the first live run forward. GDELT (2015+) is wired in as the archive source but its public API throttles aggressively. FOMC statements are the only text feature with a full point-in-time history.
- FinBERT measures tone, not macro direction: it scored "more rate hikes needed" as positive. The LLM extraction layer exists to read direction; both are logged so they can be compared.
- Confidence is self-reported by the model. It is not yet calibrated against realized forecast errors.
- The covariance matrix is a trailing 1-year sample estimate with no shrinkage.
- EPU and GPR are as published today. The authors revise history, so backtests on them are point-in-time in construction but not in data vintage.
- Two assets only; the optimizer uses the exact two-asset closed form.
