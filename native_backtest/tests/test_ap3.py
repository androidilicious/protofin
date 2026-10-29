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


def test_paid_providers_refuse_while_the_budget_is_zero(monkeypatch):
    from native_backtest.ap3 import llm_client as Lc
    assert Lc.paid_budget_usd() == 0.0                         # project budget set to $0 on 2026-10-29
    monkeypatch.setenv("AP3_ALLOW_PAID_INFERENCE", "1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "x"); monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "y")
    for prov in (DeepInfraProvider(), BedrockProvider()):
        with pytest.raises(PaidInferenceNotApproved, match=r"\$0"):
            prov.complete(Request(step="x", system="s", user="u", schema={}, temperature=0.0, seed=0))


def test_paid_providers_refuse_without_credentials(monkeypatch):
    from native_backtest.ap3 import llm_client as Lc
    monkeypatch.setattr(Lc, "paid_budget_usd", lambda: 1.0)   # only to reach the credential check
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


# ------------------------------------------------------------------ mediator inventory v2: captures, ALFRED vintages, labels
def test_t5yie_capture_verifies_and_matches_alfred_latest():
    from native_backtest.ap3 import mediator_data as md
    s = md.read_capture("T5YIE")           # stops if any part differs from its browser-side SHA-256
    assert len(s) == 3709 and str(s.index[0].date()) == "2011-12-01" and str(s.index[-1].date()) == "2026-09-30"
    ev = md.alfred_evidence()["series"]["T5YIE"]
    assert ev["latest_window_table_sha256"] == "306e6641502a5a1e542c326c8e060a6b71d5e2c849907830fc2ea035a92ade8d"


def test_alfred_vintages_make_availability_and_revisions_point_in_time():
    from native_backtest.ap3 import mediator_data as md
    from native_backtest.ap3.mediators import MediatorStore
    # synthetic frame on real BAA10Y evidence: the 2016-10..2017-03 posting gap and the June 2020 revisions
    days = pd.DatetimeIndex(["2016-10-06", "2016-10-07", "2020-05-26", "2020-05-29", "2020-06-01", "2020-06-02", "2020-06-03",
                             "2020-06-04", "2020-06-05"])
    f = pd.DataFrame({"date": days, "value": [3.0, 3.1, 3.14, 3.08, 3.10, 3.08, 3.02, 2.99, 2.86], "available_at": md.available_at(days, "h15")})
    g = md.apply_alfred(f, "BAA10Y")
    st = MediatorStore({"X": g})
    t = pd.Timestamp("2016-12-30 20:00", tz="America/New_York")
    assert st.asof("X", t)["date"].max() == pd.Timestamp("2016-10-06")      # first posted 2017-03-22
    v = st.asof("X", pd.Timestamp("2020-06-09 20:00", tz="America/New_York")).set_index("date")["value"]
    assert v[pd.Timestamp("2020-06-04")] == pytest.approx(3.01) and v[pd.Timestamp("2020-06-05")] == pytest.approx(2.91)
    v = st.asof("X", pd.Timestamp("2020-06-30 20:00", tz="America/New_York")).set_index("date")["value"]
    assert v[pd.Timestamp("2020-06-04")] == pytest.approx(2.99) and v[pd.Timestamp("2020-06-05")] == pytest.approx(2.86)


def test_inventory_v2_labels_ig_proxy_and_keeps_v1():
    from native_backtest.ap3 import mediator_data as md
    lab = md.labels("v2")
    assert lab["IG_SPREAD"].startswith("PROXY") and "not an option-adjusted" in lab["IG_SPREAD"].lower().replace("Not", "not")
    assert md.SERIES_V2["IG_SPREAD"]["status"] == "proxy_approved" and md.SERIES_V1["IG_SPREAD"]["status"] == "substitute_pending_approval"
    assert md.SERIES_V2["FF_FUTURES_6M"]["status"] == "not_available"
    try:
        store, status = md.load_store(include_pending_substitutes=True, inventory="v2")
    except Exception as e:
        pytest.skip(f"pinned mediators unavailable: {e}")
    if "VIX" not in store.series or "IG_SPREAD" not in store.series:
        pytest.skip("pinned v2 inputs not fetched")
    assert store.labels["IG_SPREAD"] == lab["IG_SPREAD"] and "BEI5Y" in store.series
    ev = md.stress_events(store, pd.Timestamp("2020-03-01"), pd.Timestamp("2020-03-31 20:00", tz="America/New_York"), 2.0)
    assert all(e["series_label"] == lab[e["series"]] for e in ev)


# ------------------------------------------------------------------ fed funds futures importer (synthetic test data only)
def _synthetic_ff_export(tmp, drop_day=None, wide=False):
    """SYNTHETIC test data, never a result: a flat 2% effective rate and contracts priced at 98.00."""
    days = [d for d in pd.bdate_range("2019-12-02", "2020-03-31")]
    rows, static = [], []
    for m in pd.period_range("2019-12", "2020-10", freq="M"):
        t = f"FF{'FGHJKMNQUVXZ'[m.month - 1]}{str(m.year)[2:]} Comdty"
        static += [(t, "FUT_DLV_DT_FIRST", m.start_time.date().isoformat()), (t, "FUT_DLV_DT_LAST", m.end_time.date().isoformat()),
                   (t, "LAST_TRADEABLE_DT", (m.end_time - pd.offsets.BDay(0)).date().isoformat())]
        for d in days:
            if d.strftime("%Y-%m-%d") != drop_day and d <= m.end_time:
                rows.append((d.date().isoformat(), t, "PX_SETTLE", 98.0))
    for d in days:
        rows.append((d.date().isoformat(), "FEDL01 Index", "PX_LAST", 2.0))
    h = pd.DataFrame(rows, columns=["date", "ticker", "field", "value"])
    if wide:
        h = h.assign(key=h.ticker + "|" + h.field).pivot(index="date", columns="key", values="value").reset_index().rename(columns={"date": "Date"})
    h.to_csv(tmp / "ff_futures_history.csv", index=False)
    pd.DataFrame(static, columns=["ticker", "field", "value"]).to_csv(tmp / "ff_futures_static.csv", index=False)


def test_ff_futures_importer_builds_six_month_series_and_checks(tmp_path):
    from native_backtest.scripts import import_ff_futures as ff
    _synthetic_ff_export(tmp_path)
    hist, static = ff.read_history(tmp_path / "ff_futures_history.csv"), ff.read_static(tmp_path / "ff_futures_static.csv")
    s, checks = ff.build(hist, static, "2019-12-02", "2020-03-31")
    assert s["contract_month"].iloc[0] == "2020-06" and s["contract_month"].iloc[-1] == "2020-09"   # month + 6
    assert np.allclose(s["implied_rate"], 2.0) and np.allclose(s["change_same_contract"].dropna(), 0.0)
    assert checks["contract_identification"]["pass"] and checks["coverage"]["pass"] and checks["duplicate_rows"]["pass"]
    assert checks["final_settlement_vs_effr"]["pass"] is True                       # Dec 2019 .. Mar 2020 contracts expired
    wide = tmp_path / "w"; wide.mkdir()
    _synthetic_ff_export(wide, wide=True)
    s2, _ = ff.build(ff.read_history(wide / "ff_futures_history.csv"), ff.read_static(wide / "ff_futures_static.csv"), "2019-12-02", "2020-03-31")
    assert s2.equals(s)


def test_ff_futures_importer_flags_gaps_and_unidentified_contracts(tmp_path):
    from native_backtest.scripts import import_ff_futures as ff
    _synthetic_ff_export(tmp_path, drop_day="2020-02-03")
    hist, static = ff.read_history(tmp_path / "ff_futures_history.csv"), ff.read_static(tmp_path / "ff_futures_static.csv")
    _, checks = ff.build(hist, static, "2019-12-02", "2020-03-31")
    assert checks["coverage"]["missing"] == 1 and "2020-02-03" in checks["coverage"]["first_missing"]
    static.pop("FFM20 Comdty")
    _, checks = ff.build(hist, static, "2019-12-02", "2020-03-31")
    assert checks["contract_identification"]["pass"] is False


# ------------------------------------------------------------------ paid-inference guards (no network, no credentials used)
def test_cost_guard_stops_before_the_cap(tmp_path):
    from native_backtest.ap3 import llm_client as L
    g = L.CostGuard(0.01, tmp_path / "ledger.jsonl", {"mode": "tokens", "usd_per_m_input": 1.0, "usd_per_m_output": 1.0})
    small = L.Request(step="s", system="x" * 300, user="y" * 300, schema={}, temperature=0.0, seed=0, max_tokens=100)
    g.check(small)                                                    # ~300 tokens: fine
    g.record("s", {"prompt_tokens": 9000, "completion_tokens": 900})  # $0.0099 spent
    with pytest.raises(L.BudgetExceeded):
        g.check(small)
    g2 = L.CostGuard(5.0, tmp_path / "l2.jsonl", {"mode": "hourly", "usd_per_hour": 5.0, "started_utc": "2000-01-01T00:00:00Z"})
    with pytest.raises(L.BudgetExceeded):                             # an endpoint running for years is far past $5
        g2.check(small)


def test_paid_provider_needs_a_guard_and_approval(tmp_path, monkeypatch):
    from native_backtest.ap3 import llm_client as L
    with pytest.raises(L.PaidInferenceNotApproved):
        L.LLMClient(L.BedrockProvider(), tmp_path / "c", tmp_path / "log.jsonl", "t")      # no CostGuard
    monkeypatch.delenv("AP3_ALLOW_PAID_INFERENCE", raising=False)
    guard = L.CostGuard(5.0, tmp_path / "l.jsonl", {"mode": "tokens", "usd_per_m_input": 1.0, "usd_per_m_output": 1.0})
    c = L.LLMClient(L.BedrockProvider(), tmp_path / "c", tmp_path / "log.jsonl", "t", guard=guard)
    with pytest.raises(L.PaidInferenceNotApproved):
        c.complete_json(L.Request(step="s", system="a", user="b", schema={}, temperature=0.0, seed=0))


def test_smoke_runner_refuses_without_approval(monkeypatch):
    from native_backtest.scripts import ap3_smoke_test as sm
    monkeypatch.delenv("AP3_ALLOW_PAID_INFERENCE", raising=False)
    cfg = sm.load_config()
    assert cfg["cap_usd"] == 15.0 and cfg["months"] == ["2015-03", "2019-06", "2020-03"]
    # the 2026-10-29 approval covers the dedicated endpoint only: Bedrock (existing AWS credentials) stays refused
    missing = sm.prerequisites(cfg, "bedrock")
    assert any("not A / bedrock" in m for m in missing) and "AP3_ALLOW_PAID_INFERENCE=1" in missing
    with pytest.raises(sm.NotApproved):
        sm.main(["--provider", "bedrock", "--execute"])


# ---------------------------------------------------------------- browser-captured corpus import
def _corpus_zip(path, docs, tamper=False):
    import hashlib as _h
    import json as _j
    import zipfile as _z
    man = {"archive": path.stem, "created_utc": "2026-10-29T02:00:00Z", "page_origin": "https://www.bls.gov", "documents": []}
    with _z.ZipFile(path, "w", compression=_z.ZIP_DEFLATED) as z:
        for name, body, meta in docs:
            rec = {**meta, "status": 200, "bytes": len(body), "sha256": _h.sha256(body).hexdigest(), "retrieved_utc": "2026-10-29T02:00:01Z", "file": name}
            man["documents"].append(rec)
            z.writestr(name, body + (b"x" if tamper else b""))
        man["documents"].append({"family": "bls_cpi", "url": "https://www.bls.gov/x_missing.htm", "status": 404})
        z.writestr("manifest.json", _j.dumps(man))


def test_corpus_import_verifies_page_side_hashes(tmp_path, monkeypatch):
    import pytest
    from native_backtest.scripts import ap3_corpus_import as imp
    monkeypatch.setattr(imp, "RAW", tmp_path / "raw")
    monkeypatch.setattr(imp, "IMPORT_MANIFEST", tmp_path / "import_manifest.json")
    monkeypatch.setattr(imp, "ROOT", tmp_path)
    zips = tmp_path / "zips"
    zips.mkdir()
    meta = {"family": "bls_cpi", "url": "https://www.bls.gov/news.release/archives/cpi_01162015.htm", "url_date": "2015-01-16", "release_date": "2015-01-16"}
    _corpus_zip(zips / "ap3_corpus_bls_cpi_v1.zip", [("bls_cpi/20150116.html", b"<pre>embargoed until 8:30 a.m. (EST) Friday, January 16, 2015</pre>", meta)])
    out = imp.import_archives(zips)
    a = out["archives"]["bls_cpi"]
    assert a["imported"] == 1 and a["failed_fetches"][0]["status"] == 404 and out["archives"]["bls_ppi"] == {"missing": True}
    log = [json.loads(l) for l in (tmp_path / "raw" / "fetch_log.jsonl").read_text().splitlines()]
    assert log[0]["via"] == "browser_capture" and log[0]["file"] == "raw/bls_cpi/20150116.html" and log[0]["url_date"] == "2015-01-16"
    _corpus_zip(zips / "ap3_corpus_bls_cpi_v1.zip", [("bls_cpi/20150116.html", b"<pre>abc</pre>", meta)], tamper=True)
    with pytest.raises(SystemExit, match="page-side SHA-256"):
        imp.import_archives(zips)


def test_smoke_runner_safeguards(tmp_path, monkeypatch):
    from native_backtest.scripts import ap3_smoke_test as st
    from native_backtest.scripts import ap3_hf_endpoint as ep
    cfg = st.load_config()
    assert st.cap(cfg, "hf_endpoint") == 15.0 and st.cap(cfg, "bedrock") == 5.0
    spec = ep.spec()
    assert spec["revision"] == "1605565b47bb9346c5515c34102e054115b4f98b" and "@sha256:" in spec["image"]
    assert spec["min_replica"] == 0 and spec["scale_to_zero_timeout_minutes"] == 15 and spec["env"]["VLLM_BATCH_INVARIANT"] == "1"
    monkeypatch.delenv("HF_TOKEN", raising=False)
    assert ep.approved() is False and ep.main([]) == 0          # plan only, nothing contacted
    with pytest.raises(SystemExit):                              # creation exists only inside the managed smoke run
        ep.main(["--create"])
    with pytest.raises(SystemExit, match="HF_TOKEN"):
        ep.main(["--delete"])
    # hourly guard: elapsed time beyond the cap stops the next call
    from native_backtest.ap3 import llm_client as L
    g = L.CostGuard(15.0, tmp_path / "l.jsonl", {"mode": "hourly", "usd_per_hour": 10.0, "started_utc": "2026-10-28T00:00:00Z"})
    with pytest.raises(L.BudgetExceeded):
        g.check(L.Request(step="x", system="s", user="u", schema={}, temperature=0.0, seed=0))


def test_corpus_fetch_is_resumable(tmp_path, monkeypatch):
    import hashlib as _h
    from native_backtest.scripts import ap3_corpus_fetch as fe
    monkeypatch.setattr(fe, "ROOT", tmp_path)
    monkeypatch.setattr(fe, "RAW", tmp_path / "raw")
    (tmp_path / "raw" / "bls_cpi").mkdir(parents=True)
    good, bad = tmp_path / "raw/bls_cpi/a.html", tmp_path / "raw/bls_cpi/b.html"
    good.write_bytes(b"ok"); bad.write_bytes(b"changed")
    rows = [{"url": "u1", "status": 200, "file": "raw/bls_cpi/a.html", "sha256": _h.sha256(b"ok").hexdigest()},
            {"url": "u2", "status": 200, "file": "raw/bls_cpi/b.html", "sha256": _h.sha256(b"original").hexdigest()},
            {"url": "u3", "status": 404}]
    (tmp_path / "raw" / "fetch_log.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert fe.already_fetched() == {"u1"}


def test_corpus_fetch_manifest_lists_fetched_and_missing(tmp_path, monkeypatch):
    import hashlib as _h
    import pytest
    from native_backtest.scripts import ap3_corpus_import as imp
    monkeypatch.setattr(imp, "ROOT", tmp_path)
    monkeypatch.setattr(imp, "RAW", tmp_path / "raw")
    monkeypatch.setattr(imp, "FETCH_MANIFEST", tmp_path / "fetch_manifest.json")
    (tmp_path / "raw" / "fomc_minutes").mkdir(parents=True)
    (tmp_path / "raw/fomc_minutes/20150128.html").write_bytes(b"minutes")
    rows = [{"family": "bls_cpi", "kind": "index", "url": "https://www.bls.gov/bls/news-release/cpi.htm", "status": 403, "sha256": "x", "bytes": 1, "retrieved_utc": "t"},
            {"family": "fomc_minutes", "url": "m1", "status": 404, "sha256": "x", "bytes": 0, "retrieved_utc": "t0"},
            {"family": "fomc_minutes", "url": "m1", "status": 200, "file": "raw/fomc_minutes/20150128.html", "bytes": 7,
             "sha256": _h.sha256(b"minutes").hexdigest(), "retrieved_utc": "t1", "url_date": "2015-01-28", "release_date": "2015-02-18"},
            {"family": "fomc_minutes", "url": "m2", "status": 500, "sha256": "x", "bytes": 0, "retrieved_utc": "t2"}]
    (tmp_path / "raw" / "fetch_log.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    out = imp.from_fetch_log()
    f = out["families"]
    assert f["fomc_minutes"]["fetched"] == 1 and [d["url"] for d in f["fomc_minutes"]["failed_documents"]] == ["m2"]
    assert f["bls_cpi"]["fetched"] == 0 and f["bls_cpi"]["index_unreachable"] == ["https://www.bls.gov/bls/news-release/cpi.htm"]
    assert out["documents"][0]["release_date"] == "2015-02-18" and out["documents"][0]["via"] == "direct_fetch"
    (tmp_path / "raw/fomc_minutes/20150128.html").write_bytes(b"altered")
    with pytest.raises(SystemExit, match="logged SHA-256"):
        imp.from_fetch_log()


# ------------------------------------------------------------------ Causal RAG versions: evidence pools, failures, reliability

def _pool(variant="reduced_evidence", corpus_chunks=None):
    from native_backtest.ap3 import evidence_pool as ep, runner
    from native_backtest.ap3.graph_vintage import load_concepts
    concepts = load_concepts()
    return ep.EvidencePool(variant, _fixture_mediators(), {"UST2Y": "2-year yield"}, {k: v["label"] for k, v in concepts["triggers"].items()},
                           runner.load_limits(), corpus_chunks)


def _packet(month="2019-06", dt="2019-06-28T20:00:00-04:00", triggers=None):
    return {"decision_month": month, "decision_time": dt, "triggers": triggers or [{"trigger": "CPI", "description": "CPI release", "surprise_z": 1.4}],
            "all_surprises_z": {"CPI": 1.4, "NFP": -0.2, "PPI": None}}


REC = {"edge": "inflation -> interest rates", "paper_id": "w123", "title": "A paper", "year": 2016, "evidence_class": "theoretical", "causal_inference_method": None}


def test_reduced_evidence_pool_is_point_in_time_and_excludes_judged_mediators():
    from native_backtest.ap3 import evidence_pool as ep
    pool = _pool()
    hyp = {"predicted_mediators": [], "research_records": [REC]}
    c = pool.for_hypothesis(_packet(), hyp, [REC], pd.Timestamp("2019-06-01"))
    kinds = ep.pool_summary(c)["by_kind"]
    assert kinds["research_claim"] == 1                      # the record behind hypothesis and rival appears once
    assert kinds["data_note"] >= 3                           # month-to-date, release window, surprises
    assert all(pd.Timestamp(x["available_at_et"]) < pd.Timestamp("2019-06-28T20:00:00-04:00") for x in c)
    assert not any(x.get("series") in ("SPY", "IEF", "LQD") for x in c)          # never asset returns
    assert any(x.get("window") == "release_to_decision" for x in c)              # CPI release 2019-06-12 from ALFRED
    # a series the hypothesis predicts is judged by the mediator test, so its notes leave that hypothesis's pool
    c2 = pool.for_hypothesis(_packet(), {"predicted_mediators": [{"series": "UST2Y", "sign": 1}], "research_records": []}, [], pd.Timestamp("2019-06-01"))
    assert not any(x.get("series") == "UST2Y" for x in c2)
    # PPI has no value this month: no note is invented
    assert not any(x.get("series") == "PPI" for x in c)


def test_evidence_pool_refuses_late_chunks_canaries_and_missing_corpus():
    import pytest
    from native_backtest.ap3 import corpus, evidence_pool as ep
    with pytest.raises(ep.EvidenceError, match="unknown"):
        _pool("full")
    with pytest.raises(ep.EvidenceError, match="corpus"):
        _pool("historical_documents", None)
    late = {"doc_id": "d", "chunk_id": "d#c000", "text": "x", "available_at_et": "2019-06-28T20:00:00-04:00"}
    with pytest.raises(ep.EvidenceError, match="point-in-time"):
        ep.check_point_in_time([late], "2019-06-28T20:00:00-04:00")
    can = corpus.canaries("2026-09-30", 1)
    with pytest.raises(ep.EvidenceError, match="point-in-time"):
        ep.check_point_in_time([{**can[0], "available_at_et": "2019-01-01T00:00:00-05:00"}], "2019-06-28T20:00:00-04:00")
    # historical-documents pool = reduced-evidence pool + documents eligible at the decision time (canaries never)
    docs = FIXTURE_CHUNKS + corpus.canaries("2026-09-30", 2)
    hd = _pool("historical_documents", docs).for_hypothesis(_packet(), {"predicted_mediators": [], "research_records": [REC]}, [], pd.Timestamp("2019-06-01"))
    re_ = _pool().for_hypothesis(_packet(), {"predicted_mediators": [], "research_records": [REC]}, [], pd.Timestamp("2019-06-01"))
    assert {x["chunk_id"] for x in re_} < {x["chunk_id"] for x in hd}
    assert {x["chunk_id"] for x in hd} - {x["chunk_id"] for x in re_} == {x["chunk_id"] for x in FIXTURE_CHUNKS}


def test_release_dates_come_from_the_official_record():
    from native_backtest.ap3 import evidence_pool as ep
    d = ep.release_dates()
    r = ep.trigger_release({"trigger": "CPI"}, "2019-06-28T20:00:00-04:00", d)
    assert r[0] == pd.Timestamp("2019-06-12 08:30", tz="America/New_York")
    assert ep.trigger_release({"trigger": "FOMC", "date": "2019-06-19"}, "2019-06-28T20:00:00-04:00", d)[0].hour == 14
    assert ep.trigger_release({"trigger": "ISM_MANUFACTURING"}, "2019-06-28T20:00:00-04:00", d) is None   # no official-source record
    assert ep.trigger_release({"trigger": "CPI"}, "2019-06-12T08:00:00-04:00", d) is None   # released after the decision time


class _BadProvider:
    name, model, is_mock = "engineering_mock", "bad", True

    def __init__(self, bad_step):
        self.bad = bad_step

    def complete(self, req):
        from native_backtest.ap3 import engineering_mock
        if req.step.startswith(self.bad):
            return "I cannot answer in JSON.", {}
        return json.dumps(engineering_mock.responder(req)), {}


@needs_claims
def test_invalid_model_output_is_logged_and_never_fabricated(tmp_path):
    from native_backtest.ap3 import runner
    from native_backtest.ap3.graph_vintage import build_vintage, load_concepts
    concepts, limits = load_concepts(), runner.load_limits()
    vintage = build_vintage(2018, concepts)
    lib = json.loads((EXTERNAL / "ap3_libraries" / "library_v1.0_vintage2018.json").read_text())
    packet = runner.build_packet("2019-06", "2019-06-28T20:00:00-04:00", {"CPI": 1.4}, [], [], concepts, limits)
    # a failed Testing Agent: status Insufficient, flagged as a failure
    client = LLMClient(_BadProvider("assessor_"), tmp_path / "c1", tmp_path / "l1.jsonl", "t")
    rec = runner.run_month(client, packet, vintage, lib, [], _fixture_mediators(), pd.Timestamp("2019-06-01"), limits, evidence=_pool())
    t = rec["tests"][0]
    assert t["status"] == "Insufficient" and t["failure"].startswith("testing agent") and rec["variant"] == "reduced_evidence"
    assert any(json.loads(l).get("invalid") for l in (tmp_path / "l1.jsonl").read_text().splitlines())
    # a failed Hypothesis Agent: no hypotheses, status features zero, recorded
    client = LLMClient(_BadProvider("hypothesis_turn_"), tmp_path / "c2", tmp_path / "l2.jsonl", "t")
    rec = runner.run_month(client, packet, vintage, lib, [], _fixture_mediators(), pd.Timestamp("2019-06-01"), limits, evidence=_pool())
    assert rec["hypothesis_agent"]["failure"] and rec["tests"] == []
    assert all(v == 0.0 for a in rec["status_features"].values() for v in a.values())
    from native_backtest.ap3 import reliability
    rep = reliability.report([rec])
    assert rep["failed_months"] and reliability.gate_g4a(rep)["pass"] is False


@needs_claims
def test_reduced_evidence_month_end_to_end_with_mock(tmp_path):
    from native_backtest.ap3 import engineering_mock, reliability, runner
    from native_backtest.ap3.graph_vintage import build_vintage, load_concepts
    concepts, limits = load_concepts(), runner.load_limits()
    vintage = build_vintage(2018, concepts)
    lib = json.loads((EXTERNAL / "ap3_libraries" / "library_v1.0_vintage2018.json").read_text())
    packet = runner.build_packet("2019-06", "2019-06-28T20:00:00-04:00", {"CPI": 1.4}, [], [], concepts, limits)
    client = LLMClient(EngineeringMockProvider(engineering_mock.responder), tmp_path / "cache", tmp_path / "calls.jsonl", "engineering-test")
    rec = runner.run_month(client, packet, vintage, lib, [], _fixture_mediators(), pd.Timestamp("2019-06-01"), limits, evidence=_pool())
    t = rec["tests"][0]
    assert rec["variant_label"] == "Causal RAG — Reduced Evidence" and t["evidence_pool"]["by_kind"]["data_note"] > 0
    assert t["runs"][0]["assess_meta"] is not None                # the assessor really ran on the pool
    rep = reliability.report([rec])
    assert rep["point_in_time_violations"] == [] and rep["directional_labels_downgraded_by_quote_validation"] >= 1


def test_g3b_fixtures_are_well_formed():
    from native_backtest.scripts import ap3_g3b_fixtures as g
    fx = json.loads(g.FIXTURES.read_text())["fixtures"]
    assert len(fx) == 30 and len({f["id"] for f in fx}) == 30
    assert {f["expected_status"] for f in fx} == {"Supported", "Contradicted", "Insufficient"}
    ids = [e["chunk_id"] for f in fx for e in f["excerpts"]]
    assert len(ids) == len(set(ids))
    for f in fx:
        assert all(pd.Timestamp(e["available_at_et"]) < pd.Timestamp(f["decision_time"]) for e in f["excerpts"])
    rows = [{"category": f["category"], "expected": f["expected_status"], "got": f["expected_status"], "correct": True} for f in fx]
    assert g.score(rows)["pass"] is True
    rows[0] = {**rows[0], "got": "Contradicted", "correct": False}
    rows[1] = {**rows[1], "got": "Contradicted", "correct": False}
    assert g.score(rows)["checks"]["opposite_direction_errors"]["pass"] is False


def test_replay_and_g3b_refuse_paid_runs_without_approval(monkeypatch, capsys):
    import pytest
    from native_backtest.scripts import ap3_dev_replay as rp, ap3_g3b_fixtures as g
    monkeypatch.delenv("AP3_ALLOW_PAID_INFERENCE", raising=False)
    missing = rp.prerequisites_b("hf_endpoint", "reduced_evidence")
    assert any("approval record" in m for m in missing) and any("AP3_ALLOW_PAID_INFERENCE" in m for m in missing)
    assert rp.main(["--variant", "reduced_evidence", "--provider", "hf_endpoint"]) == 0          # plan only
    assert '"will_call_a_paid_model": false' in capsys.readouterr().out
    with pytest.raises(rp.NotApproved):
        rp.main(["--variant", "reduced_evidence", "--provider", "bedrock", "--execute"])
    with pytest.raises(rp.NotApproved):
        g.main(["--provider", "hf_endpoint", "--execute"])
    with pytest.raises(SystemExit, match="engineering"):
        rp.main(["--variant", "historical_documents", "--provider", "hf_endpoint", "--allow-incomplete-corpus"])
    # the protected window is refused before anything runs
    with pytest.raises(Exception):
        rp.main(["--variant", "reduced_evidence", "--provider", "engineering_mock", "--months", "2022-12,2023-02"])


def test_variants_differ_only_in_evidence():
    from native_backtest.ap3 import evidence_pool as ep
    v = ep.load_variants()
    re_, hd = v["variants"]["reduced_evidence"], v["variants"]["historical_documents"]
    assert set(hd["evidence"]) - set(re_["evidence"]) == {"official_documents"} and set(re_["evidence"]) < set(hd["evidence"])
    assert v["primary_version"]["selected"] is None and "never used" in v["primary_version"]["rule"]


# ------------------------------------------------------------------ dedicated-endpoint spending controller (fake API, fake clock)

class _FakeHF:
    def __init__(self, statuses, echo_args=True):
        self.statuses, self.echo_args, self.calls, self.exists = list(statuses), echo_args, [], False

    def create(self, e):
        self.calls.append("create"); self.exists = True
        model = {"repository": e["repository"], "revision": e["revision"], "image": {"custom": {"url": e["image"], **({"args": e["container_args"]} if self.echo_args else {})}}}
        return {"status": "pending", "url": None, "raw": {"model": model, "compute": {"instanceType": e["instance_type"], "instanceSize": e["instance_size"]}}}

    def get(self, name):
        if not self.exists:
            return None
        st = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        return {"status": st, "url": "https://x.us-east-1.aws.endpoints.huggingface.cloud" if st == "running" else None, "raw": {}}

    def delete(self, name):
        self.calls.append("delete"); self.exists = False


class _Clock:
    def __init__(self):
        self.t = 1_800_000_000.0

    def __call__(self):
        return self.t


def _ctl(tmp_path, statuses, **kw):
    from native_backtest.scripts import ap3_hf_endpoint as ep
    monkey_state = tmp_path / "endpoint.json"
    ep.STATE = monkey_state
    clock = _Clock()
    api = _FakeHF(statuses, **kw)
    return ep, ep.EndpointController(api, "t", log=tmp_path / "log.jsonl", clock=clock), api, clock


def test_safeguards_bound_every_failure_mode_within_the_authorization():
    from native_backtest.scripts import ap3_hf_endpoint as ep
    w = ep.worst_cases()
    s = ep.safeguards()
    assert s["authorized_usd"] == 15.0 and all(v["max_usd"] <= 15.0 for v in w.values() if v["max_usd"] is not None)
    ep.spec_check()
    with pytest.raises(SystemExit, match="above"):
        ep.spec_check({**s, "stop_new_calls_minute": 80, "delete_minute": 85})
    a = json.loads((ROOT / "native_backtest/config/approvals/ap3_inference_approval_A.json").read_text())
    assert a["provider"] == "hf_endpoint" and a["cap_usd"] == 15.0 and a["stage"] == "A" and a["status"] == "withdrawn"


def test_controller_deletes_when_the_pinned_configuration_is_not_echoed(tmp_path):
    ep, c, api, clock = _ctl(tmp_path, ["pending"], echo_args=False)
    with pytest.raises(SystemExit, match="container arguments"):
        c.create()
    assert api.calls == ["create", "delete"] and c.deleted["confirmed"]


def test_controller_init_deadline_failure_and_spending_deadline(tmp_path):
    ep, c, api, clock = _ctl(tmp_path, ["initializing"])
    c.create()
    clock.t += 39 * 60; c.poll_once(); assert not c.deleted
    clock.t += 2 * 60; c.poll_once()
    assert c.deleted and "not running after 40" in c.deleted["reason"] and c.cost_usd() <= 6.84
    ep, c, api, clock = _ctl(tmp_path, ["failed"])
    c.create(); c.poll_once()
    assert "failed" in c.deleted["reason"]
    ep, c, api, clock = _ctl(tmp_path, ["running"])
    c.create(); c.poll_once()
    assert c.stop_reason() is None
    clock.t += 65 * 60
    assert "time limit" in c.stop_reason()                       # no new calls from minute 65
    clock.t += 3 * 60; c.poll_once()
    assert "spending deadline" in c.deleted["reason"] and c.runtime_record()["cost_usd_upper"] <= 11.5


def test_guard_gate_never_wakes_a_non_running_endpoint(tmp_path):
    from native_backtest.ap3 import llm_client as Lc
    ep, c, api, clock = _ctl(tmp_path, ["running", "scaledToZero"])
    c.create(); c.poll_once()
    g = Lc.CostGuard(10.0, tmp_path / "ledger.jsonl", {"mode": "hourly", "usd_per_hour": 10.0, "started_utc": "2027-01-15T08:00:00Z"}, gate=c.stop_reason)
    req = Request(step="x", system="s", user="u", schema={}, temperature=0.0, seed=0)
    c.poll_once()
    with pytest.raises(Lc.BudgetExceeded, match="not running"):
        g.check(req)
    assert c.wait_running if True else None


def test_wait_running_returns_url_and_runtime_is_recorded(tmp_path):
    ep, c, api, clock = _ctl(tmp_path, ["initializing", "initializing", "running"])
    c.create()
    url = c.wait_running(sleep=lambda s: setattr(clock, "t", clock.t + s))
    assert url.startswith("https://") and c.status == "running"
    c.delete("done")
    r = c.runtime_record()
    assert r["deleted"]["confirmed"] and r["billable_minutes_upper"] >= 1 and api.calls[-1] == "delete"
    log = [json.loads(l)["event"] for l in (tmp_path / "log.jsonl").read_text().splitlines()]
    assert log[0] == "create_requested" and "ready" in log and log[-1] == "deleted"


def test_smoke_plan_lists_missing_access_without_contacting_anyone(monkeypatch, capsys):
    from native_backtest.scripts import ap3_smoke_test as st
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("AP3_ALLOW_PAID_INFERENCE", raising=False)
    assert st.main(["--provider", "hf_endpoint"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["will_call_a_paid_model"] is False and "worst_cases" in plan["estimate"]
    miss = plan["prerequisites_missing"]
    assert any("HF_TOKEN" in m for m in miss) and any("withdrawn" in m for m in miss) and any("$0" in m for m in miss)
    with pytest.raises(st.NotApproved):
        st.main(["--provider", "hf_endpoint", "--execute"])


@needs_claims
def test_smoke_report_refuses_mock_records_and_redacts_claims_text(tmp_path, monkeypatch):
    """Formatting check on a TEST-ONLY copy of a mock month; real smoke folders never receive mock records."""
    from native_backtest.ap3 import engineering_mock, runner
    from native_backtest.ap3.graph_vintage import build_vintage, load_concepts
    from native_backtest.scripts import ap3_smoke_report as rp
    concepts, limits = load_concepts(), runner.load_limits()
    lib = json.loads((EXTERNAL / "ap3_libraries" / "library_v1.0_vintage2018.json").read_text())
    packet = runner.build_packet("2019-06", "2019-06-28T20:00:00-04:00", {"CPI": 1.4}, [], [], concepts, limits)
    client = LLMClient(EngineeringMockProvider(engineering_mock.responder), tmp_path / "c", tmp_path / "x" / "calls.jsonl", "t")
    rec = runner.run_month(client, packet, build_vintage(2018, concepts), lib, [], _fixture_mediators(), pd.Timestamp("2019-06-01"), limits,
                           evidence=_pool(), max_parallel_tests=3)
    d = tmp_path / "x"
    d.mkdir(exist_ok=True)
    monkeypatch.setattr(rp, "SMOKE", tmp_path)
    monkeypatch.setattr(rp, "DOC", tmp_path / "report.md")
    (d / "smoke_records.jsonl").write_text(json.dumps(rec, default=str) + "\n")
    with pytest.raises(SystemExit, match="engineering-mock"):
        rp.build("x")
    (d / "smoke_records.jsonl").write_text(json.dumps({**rec, "engineering_mock": False}, default=str) + "\n")
    (d / "canary.json").write_text(json.dumps([{"id": "c1", "ok": True}]))
    (d / "runtime.json").write_text(json.dumps({"billable_minutes_upper": 40, "cost_usd_upper": 6.67}))
    r = rp.build("x")
    h = r["months"][0]["hypotheses"][0]
    assert all("links" in v for v in h["cited_pathways"].values()) and all("title" not in x for x in h["research_records"])
    quotes = [q for run in h["testing_runs"] for it in run["assessments"] for q in it["supporting_quotes"] + it["contradicting_quotes"]]
    assert all(q["quote"].startswith("[research-claim") for q in quotes if q["chunk_id"].startswith("RC_"))
    assert r["checks"]["spend_within_authorization"]["pass"] and "Forecast and allocation" in (tmp_path / "report.md").read_text()
    full = json.loads((d / "smoke_report_full.json").read_text())
    assert full["months"][0]["hypotheses"][0]["research_records"] == [] or "title" in full["months"][0]["hypotheses"][0]["research_records"][0]


def test_policy_path_proxy_is_a_separate_labelled_variant_and_point_in_time():
    from native_backtest.ap3 import mediator_data as md, evidence_pool as ep
    _, frozen = md.load_store(include_pending_substitutes=True, inventory="v2")
    assert frozen["FF_FUTURES_6M"].startswith("unavailable")            # frozen specification unchanged: no silent proxy
    f = md.load_series("FF_FUTURES_6M", "v2_policy_proxy")
    two = md.load_series("UST2Y", "v2")
    j = f.merge(two, on="date", suffixes=("", "_2y"))
    assert (j["available_at"] >= j["available_at_2y"]).all()             # never earlier than its inputs
    assert md.labels("v2_policy_proxy")["FF_FUTURES_6M"].startswith("PROXY")
    v = ep.load_variants()["variants"]["reduced_evidence_policy_proxy"]
    assert v["mediator_inventory"] == "v2_policy_proxy" and "not part of the frozen specification" in v["role"].lower()
