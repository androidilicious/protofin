# Deterministic signal research

The original website remains at `dist/index.html`. New experiments are at
`dist/research.html`. These are development experiments, not a replacement
for the locked model or an evaluation of 2023 onward.

Local model source:
`determinisitic model/deterministic_mvp/src/research_backtest.py`.

The copied code in this directory imports the existing deterministic model's
release cleaning, macro features, Black–Litterman, and constrained optimizer.
The reproducible original run and raw downloads live in `deterministic_mvp/research/`.

## Rebuild

1. In deterministic_mvp, download adjusted daily SPY/IEF/LQD prices beginning
   January 2010 through January 3, 2023 from Yahoo Finance chart endpoints.
   Store as `research/raw/{spy,ief,lqd}_history.json`.
2. Download FRED graph CSVs for ICSA, BAA10Y and T10Y3M, January 2014 through
   December 2022, as `research/raw/{claims,credit,curve}.csv`.
3. Retain the Oct 26 workbook, ANFCI CSV and GPR DTA from the original project.
4. Run `python3 src/research_backtest.py` then
   `python3 -m unittest discover -s tests -v`.
5. Run the site's `scripts/build-research.mjs` with the absolute path to
   `deterministic_mvp/research/outputs` as its argument.

## Method

- Core model and three independent additions: claims, credit spread, yield curve.
- Expanding training from February 2015, at least 36 completed targets.
- Five fixed Ridge penalties tuned in chronological inner folds. Imputation and
  scaling are fit inside each training fold. No episode-specific tuning.
- At least 12 prior out-of-sample forecast errors for view uncertainty.
- Same BL settings (tau 0.05, risk aversion 2.5), starting mix (45/35/20),
  bounds (SPY 20–70, IEF 15–60, LQD 10–40), 1% grid, turnover penalty.
- Decision: 8pm New York on last trading day. Entry: following trading-day
  adjusted close. Exit: next rebalance adjusted close. Holding month is entry month.
- Trading costs: 5bp per dollar traded, based on full absolute weight changes
  from drifted pretrade weights. Cost deducted before the holding-period return.
  Initial allocations are treated as already funded, without entry funding costs.
- Daily buy-and-hold paths and daily peak-to-trough drawdown. Annualized return
  and zero-cash arithmetic Sharpe omitted for episodes shorter than 12 months.
- Passive 45/35/20, 60/40 and SPY-only references share execution/cost rules.
- COVID shock: Feb–Apr 2020 holding months. Recovery: May–Dec 2020.
  Inflation/rate shock: Jan–Dec 2022. December exits on January 3, 2023; this
  exit quote closes 2022, rather than evaluating a January 2023 strategy decision.
- Rolling 12-month windows overlap and are descriptive, not independent trials.

## Limits and differences from the original site

Longer ETF history enables the COVID experiment. Exact next-trading-close
execution, stricter target availability, fold-local imputation, and daily
drawdown differ from the earlier approximate monthly MVP. Every research
variant, including the baseline, is recomputed identically. Compare new signals
with this research baseline, not the older site's numerical results.

Claims, ANFCI and GPR use revised histories with assumed availability lags,
not a full real-time vintage archive. The policy-path workbook starts September
2019; earlier missing values use training-only medians (zero if the entire
training column is missing). No policy history is synthesized. Small samples,
limited recessions, and overlapping rolling windows cannot establish robustness.
The experiments do not automatically select a new production model.
