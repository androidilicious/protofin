#!/usr/bin/env python3
"""Fetch every pinned Stage-2 market/signal input listed in a data snapshot manifest.

Each source is fetched from its pinned GitHub commit and blob, written to
stage2/data/_pinned/<role><ext>, and verified against the manifest SHA-256.
A hash mismatch is a hard stop. The _pinned folder is git-ignored because the
raw series are third-party copies that the snapshot policy does not republish.

Usage (from the repository root):
    python stage2/scoring/fetch_pinned_inputs.py \
        --manifest stage2/reproducibility/stage2_data_snapshot_manifest_v2_2026-10-27.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_blob(repo: str, commit: str, blob: str, dest: Path, cache: Path) -> None:
    d = cache / repo.replace("/", "_")
    if not d.exists():
        subprocess.run(["git", "init", "-q", str(d)], check=True)
        subprocess.run(["git", "-C", str(d), "remote", "add", "o", f"https://github.com/{repo}"], check=True)
    subprocess.run(["git", "-C", str(d), "fetch", "-q", "--depth", "1", "--filter=blob:none", "o", commit], check=True)
    data = subprocess.run(["git", "-C", str(d), "cat-file", "-p", blob], check=True, capture_output=True).stdout
    dest.write_bytes(data)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=Path("stage2/data/_pinned"))
    args = ap.parse_args()

    manifest = json.loads(args.manifest.read_text())
    args.out.mkdir(parents=True, exist_ok=True)
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        for s in manifest["sources"]:
            if "repo" not in s:
                continue
            ext = Path(s["path"]).suffix or ".csv"
            dest = args.out / f"{s['role']}{ext}"
            if not (dest.exists() and sha256(dest) == s["sha256"]):
                fetch_blob(s["repo"], s["commit"], s["git_blob_sha"], dest, Path(tmp))
            got = sha256(dest)
            ok = got == s["sha256"]
            failures += not ok
            print(f"{'OK      ' if ok else 'MISMATCH'} {s['role']:28s} {dest}  {got}")
    if failures:
        print(f"{failures} pinned input(s) failed hash verification", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
