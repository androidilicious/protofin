#!/usr/bin/env python3
"""Build the frozen Stage-2 DTB4WK risk-free file from its two hashed components.

Component 1: the pinned GitHub copy used in development (serorjb/fx_case,
             data/FRED/DTB4WK.csv), 2001-07-31 to 2025-08-05.
Component 2: the team's FRED export extending the series, 2025-08-06 to 2026-10-01.

Rule: keep component 1 byte-for-byte; append each data row of component 2,
converting FRED's '.' missing marker to an empty value (component 1's
convention). Dates must not overlap and must be strictly increasing.

Usage (from the repository root, after fetch_pinned_inputs.py):
    python stage2/scoring/build_dtb4wk_combined.py
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

PINNED = Path("stage2/data/_pinned/risk_free.csv")
PINNED_SHA = "379e39900aa048d17df36f384b6bb87bfb74498b2c673f797f3db4a876f65410"
EXTENSION = Path("stage2/data/risk_free/DTB4WK_FRED_extension_2025-08-06_to_2026-10-01.csv")
EXTENSION_SHA = "101ec9985c37326330abb58b05ab7167474d80d347bce12fb7e6894d85821d83"
OUT = Path("stage2/data/risk_free/DTB4WK_combined_2001-07-31_to_2026-10-01.csv")


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> int:
    pinned = PINNED.read_bytes()
    ext = EXTENSION.read_bytes()
    for name, data, expected in [("pinned", pinned, PINNED_SHA), ("extension", ext, EXTENSION_SHA)]:
        if sha256(data) != expected:
            print(f"HARD STOP: {name} hash mismatch", file=sys.stderr)
            return 2
    if not pinned.endswith(b"\n") or b"\r" in pinned or b"\r" in ext:
        print("HARD STOP: unexpected line endings", file=sys.stderr)
        return 2

    pinned_lines = pinned.decode().splitlines()
    ext_lines = ext.decode().splitlines()
    if pinned_lines[0] != "observation_date,DTB4WK" or ext_lines[0] != "DATE,DTB4WK":
        print("HARD STOP: unexpected headers", file=sys.stderr)
        return 2

    last_pinned = pinned_lines[-1].split(",")[0]
    out_rows = []
    prev = last_pinned
    for line in ext_lines[1:]:
        date, value = line.split(",")
        if date <= prev:
            print(f"HARD STOP: non-increasing or overlapping date {date}", file=sys.stderr)
            return 2
        out_rows.append(f"{date},{'' if value == '.' else value}")
        prev = date

    combined = pinned + ("\n".join(out_rows) + "\n").encode()
    OUT.write_bytes(combined)
    print(f"{OUT}  rows={len(pinned_lines) - 1 + len(out_rows)}  sha256={sha256(combined)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
