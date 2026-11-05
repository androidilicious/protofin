"""The plugin contract: what an evidence source must return, and the checks the harness applies.

An Answer is one month's output. `stated` is the plugin's own signed view per fund (any units: the
calibration step rescales it, so only direction and relative size carry information). `features` are
the numbers the "either way" learner may use; the "as stated" rule uses `stated` only. `confidence`
and `trace` are recorded for the reader and never move the weights.
"""
from __future__ import annotations

import dataclasses
import math
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

import pandas as pd

FUND_SETS: Mapping[str, tuple[str, ...]] = {"spy_tlt": ("SPY", "TLT"), "spy_ief_lqd": ("SPY", "IEF", "LQD")}
KINDS = ("replay", "placebo")   # replay = saved answers, re-run from disk; live plugins are not allowed in the harness


@dataclasses.dataclass(frozen=True)
class Answer:
    month: str                                   # decision month "YYYY-MM": the month-end at which the answer was known
    stated: Mapping[str, float]                  # per fund: signed view; {} when the plugin states no direction (features only)
    features: Mapping[str, float] = dataclasses.field(default_factory=dict)
    confidence: float | None = None              # self-reported, 0..1; recorded, not used
    trace: Mapping[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class Manifest:
    name: str                                    # registry key, lower-case; the scorer reports it upper-case (DET, JEV, ...)
    title: str
    kind: str                                    # "replay" or "placebo"
    fund_sets: Sequence[str]
    description: str = ""
    author: str = ""
    data: Mapping[str, str] = dataclasses.field(default_factory=dict)   # fund_set -> path of the saved answers, relative to the repo
    exploratory: bool = False                    # kept out of the primary (Holm) family when true
    horizon_months: int = 1
    states_direction: bool = True                # false = features only; the "as stated" rule then falls back to the learner

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Manifest":
        known = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


class Plugin(Protocol):
    manifest: Manifest

    def answers(self, fund_set: str) -> list[Answer]: ...


class ContractError(ValueError):
    pass


def validate(answers: Sequence[Answer], manifest: Manifest, fund_set: str) -> None:
    """Raise ContractError on anything the harness cannot score."""
    if manifest.kind not in KINDS:
        raise ContractError(f"{manifest.name}: kind must be one of {KINDS}")
    if fund_set not in FUND_SETS:
        raise ContractError(f"unknown fund set {fund_set}")
    if fund_set not in manifest.fund_sets:
        raise ContractError(f"{manifest.name} does not support {fund_set}")
    assets = FUND_SETS[fund_set]
    seen = set()
    for a in answers:
        try:
            pd.Period(a.month, "M")
        except Exception as e:  # noqa: BLE001
            raise ContractError(f"{manifest.name}: bad month {a.month!r}") from e
        if len(a.month) != 7:
            raise ContractError(f"{manifest.name}: month must be YYYY-MM, got {a.month!r}")
        if a.month in seen:
            raise ContractError(f"{manifest.name}: month {a.month} answered twice")
        seen.add(a.month)
        if manifest.states_direction:
            missing = [x for x in assets if x not in a.stated]
            if missing:
                raise ContractError(f"{manifest.name} {a.month}: stated view missing for {missing}")
        elif a.stated:
            raise ContractError(f"{manifest.name}: states_direction is false but {a.month} has a stated view")
        for k, v in list(a.stated.items()) + list(a.features.items()):
            if v is not None and not isinstance(v, (int, float)):
                raise ContractError(f"{manifest.name} {a.month}: {k} is not a number")
        if a.confidence is not None and not (isinstance(a.confidence, (int, float)) and 0 <= a.confidence <= 1):
            raise ContractError(f"{manifest.name} {a.month}: confidence must be in [0, 1]")
        if not a.features and manifest.kind != "placebo" and not a.stated:
            raise ContractError(f"{manifest.name} {a.month}: an answer needs a stated view or features")


def to_frame(answers: Sequence[Answer], fund_set: str, manifest: Manifest) -> pd.DataFrame | None:
    """The raw-signal table the level field scores: one row per month, feature columns, and the stated
    view per fund in `attrs['stated']`. None for the placebo (no signal at all)."""
    if manifest.kind == "placebo" or not answers:
        return None
    assets = FUND_SETS[fund_set]
    rows = {}
    for a in answers:
        row = {k: (math.nan if v is None else float(v)) for k, v in a.features.items()}
        for x in assets:
            if x in a.stated:
                row[f"stated_{x}"] = math.nan if a.stated[x] is None else float(a.stated[x])
        rows[pd.Period(a.month, "M")] = row
    df = pd.DataFrame.from_dict(rows, orient="index").sort_index()
    feat_cols = [c for c in df.columns if not c.startswith("stated_")]
    out = df[feat_cols].copy()          # the learner sees the features only; a plugin that wants its stated
    if manifest.states_direction:       # view learnable lists it among the features as well
        out.attrs["stated"] = {x: df[f"stated_{x}"] for x in assets}
    return out


def coverage(answers: Sequence[Answer], months: Sequence[pd.Period], fund_set: str, manifest: Manifest) -> float:
    """Share of the scored months with a usable answer (a finite stated view, or any feature)."""
    if manifest.kind == "placebo":
        return 1.0
    assets = FUND_SETS[fund_set]
    by_month = {pd.Period(a.month, "M"): a for a in answers}
    ok = 0
    for m in months:
        a = by_month.get(m)
        if a is None:
            continue
        if manifest.states_direction:
            if all(a.stated.get(x) is not None and math.isfinite(a.stated[x]) for x in assets):
                ok += 1
        elif any(v is not None and math.isfinite(v) for v in a.features.values()):
            ok += 1
    return ok / len(months) if months else 0.0


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
