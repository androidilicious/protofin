# One common universe for all three approaches

**Date:** 30 October 2026 · **Pre-registration:** [`native_backtest/config/jev_common_universe_respecification_v1.json`](../config/jev_common_universe_respecification_v1.json) (committed at `0c87d0e`, before any result below was computed) · **Framework config:** v1.9 → v1.10

## What changed

Until now the Agentic Workflow held two funds, SPY and TLT, while the Deterministic model and Causal RAG held
three, SPY, IEF and LQD. A net-CER difference between them therefore mixed forecasting with the choice of bond
fund, and TLT's duration is roughly twice IEF's with no credit exposure at all.

All three approaches now hold the same three funds. The Agentic Workflow's allocation is **re-expressed**, not
re-run:

- Its saved answers, its prompts, its model and its native mechanism are untouched. Nothing was re-asked and no
  inference was paid for.
- The only number the engine decides is the stock weight, and it **carries over exactly** — the largest difference
  across all 272 months is 0.0.
- The bond remainder is split at one frozen ratio, **63.6364% IEF / 36.3636% LQD**, which is the Deterministic
  model's own 35:20 neutral sleeve. It is identical in every month, so the Agentic Workflow still never chooses
  between Treasuries and corporate bonds. That is a rule, not a forecast.
- The native SPY/TLT records stay in the repository under their own names
  (`AP2B_native_spy_tlt.jsonl`, `AP2A_native_spy_tlt.jsonl`, `AP2_COMBO_native_spy_tlt.jsonl`) and still back the
  native-to-common bridge below.

This reverses design decision 1 of [`NATIVE_BEHAVIOUR_AUDIT.md`](NATIVE_BEHAVIOUR_AUDIT.md) ("each system runs on
its native universe"), which was recorded as *not adopted*. The reversal is recorded there too.

## The universe change is its own measured step

The native-to-common ladder gains a rung, so the effect of the re-specification is visible rather than folded into
another adjustment. Net CER, 46 development months:

| Step | JEV | Agent Committee |
|---|---|---|
| V0 as originally scored | 4.14% | 3.83% |
| V1 verified price data | 4.14% | 3.83% |
| V2 trade next trading day | 4.66% | 5.14% |
| V3 shared trading costs | 4.64% | 5.08% |
| V4 shared cash rate | 4.67% | 5.11% |
| **V5 same three funds — reported** | **5.04%** | **5.73%** |

The universe step adds **+0.36 pts** to JEV and **+0.62 pts** to the Committee. The direction is not a surprise:
over 2019–2022 the bond leg's return is what changed, and long Treasuries fell harder in 2022 than intermediate
Treasuries and corporate bonds. This is an artefact of which bond fund the approach is deemed to hold, which is
exactly why holding the comparison fixed matters.

## Development results on the common universe (46 months, 2019-03 – 2022-12)

| | Net CER | Sharpe | Worst fall | Volatility | Turnover |
|---|---|---|---|---|---|
| Deterministic (baseline) | 3.67% | 0.46 | −18.6% | 11.5% | 46% |
| Agentic Workflow (JEV) | 5.04% | 0.54 | −19.5% | 13.6% | 32% |
| Agentic Causal RAG | 5.12% | 0.61 | −18.7% | 10.8% | 106% |
| Agent Committee (within-approach) | 5.73% | 0.61 | −19.2% | 12.7% | 113% |

Primary contrasts, each a paired block bootstrap (6-month blocks, 5,000 draws, seed 20261027):

| Contrast | Difference | 95% range | p |
|---|---|---|---|
| JEV − Deterministic | +1.373 pts | −0.73 to +3.58 | 0.198 |
| Causal RAG − Deterministic | +1.457 pts | −0.29 to +4.75 | 0.472 |
| Causal RAG − JEV | +0.084 pts | −3.35 to +4.56 | 0.977 |

**None is statistically clear.** Two things are worth saying plainly:

1. The two agentic approaches are now **indistinguishable from each other** (+0.08 pts, p = 0.98). Before the
   re-specification the gap read +0.45 pts. Most of what looked like a difference between two AI approaches was
   the bond fund each was deemed to hold.
2. JEV's lead over the Deterministic baseline widened from +1.01 to +1.373 pts, and its p-value fell from 0.63 to
   0.198. It is still not significant, and the reason the lead exists has not changed — see the next section.

## Where the Agentic Workflow's lead comes from

With both no-signal portfolios now holding the same bond composition, the attribution of the +1.373 pt gap is
cleaner than before:

| Part | Contribution |
|---|---|
| Starting stock weight (60% against 45%) | **+1.12 pts** |
| Bond composition | **exactly 0.00 pts** |
| JEV's own signals, against its own no-signal portfolio | +0.15 pts |
| The Deterministic signals' small loss | +0.11 pts |
| Total | +1.37 pts |

The bond term is zero **by construction**, not by chance: the two neutral mixes share their bond composition, so
the term is identically zero in every bootstrap replication. Both the analysis and its independent audit detect
that and report no p-value for it rather than one computed from floating-point dust.

So the gap is still almost entirely the neutral stance. Four fifths of it is the decision to start from 60% stocks
rather than 45% — a parameter of the approach, taken before any forecast is made. JEV's forecasting contributes
+0.15 pts (95% range −0.47 to +0.98, p = 0.77).

## What the re-specification does not fix

The mapping removes one difference and leaves the others in place. All of these are still disclosed wherever the
approaches are compared:

- **The question's horizon.** The Agentic Workflow asks a 12-month stocks-versus-bonds question; the other two
  forecast each asset one month ahead. That is a property of the saved prompts, which cannot be changed without
  re-running paid inference, and relabelling it would be false.
- **The neutral stance.** 60% stocks against 45%. This is the largest remaining driver of the gap, and it is
  reported as such rather than netted out.
- **No view on bonds against bonds.** The Agentic Workflow's bond split is a constant. The Committee's case is a
  larger step still: its view is specific to long Treasuries, and the portfolio now expresses it over intermediate
  Treasuries and corporate bonds instead.
- **Different information.** Data surprises, market snapshots, research papers and dated documents.
- **The mechanism.** A capped tilt is not Black–Litterman.
- **Hindsight.** JEV's and the Committee's historical answers were recorded after the fact by models whose
  training cut-offs postdate the development window.

The frozen passive 60/40 SPY/IEF reference is **unchanged**, numerically and in its fingerprint. One descriptive
sentence in its frozen specification says it is "closer to the Deterministic and Causal RAG universes (SPY/IEF/LQD)
than to JEV's (SPY/TLT)". That described the world on 28 October, when it was frozen. It is superseded by this
document and deliberately left as written, because editing a frozen approval record to match a later change would
destroy the record.

## Verification

| Check | Result |
|---|---|
| Stock weight carried over, 272 months × 3 record sets | max difference **0.0** |
| Weights fully invested | max \|Σw − 1\| **1.1e-16** |
| Non-negative weights | min weight **0.073** |
| One bond ratio in every month | **1** distinct value |
| Saved answers, confidence, decision times, cut-offs | byte-identical to the native records |
| Combination = average of its mapped components | max difference **5.6e-17** |
| 1× sensitivity scenario reproduces the archived allocation | **true** for all four allocators |
| Independent sensitivity audit | **485 checks, 0 failures** |
| Independent signal-value audit | **275 checks, 0 failures** |
| Independent portfolio-integrity audit | **no implementation error found** |
| Protected window | **sealed**; not scored, not read |
| Model calls, spend | **0**, **$0** |

## Files

- Pre-registration: `native_backtest/config/jev_common_universe_respecification_v1.json`
- Mapping: `native_backtest/scripts/jev_common_universe.py`
- Guards: `native_backtest/tests/test_common_universe.py`
- Sensitivity pre-registration amendment 1.0 → 1.1 (controls only):
  `native_backtest/config/forecast_to_allocation_sensitivity_preregistration_v1.json`
