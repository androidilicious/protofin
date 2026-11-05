"""Jev plugin: replays the saved one-month answers (collect_1m.py / collect_3f.py)."""
from __future__ import annotations

import json
from pathlib import Path

from decision_support.contract import Answer, Manifest

TILT_POINTS = {"strong_equities": 3, "lean_equities": 1.5, "neutral": 0, "lean_bonds": -1.5, "strong_bonds": -3}


class Jev:
    def __init__(self, root: Path, manifest: Manifest):
        self.manifest = manifest
        self.root = root

    def _months(self, fund_set: str) -> dict:
        return json.loads((self.root / self.manifest.data[fund_set]).read_text(encoding="utf-8"))["months"]

    def answers(self, fund_set: str) -> list[Answer]:
        out = []
        for as_of, j in sorted(self._months(fund_set).items()):
            month = as_of[:7]
            if fund_set == "spy_tlt":
                tilt = float(j["offset"])
                out.append(Answer(month=month, stated={"SPY": tilt, "TLT": -tilt},
                                  features={"p_stocks_beat_bonds": float(j["p"]), "expected_tilt": tilt, "confidence": float(j["confidence"])},
                                  confidence=float(j["confidence"]),
                                  trace={"p_stocks_beat_bonds": j["p"], "choice": j["choice"], "tilt_probabilities": j["probs"],
                                         "tilt_points": TILT_POINTS, "expected_tilt": tilt, "confidence": j["confidence"]}))
            else:
                best = {a: float(j["probs"][a]) for a in ("SPY", "IEF", "LQD")}
                out.append(Answer(month=month, stated={a: best[a] - 1 / 3 for a in best},
                                  features={"p_spy_ief": float(j["p_spy_ief"]), "p_lqd_ief": float(j["p_lqd_ief"]), "confidence": float(j["confidence"]),
                                            **{f"best_{a.lower()}": best[a] for a in best}},
                                  confidence=float(j["confidence"]),
                                  trace={"p_spy_beats_ief": j["p_spy_ief"], "p_lqd_beats_ief": j["p_lqd_ief"], "best_fund": j["best"],
                                         "p_best": j["probs"], "confidence": j["confidence"]}))
        return out


def build(root: Path, manifest: Manifest) -> Jev:
    return Jev(root, manifest)
