"""Shared portfolio accounting.

Same conventions as stage2_portfolio.simulate (Stage 2 conventions 6-8), generalised to any asset
list: the target weights of each decision month are traded at the entry close; the cost is
cost_per_dollar times the dollars traded against the drifted pre-trade weights; the first month
starts from cash; returns are held to the exit close; weights then drift with realised returns.
"""
from __future__ import annotations

from typing import Dict, List, Mapping, Sequence

import numpy as np
import pandas as pd

from .market import Market
from .records import DecisionRecord


class AccountingError(RuntimeError):
    pass


def simulate_records(
    records: Sequence[DecisionRecord],
    market: Market,
    months: Sequence[pd.Period],
    *,
    cost_per_dollar: float,
) -> pd.DataFrame:
    if not records:
        raise AccountingError("no records")
    system = {r.system_id for r in records}
    if len(system) != 1:
        raise AccountingError(f"records from several systems: {sorted(system)}")
    mock = [r.decision_month for r in records if r.generation.get("mode") == "engineering_mock"]
    if mock:
        raise AccountingError(f"refusing to score engineering-mock records ({len(mock)} months, first {mock[0]}): mock outputs are never backtest results")
    universe = list(records[0].universe)
    by_month = {r.decision_month: r for r in records}
    for r in records:
        if list(r.universe) != universe:
            raise AccountingError(f"{r.decision_month}: universe changed")
    pre = np.zeros(len(universe))
    rows: List[Dict] = []
    for m in months:
        key = str(m)
        if key not in by_month:
            raise AccountingError(f"{records[0].system_id}: no decision record for {key}; the adapter must apply the failure rule")
        rec = by_month[key]
        w = np.array([float(rec.target_weights[a]) for a in universe])
        r_map = market.period_returns(m, universe)
        r = np.array([r_map[a] for a in universe])
        rf = market.rf_return(m)
        entry, exit_ = market.holding_period(m)
        notional = float(np.abs(w - pre).sum())
        cost = cost_per_dollar * notional
        gross = float(w @ r)
        rows.append({
            "system_id": rec.system_id,
            "decision_month": key,
            "entry_date": entry.date().isoformat(),
            "exit_date": exit_.date().isoformat(),
            "generation_mode": rec.generation.get("mode"),
            **{f"w_{a}": float(w[i]) for i, a in enumerate(universe)},
            **{f"pretrade_w_{a}": float(pre[i]) for i, a in enumerate(universe)},
            "traded_notional": notional,
            "one_way_turnover": 0.5 * notional,
            "cost": cost,
            "rf_return": rf,
            "gross_total_return": gross,
            "gross_excess_return": gross - rf,
            "net_total_return": gross - cost,
            "net_excess_return": gross - rf - cost,
        })
        grown = w * (1.0 + r)
        pre = grown / grown.sum()
    return pd.DataFrame(rows)


def static_portfolio_records(system_id: str, weights: Mapping[str, float], template: Sequence[DecisionRecord]) -> List[DecisionRecord]:
    """A fixed-weight benchmark on the same decision dates as `template` (e.g. a system's native neutral portfolio)."""
    import dataclasses

    out = []
    for r in template:
        out.append(dataclasses.replace(
            r,
            system_id=system_id,
            target_weights=dict(weights),
            universe=list(weights),
            generation={"mode": "computed_native", "benchmark": "static", "weights": dict(weights)},
            forecast=None,
            confidence=None,
            native_detail=None,
        ))
    return out
