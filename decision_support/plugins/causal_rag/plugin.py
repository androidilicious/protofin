"""Causal RAG plugin: replays the saved status features of the qwen3 run (exploratory)."""
from __future__ import annotations

import json
from pathlib import Path

from decision_support.contract import Answer, Manifest


class CausalRag:
    def __init__(self, root: Path, manifest: Manifest):
        self.manifest = manifest
        self.root = root

    def answers(self, fund_set: str) -> list[Answer]:
        d = json.loads((self.root / self.manifest.data[fund_set]).read_text(encoding="utf-8"))
        out = []
        for m, v in sorted(d["months"].items()):
            if fund_set == "spy_tlt":
                feats = {"spy_S": v["SPY"]["F_S"], "spy_C": v["SPY"]["F_C"], "spy_I": v["SPY"]["F_I"],
                         "ief_S": v["IEF"]["F_S"], "ief_C": v["IEF"]["F_C"], "ief_I": v["IEF"]["F_I"]}
                stated = {"SPY": float(v["SPY"]["F_S"]), "TLT": float(v["IEF"]["F_S"])}
            else:
                feats = {f"{a.lower()}_{k[-1]}": v[a][k] for a in ("SPY", "IEF", "LQD") for k in ("F_S", "F_C", "F_I")}
                stated = {a: float(v[a]["F_S"]) for a in ("SPY", "IEF", "LQD")}
            out.append(Answer(month=m, stated=stated, features={k: float(x) for k, x in feats.items()}, confidence=None,
                              trace={"status_features": {a: v[a] for a in v if a in ("SPY", "IEF", "LQD")},
                                     "n_hypotheses": v.get("n_hypotheses"), "model": v.get("model", d.get("model")),
                                     "status": d.get("status"), "source": d.get("source")}))
        return out


def build(root: Path, manifest: Manifest) -> CausalRag:
    return CausalRag(root, manifest)
