"""Export the harness outputs for the support page: site/data/support.json.

    python -m decision_support.export_site

One file: the registry (manifests), the four scored runs (scores, contrasts, monthly net excess returns,
monthly chain per plugin) and every plugin's trace for every month of both fund sets.
"""
from __future__ import annotations

import csv
import dataclasses
import json
from pathlib import Path

from .contract import FUND_SETS, repo_root
from .registry import discover, load_all

ROOT = repo_root()
OUT = ROOT / "decision_support" / "out"
RUNS = {"spy60_sign": ("spy_tlt", "sign"), "spy60_ridge": ("spy_tlt", "ridge"), "f3_sign": ("spy_ief_lqd", "sign"), "f3_ridge": ("spy_ief_lqd", "ridge")}


def _run(tag: str) -> dict:
    d = json.loads((OUT / f"{tag}.json").read_text(encoding="utf-8"))
    res = d["result"]
    chain: dict[str, dict] = {}
    with (OUT / f"{tag}_monthly.csv").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            chain.setdefault(row["system"], {})[row["decision_month"]] = {k: (v if k.startswith("alpha") else float(v)) for k, v in row.items() if k not in ("system", "decision_month")}
    systems = {}
    for k, m in res["metrics"].items():
        c = res["vs_static"].get(k)
        systems[k] = {"net_cer": m["net_cer"], "sharpe": m.get("net_sharpe"), "max_drawdown": m.get("max_drawdown"), "turnover": m.get("annualized_one_way_turnover"),
                      "spy_min": m.get("min_spy_weight"), "spy_max": m.get("max_spy_weight"),
                      "vs_static": None if c is None else {"d": c["cer_difference"], "lo": c["ci95"][0], "hi": c["ci95"][1], "p": c["p_two_sided_bootstrap"]},
                      "vs_placebo": None if k not in res["vs_placebo"] else {"d": res["vs_placebo"][k]["cer_difference"], "lo": res["vs_placebo"][k]["ci95"][0], "hi": res["vs_placebo"][k]["ci95"][1]},
                      "series": d["series"][k], "chain": chain.get(k)}
    return {"fund_set": d["fund_set"], "assets": d["assets"], "mapping": d["mapping"], "development": d["development"], "months": d["months"],
            "plugins": d["plugins"], "systems": systems}


def main() -> int:
    manifests = {n: dataclasses.asdict(m) for n, m in discover().items()}
    plugins = load_all()
    traces = {}
    for fs in FUND_SETS:
        traces[fs] = {}
        for n, p in plugins.items():
            if fs not in p.manifest.fund_sets or p.manifest.kind == "placebo":
                continue
            traces[fs][n] = {a.month: {"stated": a.stated, "confidence": a.confidence, "trace": a.trace} for a in p.answers(fs)
                             if "2019-03" <= a.month <= "2022-12"}
    out = {"generated_from": "decision_support/out", "runs": {t: _run(t) for t in RUNS}, "manifests": manifests, "traces": traces}
    dst = ROOT / "site" / "data" / "support.json"
    dst.write_text(json.dumps(out, separators=(",", ":"), default=str), encoding="utf-8")
    print(f"wrote {dst} ({dst.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
