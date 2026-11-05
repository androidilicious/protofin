from __future__ import annotations

from pathlib import Path

from decision_support.contract import Answer, Manifest


class Placebo:
    def __init__(self, manifest: Manifest):
        self.manifest = manifest

    def answers(self, fund_set: str) -> list[Answer]:
        return []


def build(root: Path, manifest: Manifest) -> Placebo:
    return Placebo(manifest)
