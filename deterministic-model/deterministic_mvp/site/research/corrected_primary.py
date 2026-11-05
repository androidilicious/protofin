"""Policy safeguards and a verifiable freeze for the corrected primary model.

Run the full development pipeline with research_backtest.py; freeze only after
its checks with `python src/corrected_primary.py freeze`. There is intentionally
no reserved-test execution command.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from deterministic_mvp import _parse_excel_dates

ROOT = Path(__file__).resolve().parents[1]
PRIMARY_SPEC_PATH = ROOT / "research/primary_spec.json"
FREEZE_PATH = ROOT / "research/primary_freeze.json"
SOURCE_FILES = ["corrected_primary.py", "research_backtest.py", "research_stability.py",
                "research_diagnostics.py", "research_inference.py", "deterministic_mvp.py"]
POLICY = ["policy_3m_level", "policy_6m_level", "policy_path_slope", "policy_3m_change", "policy_6m_change"]


def primary_spec():
    return json.loads(PRIMARY_SPEC_PATH.read_text())


def policy_source_dates(workbook):
    """Original feature observations by month, without creating ffilled sources."""
    tables = []
    for horizon in ["3m", "6m"]:
        raw = pd.read_excel(workbook, sheet_name=f"policy_{horizon}")
        frame = pd.DataFrame({f"source_{horizon}": _parse_excel_dates(raw.Date),
                              f"level_{horizon}": pd.to_numeric(raw[f"implied_policy_rate_{horizon}_pct"], errors="coerce")})
        frame["date"] = frame[f"source_{horizon}"].dt.to_period("M").dt.to_timestamp("M")
        frame = frame.sort_values("date")
        frame[f"change_{horizon}"] = frame[f"level_{horizon}"].diff()
        tables.append(frame)
    merged = tables[0].merge(tables[1], on="date", how="outer", validate="one_to_one")
    result = pd.DataFrame({"date": merged.date})
    for horizon in ["3m", "6m"]:
        for kind in ["level", "change"]:
            feature = f"policy_{horizon}_{kind}"
            result[f"{feature}__source"] = merged[f"source_{horizon}"].where(merged[f"{kind}_{horizon}"].notna())
    result["policy_path_slope__source"] = merged[["source_3m", "source_6m"]].max(axis=1).where(
        merged[["level_3m", "level_6m"]].notna().all(axis=1))
    return result.set_index("date")


def policy_support(x, processed_std, names, sources, rules):
    """Evaluate coverage/variation using this training fold only, never its test."""
    if sources is None or np.shape(sources) != x.shape or len(names) != x.shape[1]:
        raise ValueError("Corrected policy checks require per-feature source dates matching the training matrix")
    n_features = x.shape[1]
    supported = np.ones(n_features, dtype=bool)
    counts, bins = np.zeros(n_features, int), np.zeros(n_features, int)
    observed_std = np.zeros(n_features)
    reasons = [[] for _ in names]
    for i, name in enumerate(names):
        if not name.startswith("policy_"):
            continue
        ids = np.asarray(sources[:, i], dtype="datetime64[ns]")
        eligible = np.isfinite(x[:, i]) & ~np.isnat(ids)
        values, source_ids = x[eligible, i], ids[eligible]
        _, unique = np.unique(source_ids, return_index=True)
        values = values[unique]
        counts[i] = len(values)
        bins[i] = len(np.unique(np.rint(values / rules["resolution_percentage_points"])))
        observed_std[i] = values.std(ddof=0) if len(values) else 0.
        if counts[i] < rules["min_source_observations"]:
            reasons[i].append("insufficient_source_history")
        if bins[i] < rules["min_distinct_resolution_bins"]:
            reasons[i].append("insufficient_distinct_values")
        if observed_std[i] < rules["min_observed_std_percentage_points"]:
            reasons[i].append("near_constant_observations")
        if processed_std[i] < rules["min_processed_std_percentage_points"]:
            reasons[i].append("near_constant_processed_training")
        supported[i] = not reasons[i]
    return {"supported": supported, "unique_source_observations": counts,
            "distinct_resolution_bins": bins, "observed_source_std": observed_std,
            "disabled_reasons": reasons}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze_fingerprints():
    return {str(p.relative_to(ROOT)): digest(p) for p in
            [PRIMARY_SPEC_PATH, ROOT / "research/experiment_spec.json", ROOT / "requirements-primary.txt",
             *[ROOT / "src" / name for name in SOURCE_FILES]]}


def verify_freeze(path=FREEZE_PATH):
    manifest = json.loads(path.read_text())
    if manifest["files"] != freeze_fingerprints():
        raise ValueError("Frozen primary code/specification changed; use a new documented version, not an overwritten freeze")
    for name, fingerprint in manifest["inputs"].items():
        if digest(ROOT / name) != fingerprint:
            raise ValueError(f"Frozen input changed: {name}")
    return manifest


def freeze(path=FREEZE_PATH):
    if path.exists():
        return verify_freeze(path)
    report_path = ROOT / "research/outputs/research_results.json"
    report = json.loads(report_path.read_text())
    if report["primary"]["specification_sha256"] != digest(PRIMARY_SPEC_PATH):
        raise ValueError("Rerun the complete corrected-primary development pipeline before freezing")
    for name, fingerprint in report["code_hashes"].items():
        if digest(ROOT / "src" / name) != fingerprint:
            raise ValueError(f"Development run has stale code: {name}")
    if report["specification_sha256"] != digest(ROOT / "research/experiment_spec.json"):
        raise ValueError("Development experiment settings changed after the run")
    if not report["primary"]["numerical_acceptance"]["passed"]:
        raise ValueError("Corrected primary failed its recorded numerical acceptance checks; no freeze written")
    inputs = dict(report["input_hashes"])
    from research_backtest import WORKBOOK
    # Workbook is outside ROOT; use an explicit relative path for verifiability.
    inputs[os.path.relpath(WORKBOOK, ROOT)] = report["workbook_sha256"]
    for name, fingerprint in inputs.items():
        if digest(ROOT / name) != fingerprint:
            raise ValueError(f"Development run has stale input: {name}")
    manifest = {"id": primary_spec()["id"], "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
                "status": "Frozen corrected primary for a future separately authorized reserved test; development-selected, not independent confirmation.",
                "files": freeze_fingerprints(), "inputs": inputs,
                "development_results_sha256": digest(report_path),
                "environment": report["environment"],
                "numerical_acceptance": report["primary"]["numerical_acceptance"],
                "predictive_claims": report["primary"]["predictive_claims"],
                "reserved_test": {"evaluated": False, "team_nonexposure_confirmed": False, "requires_separate_authorization": True}}
    # Exclusive create: an existing freeze can be verified, never silently replaced.
    with path.open("x") as output:
        json.dump(manifest, output, indent=2, allow_nan=False)
        output.write("\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["freeze", "verify-freeze"])
    action = parser.parse_args().action
    manifest = freeze() if action == "freeze" else verify_freeze()
    print(json.dumps({"id": manifest["id"], "status": manifest["status"], "freeze_path": str(FREEZE_PATH)}))


if __name__ == "__main__":
    main()
