"""Regression tests for the defects found in the first real-model run (qwen3:4b, 2026-10-29, ap3-qwen3-runs @ 790a049).

Each test pins one defect so it cannot return:
1. the Hypothesis Agent never received the "final answer now" turn after its tool budget (all 12 G3a months failed);
2. the agent's own earlier calls were pasted into the user message instead of being sent back as assistant turns;
3. node search matched substrings ("PPI" -> "happiness"), contradicting its documented whole-word matching;
4. a repeated identical tool call was silently re-run;
5. any rival_path_id string (e.g. "none") created rival edges, though the rival must be one of the candidates;
6. the runner exited 0 although both gates failed;
7. a rerun would have reused the failed attempt's results;
8. the GitHub token was written into git remote URLs inside the saved output folder.
The pre-registered gate thresholds are checked to be unchanged.
"""
import ast
import json
import re
import tempfile
from pathlib import Path

import pytest

from native_backtest.ap3 import hypothesis_agent as HA
from native_backtest.ap3 import llm_client as L
from native_backtest.ap3 import protocol, runner, testing_agent
from native_backtest.ap3.mediators import MediatorStore

ROOT = Path(__file__).resolve().parents[2]
HAS_CLAIMS = (ROOT / "native_backtest/data/_external/claims_part01.parquet").exists()
FIXTURES = json.loads((ROOT / "native_backtest/ap3/fixtures/testing_agent_fixtures_v1.json").read_text())["fixtures"]


@pytest.fixture(scope="module")
def graph():
    if not HAS_CLAIMS:
        pytest.skip("claims data not fetched")
    from native_backtest.ap3.graph_vintage import build_vintage, load_concepts
    from native_backtest.scripts import ap3_dev_replay as rp
    concepts = load_concepts()
    return {"concepts": concepts, "vintage": build_vintage(2014, concepts),
            "library": json.loads((rp.LIBS / "library_v1.0_vintage2014.json").read_text()), "packet": rp.load_packets()["2015-04"]}


def _client(fn):
    tmp = Path(tempfile.mkdtemp())
    return L.LLMClient(L.EngineeringMockProvider(fn), tmp / "c", tmp / "calls.jsonl", "test")


def _run(graph, fn):
    from native_backtest.ap3.tools import CauseTraceTools
    limits = runner.load_limits()
    tools = CauseTraceTools(graph["vintage"], graph["concepts"], budget=limits["hypothesis_agent"]["max_tool_calls"])
    reqs = []
    def rec(req):
        reqs.append(req)
        return fn(req)
    return HA.run(_client(rec), graph["packet"], graph["library"], tools, limits), reqs


SAME_CALL = {"action": "tool", "tool": "search_nodes", "args": {"query": "FOMC", "limit": 10}}   # what qwen3:4b repeated in 2015-04


def test_final_answer_turn_is_given_after_the_tool_budget(graph):
    """Kaggle 2015-04: 15 identical calls, 16 turns, no final answer. A model that answers when asked now can."""
    def answers_when_asked(req):
        last = req.turns[-1]["content"] if req.turns else req.user
        return {"action": "final", "hypotheses": []} if "Give your final answer now" in last else SAME_CALL
    out, reqs = _run(graph, answers_when_asked)
    assert out.get("failure") is None and out["final_answer_forced"] is True
    assert len(out["turns"]) == 16 and len(out["tool_calls"]) == 15 and out["duplicate_tool_calls"] == 14
    assert reqs[-1].schema["properties"]["action"] == {"const": "final"} and "oneOf" not in reqs[-1].schema   # final-answer schema only
    assert all("oneOf" in r.schema for r in reqs[:-1])


def test_a_model_that_still_calls_a_tool_on_the_final_turn_fails_honestly(graph):
    with pytest.raises(L.ModelOutputError, match="hypothesis_turn_15"):
        _run(graph, lambda req: SAME_CALL)          # violates the final-answer schema: a recorded month failure, not a pass


def test_agent_replies_return_as_assistant_turns(graph):
    def two_calls_then_final(req):
        n = sum(t["role"] == "assistant" for t in req.turns)
        return [{"action": "tool", "tool": "search_nodes", "args": {"query": "inflation", "limit": 3}},
                {"action": "tool", "tool": "search_nodes", "args": {"query": "FOMC", "limit": 3}}][n] if n < 2 else {"action": "final", "hypotheses": []}
    out, reqs = _run(graph, two_calls_then_final)
    assert [len(r.turns) for r in reqs] == [0, 2, 4]
    assert all(r.user == reqs[0].user for r in reqs)                                  # the packet message is unchanged
    assert "YOUR TOOL CALL" not in reqs[2].user and [t["role"] for t in reqs[2].turns] == ["assistant", "user", "assistant", "user"]
    assert json.loads(reqs[2].turns[0]["content"]) == out["turns"][0]["output"] and reqs[2].turns[1]["content"].startswith("TOOL RESULT: ")
    assert out["final_answer_forced"] is False and out["duplicate_tool_calls"] == 0


def test_node_search_matches_whole_words(graph):
    from native_backtest.ap3.tools import CauseTraceTools
    t = CauseTraceTools(graph["vintage"], graph["concepts"], budget=15)
    ppi = [x["node"] for x in t.call("search_nodes", {"query": "PPI", "limit": 10})]
    assert ppi and all("ppi" in re.findall(r"[a-z0-9]+", n) for n in ppi) and "happiness" not in ppi
    assert not [x for x in t.call("search_nodes", {"query": "AHE", "limit": 10}) if "ahead" in x["node"]]
    assert "industrial production" in [x["node"] for x in t.call("search_nodes", {"query": "INDUSTRIAL_PRODUCTION", "limit": 10})]
    err = t.call("paths", {"source": "PPI", "target": "SPY", "max_paths": 25})["error"]
    assert "trigger codes" in err and "tickers" in err


def test_repeated_tool_call_is_flagged_not_rerun(graph):
    from native_backtest.ap3.tools import CauseTraceTools
    t = CauseTraceTools(graph["vintage"], graph["concepts"], budget=3)
    first = t.call("search_nodes", {"query": "FOMC", "limit": 10})
    again = t.call("search_nodes", {"query": "FOMC", "limit": 10})
    assert isinstance(first, list) and again["repeat"] is True and t.calls[1]["duplicate_of"] == 0 and t.remaining == 1


def _fixture_args(f):
    packet = {"decision_month": f["decision_time"][:7], "decision_time": f["decision_time"],
              "triggers": [{**f["trigger"], "description": "Consumer price index release"}]}
    return packet, {"hypothesis_id": f"G3B-{f['id']}", **f["hypothesis"]}


def test_rival_must_be_one_of_the_candidates():
    """Protocol step 3: a candidate rival path_id, or none. Version 1.0 accepted any string (e.g. "none") and built
    rival edges from it; now the schema allows only the candidates or null, and anything else is rejected, not used."""
    f = next(x for x in FIXTURES if x["id"] == "S01")
    packet, hyp = _fixture_args(f)
    limits = runner.load_limits()

    def model(rival_id):
        def fn(req):
            if req.step.startswith("testing_plan_"):
                return {"implications": [{"observable": "x", "would_contradict": "y"}],
                        "rival": {"rival_path_id": rival_id, "mechanism": "rival", "predicted_assets": {"SPY": 1, "IEF": 1, "LQD": 0}},
                        "supporting_queries": ["CPI Treasury yields"], "contradicting_queries": ["yields fell"]}
            return {"assessments": [{"edge_id": e, "label": "insufficient_evidence", "supporting_evidence": [], "contradicting_evidence": [],
                                     "conflict": False, "explanation": "x"} for e in re.findall(r"edge_id: (\S+)", req.user)]}
        return fn

    assert testing_agent.plan_schema([])["properties"]["rival"]["properties"]["rival_path_id"] == {"enum": [None]}
    with pytest.raises(L.ModelOutputError, match="testing_plan_"):          # "none" as a string is invalid, never a rival
        testing_agent.test_hypothesis(_client(model("none")), packet, hyp, [], [], f["excerpts"], MediatorStore({}), limits, "2018-02-01")
    t = testing_agent.test_hypothesis(_client(model(None)), packet, hyp, [], [], f["excerpts"], MediatorStore({}), limits, "2018-02-01")
    assert all(r["rival_valid"] is False and not any(i["edge_id"].startswith("R:") for i in r["assessments"]) for r in t["runs"])
    cand = [{"path_id": "p2017-aaaaaaaaaaaa", "channel": "growth", "path": ["a", "b"]}]
    t = testing_agent.test_hypothesis(_client(model("p2017-aaaaaaaaaaaa")), packet, hyp, [], cand, f["excerpts"], MediatorStore({}), limits, "2018-02-01")
    assert all(r["rival_valid"] is True and any(i["edge_id"].startswith("R:") for i in r["assessments"]) for r in t["runs"])


def _oracle(req, by_id):
    """A correct assessor with verbatim quotes, for the synthetic fixtures only."""
    f = by_id[re.search(r"G3B-([A-Z]\d\d)", req.step).group(1)]
    if req.step.startswith("testing_plan_"):
        m = f["hypothesis"]["mechanism"]
        return {"implications": [{"observable": m, "would_contradict": "the opposite"}],
                "rival": {"rival_path_id": None, "mechanism": "none", "predicted_assets": {"SPY": 0, "IEF": 0, "LQD": 0}},
                "supporting_queries": [m[:200]], "contradicting_queries": [("did not " + m)[:200]]}
    lab = {"Supported": "supported", "Contradicted": "contradicted", "Insufficient": "insufficient_evidence"}[f["expected_status"]]
    chunks = re.findall(r'<excerpt chunk_id="([^"]+)" doc_id="([^"]+)"[^>]*>\n(.*?)\n</excerpt>', req.user, re.S)
    ev = [{"doc_id": d, "chunk_id": c, "quote": " ".join(re.split(r"(?<=[.!?])\s+", t.strip())[0].split()[:35])} for c, d, t in chunks]
    return {"assessments": [{"edge_id": e, "label": lab, "supporting_evidence": ev if lab == "supported" else [],
                             "contradicting_evidence": ev if lab == "contradicted" else [], "conflict": False, "explanation": "oracle"}
                            for e in re.findall(r"edge_id: (\S+)", req.user)]}


def test_g3b_pipeline_returns_every_expected_status_for_a_correct_assessor(monkeypatch, tmp_path):
    """The real run's 16/30 is not a pipeline limitation: retrieval, quote validation, rubric and majority return all
    30 expected statuses when the model answers correctly, with exactly the 177 calls the real run made."""
    from native_backtest.scripts import ap3_g3b_fixtures as G
    from native_backtest.scripts import ap3_dev_replay as rp
    by_id = {f["id"]: f for f in FIXTURES}
    monkeypatch.setattr(rp, "make_client", lambda provider, variant, out: L.LLMClient(L.EngineeringMockProvider(lambda r: _oracle(r, by_id)),
                                                                                     tmp_path / "c", tmp_path / "calls.jsonl", "oracle"))
    monkeypatch.setattr(G, "out_dir", lambda provider: tmp_path)
    res = G.run("engineering_mock")
    sc = G.score(res["rows"])
    assert sc["pass"] and sc["checks"]["accuracy"]["value"] == 1.0 and res["calls"] == 177
    s01 = next(r for r in res["rows"] if r["id"] == "S01")                          # per-fixture diagnostics are complete
    a = s01["runs"][0]["assessments"][0]
    assert a["model_label"] == "supported" and a["valid_supporting"] >= 2 and all(q["citation"] == "valid" for q in a["supporting"])


def test_runner_exits_non_zero_when_a_gate_fails(monkeypatch, tmp_path):
    from native_backtest.scripts import ap3_free_run as R
    failed_g3b = {"gate": "G3b", "checks": {"accuracy": {"value": 0.53, "pass": False}}, "pass": False, "rows": []}
    monkeypatch.setattr(R, "BUNDLE", tmp_path / "bundle")
    monkeypatch.setattr(R, "check", lambda: {"model": {}})
    monkeypatch.setattr(R, "g3b", lambda: failed_g3b)
    assert R.main(["--stage", "g3b"]) == R.GATE_FAILED == 3
    failed_g3a = {"checks": {"failed_months": {"value": 12, "pass": False}}, "pass": False, "reliability": {}}
    monkeypatch.setattr(R, "run_months", lambda ms, deadline, workers: {m: {} for m in ms})
    monkeypatch.setattr(R, "g3a", lambda recs: failed_g3a)
    monkeypatch.setattr(R, "bundle", lambda *a, **k: {})
    assert R.main(["--stage", "all"]) == 3
    assert R.main(["--stage", "sample"]) == 3


def test_results_from_another_protocol_are_never_reused(monkeypatch, tmp_path):
    from native_backtest.scripts import ap3_free_run as R
    b = tmp_path / "qwen3_runs"
    (b / "months").mkdir(parents=True)
    (b / "summary.json").write_text(json.dumps({"gates": {"G3a": {"pass": False, "checks": {}}}}))     # protocol 1.0: no fingerprint
    monkeypatch.setattr(R, "BUNDLE", b)
    note = R.set_aside_stale_bundle()
    assert note and not b.exists() and (tmp_path / "qwen3_runs_superseded_v1.0").exists()
    b.mkdir()
    (b / "summary.json").write_text(json.dumps({"protocol": {"fingerprint": protocol.fingerprint()}}))
    assert R.set_aside_stale_bundle() is None and b.exists()                                       # same protocol: kept
    src = (ROOT / "native_backtest/scripts/ap3_dev_replay.py").read_text()
    assert 'r.get("protocol_fingerprint") == fp' in src and 'rec["protocol_fingerprint"] = fp' in src
    assert '.get("protocol_fingerprint") == _fingerprint()' in (ROOT / "native_backtest/scripts/ap3_free_run.py").read_text()


def test_no_token_in_git_urls():
    for f in ("native_backtest/scripts/ap3_free_run.py", "native_backtest/notebooks/ap3_qwen3_free_run.ipynb"):
        text = (ROOT / f).read_text()
        assert "x-access-token:{" not in text and "x-access-token:{TOKEN}" not in text, f
    tree = ast.parse((ROOT / "native_backtest/scripts/ap3_free_run.py").read_text())
    urls = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.startswith("https://github.com")]
    assert urls == ["https://github.com/androidilicious/protofin.git"]


def test_gate_thresholds_and_limits_are_unchanged():
    g = json.loads((ROOT / "native_backtest/config/ap3_reliability_gates_v1.json").read_text())
    assert g["version"] == "1.0" and g["G3b_testing_agent_fixtures"]["accuracy_min"] == 0.8
    assert g["G3b_testing_agent_fixtures"]["opposite_direction_errors_max"] == 1 and g["G3a_first_12_months"]["failed_months_max"] == 1
    assert g["G3a_first_12_months"]["schema_valid_call_rate_min"] == 0.98
    lim = runner.load_limits()
    assert (lim["hypothesis_agent"]["max_tool_calls"], lim["hypothesis_agent"]["max_turns"], lim["hypothesis_agent"]["temperature"]) == (15, 16, 0.0)
    assert lim["testing_agent"]["runs"] == 3 and lim["testing_agent"]["temperature"] == 0.3
    assert len(FIXTURES) == 30
