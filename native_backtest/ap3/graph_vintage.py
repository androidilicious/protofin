"""AP3 knowledge-graph vintages built with CauseTrace's own graph code.

Claims are loaded and filtered exactly as CauseTrace's notebook does (is_macroeconomics == True,
cause/effect stripped and lower-cased, empty labels dropped). A vintage keeps claims from papers
dated up to the vintage year and drops claims whose text mentions a later year or a later episode.
The graph itself is CauseTrace's GraphStore (vendored, unchanged).
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Dict

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
_CT = ROOT / "native_backtest/vendor/causetrace_82abe0a"
if str(_CT) not in sys.path:
    sys.path.insert(0, str(_CT))
from causetrace.graph import GraphStore  # noqa: E402  (vendored CauseTrace @ 82abe0a)

EXTERNAL = ROOT / "native_backtest/data/_external"
CONCEPTS = ROOT / "native_backtest/ap3/concepts_v1.json"
MANIFEST = ROOT / "native_backtest/config/ap3_claims_manifest_v1.json"


def load_concepts(path: Path = CONCEPTS) -> dict:
    return json.loads(Path(path).read_text())


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@lru_cache(maxsize=1)
def load_macro_claims() -> pd.DataFrame:
    """CauseTrace notebook rule, applied to the pinned shards (hash-checked)."""
    man = json.loads(MANIFEST.read_text())
    parts = []
    for s in man["sources"]:
        p = EXTERNAL / f"{s['role']}.parquet"
        if not p.exists():
            raise FileNotFoundError(f"{p} missing: run stage2/scoring/fetch_pinned_inputs.py --manifest {MANIFEST.relative_to(ROOT)} --out native_backtest/data/_external")
        if _sha(p) != s["sha256"]:
            raise ValueError(f"hash mismatch for {p}")
        parts.append(pd.read_parquet(p))
    df = pd.concat(parts, ignore_index=True)
    macro = df.loc[df["is_macroeconomics"] == True].copy()  # noqa: E712  (notebook rule verbatim)
    for col in ("cause", "effect"):
        macro[col] = macro[col].astype("string").str.strip().str.lower()
    macro = macro.dropna(subset=["cause", "effect"])
    macro = macro[(macro["cause"] != "") & (macro["effect"] != "")]
    return macro.reset_index(drop=True)


def _scan_mask(claims: pd.DataFrame, vintage: int, scan: dict) -> pd.Series:
    text = (claims["cause"].fillna("") + " || " + claims["effect"].fillna("") + " || " + claims["title"].astype("string").fillna("").str.lower())
    years = text.str.findall(scan["year_regex"])
    late_year = years.apply(lambda ys: any(int(y) > vintage for y in ys))
    late_episode = pd.Series(False, index=claims.index)
    for term, first in scan["episodes"].items():
        if first > vintage:
            late_episode |= text.str.contains(term, regex=False)
    return late_year | late_episode


@dataclasses.dataclass
class Vintage:
    year: int
    store: GraphStore
    claims: pd.DataFrame
    stats: Dict[str, int]


def build_vintage(vintage_year: int, concepts: dict | None = None) -> Vintage:
    concepts = concepts or load_concepts()
    macro = load_macro_claims()
    dated = macro[macro["year"].notna() & (macro["year"] <= vintage_year)]
    flagged = _scan_mask(dated, vintage_year, concepts["post_vintage_scan"])
    kept = dated[~flagged].reset_index(drop=True)
    nodes = sorted(set(kept["cause"]).union(set(kept["effect"])))
    store = GraphStore(kept, nodes)
    stats = {"vintage_year": vintage_year, "macro_claims_total": int(len(macro)), "claims_dated_le_vintage": int(len(dated)),
             "excluded_by_post_vintage_scan": int(flagged.sum()), "claims_kept": int(len(kept)),
             "papers_kept": int(kept["paper_id"].nunique()), "nodes": store.graph.number_of_nodes(), "edges": store.graph.number_of_edges()}
    return Vintage(vintage_year, store, kept, stats)


def vintage_for_decision(decision_month: str) -> int:
    return int(decision_month[:4]) - 1
