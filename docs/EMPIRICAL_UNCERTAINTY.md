# Empirical view uncertainty (stochastic view calibration)

Status: experimental, off by default. Code: `stochastic_views.py`, `allocation.view_omega`. Tests: `tests/test_empirical_uncertainty.py`.

## Question

How much run-to-run variability does the committee's view carry when the model is allowed to sample (temperature > 0), and can that variability be measured and fed into Black-Litterman's view uncertainty so the allocation stays within an acceptable stability range? Temperature 0 hides this variation. It does not make the view any more correct.

## Procedure

```
one frozen snapshot (the three prompts, which carry every input)
    -> the unchanged committee (economist ∥ risk manager -> CIO), run N times at temperature T
    -> per run r: Q^(r) = (SPY %, TLT %), CIO_Confidence^(r), CIO decision and grounding text
    -> Q = mean over valid runs, s² = sample variance over valid runs
    -> Black-Litterman -> constrained optimizer -> weights
```

Only the sampling changes between runs. The prompts are hashed into a `snapshot_id` so the audit record shows that the input really was the same. Runs that the existing CIO parser rejects are excluded and recorded. With no valid runs, the 60/40 prior is used alone, as before.

## Symbols

| Symbol | Meaning | Where |
| --- | --- | --- |
| Q | The view: the CIO's 12-month total-return forecast per asset, minus cash before blending. In stochastic mode, Q_i = mean_r Q_i^(r). | `committee.parse_cio`, `stochastic_views.aggregate_views` |
| Σ | Annualised 1-year sample covariance of SPY and TLT daily returns | `signals.py` |
| τ | Prior uncertainty scalar, 0.05 | `allocation.TAU` |
| c | Reported-confidence multiplier: High 0.5, Medium 1, Low 2 | `allocation.OMEGA_SCALE` |
| s_i² | Run-to-run sample variance (ddof = 1) of Q_i across valid runs, in decimal² of annual return | `stochastic_views.aggregate_views` |
| Ω | View-uncertainty covariance (P = I, one absolute view per asset) | `allocation.view_omega` |

## Reported confidence (unchanged)

The CIO states High, Medium or Low. The label sets Ω = c · τΣ. Because P = I and Ω is proportional to τΣ, the posterior is a plain weighted average: the view gets 1/(1+c) of the weight (2/3, 1/2 or 1/3). An elevated EPU/GPR regime moves the label down one notch before use (`macro_indexes.downgrade_confidence`).

With N runs, the reported label is the **modal label** over valid runs. Ties go to the lower confidence, so aggregation never adds trust. The per-run labels and their counts are recorded. The label is aggregated first and the regime gate is applied afterwards to that single label, just as in the deterministic path. Because the gate merges Medium and Low, applying it before aggregating could give a different label for some even or larger N, for example High, High, Medium, Low.

## Empirical uncertainty

s_i² is what we *observe*: how much the same agent disagrees with itself on identical input. It is a different quantity from the self-report, and both are kept.

## The Ω formula

```
reported   Ω = c(reported label) · τΣ                 (original rule; Q is the mean view)
empirical  Ω = c(Medium)         · τΣ + diag(s²)      (self-report ignored: neutral c = 1)
combined   Ω = c(reported label) · τΣ + diag(s²)
```

In all three modes the regime gate is applied to the label first. It is an external data signal, not a self-report.

Why this form:

- **Consistent units.** Q is a decimal annual return, and τΣ is the covariance of such returns scaled by τ. s² is the variance of that same quantity, so the two can be added directly. No free scaling constant is introduced.
- **Additive variances.** The reported term is read as the agent's systematic view error and s² as independent sampling noise. The variance of a sum of independent errors is the sum of the variances. **The independence assumption is the experimental calibration choice.** It is not an established result, and it gets no weight parameter (no arbitrary 0.5/0.5 mix).
- **Why not Ω = diag(s²) alone.** The raw run-to-run variance is typically one to two orders of magnitude smaller than τΣ_ii. Used alone, it would give near-infinite trust to any agent that repeats itself, even a confidently wrong one. Stability is not accuracy. Keeping the c·τΣ baseline in every mode keeps Ω on the scale the rest of the model was built for.
- **Diagonal.** Off-diagonal run-to-run covariance is left out. With N ≈ 5 its estimate is mostly noise, and the per-asset variances are the stated quantity of interest.
- **No numerical floor is needed.** c·τΣ is positive definite, so identical runs (s² = 0) give exactly the reported Ω and never a singular matrix. Negative or non-finite variances are rejected with an error.

With fewer than 2 valid runs, s² is undefined. The empirical and combined modes then fall back to reported, and the result says so.

### Consequences to keep in mind

- **τ no longer cancels.** With Ω ∝ τΣ, τ drops out of the posterior. Once diag(s²) is added, the relative size of s² against τΣ_ii matters, so τ = 0.05 now affects how strongly dispersion moves the allocation.
- **Direction.** Larger s² always increases the posterior uncertainty of the mean in the Loewner order. When dispersion is equal across assets, it moves every posterior component toward the prior. When dispersion is uneven and Σ is correlated, an individual component can move very slightly *away* from the prior. The SPY–TLT spread, which is what sets the weight, still moves back toward the prior. The tests check both behaviours.
- **Magnitude.** For the example SPY runs 5.8, 6.1, 5.9, 6.3 and 5.7 (s = 0.24%), with SPY variance 0.01688: τΣ_SPY = 8.4e-4 and s² = 5.8e-6, a dispersion ratio of 0.083. At High confidence, the empirical term raises Ω_SPY by about 1.4%. Dispersion of this size barely matters. It starts to matter when s approaches √(τΣ_ii), roughly 3 percentage points of view here.

## Stability metric shown on the dashboard

**Dispersion ratio** = s_i / √(τ Σ_ii): the run-to-run standard deviation measured against the prior's view-uncertainty scale. It is 0 when every run agreed and 1 when sampling noise is as large as the prior uncertainty. It does not depend on the confidence mode. The record also stores each asset's Ω_ii split into its reported and empirical parts, plus the empirical share.

## Configuration

`.env` (defaults shown):

```
STOCHASTIC_VIEWS=0        # 1 = run the committee N times; 0 = original single call, temperature 0, seed 42
VIEW_TEMPERATURE=0.2
VIEW_N_RUNS=5             # at least 2
VIEW_SEED=                # optional base seed; run r gets seed + r (best effort, not a determinism guarantee)
CONFIDENCE_MODE=combined  # reported | empirical | combined
```

The same settings can be overridden per request: `/api/run_pipeline?stochastic=1&n_runs=5&temperature=0.2&confidence_mode=empirical`.

A stochastic run costs N × 3 model calls.

## Audit record

Every stochastic response carries `stochastic`, and the run log (`runs/pipeline_log.jsonl`) also stores every run's raw replies as `stochastic_raw`. The record holds:

- timestamp, model, config (temperature, N, seed, mode), snapshot_id, evidence fingerprint
- per run: Q, reported confidence, validity and parse problems, CIO decision and grounding, economist and risk numbers
- aggregate: per-asset values, mean, std, variance, min, max, confidence counts, modal label
- the empirical variance, the final Ω, the effective mode, the label before and after the regime gate
- stability metrics, and the SPY target each valid run would have produced on its own (`per_run_target_spy`, `target_spy_distribution`)

No confidence interval is reported. With N ≈ 5, and outputs that are neither independent draws of a normal quantity nor continuous (models round to 0.5 points), a t-interval would look more precise than it is. Min and max are shown instead.

## Backtest use

`stochastic_views.decide_from_runs(sigma, run_views, rf_pct, mode, regime, previous_spy)` does no I/O. For each historical snapshot, a backtest collects N runs (for example with the masked prompts from `research/masked_replay.py`) and calls it. It returns the aggregated decision and, separately, the target each individual run would have produced. The spread of those targets is the distribution of portfolio outcomes that a single stochastic path would hide. No backtest strategy has been wired to it yet, because that needs N paid runs per month.

## Scope

- Python only. The public site (`site/`) replays stored single runs, and `site/js/allocation.js` is unchanged. With `empirical_var` omitted, the Python path is bit-for-bit the original, so JS/Python parity is kept.
- The rationale exposed is the existing structured CIO decision and grounding summary. No hidden reasoning is requested or stored.
