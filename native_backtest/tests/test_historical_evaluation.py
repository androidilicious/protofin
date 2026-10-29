"""The final historical backtest stays sealed: these tests only exercise its refusals; nothing is scored."""
from __future__ import annotations

import json

import pytest

from native_backtest.framework.lock import WindowLocked
from native_backtest.scripts import historical_evaluation as H


def test_check_mode_scores_nothing_and_lists_prerequisites(capsys):
    assert H.main(["--check"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ready"] is False
    assert any("signed GO record" in m for m in out["missing"])
    assert any("primary version" in m for m in out["missing"])


def test_refuses_without_signed_go_record_and_token(tmp_path):
    with pytest.raises(WindowLocked):
        H.main([])
    fake = tmp_path / "go.json"
    fake.write_text(json.dumps({"decision": "GO"}))          # unsigned
    with pytest.raises(WindowLocked, match="not a signed GO"):
        H.main(["--go-record", str(fake), "--token", "wrong"])


def test_protected_periods_match_the_frozen_design():
    from native_backtest.framework.market import load_config
    p = H.periods(load_config())
    assert (str(p["primary"][0]), str(p["primary"][-1]), len(p["primary"])) == ("2024-01", "2026-08", 32)
    assert (str(p["secondary_2023"][0]), str(p["secondary_2023"][-1])) == ("2023-01", "2023-12")


def test_release_manifest_verifies():
    from native_backtest.scripts import release_manifest as R
    assert R.check() == [], "run: python -m native_backtest.scripts.release_manifest"
