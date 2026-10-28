#!/usr/bin/env python3
"""Build AP3 graph vintages and channel libraries for decision years 2015..2026 (vintages 2014..2025).

Libraries contain claim-derived text, so they are written under native_backtest/data/_external
(git-ignored; the claims data has no published licence). The committed manifest records only
counts and SHA-256 hashes. A determinism check rebuilds one vintage from scratch and requires a
byte-identical library.

Usage: python -m native_backtest.scripts.build_ap3_libraries
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from native_backtest.ap3.graph_vintage import build_vintage, load_concepts, load_macro_claims
from native_backtest.ap3.library import derive_library

ROOT = Path(__file__).resolve().parents[2]
LIBDIR = ROOT / "native_backtest/data/_external/ap3_libraries"
MANIFEST = ROOT / "native_backtest/out/ap3/ap3_library_manifest_v1.json"


def main() -> int:
    concepts = load_concepts()
    LIBDIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for year in range(2014, 2026):
        lib = derive_library(build_vintage(year, concepts), concepts)
        path = LIBDIR / f"library_v{concepts['version']}_vintage{year}.json"
        path.write_text(json.dumps(lib, sort_keys=True, separators=(",", ":")))
        from collections import Counter
        rows.append({"vintage_year": year, "decision_year": year + 1, **lib["vintage_stats"], "n_paths": lib["n_paths"],
                     "paths_by_channel": dict(Counter(e["channel"] for e in lib["entries"])),
                     "concepts_missing": lib["concepts_missing_in_vintage"],
                     "library_sha256": lib["library_sha256"], "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        print(year, lib["n_paths"], lib["library_sha256"][:16])
    # determinism: rebuild the 2018 vintage from a fresh claims load and compare
    load_macro_claims.cache_clear()
    again = derive_library(build_vintage(2018, concepts), concepts)
    first = next(r for r in rows if r["vintage_year"] == 2018)
    det = {"vintage_year": 2018, "first_sha256": first["library_sha256"], "rebuild_sha256": again["library_sha256"],
           "identical": first["library_sha256"] == again["library_sha256"]}
    man = {"concepts_version": concepts["version"], "concepts_sha256": hashlib.sha256((ROOT / "native_backtest/ap3/concepts_v1.json").read_bytes()).hexdigest(),
           "claims_manifest": "native_backtest/config/ap3_claims_manifest_v1.json", "causetrace_vendored_commit": "82abe0a",
           "libraries": rows, "determinism_check": det}
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(man, indent=1))
    print(json.dumps(det))
    return 0 if det["identical"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
