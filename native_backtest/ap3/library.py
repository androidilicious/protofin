"""AP3 channel library, derived from a graph vintage by frozen code.

For every (trigger concept, asset concept) pair, CauseTrace's own bounded path search
(causetrace.paths.find_paths, unchanged) enumerates simple directed paths shortest-first with
sorted successors. The wall-clock limit is disabled so the result depends only on the graph;
the count limit (max_paths_per_pair) bounds the search. Each path gets a channel from the frozen
lexicon and literature support from CauseTrace's edge evidence.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[2]
_CT = ROOT / "native_backtest/vendor/causetrace_82abe0a"
if str(_CT) not in sys.path:
    sys.path.insert(0, str(_CT))
from causetrace.evidence import edge_paper_ids, edge_summary  # noqa: E402
from causetrace.paths import find_paths  # noqa: E402

from native_backtest.ap3.graph_vintage import Vintage, load_concepts

NO_TIME_LIMIT_S = 1e9


def channel_of(path: List[str], lexicon: dict) -> str:
    inter = path[1:-1]
    if not inter:
        return "direct"
    for node in inter:
        for ch in lexicon["priority"]:
            if any(tok in node for tok in lexicon[ch]):
                return ch
    return "other"


def path_support(v: Vintage, path: List[str]) -> dict:
    edges = list(zip(path[:-1], path[1:]))
    summaries = [edge_summary(v.store, s, t) for s, t in edges]
    paper_sets = [edge_paper_ids(v.store, s, t) for s, t in edges]
    all_papers = set().union(*paper_sets) if paper_sets else set()
    rows = sum(x["claim_rows"] for x in summaries)
    causal_rows = sum(x["evidence_class_rows"].get("causal_method_tagged", 0) for x in summaries)
    common = set.intersection(*paper_sets) if paper_sets else set()
    return {
        "edge_ids": [x["edge_id"] for x in summaries],
        "min_papers_per_edge": min(x["unique_papers"] for x in summaries),
        "distinct_papers": len(all_papers),
        "causal_method_share": (causal_rows / rows) if rows else 0.0,
        "cross_paper": len(edges) > 1 and len(common) == 0,
    }


def derive_library(v: Vintage, concepts: dict | None = None) -> dict:
    concepts = concepts or load_concepts()
    lim = concepts["path_limits"]
    lex = concepts["channel_lexicon"]
    graph = v.store.graph
    entries: List[Dict] = []
    missing = set()
    for trig, tcfg in sorted(concepts["triggers"].items()):
        for asset, acfg in sorted(concepts["assets"].items()):
            for src in tcfg["concepts"]:
                if src not in graph:
                    missing.add(src)
                    continue
                for tgt in acfg["concepts"]:
                    if tgt not in graph:
                        missing.add(tgt)
                        continue
                    if src == tgt:
                        continue
                    res = find_paths(v.store, src, tgt, max_hops=lim["max_hops"], max_paths=lim["max_paths_per_pair"], time_limit_s=NO_TIME_LIMIT_S)
                    if res["truncated_reason"] == "time_limit":
                        raise RuntimeError(f"time limit hit for {src}->{tgt}; the library must be count-limited only")
                    for k, p in enumerate(res["paths"]):
                        pid = hashlib.sha1(("|".join(p)).encode()).hexdigest()[:12]
                        entries.append({"path_id": f"p{v.year}-{pid}", "trigger": trig, "asset": asset, "source": src, "target": tgt,
                                        "rank_in_pair": k, "hops": len(p) - 1, "path": p, "channel": channel_of(p, lex),
                                        "truncated_pair": res["truncated_reason"] == "max_paths", **path_support(v, p)})
    lib = {"vintage_year": v.year, "concepts_version": concepts["version"], "vintage_stats": v.stats,
           "concepts_missing_in_vintage": sorted(missing), "n_paths": len(entries), "entries": entries}
    lib["library_sha256"] = hashlib.sha256(json.dumps(lib, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return lib
