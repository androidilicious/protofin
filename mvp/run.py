#!/usr/bin/env python3
"""One entry point for the backtest MVP.

    python mvp/run.py fetch     # download pinned inputs from GitHub and verify every SHA-256
    python mvp/run.py build     # rerun the pipeline (development months only) and rebuild the dashboard data
    python mvp/run.py serve     # open the dashboard at http://127.0.0.1:8000
    python mvp/run.py check     # unit tests + headless-browser dashboard check

Nothing here calls a paid model or opens the sealed 2023-01..2026-08 window.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
EXTERNAL = ROOT / "native_backtest" / "data" / "_external"


def sh(*args: str) -> None:
    print("$", " ".join(args), flush=True)
    subprocess.run(list(args), cwd=ROOT, check=True)


def fetch(_: argparse.Namespace) -> None:
    sh(PY, "stage2/scoring/fetch_pinned_inputs.py", "--manifest", "stage2/reproducibility/stage2_data_snapshot_manifest_v3_2026-10-27.json")
    sh(PY, "stage2/scoring/fetch_pinned_inputs.py", "--manifest", "native_backtest/config/native_data_manifest_v1.json")
    sh(PY, "stage2/scoring/fetch_pinned_inputs.py", "--manifest", "native_backtest/config/ap3_mediator_manifest_v1.json")
    sh(PY, "stage2/scoring/fetch_pinned_inputs.py", "--manifest", "native_backtest/config/ap3_mediator_manifest_v2.json")
    # Garg & Fetzer claims: no published licence, so they are fetched for local use only (git-ignored).
    sh(PY, "stage2/scoring/fetch_pinned_inputs.py", "--manifest", "native_backtest/config/ap3_claims_manifest_v1.json", "--out", str(EXTERNAL))


def build(_: argparse.Namespace) -> None:
    sh(PY, "stage2/scoring/stage2_backtest.py", "--spec", "stage2/scoring/stage2_run_spec_dev_v4.json", "--mode", "development",
       "--output-dir", "native_backtest/out/ap1/stage2_dev_rerun")
    sh(PY, "-m", "native_backtest.scripts.build_ap1_decisions")
    sh(PY, "-m", "native_backtest.scripts.ap2_native_reproduction")
    sh(PY, "-m", "native_backtest.scripts.development_evaluation")
    sh(PY, "-m", "native_backtest.scripts.common_benchmark_checks")
    # Gate 5 extended to TLT: reports PASS or FAIL in native_backtest/out/tlt_dividend_gate; a FAIL is a gate
    # result for the team to review, not a build error.
    print("$", PY, "-m native_backtest.scripts.check_tlt_distributions", flush=True)
    rc = subprocess.run([PY, "-m", "native_backtest.scripts.check_tlt_distributions"], cwd=ROOT).returncode
    if rc not in (0, 2):
        sys.exit(f"TLT distribution check could not run (exit {rc})")
    sh(PY, "-m", "native_backtest.scripts.diagnose_tlt_gate5")
    sh(PY, "-m", "native_backtest.scripts.ap3_mediator_inventory")
    if (EXTERNAL / "claims_part01.parquet").exists():
        sh(PY, "-m", "native_backtest.scripts.build_ap3_libraries")
        sh(PY, "mvp/build_ap3_demo.py")
        sh(PY, "-m", "native_backtest.scripts.ap3_dev_readiness")                        # v1 (kept reproducible)
        sh(PY, "-m", "native_backtest.scripts.ap3_dev_readiness", "--inventory", "v2")   # validated inventory, provisional
        sh(PY, "-m", "native_backtest.scripts.ap3_inference_budget")
    else:
        print("claims data not present: skipping AP3 graph libraries and demo (committed manifest and demo are used)")
    sh(PY, "-m", "native_backtest.scripts.audit_portfolio_integrity")   # independent rebuild; fails the build on any finding
    sh(PY, "-m", "native_backtest.scripts.signal_value_added")          # signals vs own no-signal portfolios (development)
    sh(PY, "-m", "native_backtest.scripts.audit_signal_value")          # independent rebuild of it; fails on any mismatch
    sh(PY, "mvp/build_dashboard_data.py")


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):  # noqa: D401
        pass


def _server(port: int):
    handler = functools.partial(_Quiet, directory=str(ROOT / "mvp"))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    return srv


def serve(a: argparse.Namespace) -> None:
    if not (ROOT / "mvp" / "data" / "dashboard.json").exists():
        sys.exit("mvp/data/dashboard.json is missing: run `python mvp/run.py build` first")
    srv = _server(a.port)
    print(f"Protofin Backtest dashboard: http://127.0.0.1:{a.port}/  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


def check(a: argparse.Namespace) -> None:
    sh(PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "native_backtest/tests", "mvp/tests")
    sh(PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "stage2/scoring")
    srv = _server(a.port)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    time.sleep(0.5)
    try:
        sh(PY, "mvp/tests/check_dashboard.py", "--url", f"http://127.0.0.1:{a.port}/")
    finally:
        srv.shutdown()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch").set_defaults(fn=fetch)
    sub.add_parser("build").set_defaults(fn=build)
    for name, fn, port in (("serve", serve, 8000), ("check", check, 8766)):
        p = sub.add_parser(name)
        p.add_argument("--port", type=int, default=port)
        p.set_defaults(fn=fn)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
