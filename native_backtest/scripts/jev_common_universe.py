#!/usr/bin/env python3
"""Re-express JEV's native allocation on the common SPY/IEF/LQD universe.

Pre-registered in native_backtest/config/jev_common_universe_respecification_v1.json. The agent's saved answers
and the native mechanism are replayed untouched; only the asset set the resulting allocation is expressed over
changes. The stock weight carries over exactly and the bond remainder is split at the frozen ratio implied by
the Deterministic neutral portfolio, which is a fixed rule and not a forecast.

Usage (repository root): python -m native_backtest.scripts.jev_common_universe
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "native_backtest/config/jev_common_universe_respecification_v1.json"
DEC = ROOT / "native_backtest/out/decisions"
TOL = 1e-12
# The native SPY/TLT records are archived under their own name and keep backing the stock-weight verification;
# the common-universe expression takes the system's primary filename, which every downstream loader reads.
# AP2_COMBO is the average of the two; the mapping is linear in the stock weight, so mapping the
# average equals averaging the mapped records — the combination experiment stays coherent either way.
SYSTEMS = ("AP2B", "AP2A", "AP2_COMBO")
ARCHIVE = "{}_native_spy_tlt.jsonl"


def main(argv=None) -> int:
    pre = json.loads(PREREG.read_text())
    sleeve = pre["mapping"]["bond_sleeve_proportions"]
    assets = ["SPY", *sleeve]
    assert abs(sum(sleeve.values()) - 1.0) < TOL, "the bond sleeve must be a full split"

    report = {}
    for system in SYSTEMS:
        report[system] = convert(system, pre, sleeve, assets)
    print(json.dumps({"respecification": pre["id"], "neutral": pre["mapping"]["native_neutral_weights"],
                      "systems": report}, indent=1))
    return 0


def convert(system: str, pre: dict, sleeve: dict, assets: list) -> dict:
    archive = DEC / ARCHIVE.format(system)
    primary = DEC / f"{system}.jsonl"
    # first run: move the native records aside, once. After that the archive is the source of truth.
    if not archive.exists():
        archive.write_text(primary.read_text())
    rows = [json.loads(l) for l in archive.read_text().splitlines() if l.strip()]
    out, checks = [], {"months": 0, "max_abs_stock_weight_difference": 0.0,
                       "max_abs_sum_minus_one": 0.0, "min_weight": 1.0,
                       "distinct_bond_sleeve_ratios": set()}
    for r in rows:
        assert r["universe"] == ["SPY", "TLT"], r["decision_month"]
        w_spy = float(r["target_weights"]["SPY"])
        rest = 1.0 - w_spy
        w = {"SPY": w_spy, **{a: rest * p for a, p in sleeve.items()}}
        checks["months"] += 1
        checks["max_abs_stock_weight_difference"] = max(checks["max_abs_stock_weight_difference"], abs(w["SPY"] - w_spy))
        checks["max_abs_sum_minus_one"] = max(checks["max_abs_sum_minus_one"], abs(sum(w.values()) - 1.0))
        checks["min_weight"] = min(checks["min_weight"], min(w.values()))
        if rest > TOL:
            checks["distinct_bond_sleeve_ratios"].add(round(w["IEF"] / rest, 12))
        n = dict(r)
        n["universe"] = assets
        n["target_weights"] = w
        n["generation"] = {**r["generation"], "respecification": pre["id"], "respecification_version": pre["version"],
                           "native_universe": ["SPY", "TLT"],
                           "note": ("the agent's answers and the native mechanism are unchanged; only the asset set "
                                    "the allocation is expressed over differs, per the committed pre-registration")}
        out.append(n)

    # the pre-registered checks, before any result is read
    assert checks["max_abs_stock_weight_difference"] <= TOL, checks
    assert checks["max_abs_sum_minus_one"] <= TOL, checks
    assert checks["min_weight"] >= 0.0, checks
    assert len(checks["distinct_bond_sleeve_ratios"]) == 1, "the bond split must be identical in every month"
    assert [r["decision_month"] for r in out] == [r["decision_month"] for r in rows]
    assert all(a["decision_time"] == b["decision_time"] and a["info_cutoff"] == b["info_cutoff"]
               for a, b in zip(out, rows)), "timestamps must be untouched"

    primary.write_text("".join(json.dumps(r, default=str) + "\n" for r in out))
    checks["distinct_bond_sleeve_ratios"] = sorted(checks["distinct_bond_sleeve_ratios"])
    return {"archive": str(archive.relative_to(ROOT)), "written": str(primary.relative_to(ROOT)), "checks": checks}


if __name__ == "__main__":
    raise SystemExit(main())
