#!/usr/bin/env python3
"""Versioned archives of the raw AP3 evidence corpus, stored outside the repository history.

pack:    builds one deterministic ZIP per fetched family from native_backtest/data/_corpus_raw (fixed entry order
         and timestamps, so the same documents always give the same archive bytes) and writes
         native_backtest/data/ap3_corpus/archive_manifest_v1.json (archive SHA-256 and size, document count,
         and the fetch-manifest SHA-256 the archives belong to). The archives are published as assets of a
         private GitHub release; only the manifests are committed.
restore: unpacks downloaded archives into the raw store, re-hashing every document against the committed fetch
         manifest (source URL, SHA-256, retrieval time), and rewrites fetch_log.jsonl so ap3_corpus_build and the
         checks run unchanged. Nothing is fetched from the agencies again.

Usage (repository root):
  python -m native_backtest.scripts.ap3_corpus_archive pack --out <folder>
  gh release download ap3-corpus-v1.0-partial --repo androidilicious/protofin --dir <folder>
  python -m native_backtest.scripts.ap3_corpus_archive restore --zips <folder>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "native_backtest/data/_corpus_raw"
FETCH_MANIFEST = ROOT / "native_backtest/data/ap3_corpus/fetch_manifest_v1.json"
ARCHIVE_MANIFEST = ROOT / "native_backtest/data/ap3_corpus/archive_manifest_v1.json"
FIXED_TIME = (2026, 10, 29, 0, 0, 0)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def pack(out: Path, release_tag: str) -> dict:
    fm_bytes = FETCH_MANIFEST.read_bytes()
    fm = json.loads(fm_bytes)
    out.mkdir(parents=True, exist_ok=True)
    archives = {}
    for fam in sorted({d["family"] for d in fm["documents"]}):
        docs = sorted((d for d in fm["documents"] if d["family"] == fam), key=lambda d: d["file"])
        zp = out / f"ap3_corpus_{fam}_v1.zip"
        with zipfile.ZipFile(zp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for d in docs:
                body = (RAW / fam / d["file"]).read_bytes()
                if sha(body) != d["sha256"]:
                    raise SystemExit(f"STOP: {fam}/{d['file']} differs from the fetch manifest")
                info = zipfile.ZipInfo(f"{fam}/{d['file']}", date_time=FIXED_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                z.writestr(info, body)
        b = zp.read_bytes()
        archives[fam] = {"file": zp.name, "documents": len(docs), "bytes": len(b), "sha256": sha(b)}
    man = {"title": "AP3 evidence corpus: versioned raw archives (stored outside the repository history)",
           "release": {"repository": "androidilicious/protofin", "tag": release_tag, "visibility": "private repository; release assets are visible only to collaborators"},
           "fetch_manifest_sha256": sha(fm_bytes), "archives": archives,
           "families_not_archived": [f for f, x in fm["families"].items() if x["fetched"] == 0],
           "restore": "python -m native_backtest.scripts.ap3_corpus_archive restore --zips <folder with the downloaded archives>"}
    ARCHIVE_MANIFEST.write_text(json.dumps(man, indent=1) + "\n")
    return man


def restore(folder: Path) -> dict:
    fm = json.loads(FETCH_MANIFEST.read_text())
    am = json.loads(ARCHIVE_MANIFEST.read_text())
    if am["fetch_manifest_sha256"] != sha(FETCH_MANIFEST.read_bytes()):
        raise SystemExit("STOP: archives were packed against a different fetch manifest")
    by_file = {(d["family"], d["file"]): d for d in fm["documents"]}
    log, n = [], 0
    for fam, a in am["archives"].items():
        zp = folder / a["file"]
        b = zp.read_bytes()
        if sha(b) != a["sha256"]:
            raise SystemExit(f"STOP: {a['file']} differs from the archive manifest")
        with zipfile.ZipFile(zp) as z:
            if z.testzip():
                raise SystemExit(f"STOP: CRC error in {a['file']}")
            for name in z.namelist():
                fam_, file = name.split("/", 1)
                d = by_file[(fam_, file)]
                body = z.read(name)
                if sha(body) != d["sha256"]:
                    raise SystemExit(f"STOP: {name} differs from the fetch manifest")
                p = RAW / fam_ / file
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(body)
                log.append({"family": fam_, "url": d["url"], "status": 200, "bytes": d["bytes"], "sha256": d["sha256"], "retrieved_utc": d["retrieved_utc"],
                            "url_date": d["url_date"], "release_date": d["release_date"], "file": str(p.relative_to(ROOT)), "via": d["via"]})
                n += 1
    for fam, x in fm["families"].items():      # keep the record of unreachable index pages and failed documents
        for i in x["index_pages"]:
            log.append({**i, "kind": "index", "bytes": 0})
        for f in x["failed_documents"]:
            log.append({**f, "bytes": 0, "sha256": ""})
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "fetch_log.jsonl").write_text("".join(json.dumps(r) + "\n" for r in log))
    return {"documents_restored": n, "archives": len(am["archives"])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pack")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--tag", default="ap3-corpus-v1.0-partial")
    r = sub.add_parser("restore")
    r.add_argument("--zips", type=Path, required=True)
    a = ap.parse_args(argv)
    print(json.dumps(pack(a.out, a.tag) if a.cmd == "pack" else restore(a.zips), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
