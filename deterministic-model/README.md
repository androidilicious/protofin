# Deterministic Macro Allocation Model

This directory contains the deterministic quantitative baseline for the Protofin capstone project. It turns point-in-time macroeconomic surprises into Growth and Inflation signals, forecasts next-month Equity, Treasury, and Investment-Grade Credit returns with expanding-window Ridge models, and converts those forecasts into constrained portfolio weights through Black–Litterman.

The model is intentionally deterministic: it does not use RAG or autonomous agents.

## Contents

- `deterministic_mvp/` — Python model, tests, data preparation, generated outputs, and the interactive local demonstration site.
- `deterministic_data2 - Oct26.xlsx` — updated economic-release dataset used by the current MVP and signal research.
- `deterministic_data1.xlsx` — retained earlier source for the original MVP and regression checks.
- `determinisitic_data1_status_description.docx` — source-data description.

## Run the model

```bash
cd deterministic_mvp
python -m pip install -r requirements.txt
python src/deterministic_mvp.py --workbook "../deterministic_data2 - Oct26.xlsx" --supplemental supplemental_monthly.csv --output-dir outputs
```

Run the tests with:

```bash
python -m unittest discover -s tests -v
```

## Open the demonstration site

After generating the model outputs, rebuild the browser data bundle:

```bash
cd deterministic_mvp/site
node scripts/build-data.mjs
```

Then open `deterministic_mvp/site/dist/index.html` in a browser. The site includes the surprise calculation, system architecture, historical decision replay, Ridge forecasts, Black–Litterman adjustment, portfolio weights, and backtest evidence.

## Signal research (November 2026)

From `deterministic_mvp/`:

```bash
python src/research_backtest.py
node site/scripts/build-research.mjs "$PWD/research/outputs"
python -m unittest discover -s tests -v
python -m http.server 4173 --directory site/dist
```

Open `http://localhost:4173/research.html` for the interactive research page.
The committed input histories and output snapshots permit reproduction without
new downloads. The research tests three added signals separately—unemployment
claims, credit spreads, and the yield curve—across the COVID shock, COVID recovery,
and 2022, plus 33 rolling 12-month windows. Passive references are fixed 45/35/20,
60/40, and SPY-only. Revised economic histories make the results exploratory.

The live site is https://macro-surprise-mvp.yangqy03.chatgpt.site/research.html.
See `deterministic_mvp/research/README.md` for timing, definitions, limitations,
and the difference between the research rerun and the older MVP results.

## Point-in-time design

- Surprise standardization uses only earlier release errors.
- Ridge models train and tune on past observations only.
- Black–Litterman covariance and view uncertainty use only history available at each decision date.
- Subsequent realized returns are evaluation evidence and are not used as decision inputs.
