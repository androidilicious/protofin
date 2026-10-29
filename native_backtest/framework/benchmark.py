"""Common benchmark: one fixed-weight reference portfolio for every approach.

Evaluation and display layer only. It never feeds a system's forecasts, signals, universe, horizon or
weights, and it never enters the primary hypothesis family (the pre-registered pairwise net-CER
contrasts among the three approaches, Holm-corrected). Results against it are secondary and descriptive.

Accounting is exactly the shared evaluator's (accounting.simulate_records on static records):
- decision dates: the template records' dates (last common trading day of each month, 20:00 ET);
- trades: back to the target weights at the entry close (first common trading day after month-end),
  held to the next entry close; weights drift with realised returns in between;
- costs: cost_per_dollar on dollars traded against the drifted weights; the first month starts from cash;
- returns: distribution-adjusted closing prices of the pinned, verified market inputs (total return);
- excess return: net return minus DTB4WK accrued over the same holding period.
The specification lives in framework_config_v1.json under "common_benchmark".
"""
from __future__ import annotations

import hashlib
import json
from typing import Dict, Mapping, Sequence

import numpy as np
import pandas as pd

from . import metrics as M
from .accounting import simulate_records, static_portfolio_records
from .market import Market
from .records import DecisionRecord


class BenchmarkSpecError(ValueError):
    pass


FINGERPRINT_FIELDS = ("id", "weights", "rebalance", "rules", "role", "decomposition")
INHERITED = ("calendar_assets", "timing", "costs", "metrics")


def _fingerprint(b: dict, cfg: dict) -> str:
    payload = {"common_benchmark": {k: b[k] for k in FINGERPRINT_FIELDS}, "inherited": {k: cfg[k] for k in INHERITED}}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def spec(cfg: dict) -> dict:
    """The validated specification. A frozen specification must still match the fingerprint recorded at approval;
    any later change to the benchmark or to the shared settings it inherits stops every use of it."""
    b = cfg.get("common_benchmark")
    if not b:
        raise BenchmarkSpecError("framework config has no common_benchmark")
    w = b["weights"]
    if abs(sum(w.values()) - 1.0) > 1e-12 or any(v < 0 for v in w.values()):
        raise BenchmarkSpecError(f"common benchmark weights must be long-only and sum to 1: {w}")
    missing = [a for a in w if a not in cfg["calendar_assets"]]
    if missing:
        raise BenchmarkSpecError(f"common benchmark assets outside the evaluation calendar: {missing}")
    if b.get("rebalance") != "monthly_to_target_at_entry_close":
        raise BenchmarkSpecError("only monthly rebalancing at the shared entry close is implemented")
    if b.get("status") == "frozen":
        got, want = _fingerprint(b, cfg), b.get("frozen", {}).get("fingerprint_sha256")
        if got != want:
            raise BenchmarkSpecError(f"frozen common benchmark changed: fingerprint {got} != approved {want}")
    return b


def fingerprint(cfg: dict) -> str:
    """SHA-256 of everything that defines the benchmark's returns and role: its own specification fields plus the
    shared settings it inherits (calendar assets, timing, costs, metrics). Status, notes and the freeze record are
    excluded, so approval does not change it, while any change that would move a number or the role does."""
    return _fingerprint(spec(cfg), cfg)


def records(cfg: dict, template: Sequence[DecisionRecord]) -> list:
    b = spec(cfg)
    return static_portfolio_records(b["id"], b["weights"], template)


def simulate(cfg: dict, market: Market, months: Sequence[pd.Period], template: Sequence[DecisionRecord]) -> pd.DataFrame:
    return simulate_records(records(cfg, template), market, months, cost_per_dollar=cfg["costs"]["cost_per_dollar_traded"])


def cumulative_return(sim: pd.DataFrame) -> float:
    return float(np.prod(1.0 + sim["net_total_return"].to_numpy(float)) - 1.0)


def relative(sim: pd.DataFrame, bench: pd.DataFrame, cfg: dict) -> Dict:
    """A system against the common benchmark on identical months (secondary, descriptive)."""
    m = cfg["metrics"]
    c = M.paired_cer_contrast(sim, bench, delta=m["cer_delta"], block=m["bootstrap_block_months"], reps=m["bootstrap_reps"], seed=m["bootstrap_seed"])
    j = sim[["decision_month", "net_total_return"]].merge(bench[["decision_month", "net_total_return"]], on="decision_month", suffixes=("_s", "_b"), validate="one_to_one")
    d = (j["net_total_return_s"] - j["net_total_return_b"]).to_numpy(float)
    ms, mb = M.metrics(sim), M.metrics(bench)
    cs, cb = cumulative_return(sim), cumulative_return(bench)
    return {"cer_difference": c["cer_difference"], "ci90": c["ci90"], "ci95": c["ci95"], "p_two_sided_bootstrap": c["p_two_sided_bootstrap"],
            "n_months": c["n_months"], "first_month": c["first_month"], "last_month": c["last_month"],
            "annualized_excess_return_difference": ms["net_annualized_excess_return"] - mb["net_annualized_excess_return"],
            "sharpe_difference": ms["net_sharpe"] - mb["net_sharpe"],
            "cumulative_return": {"system": cs, "benchmark": cb, "difference": cs - cb},
            "tracking_error_annualized": float(np.std(d, ddof=1) * np.sqrt(12.0)),
            "role": "secondary and descriptive; not part of the primary Holm family"}


def decomposition(sim: pd.DataFrame, own_neutral: pd.DataFrame, bench: pd.DataFrame, delta: float) -> Dict[str, float]:
    """Accounting decomposition (an identity, not a causal attribution) of CER(system) - CER(common benchmark):
    active_decisions          = CER(system) - CER(its own native benchmark), labelled "decisions";
    benchmark_mix_difference  = CER(own native benchmark) - CER(common benchmark), labelled "benchmark mix": the
                                difference between two fixed mixes, which involves no decision of the system.
    CER is not additive across portfolios in a causal sense; the split is exact arithmetic only."""
    cs, cn, cb = (M.cer(x["net_excess_return"], delta) for x in (sim, own_neutral, bench))
    return {"total_vs_common": cs - cb, "active_decisions": cs - cn, "benchmark_mix_difference": cn - cb}


def static_metrics(cfg: dict, market: Market, months: Sequence[pd.Period], template: Sequence[DecisionRecord], weights: Mapping[str, float], label: str) -> Dict:
    sim = simulate_records(static_portfolio_records(label, dict(weights), template), market, months, cost_per_dollar=cfg["costs"]["cost_per_dollar_traded"])
    return {"weights": dict(weights), **M.metrics(sim), "cumulative_return": cumulative_return(sim), "_sim": sim}
