"""AP3 tests. Everything here runs WITHOUT a model: agent steps use the labelled engineering mock,
documents and mediator series are ENGINEERING FIXTURES, and nothing produced here is a result."""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from native_backtest.ap3 import encoder, testing_agent
from native_backtest.ap3.llm_client import (BedrockProvider, DeepInfraProvider, EngineeringMockProvider, LLMClient,
                                            PaidInferenceNotApproved, Request)

ROOT = Path(__file__).resolve().parents[2]
EXTERNAL = ROOT / "native_backtest" / "data" / "_external"
HAS_CLAIMS = (EXTERNAL / "claims_part01.parquet").exists()
needs_claims = pytest.mark.skipif(not HAS_CLAIMS, reason="Garg & Fetzer claims not fetched (licence: local use only)")


# ------------------------------------------------------------------ guards against paid inference and mock leakage

@pytest.mark.parametrize("prov", [DeepInfraProvider(), BedrockProvider()])
def test_paid_providers_refuse_without_approval(prov, monkeypatch):
    monkeypatch.delenv("AP3_ALLOW_PAID_INFERENCE", raising=False)
    with pytest.raises(PaidInferenceNotApproved):
        prov.complete(Request(step="x", system="s", user="u", schema={}, temperature=0.0, seed=0))


def test_paid_providers_refuse_without_credentials(monkeypatch):
    monkeypatch.setenv("AP3_ALLOW_PAID_INFERENCE", "1")
    for v in ("DEEPINFRA_API_KEY", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(v, raising=False)
    for prov in (DeepInfraProvider(), BedrockProvider()):
        with pytest.raises(PaidInferenceNotApproved, match="missing credentials"):
            prov.complete(Request(step="x", system="s", user="u", schema={}, temperature=0.0, seed=0))


def test_evaluator_refuses_mock_records():
    from native_backtest.framework.accounting import AccountingError, simulate_records
    from native_backtest.framework.records import DecisionRecord
    rec = DecisionRecord(system_id="AP3", decision_month="2019-06", decision_time="2019-06-28T20:00:00-04:00",
                         info_cutoff="2019-06-28T16:00:00-04:00", universe=["SPY", "IEF", "LQD"],
                         target_weights={"SPY": 0.45, "IEF": 0.35, "LQD": 0.2}, generation={"mode": "engineering_mock"})
    with pytest.raises(AccountingError, match="engineering-mock"):
        simulate_records([rec], market=None, months=[pd.Period("2019-06", "M")], cost_per_dollar=0.0005)


# ------------------------------------------------------------------ encoder, majority, rubric

def test_status_features_keep_three_outcomes_distinct():
    hyps = [{"hypothesis_id": "h1", "predicted_assets": {"SPY": -1, "IEF": -1, "LQD": 0}},
            {"hypothesis_id": "h2", "predicted_assets": {"SPY": 1, "IEF": 0, "LQD": 1}},
            {"hypothesis_id": "h3", "predicted_assets": {"SPY": 1, "IEF": 1, "LQD": -1}}]
    tests = [{"hypothesis_id": "h1", "status": "Supported"}, {"hypothesis_id": "h2", "status": "Contradicted"},
             {"hypothesis_id": "h3", "status": "Insufficient"}]
    f = encoder.status_features(hyps, tests)
    assert f["SPY"] == {"F_S": -1.0, "F_C": 1.0, "F_I": 1.0}
    assert f["IEF"] == {"F_S": -1.0, "F_C": 0.0, "F_I": 1.0}
    assert f["LQD"] == {"F_S": 0.0, "F_C": 1.0, "F_I": -1.0}
    assert encoder.status_features([], []) == {a: {"F_S": 0.0, "F_C": 0.0, "F_I": 0.0} for a in ("SPY", "IEF", "LQD")}
    with pytest.raises(ValueError):
        encoder.status_features(hyps[:1], [{"hypothesis_id": "h1", "status": "Maybe"}])


@pytest.mark.parametrize("runs,expected", [
    (["Supported", "Supported", "Contradicted"], "Supported"),
    (["Supported", "Contradicted", "Insufficient"], "Insufficient"),
    (["Contradicted", "Contradicted", "Contradicted"], "Contradicted"),
    (["Supported", "Contradicted"], "Insufficient"),
])
def test_majority_tie_rule(runs, expected):
    assert testing_agent.majority(runs) == expected


def test_rubric_cases():
    sup = [{"validated_label": "supported", "n_valid_supporting": 2, "n_valid_contradicting": 0}]
    con = [{"validated_label": "contradicted", "n_valid_supporting": 0, "n_valid_contradicting": 1}]
    none = [{"validated_label": "insufficient_evidence", "n_valid_supporting": 0, "n_valid_contradicting": 0}]
    med_c = [{"result": "consistent"}]
    med_i = [{"result": "inconsistent"}]
    assert testing_agent.rubric(sup, [], [])["status"] == "Supported"
    assert testing_agent.rubric([{**sup[0], "n_valid_supporting": 1}], [], [])["status"] == "Insufficient"  # one item is not enough
    assert testing_agent.rubric([{**sup[0], "n_valid_supporting": 1}], [], med_c)["status"] == "Supported"   # item + mediator
    assert testing_agent.rubric(con, [], [])["status"] == "Contradicted"
    assert testing_agent.rubric(none, [], med_i)["status"] == "Contradicted"
    r = testing_agent.rubric(sup, [], med_i)
    assert r["status"] == "Insufficient" and r["conflict"] is True                                             # strong both ways
    rival = [{"validated_label": "supported", "n_valid_supporting": 3, "n_valid_contradicting": 0}]
    assert testing_agent.rubric(none, rival, [])["status"] == "Contradicted"                                    # rival dominates


# ------------------------------------------------------------------ calibration and allocation on synthetic data

def _synthetic_panel(seed=0, informative=False):
    from native_backtest.ap3.calibration import COLUMNS
    rng = np.random.default_rng(seed)
    months = pd.period_range("2015-02", "2022-12", freq="M")
    cols = list(COLUMNS)
    rows, labels = [], {}
    for m in months:
        f = {a: rng.normal(size=len(cols)) for a in ("SPY", "IEF", "LQD")}
        for a in f:
            rows.append({"month": m, "asset": a, **dict(zip(cols, f[a]))})
        labels[m] = {a: (0.01 * f[a][8] if informative else 0.0) + rng.normal(0, 0.03) for a in f}
    feats = pd.DataFrame(rows).set_index(["month", "asset"])
    return feats, pd.DataFrame(labels).T, cols


def test_calibration_runs_and_shrinks_noise():
    from native_backtest.ap3 import calibration as cal
    feats, labels, cols = _synthetic_panel(informative=False)
    score = list(pd.period_range("2019-03", "2019-08", freq="M"))
    pred = cal.walk_forward(feats, labels, score)
    assert set(pred["asset"]) == {"SPY", "IEF", "LQD"} and len(pred) == 18
    assert np.isfinite(pred["prediction_excess_return"]).all()
    assert 0.0 <= cal.intercept_only_share(pred) <= 1.0


# ------------------------------------------------------------------ end-to-end engineering run (mock + fixtures)

from native_backtest.ap3.engineering_fixtures import FIXTURE_CHUNKS, fixture_mediators as _fixture_mediators  # noqa: E402


@needs_claims
def test_engineering_month_end_to_end(tmp_path):
    from native_backtest.ap3 import engineering_mock, runner
    from native_backtest.ap3.graph_vintage import build_vintage, load_concepts

    concepts = load_concepts()
    vintage = build_vintage(2018, concepts)
    lib = json.loads((EXTERNAL / "ap3_libraries" / "library_v1.0_vintage2018.json").read_text())
    limits = runner.load_limits()
    packet = runner.build_packet("2019-06", "2019-06-28T20:00:00-04:00", {"CPI": 1.4, "NFP": -0.2}, [], [], concepts, limits)
    client = LLMClient(EngineeringMockProvider(engineering_mock.responder), tmp_path / "cache", tmp_path / "calls.jsonl", "engineering-test")
    rec = runner.run_month(client, packet, vintage, lib, FIXTURE_CHUNKS, _fixture_mediators(), pd.Timestamp("2019-06-01"), limits)
    assert rec["engineering_mock"] is True and rec["provider"] == "engineering_mock"
    assert rec["graph_vintage"] == 2018 and rec["library_sha256"] == lib["library_sha256"]
    assert len(rec["hypothesis_agent"]["hypotheses"]) >= 1
    t = rec["tests"][0]
    assert t["causal_validation"] == "not established" and t["assessor_provenance"]["identical_to_original"] is False
    assert len(t["runs"]) == limits["testing_agent"]["runs"]
    # the mock's fabricated citation must be rejected by the native assessor's validation
    labels = [a["validated_label"] for r in t["runs"] for a in r["assessments"]]
    assert "contradicted" not in labels
    assert set(rec["status_features"]) == {"SPY", "IEF", "LQD"}
    calls = [json.loads(l) for l in (tmp_path / "calls.jsonl").read_text().splitlines()]
    assert calls and all(c["mock"] for c in calls)


# ------------------------------------------------------------------ FOMC trigger calendar
def test_fomc_calendar_assignment():
    from native_backtest.ap3 import fomc_calendar as fc
    dates = fc.load_dates()  # checks the pinned SHA-256
    assert len(dates) == 158 and dates[0] == pd.Timestamp("2008-01-22")
    days = {pd.Period("2019-07", "M"): pd.Timestamp("2019-07-31"), pd.Period("2020-02", "M"): pd.Timestamp("2020-02-28"),
            pd.Period("2020-03", "M"): pd.Timestamp("2020-03-31")}
    ev = fc.events_by_decision_month(days, dates)
    # a scheduled 14:00 ET statement on the decision day precedes the 20:00 ET decision
    assert [e["date"] for e in ev[pd.Period("2019-07", "M")]] == ["2019-07-31"] and ev[pd.Period("2019-07", "M")][0]["on_decision_day"]
    # March 2020: two unscheduled communications and the 23 March statement
    assert [e["date"] for e in ev[pd.Period("2020-03", "M")]] == ["2020-03-03", "2020-03-15", "2020-03-23"]
    # nothing before the first month's window leaks in
    assert all(pd.Timestamp(e["date"]) > pd.Timestamp("2019-06-28") for v in ev.values() for e in v)


def test_fomc_event_after_last_trading_day_rolls_forward_and_unscheduled_on_decision_day_refused():
    from native_backtest.ap3 import fomc_calendar as fc
    days = {pd.Period("2021-01", "M"): pd.Timestamp("2021-01-29"), pd.Period("2021-02", "M"): pd.Timestamp("2021-02-26")}
    ev = fc.events_by_decision_month(days, [pd.Timestamp("2021-01-31")])   # Sunday after the January decision
    assert ev[pd.Period("2021-01", "M")] == [] and ev[pd.Period("2021-02", "M")][0]["date"] == "2021-01-31"
    with pytest.raises(fc.CalendarError):
        fc.events_by_decision_month(days, [pd.Timestamp("2021-01-29")], unscheduled=("2021-01-29",))


def test_fomc_calendar_on_the_real_decision_calendar():
    from native_backtest.ap3 import fomc_calendar as fc
    from native_backtest.framework.market import load_config, load_market
    try:
        mk = load_market(load_config())
    except Exception as e:  # pinned prices not fetched
        pytest.skip(f"market data unavailable: {e}")
    dd = {m: d for m, d in mk.decision_dates.items() if pd.Period("2015-02", "M") <= m <= pd.Period("2022-12", "M")}
    assert fc.check_unscheduled_not_on_decision_days(dd) == []
    ev = fc.events_by_decision_month(dd)
    n = sum(len(v) for v in ev.values())
    assert n == sum(1 for d in fc.load_dates() if pd.Timestamp("2015-01-30") < d <= max(dd.values()))


# ------------------------------------------------------------------ gate 5 extended to TLT (issuer records)
def test_tlt_issuer_captures_verify_and_agree():
    from native_backtest.scripts import check_tlt_distributions as c
    dist, pairs, monthly = c.build_records()   # stops if a capture's SHA-256 differs from the browser-side hash
    assert len(dist) == len(pairs) == 109 and len(monthly) == 110
    assert dist["ex_date"].min() >= "2014-01-01" and dist["ex_date"].max() <= "2023-02-01"   # no protected-window ex-dates
    assert monthly["month_end"].max() <= "2023-01-31"


# ------------------------------------------------------------------ evidence corpus pipeline (synthetic pages in the official formats)
_BLS_PAGE = (b"<html><body><div id='main-content'><pre>Transmission of material in this release is embargoed until USDL-19-2105 "
             b"8:30 a.m. (EST) Friday, December 6, 2019\n\n" + b"FIXTURE TEXT. Total nonfarm payroll employment rose in November. " * 60
             + b"</pre></div></body></html>")
_FED_PAGE = (b"<html><body><div id='article'><p>For release at 2:00 p.m. EDT</p>"
             + b"<p>FIXTURE TEXT. Information received since the Federal Open Market Committee met indicates that the labor market remains strong.</p>" * 20
             + b"</div></body></html>")


def test_corpus_documents_take_their_time_from_the_document():
    from native_backtest.ap3 import corpus
    d = corpus.make_document("bls_employment_situation", "https://www.bls.gov/news.release/archives/empsit_12062019.htm", _BLS_PAGE,
                             pd.Timestamp("2019-12-06"))
    assert d.available_at_et == "2019-12-06T08:30:00-05:00" and d.available_at_source == "printed in the document"
    s = corpus.make_document("fomc_statement", "https://www.federalreserve.gov/newsevents/pressreleases/monetary20190731a.htm", _FED_PAGE,
                             pd.Timestamp("2019-07-31"))
    assert s.available_at_et == "2019-07-31T14:00:00-04:00"
    # the printed date must agree with the URL date
    with pytest.raises(corpus.CorpusError):
        corpus.make_document("bls_employment_situation", "x", _BLS_PAGE, pd.Timestamp("2019-11-01"))
    ch = corpus.chunks_for(d)
    assert ch and all(c["chunk_id"].startswith(d.doc_id + "#c") and c["available_at_et"] == d.available_at_et for c in ch)


def test_corpus_canaries_are_never_eligible_and_the_audit_catches_leaks():
    from native_backtest.ap3 import corpus
    d = corpus.make_document("bls_employment_situation", "u", _BLS_PAGE, pd.Timestamp("2019-12-06"))
    chunks = corpus.chunks_for(d) + corpus.canaries("2026-09-30")
    times = ["2019-11-29T20:00:00-05:00", "2019-12-31T20:00:00-05:00", "2022-12-30T20:00:00-05:00"]
    assert corpus.eligible(chunks, times[0]) == []                       # published after the November decision
    assert {c["role"] for c in corpus.eligible(chunks, times[1])} == {"data_release"}
    assert corpus.audit(chunks, times)["pass"]
    leaked = chunks + [{**corpus.canaries("2018-01-01")[0], "available_at_et": "2019-01-01T00:00:00-05:00"}]
    assert not corpus.audit(leaked, times)["pass"]


def test_tlt_daily_nav_captures_verify():
    from native_backtest.scripts import diagnose_tlt_gate5 as dg
    nav = dg.load_nav()   # stops if any part differs from its browser-side SHA-256
    assert len(nav) == 2288 and str(nav.index[0].date()) == "2013-12-31" and str(nav.index[-1].date()) == "2023-02-01"


# ------------------------------------------------------------------ mediators: availability rules and stress triggers
def test_mediator_availability_rules_and_stress_aggregation():
    from native_backtest.ap3 import mediator_data as md
    t = md.available_at(pd.DatetimeIndex(["2019-07-03", "2019-07-05"]), "h15")   # H.15: next business day 18:00 ET (skips 4 July)
    assert [str(x) for x in t] == ["2019-07-05 18:00:00-04:00", "2019-07-08 18:00:00-04:00"]
    v = md.available_at(pd.DatetimeIndex(["2019-07-05"]), "close")
    assert str(v[0]) == "2019-07-05 17:00:00-04:00"
    try:
        store, status = md.load_store(include_pending_substitutes=False)
    except Exception as e:
        pytest.skip(f"pinned mediators unavailable: {e}")
    assert status["IG_SPREAD"].startswith("not loaded") and "BEI5Y" not in store.series
    if "VIX" not in store.series:
        pytest.skip("pinned VIX not fetched")
    ev = md.stress_events(store, pd.Timestamp("2020-03-01"), pd.Timestamp("2020-03-31 20:00", tz="America/New_York"), 2.0)
    assert len({e["series"] for e in ev}) == len(ev)          # one trigger per series
    assert all(e["days_at_or_above_threshold"] >= 1 and abs(e["z"]) >= 2.0 for e in ev)
