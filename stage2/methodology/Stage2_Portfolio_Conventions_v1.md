# Stage 2 portfolio layer — implementation conventions v1

**Written:** 2026-10-27, before any Stage 2 portfolio result was computed.
**Scope:** how `stage2/scoring/stage2_portfolio.py` implements Freeze v2 §8–10. Frozen values are used exactly; this file only fixes the details the freeze leaves open. None of these conventions may change after a portfolio result is viewed without a version increment and a rerun of every system.

## Frozen values used exactly

| Item | Value |
|---|---|
| Allocator | Black–Litterman, P = I, Q = Ridge excess-return forecasts |
| τ | 0.05 |
| Risk aversion δ | 2.5 |
| Prior weights | SPY 0.45, IEF 0.35, LQD 0.20 |
| Covariance | Trailing 36-month Ledoit–Wolf covariance of realised excess returns available by decision time |
| Ω | Diagonal forecast-error variance from System A development-period OOS errors, frozen and shared by every system |
| Constraints | Long-only, fully invested; SPY 20–70%, IEF 15–60%, LQD 10–40% |
| Cost | 5 bp per dollar traded; traded notional = Σ\|target − drifted pre-trade weight\|; one-way turnover = 0.5 × notional |
| Benchmarks | (1) historical-mean forecasts through the same allocator, Ω and costs; (2) static 45/35/20 rebalanced monthly with the same cost accounting |
| Secondary metrics | Net annualised excess return, annualised volatility, net Sharpe, maximum drawdown, CER (δ = 2.5), turnover, break-even transaction cost |

## Conventions fixed here (not specified by the freeze)

1. **Covariance returns.** The 36 most recent completed holding-period excess returns (the same labels as the forecast target), i.e. decisions t−37 to t−2. This applies the frozen t-2 availability rule and the frozen return definition. Estimator: Ledoit–Wolf (2004) shrinkage towards a scaled identity, sample mean removed (`sklearn.covariance.LedoitWolf`, `assume_centered=False`).
2. **Equilibrium returns.** π = δ Σ w_prior.
3. **Ω.** Ω_ii = sample variance (ddof = 1) of System A's 46 development OOS forecast errors for asset i; off-diagonals zero. Computed once from the canonical development rerun and written to `stage2/config/stage2_omega_from_A_development.json`. Historical mode must load that frozen file. Development-mode portfolio results use the same Ω and therefore contain within-window look-ahead in Ω; they are diagnostics only.
4. **Posterior.** μ_BL = [(τΣ)⁻¹ + Ω⁻¹]⁻¹ [(τΣ)⁻¹π + Ω⁻¹Q]; Σ_BL = Σ + [(τΣ)⁻¹ + Ω⁻¹]⁻¹ (He–Litterman).
5. **Optimiser.** Maximise w′μ_BL − (δ/2) w′Σ_BL w subject to Σw = 1 and the frozen bounds. Solved exactly by enumerating which assets sit at a bound (3³ cases), so the result is deterministic and solver-independent.
6. **Timing.** Weights chosen at decision t are traded at the entry close and held to the exit close, the same interval as the label. Portfolio total return = Σ w_i R_i; excess return = Σ w_i R_i − r_f, with r_f the label's DTB4WK accrual.
7. **Drift.** Pre-trade weights at the next entry are w_i(1 + R_i) / (1 + Σ w_j R_j).
8. **Costs.** Charged at each rebalance and deducted from that period's return. Every strategy starts from cash (first traded notional = 1). No terminal liquidation charge.
9. **Annualisation.** Holding periods are treated as months: annualised return = 12 × mean; annualised volatility = √12 × standard deviation (ddof = 1).
10. **Net Sharpe.** Annualised net excess return ÷ annualised volatility of net excess returns.
11. **Maximum drawdown.** Largest peak-to-trough decline of the cumulative net total-return wealth index, starting at 1.
12. **CER.** 12 × [mean − (δ/2) × variance(ddof = 1)] of monthly net excess returns, δ = 2.5.
13. **Turnover.** Mean one-way turnover per rebalance, and that mean × 12.
14. **Break-even transaction cost.** The cost per dollar traded c* at which the strategy's net CER equals a comparator's when both pay c*. Reported against the historical-mean allocator, the static 45/35/20 portfolio and, for B systems, System A. "Not defined" when the strategy's CER does not exceed the comparator's at zero cost; "above 100%" when it still exceeds it at a cost of 1 per dollar traded.
