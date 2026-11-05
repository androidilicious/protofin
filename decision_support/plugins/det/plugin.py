"""Deterministic model plugin: the 8 surprise z-scores, replayed from the frozen Stage 2 macro panel."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from decision_support.contract import Answer, Manifest


class Det:
    def __init__(self, root: Path, manifest: Manifest):
        self.manifest = manifest
        sys.path.insert(0, str(root))
        from level_playing_field import run as lpf
        from native_backtest.framework import market as mk
        fcfg = mk.load_config()
        spec = json.loads((root / fcfg["inherits_stage2_run_spec"]["path"]).read_text())
        self._frame = lpf.signals_det(spec)

    def answers(self, fund_set: str) -> list[Answer]:
        out = []
        for m, row in self._frame.iterrows():
            feats = {k: (None if (v is None or (isinstance(v, float) and math.isnan(v))) else float(v)) for k, v in row.items()}
            out.append(Answer(month=str(m), stated={}, features=feats, confidence=None,
                              trace={"surprise_z": feats, "note": "z = (actual - consensus) / std of the prior 12 releases"}))
        return out


def build(root: Path, manifest: Manifest) -> Det:
    return Det(root, manifest)
