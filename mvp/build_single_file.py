#!/usr/bin/env python3
"""Bundle the dashboard into one self-contained HTML file.

Everything is inlined: styles, Chart.js, the application and the whole dataset. The result opens from a local
file with no server and no network, which is what makes it portable enough to hand to another tool for review.
Build: python mvp/build_single_file.py
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MVP = ROOT / "mvp"
OUT = MVP / "dist" / "protofin_dashboard_single_file.html"


def git(*a: str) -> str:
    try:
        r = subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def main() -> int:
    html = (MVP / "index.html").read_text()
    app = (MVP / "assets/app.js").read_text()
    chart = (MVP / "assets/vendor/chart.umd.4.4.4.js").read_text()
    data = json.loads((MVP / "data/dashboard.json").read_text())

    # The app fetches data/dashboard.json; inlined, it reads the preloaded object instead.
    assert "fetch(" in app, "the loader changed: re-check how the data is read"
    boot = ("<script>window.__PROTOFIN_DATA__ = " + json.dumps(data, separators=(",", ":"), ensure_ascii=False)
            + ";</script>")

    html = html.replace('<script src="assets/vendor/chart.umd.4.4.4.js"></script>',
                        boot + "\n<script>" + chart + "</script>")
    html = html.replace('<script src="assets/app.js"></script>', "<script>" + app + "</script>")

    # Web fonts are the one thing that would still reach the network. The stylesheet already falls back to the
    # system stack, so the bundle drops the link rather than shipping ~200 KB of font binaries for a small
    # difference in letterforms.
    for link in ('<link rel="preconnect" href="https://fonts.googleapis.com">',
                 '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700'
                 '&family=JetBrains+Mono:wght@400;600&display=swap">'):
        assert link in html, "the font links changed: re-check what the bundle has to strip"
        html = html.replace(link, "")
    # check the script TAGS are gone: the inlined Chart.js mentions its own filename in a source-map comment
    for tag in ('<script src="assets/app.js">', '<script src="assets/vendor/'):
        assert tag not in html, f"a reference was left behind: {tag}"

    note = (f"\n<!-- Protofin research dashboard, single-file build.\n"
            f"     Source: {git('rev-parse', '--abbrev-ref', 'HEAD') or 'backtest'} "
            f"@ {git('rev-parse', 'HEAD') or 'unknown'}\n"
            f"     Data generated: {data.get('build', {}).get('generated_at_utc', '')}\n"
            f"     Development diagnostics only. The protected historical test window "
            f"{'..'.join(data['windows']['historical_test'])} is sealed and was never scored.\n"
            f"     Causal RAG figures are EXPLORATORY: its agents did not pass their pre-registered reliability\n"
            f"     gates, so they are a diagnostic of the pipeline, not validated evidence. -->\n")
    html = html.replace("</head>", note + "</head>", 1)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html)
    print(json.dumps({"written": str(OUT.relative_to(ROOT)), "bytes": OUT.stat().st_size,
                      "mb": round(OUT.stat().st_size / 1e6, 2),
                      "sha256": hashlib.sha256(OUT.read_bytes()).hexdigest()[:16]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
