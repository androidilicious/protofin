"""python -m decision_support list | score [--config config.json] [--mapping sign|ridge|both] [--plugins a,b] | trace <plugin> <fund_set> <YYYY-MM>"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys

from .registry import discover
from .scorer import score, summary_table, trace


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="decision_support")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="registered plugins")
    s = sub.add_parser("score", help="score every plugin on the level field")
    s.add_argument("--config", default="config.json", help="config.json (SPY/TLT 60/40) or config_3f.json (SPY/IEF/LQD 45/35/20)")
    s.add_argument("--mapping", default="both", choices=["sign", "ridge", "both"])
    s.add_argument("--plugins", default="", help="comma-separated subset; default all")
    t = sub.add_parser("trace", help="one plugin's answer for one month, as a reader would see it")
    t.add_argument("plugin"); t.add_argument("fund_set"); t.add_argument("month")
    a = ap.parse_args(argv)
    if a.cmd == "list":
        for name, m in discover().items():
            flag = " (exploratory)" if m.exploratory else ""
            print(f"{name:12s} {m.kind:8s} {','.join(m.fund_sets):22s} {m.title}{flag}")
        return 0
    if a.cmd == "score":
        names = [x for x in a.plugins.split(",") if x] or None
        for mp in (["sign", "ridge"] if a.mapping == "both" else [a.mapping]):
            out = score(a.config, mp, names)
            print(summary_table(out)); print()
        return 0
    ans = trace(a.plugin, a.fund_set, a.month)
    if ans is None:
        print("no answer for that month", file=sys.stderr); return 1
    print(json.dumps(dataclasses.asdict(ans), indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
