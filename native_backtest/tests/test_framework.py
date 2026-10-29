"""Tests for the shared evaluation framework (records, lock, market, accounting, metrics)."""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from native_backtest.framework import metrics as M
from native_backtest.framework.accounting import AccountingError, simulate_records
from native_backtest.framework.lock import OPENING_TOKEN, WindowLocked, assert_scoring_allowed
from native_backtest.framework.market import MarketDataError, decision_time_iso, load_config, load_market
from native_backtest.framework.records import DecisionRecord, RecordError, read_jsonl, validate, write_jsonl

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def market():
    return load_market(load_config())


def _rec(**kw):
    base = dict(system_id="T", decision_month="2019-03", decision_time="2019-03-29T20:00:00-04:00",
                info_cutoff="2019-03-29T16:00:00-04:00", universe=["SPY", "TLT"],
                target_weights={"SPY": 0.6, "TLT": 0.4}, generation={"mode": "computed_native"})
    base.update(kw)
    return DecisionRecord(**base)


# ---------------------------------------------------------------- records
def test_record_valid_roundtrip(tmp_path):
    r = _rec()
    validate(r)
    h = write_jsonl([r], tmp_path / "x.jsonl")
    assert len(h) == 64
    assert read_jsonl(tmp_path / "x.jsonl")[0] == dataclasses.replace(r, universe=["SPY", "TLT"])


@pytest.mark.parametrize("bad", [
    dict(target_weights={"SPY": 0.7, "TLT": 0.4}),                       # does not sum to 1
    dict(target_weights={"SPY": 1.1, "TLT": -0.1}),                      # short
    dict(info_cutoff="2019-03-30T10:00:00-04:00"),                       # cutoff after decision
    dict(decision_time="2019-03-29T20:00:00"),                           # no offset
    dict(decision_month="2019-04"),                                      # month mismatch
    dict(generation={"mode": "invented"}),                               # unknown mode
    dict(native_detail={"r_spy": 0.01}),                                 # outcome field smuggled in
    dict(forecast={"values": {"realized_return": 0.02}}),                # nested outcome field
])
def test_record_rejects(bad):
    with pytest.raises(RecordError):
        validate(_rec(**bad))


def test_duplicate_records_rejected(tmp_path):
    with pytest.raises(RecordError):
        write_jsonl([_rec(), _rec()], tmp_path / "d.jsonl")


# ---------------------------------------------------------------- lock
def test_lock_blocks_protected_months(tmp_path):
    months = [pd.Period("2022-12", "M"), pd.Period("2023-01", "M")]
    with pytest.raises(WindowLocked):
        assert_scoring_allowed(months, protected_start="2023-01")
    assert_scoring_allowed(months[:1], protected_start="2023-01")


def test_lock_needs_signed_go_token_and_matching_hashes(tmp_path):
    months = [pd.Period("2024-01", "M")]
    go = tmp_path / "go.json"
    go.write_text(json.dumps({"decision": "NO-GO"}))
    with pytest.raises(WindowLocked):
        assert_scoring_allowed(months, protected_start="2023-01", go_record_path=go, token=OPENING_TOKEN)
    go.write_text(json.dumps({"decision": "GO", "signed_by": ["x"], "frozen_decision_files_sha256": {"AP2A": "aa"}}))
    with pytest.raises(WindowLocked):
        assert_scoring_allowed(months, protected_start="2023-01", go_record_path=go, token="wrong")
    with pytest.raises(WindowLocked):
        assert_scoring_allowed(months, protected_start="2023-01", go_record_path=go, token=OPENING_TOKEN, decision_file_hashes={"AP2A": "bb"})
    assert_scoring_allowed(months, protected_start="2023-01", go_record_path=go, token=OPENING_TOKEN, decision_file_hashes={"AP2A": "aa"})


# ---------------------------------------------------------------- market
def test_decision_day_is_last_common_trading_day(market):
    for m, d in list(market.decision_dates.items())[:-1]:
        later = market.calendar[(market.calendar > d) & (market.calendar.to_period("M") == m)]
        assert len(later) == 0
        assert d.to_period("M") == m


def test_holding_period_and_returns(market):
    m = pd.Period("2020-03", "M")
    entry, exit_ = market.holding_period(m)
    assert entry > market.decision_dates[m] and entry.to_period("M") == pd.Period("2020-04", "M")
    r = market.period_returns(m, ["SPY", "TLT"])
    assert abs(r["SPY"] - (market.prices["SPY"].loc[exit_] / market.prices["SPY"].loc[entry] - 1)) < 1e-15


def test_pre_2011_prices_refused(market):
    with pytest.raises(MarketDataError):
        market.period_returns(pd.Period("2010-11", "M"), ["SPY"])


def test_tlt_scale_follows_the_stage2_rule():
    cfg = load_config()
    for a in ("SPY", "IEF", "LQD", "TLT"):
        seg_pre, seg_post = cfg["_prices"][a]["segments"]
        pre = pd.read_csv(ROOT / seg_pre["path"], parse_dates=["Date"]).set_index("Date")["Close"]
        post = pd.read_csv(ROOT / seg_post["path"], sep="\t", parse_dates=["Date"]).set_index("Date")["Close"]
        d = pd.Timestamp("2018-01-02")
        assert abs(post[d] / pre[d] - seg_pre["scale"]) < 1e-15


def test_decision_time_has_dst_offset():
    assert decision_time_iso(pd.Timestamp("2019-03-29")).endswith("-04:00")
    assert decision_time_iso(pd.Timestamp("2019-01-31")).endswith("-05:00")


# ---------------------------------------------------------------- accounting and metrics
def test_accounting_matches_hand_calculation(market):
    months = [pd.Period("2019-03", "M"), pd.Period("2019-04", "M")]
    recs = [_rec(decision_month=str(m), decision_time=decision_time_iso(market.decision_dates[m]),
                 info_cutoff=decision_time_iso(market.decision_dates[m])) for m in months]
    sim = simulate_records(recs, market, months, cost_per_dollar=0.0005)
    r0 = market.period_returns(months[0], ["SPY", "TLT"])
    assert abs(sim.loc[0, "cost"] - 0.0005) < 1e-15                      # from cash: $1 traded
    gross0 = 0.6 * r0["SPY"] + 0.4 * r0["TLT"]
    pre = np.array([0.6 * (1 + r0["SPY"]), 0.4 * (1 + r0["TLT"])]); pre /= pre.sum()
    assert abs(sim.loc[0, "gross_total_return"] - gross0) < 1e-15
    assert abs(sim.loc[1, "traded_notional"] - np.abs(np.array([0.6, 0.4]) - pre).sum()) < 1e-15


def test_accounting_requires_every_month(market):
    with pytest.raises(AccountingError):
        simulate_records([_rec()], market, [pd.Period("2019-03", "M"), pd.Period("2019-04", "M")], cost_per_dollar=0.0005)


def test_cer_matches_stage2():
    import stage2_portfolio as s2p
    x = np.random.default_rng(1).normal(0.004, 0.03, 60)
    assert abs(M.cer(x) - s2p.cer(x)) < 1e-15


def test_holm():
    out = M.holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert out["a"]["reject_at_alpha"] and not out["b"]["reject_at_alpha"] and not out["c"]["reject_at_alpha"]
    assert abs(out["a"]["holm_adjusted_p"] - 0.03) < 1e-12 and abs(out["b"]["holm_adjusted_p"] - 0.06) < 1e-12


def test_bootstrap_is_seeded():
    a = pd.DataFrame({"decision_month": [f"m{i}" for i in range(30)], "net_excess_return": np.linspace(-0.02, 0.03, 30)})
    b = a.assign(net_excess_return=a["net_excess_return"] * 0.5)
    r1, r2 = M.paired_cer_contrast(a, b, reps=200), M.paired_cer_contrast(a, b, reps=200)
    assert r1 == r2


# ---------------------------------------------------------------- common benchmark (evaluation layer only)
def _template(market, months):
    return [_rec(system_id="SYS", decision_month=str(m), decision_time=decision_time_iso(market.decision_dates[m]),
                 info_cutoff=decision_time_iso(market.decision_dates[m]), universe=["SPY", "IEF"],
                 target_weights={"SPY": 0.5, "IEF": 0.5}) for m in months]


def test_common_benchmark_spec_is_proposed_and_valid():
    from native_backtest.framework import benchmark as B
    cfg = load_config()
    b = B.spec(cfg)
    assert b["status"] == "frozen" and b["weights"] == {"SPY": 0.6, "IEF": 0.4}
    assert abs(sum(b["weights"].values()) - 1) < 1e-12
    bad = json.loads(json.dumps(cfg))
    bad["common_benchmark"]["weights"] = {"SPY": 0.7, "TLT": 0.4}
    with pytest.raises(B.BenchmarkSpecError):
        B.spec(bad)
    bad["common_benchmark"]["weights"] = {"SPY": 0.6, "AGG": 0.4}
    with pytest.raises(B.BenchmarkSpecError):
        B.spec(bad)


def test_common_benchmark_uses_shared_accounting_and_dates(market):
    from native_backtest.framework import benchmark as B
    from native_backtest.framework.accounting import static_portfolio_records
    cfg = load_config()
    months = [pd.Period(m, "M") for m in ("2019-03", "2019-04", "2019-05")]
    tmpl = _template(market, months)
    bench = B.simulate(cfg, market, months, tmpl)
    direct = simulate_records(static_portfolio_records("X", cfg["common_benchmark"]["weights"], tmpl), market, months,
                              cost_per_dollar=cfg["costs"]["cost_per_dollar_traded"])
    assert list(bench["decision_month"]) == [str(m) for m in months]
    assert np.allclose(bench["net_total_return"], direct["net_total_return"], rtol=0, atol=1e-15)
    assert abs(B.cumulative_return(bench) - (np.prod(1 + bench["net_total_return"]) - 1)) < 1e-15


def test_common_benchmark_decomposition_is_exact_and_cancels_between_systems(market):
    from native_backtest.framework import benchmark as B
    from native_backtest.framework.accounting import static_portfolio_records
    cfg = load_config()
    d = cfg["metrics"]["cer_delta"]
    months = [pd.Period(f"2019-{i:02d}", "M") for i in range(3, 13)]
    tmpl = _template(market, months)
    cost = cfg["costs"]["cost_per_dollar_traded"]
    sim = lambda w: simulate_records(static_portfolio_records("S", w, tmpl), market, months, cost_per_dollar=cost)
    a, b, own = sim({"SPY": 0.7, "IEF": 0.3}), sim({"SPY": 0.4, "TLT": 0.6}), sim({"SPY": 0.5, "IEF": 0.5})
    bench = B.simulate(cfg, market, months, tmpl)
    dec = B.decomposition(a, own, bench, d)
    assert abs(dec["total_vs_common"] - dec["active_decisions"] - dec["benchmark_mix_difference"]) < 1e-15
    # a common reference never changes the gap between two systems
    ga = B.decomposition(a, own, bench, d)["total_vs_common"]
    gb = B.decomposition(b, own, bench, d)["total_vs_common"]
    assert abs((ga - gb) - (M.cer(a["net_excess_return"], d) - M.cer(b["net_excess_return"], d))) < 1e-12
    rel = B.relative(a, bench, cfg)
    assert rel["n_months"] == len(months) and rel["tracking_error_annualized"] > 0


def test_common_benchmark_independent_reimplementation(market):
    from native_backtest.framework import benchmark as B
    from native_backtest.scripts.common_benchmark_checks import independent_path
    cfg = load_config()
    months = [pd.Period(f"2020-{i:02d}", "M") for i in range(1, 7)]
    bench = B.simulate(cfg, market, months, _template(market, months))
    dates = {r.decision_month: (r.entry_date, r.exit_date) for r in bench.itertuples()}
    ind = independent_path(market, months, cfg["common_benchmark"]["weights"], cfg["costs"]["cost_per_dollar_traded"], dates)
    for c in ("traded_notional", "cost", "net_total_return", "net_excess_return"):
        assert np.abs(ind[c].to_numpy(float) - bench[c].to_numpy(float)).max() < 1e-12


def test_common_benchmark_fingerprint_tracks_numbers_not_status():
    from native_backtest.framework import benchmark as B
    cfg = load_config()
    f0 = B.fingerprint(cfg)
    assert f0 == cfg["common_benchmark"]["frozen"]["fingerprint_sha256"]
    rec = json.loads((ROOT / cfg["common_benchmark"]["frozen"]["approval_record"]).read_text())
    assert rec["fingerprint_sha256"] == f0 and rec["decision"] == "APPROVED AND FROZEN"
    c = json.loads(json.dumps(cfg))
    c["common_benchmark"]["status_note"] = "reworded note"
    assert B.fingerprint(c) == f0                      # notes are outside the fingerprint
    for change in ({"weights": {"SPY": 0.55, "IEF": 0.45}}, {"role": "x"}):
        c = json.loads(json.dumps(cfg))
        c["common_benchmark"].update(change)
        with pytest.raises(B.BenchmarkSpecError, match="frozen common benchmark changed"):
            B.spec(c)
    c = json.loads(json.dumps(cfg))
    c["costs"]["cost_per_dollar_traded"] = 0.001       # an inherited shared setting
    with pytest.raises(B.BenchmarkSpecError, match="frozen common benchmark changed"):
        B.spec(c)
    c["common_benchmark"]["status"] = "draft"          # an unfrozen copy may differ, and its fingerprint does
    assert B.fingerprint(c) != f0
