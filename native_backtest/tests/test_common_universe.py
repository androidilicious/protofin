"""Guards on the common-universe re-specification.

All three primary approaches hold the same three funds. The Agentic Workflow's records are re-expressed from its
native SPY/TLT allocation onto SPY/IEF/LQD under the pre-registration committed before any result was computed.
These tests check that the re-expression changed only the asset set: the stock weight the engine actually decides,
the decision dates and the saved answers are untouched, and the bond split is one frozen constant.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEC = ROOT / "native_backtest/out/decisions"
PREREG = ROOT / "native_backtest/config/jev_common_universe_respecification_v1.json"
CONFIG = ROOT / "native_backtest/config/framework_config_v1.json"
MAPPED = ("AP2B", "AP2A", "AP2_COMBO")
COMMON = ["SPY", "IEF", "LQD"]


def jload(p: Path) -> dict:
    return json.loads(p.read_text())


def rows(name: str) -> list:
    return [json.loads(l) for l in (DEC / f"{name}.jsonl").read_text().splitlines() if l.strip()]


@pytest.fixture(scope="module")
def pre() -> dict:
    return jload(PREREG)


def test_the_respecification_is_pre_registered_before_any_result():
    pre = jload(PREREG)
    assert pre["id"] and pre["version"]
    sleeve = pre["mapping"]["bond_sleeve_proportions"]
    assert set(sleeve) == {"IEF", "LQD"}
    assert sum(sleeve.values()) == pytest.approx(1.0, abs=1e-12)
    # the ratio is the Deterministic neutral portfolio's own 35:20, a fixed rule rather than a fitted number
    assert sleeve["IEF"] == pytest.approx(35 / 55, abs=1e-12)
    assert sleeve["LQD"] == pytest.approx(20 / 55, abs=1e-12)
    assert set(pre["mapping"]["applies_to"]) == set(MAPPED)
    assert pre["surviving_limitations"], "the limitations the mapping does not remove must stay on the record"


def test_every_system_in_the_frozen_config_holds_the_same_three_funds():
    cfg = jload(CONFIG)
    for sid, s in cfg["systems"].items():
        assert list(s["universe"]) == COMMON, sid
        assert set(s["native_neutral_weights"]) == set(COMMON), sid
        assert sum(s["native_neutral_weights"].values()) == pytest.approx(1.0, abs=1e-12), sid
    # the surviving neutral difference is the stock weight, and it is still there
    assert cfg["systems"]["AP1"]["native_neutral_weights"]["SPY"] == 0.45
    assert cfg["systems"]["AP3"]["native_neutral_weights"]["SPY"] == 0.45
    assert cfg["systems"]["AP2B"]["native_neutral_weights"]["SPY"] == 0.60
    assert cfg["systems"]["AP2A"]["native_neutral_weights"]["SPY"] == 0.60


def test_the_native_records_are_archived_unchanged_beside_the_mapped_ones():
    for name in MAPPED:
        arch = DEC / f"{name}_native_spy_tlt.jsonl"
        assert arch.exists(), f"{name}: the native records must stay in the repository"
        native = [json.loads(l) for l in arch.read_text().splitlines() if l.strip()]
        assert native and all(r["universe"] == ["SPY", "TLT"] for r in native)
        assert all(set(r["target_weights"]) == {"SPY", "TLT"} for r in native)


@pytest.mark.parametrize("name", MAPPED)
def test_the_mapping_changed_only_the_asset_set(name, pre):
    sleeve = pre["mapping"]["bond_sleeve_proportions"]
    native = {r["decision_month"]: r for r in
              (json.loads(l) for l in (DEC / f"{name}_native_spy_tlt.jsonl").read_text().splitlines() if l.strip())}
    mapped = rows(name)
    assert [r["decision_month"] for r in mapped] == sorted(native)
    ratios = set()
    for r in mapped:
        n = native[r["decision_month"]]
        assert list(r["universe"]) == COMMON, r["decision_month"]
        # the only number this engine decides is the stock weight, and it carries over exactly
        assert r["target_weights"]["SPY"] == n["target_weights"]["SPY"], r["decision_month"]
        rest = 1.0 - r["target_weights"]["SPY"]
        for a, p in sleeve.items():
            assert r["target_weights"][a] == pytest.approx(rest * p, abs=1e-15), (r["decision_month"], a)
        assert sum(r["target_weights"].values()) == pytest.approx(1.0, abs=1e-12)
        assert min(r["target_weights"].values()) >= 0.0
        if rest > 1e-12:
            ratios.add(round(r["target_weights"]["IEF"] / rest, 12))
        # the saved answer, the timestamps and the system's own identity are untouched
        assert r["forecast"] == n["forecast"], r["decision_month"]
        assert r["confidence"] == n["confidence"], r["decision_month"]
        assert (r["decision_time"], r["info_cutoff"]) == (n["decision_time"], n["info_cutoff"])
        assert r["system_id"] == n["system_id"]
        assert r["generation"]["respecification"] == pre["id"]
    assert len(ratios) == 1, "the bond split must be one frozen constant, not a per-month choice"


def test_the_combination_is_the_average_of_its_mapped_components():
    a = {r["decision_month"]: r["target_weights"] for r in rows("AP2A")}
    b = {r["decision_month"]: r["target_weights"] for r in rows("AP2B")}
    for r in rows("AP2_COMBO"):
        m = r["decision_month"]
        for asset in COMMON:
            assert r["target_weights"][asset] == pytest.approx(0.5 * (a[m][asset] + b[m][asset]), abs=1e-15), (m, asset)


def test_the_universe_change_is_its_own_step_in_the_native_to_common_ladder():
    rep = jload(ROOT / "native_backtest/out/development/development_evaluation_report.json")
    for sid in ("AP2B", "AP2A"):
        ladder = rep["ap2_execution_attribution"][sid]["matched_2019-03_to_2022-12"]
        last = ladder[-1]
        assert "common SPY/IEF/LQD universe" in last["variant"], sid
        assert "common evaluation" in last["variant"], sid
        # no earlier rung may claim to be the reported evaluation
        assert not any("common evaluation" in r["variant"] for r in ladder[:-1]), sid
        # the step is measured, not asserted
        assert "delta_cer_vs_previous" in last and abs(last["delta_cer_vs_previous"]) > 0.0, sid


def test_the_reported_agentic_workflow_result_is_the_last_rung_of_that_ladder():
    rep = jload(ROOT / "native_backtest/out/development/development_evaluation_report.json")
    rowsd = {r["system"]: r for r in rep["common_evaluation_matched_dev"]}
    for sid in ("AP2B", "AP2A"):
        ladder = rep["ap2_execution_attribution"][sid]["matched_2019-03_to_2022-12"]
        assert rowsd[sid]["absolute"]["cer_delta_2_5"] == pytest.approx(ladder[-1]["cer_delta_2_5"], abs=1e-12), sid


def test_the_surviving_differences_are_still_disclosed():
    rep = jload(ROOT / "native_backtest/out/development/development_evaluation_report.json")
    text = rep["comparability_statement"]
    assert "same three assets" in text
    assert "12-month" in text and "60%" in text and "45%" in text
    assert "frozen constant" in text or "rather than a decision" in text


def test_the_dashboard_publishes_the_frozen_bond_split_and_says_it_is_a_rule():
    d = jload(ROOT / "mvp/data/dashboard.json")
    cu = d["common_universe"]
    assert cu["assets"] == COMMON
    assert cu["bond_sleeve"] == jload(PREREG)["mapping"]["bond_sleeve_proportions"]
    assert "rule rather than a forecast" in cu["note"]
    for s in d["systems"] + d["variants"]:
        assert list(s["universe"]) == COMMON, s["short"]
