"""Score every registered plugin on the level playing field.

The scorer is the only gate: it builds each plugin's raw-signal table, refuses plugins with thin
coverage, refuses to run into the sealed window, and hands everything to level_playing_field.run.run
(same calibration, Omega, Black-Litterman, optimizer, accounting, bootstrap for all). The output is
one JSON per config and mapping, plus the registry with each plugin's coverage and status.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Dict, Iterable

import pandas as pd

from .contract import FUND_SETS, Answer, Manifest, Plugin, coverage, repo_root, to_frame, validate
from .registry import load_all

ROOT = repo_root()
sys.path.insert(0, str(ROOT))
from level_playing_field import run as lpf  # noqa: E402
from native_backtest.framework import market as mk  # noqa: E402

MIN_COVERAGE = 0.9
LPF_DIR = ROOT / "level_playing_field"


def load_config(name: str) -> dict:
    p = Path(name)
    if not p.is_absolute():
        p = LPF_DIR / name if (LPF_DIR / name).exists() else ROOT / name
    return json.loads(p.read_text(encoding="utf-8"))


def fund_set_of(cfg: dict) -> str:
    return cfg.get("fund_set") or next(k for k, v in FUND_SETS.items() if tuple(cfg["assets"]) == v)


def build_inputs(cfg: dict):
    """Market, Stage 2 spec, scored months and completed labels: identical to level_playing_field.run.main."""
    fcfg = mk.load_config()
    market = mk.load_market(fcfg)
    spec = json.loads((ROOT / fcfg["inherits_stage2_run_spec"]["path"]).read_text())
    d0, d1 = cfg["development"]
    months = mk.months_between(d0, d1)
    if months[-1] >= pd.Period("2023-01", "M"):
        raise SystemExit("refusing: development window reaches the sealed window")
    label_months = mk.months_between("2012-01", d1)
    y = {a: pd.Series({m: market.period_returns(m, [a])[a] - market.rf_return(m) for m in label_months}) for a in cfg["assets"]}
    return market, spec, months, y


def raw_tables(plugins: Dict[str, Plugin], fund_set: str, months, spec) -> tuple[Dict[str, pd.DataFrame | None], Dict[str, dict]]:
    """One raw-signal table per plugin that passes the gate, and a status line for every plugin."""
    raw: Dict[str, pd.DataFrame | None] = {}
    status: Dict[str, dict] = {}
    for name, p in plugins.items():
        m = p.manifest
        key = name.upper()
        if fund_set not in m.fund_sets:
            status[name] = {"status": "skipped", "reason": f"does not support {fund_set}"}
            continue
        ans = p.answers(fund_set)
        validate(ans, m, fund_set)
        cov = coverage(ans, months, fund_set, m)
        if cov < MIN_COVERAGE:
            status[name] = {"status": "skipped", "reason": f"coverage {cov:.0%} < {MIN_COVERAGE:.0%}", "coverage": cov}
            continue
        raw[key] = to_frame(ans, fund_set, m)
        status[name] = {"status": "scored", "key": key, "coverage": cov, "months": len(ans), "exploratory": m.exploratory,
                        "states_direction": m.states_direction, "kind": m.kind}
    if "PLACEBO" not in raw:
        raw["PLACEBO"] = None
        status.setdefault("placebo", {"status": "scored", "key": "PLACEBO", "coverage": 1.0, "kind": "placebo"})
    return raw, status


def score(config: str = "config.json", mapping: str = "sign", plugins: Iterable[str] | None = None, out_dir: Path | None = None) -> dict:
    cfg = load_config(config)
    fund_set = fund_set_of(cfg)
    market, spec, months, y = build_inputs(cfg)
    loaded = load_all(plugins)
    raw, status = raw_tables(loaded, fund_set, months, spec)
    cfg = dict(cfg)
    cfg["primary"] = [k for k in cfg["primary"] if k in raw and not loaded.get(k.lower(), _none).manifest.exploratory]
    prior_spy = cfg["prior_weights"]["SPY"]
    res = lpf.run(cfg, prior_spy, market, spec, months, raw, y, mapping)
    detail: pd.DataFrame = res.pop("_detail")
    sims = res.pop("_sims")
    tag = cfg.get("tag") or f"spy{int(round(prior_spy * 100))}"
    out_dir = out_dir or (ROOT / "decision_support" / "out")
    out_dir.mkdir(parents=True, exist_ok=True)
    # the monthly chain every reader can audit: stated view -> Q -> Omega -> pi -> mu -> weights, per plugin
    detail.to_csv(out_dir / f"{tag}_{mapping}_monthly.csv", index=False)
    nav = {k: {"months": [str(m) for m in s["decision_month"]], "net_excess_return": [float(x) for x in s["net_excess_return"]]} for k, s in sims.items()}
    out = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "config": config, "fund_set": fund_set,
           "assets": list(cfg["assets"]), "mapping": mapping, "development": cfg["development"], "months": len(months),
           "plugins": status, "result": res, "series": nav}
    (out_dir / f"{tag}_{mapping}.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    return out


class _NoManifest:
    manifest = Manifest(name="", title="", kind="replay", fund_sets=())


_none = _NoManifest()


def trace(name: str, fund_set: str, month: str) -> Answer | None:
    p = load_all([name])[name]
    for a in p.answers(fund_set):
        if a.month == month:
            return a
    return None


def summary_table(out: dict) -> str:
    """A short text table: score, vs doing nothing with its range, verdict."""
    res = out["result"]
    met, vs = res["metrics"], res["vs_static"]
    lines = [f"{out['fund_set']} · {out['mapping']} · {out['development'][0]}..{out['development'][1]} ({out['months']} months)",
             f"{'plugin':12s} {'net CER':>8s} {'vs static':>10s} {'95% range':>18s}  verdict"]
    for k in ["STATIC"] + [k for k in met if k != "STATIC"]:
        c = vs.get(k)
        if k == "STATIC":
            lines.append(f"{k:12s} {met[k]['net_cer']*100:7.2f}% {'':>10s} {'':>18s}  the bar")
            continue
        d, (lo, hi) = c["cer_difference"], c["ci95"]
        verdict = "better" if lo > 0 else "worse" if hi < 0 else "can't tell"
        lines.append(f"{k:12s} {met[k]['net_cer']*100:7.2f}% {d*100:+9.2f} {lo*100:+8.2f}..{hi*100:+6.2f}   {verdict}")
    return "\n".join(lines)
