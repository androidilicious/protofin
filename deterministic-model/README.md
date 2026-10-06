# Deterministic Macro Allocation Model

This directory contains the deterministic quantitative baseline for the Protofin capstone project. It turns point-in-time macroeconomic surprises into Growth and Inflation signals, forecasts next-month Equity, Treasury, and Investment-Grade Credit returns with expanding-window Ridge models, and converts those forecasts into constrained portfolio weights through Black–Litterman.

The model is intentionally deterministic: it does not use RAG or autonomous agents.

## Contents

- `deterministic_mvp/` — Python model, tests, data preparation, generated outputs, and the interactive local demonstration site.
- `deterministic_data1.xlsx` — source economic-release dataset.
- `determinisitic_data1_status_description.docx` — source-data description.

## Run the model

```bash
cd deterministic_mvp
python -m pip install -r requirements.txt
python src/deterministic_mvp.py
```

Run the tests with:

```bash
python -m pytest tests
```

## Open the demonstration site

After generating the model outputs, rebuild the browser data bundle:

```bash
cd deterministic_mvp/site
node scripts/build-data.mjs
```

Then open `deterministic_mvp/site/dist/index.html` in a browser. The site includes the surprise calculation, system architecture, historical decision replay, Ridge forecasts, Black–Litterman adjustment, portfolio weights, and backtest evidence.

## Point-in-time design

- Surprise standardization uses only earlier release errors.
- Ridge models train and tune on past observations only.
- Black–Litterman covariance and view uncertainty use only history available at each decision date.
- Subsequent realized returns are evaluation evidence and are not used as decision inputs.
