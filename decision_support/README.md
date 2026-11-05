# Decision support harness

Evidence plugins, one gate. A plugin is anything that, given the masked month, returns a typed answer:
a stated view per fund, optional numeric features, a self-reported confidence and a readable trace.
The harness scores every plugin with the same calibration, trust (Ω), Black-Litterman, optimizer,
accounting and bootstrap as every other plugin (`level_playing_field/run.py`), against doing nothing
and a placebo. Plugins never see labels or each other's answers.

The four approaches are the first four plugins; the placebo is the fifth. The scores reproduce
`level_playing_field/out` exactly (the tests check each plugin's table against the level field's loaders).

```
python -m decision_support list
python -m decision_support score --config config.json     --mapping both   # SPY/TLT 60/40
python -m decision_support score --config config_3f.json  --mapping both   # SPY/IEF/LQD 45/35/20
python -m decision_support trace jev spy_tlt 2019-03                       # one answer, as a reader sees it
python -m pytest decision_support
```

Outputs in `decision_support/out/`: `<tag>_<mapping>.json` (scores, contrasts, plugin status, monthly
net excess returns per plugin) and `<tag>_<mapping>_monthly.csv` (per plugin and month: Q, Ω, π, μ,
weights, chosen α or k). The monthly file is the audit chain a manager can read.

## The contract (`contract.py`)

```python
Answer(month="2019-03",                      # the month-end at which the answer was known
       stated={"SPY": -1.23, "TLT": 1.23},   # signed view per fund, any units; only direction and relative size matter
       features={"p_stocks_beat_bonds": 0.37, "expected_tilt": -1.23, "confidence": 0.46},
       confidence=0.46,                       # 0..1, recorded, never used in the weights
       trace={...})                           # what a reader sees: texts, probabilities, chains
```

- `stated` feeds the "as stated" rule: Q = avg + k·(stated − mean), k ≥ 0 fitted on past months, so a
  plugin's direction is never inverted and an uninformative plugin collapses to the placebo (k = 0).
- `features` feed the "either way" rule: Stage 2's purged expanding Ridge, which may learn any sign.
- `confidence` and `trace` move nothing. Trust comes from the record: Ω = mean squared error of the
  plugin's own past one-step views. That is deliberate: it treats a model with no self-reported
  confidence (the deterministic model) and one with (Jev) by the same rule.

A plugin that states no direction (`states_direction: false`) is scored by the learner under both rules.

## Adding a plugin

1. Copy a folder under `decision_support/plugins/`, e.g. `jev/`. The folder name is the plugin name.
2. Edit `manifest.json`: title, description, author, `fund_sets` it supports, `data` paths of its saved
   answers per fund set, `exploratory` (true keeps it out of the primary Holm family).
3. In `plugin.py`, `build(root, manifest)` returns an object with `.manifest` and
   `.answers(fund_set) -> list[Answer]`. Read saved answers from disk; the harness runs no live model.
4. `python -m pytest decision_support` then `python -m decision_support score`.

The gate: answers must pass `validate` (one per month, a stated view for every fund, confidence in
[0, 1]); a plugin with under 90% coverage of the scored months is skipped and reported; the scorer
refuses to run into the sealed window (2023-01 onward). Every new plugin is another draw on the same
46 months, so the Holm correction runs across the primary family and a new plugin's score should be
read beside the placebo's, not alone.

## Plugins

| name | states a direction | source of answers | status |
|---|---|---|---|
| `det` | no (features only) | Stage 2 macro panel, 8 surprise z-scores | primary |
| `committee` | yes, the CIO's expected returns | `level_playing_field/data/committee_{1m,3f}.json` | primary |
| `jev` | yes, expected tilt / P(best) − ⅓ | `level_playing_field/data/jev_{1m,3f}.json` | primary |
| `causal_rag` | yes, signed count of Supported chains | `level_playing_field/data/causal_rag_qwen3{,_3f}.json` | exploratory |
| `placebo` | no signal | — | the control |

## What the harness is not

It is not a forecaster and not a product. It is the rule that lets people add evidence to an
allocation process without fooling themselves: the same masked inputs, the same pipeline, a
placebo, confidence intervals, a sealed window. On 2019–2022 no plugin beats doing nothing; the
harness is what makes that statement checkable.
