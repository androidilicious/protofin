"""CauseTrace tools the Hypothesis Agent may call, bound to one graph vintage.

Every tool wraps CauseTrace's own code (vendored @ 82abe0a, unchanged). Two documented
substitutions keep results deterministic and offline:
- node search is exact-token lexical matching over node names (whole words: letters and digits, so
  "PPI" matches "ppi targeting" but not "happiness", and "INDUSTRIAL_PRODUCTION" is read as two words), not
  BGE-M3 similarity (the embedding model cannot be downloaded here, and similarity matching was ruled out for
  leakage);
- path search runs with the wall-clock limit disabled and a count limit, so results depend only
  on the graph.
Calls are counted against a per-month budget and logged. Repeating an earlier call with identical arguments
still counts against the budget but is not re-run: the reply says it is a repeat and points to the earlier result.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
_CT = ROOT / "native_backtest/vendor/causetrace_82abe0a"
if str(_CT) not in sys.path:
    sys.path.insert(0, str(_CT))
from causetrace.evidence import edge_evidence  # noqa: E402
from causetrace.paths import find_paths  # noqa: E402

from native_backtest.ap3.graph_vintage import Vintage
from native_backtest.ap3.library import NO_TIME_LIMIT_S, channel_of, path_support

TOOL_SPECS = {
    "search_nodes": "search_nodes(query: str, limit<=10): graph concepts whose names contain every query word (whole words), most-connected first",
    "paths": "paths(source: str, target: str, max_paths<=25): directed causal-claim paths (<=3 hops) from source concept to target concept",
    "neighbourhood": "neighbourhood(node: str, direction: 'out'|'in', limit<=25): concepts directly caused by (out) or causing (in) a node",
    "edge_evidence": "edge_evidence(source: str, target: str, limit<=8): research records behind one edge (paper, year, method flags)",
}


class ToolBudgetExceeded(RuntimeError):
    pass


def words(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", str(text).lower())


NOT_A_CONCEPT = ("Not an exact concept name in this vintage: {what}. Concepts are lower-case phrases like those in the "
                 "library pathways; trigger codes (e.g. CPI, PPI) and tickers (SPY, IEF, LQD) are not concepts. "
                 "Find exact names with search_nodes.")


class CauseTraceTools:
    def __init__(self, vintage: Vintage, concepts: dict, budget: int = 15):
        self.v = vintage
        self.concepts = concepts
        self.budget = budget
        self.calls: List[Dict[str, Any]] = []
        self.paths_seen: Dict[str, List[str]] = {}
        self._seen: Dict[str, int] = {}
        self._words: Optional[Dict[str, frozenset]] = None

    @property
    def remaining(self) -> int:
        return self.budget - len(self.calls)

    def _charge(self, name: str, args: dict) -> None:
        if len(self.calls) >= self.budget:
            raise ToolBudgetExceeded(f"tool budget {self.budget} used")
        self.calls.append({"tool": name, "args": args})

    def _pid(self, p: List[str]) -> str:
        pid = f"p{self.v.year}-" + hashlib.sha1(("|".join(p)).encode()).hexdigest()[:12]
        self.paths_seen[pid] = p
        return pid

    def call(self, name: str, args: dict) -> Any:
        fn = {"search_nodes": self.search_nodes, "paths": self.paths, "neighbourhood": self.neighbourhood, "edge_evidence": self.edge_evidence}.get(name)
        if fn is None:
            return {"error": f"unknown tool {name}"}
        key = json.dumps({"tool": name, "args": args}, sort_keys=True, default=str)
        if key in self._seen:                      # a repeat: counts against the budget, is not re-run
            self._charge(name, args)
            self.calls[-1]["duplicate_of"] = self._seen[key]
            return {"repeat": True, "note": f"identical to your tool call #{self._seen[key] + 1}; its result is above. "
                                            "Call a different tool or different arguments, or give your final answer."}
        try:
            out = fn(**args)
            self._seen[key] = len(self.calls) - 1
            return out
        except ToolBudgetExceeded:
            raise
        except TypeError as e:
            return {"error": f"bad arguments: {e}"}

    def search_nodes(self, query: str, limit: int = 10) -> Any:
        self._charge("search_nodes", {"query": query, "limit": limit})
        toks = words(query)
        g = self.v.store.graph
        if self._words is None:
            self._words = {n: frozenset(words(n)) for n in g.nodes}
        hits = [n for n, w in self._words.items() if all(t in w for t in toks)] if toks else []
        hits.sort(key=lambda n: (-(g.in_degree(n) + g.out_degree(n)), n))
        return [{"node": n, "in_degree": g.in_degree(n), "out_degree": g.out_degree(n)} for n in hits[: max(1, min(int(limit), 10))]]

    def paths(self, source: str, target: str, max_paths: int = 25) -> Any:
        self._charge("paths", {"source": source, "target": target, "max_paths": max_paths})
        g = self.v.store.graph
        if source not in g or target not in g:
            return {"error": NOT_A_CONCEPT.format(what=", ".join(repr(x) for x in (source, target) if x not in g))}
        res = find_paths(self.v.store, source, target, max_hops=self.concepts["path_limits"]["max_hops"],
                         max_paths=max(1, min(int(max_paths), self.concepts["path_limits"]["max_paths_per_pair"])), time_limit_s=NO_TIME_LIMIT_S)
        out = []
        for p in res["paths"]:
            out.append({"path_id": self._pid(p), "path": p, "channel": channel_of(p, self.concepts["channel_lexicon"]), **path_support(self.v, p)})
        return {"paths": out, "truncated": res["truncated"]}

    def neighbourhood(self, node: str, direction: str = "out", limit: int = 25) -> Any:
        self._charge("neighbourhood", {"node": node, "direction": direction, "limit": limit})
        g = self.v.store.graph
        if node not in g:
            return {"error": NOT_A_CONCEPT.format(what=repr(node))}
        nbrs = list(g.successors(node)) if direction == "out" else list(g.predecessors(node))
        def papers(n):
            pair = (node, n) if direction == "out" else (n, node)
            return len(self.v.store.pair_rows.get(pair, []))
        nbrs.sort(key=lambda n: (-papers(n), n))
        return [{"node": n, "claim_rows": papers(n)} for n in nbrs[: max(1, min(int(limit), 25))]]

    def edge_evidence(self, source: str, target: str, limit: int = 8) -> Any:
        self._charge("edge_evidence", {"source": source, "target": target, "limit": limit})
        if not self.v.store.has_edge(source, target):
            return {"error": "no such edge in this vintage"}
        ev = edge_evidence(self.v.store, source, target, limit=max(1, min(int(limit), 8)))
        keep = ("paper_id", "title", "year", "evidence_class", "causal_inference_method", "evidence_id")
        return {"edge_id": ev["edge_id"], "unique_papers": ev["unique_papers"], "records": [{k: r.get(k) for k in keep} for r in ev["evidence"]]}
