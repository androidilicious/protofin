"""Fetch every plugin, append to the store, score the alerts, write site/data/harness.json."""
import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

from . import scoring, store
from .alerts import ALERTS
from .contract import RESTRICTED
from .plugins import all_plugins

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE_DIR, "site", "data", "harness.json")


def collect(plugins, store_dir, fetched_at):
    """Run each plugin on its own, so one broken source cannot stop the others."""
    report = []
    for plugin in plugins:
        row = {"plugin": plugin.name, "title": plugin.title, "licence": plugin.licence,
               "series": list(plugin.series)}
        try:
            lasts = [store.stats(name, store_dir)["last"] for name in plugin.series]
            since = min(lasts) if lasts and all(lasts) else None   # None until every series has history
            readings = plugin.fetch(since=since)
            row["readings"] = len(readings)
            if plugin.licence == RESTRICTED:
                row["status"] = "fetched, not stored (restricted licence)"
            else:
                row["added"] = store.append(readings, plugin.name, store_dir=store_dir, fetched_at=fetched_at)
                row["status"] = "ok"
        except Exception as exc:  # noqa: BLE001
            row["status"] = f"failed: {type(exc).__name__}: {exc}"
        report.append(row)
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="use a temporary store and write nothing")
    ap.add_argument("--no-fetch", action="store_true", help="score from the existing store only")
    ap.add_argument("--strict", action="store_true", help="exit 1 if any source fails or an alert has no score")
    args = ap.parse_args(argv)

    if BASE_DIR not in sys.path:
        sys.path.insert(0, BASE_DIR)   # plugins import macro_indexes from the repo root
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    tmp = tempfile.TemporaryDirectory() if args.dry_run else None
    store_dir = tmp.name if tmp else store.STORE_DIR

    plugins = all_plugins()
    report = [] if args.no_fetch else collect(plugins, store_dir, fetched_at)
    for row in report:
        print(f"{row['plugin']:<14} {row['status']}  {row.get('added', '')}")

    alerts = [scoring.score_alert(a, lambda name: store.series(name, store_dir=store_dir)) for a in ALERTS]
    names = sorted({s for p in plugins for s in p.series})
    out = {
        "generated_at": fetched_at,
        "plugins": report,
        "store": {name: store.stats(name, store_dir) for name in names},
        "alerts": alerts,
    }
    for a in alerts:
        if a["score"] is None:
            print(f"{a['title']}: {a['status']}")
            continue
        print(f"{a['title']}: score {a['score']} (range {a['low']} to {a['high']}, {a['level']}) "
              f"as of {a['as_of']}, {a['signals_used']} of {a['signals_total']} signals")
        for d in a["drivers"]:
            if d["status"] == "ok":
                print(f"  {d['points']:+6.1f}  {d['text']}  [R {d['R']} S {d['S']} P {d['P']} H {d['H']}"
                      f"{' default' if d['H_default'] else ''}]")
            else:
                print(f"     n/a  {d['label']}: {d['status']}")

    if not args.dry_run:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=1)
        print(f"wrote {os.path.relpath(OUT, BASE_DIR)}")
    if tmp:
        tmp.cleanup()
    failed = [r for r in report if r["status"].startswith("failed")]
    if report and len(failed) == len(report):
        return 1    # every source failed: let the caller see it
    if args.strict and (failed or any(a["score"] is None for a in alerts)):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
