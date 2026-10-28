"""Attach original claim records to graph edges.

Evidence classes are descriptive labels derived from dataset metadata. They are not
measures of validity, and a causal-method flag is not proof of identification.
"""

from collections import Counter
from typing import Any, Dict, List, Optional

import pandas as pd

from .graph import GraphStore

CAUSAL_METHOD_TAGGED = "causal_method_tagged"
THEORETICAL = "theoretical"
UNSPECIFIED = "unspecified_method"
OTHER_METHOD = "other_method_not_causal_tagged"
CLASS_ORDER = [CAUSAL_METHOD_TAGGED, THEORETICAL, UNSPECIFIED, OTHER_METHOD]

EVIDENCE_CLASS_MEANING = {
    CAUSAL_METHOD_TAGGED: "Dataset flag is_method_causal_inference = 1 (e.g. DiD, IV, RDD). Metadata only.",
    THEORETICAL: "Recorded method is 'theoretical/non-empirical'.",
    UNSPECIFIED: "Recorded method is 'other', 'do not know' or missing.",
    OTHER_METHOD: "Another recorded method (e.g. fixed effects, simulation) without the causal flag.",
}

UNSPECIFIED_METHODS = {"other", "do not know"}


def _clean(value: Any) -> Optional[Any]:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    return value


def classify_evidence(flag: Any, method: Any) -> str:
    flag, method = _clean(flag), _clean(method)
    if flag is not None and float(flag) == 1.0:
        return CAUSAL_METHOD_TAGGED
    if method == "theoretical/non-empirical":
        return THEORETICAL
    if method is None or method in UNSPECIFIED_METHODS:
        return UNSPECIFIED
    return OTHER_METHOD


def _display_fields(row: pd.Series) -> Dict[str, Any]:
    year = _clean(row.get("year"))
    flag = _clean(row.get("is_method_causal_inference"))
    method = _clean(row.get("causal_inference_method"))
    return {
        "paper_id": _clean(row.get("paper_id")),
        "title": _clean(row.get("title")),
        "year": None if year is None else int(year),
        "is_method_causal_inference": None if flag is None else int(flag),
        "causal_inference_method": method,
        "evidence_class": classify_evidence(flag, method),
        "sources_of_exogenous_variation": _clean(row.get("sources_of_exogenous_variation")),
        "jel_cause": _clean(row.get("jel_cause")),
        "jel_effect": _clean(row.get("jel_effect")),
        "edge_overlap": _clean(row.get("edge_overlap")),
    }


def edge_id(store: GraphStore, source: str, target: str) -> str:
    return "{}>{}".format(store.node_to_id[source], store.node_to_id[target])


def edge_rows(store: GraphStore, source: str, target: str) -> pd.DataFrame:
    positions = store.pair_rows.get((source, target))
    if positions is None:
        return store.claims.iloc[0:0]
    return store.claims.iloc[positions]


def edge_summary(store: GraphStore, source: str, target: str) -> Dict[str, Any]:
    """Counts for one edge. Rows, distinct papers and records are reported separately."""
    rows = edge_rows(store, source, target)
    classes = Counter(
        classify_evidence(flag, method)
        for flag, method in zip(rows["is_method_causal_inference"], rows["causal_inference_method"])
    )
    papers = rows["paper_id"].dropna()
    return {
        "edge_id": edge_id(store, source, target),
        "source": source,
        "target": target,
        "source_id": store.node_to_id[source],
        "target_id": store.node_to_id[target],
        "claim_rows": int(len(rows)),
        "unique_papers": int(papers.nunique()),
        "rows_without_paper_id": int(len(rows) - len(papers)),
        "evidence_class_rows": dict(classes),
    }


def edge_evidence(store: GraphStore, source: str, target: str, limit: int = 50) -> Dict[str, Any]:
    """All supporting rows for an edge, merged only where displayed fields are identical."""
    rows = edge_rows(store, source, target)
    groups: Dict[tuple, Dict[str, Any]] = {}
    for position, (_, row) in zip(rows.index, rows.iterrows()):
        fields = _display_fields(row)
        key = tuple(sorted((k, str(v)) for k, v in fields.items()))
        if key not in groups:
            groups[key] = dict(fields, evidence_id="ev{}".format(position), row_ids=[])
        groups[key]["row_ids"].append(int(position))
    records = list(groups.values())
    for record in records:
        record["row_count"] = len(record["row_ids"])
    records.sort(key=lambda r: (r["year"] is None, r["year"] or 0, r["paper_id"] or ""))

    summary = edge_summary(store, source, target)
    summary.update({
        "evidence_records_total": len(records),
        "evidence_records_returned": min(limit, len(records)),
        "truncated": len(records) > limit,
        "evidence": records[:limit],
        "evidence_class_meaning": EVIDENCE_CLASS_MEANING,
        "unassessed": [
            "Whether the original papers actually support this link has not been verified here.",
            "Conditions, sign and magnitude are not extracted.",
        ],
    })
    return summary


def edge_paper_ids(store: GraphStore, source: str, target: str) -> set:
    """Distinct nonmissing paper ids behind one edge."""
    return set(edge_rows(store, source, target)["paper_id"].dropna())


def path_paper_overlap(store: GraphStore, nodes: List[str]) -> Dict[str, Any]:
    """Which papers (if any) appear on every edge of a path.

    If none do, the path joins findings across different papers, and compatibility of
    those findings has not been assessed.
    """
    sets = [edge_paper_ids(store, a, b) for a, b in zip(nodes, nodes[1:])]
    common = set.intersection(*sets) if sets else set()
    return {
        "papers_on_every_edge": sorted(common),
        "joins_findings_across_papers": len(nodes) > 2 and not common,
    }
