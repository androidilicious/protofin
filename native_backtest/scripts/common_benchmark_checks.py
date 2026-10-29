#!/usr/bin/env python3
"""Specification and accounting checks for the common benchmark (development months only).

Every check must pass before the benchmark is put forward for freeze approval:
  1. spec          the configured benchmark is valid (long-only, sums to 1, assets on the evaluation calendar,
                   monthly rebalancing at the shared entry close) and, once frozen, still matches the fingerprint in
                   its approval record;
  2. data_gates    each benchmark asset passed Stage 2 gate 5 (distribution adjustment);
  3. inputs        the pinned price and cash inputs match their recorded SHA-256;
  4. dates         decision months, entry dates and exit dates are identical to every system's;
  5. template      the benchmark path does not depend on which system's records supply the dates;
  6. independent   an independent re-implementation from the raw price series (dollar holdings, not the
                   shared simulator) reproduces every monthly return, cost and turnover to 1e-12;
  7. first_month   the first month starts from cash: dollars traded = 1, cost = the shared cost rate;
  8. gaps          subtracting the common benchmark leaves every pairwise primary CER difference unchanged;
  9. decomposition vs-common = decisions + benchmark mix, exactly, for every system (accounting identity);
 10. protected     no month at or after the protected window start is read.
Sensitivity to the cost rate (0 and 10 bp) is reported for information; it is not a pass criterion.

Writes native_backtest/out/development/common_benchmark_checks.json. Exit code 0 only if every check passes.
Usage: python -m native_backtest.scripts.common_benchmark_checks
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from native_backtest.framework import benchmark as B
from native_backtest.framework import metrics as M
from native_backtest.framework.accounting import simulate_records, static_portfolio_records
from native_backtest.framework.lock import assert_scoring_allowed
from native_backtest.framework.market import load_config, load_market, months_between, verify_input_hashes
from native_backtest.framework.records import read_jsonl

ROOT = Path(__file__).resolve().parents[2]
DEC = ROOT / "native_backtest/out/decisions"
OUT = ROOT / "native_backtest/out/development"
GATE = ROOT / "stage2/results/dividend_gate/dividend_gate_status.json"
TOL = 1e-12


def independent_path(mk, months, weights, cost_rate, dates):
    """Dollar-holdings re-implementation of the stated rules, reading raw prices on the given dates."""
    assets = list(weights)
    hold = {a: 0.0 for a in assets}          # dollars per asset before the trade, per $1 of start-of-month value
    rows = []
    for m in months:
        entry, exit_ = (pd.Timestamp(d) for d in dates[str(m)])
        value = sum(hold.values())
        pre = {a: (hold[a] / value if value > 0 else 0.0) for a in assets}
        traded = sum(abs(weights[a] - pre[a]) for a in assets)
        px_ret = {a: mk.prices[a].loc[exit_] / mk.prices[a].loc[entry] - 1.0 for a in assets}
        gross = sum(weights[a] * px_ret[a] for a in assets)
        cost = cost_rate * traded
        rows.append({"decision_month": str(m), "traded_notional": traded, "cost": cost, "gross_total_return": gross,
                     "net_total_return": gross - cost, "net_excess_return": gross - cost - mk.rf_return(m)})
        hold = {a: weights[a] * (1.0 + px_ret[a]) for a in assets}
    return pd.DataFrame(rows)


def main() -> int:
    cfg = load_config()
    mk = load_market(cfg)
    prot = cfg["windows"]["protected"][0]
    cost = cfg["costs"]["cost_per_dollar_traded"]
    delta = cfg["metrics"]["cer_delta"]
    months = months_between(*cfg["windows"]["development"])
    checks, info = {}, {}

    # 10. protected window (checked first: nothing is read if it fails)
    assert_scoring_allowed(months, protected_start=prot)
    checks["protected"] = {"pass": all(str(m) < prot for m in months), "last_month": str(months[-1]), "protected_start": prot}

    # 1. specification
    spec = B.spec(cfg)
    fp = B.fingerprint(cfg)
    rec = ROOT / spec.get("frozen", {}).get("approval_record", "-")
    frozen_ok = spec["status"] != "frozen" or (rec.is_file() and json.loads(rec.read_text())["fingerprint_sha256"] == fp)
    checks["spec"] = {"pass": frozen_ok and spec["rebalance"] == "monthly_to_target_at_entry_close",
                      "id": spec["id"], "label": spec["label"], "weights": spec["weights"], "status": spec["status"],
                      "fingerprint_sha256": fp, "approval_record": str(rec.relative_to(ROOT)) if rec.is_file() else None}

    # 2. data gates
    gate = json.loads(GATE.read_text())
    by = {t["ticker"]: t for t in gate["by_ticker"]}
    status = {a: ("PASS" if by.get(a, {}).get("pass") is True and all(by[a][k]["pass"] for k in by[a] if k.startswith("C")) else "NOT PASSED")
              for a in spec["weights"]}
    checks["data_gates"] = {"pass": gate["status"] == "PASS" and all(v == "PASS" for v in status.values()), "gate5": status,
                            "price_data_cutoff": gate["price_data_cutoff"], "source": str(GATE.relative_to(ROOT))}

    # 3. pinned inputs
    hashes = verify_input_hashes(cfg)
    checks["inputs"] = {"pass": True, "verified_sha256": {k: v for k, v in hashes.items() if k.split("#")[0] in spec["weights"] or k == "DTB4WK"},
                        "how": "load_market refuses to load if any pinned input differs from its recorded SHA-256"}

    recs = {s: [r for r in read_jsonl(DEC / f"{s}.jsonl") if r.decision_month in {str(m) for m in months}] for s in ("AP1", "AP2B", "AP2A")}
    sims = {s: simulate_records(recs[s], mk, months, cost_per_dollar=cost) for s in recs}
    bench = {s: B.simulate(cfg, mk, months, recs[s]) for s in recs}
    b = bench["AP1"]

    # 4. dates
    cols = ["decision_month", "entry_date", "exit_date"]
    same = {s: bool(sims[s][cols].equals(b[cols])) for s in sims}
    checks["dates"] = {"pass": all(same.values()), "identical_to": same, "first": b[cols].iloc[0].tolist(), "last": b[cols].iloc[-1].tolist()}

    # 5. template invariance
    num = ["net_total_return", "net_excess_return", "cost", "traded_notional"]
    dev = {s: float(np.abs(bench[s][num].to_numpy(float) - b[num].to_numpy(float)).max()) for s in bench}
    checks["template"] = {"pass": max(dev.values()) == 0.0, "max_abs_difference": dev}

    # 6. independent re-implementation
    dates = {r.decision_month: (r.entry_date, r.exit_date) for r in b.itertuples()}
    ind = independent_path(mk, months, spec["weights"], cost, dates)
    diff = {c: float(np.abs(ind[c].to_numpy(float) - b[c].to_numpy(float)).max()) for c in ("traded_notional", "cost", "gross_total_return", "net_total_return", "net_excess_return")}
    checks["independent"] = {"pass": max(diff.values()) < TOL, "max_abs_difference": diff, "tolerance": TOL}

    # 7. first month from cash
    checks["first_month"] = {"pass": abs(b["traded_notional"].iloc[0] - 1.0) < TOL and abs(b["cost"].iloc[0] - cost) < TOL,
                             "traded_notional": float(b["traded_notional"].iloc[0]), "cost": float(b["cost"].iloc[0])}

    # 8. pairwise gaps unchanged; 9. exact accounting decomposition
    vc = {s: B.relative(sims[s], b, cfg)["cer_difference"] for s in sims}
    gaps = {}
    for x, y in cfg["primary_contrasts"]:
        if x in sims and y in sims:
            gaps[f"{x}-{y}"] = abs((vc[x] - vc[y]) - M.paired_cer_contrast(sims[x], sims[y])["cer_difference"])
    checks["gaps"] = {"pass": bool(gaps) and max(gaps.values()) < TOL, "abs_difference": gaps}
    attr = {}
    for s in sims:
        own = simulate_records(static_portfolio_records("own", cfg["systems"][s]["native_neutral_weights"], recs[s]), mk, months, cost_per_dollar=cost)
        d = B.decomposition(sims[s], own, b, delta)
        attr[s] = {**d, "residual": d["total_vs_common"] - d["active_decisions"] - d["benchmark_mix_difference"]}
    checks["decomposition"] = {"pass": all(abs(v["residual"]) < TOL for v in attr.values()), "by_system": attr}

    # information: cost sensitivity of the benchmark
    for c in (0.0, 0.0010):
        # a sensitivity variant, not the frozen benchmark: same weights and dates at another cost rate
        s = simulate_records(static_portfolio_records("SENS", spec["weights"], recs["AP1"]), mk, months, cost_per_dollar=c)
        info[f"cer_at_{c * 1e4:.0f}bp"] = M.cer(s["net_excess_return"], delta)
    info[f"cer_at_{cost * 1e4:.0f}bp"] = M.cer(b["net_excess_return"], delta)
    info["annualized_one_way_turnover"] = M.metrics(b)["annualized_one_way_turnover"]

    for v in checks.values():
        v["pass"] = bool(v["pass"])
    ok = all(v["pass"] for v in checks.values())
    out = {"benchmark": spec["id"], "window": [str(months[0]), str(months[-1])], "all_pass": ok, "checks": checks, "information": info,
           "note": "Development months only. Checks the specification and accounting; they say nothing about whether the benchmark is easy or hard to beat."}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "common_benchmark_checks.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
    print(json.dumps({k: v["pass"] for k, v in checks.items()}, indent=1), "\nall_pass:", ok)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
