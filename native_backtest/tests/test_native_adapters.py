"""Native fidelity tests for the AP1 and AP2 adapters (development data only)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from native_backtest.adapters import ap2_native as a
from native_backtest.framework.records import FORBIDDEN_KEYS, read_jsonl

ROOT = Path(__file__).resolve().parents[2]


def test_vendored_files_match_provenance():
    prov = json.loads((ROOT / "native_backtest/vendor/PROVENANCE.json").read_text())
    for f in prov["files"]:
        assert hashlib.sha256((ROOT / f["vendored_path"]).read_bytes()).hexdigest() == f["sha256"], f["vendored_path"]


@pytest.fixture(scope="module")
def js(tmp_path_factory):
    d = tmp_path_factory.mktemp("node")
    return {
        "committee": a.run_node(a.A2 / "site/js", "decisions", "committee", d / "c.json")["rows"],
        "jev_fj": a.run_node(a.FJ / "site/js", "decisions", "jev", d / "j1.json")["rows"],
        "jev_a2": a.run_node(a.A2 / "site/js", "decisions", "jev", d / "j2.json")["rows"],
    }


def test_committee_js_equals_native_python(js):
    assert a.check_committee_against_native_python(js["committee"])["pass"]


def test_committee_native_parser_reparse():
    r = a.check_committee_reparse()
    assert r["pass"] and r["deterministic_cached_replies"] == 272


def test_jev_matches_saved_log_on_both_branches(js):
    assert a.check_jev(js["jev_fj"], js["jev_a2"])["pass"]


def test_native_engine_decides_without_outcomes(js):
    # the harness deletes r_spy, r_tlt and next before decide(); decisions still exist for every month
    assert len(js["committee"]) == 272 and all(0.4 <= r["w_spy"] <= 0.8 for r in js["committee"])


def test_native_dev_performance_reproduced(tmp_path):
    last = "2022-12-30"
    rows = a.run_node(a.A2 / "site/js", "decisions", "committee", tmp_path / "c.json")["rows"]
    nat = a.run_node(a.A2 / "site/js", "native-dev", "committee", tmp_path / "n.json", last_as_of=last)
    rep = a.native_execution_replica({r["as_of"]: r["w_spy"] for r in rows}, last)
    assert len(rep) == nat["n"] == 228
    assert max(abs(x["nav_live"] - y) for x, y in zip(nat["log"], rep["nav"])) < 1e-12


def test_decision_files_have_no_outcomes():
    for s in ("AP1", "AP2A", "AP2B"):
        p = ROOT / f"native_backtest/out/decisions/{s}.jsonl"
        if not p.exists():
            pytest.skip("decision files not built")
        text = p.read_text()
        for k in FORBIDDEN_KEYS:
            assert f'"{k}"' not in text, (s, k)
        assert read_jsonl(p)


def test_ap1_shared_evaluator_reproduces_stage2():
    from native_backtest.framework.accounting import simulate_records
    from native_backtest.framework.market import load_config, load_market
    run = ROOT / "stage2/results/dev_rerun_v4_portfolio_2026-10-27"
    recs = read_jsonl(ROOT / "native_backtest/out/decisions/AP1.jsonl")
    mk = load_market(load_config())
    sim = simulate_records(recs, mk, [pd.Period(r.decision_month, "M") for r in recs], cost_per_dollar=0.0005)
    s2 = pd.read_csv(run / "stage2_portfolio_returns.csv")
    s2 = s2[s2.strategy == "A"].reset_index(drop=True)
    assert (sim["net_excess_return"] - s2["net_excess_return"]).abs().max() < 1e-12
