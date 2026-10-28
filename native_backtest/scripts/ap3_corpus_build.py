#!/usr/bin/env python3
"""Build AP3's corpus from the fetched raw documents: text, available_at, native chunks, canaries, audit.

Inputs: native_backtest/data/_corpus_raw/fetch_log.jsonl and the raw files it lists (hash-verified).
Outputs:
  native_backtest/data/_corpus/chunks.jsonl         chunks incl. canaries (git-ignored; rebuilt from raw)
  native_backtest/out/ap3/corpus_manifest_v1.json   every document: URL, raw SHA-256, available_at and its
                                                    source, chunk count, text SHA-256; per-family counts;
                                                    the point-in-time audit over all AP3 decision times
Usage: python -m native_backtest.scripts.ap3_corpus_build
"""
from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path

import pandas as pd

from native_backtest.ap3 import corpus
from native_backtest.framework.market import decision_time_iso, load_config, load_market, months_between

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "native_backtest/data/_corpus_raw"
OUTC = ROOT / "native_backtest/data/_corpus"
MAN = ROOT / "native_backtest/out/ap3/corpus_manifest_v1.json"


def main() -> int:
    log = [json.loads(l) for l in (RAW / "fetch_log.jsonl").read_text().splitlines()]
    docs, chunks, errors = [], [], []
    src = corpus.load_sources()
    latest = {}
    for r in log:  # last successful fetch per URL
        if r.get("file") and r.get("status") == 200:
            latest[r["url"]] = r
    for r in latest.values():
        raw = (ROOT / r["file"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != r["sha256"]:
            errors.append({"url": r["url"], "error": "raw file differs from its logged SHA-256"})
            continue
        try:
            d = corpus.make_document(r["family"], r["url"], raw, pd.Timestamp(r["url_date"]) if r.get("url_date") else None,
                                     pd.Timestamp(r["release_date"]) if r.get("release_date") else None, src)
        except corpus.CorpusError as e:
            errors.append({"url": r["url"], "error": str(e)})
            continue
        cs = corpus.chunks_for(d)
        chunks += cs
        docs.append({"doc_id": d.doc_id, "family": d.family, "url": d.url, "raw_sha256": d.raw_sha256,
                     "available_at_et": d.available_at_et, "available_at_source": d.available_at_source,
                     "text_sha256": hashlib.sha256(d.text.encode()).hexdigest(), "n_chunks": len(cs), "n_words": len(d.text.split())})
    chunks += corpus.canaries(src["window"][1])
    OUTC.mkdir(parents=True, exist_ok=True)
    (OUTC / "chunks.jsonl").write_text("".join(json.dumps(c) + "\n" for c in chunks))
    mk = load_market(load_config())
    times = [decision_time_iso(mk.decision_dates[m]) for m in months_between("2015-02", "2022-12")]
    aud = corpus.audit(chunks, times)
    counts = collections.defaultdict(collections.Counter)
    for d in docs:
        counts[d["family"]][d["available_at_et"][:4]] += 1
    MAN.parent.mkdir(parents=True, exist_ok=True)
    MAN.write_text(json.dumps({"version": src["version"], "window": src["window"], "n_documents": len(docs), "n_chunks": len(chunks),
                               "chunks_sha256": hashlib.sha256((OUTC / "chunks.jsonl").read_bytes()).hexdigest(),
                               "counts_by_family_year": {k: dict(sorted(v.items())) for k, v in counts.items()},
                               "errors": errors, "point_in_time_audit_dev": aud, "documents": sorted(docs, key=lambda x: x["doc_id"])}, indent=1) + "\n")
    print(json.dumps({"documents": len(docs), "chunks": len(chunks), "errors": len(errors), "audit_pass": aud["pass"]}, indent=1))
    return 0 if not errors and aud["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
