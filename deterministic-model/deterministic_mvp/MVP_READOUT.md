# Deterministic model MVP readout

## Delivered scope

The supplied workbook now drives a reproducible, point-in-time quantitative pipeline with no RAG, LLM, or agent component.

The source workbook supports signal construction. The missing state and return series were added from documented public sources, so the complete Ridge, Black–Litterman, and portfolio backtest now runs. The supplemental history is suitable for an MVP, but ANFCI and GPR use their latest revised histories rather than a complete real-time vintage archive.

## Source-data result

- 744 macro release observations across eight indicators.
- 94 monthly feature rows.
- 79 months contain all four Growth and all four Inflation component z-scores.
- Complete macro/policy features run from December 2019 through September 2026.
- Four delayed 2025 releases map to two reference periods on one release date. The pipeline flags those rows and retains one market-observable release rather than duplicating the surprise.
- Each standardized surprise uses only prior forecast errors. The current release never enters its own scale estimate.

Two surprise measures are retained at event level:

- `raw_surprise`: first-release actual minus pre-release survey median.
- `standardized_surprise`: raw surprise divided by the expanding standard deviation of prior forecast errors. This is the signal used in the model.

`survey_dispersion_surprise`, which scales the miss by Bloomberg's cross-sectional survey dispersion, is retained as a diagnostic but is not the baseline model signal.

## Latest complete signal

Decision month: September 2026.

- Growth surprise: -0.128 standard deviations.
- Inflation surprise: +0.170 standard deviations.
- Growth coverage: 4 of 4 indicators.
- Inflation coverage: 4 of 4 indicators.
- 3-month implied policy rate: 3.9288%.
- 6-month implied policy rate: 4.0849%.
- 6m-minus-3m policy-path slope: +0.1561 percentage points.
- Policy observation date: August 31, 2026, so the policy state is one month old at the September decision date.

## Online supplemental data

- Financial conditions: Chicago Fed ANFCI from FRED. A Friday observation is treated as available five calendar days later, then the last available observation is selected at month-end.
- Geopolitical risk: Caldara–Iacoviello Recent GPR. Each reference-month value is lagged to the following decision month because the monthly file is published at the beginning of the next month.
- Equity: SPY dividend-adjusted monthly return.
- Treasury: IEF dividend-adjusted monthly return, representing 7–10 year U.S. Treasuries.
- IG Credit: LQD dividend-adjusted monthly return, representing U.S. dollar investment-grade corporate bonds.

The exact URLs, transformations, retrieval time, and limitations are recorded in `data_sources.csv`.

## Initial model result

The expanding-window evaluation produced 45 realized forecasts per asset and 33 realized portfolio months from the December 2023 decision through the August 2026 realized return.

- Equity forecast RMSE: 3.85%; directional accuracy: 62.2%.
- Treasury forecast RMSE: 2.10%; directional accuracy: 44.4%.
- IG Credit forecast RMSE: 2.51%; directional accuracy: 40.0%.
- Portfolio annualized return after modeled costs: 10.03%.
- Fixed 45/35/20 benchmark annualized return: 9.46%.
- Annualized excess return: 0.57%.
- Portfolio Sharpe ratio: 1.33 versus 1.34 for the fixed benchmark.
- Portfolio maximum drawdown: -3.65% versus -3.56% for the fixed benchmark.

The current result does not establish superior risk-adjusted performance. The small return improvement came with slightly worse Sharpe ratio and drawdown, and the selected Ridge penalty of 100 for all three assets indicates strong shrinkage toward the historical mean.

## Latest model output

For the September 30, 2026 decision date, the next-month forecasts are:

- Equity: +0.678%.
- Treasury: -0.008%.
- IG Credit: -0.118%.

The corresponding constrained allocation is 47% Equity, 31% Treasury, and 22% IG Credit.

## Proposal alignment

Implemented:

- First-release actual minus pre-release median consensus.
- Point-in-time historical standardization.
- Equal-weight Growth and Inflation composites.
- Policy levels, changes, and forward-path slope.
- Prespecified Growth/Inflation interactions with ANFCI and GPR.
- Expanding-window Ridge models for each asset.
- Past-only Ridge penalty selection.
- MAE, RMSE, and directional accuracy.
- Black–Litterman posterior returns with identity view matrix.
- View uncertainty from prior out-of-sample errors.
- Long-only allocation bounds, turnover penalty, and transaction costs.
- Annualized return, volatility, Sharpe ratio, maximum drawdown, turnover, and certainty-equivalent return.

Not included by design:

- RAG, causal graph, agents, LLM explanations, or document retrieval.
- Local projections, which the proposal describes as an auxiliary diagnostic rather than an optimizer input.
- Fabricated proxy returns or synthetic results in the delivered real-data output.

## Remaining research limitations

- Replace latest-revised ANFCI with ALFRED vintage observations for a formal point-in-time test.
- Reconstruct GPR from archived monthly vintages if revisions materially affect the result.
- Confirm whether IEF's 7–10 year duration is the intended Treasury sleeve or replace it with the team's chosen benchmark.
- Treat the 33-month portfolio evaluation as an MVP diagnostic, not a locked confirmatory test.
