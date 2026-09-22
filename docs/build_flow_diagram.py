"""Regenerate docs/protofin-pipeline.html with the latest run's results inside the diagram.

The archify diagram is static, so this script rewrites node sublabels, guided-view notes and
the result cards from state/last_allocation.json, then re-delivers the HTML through archify's
validator. It also writes docs/protofin-pipeline.meta.json so the dashboard knows which run
the diagram shows and can reload its embedded copy.

    python docs/build_flow_diagram.py
The server calls this in a background thread after every fresh decision.
"""
import json
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(BASE, "docs", "protofin-pipeline.workflow.json")
HTML = os.path.join(BASE, "docs", "protofin-pipeline.html")
META = os.path.join(BASE, "docs", "protofin-pipeline.meta.json")
STATE = os.path.join(BASE, "state", "last_allocation.json")
ARCHIFY = os.path.join(BASE, ".agents", "skills", "archify", "bin", "archify.mjs")   # real copy; other dot-dirs are symlinks


def short(v, digits=1):
    return f"{v:+.{digits}f}" if isinstance(v, (int, float)) else str(v)


def build_spec(r):
    spec = json.load(open(SPEC, encoding="utf-8"))
    f = (r.get("news") or {}).get("fomc") or {}
    e, g = r.get("epu") or {}, r.get("gpr") or {}
    # results as node sublabels (kept short: the node is 122px wide)
    sub = {
        "run": f"run {r['as_of']}",
        "ingest": f"10Y {r['yield']} SPY1m {r['spy_return']}",
        "shock": f"{r['svar_value']:+.0f} bps vs 3mo avg",
        "regime": f"EPU {e.get('percentile_10y', 0):.0f} GPR {g.get('percentile_10y', 0):.0f} {r['uncertainty_regime'][:4]}",
        "fomc": f"hawkish {f.get('score', 0):+.2f}",
        "committee": f"CIO SPY {r['spy_q']}% TLT {r['tlt_q']}%",
        "allocate": f"target {r['target_spy']}/{r['target_tlt']}",
        "render": f"SPY {r['spy_weight']}% TLT {r['tlt_weight']}%",
    }
    for n in spec["nodes"]:
        if n["id"] in sub:
            n["sublabel"] = sub[n["id"]][:20]
    spec["meta"]["animation"] = "trace"
    spec["meta"]["views"] = [
        {"id": "signals", "label": "Signals", "focus": ["ingest", "shock", "regime", "fomc"],
         "note": f"{r['as_of']}: 10Y {r['yield']}, shock {r['svar_value']:+.0f} bps, regime {r['uncertainty_regime']}, FOMC {f.get('score', 0):+.2f}."[:140]},
        {"id": "decision", "label": "Views to allocation", "focus": ["committee", "allocate", "render"],
         "note": f"Views SPY {r['spy_q']}% TLT {r['tlt_q']}% ({r['confidence_reported']} used as {r['confidence']}) -> {r['spy_weight']}/{r['tlt_weight']}."[:140]},
    ]
    spec["cards"] = [
        {"dot": "cyan", "title": "Last run: inputs", "items": [
            f"As of {r['as_of']}: 10Y {r['yield']}, cash {r['risk_free']}%, SPY 1m {r['spy_return']}",
            f"Rate shock {r['svar_value']:+.0f} bps; EPU {e.get('percentile_10y', 0):.0f}th, GPR {g.get('percentile_10y', 0):.0f}th pct; regime {r['uncertainty_regime']}",
            f"FOMC stance {f.get('score', 0):+.2f} (statement {f.get('date', 'n/a')}); headlines display only"]},
        {"dot": "emerald", "title": "Last run: decision", "items": [
            f"Committee: SPY {r['spy_q']}%, TLT {r['tlt_q']}%, confidence {r['confidence_reported']} used as {r['confidence']}",
            f"Posterior excess {r['posterior_spy']}/{r['posterior_tlt']} -> target {r['target_spy']}/{r['target_tlt']}",
            f"Final {r['spy_weight']}/{r['tlt_weight']} ({r['trade_status']})"]},
    ]
    return spec


def main():
    r = json.load(open(STATE, encoding="utf-8"))["response"]
    spec = build_spec(r)
    json.dump(spec, open(SPEC, "w", encoding="utf-8"), indent=2)
    out = subprocess.run(["node", ARCHIFY, "deliver", "workflow", SPEC, HTML, "--quality", "showcase", "--json"],
                         capture_output=True, text=True, cwd=os.path.dirname(ARCHIFY))
    try:
        rec = json.loads(out.stdout or "{}")
    except ValueError:
        rec = {"ok": False, "error": (out.stdout + out.stderr)[-400:]}
    meta = {"fingerprint": r["fingerprint"], "as_of": r["as_of"], "timestamp": r.get("timestamp"),
            "delivered": bool(rec.get("ok")), "error": rec.get("error"),
            "diagnostics": [d.get("message") for d in rec.get("diagnostics", [])][:5]}
    json.dump(meta, open(META, "w", encoding="utf-8"), indent=2)
    print("delivered:", meta["delivered"], "|", meta["error"] or HTML)
    for m in meta["diagnostics"]:
        print(" -", m)
    return 0 if meta["delivered"] else 1


if __name__ == "__main__":
    sys.exit(main())
