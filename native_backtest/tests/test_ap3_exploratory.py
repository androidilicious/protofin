"""Exploratory (gate-failed) development backtest mode: it must never soften a gate, never reach the protected
window, never admit mock output, and never let a failed gate disappear from an output."""
import hashlib
import json
from pathlib import Path

import pytest

from native_backtest.ap3 import exploratory as X

ROOT = Path(__file__).resolve().parents[2]
FAILED = {"G3b": {"pass": False, "checks": {"accuracy": {"value": 0.5333333333333333, "pass": False},
                                            "opposite_direction_errors": {"value": 2, "pass": False},
                                            "injection_resisted": {"value": 3, "pass": True}}},
          "G3a": {"pass": False, "checks": {"failed_months": {"value": 12, "pass": False},
                                            "point_in_time_violations": {"value": 0, "pass": True}}}}
PASSED = {"G3b": {"pass": True, "checks": {}}, "G3a": {"pass": True, "checks": {}}}


def test_mode_is_opt_in_only(monkeypatch):
    monkeypatch.delenv("AP3_EXPLORATORY", raising=False)
    assert X.enabled() is False and X.enabled(False) is False
    assert X.enabled(True) is True
    monkeypatch.setenv("AP3_EXPLORATORY", "1")
    assert X.enabled() is True


def test_stamp_carries_the_real_failed_gate_values():
    out = X.stamp({"n_months": 95}, FAILED)
    e = out["exploratory"]
    assert e["label"] == X.LABEL and e["validated"] is False and e["usable_for_protected_window"] is False
    assert e["gate_thresholds_unchanged"] is True
    assert e["gates_failed"]["G3b"]["failed_checks"] == {"accuracy": 0.5333333333333333, "opposite_direction_errors": 2}
    assert e["gates_failed"]["G3a"]["failed_checks"] == {"failed_months": 12}
    assert "injection_resisted" not in e["gates_failed"]["G3b"]["failed_checks"]      # a passing check is not listed as failed
    assert out["n_months"] == 95 and X.is_exploratory(out)


def test_stamp_refuses_when_no_gate_failed():
    with pytest.raises(X.NotExploratory, match="no reliability gate failed"):
        X.stamp({}, PASSED)


def test_mode_can_never_reach_the_protected_window():
    with pytest.raises(X.NotExploratory, match="protected window"):
        X.assert_development_only(["2022-12", "2023-01"], "2023-01")
    with pytest.raises(X.NotExploratory, match="protected window"):
        X.stamp({}, FAILED, months=["2019-03", "2023-05"], protected_start="2023-01")
    X.assert_development_only(["2015-02", "2022-12"], "2023-01")                       # development is fine


def test_the_confirmatory_test_refuses_exploratory_records():
    src = (ROOT / "native_backtest/scripts/historical_evaluation.py").read_text()
    assert 'r.generation.get("exploratory")' in src and "EXPLORATORY gate-failed mode" in src
    from native_backtest.framework.records import DecisionRecord
    from native_backtest.scripts import historical_evaluation as H

    class _Rec:
        def __init__(self, gen):
            self.decision_month, self.generation = "2024-01", gen
    recs = [_Rec({"mode": "live_native", "exploratory": True})]
    assert any(r.generation.get("exploratory") for r in recs)                          # the condition the guard uses
    assert DecisionRecord is not None and H.SYSTEMS == ("AP1", "AP2B", "AP3")


def test_gate_thresholds_and_prompts_are_untouched_by_this_mode():
    g = json.loads((ROOT / "native_backtest/config/ap3_reliability_gates_v1.json").read_text())
    assert g["version"] == "1.0" and g["G3b_testing_agent_fixtures"]["accuracy_min"] == 0.8
    assert g["G3b_testing_agent_fixtures"]["opposite_direction_errors_max"] == 1 and g["G3a_first_12_months"]["failed_months_max"] == 1
    mode = X.load_mode()
    assert mode["gates"]["unchanged"] is True and mode["labelling"]["label"] == X.LABEL
    assert any("never" in n or "protected" in n for n in mode["never_permits"])
    fr = mode["frozen_for_reproduction"]
    assert fr["prompts_unchanged_since_run_1"] is True and fr["model"]["name"] == "qwen3:4b"
    # the recorded prompt hashes are the prompts the code actually uses
    from native_backtest.ap3 import hypothesis_agent, testing_agent
    assert fr["prompts_sha256"]["hypothesis_agent.SYSTEM"] == hashlib.sha256(hypothesis_agent.SYSTEM.encode()).hexdigest()
    assert fr["prompts_sha256"]["testing_agent.PLAN_SYSTEM"] == hashlib.sha256(testing_agent.PLAN_SYSTEM.encode()).hexdigest()


def test_runner_keeps_the_failed_exit_code_and_requires_the_flag(monkeypatch, tmp_path):
    from native_backtest.scripts import ap3_free_run as R
    monkeypatch.delenv("AP3_EXPLORATORY", raising=False)
    monkeypatch.setattr(R, "BUNDLE", tmp_path / "bundle")
    monkeypatch.setattr(R, "check", lambda: {"model": {}})
    monkeypatch.setattr(R, "g3b", lambda: {**FAILED["G3b"], "rows": []})
    monkeypatch.setattr(R, "run_months", lambda ms, deadline, workers: {m: {} for m in ms})
    monkeypatch.setattr(R, "g3a", lambda recs: FAILED["G3a"])
    seen = {}
    monkeypatch.setattr(R, "bundle", lambda *a, **k: seen.update(k) or {})
    monkeypatch.setattr(R, "run_months", lambda ms, deadline, workers: {m: {} for m in ms})
    assert R.main(["--stage", "all"]) == R.GATE_FAILED                      # without the flag: no replay
    assert seen.get("exploratory") is False
    ran = []
    monkeypatch.setattr(R, "run_months", lambda ms, deadline, workers: (ran.append(ms), {m: {} for m in ms})[1])
    assert R.main(["--stage", "all", "--exploratory"]) == R.GATE_FAILED     # with the flag: replay runs, code still 3
    assert seen.get("exploratory") is True
    assert ran and ran[-1][-1] <= "2022-12"                                 # and never past the development window


def test_import_requires_the_banner_and_the_full_history(tmp_path, monkeypatch):
    from native_backtest.scripts import ap3_free_import as im

    def bundle(dirname, months, summary_extra):
        d = tmp_path / dirname / "qwen3_runs"
        (d / "months").mkdir(parents=True)
        shas = []
        for m in months:
            sha = hashlib.sha256(m.encode()).hexdigest()
            shas.append(sha)
            (d / "months" / f"{m}.json").write_text(json.dumps(
                {"month": m, "status_features": {a: {"F_S": 0.0, "F_C": 0.0, "F_I": 0.0} for a in ("SPY", "IEF", "LQD")},
                 "record_sha256": sha, "engineering_mock": False, "provider": "ollama_local", "model": "qwen3:4b@359d7dd4bcda",
                 "hypothesis_agent": {"failure": "no final answer within the turn limit"}, "hypotheses": []}))
        (d / "summary.json").write_text(json.dumps({"records_chain_sha256": hashlib.sha256("".join(shas).encode()).hexdigest(),
                                                    "gates": FAILED, "cost_usd": 0.0, **summary_extra}))
        return d
    ran = []
    monkeypatch.setattr(im, "evaluate", lambda months, summary, explor=False: ran.append(explor) or {"status": "x", "coverage": {}})
    monkeypatch.setattr(im, "BUNDLE", tmp_path / "imported")
    from native_backtest.framework.market import months_between
    full = [str(m) for m in months_between(*im.AGENT_MONTHS)]
    assert len(full) == 95
    report = lambda: json.loads((tmp_path / "imported" / "import_report.json").read_text())
    # a complete history, gates failed, no banner: refused, and the gates are not quietly ignored
    assert im.main(["--from-dir", str(bundle("a", full, {}))]) == 0
    assert "does not carry the exploratory banner" in report()["evaluation"] and ran == []
    # the banner alone does not buy a score: an incomplete history says how many months exist
    stamped = X.stamp({}, FAILED)
    assert im.main(["--from-dir", str(bundle("b", ["2015-02", "2015-03"], stamped))]) == 0
    assert "2 of 95 agent months" in report()["evaluation"] and report()["exploratory"] is True and ran == []
    # complete history plus the banner: evaluated, as an explicitly exploratory run
    assert im.main(["--from-dir", str(bundle("c", full, stamped))]) == 0
    assert ran == [True] and report()["exploratory"] is True and report()["label"] == X.LABEL


def test_coverage_counts_failures_and_never_invents_months():
    from native_backtest.scripts import ap3_free_import as im
    months = {"2019-03": {"hypothesis_agent": {"failure": "no final answer within the turn limit"}, "hypotheses": []},
              "2019-04": {"hypothesis_agent": {}, "hypotheses": [{"status": "Insufficient", "test_failure": None},
                                                                 {"status": "Supported", "test_failure": None}]},
              "2019-05": {"hypothesis_agent": {}, "hypotheses": [{"status": "Insufficient", "test_failure": "testing agent: invalid output"}]}}
    c = im.coverage(months, ["2019-03", "2019-04", "2019-05", "2019-06"])
    assert c["scored_months_present"] == 3 and c["scored_months_expected"] == 4          # 2019-06 absent, not invented
    assert c["scored_months_with_at_least_one_hypothesis"] == 2
    assert c["scored_months_without_hypotheses"] == ["2019-03"]
    assert c["n_months_with_agent_failure"] == 1 and c["tests"] == 3 and c["failed_tests"] == 1
    assert c["status_counts"] == {"Insufficient": 2, "Supported": 1}


HAS_CLAIMS = (ROOT / "native_backtest/data/_external/claims_part01.parquet").exists()


@pytest.mark.skipif(not HAS_CLAIMS, reason="claims data not fetched")
def test_exploratory_bundle_from_a_genuine_month_carries_the_banner(tmp_path, monkeypatch):
    """One real month through the unchanged pipeline against a local server, bundled in exploratory mode: the
    banner, the failed gates and the freeze record must all be in the committed summary."""
    import pandas as pd
    from native_backtest.ap3 import runner
    from native_backtest.ap3.engineering_fixtures import fixture_mediators
    from native_backtest.ap3.graph_vintage import build_vintage, load_concepts
    from native_backtest.ap3 import llm_client as L
    from native_backtest.scripts import ap3_free_run as fr
    from native_backtest.tests.test_ap3 import _pool
    from native_backtest.tests.test_ap3_free import _Fake                      # the local fake Ollama server
    from http.server import HTTPServer
    import threading

    srv = HTTPServer(("127.0.0.1", 0), _Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("AP3_OLLAMA_URLS", f"http://127.0.0.1:{srv.server_port}")
    _Fake.seen.clear()
    try:
        concepts, limits = load_concepts(), runner.load_limits()
        lib = json.loads((ROOT / "native_backtest/data/_external/ap3_libraries/library_v1.0_vintage2018.json").read_text())
        packet = runner.build_packet("2019-06", "2019-06-28T20:00:00-04:00", {"CPI": 1.4}, [], [], concepts, limits)
        client = L.LLMClient(L.OllamaProvider(), tmp_path / "c", tmp_path / "calls.jsonl", "t")
        rec = runner.run_month(client, packet, build_vintage(2018, concepts), lib, [], fixture_mediators(),
                               pd.Timestamp("2019-06-01"), limits, evidence=_pool(), max_parallel_tests=2)
        assert rec["engineering_mock"] is False and rec["provider"] == "ollama_local"
        monkeypatch.setattr(fr, "BUNDLE", tmp_path / "bundle")
        monkeypatch.setattr(fr, "_out", lambda: tmp_path)
        env = {"model": {"servers": [{"digest": "359d7dd4bcda0000"}]}}
        s = fr.bundle({"2019-06": rec}, FAILED, env, None, exploratory=True)
    finally:
        srv.shutdown()
    assert s["exploratory"]["label"] == X.LABEL and s["exploratory"]["validated"] is False
    assert s["exploratory"]["gates_failed"]["G3b"]["failed_checks"]["accuracy"] == pytest.approx(0.5333, abs=1e-3)
    assert s["baseline_identity"] == "Approach 3 — Qwen3:4B Original Prompt Baseline"
    fr_frozen = s["frozen_for_reproduction"]
    assert fr_frozen["model"]["name"] == "qwen3:4b" and fr_frozen["agent_protocol"]["version"] == "1.1"
    assert fr_frozen["prompts_unchanged_since_run_1"] is True
    # the gates in the bundle keep their real values, unchanged
    assert s["gates"]["G3b"]["checks"]["accuracy"]["value"] == pytest.approx(0.5333, abs=1e-3)
    assert s["gates"]["G3b"]["pass"] is False and s["gates"]["G3a"]["pass"] is False
