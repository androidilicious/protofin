"""The harness must reproduce the level field exactly: each plugin's table equals run.py's loader."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from decision_support import contract, registry  # noqa: E402
from level_playing_field import run as lpf  # noqa: E402

CFG = contract.repo_root() / "level_playing_field" / "config.json"


def _same(a: pd.DataFrame, b: pd.DataFrame):
    a, b = a.sort_index(), b.sort_index()
    assert sorted(a.columns) == sorted(b.columns)
    pd.testing.assert_frame_equal(a[sorted(a.columns)], b[sorted(b.columns)], check_dtype=False, check_names=False)
    for k in b.attrs.get("stated", {}):
        pd.testing.assert_series_equal(a.attrs["stated"][k], b.attrs["stated"][k], check_names=False, check_dtype=False)


def test_registry_finds_the_five_plugins():
    names = sorted(registry.discover())
    assert names == ["causal_rag", "committee", "det", "jev", "placebo"]


@pytest.mark.parametrize("name,fund_set,loader", [
    ("jev", "spy_tlt", lambda: lpf.signals_jev(ROOT / "level_playing_field/data/jev_1m.json")),
    ("jev", "spy_ief_lqd", lambda: lpf.signals_jev_3f(ROOT / "level_playing_field/data/jev_3f.json")),
    ("committee", "spy_tlt", lambda: lpf.signals_committee(ROOT / "level_playing_field/data/committee_1m.json")),
    ("committee", "spy_ief_lqd", lambda: lpf.signals_committee_3f(ROOT / "level_playing_field/data/committee_3f.json")),
    ("causal_rag", "spy_tlt", lambda: lpf.signals_causal_rag(ROOT / "level_playing_field/data/causal_rag_qwen3.json")),
    ("causal_rag", "spy_ief_lqd", lambda: lpf.signals_causal_rag_3f(ROOT / "level_playing_field/data/causal_rag_qwen3_3f.json")),
])
def test_plugin_table_equals_level_field_loader(name, fund_set, loader):
    p = registry.load(name)
    ans = p.answers(fund_set)
    contract.validate(ans, p.manifest, fund_set)
    _same(contract.to_frame(ans, fund_set, p.manifest), loader())


def test_det_table_equals_level_field_loader():
    p = registry.load("det")
    ans = p.answers("spy_tlt")
    contract.validate(ans, p.manifest, "spy_tlt")
    import json
    from native_backtest.framework import market as mk
    spec = json.loads((ROOT / mk.load_config()["inherits_stage2_run_spec"]["path"]).read_text())
    _same(contract.to_frame(ans, "spy_tlt", p.manifest), lpf.signals_det(spec))


def test_placebo_is_no_signal():
    p = registry.load("placebo")
    assert p.answers("spy_tlt") == []
    assert contract.to_frame([], "spy_tlt", p.manifest) is None
    assert contract.coverage([], [pd.Period("2019-03", "M")], "spy_tlt", p.manifest) == 1.0


def test_contract_rejects_bad_answers():
    m = contract.Manifest(name="x", title="x", kind="replay", fund_sets=["spy_tlt"])
    good = contract.Answer(month="2019-03", stated={"SPY": 1.0, "TLT": -1.0}, confidence=0.4)
    contract.validate([good], m, "spy_tlt")
    with pytest.raises(contract.ContractError):
        contract.validate([good, good], m, "spy_tlt")                                   # a month twice
    with pytest.raises(contract.ContractError):
        contract.validate([contract.Answer(month="2019-03", stated={"SPY": 1.0})], m, "spy_tlt")   # TLT missing
    with pytest.raises(contract.ContractError):
        contract.validate([contract.Answer(month="2019-03-29", stated={"SPY": 1.0, "TLT": 0.0})], m, "spy_tlt")
    with pytest.raises(contract.ContractError):
        contract.validate([contract.Answer(month="2019-03", stated={"SPY": 1.0, "TLT": 0.0}, confidence=1.4)], m, "spy_tlt")
    with pytest.raises(contract.ContractError):
        contract.validate([good], m, "spy_ief_lqd")                                     # unsupported fund set


def test_coverage_counts_usable_months():
    m = contract.Manifest(name="x", title="x", kind="replay", fund_sets=["spy_tlt"])
    months = [pd.Period("2019-03", "M"), pd.Period("2019-04", "M")]
    ans = [contract.Answer(month="2019-03", stated={"SPY": 1.0, "TLT": -1.0}), contract.Answer(month="2019-04", stated={"SPY": None, "TLT": 0.0})]
    assert contract.coverage(ans, months, "spy_tlt", m) == 0.5
