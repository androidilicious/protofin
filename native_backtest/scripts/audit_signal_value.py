#!/usr/bin/env python3
"""Independent check of the signal value-added analysis (out/signal_value/signal_value_v1.json).

Rebuilds every reported number from the raw inputs:
- the pinned adjusted prices (hash-checked);
- the DTB4WK cash file;
- the decision records.

It imports no project accounting, metrics, benchmark or Stage 2 code. It uses only numpy, pandas and the helpers
of the independent portfolio-integrity audit, which themselves import no project code (checked by a test). The
circular block bootstrap is re-implemented here from its written definition.

Rebuilt and compared:
- the signal-on and signal-off portfolios, the hybrid mixes and the buy-and-hold references;
- every metric, every incremental contrast with its bootstrap range and p-value;
- the three research questions;
- both attributions and their reconciliation;
- the decision diagnostics, the regime splits and the Stage 2 and native JEV sensitivities.

Every number must agree within 1e-12.

Usage (repository root): python -m native_backtest.scripts.audit_signal_value
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from native_backtest.scripts import audit_portfolio_integrity as A

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "native_backtest/out/signal_value"
TOL = 1e-12
NO_SIGNAL = {"AP1": {"SPY": 0.45, "IEF": 0.35, "LQD": 0.20}, "AP2B": {"SPY": 0.60, "TLT": 0.40}}
# Causal RAG is rebuilt here too once its genuine decisions exist; its own frozen control is the same
# 45/35/20 portfolio as the Deterministic model's.
if (ROOT / "native_backtest/out/decisions/AP3_qwen3_reduced_evidence.jsonl").exists():
    NO_SIGNAL["AP3"] = {"SPY": 0.45, "IEF": 0.35, "LQD": 0.20}
HYBRID = {"JEV_STOCKS_DET_BONDS": {"SPY": 0.60, "IEF": 0.40 * 35 / 55, "LQD": 0.40 * 20 / 55},
          "DET_STOCKS_JEV_BONDS": {"SPY": 0.45, "TLT": 0.55}}
UNIVERSE = {"AP1": ["SPY", "IEF", "LQD"], "AP2B": ["SPY", "TLT"], "AP3": ["SPY", "IEF", "LQD"]}


def cer(x, delta: float) -> float:
    x = np.asarray(x, float)
    return float(12.0 * (x.mean() - 0.5 * delta * x.var(ddof=1)))


def block_indices(T: int, block: int, rng) -> np.ndarray:
    """Circular blocks: ceil(T/block) uniform starts, each followed by block-1 successors (mod T), truncated to T."""
    starts = rng.integers(0, T, size=math.ceil(T / block))
    return np.array([(int(s) + k) % T for s in starts for k in range(block)][:T], dtype=int)


def bootstrap(series: dict, stats: dict, P: dict) -> dict:
    T = len(next(iter(series.values())))
    rng = np.random.default_rng(P["seed"])
    d = {k: np.empty(P["reps"]) for k in stats}
    for i in range(P["reps"]):
        idx = block_indices(T, P["block"], rng)
        c = {k: cer(v[idx], P["delta"]) for k, v in series.items()}
        for k, f in stats.items():
            d[k][i] = f(c)
    pt = {k: cer(v, P["delta"]) for k, v in series.items()}
    return {k: {"point": f(pt), "ci90": [np.percentile(d[k], 5), np.percentile(d[k], 95)], "ci95": [np.percentile(d[k], 2.5), np.percentile(d[k], 97.5)],
                "p_two_sided_bootstrap": min(1.0, 2.0 * min(np.mean(d[k] <= 0), np.mean(d[k] >= 0)))} for k, f in stats.items()}


class Checker:
    def __init__(self):
        self.n, self.worst, self.fail = 0, 0.0, []

    def num(self, name, mine, theirs, tol=TOL):
        if isinstance(mine, (list, tuple)):
            for i, (a, b) in enumerate(zip(mine, theirs)):
                self.num(f"{name}[{i}]", a, b, tol)
            return
        self.n += 1
        if mine is None or theirs is None:
            if mine is not theirs:
                self.fail.append(f"{name}: {mine} vs {theirs}")
            return
        d = abs(float(mine) - float(theirs))
        self.worst = max(self.worst, d)
        if not d <= tol:
            self.fail.append(f"{name}: {mine} vs {theirs} (diff {d:.3g})")

    def true(self, name, cond):
        self.n += 1
        if not cond:
            self.fail.append(name)


def main() -> int:
    rep = json.loads((OUT / "signal_value_v1.json").read_text())
    cfg = json.loads((ROOT / "native_backtest/config/framework_config_v1.json").read_text())
    mcfg = cfg["metrics"]
    P = {"delta": mcfg["cer_delta"], "block": mcfg["bootstrap_block_months"], "reps": mcfg["bootstrap_reps"], "seed": mcfg["bootstrap_seed"]}
    C = Checker()
    # the frozen definitions this check states independently
    for s in NO_SIGNAL:
        C.true(f"{s} no-signal weights are the frozen native neutral weights", cfg["systems"][s]["native_neutral_weights"] == NO_SIGNAL[s])
    C.true("frozen bootstrap settings", (P["block"], P["reps"], P["seed"], P["delta"]) == (6, 5000, 20261027, 2.5))
    C.true("frozen cost", cfg["costs"]["cost_per_dollar_traded"] == A.COST)

    prices = {a: A.load_close(a) for a in ("SPY", "IEF", "LQD", "TLT")}
    cal, dtb = A.calendar(prices), A.load_dtb4wk()
    months = [str(p) for p in pd.period_range(A.DEV[0], A.DEV[1], freq="M")]
    C.true("months", rep["months"] == [months[0], months[-1], len(months)])
    recs = {s: A.read_weights(s) for s in NO_SIGNAL}
    sims = {}
    for s in NO_SIGNAL:
        on_w = {m: {a: float(recs[s][m]["target_weights"][a]) for a in UNIVERSE[s]} for m in months}
        C.true(f"{s} universe unchanged in every record", all(list(recs[s][m]["universe"]) == UNIVERSE[s] for m in months))
        sims[f"{s}_ON"] = A.simulate(on_w, months, prices, cal, dtb)
        sims[f"{s}_OFF"] = A.simulate({m: dict(NO_SIGNAL[s]) for m in months}, months, prices, cal, dtb)
        w, bh = np.array(list(NO_SIGNAL[s].values())), {}
        for m in months:
            bh[m] = dict(zip(NO_SIGNAL[s], w))
            _, entry, exit_ = A.dates_for(m, cal)
            g = w * np.array([prices[a][exit_] / prices[a][entry] for a in NO_SIGNAL[s]])
            w = g / g.sum()
        sims[f"{s}_BH"] = A.simulate(bh, months, prices, cal, dtb)
    for k, w in HYBRID.items():
        sims[k] = A.simulate({m: dict(w) for m in months}, months, prices, cal, dtb)
    for s in NO_SIGNAL:   # execution, pricing, cash and cost conventions shared by each pair
        on, off = sims[f"{s}_ON"], sims[f"{s}_OFF"]
        C.true(f"{s} same dates", (on[["month", "decision_date", "entry", "exit"]].values == off[["month", "decision_date", "entry", "exit"]].values).all())
        C.num(f"{s} same cash", float((on["rf"] - off["rf"]).abs().max()), 0.0)
        C.num(f"{s} same asset returns", max(float((on[f"r_{a}"] - off[f"r_{a}"]).abs().max()) for a in UNIVERSE[s]), 0.0)
        C.num(f"{s} cost = 5 bp x traded", float((on["cost"] - A.COST * on["traded"]).abs().max()) + float((off["cost"] - A.COST * off["traded"]).abs().max()), 0.0)
        C.num(f"{s} no-signal starts from cash", float(off["traded"].iloc[0]), 1.0)
        C.true(f"{s} no-signal weights never tilt", all((off[f"w_{a}"] == NO_SIGNAL[s][a]).all() for a in UNIVERSE[s]))
        C.true(f"{s} signals change the weights", any((on[f"w_{a}"] != off[f"w_{a}"]).any() for a in UNIVERSE[s]))

    # monthly series in the analysis's CSV
    mon = pd.read_csv(OUT / "monthly_v1.csv", dtype={"decision_month": str})
    names = {"AP1_ON": "AP1_ON", "AP1_OFF": "AP1_OFF", "AP2B_ON": "AP2B_ON", "AP2B_OFF": "AP2B_OFF", "AP1_BH": "AP1_OFF_BUY_AND_HOLD",
             "AP2B_BH": "AP2B_OFF_BUY_AND_HOLD", "JEV_STOCKS_DET_BONDS": "JEV_STOCKS_DET_BONDS", "DET_STOCKS_JEV_BONDS": "DET_STOCKS_JEV_BONDS"}
    for mine, theirs in names.items():
        C.num(f"monthly net {theirs}", float(np.abs(sims[mine]["net"].to_numpy() - mon[f"{theirs}__net_total_return"].to_numpy()).max()), 0.0, 1e-11)

    # metrics and incremental contrasts
    keymap = {"net_cer": "cer", "net_annualized_excess_return": "ann_excess_return", "cumulative_return": "cumulative_return", "net_sharpe": "sharpe",
              "max_drawdown": "max_drawdown", "annualized_volatility": "volatility", "annualized_one_way_turnover": "turnover", "total_cost": "total_cost"}
    x = {k: v["excess"].to_numpy(float) for k, v in sims.items()}
    g = {k: (v["gross"] - v["rf"]).to_numpy(float) for k, v in sims.items()}
    for s in NO_SIGNAL:
        on, off = sims[f"{s}_ON"], sims[f"{s}_OFF"]
        mo, mf = A.metrics(on), A.metrics(off)
        R = rep["systems"][s]
        for k, mk in keymap.items():
            C.num(f"{s} with {k}", mo[mk], R["with_signals"][k])
            C.num(f"{s} without {k}", mf[mk], R["without_signals"][k])
            C.num(f"{s} difference {k}", mo[mk] - mf[mk], R["incremental"]["differences_with_minus_without"][k])
        a = x[f"{s}_ON"] - x[f"{s}_OFF"]
        te = math.sqrt(12) * a.std(ddof=1)
        C.num(f"{s} tracking error", te, R["incremental"]["tracking_error_annualised"])
        C.num(f"{s} mean active", 12 * a.mean(), R["incremental"]["mean_active_return_annualised"])
        C.num(f"{s} information ratio", 12 * a.mean() / te, R["incremental"]["information_ratio"])
        C.num(f"{s} active months positive", int((a > 0).sum()), R["incremental"]["months_active_positive"])
        b = bootstrap({"on": x[f"{s}_ON"], "off": x[f"{s}_OFF"]}, {"d": lambda c: c["on"] - c["off"]}, P)["d"]
        for k in ("ci90", "ci95", "p_two_sided_bootstrap"):
            C.num(f"{s} incremental {k}", b[k], R["incremental"][k])
        C.num(f"{s} incremental point", b["point"], R["incremental"]["net_cer_difference"])

    D1, D0, J1, J0, HE, HB = "AP1_ON", "AP1_OFF", "AP2B_ON", "AP2B_OFF", "JEV_STOCKS_DET_BONDS", "DET_STOCKS_JEV_BONDS"
    stats = {"q1_deterministic_signals_vs_own_no_signal": lambda c: c[D1] - c[D0],
             "q2_jev_signals_vs_own_no_signal": lambda c: c[J1] - c[J0],
             "q3_jev_vs_deterministic_after_allocation": lambda c: (c[J1] - c[J0]) - (c[D1] - c[D0]),
             "jev_minus_deterministic_total": lambda c: c[J1] - c[D1],
             "no_signal_mix_difference": lambda c: c[J0] - c[D0],
             "mix_stock_weight_net": lambda c: 0.5 * ((c[HE] - c[D0]) + (c[J0] - c[HB])),
             "mix_bond_sleeve_net": lambda c: 0.5 * ((c[HB] - c[D0]) + (c[J0] - c[HE]))}
    qb = bootstrap({k: x[k] for k in (D1, D0, J1, J0, HE, HB)}, stats, P)
    for k in stats:
        for f in ("point", "ci90", "ci95", "p_two_sided_bootstrap"):
            C.num(f"question {k} {f}", qb[k][f], rep["questions"][k][f])

    # attribution identities
    dl = P["delta"]
    att = rep["attribution_net_cer"]
    total = cer(x[J1], dl) - cer(x[D1], dl)
    C.num("attribution total", total, att["total_net_cer_difference"])
    sh = lambda v, a, b: 0.5 * ((cer(v[a], dl) - cer(v[D0], dl)) + (cer(v[J0], dl) - cer(v[b], dl)))
    stand = {s: (lambda t: 12 * t.mean() - 6 * dl * t.var(ddof=1))(g[f"{s}_ON"] - g[f"{s}_OFF"]) for s in NO_SIGNAL}
    inter = {s: -12 * dl * np.cov(g[f"{s}_OFF"], g[f"{s}_ON"] - g[f"{s}_OFF"], ddof=1)[0, 1] for s in NO_SIGNAL}
    four = {"1a_mix_stock_weight_before_costs": sh(g, HE, HB), "1b_mix_bond_sleeve_before_costs": sh(g, HB, HE),
            "2a_jev_tilts_before_costs": stand["AP2B"], "2b_minus_deterministic_tilts_before_costs": -stand["AP1"],
            "3_trading_costs": (cer(x[J1], dl) - cer(g[J1], dl)) - (cer(x[D1], dl) - cer(g[D1], dl)),
            "4_interaction_tilts_with_mix": inter["AP2B"] - inter["AP1"]}
    for k, v in four.items():
        C.num(f"attribution {k}", v, att["four_parts"][k])
    C.num("four parts add up to the total", sum(four.values()), total)
    two = {"mix_stock_weight_net": sh(x, HE, HB), "mix_bond_sleeve_net": sh(x, HB, HE),
           "jev_signal_value": cer(x[J1], dl) - cer(x[J0], dl), "minus_deterministic_signal_value": -(cer(x[D1], dl) - cer(x[D0], dl))}
    for k, v in two.items():
        C.num(f"attribution 2x2 {k}", v, att["two_by_two"][k])
    C.num("2x2 parts add up to the total", sum(two.values()), total)
    ra = rep["attribution_mean_return"]
    r = {a: next(sims[k][f"r_{a}"].to_numpy() for k in sims if f"r_{a}" in sims[k]) for a in ("SPY", "IEF", "LQD", "TLT")}
    bd = (35 * r["IEF"] + 20 * r["LQD"]) / 55
    parts = {"mix_stock_weight": 0.15 * (r["SPY"] - bd), "mix_bond_sleeve": 0.40 * (r["TLT"] - bd),
             "jev_tilts": sims[J1]["gross"].to_numpy() - sims[J0]["gross"].to_numpy(), "minus_deterministic_tilts": -(sims[D1]["gross"].to_numpy() - sims[D0]["gross"].to_numpy()),
             "trading_costs": -(sims[J1]["cost"].to_numpy() - sims[D1]["cost"].to_numpy())}
    for k, v in parts.items():
        C.num(f"return attribution {k}", 12 * v.mean(), ra["parts_annualised"][k])
    C.num("return attribution adds up month by month", float(np.abs(x[J1] - x[D1] - sum(parts.values())).max()), 0.0)

    # decisions
    dec = rep["decisions"]
    for s in NO_SIGNAL:
        on = sims[f"{s}_ON"]
        tilt = pd.DataFrame({a: on[f"w_{a}"] - NO_SIGNAL[s][a] for a in UNIVERSE[s]})
        spy = tilt["SPY"].to_numpy()
        C.num(f"{s} one-way tilt mean", float((0.5 * tilt.abs().sum(axis=1)).mean()), dec[s]["one_way_tilt_mean"])
        C.num(f"{s} SPY tilt sd", float(spy.std(ddof=1)), dec[s]["spy_tilt"]["sd"])
        sg = np.sign(spy[np.abs(spy) > 1e-12])
        C.num(f"{s} direction changes", int((sg[1:] != sg[:-1]).sum()), dec[s]["spy_tilt_direction_changes"])
        t = sims[f"{s}_ON"]["gross"].to_numpy() - sims[f"{s}_OFF"]["gross"].to_numpy()
        C.num(f"{s} tilt hit rate", float((t > 0).mean()), dec[s]["tilt_hit_rate_before_costs"])
        C.num(f"{s} tilt return", 12 * t.mean(), dec[s]["tilt_return_before_costs_annualised"])
        W, Rm = on[[f"w_{a}" for a in UNIVERSE[s]]].to_numpy(), np.column_stack([r[a] for a in UNIVERSE[s]])
        wbar, w0 = W.mean(axis=0), np.array([NO_SIGNAL[s][a] for a in UNIVERSE[s]])
        C.num(f"{s} average-tilt return", 12 * float((Rm @ (wbar - w0)).mean()), dec[s]["average_tilt_vs_timing_ex_post"]["average_tilt_return_annualised"])
        C.num(f"{s} timing return", 12 * float(((W - wbar) * Rm).sum(axis=1).mean()), dec[s]["average_tilt_vs_timing_ex_post"]["timing_return_annualised"])

    # regimes (volatility known at the decision close)
    lr = np.log(prices["SPY"].reindex(cal)).diff()
    vol = []
    for m in months:
        day = A.dates_for(m, cal)[0]
        vol.append(float(lr.loc[:day].iloc[-63:].std(ddof=1) * math.sqrt(252)))
    C.num("ex-ante volatility", float(np.abs(np.array(vol) - mon["spy_vol_63d_at_decision"].to_numpy()).max()), 0.0, 1e-11)
    high = np.array(vol) >= 0.20
    for s in NO_SIGNAL:
        a = x[f"{s}_ON"] - x[f"{s}_OFF"]
        rg = rep["regimes"][s]
        C.num(f"{s} high-volatility active sum", float(a[high].sum()), rg["volatility_at_decision"]["high (20%+ a year)"]["active_return_sum"])
        for y in ("2019", "2020", "2021", "2022"):
            sel = np.array([m.startswith(y) for m in months])
            C.num(f"{s} {y} active sum", float(a[sel].sum()), rg["year"][y]["active_return_sum"])

    # leave-one-month-out influence
    for s, (on, off) in {k: (f"{k}_ON", f"{k}_OFF") for k in NO_SIGNAL}.items():
        loo = [cer(np.delete(x[on], i), dl) - cer(np.delete(x[off], i), dl) for i in range(len(months))]
        inf = rep["influence_leave_one_month_out"][s]
        C.num(f"{s} leave-one-out range", [min(loo), max(loo)], [inf["leave_one_out_min"], inf["leave_one_out_max"]])
        C.true(f"{s} most influential month", months[int(np.argmax(np.abs(np.array(loo) - inf["full"])))] == inf["most_influential_month"])

    # sensitivities
    sens = rep["sensitivities"]
    for s in NO_SIGNAL:
        bh = sens["buy_and_hold_no_signal"][s]
        C.num(f"{s} buy-and-hold CER", cer(x[f"{s}_BH"], dl), bh["net_cer_without_buy_and_hold"])
        b = bootstrap({"on": x[f"{s}_ON"], "bh": x[f"{s}_BH"]}, {"d": lambda c: c["on"] - c["bh"]}, P)["d"]
        C.num(f"{s} buy-and-hold incremental", [b["point"], *b["ci95"], b["p_two_sided_bootstrap"]],
              [bh["incremental"]["net_cer_difference"], *bh["incremental"]["ci95"], bh["incremental"]["p_two_sided_bootstrap"]])
    s2 = pd.read_csv(ROOT / "stage2/results/dev_rerun_v4_portfolio_2026-10-27/stage2_portfolio_returns.csv", dtype={"decision_month": str})
    for strat, k in (("A", D1), ("BENCH_STATIC_45_35_20", D0)):
        v = s2[s2["strategy"] == strat].sort_values("decision_month")
        C.true(f"Stage 2 {strat} months", v["decision_month"].tolist() == months)
        C.num(f"Stage 2 {strat} net returns", float(np.abs(v["net_total_return"].to_numpy() - sims[k]["net"].to_numpy()).max()), 0.0, 1e-12)
    eng = json.loads((ROOT / sens["jev_native_engine"]["engine_output"]).read_text())
    rows = pd.DataFrame(eng["rows"])
    C.true("native engine never stepped past the development window", rows["as_of"].max() <= "2022-12-30")
    C.num("native: tilt switched off gives 60% SPY", float((rows["w_off"] - 0.6).abs().max()), 0.0, 1e-12)
    C.num("native: signal-on weights are the decision records", max(abs(r_["w_on"] - recs["AP2B"][r_["as_of"][:7]]["target_weights"]["SPY"]) for r_ in eng["rows"]), 0.0)
    net = {k: rows[f"nav_{k}"] / rows[f"nav_{k}"].shift(1, fill_value=1.0) - 1.0 for k in ("on", "off")}
    sel = rows["as_of"].str[:7].isin(months).to_numpy()
    xn = {k: (net[k] - rows["rf_month"]).to_numpy()[sel] for k in net}
    b = bootstrap(xn, {"d": lambda c: c["on"] - c["off"]}, P)["d"]
    jn = sens["jev_native_engine"]
    C.num("native JEV with/without CER", [cer(xn["on"], dl), cer(xn["off"], dl)], [jn["net_cer_with"], jn["net_cer_without"]])
    C.num("native JEV incremental", [b["point"], *b["ci95"], b["p_two_sided_bootstrap"]],
          [jn["incremental"]["net_cer_difference"], *jn["incremental"]["ci95"], jn["incremental"]["p_two_sided_bootstrap"]])

    out = {"checks": C.n, "largest_difference": C.worst, "tolerance": TOL, "failures": C.fail,
           "imports": "numpy, pandas and native_backtest.scripts.audit_portfolio_integrity only (no framework, metrics or Stage 2 code)"}
    (OUT / "independent_check_v1.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "failures"}, indent=1), "\nfailures:", C.fail[:20])
    return 0 if not C.fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
