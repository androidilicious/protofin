"""ENGINEERING MOCK RESPONSES — for wiring and validation tests only.

These responses are produced by code, not by any model. They exercise the agent loop, the tool
protocol, schema validation, the native assessor's quote validation, the rubric and the encoder.
They carry no information about markets and must never be used as backtest results; records built
with them are marked engineering_mock and the shared evaluator refuses to score them.
"""
from __future__ import annotations

import re

from native_backtest.ap3.llm_client import Request


def responder(req: Request) -> dict:
    if req.step.startswith("hypothesis_turn_"):
        turn = int(req.step.rsplit("_", 1)[1])
        lib_ids = re.findall(r"\b(p\d{4}-[0-9a-f]{12})\b", req.user)
        trig = re.search(r'"trigger": "([A-Z_]+)"', req.user)
        if turn == 0:
            return {"action": "tool", "tool": "search_nodes", "args": {"query": "inflation", "limit": 3}}
        return {"action": "final", "hypotheses": [{
            "trigger": trig.group(1) if trig else "CPI", "channel": "inflation",
            "mechanism": "ENGINEERING MOCK: placeholder mechanism text for wiring tests.",
            "path_ids": lib_ids[:1] + ["p0000-000000000000"], "predicted_mediators": [{"series": "UST2Y", "sign": 1}],
            "predicted_assets": {"SPY": -1, "IEF": -1, "LQD": 0}, "confidence": "High"}]}
    if req.step.startswith("testing_plan_"):
        rid = re.findall(r"- (p\d{4}-[0-9a-f]{12}) \[", req.user)
        return {"implications": [{"observable": "MOCK observable", "would_contradict": "MOCK contradicting observation"}],
                "rival": {"rival_path_id": rid[0] if rid else None, "mechanism": "MOCK rival mechanism", "predicted_assets": {"SPY": 1, "IEF": 0, "LQD": 0}},
                "supporting_queries": ["retail sales consumer spending"], "contradicting_queries": ["weak demand decline"]}
    if req.step.startswith("assessor_"):
        edges = re.findall(r"edge_id: ([HR]:[A-Z]+)", req.user)
        ex = re.search(r'<excerpt chunk_id="([^"]+)" doc_id="([^"]+)"[^>]*>\n(.+?)\n', req.user, re.S)
        out = []
        for i, e in enumerate(edges):
            if i == 0 and ex:
                words = ex.group(3).split()[:8]
                out.append({"edge_id": e, "label": "supported", "supporting_evidence": [{"doc_id": ex.group(2), "chunk_id": ex.group(1), "quote": " ".join(words)}],
                            "contradicting_evidence": [], "conflict": False, "explanation": "MOCK"})
            elif i == 1:
                out.append({"edge_id": e, "label": "contradicted", "supporting_evidence": [],
                            "contradicting_evidence": [{"doc_id": "x", "chunk_id": "not-supplied#c000", "quote": "MOCK fabricated quote"}],
                            "conflict": False, "explanation": "MOCK: invalid citation that validation must downgrade"})
            else:
                out.append({"edge_id": e, "label": "insufficient_evidence", "supporting_evidence": [], "contradicting_evidence": [], "conflict": False, "explanation": "MOCK"})
        return {"assessments": out}
    raise ValueError(f"no mock for step {req.step}")
