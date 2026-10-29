"""Resuming a qwen3:4b session from the results branch.

The results branch holds genuine agent outputs from earlier sessions. A later session must continue from them
instead of spending free-GPU time on inference it already has: completed months are not rerun, and a gate already
scored on the same fixtures under the same agent protocol is not rescored. Nothing here relaxes a gate: the
restored verdicts keep their real (failed) values, and the reports of the sessions the bundle came from survive
the rewrite of summary.json.
"""
import json

import pytest


def _bundle(tmp_path, months, gates, reliability=None):
    b = tmp_path / "bundle"
    (b / "months").mkdir(parents=True)
    for i, m in enumerate(months):
        (b / "months" / f"{m}.json").write_text(json.dumps({"month": m, "record_sha256": f"{i:064x}"}))
    s = {"protocol": {"version": "1.1", "fingerprint": "983e4b398c4a09ac"}, "gates": gates,
         "n_months": len(months), "months_complete": list(months), "written_utc": "2026-10-29T15:11:00Z",
         "reliability_this_session": reliability}
    (b / "summary.json").write_text(json.dumps(s))
    return b


GATES = {"G3a": {"pass": False, "checks": {"schema_valid_call_rate": {"value": 0.977, "pass": False}}},
         "G3b": {"pass": False, "checks": {"accuracy": {"value": 0.5666666666666667, "pass": False},
                                           "opposite_direction_errors": {"value": 2, "pass": False}}}}
SAMPLE_MONTHS = ["2015-02", "2015-03", "2015-04", "2015-05", "2015-06", "2015-07",
                 "2015-08", "2015-09", "2015-10", "2015-11", "2015-12", "2016-01"]


def test_a_restored_bundle_reuses_both_gate_verdicts_and_never_rescores_them(tmp_path, monkeypatch):
    from native_backtest.scripts import ap3_free_run as fr
    b = _bundle(tmp_path, SAMPLE_MONTHS, GATES)
    monkeypatch.setattr(fr, "BUNDLE", b)
    monkeypatch.setattr(fr, "_out", lambda: tmp_path)
    monkeypatch.setattr(fr, "check", lambda: {"model": {}})
    written = []
    monkeypatch.setattr(fr, "bundle", lambda recs, gates, *a, **k: (written.append((len(recs), gates)), {})[1])
    monkeypatch.setattr(fr, "g3b", lambda: pytest.fail("G3b was rescored although the bundle holds its verdict"))
    monkeypatch.setattr(fr, "g3a", lambda recs: pytest.fail("G3a was rescored although the bundle holds its verdict"))
    ran = []
    monkeypatch.setattr(fr, "run_months", lambda ms, d, w: (ran.append(list(ms)), {m: {"status_features": {}} for m in ms})[1])

    code = fr.main(["--stage", "all", "--hours", "1", "--exploratory"])

    assert code == fr.GATE_FAILED                                   # a gate did fail and the exit code still says so
    assert [m for b_ in ran for m in b_][:1] == ["2016-02"]          # the 12 sample months are not reprocessed
    assert sum(len(x) for x in ran) == 83                            # 2016-02..2022-12 only
    for _, g in written:                                             # the real failed values are carried through
        assert g["G3b"]["checks"]["accuracy"]["value"] == pytest.approx(0.5666666666666667)
        assert g["G3b"]["pass"] is False and g["G3a"]["pass"] is False


def test_an_explicit_g3b_stage_always_rescores_the_fixtures(tmp_path, monkeypatch):
    from native_backtest.scripts import ap3_free_run as fr
    monkeypatch.setattr(fr, "BUNDLE", _bundle(tmp_path, SAMPLE_MONTHS, GATES))
    monkeypatch.setattr(fr, "_out", lambda: tmp_path)
    monkeypatch.setattr(fr, "check", lambda: {"model": {}})
    calls = []
    monkeypatch.setattr(fr, "g3b", lambda: (calls.append(1), {"pass": False, "checks": {}, "rows": []})[1])
    assert fr.main(["--stage", "g3b"]) == fr.GATE_FAILED and calls == [1]


def test_the_restored_bundle_keeps_the_reliability_report_of_the_session_it_came_from(tmp_path, monkeypatch):
    from native_backtest.scripts import ap3_free_run as fr
    rel = {"months_with_hypotheses": 12, "hypotheses": 59, "tests": 59, "failed_tests": 10, "failed_months": 0}
    b = _bundle(tmp_path, SAMPLE_MONTHS, GATES, reliability=rel)
    # what restore_from_branch() writes beside a bundle it carried over
    earlier = [{"written_utc": "2026-10-29T15:11:00Z", "n_months": 12, "months_complete": SAMPLE_MONTHS,
                "gates": {"G3a": False, "G3b": False}, "report": rel}]
    (b / "reliability_earlier.json").write_text(json.dumps(earlier))
    monkeypatch.setattr(fr, "BUNDLE", b)
    monkeypatch.setattr(fr, "_out", lambda: tmp_path)

    s = fr.bundle({}, GATES, {"model": {}}, None)

    assert s["n_months"] == 12 and s["reliability_this_session"] is None      # this session added no months
    assert s["reliability_earlier_sessions"] == earlier                      # but the earlier report is not lost
    assert s["reliability_earlier_sessions"][0]["report"]["hypotheses"] == 59


def test_a_bundle_from_another_protocol_is_never_restored(tmp_path, monkeypatch):
    from native_backtest.ap3 import protocol
    from native_backtest.scripts import ap3_free_run as fr
    b = _bundle(tmp_path, SAMPLE_MONTHS, GATES)
    s = json.loads((b / "summary.json").read_text())
    s["protocol"] = {"version": "1.0", "fingerprint": "0" * 16}
    (b / "summary.json").write_text(json.dumps(s))
    monkeypatch.setattr(fr, "BUNDLE", b)
    assert protocol.fingerprint() != "0" * 16
    note = fr.set_aside_stale_bundle()
    assert note and not b.exists() and (tmp_path / "qwen3_runs_superseded_0000000000000000").exists()
