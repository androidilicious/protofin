"""AI committee plugin: replays the saved one-month CIO answers and the three role texts."""
from __future__ import annotations

import json
from pathlib import Path

from decision_support.contract import Answer, Manifest

CONF_NUM = {"Low": 0.0, "Medium": 1.0, "High": 2.0}
CONF_01 = {"Low": 0.25, "Medium": 0.5, "High": 0.75}


def _text(role: dict | None) -> str:
    return (role or {}).get("text") or (role or {}).get("cio") or ""


class Committee:
    def __init__(self, root: Path, manifest: Manifest):
        self.manifest = manifest
        self.root = root

    def answers(self, fund_set: str) -> list[Answer]:
        months = json.loads((self.root / self.manifest.data[fund_set]).read_text(encoding="utf-8"))["months"]
        assets = ("SPY", "TLT") if fund_set == "spy_tlt" else ("SPY", "IEF", "LQD")
        out = []
        for as_of, c in sorted(months.items()):
            cio, ok = c["cio"], not c["problems"]
            if fund_set == "spy_tlt":
                stated = {"SPY": float(cio["spy_q"]) if ok else None, "TLT": float(cio["tlt_q"]) if ok else None}
                feats = {"cio_spy": stated["SPY"], "cio_tlt": stated["TLT"]}
            else:
                stated = {a: (float(cio[a]) if ok else None) for a in assets}
                feats = {f"cio_{a.lower()}": stated[a] for a in assets}
            feats["confidence"] = CONF_NUM.get(cio.get("confidence"), None) if ok else None
            out.append(Answer(month=as_of[:7], stated=stated, features=feats,
                              confidence=CONF_01.get(cio.get("confidence")) if ok else None,
                              trace={"economist": _text(c.get("economist")), "risk_manager": _text(c.get("risk")),
                                     "cio": cio.get("cio", ""), "grounding": cio.get("grounding", ""),
                                     "cio_views_pct": {a: stated[a] for a in assets}, "confidence_word": cio.get("confidence"),
                                     "problems": c["problems"]}))
        return out


def build(root: Path, manifest: Manifest) -> Committee:
    return Committee(root, manifest)
