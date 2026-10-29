"""Free local inference path (qwen3:4b through Ollama). These tests use a FAKE local server that answers with the
engineering mock; they check wiring, safety refusals and the gate logic. Nothing here is a model result."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pandas as pd
import pytest

from native_backtest.ap3 import engineering_mock, hypothesis_agent, llm_client as L, testing_agent

ROOT = Path(__file__).resolve().parents[2]
HAS_CLAIMS = (ROOT / "native_backtest/data/_external/claims_part01.parquet").exists()


def _step(system: str, user: str, n_assistant: int = 0) -> str:
    if system.startswith("You are the Hypothesis Agent"):
        return f"hypothesis_turn_{n_assistant}"          # turn protocol 1.1: the agent's own replies come back as assistant turns
    if system == testing_agent.PLAN_SYSTEM:
        return "testing_plan_x"
    if system == testing_agent.native_assess.SYSTEM:
        return "assessor_x"
    return "canary_x"


class _Fake(BaseHTTPRequestHandler):
    digest = L.OLLAMA_DIGEST_PREFIX + "0" * 52
    seen = []

    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path == "/api/tags":
            self._send({"models": [{"name": "qwen3:4b", "model": "qwen3:4b", "digest": self.digest, "size": 2_500_000_000}]})
        else:
            self._send({"version": "fake-0.0"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Fake.seen.append(body)
        sys_, usr = body["messages"][0]["content"], body["messages"][1]["content"]
        st = _step(sys_, usr, sum(m["role"] == "assistant" for m in body["messages"]))
        reply = {"ok": True} if st == "canary_x" else engineering_mock.responder(L.Request(step=st, system=sys_, user=usr, schema={}, temperature=0, seed=0))
        self._send({"message": {"content": json.dumps(reply)}, "prompt_eval_count": len(usr) // 4, "eval_count": 50,
                    "done_reason": "stop", "total_duration": 1_000_000})


@pytest.fixture
def fake_ollama(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), _Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("AP3_OLLAMA_URLS", f"http://127.0.0.1:{srv.server_port}")
    _Fake.seen.clear()
    yield srv
    srv.shutdown()


def test_free_provider_is_local_only_pinned_and_never_truncates(fake_ollama, tmp_path):
    with pytest.raises(L.PaidInferenceNotApproved, match="this machine"):
        L.OllamaProvider("https://api.example.com")                      # no remote (possibly paid) service
    p = L.OllamaProvider()
    prov = p.verify()
    assert prov["servers"][0]["digest"].startswith(L.OLLAMA_DIGEST_PREFIX) and p.model == "qwen3:4b@359d7dd4bcda"
    c = L.LLMClient(p, tmp_path / "c", tmp_path / "calls.jsonl", "t")      # free: no cost guard needed
    schema = {"type": "object", "required": ["ok"], "properties": {"ok": {"type": "boolean"}}}
    obj, meta = c.complete_json(L.Request(step="canary_1", system="s", user="u", schema=schema, temperature=0.0, seed=0))
    assert obj == {"ok": True}
    sent = _Fake.seen[-1]
    assert sent["think"] is False and sent["format"] == schema and sent["options"]["seed"] == 0 and sent["options"]["num_ctx"] == 32768
    log = json.loads((tmp_path / "calls.jsonl").read_text().splitlines()[-1])
    assert log["usage"]["completion_tokens"] == 50 and log["mock"] is False
    with pytest.raises(L.ContextOverflow):
        p.complete(L.Request(step="big", system="s", user="x" * 140_000, schema=schema, temperature=0.0, seed=0))
    _Fake.digest = "deadbeef" + "0" * 56
    try:
        with pytest.raises(L.ModelOutputError, match="not the pinned"):
            L.OllamaProvider().verify()
    finally:
        _Fake.digest = L.OLLAMA_DIGEST_PREFIX + "0" * 52


@pytest.mark.skipif(not HAS_CLAIMS, reason="claims data not fetched")
def test_free_month_end_to_end_and_redacted_bundle(fake_ollama, tmp_path, monkeypatch):
    from native_backtest.ap3 import runner
    from native_backtest.ap3.graph_vintage import build_vintage, load_concepts
    from native_backtest.ap3.engineering_fixtures import fixture_mediators
    from native_backtest.scripts import ap3_free_run as fr
    from native_backtest.tests.test_ap3 import _pool
    concepts, limits = load_concepts(), runner.load_limits()
    lib = json.loads((ROOT / "native_backtest/data/_external/ap3_libraries/library_v1.0_vintage2018.json").read_text())
    packet = runner.build_packet("2019-06", "2019-06-28T20:00:00-04:00", {"CPI": 1.4}, [], [], concepts, limits)
    client = L.LLMClient(L.OllamaProvider(), tmp_path / "c", tmp_path / "calls.jsonl", "t")
    rec = runner.run_month(client, packet, build_vintage(2018, concepts), lib, [], fixture_mediators(), pd.Timestamp("2019-06-01"), limits,
                           evidence=_pool(), max_parallel_tests=2)
    assert rec["provider"] == "ollama_local" and rec["model"] == "qwen3:4b@359d7dd4bcda" and rec["tests"][0]["runs"]
    monkeypatch.setattr(fr, "BUNDLE", tmp_path / "bundle")
    monkeypatch.setattr(fr, "_out", lambda: tmp_path)
    s = fr.bundle({"2019-06": rec}, {"G3b": {"pass": True}}, {"model": {"servers": [{"digest": "359d7dd4bcda..."}]}}, None)
    assert s["n_months"] == 1 and s["cost_usd"] == 0.0 and s["model_substitution"]["planned"].startswith("meta-llama")
    m = json.loads((tmp_path / "bundle/months/2019-06.json").read_text())
    h = m["hypotheses"][0]
    assert all("links" in v for v in h["cited_pathways"].values()) and all("title" not in x for x in h["research_records"])
    with pytest.raises(SystemExit, match="engineering-mock"):
        fr.bundle({"2019-06": {**rec, "engineering_mock": True}}, {}, {}, None)


def test_replay_starts_only_after_both_pre_registered_gates_pass(tmp_path, monkeypatch):
    from native_backtest.scripts import ap3_free_run as fr
    monkeypatch.setattr(fr, "BUNDLE", tmp_path / "bundle")
    monkeypatch.setattr(fr, "_out", lambda: tmp_path)
    monkeypatch.setattr(fr, "check", lambda: {"model": {}})
    monkeypatch.setattr(fr, "bundle", lambda *a, **k: {})
    ran = []
    monkeypatch.setattr(fr, "run_months", lambda ms, d, w: (ran.append(list(ms)), {m: {"status_features": {}} for m in ms})[1])
    monkeypatch.setattr(fr, "g3a", lambda recs: {"pass": True, "checks": {}})
    monkeypatch.setattr(fr, "g3b", lambda: {"pass": False, "checks": {}})
    fr.main(["--stage", "all", "--hours", "1"])
    assert len(ran) == 1 and ran[0][0] == "2015-02" and len(ran[0]) == 12      # sample only: G3b failed
    ran.clear()
    monkeypatch.setattr(fr, "g3b", lambda: {"pass": True, "checks": {}})
    monkeypatch.setattr(fr, "g3a", lambda recs: {"pass": False, "checks": {}})
    fr.main(["--stage", "all", "--hours", "1"])
    assert len(ran) == 1                                                         # G3a failed: no replay
    ran.clear()
    monkeypatch.setattr(fr, "g3a", lambda recs: {"pass": True, "checks": {}})
    monkeypatch.setattr(fr.time, "time", lambda: 0.0)
    from native_backtest.scripts import ap3_dev_replay as rp
    called = []
    monkeypatch.setattr(rp, "downstream", lambda recs, out, mock: called.append(len(recs)))
    fr.main(["--stage", "all", "--hours", "1"])
    assert called == []                                                          # calibration runs at import, never on the GPU machine
    assert ran[1][0] == "2016-02" and sum(len(x) for x in ran[1:]) == 83          # gates passed: 2016-02..2022-12 in batches


def test_free_runner_never_touches_the_protected_window():
    from native_backtest.scripts import ap3_free_run as fr
    assert fr.months(*fr.REPLAY)[-1] == "2022-12" and fr.months(*fr.SAMPLE)[0] == "2015-02"
    assert len(fr.months(*fr.SAMPLE)) + len(fr.months(*fr.REPLAY)) == 95


def _bundle(tmp, months, **over):
    import hashlib
    d = tmp / "qwen3_runs"
    (d / "months").mkdir(parents=True, exist_ok=True)
    shas = []
    for m in months:
        sha = hashlib.sha256(m.encode()).hexdigest()
        shas.append(sha)
        j = {"month": m, "status_features": {a: {"F_S": 0.0, "F_C": 0.0, "F_I": 0.0} for a in ("SPY", "IEF", "LQD")},
             "record_sha256": sha, "engineering_mock": False, "provider": "ollama_local", "model": "qwen3:4b@359d7dd4bcda", **over}
        (d / "months" / f"{m}.json").write_text(json.dumps(j))
    (d / "summary.json").write_text(json.dumps({"records_chain_sha256": hashlib.sha256("".join(shas).encode()).hexdigest(),
                                                "gates": {"G3b": {"pass": True}, "G3a": {"pass": True}}, "cost_usd": 0.0}))
    return d


def test_import_refuses_mock_wrong_model_protected_months_and_tampering(tmp_path):
    from native_backtest.scripts import ap3_free_import as im
    assert len(im.validate(_bundle(tmp_path / "a", ["2015-02", "2015-03"]))["months"]) == 2
    with pytest.raises(im.ImportError_, match="not a genuine"):
        im.validate(_bundle(tmp_path / "b", ["2015-02"], engineering_mock=True))
    with pytest.raises(im.ImportError_, match="not a genuine"):
        im.validate(_bundle(tmp_path / "c", ["2015-02"], model="llama3:8b"))
    with pytest.raises(im.ImportError_, match="protected window"):
        im.validate(_bundle(tmp_path / "d", ["2023-01"]))
    d = _bundle(tmp_path / "e", ["2015-02"])
    j = json.loads((d / "months/2015-02.json").read_text()); j["record_sha256"] = "0" * 64
    (d / "months/2015-02.json").write_text(json.dumps(j))
    with pytest.raises(im.ImportError_, match="hash chain"):
        im.validate(d)


def test_import_evaluation_path_runs_on_the_development_window(tmp_path, monkeypatch):
    """Wiring only: zero status features in a temporary folder. Never written to the real outputs."""
    from native_backtest.ap3 import calibration
    from native_backtest.framework.market import months_between
    from native_backtest.scripts import ap3_free_import as im
    monkeypatch.setattr(im, "BUNDLE", tmp_path / "bundle")
    monkeypatch.setattr(im, "DECISIONS", tmp_path / "AP3.jsonl")
    monkeypatch.setattr(calibration, "permutation_placebo", lambda *a, **k: {"skipped_in_test": True})
    v = im.validate(_bundle(tmp_path, [str(m) for m in months_between("2015-02", "2022-12")]))
    res = im.evaluate(v["months"], v["summary"])
    assert res["months"][:2] == ["2019-03", "2022-12"] and "model substitution" in res["status"]
    assert set(res["primary_contrasts_development"]) == {"AP3-AP1", "AP3-AP2B"}
    from native_backtest.framework.records import read_jsonl
    recs = read_jsonl(tmp_path / "AP3.jsonl")
    assert len(recs) == 46 and all(abs(sum(r.target_weights.values()) - 1) < 1e-9 for r in recs)
