"""ENGINEERING FIXTURES — synthetic documents and a synthetic mediator series for wiring tests and the
dashboard's labelled demo. They describe no real market and are never inputs to a backtest result."""
from __future__ import annotations

import numpy as np
import pandas as pd

FIXTURE_CHUNKS = [
    {"doc_id": "ENGFIX_D1", "chunk_id": "ENGFIX_D1#c000", "available_at_et": "2019-06-12T08:30:00-04:00",
     "text": "ENGINEERING FIXTURE. Consumer prices rose and retail sales consumer spending were firm in the latest release."},
    {"doc_id": "ENGFIX_D2", "chunk_id": "ENGFIX_D2#c000", "available_at_et": "2019-06-19T14:00:00-04:00",
     "text": "ENGINEERING FIXTURE. Weak demand decline in manufacturing was noted while policy was held steady."},
    {"doc_id": "ENGFIX_D3", "chunk_id": "ENGFIX_D3#c000", "available_at_et": "2019-06-20T10:00:00-04:00",
     "text": "ENGINEERING FIXTURE. Inflation expectations and interest rates were discussed in general terms."},
]


def fixture_mediators():
    from native_backtest.ap3.mediators import MediatorStore
    days = pd.bdate_range("2015-01-02", "2019-06-28")
    rng = np.random.default_rng(3)
    v = np.cumsum(rng.normal(0, 0.03, len(days))) + 2.0
    df = pd.DataFrame({"date": days, "value": v, "available_at": (days + pd.Timedelta(hours=17)).tz_localize("America/New_York")})
    return MediatorStore({"UST2Y": df})
