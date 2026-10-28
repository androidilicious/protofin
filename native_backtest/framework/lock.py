"""Protected historical window.

Scoring (computing any portfolio outcome) for a decision month at or after the protected start is
refused unless a signed GO record exists, the operator passes the opening token, and the decision
records being scored are byte-identical to those frozen in the GO record. Building decision
records for those months is allowed; it never touches outcomes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping, Optional

import pandas as pd

OPENING_TOKEN = "OPEN_NATIVE_FOUR_SYSTEM_WINDOW"


class WindowLocked(RuntimeError):
    pass


def locked_months(months: Iterable[pd.Period], protected_start: str) -> list:
    start = pd.Period(protected_start, "M")
    return [m for m in months if m >= start]


def assert_scoring_allowed(
    months: Iterable[pd.Period],
    *,
    protected_start: str,
    go_record_path: Optional[Path] = None,
    token: Optional[str] = None,
    decision_file_hashes: Optional[Mapping[str, str]] = None,
) -> None:
    months = list(months)
    blocked = locked_months(months, protected_start)
    if not blocked:
        return
    first = min(blocked)
    if go_record_path is None or token != OPENING_TOKEN:
        raise WindowLocked(
            f"{len(blocked)} requested month(s) from {first} are in the protected window; "
            "scoring them needs a signed GO record and the opening token"
        )
    rec = json.loads(Path(go_record_path).read_text())
    if rec.get("decision") != "GO" or not rec.get("signed_by"):
        raise WindowLocked(f"GO record {go_record_path} does not state a signed GO")
    frozen = rec.get("frozen_decision_files_sha256", {})
    for name, h in (decision_file_hashes or {}).items():
        if frozen.get(name) != h:
            raise WindowLocked(f"decision file {name} hash {h} differs from the GO record's {frozen.get(name)}")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
