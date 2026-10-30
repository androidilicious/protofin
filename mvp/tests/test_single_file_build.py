"""The single-file build: one portable HTML file with no external dependency.

It exists so the dashboard can be handed to someone outside this project - a reviewer, another tool - without a
server, a network or the repository. That only holds if nothing in it points outward, so this checks exactly that.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "mvp/dist/protofin_dashboard_single_file.html"


@pytest.fixture(scope="module")
def built() -> str:
    r = subprocess.run([sys.executable, str(ROOT / "mvp/build_single_file.py")],
                       cwd=ROOT, capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stderr
    return OUT.read_text()


def test_it_is_one_file_with_nothing_to_fetch(built):
    assert '<script src="assets/app.js">' not in built
    assert '<script src="assets/vendor/' not in built
    assert 'href="data/' not in built and 'src="data/' not in built
    # no remote origin of any kind: a reviewer offline must see the same dashboard
    for src in re.findall(r'<(?:script|link)[^>]+(?:src|href)="([^"]+)"', built):
        assert not src.startswith(("http://", "https://", "//")), src


def test_the_loader_prefers_preloaded_data_but_still_supports_the_served_build(built):
    app = (ROOT / "mvp/assets/app.js").read_text()
    assert "window.__PROTOFIN_DATA__" in app and "fetch('data/dashboard.json'" in app, \
        "the served build must keep working alongside the bundle"
    assert "window.__PROTOFIN_DATA__ =" in built, "the bundle must preload the dataset"


def test_the_whole_dataset_travels_with_it(built):
    m = re.search(r"window\.__PROTOFIN_DATA__ = (\{.*?\});</script>", built, re.S)
    assert m, "the preloaded dataset is missing"
    data = json.loads(m.group(1))
    live = json.loads((ROOT / "mvp/data/dashboard.json").read_text())
    assert data == live, "the bundle must carry exactly the published dataset"
    for block in ("systems", "dev", "pipeline", "sensitivity", "signal_value", "appendix", "export", "build"):
        assert block in data, block


def test_it_carries_its_own_provenance_and_caveats(built):
    head = built[:built.index("</head>")]
    assert "single-file build" in head and "Source:" in head
    assert re.search(r"@ [0-9a-f]{40}", head), "the source commit must be recorded in the file"
    assert "sealed" in head and "never scored" in head
    assert "EXPLORATORY" in head and "not validated evidence" in head


def test_it_stays_a_reasonable_size(built):
    mb = OUT.stat().st_size / 1e6
    assert mb < 5.0, f"{mb:.2f} MB is too large to hand around"
