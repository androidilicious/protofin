"""Status features: the three Testing Agent outcomes kept distinct.

For asset a in month t: F^S = sum of the predicted directions s_{h,a} of hypotheses whose majority
status is Supported; F^C the same for Contradicted; F^I for Insufficient. A month with no
hypotheses has all three at 0. No status is scored +1/-1 against another.
"""
from __future__ import annotations

from typing import Dict, List

ASSETS = ("SPY", "IEF", "LQD")
STATUS_COL = {"Supported": "F_S", "Contradicted": "F_C", "Insufficient": "F_I"}


def status_features(hypotheses: List[dict], tests: List[dict]) -> Dict[str, Dict[str, float]]:
    by_id = {t["hypothesis_id"]: t["status"] for t in tests}
    out = {a: {"F_S": 0.0, "F_C": 0.0, "F_I": 0.0} for a in ASSETS}
    for h in hypotheses:
        st = by_id.get(h["hypothesis_id"])
        if st not in STATUS_COL:
            raise ValueError(f"hypothesis {h['hypothesis_id']} has no valid status ({st})")
        for a in ASSETS:
            out[a][STATUS_COL[st]] += float(h["predicted_assets"][a])
    return out
