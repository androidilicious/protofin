"""Stochastic view evaluation: the same frozen input, the same committee, N sampled runs.

    frozen prompts (one snapshot)
        -> committee run 1 .. N at temperature > 0   (only the LLM sampling varies)
        -> per-asset distribution of the CIO's view Q^(r) and the reported confidence per run
        -> Q = mean over valid runs, s^2 = sample variance over valid runs
        -> Black-Litterman with Omega = c(label) * tau * Sigma + diag(s^2)   (allocation.view_omega)

Two uncertainty signals are kept apart:
  reported confidence  what the CIO says (High / Medium / Low), aggregated as the modal label
  empirical dispersion what we observe across repeated runs on identical input

confidence_mode chooses which of them sets Omega:
  reported   Omega = c(reported label)  * tau * Sigma               (original rule, Q = mean view)
  empirical  Omega = c("Medium")        * tau * Sigma + diag(s^2)   (self-report ignored, neutral c)
  combined   Omega = c(reported label)  * tau * Sigma + diag(s^2)
The EPU/GPR regime gate is an external data signal, not a self-report, so the caller applies it to
the label in every mode, exactly as in the deterministic path.

Everything here except run_stochastic_committee is free of I/O, so a historical backtest can call
decide_from_runs() once per snapshot with the stored runs. See docs/EMPIRICAL_UNCERTAINTY.md.
"""
import hashlib
import json
import os
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from typing import Optional

import numpy as np

import committee
from allocation import OMEGA_SCALE, TAU, allocate, view_omega
from macro_indexes import downgrade_confidence

CONFIDENCE_MODES = ("reported", "empirical", "combined")
ASSETS = ("SPY", "TLT")
NEUTRAL_LABEL = "Medium"                      # c = 1: the label used when the self-report is ignored
CONFIDENCE_ORDER = ("Low", "Medium", "High")  # ties in the modal label resolve to the lower one

DEFAULT_TEMPERATURE = 0.2
DEFAULT_N_RUNS = 5
DEFAULT_CONFIDENCE_MODE = "combined"


# ------------------------------------------------------------------ configuration
@dataclass(frozen=True)
class StochasticConfig:
    """enabled=False keeps the original single deterministic call (temperature 0, seed 42).

    seed: optional base seed; run r is sent seed + r so the runs still differ. Providers treat a
    seed as best-effort, so seed + temperature does not guarantee identical replies.
    """
    enabled: bool = False
    temperature: float = DEFAULT_TEMPERATURE
    n_runs: int = DEFAULT_N_RUNS
    seed: Optional[int] = None
    confidence_mode: str = DEFAULT_CONFIDENCE_MODE

    def __post_init__(self):
        if self.confidence_mode not in CONFIDENCE_MODES:
            raise ValueError(f"confidence_mode must be one of {CONFIDENCE_MODES}, got {self.confidence_mode!r}")
        if self.n_runs < 2:
            raise ValueError("n_runs must be at least 2 to measure run-to-run dispersion")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError(f"temperature must be in [0, 2], got {self.temperature}")

    def run_seed(self, run_index):
        return None if self.seed is None else self.seed + run_index


def _opt_int(value):
    return None if value in (None, "") else int(value)


def config_from_env(env=None):
    """STOCHASTIC_VIEWS=1, VIEW_TEMPERATURE, VIEW_N_RUNS, VIEW_SEED, CONFIDENCE_MODE (see .env.example)."""
    env = os.environ if env is None else env
    return StochasticConfig(enabled=env.get("STOCHASTIC_VIEWS", "0") == "1",
                            temperature=float(env.get("VIEW_TEMPERATURE", DEFAULT_TEMPERATURE)),
                            n_runs=int(env.get("VIEW_N_RUNS", DEFAULT_N_RUNS)),
                            seed=_opt_int(env.get("VIEW_SEED")),
                            confidence_mode=env.get("CONFIDENCE_MODE", DEFAULT_CONFIDENCE_MODE))


def with_overrides(config, args):
    """Per-request overrides from a mapping such as Flask's request.args."""
    changes = {}
    if "stochastic" in args:
        changes["enabled"] = args["stochastic"] == "1"
    if "temperature" in args:
        changes["temperature"] = float(args["temperature"])
    if "n_runs" in args:
        changes["n_runs"] = int(args["n_runs"])
    if "seed" in args:
        changes["seed"] = _opt_int(args["seed"])
    if "confidence_mode" in args:
        changes["confidence_mode"] = args["confidence_mode"]
    return replace(config, **changes) if changes else config


def snapshot_id(prompts):
    """Hash of the frozen prompts, which carry every input the committee sees."""
    return hashlib.sha256(json.dumps(prompts, sort_keys=True).encode("utf-8")).hexdigest()[:16]


# ------------------------------------------------------------------ running
def run_stochastic_committee(prompts, call, config, parallel=True):
    """call(prompt, temperature, seed) -> reply text. Runs the unchanged committee N times on the
    same prompts; returns the committee outputs, each tagged with its run index and seed."""
    runs = []
    for r in range(config.n_runs):
        seed = config.run_seed(r)
        com = committee.run_committee(prompts, lambda p, s=seed: call(p, config.temperature, s), parallel=parallel)
        runs.append({**com, "run": r, "seed": seed})
    return runs


def run_view(com):
    """Per-run summary from a committee output: the view, the self-report and structured rationale."""
    cio = com["cio"]
    return {"run": com.get("run"), "seed": com.get("seed"), "valid": not com["problems"], "problems": com["problems"],
            "spy_q": cio["spy_q"], "tlt_q": cio["tlt_q"], "confidence": cio["confidence"],
            "cio": cio["cio"], "grounding": cio["grounding"],
            "economist_q": [com["economist"]["spy"], com["economist"]["tlt"]],
            "risk_q": [com["risk"]["spy"], com["risk"]["tlt"]]}


# ------------------------------------------------------------------ aggregation (pure)
def modal_confidence(labels):
    """Most frequent label; ties go to the lower confidence so aggregation never adds trust."""
    counts = {c: labels.count(c) for c in CONFIDENCE_ORDER}
    top = max(counts.values())
    return next(c for c in CONFIDENCE_ORDER if counts[c] == top), counts


def aggregate_views(run_views):
    """Per-asset mean, sample std/variance (ddof=1), min, max over VALID runs, in percent.

    empirical_var is the per-asset variance in decimal^2 (for Omega); None with fewer than 2 valid runs.
    """
    valid = [r for r in run_views if r["valid"]]
    out = {"n_runs": len(run_views), "n_valid": len(valid), "assets": {}, "empirical_var": None,
           "confidence_reported": None, "confidence_counts": None,
           "invalid_runs": [{"run": r["run"], "problems": r["problems"]} for r in run_views if not r["valid"]]}
    for asset in ASSETS:
        vals = [float(r[asset.lower() + "_q"]) for r in valid]
        a = np.array(vals)
        n = len(vals)
        out["assets"][asset] = {
            "values": vals,
            "mean": float(a.mean()) if n else None,
            "std": float(a.std(ddof=1)) if n >= 2 else None,
            "var": float(a.var(ddof=1)) if n >= 2 else None,
            "min": float(a.min()) if n else None,
            "max": float(a.max()) if n else None,
        }
    if len(valid) >= 2:
        out["empirical_var"] = [out["assets"][a]["var"] / 1e4 for a in ASSETS]
    if valid:
        out["confidence_reported"], out["confidence_counts"] = modal_confidence([r["confidence"] for r in valid])
    return out


def resolve_mode(mode, agg):
    """-> (effective_mode, confidence label before the regime gate, empirical_var or None, note)."""
    if mode not in CONFIDENCE_MODES:
        raise ValueError(f"confidence_mode must be one of {CONFIDENCE_MODES}, got {mode!r}")
    reported = agg["confidence_reported"]
    if mode == "reported":
        return "reported", reported, None, "Omega from the reported confidence only"
    if agg["empirical_var"] is None:
        return ("reported", reported, None,
                f"{mode} mode needs at least 2 valid runs ({agg['n_valid']} valid); fell back to reported confidence")
    if mode == "empirical":
        return "empirical", NEUTRAL_LABEL, agg["empirical_var"], "Omega from run-to-run dispersion; self-report ignored (neutral c = 1)"
    return "combined", reported, agg["empirical_var"], "Omega from reported confidence plus run-to-run dispersion"


def stability_metrics(agg, sigma, confidence_used, empirical_var, tau=TAU):
    """Per asset: dispersion ratio s / sqrt(tau * Sigma_ii) (0 = identical runs; mode-independent),
    and the diagonal Omega split into its reported and empirical parts."""
    c = OMEGA_SCALE[confidence_used]
    out = {}
    for i, asset in enumerate(ASSETS):
        std = agg["assets"][asset]["std"]
        prior_sd = float(np.sqrt(tau * sigma[i, i]))
        omega_rep = float(c * tau * sigma[i, i])
        omega_emp = float(empirical_var[i]) if empirical_var is not None else 0.0
        out[asset] = {"dispersion_ratio": None if std is None else (std / 100.0) / prior_sd,
                      "omega_reported_part": omega_rep, "omega_empirical_part": omega_emp,
                      "empirical_share_of_omega": omega_emp / (omega_rep + omega_emp)}
    return out


def decide_from_runs(sigma, run_views, rf_pct, mode=DEFAULT_CONFIDENCE_MODE, regime=None, previous_spy=None):
    """Aggregate the runs and allocate once; also allocate each valid run on its own (reported
    confidence, as the deterministic path would have) to expose the distribution of weights a single
    stochastic run could have produced. Shared by the live server and any future backtest."""
    sigma = np.asarray(sigma, dtype=float)
    agg = aggregate_views(run_views)
    gate = (lambda lbl: downgrade_confidence(lbl, regime)) if regime else (lambda lbl: lbl)
    if agg["n_valid"] == 0:
        decision = allocate(sigma, None, NEUTRAL_LABEL, rf_pct, previous_spy)
        return {"aggregate": agg, "mode": mode, "effective_mode": "prior_only", "confidence_label": None,
                "confidence_used": None, "empirical_var": None, "omega": None, "decision": decision,
                "stability": None, "per_run_target_spy": [], "target_spy_distribution": None,
                "note": "no valid run; equilibrium prior only"}
    effective, label, ev, note = resolve_mode(mode, agg)
    used = gate(label)
    q = [agg["assets"][a]["mean"] for a in ASSETS]
    decision = allocate(sigma, q, used, rf_pct, previous_spy, empirical_var=ev)
    per_run = [allocate(sigma, [r["spy_q"], r["tlt_q"]], gate(r["confidence"]), rf_pct, None)["target_spy"]
               for r in run_views if r["valid"]]
    pr = np.array(per_run)
    return {"aggregate": agg, "mode": mode, "effective_mode": effective, "confidence_label": label,
            "confidence_used": used, "empirical_var": ev, "omega": decision["omega"].tolist(), "decision": decision,
            "stability": stability_metrics(agg, sigma, used, ev),
            "per_run_target_spy": [float(x) for x in per_run],
            "target_spy_distribution": {"mean": float(pr.mean()), "std": float(pr.std(ddof=1)) if len(pr) >= 2 else None,
                                        "min": float(pr.min()), "max": float(pr.max())},
            "note": note}


def evaluation_record(config, model, snap_id, run_views, outcome, fingerprint=None, timestamp=None):
    """JSON-serialisable audit record: everything needed to reproduce or re-score the evaluation."""
    return {"timestamp": timestamp or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model": model, "config": asdict(config), "snapshot_id": snap_id, "fingerprint": fingerprint,
            "runs": run_views, "aggregate": outcome["aggregate"],
            "q_mean_pct": [outcome["aggregate"]["assets"][a]["mean"] for a in ASSETS],
            "mode": outcome["mode"], "effective_mode": outcome["effective_mode"],
            "confidence_label": outcome["confidence_label"], "confidence_used": outcome["confidence_used"],
            "empirical_var": outcome["empirical_var"], "omega": outcome["omega"],
            "stability": outcome["stability"], "per_run_target_spy": outcome["per_run_target_spy"],
            "target_spy_distribution": outcome["target_spy_distribution"], "note": outcome["note"]}
