"""Bounded directed path retrieval.

Paths are simple (no repeated node), follow edge direction cause -> effect, and are
enumerated shortest-first. Hitting a limit is reported; it never means "no relationship".
"""

import time
from typing import Any, Dict, List, Optional

from . import config
from .graph import GraphStore


def _backward_distances(store: GraphStore, target: str, max_hops: int, deadline: float):
    """Hop distance to `target` for nodes within max_hops, following edges backwards."""
    dist = {target: 0}
    frontier = [target]
    for depth in range(1, max_hops + 1):
        nxt = []
        for node in frontier:
            for pred in store.graph.predecessors(node):
                if pred not in dist:
                    dist[pred] = depth
                    nxt.append(pred)
            if time.monotonic() > deadline:
                return dist, True
        frontier = nxt
    return dist, False


def find_paths(
    store: GraphStore,
    source: str,
    target: str,
    max_hops: int = config.PATH_MAX_HOPS_DEFAULT,
    max_paths: int = config.PATH_MAX_RESULTS_DEFAULT,
    time_limit_s: float = config.PATH_TIME_LIMIT_DEFAULT_S,
) -> Dict[str, Any]:
    limits = {"max_hops": max_hops, "max_paths": max_paths, "time_limit_s": time_limit_s}
    start = time.monotonic()
    deadline = start + time_limit_s
    paths: List[List[str]] = []
    truncated_reason: Optional[str] = None

    dist, timed_out = _backward_distances(store, target, max_hops, deadline)
    if timed_out:
        truncated_reason = "time_limit"
    elif source in dist:
        for limit in range(dist[source], max_hops + 1):
            truncated_reason = _enumerate(
                store, source, target, limit, dist, max_paths, deadline, paths
            )
            if truncated_reason:
                break

    return {
        "paths": paths,
        "limits": limits,
        "truncated": truncated_reason is not None,
        "truncated_reason": truncated_reason,
        "elapsed_s": round(time.monotonic() - start, 3),
    }


def _enumerate(store, source, target, length, dist, max_paths, deadline, out):
    """Depth-first enumeration of simple paths with exactly `length` hops."""
    stack = [(source, iter(sorted(store.graph.successors(source))))]
    trail = [source]
    on_trail = {source}
    steps = 0
    while stack:
        node, children = stack[-1]
        child = next(children, None)
        if child is None:
            stack.pop()
            on_trail.discard(trail.pop())
            continue
        steps += 1
        if steps % 2000 == 0 and time.monotonic() > deadline:
            return "time_limit"
        used = len(trail)  # hops taken after stepping to `child`
        if child in on_trail:
            continue
        if used == length:
            if child == target:
                if len(out) >= max_paths:
                    return "max_paths"
                out.append(trail + [child])
            continue
        if child == target or dist.get(child, length + 1) > length - used:
            continue
        trail.append(child)
        on_trail.add(child)
        stack.append((child, iter(sorted(store.graph.successors(child)))))
    return None


def group_by_first_intermediate(paths: List[List[str]]) -> List[Dict[str, Any]]:
    """Algorithmic grouping by the first concept after the source. Not a validated mechanism."""
    groups: Dict[str, List[int]] = {}
    for index, path in enumerate(paths):
        key = "(direct edge)" if len(path) == 2 else path[1]
        groups.setdefault(key, []).append(index)
    return [
        {"grouping": "first_intermediate_concept", "via": via, "path_indices": idx, "path_count": len(idx)}
        for via, idx in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    ]
