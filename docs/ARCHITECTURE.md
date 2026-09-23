# Protofin architecture note

Written for teammates and reviewers who need to know how the pieces fit, what is deterministic, and what is being evaluated.

## One sentence

An LLM committee supplies traceable evidence and return views; deterministic mathematics decides how much to trust them and what to hold.

## Division of labour

| Layer | Deterministic? | Code | Evaluated by |
| --- | --- | --- | --- |
| Signals: prices, rates, rate shock, EPU/GPR regime, FOMC stance | Yes | `signals.py`, `macro_indexes.py`, `news_pipeline.py` | `research/fomc_validation.py`; regime frequency (29% of days since 2004) |
| Committee: economist ∥ risk manager → CIO | No (temperature 0, but a model call) | `committee.py`, `site/js/pipeline.js` | Masked replay probes, forecast-skill check, forward log |
| Blend and allocate: Black-Litterman, constrained optimizer, trade policy | Yes | `allocation.py`, `site/js/allocation.js` | `research/allocation_sensitivity.py`, JS/Python parity test, backtests |

## Flow

```
Yahoo Finance ─┐
EPU / GPR ─────┼─► signals.collect() ─► three prompts
FOMC archive ──┘                          │
                     ┌────────────────────┴────────────────────┐
                     ▼                                         ▼
              Economist (independent)                 Risk manager (independent)
                     └────────────────────┬────────────────────┘
                                          ▼
                                   CIO: both views verbatim → SPY %, TLT %, confidence
                                          ▼
                          regime elevated? → confidence −1 notch
                                          ▼
                    views − cash → Black-Litterman with 60/40 prior → optimizer (40–80% SPY)
                                          ▼
                              (prototype) target applied → rendered, logged
```

The two persona calls are concurrent when made against an API. On a single local GPU they are independent but execute one after the other. The CIO never runs before both are back.

## Why the mathematics is shaped this way

A worked, plain-language walk through one run, with the arithmetic, is in [HOW_IT_WORKS.md](HOW_IT_WORKS.md); the site's `how.html` fills the same steps from any saved run.

- **Views as excess returns.** The Black-Litterman prior is an implied excess return (δ Σ w), so the committee's total-return views are reduced by the cash rate before blending. Mixing the two scales was an early bug.
- **Confidence scales Ω.** High halves the view uncertainty, Low doubles it. Because P is the identity here, τ cancels and the posterior is a weighted average of prior and view; changing τ alone can't stabilise anything.
- **Regime gate only lowers trust.** A stressed news environment makes every forecast less reliable; it never makes a view more credible.
- **Closed-form constrained optimum.** With two assets the long-only, fully invested optimum inside the tilt band is exact. The earlier clip-then-renormalise step could flip 100/0 to 0/100 on a 0.02-point change in a view.
- **Trade policy (off in prototype mode).** A 2pp no-trade band and a 10pp move cap against the previous holding, plus an evidence fingerprint so a repeated refresh cannot consume another adjustment.

## Evaluation principles

1. **Same inputs live and in backtest.** Every decision input has full point-in-time history back to 2008. Headlines are shown but never used, because they have none.
2. **No unmasked historical LLM runs.** A current model has read the past. The masked replay strips dates, names, levels and headlines, and two probes (year guess, sign flip) measure whether the mask holds.
3. **Controls before signals.** Fixed 60/40, prior-only and the trade policy are always in the comparison, on identical dates and costs, so any claimed AI value is net of what the rules already deliver.
4. **Log everything.** Each live run appends prompts, raw replies and every intermediate quantity; the forward log is the only honest test of the news channel and accumulates one run at a time.

## What the September 2026 evidence says

- The rules matched fixed 60/40's return with a quarter of the trades.
- gpt-4o's masked views had a built-in bullish tilt and no forecast skill; net of costs they returned less than 60/40 and traded four times as much.
- Gating trust by the uncertainty regime recovered most of that loss.
- The FOMC hawkishness index tracks stance, not surprise.

## Open items

- Replace the yield-deviation shock with SVAR-identified surprises and price them with local projections; that becomes a quantitative view channel with its own error bar.
- Calibrate self-reported confidence against realised errors.
- Three-month horizon and monthly decisions, as the team agreed; the prompts currently ask for 12-month views.
- An archived, licensed news source if the text channel is to be evaluated.
