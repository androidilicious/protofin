#!/usr/bin/env python3
"""Import the browser-captured AP3 evidence corpus and run its coverage and point-in-time checks.

Input: a folder of archives made by native_backtest/scripts/browser/ap3_corpus_capture.js, one per family
(ap3_corpus_<family>_v1.zip). Each archive holds the documents exactly as served plus manifest.json with the URL,
HTTP status, SHA-256 (computed in the page), retrieval time and the index dates of every document.

Steps
1. Archive integrity: zip CRC test, archive SHA-256, every document re-hashed against the page-side SHA-256.
2. Raw store: documents written to native_backtest/data/_corpus_raw/<family>/ and listed in fetch_log.jsonl in the
   direct fetcher's format (with "via": "browser_capture"), so ap3_corpus_build runs unchanged.
3. Build: ap3_corpus_build extracts text and available_at from the documents themselves (printed embargo or
   release lines; documented release times where none is printed). PDF metadata is never used.
4. Checks (written to native_backtest/out/ap3/corpus_checks_v1.json):
   - coverage by family and year against the expected counts, with documented exceptions (partial first and
     last years, the October-November 2025 federal shutdown);
   - every document's available_at date equals its index date (BLS archive date, Fed calendar release date,
     G.17 release date, FOMC statement date) and, where an ALFRED series exists, is one of that series' vintage
     dates (data/ap3_corpus/alfred_release_vintages_v1.json);
   - the point-in-time audit over every AP3 decision time 2015-02..2026-08 (calendar only; nothing is scored):
     no chunk is eligible before it was public and no canary is ever eligible.

Usage (repository root): python -m native_backtest.scripts.ap3_corpus_import --zips <folder>
                          python -m native_backtest.scripts.ap3_corpus_import --from-fetch-log   (direct fetch)
Exit code 0 only if every archive verifies and every check passes or is a documented exception.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import zipfile
from pathlib import Path

import pandas as pd

from native_backtest.ap3 import corpus
from native_backtest.framework.market import decision_time_iso, load_config, load_market, months_between

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "native_backtest/data/_corpus_raw"
IMPORT_MANIFEST = ROOT / "native_backtest/data/ap3_corpus/import_manifest_v1.json"
ALFRED = ROOT / "native_backtest/data/ap3_corpus/alfred_release_vintages_v1.json"
CORPUS_MANIFEST = ROOT / "native_backtest/out/ap3/corpus_manifest_v1.json"
CHECKS = ROOT / "native_backtest/out/ap3/corpus_checks_v1.json"
FAMILIES = ("bls_employment_situation", "bls_cpi", "bls_ppi", "fomc_minutes", "fomc_statement",
            "fed_g17_industrial_production", "census_advance_retail_sales")
# Documented coverage exceptions (counts outside expected_per_year that are explained, not errors).
SHUTDOWN_2025 = "Federal government shutdown 2025-10-01..2025-11-12: releases cancelled or combined"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def import_archives(folder: Path) -> dict:
    RAW.mkdir(parents=True, exist_ok=True)
    log, archives = [], {}
    for fam in FAMILIES:
        zp = folder / f"ap3_corpus_{fam}_v1.zip"
        if not zp.exists():
            archives[fam] = {"missing": True}
            continue
        raw_zip = zp.read_bytes()
        with zipfile.ZipFile(zp) as z:
            bad = z.testzip()
            if bad:
                raise SystemExit(f"STOP: {zp.name}: CRC error in {bad}")
            man_bytes = z.read("manifest.json")
            man = json.loads(man_bytes)
            docs = man["documents"]
            ok, failures = 0, []
            for d in docs:
                if d.get("status") != 200:
                    failures.append({"url": d["url"], "status": d.get("status")})
                    continue
                body = z.read(d["file"])
                if sha(body) != d["sha256"] or len(body) != d["bytes"]:
                    raise SystemExit(f"STOP: {zp.name}: {d['file']} differs from its page-side SHA-256")
                name = d["file"].split("/", 1)[1]
                out = RAW / fam / name
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(body)
                log.append({"family": fam, "url": d["url"], "status": 200, "bytes": d["bytes"], "sha256": d["sha256"],
                            "retrieved_utc": d["retrieved_utc"], "url_date": d.get("url_date"), "release_date": d.get("release_date"),
                            "file": str(out.relative_to(ROOT)), "via": "browser_capture", "archive": zp.name})
                ok += 1
        archives[fam] = {"archive": zp.name, "bytes": len(raw_zip), "sha256": sha(raw_zip), "manifest_sha256": sha(man_bytes),
                         "created_utc": man.get("created_utc"), "page_origin": man.get("page_origin"),
                         "documents": len(docs), "imported": ok, "failed_fetches": failures}
    (RAW / "fetch_log.jsonl").write_text("".join(json.dumps(r) + "\n" for r in log))
    out = {"title": "AP3 evidence corpus: browser-captured archives", "archives": archives,
           "documents": sorted(({k: r[k] for k in ("family", "url", "sha256", "bytes", "retrieved_utc", "url_date", "release_date")} for r in log),
                               key=lambda r: (r["family"], r["url"]))}
    IMPORT_MANIFEST.write_text(json.dumps(out, indent=1) + "\n")
    return out


FETCH_MANIFEST = ROOT / "native_backtest/data/ap3_corpus/fetch_manifest_v1.json"


def from_fetch_log() -> dict:
    """Direct-fetch path: read the fetcher's log, re-hash every raw file, and write the committed fetch manifest.

    The manifest lists, per family, every document that was fetched (source URL, SHA-256, bytes, retrieval time,
    index date, release date) and every planned document or index page that was not (URL and HTTP status), so
    missing records are explicit. The raw files themselves stay outside git.
    """
    log = [json.loads(l) for l in (RAW / "fetch_log.jsonl").read_text().splitlines()]
    latest, failed, index = {}, {}, {}
    for r in log:
        if r.get("kind") == "index":
            index[r["url"]] = {"family": r["family"], "url": r["url"], "status": r["status"], "sha256": r["sha256"],
                               "retrieved_utc": r["retrieved_utc"]}
        elif r.get("status") == 200 and r.get("file"):
            latest[r["url"]] = r
            failed.pop(r["url"], None)
        elif r["url"] not in latest:
            failed[r["url"]] = {"family": r["family"], "url": r["url"], "status": r["status"], "retrieved_utc": r["retrieved_utc"],
                                "url_date": r.get("url_date"), "release_date": r.get("release_date")}
    docs = []
    for r in latest.values():
        body = (ROOT / r["file"]).read_bytes()
        if sha(body) != r["sha256"] or len(body) != r["bytes"]:
            raise SystemExit(f"STOP: {r['file']} differs from its logged SHA-256")
        docs.append({k: r.get(k) for k in ("family", "url", "sha256", "bytes", "retrieved_utc", "url_date", "release_date")}
                    | {"file": Path(r["file"]).name, "via": r.get("via", "direct_fetch")})
    fams = {}
    for fam in FAMILIES:
        fams[fam] = {"fetched": sum(d["family"] == fam for d in docs),
                     "failed_documents": sorted((f for f in failed.values() if f["family"] == fam), key=lambda f: f["url"]),
                     "index_pages": sorted((i for i in index.values() if i["family"] == fam), key=lambda i: i["url"])}
        fams[fam]["index_unreachable"] = [i["url"] for i in fams[fam]["index_pages"] if i["status"] != 200]
    out = {"title": "AP3 evidence corpus: direct fetch from the issuing agencies",
           "sources_config": "native_backtest/ap3/corpus_sources_v1.json",
           "raw_store": "native_backtest/data/_corpus_raw/ (git-ignored; versioned archives stored outside the repository history)",
           "families": fams,
           "documents": sorted(docs, key=lambda d: (d["family"], d["url"]))}
    FETCH_MANIFEST.write_text(json.dumps(out, indent=1) + "\n")
    return out


def _same_year_december_minutes(fd: list, by_url: dict, y: int):
    """The December meeting of year y whose minutes the calendar dates within year y (normally they follow in January)."""
    for d in fd:
        meet = (by_url.get(d["url"], {}) or {}).get("url_date")
        if meet and meet[:7] == f"{y}-12" and d["available_at_et"][:4] == str(y):
            return {"url_date": meet, "available_at_et": d["available_at_et"]}
    return None


def reconciliation() -> dict:
    """Expected vs downloaded documents per family, reconciled against an independent record of release dates
    (ALFRED vintage dates of each release's headline series; FOMC families against the Fed's own calendar pages).
    ALFRED also records revision-only vintages (annual revisions), so its count is an upper bound on releases."""
    fm = json.loads((ROOT / "native_backtest/data/ap3_corpus/fetch_manifest_v1.json").read_text())
    man = json.loads(CORPUS_MANIFEST.read_text())
    alfred = json.loads(ALFRED.read_text())["families"]
    w0, w1 = corpus.load_sources()["window"]
    out, tot = {}, collections.Counter()
    for fam in FAMILIES:
        x = fm["families"].get(fam, {})
        docs = [d for d in man["documents"] if d["family"] == fam]
        dates = {d["available_at_et"][:10] for d in docs}
        row = {"listed_on_official_index": None if x.get("index_unreachable") else x.get("fetched", 0) + len(x.get("failed_documents", [])),
               "downloaded": x.get("fetched", 0), "built_and_dated": len(docs), "failed_downloads": len(x.get("failed_documents", [])),
               "index_unreachable": x.get("index_unreachable", [])}
        if fam in alfred:
            v = sorted(d for d in alfred[fam]["vintage_dates"] if w0 <= d <= w1)
            row.update({"alfred_series": alfred[fam]["series"], "alfred_dates_in_window": len(v),
                        "alfred_dates_without_document": sorted(set(v) - dates),
                        "documents_not_on_an_alfred_date": sorted(dates - set(v))})
        else:
            row["independent_record"] = "Federal Reserve calendar pages (statement dates from the vendored FOMC index; minutes release dates)"
        row["missing"] = (row.get("alfred_dates_without_document") if not docs else
                          [] if row["listed_on_official_index"] == row["built_and_dated"] else ["see failed downloads"])
        out[fam] = row
        tot["downloaded"] += row["downloaded"]
        tot["expected_upper"] += row["built_and_dated"] if docs else row.get("alfred_dates_in_window", 0)
    return {"families": out, "totals": {"downloaded_and_validated": tot["downloaded"], "expected_upper_bound": tot["expected_upper"]},
            "note": "For downloaded families the official index is the expected list; ALFRED dates without a document there are revision-only "
                    "vintages (annual revisions), not missing releases. For unreachable families the ALFRED dates are the missing list (upper bound)."}


def checks(imported: dict) -> dict:
    src = corpus.load_sources()
    man = json.loads(CORPUS_MANIFEST.read_text())
    alfred = json.loads(ALFRED.read_text())["families"]
    by_url = {d["url"]: d for d in imported["documents"]}
    docs = man["documents"]
    res = {"build_errors": man["errors"], "coverage": {}, "dates": {}, "alfred": {}}
    w0, w1 = src["window"]
    for fam in FAMILIES:
        lo, hi = src["families"][fam]["expected_per_year"]
        fd = [d for d in docs if d["family"] == fam]
        years = collections.Counter(d["available_at_et"][:4] for d in fd)
        rows = {}
        for y in range(int(w0[:4]), int(w1[:4]) + 1):
            n = years.get(str(y), 0)
            if lo <= n <= hi:
                status = "ok"
            elif y == int(w1[:4]):
                status = "partial year (window ends " + w1 + ")"
            elif y == 2025 and n < lo:
                status = "explained: " + SHUTDOWN_2025
            elif y == int(w0[:4]) and fam in ("fomc_minutes",) and n < lo:
                status = "partial year"
            elif fam == "fomc_minutes" and n == hi + 1 and _same_year_december_minutes(fd, by_url, y):
                d = _same_year_december_minutes(fd, by_url, y)
                status = (f"explained: minutes of the December {y} meeting ({d['url_date']}) were released on {d['available_at_et'][:10]}, "
                          f"within the same year, per the Federal Reserve calendar")
            else:
                status = "UNEXPLAINED"
            rows[str(y)] = {"n": n, "expected": [lo, hi], "status": status}
        res["coverage"][fam] = rows
        # available_at date vs the index date
        mism = []
        for d in fd:
            r = by_url.get(d["url"], {})
            index_date = r.get("release_date") or r.get("url_date")
            got = d["available_at_et"][:10]
            if index_date and got != index_date:
                mism.append({"url": d["url"], "available_at": got, "index_date": index_date})
        res["dates"][fam] = {"checked": sum(1 for d in fd if (by_url.get(d["url"], {}).get("release_date") or by_url.get(d["url"], {}).get("url_date"))),
                             "mismatches": mism}
        if fam in alfred:
            vint = set(alfred[fam]["vintage_dates"])
            not_vintage = [{"url": d["url"], "available_at": d["available_at_et"][:10]} for d in fd if d["available_at_et"][:10] not in vint]
            res["alfred"][fam] = {"series": alfred[fam]["series"], "documents": len(fd), "not_an_alfred_vintage_date": not_vintage}
    mk = load_market(load_config())
    times = [decision_time_iso(mk.decision_dates[m]) for m in months_between("2015-02", "2026-08")]
    chunks = [json.loads(l) for l in (ROOT / "native_backtest/data/_corpus/chunks.jsonl").read_text().splitlines()]
    res["point_in_time_audit_2015_02_to_2026_08"] = corpus.audit(chunks, times)
    unexplained = [(f, y) for f, rows in res["coverage"].items() for y, r in rows.items() if r["status"] == "UNEXPLAINED"]
    res["summary"] = {
        "documents": len(docs), "build_errors": len(man["errors"]), "coverage_unexplained": unexplained,
        "date_mismatches": sum(len(v["mismatches"]) for v in res["dates"].values()),
        "alfred_mismatches": sum(len(v["not_an_alfred_vintage_date"]) for v in res["alfred"].values()),
        "point_in_time_pass": res["point_in_time_audit_2015_02_to_2026_08"]["pass"],
        "pdf_metadata_used": False,
        "families_missing": [f for f, x in imported.get("families", {}).items() if x.get("fetched") == 0],
        "index_pages_unreachable": {f: x["index_unreachable"] for f, x in imported.get("families", {}).items() if x.get("index_unreachable")},
        "failed_documents": {f: len(x["failed_documents"]) for f, x in imported.get("families", {}).items() if x.get("failed_documents")}}
    s = res["summary"]
    res["reconciliation"] = reconciliation()
    s["reconciliation_totals"] = res["reconciliation"]["totals"]
    s["pass"] = bool(not s["build_errors"] and not unexplained and not s["date_mismatches"] and not s["alfred_mismatches"] and s["point_in_time_pass"])
    CHECKS.write_text(json.dumps(res, indent=1) + "\n")
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--zips", type=Path, help="folder of browser-captured archives")
    g.add_argument("--from-fetch-log", action="store_true", help="use the direct fetcher's raw store and log")
    g.add_argument("--reconcile-only", action="store_true", help="refresh the reconciliation in the existing checks file")
    a = ap.parse_args()
    if a.reconcile_only:
        res = json.loads(CHECKS.read_text())
        res["reconciliation"] = reconciliation()
        res["summary"]["reconciliation_totals"] = res["reconciliation"]["totals"]
        CHECKS.write_text(json.dumps(res, indent=1) + "\n")
        print(json.dumps(res["reconciliation"]["totals"], indent=1))
        return 0
    if a.from_fetch_log:
        imported = from_fetch_log()
        print(json.dumps({f: {"fetched": x["fetched"], "failed": len(x["failed_documents"]), "index_unreachable": x["index_unreachable"]}
                          for f, x in imported["families"].items()}))
    else:
        imported = import_archives(a.zips)
        print(json.dumps({f: {k: v for k, v in x.items() if k in ("imported", "documents", "missing")} for f, x in imported["archives"].items()}))
    from native_backtest.scripts import ap3_corpus_build
    ap3_corpus_build.main()
    res = checks(imported)
    print(json.dumps(res["summary"], indent=1))
    return 0 if res["summary"]["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
