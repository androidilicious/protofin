"""Timestamped decision records: the single interface between a system and the shared evaluator.

A decision record states what one system decided at one decision time, which information it could
use, and where the decision came from. It never contains realised outcomes. The evaluator reads
only these records; it does not call any system's forecasting or allocation code.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

SCHEMA_VERSION = "1.0"
WEIGHT_TOL = 1e-9

# Keys that would carry realised outcomes. A record containing any of them is rejected, so an
# adapter cannot pass future returns through to the evaluator by accident.
FORBIDDEN_KEYS = frozenset({
    "r_spy", "r_tlt", "r_ief", "r_lqd", "realized_return", "realised_return", "actual_excess_return",
    "asset_total_return", "next_month_return", "future_return", "nav", "pnl",
})

GENERATION_MODES = frozenset({
    "computed_native",      # the system's own code run here on point-in-time inputs
    "saved_native_replay",  # outputs the system's own code saved earlier, replayed unchanged
    "live_native",          # the system's own code calling its model now
    "fallback_neutral",     # no valid output: native neutral portfolio (failure rule)
    "engineering_mock",     # mock model responses for engineering tests; never scored
})


class RecordError(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class DecisionRecord:
    system_id: str
    decision_month: str                 # "YYYY-MM"
    decision_time: str                  # ISO-8601 with offset, e.g. 2019-03-29T20:00:00-04:00
    info_cutoff: str                    # latest timestamp of any input used (ISO-8601 with offset)
    universe: Sequence[str]
    target_weights: Mapping[str, float]
    generation: Mapping[str, Any]       # mode, model, provenance, hashes
    forecast: Optional[Mapping[str, Any]] = None   # native forecast, e.g. {"horizon_months": 12, "kind": ..., "values": {...}}
    confidence: Optional[Mapping[str, Any]] = None
    native_detail: Optional[Mapping[str, Any]] = None
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        d = dataclasses.asdict(self)
        d["universe"] = list(self.universe)
        d["target_weights"] = dict(self.target_weights)
        return d


def _walk_keys(obj: Any) -> Iterable[str]:
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            yield str(k)
            yield from _walk_keys(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk_keys(v)


def validate(rec: DecisionRecord, *, allow_short: bool = False) -> None:
    """Raise RecordError if the record breaks the contract."""
    from datetime import datetime

    if rec.schema_version != SCHEMA_VERSION:
        raise RecordError(f"{rec.system_id} {rec.decision_month}: schema {rec.schema_version} != {SCHEMA_VERSION}")
    if len(rec.decision_month) != 7 or rec.decision_month[4] != "-":
        raise RecordError(f"bad decision_month {rec.decision_month!r}")
    try:
        dt = datetime.fromisoformat(rec.decision_time)
        ic = datetime.fromisoformat(rec.info_cutoff)
    except ValueError as e:
        raise RecordError(f"{rec.system_id} {rec.decision_month}: bad timestamp: {e}") from e
    if dt.tzinfo is None or ic.tzinfo is None:
        raise RecordError(f"{rec.system_id} {rec.decision_month}: timestamps must carry a UTC offset")
    if ic > dt:
        raise RecordError(f"{rec.system_id} {rec.decision_month}: info_cutoff {rec.info_cutoff} is after decision_time {rec.decision_time}")
    if dt.strftime("%Y-%m") != rec.decision_month:
        raise RecordError(f"{rec.system_id}: decision_time {rec.decision_time} is not in {rec.decision_month}")
    if set(rec.target_weights) != set(rec.universe):
        raise RecordError(f"{rec.system_id} {rec.decision_month}: weights {sorted(rec.target_weights)} != universe {sorted(rec.universe)}")
    total = sum(float(v) for v in rec.target_weights.values())
    if abs(total - 1.0) > 1e-6:
        raise RecordError(f"{rec.system_id} {rec.decision_month}: weights sum to {total}")
    if not allow_short and any(float(v) < -WEIGHT_TOL for v in rec.target_weights.values()):
        raise RecordError(f"{rec.system_id} {rec.decision_month}: negative weight")
    mode = rec.generation.get("mode")
    if mode not in GENERATION_MODES:
        raise RecordError(f"{rec.system_id} {rec.decision_month}: generation.mode {mode!r} not in {sorted(GENERATION_MODES)}")
    bad = FORBIDDEN_KEYS.intersection(_walk_keys(rec.to_dict()))
    if bad:
        raise RecordError(f"{rec.system_id} {rec.decision_month}: record carries outcome fields {sorted(bad)}")


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def record_hash(rec: DecisionRecord) -> str:
    return hashlib.sha256(canonical_json(rec.to_dict()).encode()).hexdigest()


def write_jsonl(records: Sequence[DecisionRecord], path: Path) -> str:
    """Write records (validated, sorted by month) and return the file's SHA-256."""
    recs = sorted(records, key=lambda r: (r.system_id, r.decision_month))
    seen = set()
    for r in recs:
        validate(r)
        key = (r.system_id, r.decision_month)
        if key in seen:
            raise RecordError(f"duplicate record {key}")
        seen.add(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in recs:
            f.write(canonical_json(r.to_dict()) + "\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> List[DecisionRecord]:
    out: List[DecisionRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        rec = DecisionRecord(**d)
        validate(rec)
        out.append(rec)
    return out
