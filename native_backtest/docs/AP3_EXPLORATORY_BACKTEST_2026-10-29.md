# Agentic Causal RAG — complete exploratory development backtest (qwen3:4b) — 2026-10-29

**Status: EXPLORATORY — RELIABILITY GATES FAILED.**
Both pre-registered reliability gates fail. The thresholds, prompts, model, agents, evidence and allocation
methodology are unchanged; nothing here is validated, and nothing here is evidence that the agents are reliable or
that AI adds investment value. The protected window 2023-01..2026-08 was never opened. Additional cost: **$0**.

---

## 1. What was run

The free-GPU replay completed all **95 of 95** agent months (2015-02..2022-12) on Kaggle, under agent protocol
1.1, fingerprint `983e4b398c4a09ac`, repository commit `186091c`. Genuine local inference only:

| | |
|---|---|
| Model calls | 2,726 |
| Input / output tokens | 6,061,843 / 1,632,064 |
| Model time | 117,097 s (≈32.5 h across 4 workers) |
| Invalid responses | 94 |
| Cost | **$0.00** |

Branch `ap3-qwen3-runs`, written 2026-10-29T23:58Z, imported and validated here: genuine outputs only, pinned
model `qwen3:4b@359d7dd4bcda`, development months only, complete status features, record hash chain intact.

**The gates still fail, with their real values:**

| Gate | Check | Measured | Threshold | Pass |
|---|---|---|---|---|
| G3b | accuracy | 0.5667 | ≥ 0.80 | no |
| G3b | opposite-direction errors | 2 | ≤ 1 | no |
| G3a | schema-valid call rate | 0.9771 | ≥ 0.98 | no |
| G3a | failed months | 0 | ≤ 1 | yes |
| G3a | point-in-time violations | 0 | 0 | yes |

The G3a shortfall is entirely the vendored CauseTrace assessor (0.9401); Protofin's own Hypothesis and Testing
Agents were schema-valid on every call.

## 2. Coverage, honestly stated

| | |
|---|---|
| Agent months present | 95 of 95 |
| Scored development months | 46 of 46 |
| Months with at least one hypothesis | **45 of 46** |
| Months with an agent failure | 0 |
| Hypotheses tested | 459 |
| Failed tests | 104 |
| Assessments | Supported 202 · Contradicted 28 · **Insufficient 229** |

**2021-08 produced no hypothesis.** The existing failure policy gives that month zero status features, so the
allocator falls back to its prior. That is disclosed, not hidden, and no return was invented for it.

Insufficient is the largest single verdict (50% of assessments). It is never counted as support.

## 3. The pipeline that was run

Hypothesis Agent → CauseTrace knowledge graph → Testing Agent → signal encoding → walk-forward ridge →
Black–Litterman → native allocation → shared evaluator. Nothing was modified.

- **Encoding.** Each month's assessments become signed counts per asset (`F_S`, `F_C`, `F_I`). The categories are
  never treated as magnitudes.
- **Forecasting.** Walk-forward ridge over the 8 macro surprises plus the three encoded features, refit monthly on
  past months only, penalty chosen by inner cross-validation.
- **Allocation.** AP3's own Ω, estimated from its own out-of-sample errors, then the same bounded fully invested
  optimiser, 45/35/20 prior, τ 0.05, δ 2.5, 36-month Ledoit–Wolf covariance.

**The agent features are used in a minority of months.** The ridge resolved to the intercept alone in
**75.4%** of asset-months. In **96 of 138** asset-months the Causal RAG forecast is *identical* to the
Deterministic model's — precisely the months where both fell back to the training mean on the same labels. On the
42 asset-months where at least one used its features, the two differ by **47 bp** on average.

## 4. Development results (46 months, 2019-03..2022-12)

| | Deterministic | JEV | **Causal RAG (exploratory)** |
|---|---|---|---|
| Net CER | 3.67% | 4.67% | **5.12%** |
| Annualised excess return | 5.33% | 7.01% | 6.59% |
| Volatility | 11.52% | 13.66% | **10.83%** |
| Sharpe | 0.462 | 0.513 | **0.608** |
| Maximum drawdown | −18.60% | −23.82% | −18.67% |
| Cumulative return | 24.3% | 31.2% | 30.8% |
| Annualised turnover | 0.46× | 0.33× | **1.06×** |

Causal RAG has the highest net CER and Sharpe and the lowest volatility of the three — **and none of it is
statistically supported:**

| Comparison | Net CER difference | 95% interval | p |
|---|---|---|---|
| Causal RAG − Deterministic | +1.46 pp | [−0.29, +4.75] | 0.472 |
| Causal RAG − JEV | +0.45 pp | [−2.99, +4.12] | 0.824 |
| Causal RAG − its own 45/35/20 control | +1.35 pp | [−0.35, +4.53] | 0.544 |

Every interval straddles zero. It trades **three times** as much as the Deterministic model to get there.

## 5. Three reasons not to read this as a win

1. **The gates failed.** The Testing Agent is right 56.7% of the time on the reliability fixtures and makes two
   opposite-direction errors. A portfolio built on assessments of that quality is a pipeline demonstration.
2. **The placebo test points the wrong way.** Permuting the status features 200 times, the genuine features'
   improvement is **−3.1e-05**, at the **3.5th percentile** of the permutation distribution: the real agent
   signal forecast *worse* than 96.5% of random relabelings. Whatever produced the CER advantage, the evidence
   does not support it being forecast skill from the agents.
3. **The forecasts are poorly calibrated.** The calibration slope is **0.299**, far below 1: the model's
   forecasts are far more confident than the outcomes justify.

Taken together: Causal RAG's portfolio did well in this sample, but its *signal* shows no evidence of predictive
content. The most defensible reading is that a larger, differently-shaped allocation happened to suit 2019–2022,
not that the agents forecast well.

## 6. Forecast-to-allocation sensitivity (now complete for all four)

Run under the same pre-registration, scaling only the calibrated numerical view —
`adjusted = prior + λ × (original − prior)` — at `native_backtest/ap3/allocation.py::weights_for_months`'s
`bl_posterior` argument `q`. The categorical assessments were never scaled. 1× reproduces the archived native
weights to **2.36e-15** and the archived returns to **1.80e-16**.

| Scenario | Net CER | Volatility | Turnover | Cost | Active weight | Months a limit binds |
|---|---|---|---|---|---|---|
| 0× Neutral | 3.637% | 11.3% | 0.27× | 2.7 bp | 1.47 pp | 0 |
| 0.5× Weaker | 4.663% | 10.9% | 0.72× | 7.2 bp | 2.90 pp | 2 |
| **1× Original** | **5.122%** | **10.8%** | **1.06×** | **10.6 bp** | **4.95 pp** | **3** |
| 2× Stronger | 5.588% | 11.0% | 1.36× | 13.6 bp | 7.83 pp | **10** |

| Comparison | Net CER difference | 95% interval | p |
|---|---|---|---|
| 0× − 1× | −1.486 pp | [−4.566, +0.206] | 0.229 |
| 0.5× − 1× | −0.460 pp | [−1.496, +0.160] | 0.319 |
| 2× − 1× | +0.466 pp | [−0.174, +1.476] | 0.242 |

**Where its signal is attenuated: the posterior, like the Deterministic model.** Causal RAG's view sits
**47.17 bp** a month from its own prior — the largest of the three Black–Litterman allocators — but the posterior
keeps only **3.71%** of it. Its position limits bind in 3 of 46 months at 1×, rising to 10 at 2×.

The difference from the Deterministic model is not the retention share (3.7% against 3.6%) but the **size of the
view**: 47.2 bp against 35.5 bp, producing a 4.95 pp active position against 2.07 pp, and a signal that is
**5.51%** of monthly return variance against 0.17%.

## 7. Does Causal RAG break the Deterministic/JEV similarity?

| Pair | 1× returns | 0× returns | Signal parts |
|---|---|---|---|
| Deterministic vs JEV | 0.9711 | 0.9837 | −0.2791 |
| **Deterministic vs Causal RAG** | **0.9733** | **1.0000** | **−0.1889** |
| JEV vs Causal RAG | 0.9800 | 0.9837 | +0.6930 |

Causal RAG shares the Deterministic model's *exact* signal-free portfolio (both are the same 45/35/20 allocator,
so their 0× series correlate at 1.0000). Their 1× series still correlate at 0.9733 — the same story as before:
**the baseline exposure dominates, and the signal parts mildly disagree.** A third architecture, with genuinely
different inputs, lands in the same place.

## 8. Limitations

1. Both reliability gates fail. Nothing here is validated.
2. qwen3:4b is a documented substitution for the planned Llama 3.1 70B. A 4B model is not a reproduction of a 70B
   system, and the gate failures may be the substitution rather than the architecture.
3. 46 development months. No comparison in this document is statistically clear.
4. The placebo test gives evidence *against* predictive content in the agent features.
5. The ridge used the intercept alone in 75.4% of asset-months, and 70% of its forecasts are identical to the
   Deterministic model's.
6. 2021-08 has no hypothesis and falls back to the prior.
7. Turnover is 1.06× a year against 0.46× and 0.33× — a materially more expensive strategy.
8. The protected window stays sealed; none of this licenses opening it.

## 9. Reproducing this

```bash
python -m native_backtest.scripts.ap3_free_import          # imports from branch ap3-qwen3-runs and evaluates
python -m native_backtest.scripts.forecast_to_allocation   # scenarios for all four, including AP3
python -m native_backtest.scripts.audit_forecast_to_allocation   # 485 independent checks
python mvp/build_dashboard_data.py
```

Outputs: `native_backtest/out/ap3/qwen3_runs/evaluation/` (predictions, weights, evaluation.json, the matched
development simulation), `native_backtest/out/decisions/AP3_qwen3_reduced_evidence.jsonl`, and
`native_backtest/out/sensitivity/ap3_{transmission_trace,scenario_returns}.csv`.
