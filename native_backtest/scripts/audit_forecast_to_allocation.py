#!/usr/bin/env python3
"""Independent audit of the Forecast-to-Allocation Sensitivity Experiment.

A deliberately separate rebuild. It imports neither the experiment script nor the evaluation framework: only
numpy, pandas and the committed result files. Everything it checks it recomputes from first principles - the
portfolio accounting, the metrics, the bootstrap, the transformation algebra, the attenuation ratios and the
reproduction of the archived 1x series - and compares with what the experiment published.

Usage (repository root): python -m native_backtest.scripts.audit_forecast_to_allocation
"""
from __future__ import annotations

import itertools
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "native_backtest/out/sensitivity"
REPORT = OUT / "forecast_to_allocation_sensitivity.json"
PREREG = ROOT / "native_backtest/config/forecast_to_allocation_sensitivity_preregistration_v1.json"
STAGE2_RUN = ROOT / "stage2/results/dev_rerun_v4_portfolio_2026-10-27"
DEC = ROOT / "native_backtest/out/decisions"
AUDITED: list = []
ASSETS = {"AP1": ("SPY", "IEF", "LQD"), "AP2B": ("SPY", "TLT"), "AP2A": ("SPY", "TLT"),
          "AP3": ("SPY", "IEF", "LQD")}
SCEN = ("0x", "0.5x", "1x", "2x")
TOL = 1e-9
checks: list = []


def ok(name: str, passed: bool, detail=None) -> None:
    checks.append({"check": name, "pass": bool(passed), "detail": detail})


def close(name: str, a: float, b: float, tol: float = TOL) -> None:
    d = abs(float(a) - float(b))
    ok(name, d <= tol, {"mine": float(a), "published": float(b), "abs_difference": d, "tolerance": tol})


# ------------------------------------------------------------------------------- accounting, rebuilt from scratch
PRICE_FILES = {   # post-2018 segments: every development entry and exit date is on or after 2019-04-01
    "SPY": "stage2/data/_pinned/market_price_SPY_2018plus.tsv",
    "IEF": "stage2/data/_pinned/market_price_IEF_2018plus.tsv",
    "LQD": "stage2/data/_pinned/market_price_LQD_2018plus.tsv",
    "TLT": "stage2/data/_pinned/market_price_TLT_2018plus.tsv",
}
DTB4WK = "stage2/data/risk_free/DTB4WK_combined_2001-07-31_to_2026-10-01.csv"


def load_prices() -> dict:
    out = {}
    for a, rel in PRICE_FILES.items():
        df = pd.read_csv(ROOT / rel, sep="\t")
        out[a] = pd.Series(pd.to_numeric(df["Close"], errors="raise").to_numpy(float),
                           index=pd.to_datetime(df["Date"]).dt.normalize()).sort_index()
    return out


def load_rf() -> pd.Series:
    df = pd.read_csv(ROOT / DTB4WK)
    v = pd.to_numeric(df.iloc[:, 1], errors="coerce")
    return pd.Series(v.to_numpy(float), index=pd.to_datetime(df.iloc[:, 0])).dropna().sort_index()


def rf_return(dtb: pd.Series, entry: pd.Timestamp, exit_: pd.Timestamp) -> float:
    q = dtb[dtb.index <= entry]
    d = q.iloc[-1] / 100.0 * 28.0 / 360.0
    r28 = d / (1.0 - d)
    return float((1.0 + r28) ** ((exit_ - entry).days / 28.0) - 1.0)


def rebuild_accounting(df: pd.DataFrame, assets, prices: dict, dtb: pd.Series) -> pd.DataFrame:
    """A full independent simulation: the published target weights, the pinned adjusted closes on the published
    entry and exit dates, drift between rebalances, start from cash, 5 bp per dollar traded."""
    rows, pre = [], np.zeros(len(assets))
    for r in df.itertuples():
        w = np.array([getattr(r, f"w_{a}") for a in assets], float)
        entry, exit_ = pd.Timestamp(r.entry_date), pd.Timestamp(r.exit_date)
        ret = np.array([prices[a][exit_] / prices[a][entry] - 1.0 for a in assets])
        traded = float(np.abs(w - pre).sum())
        cost = 0.0005 * traded
        gross = float(w @ ret)
        rf = rf_return(dtb, entry, exit_)
        rows.append({"decision_month": r.decision_month, "traded_notional": traded, "cost": cost,
                     "one_way_turnover": 0.5 * traded, "gross_total_return": gross, "rf_return": rf,
                     "net_total_return": gross - cost, "net_excess_return": gross - cost - rf,
                     **{f"pretrade_w_{a}": pre[i] for i, a in enumerate(assets)}})
        g = w * (1.0 + ret)
        pre = g / g.sum()
    return pd.DataFrame(rows)


def cer(x: np.ndarray, delta: float = 2.5) -> float:
    return float(12.0 * (x.mean() - 0.5 * delta * x.var(ddof=1)))


def block_indices(T: int, block: int, rng) -> np.ndarray:
    idx = []
    while len(idx) < T:
        s = int(rng.integers(0, T))
        idx.extend(((s + k) % T) for k in range(block))
    return np.array(idx[:T])


def paired_cer_difference(a: np.ndarray, b: np.ndarray, block: int, reps: int, seed: int, delta: float) -> dict:
    rng = np.random.default_rng(seed)
    d = np.empty(reps)
    for i in range(reps):
        idx = block_indices(len(a), block, rng)
        d[i] = cer(a[idx], delta) - cer(b[idx], delta)
    return {"point": cer(a, delta) - cer(b, delta),
            "ci95": [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))],
            "p": float(min(1.0, 2.0 * min(np.mean(d <= 0.0), np.mean(d >= 0.0))))}


# -------------------------------------------------------------------------------------------------------- audits
def audit_accounting(system: str, rep: dict) -> None:
    assets = ASSETS[system]
    ret = pd.read_csv(OUT / f"{system.lower()}_scenario_returns.csv")
    for s in SCEN:
        g = ret[ret["scenario"] == s].reset_index(drop=True)
        ok(f"{system} {s}: 46 development months", len(g) == 46, {"n": len(g)})
        ok(f"{system} {s}: weights sum to one every month",
           bool(np.allclose(g[[f"w_{a}" for a in assets]].sum(axis=1), 1.0, atol=1e-12)))
        ok(f"{system} {s}: first month trades from cash",
           bool(np.allclose(g.loc[0, [f"pretrade_w_{a}" for a in assets]].to_numpy(float), 0.0)))
        mine = rebuild_accounting(g, assets, PRICES, DTB)
        close(f"{system} {s}: total transaction cost rebuilt", mine["cost"].sum(), g["cost"].sum())
        close(f"{system} {s}: one-way turnover rebuilt", mine["one_way_turnover"].mean(), g["one_way_turnover"].mean())
        close(f"{system} {s}: gross total return rebuilt from the pinned closes",
              float(np.abs(mine["gross_total_return"].to_numpy(float) - g["gross_total_return"].to_numpy(float)).max()), 0.0, 1e-12)
        close(f"{system} {s}: cash return rebuilt from the pinned bill series",
              float(np.abs(mine["rf_return"].to_numpy(float) - g["rf_return"].to_numpy(float)).max()), 0.0, 1e-12)
        close(f"{system} {s}: net excess return rebuilt end to end",
              float(np.abs(mine["net_excess_return"].to_numpy(float) - g["net_excess_return"].to_numpy(float)).max()), 0.0, 1e-12)
        close(f"{system} {s}: drifted pre-trade weights rebuilt",
              float(np.abs(mine[[f"pretrade_w_{a}" for a in assets]].to_numpy(float)
                           - g[[f"pretrade_w_{a}" for a in assets]].to_numpy(float)).max()), 0.0, 1e-12)
        close(f"{system} {s}: net excess = gross excess - cost",
              float(np.abs(g["net_excess_return"] - (g["gross_excess_return"] - g["cost"])).max()), 0.0)
        pub = rep["approaches"][system]["performance"]["by_scenario"][s]
        x = g["net_excess_return"].to_numpy(float)
        close(f"{system} {s}: net CER", cer(x), pub["net_cer"])
        close(f"{system} {s}: annualised volatility", math.sqrt(12.0) * x.std(ddof=1), pub["annualized_volatility"])
        close(f"{system} {s}: annualised net excess return", 12.0 * x.mean(), pub["net_annualized_excess_return"])
        close(f"{system} {s}: annualised one-way turnover", 12.0 * g["one_way_turnover"].mean(), pub["annualized_one_way_turnover"])
        w = np.concatenate([[1.0], np.cumprod(1.0 + g["net_total_return"].to_numpy(float))])
        close(f"{system} {s}: maximum drawdown", float((w / np.maximum.accumulate(w) - 1.0).min()), pub["max_drawdown"])


def audit_transformation(system: str, rep: dict) -> None:
    t = pd.read_csv(OUT / f"{system.lower()}_transmission_trace.csv")
    assets = ASSETS[system]
    by = {s: t[t["scenario"] == s].sort_values("decision_month").reset_index(drop=True) for s in SCEN}
    if system == "AP2B":
        # offset(lambda) = lambda x offset, and edge = baseEdge + confidence x offset(lambda)
        for s, lam in (("0x", 0.0), ("0.5x", 0.5), ("1x", 1.0), ("2x", 2.0)):
            g = by[s]
            want = lam * g["offset_original"].to_numpy(float) * g["confidence"].to_numpy(float)
            close(f"AP2B {s}: signal-induced edge = lambda x confidence x offset",
                  float(np.abs(g["weighted_offset"].to_numpy(float) - want).max()), 0.0, 1e-12)
            close(f"AP2B {s}: edge = equilibrium edge + signal part",
                  float(np.abs(g["edge"].to_numpy(float) - (g["base_edge"].to_numpy(float) + want)).max()), 0.0, 1e-12)
    else:
        for s, lam in (("0x", 0.0), ("0.5x", 0.5), ("1x", 1.0), ("2x", 2.0)):
            g = by[s]
            pi = g[[f"pi_{a}" for a in assets]].to_numpy(float)
            q0 = by["1x"][[f"q_adj_{a}" for a in assets]].to_numpy(float)
            want = pi + lam * (q0 - pi)
            close(f"{system} {s}: adjusted view = prior + lambda x (original - prior)",
                  float(np.abs(g[[f"q_adj_{a}" for a in assets]].to_numpy(float) - want).max()), 0.0, 1e-12)
        close(f"{system} 1x: adjusted view equals the original model view",
              float(np.abs(by["1x"][[f"q_adj_{a}" for a in assets]].to_numpy(float)
                           - by["1x"][[f"q_orig_{a}" for a in assets]].to_numpy(float)).max()), 0.0, 1e-12)
        close(f"{system} 0x: adjusted view equals the allocator's own prior",
              float(np.abs(by["0x"][[f"q_adj_{a}" for a in assets]].to_numpy(float)
                           - by["0x"][[f"pi_{a}" for a in assets]].to_numpy(float)).max()), 0.0, 1e-15)
    # constraints hold in every scenario
    bounds = rep["approaches"][system]["allocator"]["bounds"]
    for s in SCEN:
        g = by[s]
        inside = all(bool(((g[f"w_{a}"] >= lo - 1e-9) & (g[f"w_{a}"] <= hi + 1e-9)).all()) for a, (lo, hi) in bounds.items())
        ok(f"{system} {s}: every weight inside the native position limits", inside, {"bounds": bounds})
    # no decision uses a future observation: the trace carries no outcome column at all
    forbidden = [c for c in t.columns if c in ("r_spy", "r_tlt", "actual_excess_return", "next", "gross_total_return")]
    ok(f"{system}: the decision trace carries no realised-return column", not forbidden, {"found": forbidden})


def audit_attenuation(system: str, rep: dict) -> None:
    t = pd.read_csv(OUT / f"{system.lower()}_transmission_trace.csv")
    assets = ASSETS[system]
    by = {s: t[t["scenario"] == s].sort_values("decision_month").reset_index(drop=True) for s in SCEN}
    pub = rep["approaches"][system]["transmission"]["per_scenario_vs_1x"]
    for s in SCEN:
        g, b = by[s], by["1x"]
        if system == "AP1":
            du = np.abs(g[[f"w_unconstrained_{a}" for a in assets]].to_numpy(float)
                        - b[[f"w_unconstrained_{a}" for a in assets]].to_numpy(float)).max(axis=1)
            dw = np.abs(g[[f"w_{a}" for a in assets]].to_numpy(float) - b[[f"w_{a}" for a in assets]].to_numpy(float)).max(axis=1)
        else:
            du = np.abs(g["w_unconstrained_SPY"].to_numpy(float) - b["w_unconstrained_SPY"].to_numpy(float))
            dw = np.abs(g["w_SPY"].to_numpy(float) - b["w_SPY"].to_numpy(float))
        close(f"{system} {s}: mean intermediate weight change", du.mean(), pub[s]["mean_abs_intermediate_weight_change_vs_1x"])
        close(f"{system} {s}: mean final weight change", dw.mean(), pub[s]["mean_abs_final_weight_change_vs_1x"])
        m = du >= 1e-6
        ok(f"{system} {s}: months below the ratio floor are counted, not divided",
           int((~m).sum()) == pub[s]["months_below_ratio_floor_not_divided"],
           {"mine": int((~m).sum()), "published": pub[s]["months_below_ratio_floor_not_divided"]})
        if m.any():
            close(f"{system} {s}: mean constraint attenuation share", float((1.0 - dw[m] / du[m]).mean()),
                  pub[s]["mean_constraint_attenuation_share"])
        binding = int((g["n_bounds_binding"] > 0).sum())
        ok(f"{system} {s}: months with a binding bound", binding == pub[s]["months_with_any_binding_bound"],
           {"mine": binding, "published": pub[s]["months_with_any_binding_bound"]})
    vp = rep["approaches"][system]["view_pipeline"]
    if system != "AP2B":
        g = by["1x"]
        pi = g[[f"pi_{a}" for a in assets]].to_numpy(float)
        dq = np.abs(g[[f"q_adj_{a}" for a in assets]].to_numpy(float) - pi).mean(axis=1)
        dm = np.abs(g[[f"mu_bl_{a}" for a in assets]].to_numpy(float) - pi).mean(axis=1)
        close(f"{system}: mean view minus prior, basis points", 1e4 * dq.mean(), vp["mean_abs_view_minus_prior_bp"])
        close(f"{system}: share of the view the posterior keeps", float((dm / dq).mean()),
              vp["mean_share_of_the_view_the_posterior_keeps"])
    else:
        g = by["1x"]
        close("AP2B: mean confidence-weighted offset", float(np.abs(g["weighted_offset"]).mean()),
              vp["stage_3_mean_abs_confidence_weighted_offset_points"])
        close("AP2B: signal as a share of the equilibrium edge",
              float(np.abs(g["weighted_offset"]).mean() / np.abs(g["base_edge"]).mean()),
              vp["signal_as_share_of_equilibrium_edge"])


def audit_reproduction(rep: dict) -> None:
    # Deterministic: the 1x weights and net excess returns against the archived Stage 2 development run
    arch_w = pd.read_csv(STAGE2_RUN / "stage2_portfolio_bl_diagnostics.csv").query("strategy == 'A'").set_index("decision_month")
    arch_r = pd.read_csv(STAGE2_RUN / "stage2_portfolio_returns.csv").query("strategy == 'A'").set_index("decision_month")
    t = pd.read_csv(OUT / "ap1_transmission_trace.csv").query("scenario == '1x'").set_index("decision_month")
    months = sorted(t.index)
    dw = max(abs(t.loc[m, f"w_{a}"] - arch_w.loc[m, f"w_{a}"]) for m in months for a in ASSETS["AP1"])
    ok("AP1 1x reproduces the archived Stage 2 weights", dw <= 1e-10, {"max_abs_difference": float(dw)})
    r = pd.read_csv(OUT / "ap1_scenario_returns.csv").query("scenario == '1x'").set_index("decision_month")
    dr = max(abs(r.loc[m, "net_excess_return"] - arch_r.loc[m, "net_excess_return"]) for m in months)
    ok("AP1 1x reproduces the archived Stage 2 net excess returns", dr <= 1e-10, {"max_abs_difference": float(dr)})
    # the two Agentic Workflow engines: the 1x weights against the archived decision records
    for system in ("AP2B", "AP2A"):
        recs = {}
        for line in (DEC / f"{system}.jsonl").read_text().splitlines():
            if line.strip():
                j = json.loads(line)
                recs[j["decision_month"]] = j["target_weights"]
        t = pd.read_csv(OUT / f"{system.lower()}_transmission_trace.csv").query("scenario == '1x'").set_index("decision_month")
        d = max(abs(t.loc[m, "w_SPY"] - recs[m]["SPY"]) for m in t.index)
        ok(f"{system} 1x reproduces the archived decision weights", d <= 1e-10, {"max_abs_difference": float(d)})


def audit_zero_scenario(rep: dict) -> None:
    pre = json.loads(PREREG.read_text())
    cfg = json.loads((ROOT / "native_backtest/config/framework_config_v1.json").read_text())
    for system in AUDITED:
        # the pre-registered definition is the frozen config's own native_neutral_weights; the per-system entries
        # are a convenience listing, so a system without one (AP3) still has a pre-registered control.
        listed = pre["no_signal_controls"].get(system)
        neutral = listed["weights"] if listed else cfg["systems"][system]["native_neutral_weights"]
        if listed:
            assert listed["weights"] == cfg["systems"][system]["native_neutral_weights"], system
        t = pd.read_csv(OUT / f"{system.lower()}_transmission_trace.csv").query("scenario == '0x'")
        d = max(abs(t[f"w_{a}"] - w).max() for a, w in neutral.items())
        pubz = rep["approaches"][system]["zero_scenario_checks"]
        # A Black-Litterman allocator at lambda = 0 sits NEAR its neutral portfolio but not exactly on it: the
        # optimizer maximises against Sigma + M while pi was defined as delta Sigma w_eq. That was pre-registered
        # for AP1 and is a property of the allocator, so AP3 - the other BL allocator - is held to the same
        # expectation. The capped-tilt allocators have no posterior step and do land on their control exactly.
        if "vs_native_neutral_static_weights" in pubz:
            close(f"{system} 0x: distance from the static control",
                  float(d), pubz["vs_native_neutral_static_weights"]["max_abs_weight_difference"])
            ok(f"{system} 0x: differs from the static control by the documented Sigma + M effect, as pre-registered",
               1e-6 < float(d) < 0.05, {"max_abs_difference": float(d)})
            ok(f"{system} 0x: that difference is documented, not assumed away",
               "Sigma + M" in pubz["vs_native_neutral_static_weights"]["why"].replace("\u03a3", "Sigma"))
        else:
            ok(f"{system} 0x: equals the native no-signal control exactly", float(d) <= 1e-9, {"max_abs_difference": float(d)})
    # and the 0x scenario carries no signal at all
    for system in [k for k in ("AP1", "AP2A", "AP3") if k in AUDITED]:
        t = pd.read_csv(OUT / f"{system.lower()}_transmission_trace.csv").query("scenario == '0x'")
        a = ASSETS[system]
        d = float(np.abs(t[[f"q_adj_{x}" for x in a]].to_numpy(float) - t[[f"pi_{x}" for x in a]].to_numpy(float)).max())
        ok(f"{system} 0x: the adjusted view is exactly the allocator's prior", d <= 1e-15, {"max_abs_difference": d})
    t = pd.read_csv(OUT / "ap2b_transmission_trace.csv").query("scenario == '0x'")
    ok("AP2B 0x: the signal-induced edge is exactly zero",
       float(np.abs(t["weighted_offset"]).max()) == 0.0, {"max_abs": float(np.abs(t["weighted_offset"]).max())})


def audit_statistics(rep: dict) -> None:
    m = json.loads((ROOT / "native_backtest/config/framework_config_v1.json").read_text())["metrics"]
    for system in AUDITED:
        ret = pd.read_csv(OUT / f"{system.lower()}_scenario_returns.csv")
        s = lambda k: ret[ret["scenario"] == k].sort_values("decision_month")["net_excess_return"].to_numpy(float)
        st = rep["approaches"][system]["statistics"]
        for k in ("0x", "0.5x", "2x"):
            mine = paired_cer_difference(s(k), s("1x"), m["bootstrap_block_months"], m["bootstrap_reps"],
                                         m["bootstrap_seed"], m["cer_delta"])
            pub = st[f"net_cer_{k}_minus_1x"]
            close(f"{system} {k} minus 1x: net CER difference", mine["point"], pub["point"])
            close(f"{system} {k} minus 1x: 95% interval lower", mine["ci95"][0], pub["ci95"][0], 1e-6)
            close(f"{system} {k} minus 1x: 95% interval upper", mine["ci95"][1], pub["ci95"][1], 1e-6)
            close(f"{system} {k} minus 1x: bootstrap p-value", mine["p"], pub["p_two_sided_bootstrap"], 1e-6)
            ok(f"{system} {k} minus 1x: not described as statistically clear",
               not (pub["ci95"][0] > 0 or pub["ci95"][1] < 0) or pub["p_two_sided_bootstrap"] < 0.05)


def audit_cross_approach(rep: dict) -> None:
    net = {}
    for system in AUDITED:
        ret = pd.read_csv(OUT / f"{system.lower()}_scenario_returns.csv")
        net[system] = {k: ret[ret["scenario"] == k].sort_values("decision_month")["net_excess_return"].to_numpy(float)
                       for k in SCEN}
    for a, b in [(x, y) for x, y in itertools.combinations(("AP1", "AP2B", "AP2A", "AP3"), 2) if x in AUDITED and y in AUDITED]:
        pub = rep["cross_approach"]["pairwise"][f"{a}_vs_{b}"]
        close(f"{a} vs {b}: 1x monthly net return correlation",
              float(np.corrcoef(net[a]["1x"], net[b]["1x"])[0, 1]), pub["monthly_net_return_correlation_1x"])
        close(f"{a} vs {b}: 0x monthly net return correlation",
              float(np.corrcoef(net[a]["0x"], net[b]["0x"])[0, 1]), pub["monthly_net_return_correlation_0x"])
        close(f"{a} vs {b}: signal-part correlation",
              float(np.corrcoef(net[a]["1x"] - net[a]["0x"], net[b]["1x"] - net[b]["0x"])[0, 1]),
              pub["monthly_signal_part_correlation"])
    for system in AUDITED:
        pub = rep["cross_approach"]["per_approach_variance_split"][system]
        sig = net[system]["1x"] - net[system]["0x"]
        close(f"{system}: signal share of 1x variance", float(sig.var(ddof=1) / net[system]["1x"].var(ddof=1)),
              pub["signal_part_share_of_1x_variance"])


def audit_integrity(rep: dict) -> None:
    ok("the protected window is never scored",
       rep["window"]["development"][1] < rep["window"]["protected_window_start"],
       {"last_development_month": rep["window"]["development"][1], "protected_start": rep["window"]["protected_window_start"]})
    for system in AUDITED:
        for f in (f"{system.lower()}_scenario_returns.csv", f"{system.lower()}_transmission_trace.csv"):
            d = pd.read_csv(OUT / f)
            late = [m for m in d["decision_month"].astype(str).unique() if m >= rep["window"]["protected_window_start"]]
            ok(f"{f}: holds no protected month", not late, {"found": late[:5]})
    # Causal RAG may be computed now that genuine agent outputs exist, but only ever as a labelled exploratory
    # diagnostic: it must never be presented as validated while a pre-registered gate is failing.
    ap3 = rep["approaches"]["AP3"]
    if ap3["status"] == "PENDING GENUINE AGENT OUTPUTS":
        ok("Causal RAG is reported as pending, with no scenario values", "performance" not in ap3)
    else:
        ok("Causal RAG, if computed, carries the exploratory designation",
           "EXPLORATORY" in ap3["status"] and ap3.get("designation", "").startswith("EXPLORATORY"), ap3["status"])
        ok("Causal RAG is never marked validated", ap3.get("validated") is False, ap3.get("validated"))
        ok("Causal RAG records the gates it failed", bool(ap3.get("gates_failed")), ap3.get("gates_failed"))
        ok("Causal RAG gate outcomes are unchanged (still failing)",
           all(v is False for v in (ap3.get("gates") or {}).values()), ap3.get("gates"))
        ok("Causal RAG categorical assessments were never scaled",
           "never scaled" in ap3.get("categorical_note", ""), ap3.get("categorical_note"))
    ok("the pre-registration is committed and referenced",
       PREREG.exists() and rep["preregistration"]["file"].endswith("forecast_to_allocation_sensitivity_preregistration_v1.json"))
    pre = json.loads(PREREG.read_text())
    ok("the scenarios match the pre-registration",
       [float(x) for x in pre["scenarios"]["lambda_values"]] == [0.0, 0.5, 1.0, 2.0])
    ok("the result is labelled a development diagnostic", rep["status"].startswith("DEVELOPMENT DIAGNOSTIC"))


PRICES: dict = {}
DTB: pd.Series = pd.Series(dtype=float)


def main(argv=None) -> int:
    global PRICES, DTB, AUDITED
    PRICES, DTB = load_prices(), load_rf()
    rep = json.loads(REPORT.read_text())
    # every approach whose scenarios were actually computed gets the full independent rebuild
    AUDITED[:] = [k for k in ("AP1", "AP2B", "AP2A", "AP3")
                  if (OUT / f"{k.lower()}_transmission_trace.csv").exists() and "performance" in rep["approaches"].get(k, {})]
    audit_reproduction(rep)
    audit_zero_scenario(rep)
    for system in AUDITED:
        audit_accounting(system, rep)
        audit_transformation(system, rep)
        audit_attenuation(system, rep)
    audit_statistics(rep)
    audit_cross_approach(rep)
    audit_integrity(rep)
    failed = [c for c in checks if not c["pass"]]
    out = {"audit": "forecast-to-allocation sensitivity, independent rebuild",
           "imports": ["numpy", "pandas"], "n_checks": len(checks), "n_failed": len(failed),
           "verdict": "all independent checks reproduce the published numbers" if not failed else "DISCREPANCIES FOUND",
           "failed": failed, "checks": checks}
    (OUT / "audit_forecast_to_allocation.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
    print(json.dumps({k: out[k] for k in ("n_checks", "n_failed", "verdict")}, indent=1))
    for c in failed[:12]:
        print("FAILED:", c["check"], json.dumps(c["detail"], default=float)[:220])
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
