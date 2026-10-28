"""Directed topology graph plus a pair -> claim-row index.

The graph carries topology only, like the notebook graph. Evidence is always read back
from the claims table, so repeated directed pairs never lose their supporting rows.
"""

from typing import Dict, List

import networkx as nx
import numpy as np
import pandas as pd

from .labels import normalize_series


class GraphStore:
    def __init__(self, claims: pd.DataFrame, nodes: List[str]) -> None:
        self.claims = claims.reset_index(drop=True)
        self.nodes = nodes
        self.node_to_id = {name: i for i, name in enumerate(nodes)}

        edges = pd.DataFrame({
            "cause": normalize_series(self.claims["cause"]),
            "effect": normalize_series(self.claims["effect"]),
        })
        valid = (
            edges["cause"].notna() & edges["effect"].notna()
            & (edges["cause"] != "") & (edges["effect"] != "")
        )
        edges = edges[valid]

        self.graph = nx.from_pandas_edgelist(
            edges, source="cause", target="effect", create_using=nx.DiGraph()
        )
        # (cause, effect) -> positions of the original claim rows.
        self.pair_rows: Dict[tuple, np.ndarray] = {
            pair: positions for pair, positions in edges.groupby(["cause", "effect"]).indices.items()
        }
        # groupby positions are relative to the filtered frame; map back to claim rows.
        kept_rows = np.flatnonzero(valid.to_numpy())
        self.pair_rows = {pair: kept_rows[pos] for pair, pos in self.pair_rows.items()}

        unknown = set(self.graph.nodes) - set(self.node_to_id)
        if unknown:
            raise ValueError("{} graph nodes are missing from the node list.".format(len(unknown)))

    def node_name(self, node_id: int) -> str:
        return self.nodes[node_id]

    def has_edge(self, source: str, target: str) -> bool:
        return self.graph.has_edge(source, target)
