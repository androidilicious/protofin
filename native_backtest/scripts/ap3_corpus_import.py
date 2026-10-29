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
        "pdf_metadata_used": False}
    s = res["summary"]
    s["pass"] = bool(not s["build_errors"] and not unexplained and not s["date_mismatches"] and not s["alfred_mismatches"] and s["point_in_time_pass"])
    CHECKS.write_text(json.dumps(res, indent=1) + "\n")
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zips", type=Path, required=True)
    a = ap.parse_args()
    imported = import_archives(a.zips)
    print(json.dumps({f: {k: v for k, v in x.items() if k in ("imported", "documents", "missing")} for f, x in imported["archives"].items()}))
    from native_backtest.scripts import ap3_corpus_build
    ap3_corpus_build.main()
    res = checks(imported)
    print(json.dumps(res["summary"], indent=1))
    return 0 if res["summary"]["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
