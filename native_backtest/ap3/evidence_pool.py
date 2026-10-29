"""AP3 evidence pools for the two Causal RAG versions.

The Testing Agent (plan prompt, balanced BM25 retrieval, the native causal-rag-mvp assessor with its
verbatim-quote validation, mediator tests and the written rubric) is the same in both versions. Only the
pool of excerpts it may retrieve from differs:

Causal RAG — Reduced Evidence (variant ``reduced_evidence``)
  1. research-claim excerpts: the CauseTrace research records behind the hypothesis's cited pathways and
     behind the candidate rival pathways, from the year-filtered graph vintage (papers dated before the
     decision year). The native assessor treats general theory as insufficient, so these excerpts can
     ground or contradict a mechanism but cannot by themselves show it operating in the period;
  2. numerical data notes, written deterministically from point-in-time data visible at the decision time:
     - month-to-date moves of every mediator series in the point-in-time store, with the z-score against
       same-length changes over the previous 36 months (the mediator test's own computation);
     - release-window moves: for each macro or FOMC trigger in the packet, the change of every mediator series
       from the close before the release day to the latest value visible at the decision time (release dates
       from the ALFRED vintage record of the issuing agency's headline series, FOMC dates from the calendar;
       ISM has no official-source release record, so it gets no release-window notes). A window with no
       observation after the release visible by the decision time yields no note;
     - the standardised surprise of every macro release in the AP1 point-in-time panel.
     Notes for the series the hypothesis itself predicts are left out of that hypothesis's pool, because
     those series are already judged by the deterministic mediator test (no double counting).
     A series with no point-in-time data (FF_FUTURES_6M until the Bloomberg export arrives) yields no note
     and is reported as unavailable; nothing is substituted for it.

Causal RAG — With Historical Documents (variant ``historical_documents``)
  The reduced-evidence pool plus the official-document corpus chunks eligible at the decision time
  (available_at strictly before it). Everything else is identical, so the difference between the versions
  measures the contribution of historical textual evidence.

Every excerpt carries available_at_et; pool() asserts that each one predates the decision time and that no
canary is present. Asset returns are never included (the Testing Agent never sees returns or labels).
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd

from native_backtest.ap3 import corpus
from native_backtest.ap3.mediators import MediatorStore, mediator_test

ROOT = Path(__file__).resolve().parents[2]
VARIANTS_FILE = ROOT / "native_backtest/ap3/variants_v1.json"
ALFRED = ROOT / "native_backtest/data/ap3_corpus/alfred_release_vintages_v1.json"
ET = "America/New_York"
RELEASE_FAMILY = {"NFP": "bls_employment_situation", "AHE": "bls_employment_situation", "CPI": "bls_cpi", "CORE_CPI": "bls_cpi",
                  "PPI": "bls_ppi", "RETAIL_SALES": "census_advance_retail_sales", "INDUSTRIAL_PRODUCTION": "fed_g17_industrial_production"}
# Short names used inside data notes (the IG spread stays labelled as a proxy).
NOTE_LABELS = {"UST2Y": "2-year Treasury yield (percent)", "UST10Y": "10-year Treasury yield (percent)",
               "SLOPE_10Y3M": "10-year minus 3-month Treasury yield spread (percentage points)",
               "BEI5Y": "5-year breakeven inflation rate (percent)",
               "IG_SPREAD": "investment-grade credit spread proxy, Baa corporate yield minus 10-year Treasury yield (percentage points)",
               "VIX": "VIX equity volatility index (points)",
               "FF_FUTURES_6M": "fed funds rate expected six months ahead from fed funds futures (percent)"}
RELEASE_TIME = {"bls_employment_situation": "08:30", "bls_cpi": "08:30", "bls_ppi": "08:30", "census_advance_retail_sales": "08:30",
                "fed_g17_industrial_production": "09:15", "FOMC": "14:00"}


class EvidenceError(RuntimeError):
    pass


def load_variants() -> dict:
    return json.loads(VARIANTS_FILE.read_text())


def _cid(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]


def research_claim_chunks(records: Iterable[dict], role: str) -> List[dict]:
    """One excerpt per research record (paper x edge). available_at: end of the paper's year, which the
    graph vintage already places before the decision year."""
    out, seen = [], set()
    for r in records:
        if not r.get("paper_id") or r.get("year") is None:
            continue
        src, dst = [s.strip() for s in r["edge"].split("->", 1)]
        key = (r["paper_id"], r["edge"])
        if key in seen:
            continue
        seen.add(key)
        method = r.get("causal_inference_method") or "not recorded"
        text = (f"Research claim from the economics literature (working paper {r['paper_id']}, {int(r['year'])}): "
                f"\"{r.get('title') or 'untitled'}\". The paper reports that {src} affects {dst}. "
                f"Recorded method: {method}; evidence class: {r.get('evidence_class')}. "
                f"This is a published research claim, not a measurement of conditions in the decision month.")
        doc_id = f"RC_{r['paper_id']}"
        out.append({"doc_id": doc_id, "chunk_id": f"{doc_id}_{_cid(r['edge'])}#c000", "text": text,
                    "available_at_et": pd.Timestamp(f"{int(r['year'])}-12-31 23:59", tz=ET).isoformat(),
                    "role": "research_claim", "pool_role": role, "family": "research_claim"})
    return out


def _fmt_change(x: float) -> str:
    return f"{x:+.2f}"


def mediator_notes(store: MediatorStore, labels: Dict[str, str], series: Iterable[str], window_start, decision_time,
                   ref_months: int, exclude: Iterable[str] = ()) -> List[dict]:
    """Neutral month-to-date data notes. The z-score is the mediator test's own computation (sign-free)."""
    exclude = set(exclude)
    out = []
    t = pd.Timestamp(decision_time)
    for name in series:
        if name in exclude or name not in store.series:
            continue
        r = mediator_test(store, name, 1, window_start, t, ref_months, z_threshold=math.inf)
        if r["result"] == "unavailable" or r.get("z") is None:
            continue
        visible = store.asof(name, t)
        last = visible[visible["date"] == pd.Timestamp(r["window_end"])]
        avail = pd.Timestamp(last["available_at"].max()).tz_convert(ET)
        direction = "rose" if r["change"] > 0 else ("fell" if r["change"] < 0 else "was unchanged")
        label = labels.get(name, name)
        text = (f"Market data note, {label}: between {r['window_start']} and {r['window_end']} the series {direction} "
                f"by {_fmt_change(r['change'])} ({r['z']:+.1f} standard deviations relative to changes of the same length "
                f"over the previous {ref_months} months). Value as published by {avail.strftime('%Y-%m-%d %H:%M')} ET.")
        doc_id = f"DN_{name}_{str(t.date())}"
        out.append({"doc_id": doc_id, "chunk_id": f"{doc_id}#c000", "text": text, "available_at_et": avail.isoformat(),
                    "role": "data_note", "pool_role": "market", "family": "data_note", "series": name,
                    "value_change": r["change"], "z": r["z"]})
    return out


def release_dates() -> Dict[str, List[str]]:
    fams = json.loads(ALFRED.read_text())["families"]
    return {trig: sorted(fams[f]["vintage_dates"]) for trig, f in RELEASE_FAMILY.items() if f in fams}


def trigger_release(trigger: dict, decision_time, dates: Dict[str, List[str]]) -> Optional[tuple]:
    """(release datetime ET, source) of the release behind a packet trigger, or None."""
    t = pd.Timestamp(decision_time)
    month_start = pd.Timestamp(t.year, t.month, 1, tz=ET)
    if trigger["trigger"] == "FOMC" and trigger.get("date"):
        rel = pd.Timestamp(f"{trigger['date']} {RELEASE_TIME['FOMC']}", tz=ET)
        return (rel, "FOMC calendar") if rel < t else None
    fam = RELEASE_FAMILY.get(trigger["trigger"])
    if fam is None:
        return None
    cands = [pd.Timestamp(f"{d} {RELEASE_TIME[fam]}", tz=ET) for d in dates.get(trigger["trigger"], [])]
    cands = [c for c in cands if month_start <= c < t]
    return (max(cands), "ALFRED vintage date of the headline series") if cands else None


def release_window_notes(store: MediatorStore, labels: Dict[str, str], series: Iterable[str], packet: dict, trigger_labels: Dict[str, str],
                         ref_months: int, dates: Dict[str, List[str]], exclude: Iterable[str] = ()) -> List[dict]:
    exclude = set(exclude)
    t = pd.Timestamp(packet["decision_time"])
    out, done = [], set()
    for trig in packet["triggers"]:
        if trig["trigger"] == "MARKET_STRESS":
            continue
        rel = trigger_release(trig, t, dates)
        if rel is None:
            continue
        rel_time, src = rel
        key = (trig["trigger"], str(rel_time.date()))
        if key in done:
            continue
        done.add(key)
        ws = (rel_time.normalize() - pd.Timedelta(days=1)).tz_localize(None)
        for name in series:
            if name in exclude or name not in store.series:
                continue
            r = mediator_test(store, name, 1, ws, t, ref_months, z_threshold=math.inf)
            if r["result"] == "unavailable" or r.get("z") is None:
                continue
            if pd.Timestamp(r["window_end"]) < rel_time.normalize().tz_localize(None):
                continue          # no close on or after the release day is visible by the decision time
            visible = store.asof(name, t)
            avail = pd.Timestamp(visible[visible["date"] == pd.Timestamp(r["window_end"])]["available_at"].max()).tz_convert(ET)
            direction = "rose" if r["change"] > 0 else ("fell" if r["change"] < 0 else "was unchanged")
            label = trigger_labels.get(trig["trigger"], trig["trigger"])
            text = (f"Market data note, {labels.get(name, name)}: from the close before the {label} on {rel_time.date()} "
                    f"({rel_time.strftime('%H:%M')} ET) to the latest value published by the decision time ({r['window_end']}), the series "
                    f"{direction} by {_fmt_change(r['change'])} ({r['z']:+.1f} standard deviations relative to changes of the same length "
                    f"over the previous {ref_months} months). Release date source: {src}.")
            doc_id = f"DN_{name}_{trig['trigger']}_{rel_time.date()}"
            out.append({"doc_id": doc_id, "chunk_id": f"{doc_id}#c000", "text": text, "available_at_et": avail.isoformat(),
                        "role": "data_note", "pool_role": "market", "family": "data_note", "series": name,
                        "window": "release_to_decision", "trigger": trig["trigger"], "value_change": r["change"], "z": r["z"]})
    return out


def surprise_notes(packet: dict, trigger_labels: Dict[str, str]) -> List[dict]:
    """Notes for every macro release in the AP1 point-in-time panel row of the decision month."""
    t = pd.Timestamp(packet["decision_time"])
    stamp = (t - pd.Timedelta(minutes=1)).isoformat()   # panel values are fixed before the decision time
    out = []
    for key, z in sorted(packet.get("all_surprises_z", {}).items()):
        if z is None:
            continue
        side = "above" if z > 0 else ("below" if z < 0 else "in line with")
        label = trigger_labels.get(key, key)
        text = (f"Macroeconomic data note, {label}: the latest release before the decision time came in {abs(z):.1f} standard "
                f"deviations {side} the consensus expectation (point-in-time standardised surprise, prior-release standardisation).")
        doc_id = f"DN_{key}_{str(t.date())}"
        out.append({"doc_id": doc_id, "chunk_id": f"{doc_id}#c000", "text": text, "available_at_et": stamp,
                    "role": "data_note", "pool_role": "macro", "family": "data_note", "series": key, "z": z})
    return out


def check_point_in_time(pool: List[dict], decision_time) -> None:
    t = pd.Timestamp(decision_time)
    late = [c["chunk_id"] for c in pool if pd.Timestamp(c["available_at_et"]) >= t]
    canary = [c["chunk_id"] for c in pool if c.get("role") == "canary" or corpus.CANARY_TAG in c["text"]]
    if late or canary:
        raise EvidenceError(f"point-in-time violation at {decision_time}: late={late[:3]} canary={canary[:3]}")
    ids = [c["chunk_id"] for c in pool]
    if len(ids) != len(set(ids)):
        raise EvidenceError("duplicate chunk ids in the evidence pool")


class EvidencePool:
    """Builds the per-hypothesis pool for one variant. Construct once per run."""

    def __init__(self, variant: str, store: MediatorStore, labels: Dict[str, str], trigger_labels: Dict[str, str],
                 limits: dict, corpus_chunks: Optional[List[dict]] = None):
        spec = load_variants()["variants"].get(variant)
        if spec is None:
            raise EvidenceError(f"unknown Causal RAG variant {variant}")
        if "official_documents" in spec["evidence"] and corpus_chunks is None:
            raise EvidenceError(f"variant {variant} needs the official-document corpus, which is not loaded")
        self.variant, self.spec = variant, spec
        self.store, self.trigger_labels, self.limits = store, trigger_labels, limits
        self.labels = {**labels, **NOTE_LABELS}
        if spec.get("mediator_inventory") == "v2_policy_proxy":
            self.labels["FF_FUTURES_6M"] = ("expected policy-path PROXY, 2-year Treasury yield minus 4-week Treasury bill rate "
                                           "(percentage points; not fed funds futures)")
        self.corpus_chunks = corpus_chunks if "official_documents" in spec["evidence"] else None
        self._month_cache: Dict[str, List[dict]] = {}
        self._dates = release_dates()

    def _month_notes(self, packet: dict, window_start) -> List[dict]:
        k = packet["decision_month"]
        if k not in self._month_cache:
            ref = self.limits["mediators"]["z_reference_months"]
            med = mediator_notes(self.store, self.labels, self.limits["mediators"]["series"], window_start, packet["decision_time"], ref)
            med += release_window_notes(self.store, self.labels, self.limits["mediators"]["series"], packet, self.trigger_labels, ref, self._dates)
            docs = corpus.eligible(self.corpus_chunks, packet["decision_time"]) if self.corpus_chunks is not None else []
            self._month_cache[k] = med + surprise_notes(packet, self.trigger_labels) + docs
        return self._month_cache[k]

    def for_hypothesis(self, packet: dict, hyp: dict, rival_records: List[dict], window_start) -> List[dict]:
        own = {m["series"] for m in hyp.get("predicted_mediators", [])}
        pool, seen = [], set()
        for c in research_claim_chunks(hyp.get("research_records", []), "hypothesis") + research_claim_chunks(rival_records, "rival"):
            if c["chunk_id"] not in seen:          # a record behind both the hypothesis and a rival appears once
                pool.append(c)
                seen.add(c["chunk_id"])
        for c in self._month_notes(packet, window_start):
            if c.get("family") == "data_note" and c.get("pool_role") == "market" and c["series"] in own:
                continue
            if c["chunk_id"] not in seen:
                pool.append(c)
                seen.add(c["chunk_id"])
        check_point_in_time(pool, packet["decision_time"])
        return pool


def pool_summary(pool: List[dict]) -> dict:
    kinds: Dict[str, int] = {}
    for c in pool:
        k = c.get("family") if c.get("family") in ("research_claim", "data_note") else "official_document"
        kinds[k] = kinds.get(k, 0) + 1
    return {"n": len(pool), "by_kind": kinds,
            "sha256": hashlib.sha256(json.dumps(sorted(c["chunk_id"] for c in pool)).encode()).hexdigest(),
            "latest_available_at": max((c["available_at_et"] for c in pool), default=None)}
