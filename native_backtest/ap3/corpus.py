"""AP3 evidence corpus: official documents -> text -> native chunks with available_at, plus canaries and audit.

The corpus is built from raw bytes saved by the fetcher (native_backtest/scripts/ap3_corpus_fetch.py) or
imported from a folder of the same files. Every document keeps:
  doc_id, family, url, raw_sha256, first-publication time (available_at, America/New_York) read from the
  document itself where it prints one, and the source of that time.
Text is chunked with causal-rag-mvp's own chunker (vendored @ 389f826, unchanged), so chunk IDs and quote
validation behave exactly as in the native assessor.

Point-in-time rule: a chunk is eligible for a decision only if available_at < decision time. Canary
documents (synthetic, clearly marked, dated after every decision in the window) are added to the index
so the audit can prove the filter works: no canary may ever be eligible or retrieved.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
_CRAG = ROOT / "native_backtest/vendor/causal-rag-mvp_389f826/src"
if str(_CRAG) not in sys.path:
    sys.path.insert(0, str(_CRAG))
from crag.retrieval import chunk_doc  # noqa: E402  (native chunker, unchanged)

SOURCES = ROOT / "native_backtest/ap3/corpus_sources_v1.json"
ET = "America/New_York"
CANARY_TAG = "AP3-CANARY-DOCUMENT-NEVER-ELIGIBLE"
MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                      "September", "October", "November", "December"], 1)}


class CorpusError(RuntimeError):
    pass


@dataclasses.dataclass
class Document:
    doc_id: str
    family: str
    url: str
    raw_sha256: str
    available_at_et: str
    available_at_source: str
    role: str
    text: str


def load_sources() -> dict:
    return json.loads(SOURCES.read_text())


def html_text(raw: bytes) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()
    container = soup.find(id="article") or soup.find(id="main-content") or soup.find("pre") or soup.body or soup
    if container.name == "pre":  # BLS releases are mostly preformatted text
        return "\n".join(p.strip() for p in re.split(r"\n\s*\n", container.get_text()) if p.strip())
    paras = [p.get_text(" ", strip=True) for p in container.find_all(["p", "li", "h1", "h2", "h3", "h4", "pre"])]
    paras = [re.sub(r"\s+", " ", p) for p in paras if p]
    return "\n".join(paras) if paras else container.get_text("\n", strip=True)


def pdf_text(raw: bytes) -> str:
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def _ts(date: pd.Timestamp, hh: int, mm: int) -> pd.Timestamp:
    return pd.Timestamp(year=date.year, month=date.month, day=date.day, hour=hh, minute=mm, tz=ET)


def _hm(h: str, m: str, ap: str) -> tuple:
    hh = int(h) % 12 + (12 if ap.lower() == "p" else 0)
    return hh, int(m)


def _parse_date(s: str) -> pd.Timestamp:
    s = s.replace(",", " ").split()
    month = s[0].capitalize()
    if month not in MONTHS:
        raise CorpusError(f"unrecognised month in {s}")
    return pd.Timestamp(year=int(s[-1]), month=MONTHS[month], day=int(s[1]))


def available_at(family: str, spec: dict, text: str, url_date: Optional[pd.Timestamp], release_date: Optional[pd.Timestamp] = None) -> tuple:
    """Returns (timestamp, source-of-time). Prefers the time printed in the document; falls back only to the
    family's documented release time on the documented date, and says so."""
    if "embargo_regex" in spec:
        text = re.sub(r"[ \t\u00a0]+", " ", text.replace("\u00a0", " "))   # PDF extraction whitespace
        m = re.search(spec["embargo_regex"], text, re.I)
        groups = (m.group(1), m.group(2), m.group(3), m.group(4)) if m else None
        if m is None and "embargo_regex_date_first" in spec:
            m2 = re.search(spec["embargo_regex_date_first"], text, re.I)
            if m2:
                m, groups = m2, (m2.group(2), m2.group(3), m2.group(4), m2.group(1))
        if m:
            hh, mm = _hm(groups[0], groups[1], groups[2])
            d = _parse_date(groups[3])
            if url_date is not None and abs((d - url_date).days) > 1:
                raise CorpusError(f"{family}: printed release date {d.date()} differs from the URL date {url_date.date()}")
            return _ts(d, hh, mm), "printed in the document"
        raise CorpusError(f"{family}: no embargo/release line found")
    if "release_time_regex" in spec:
        m = re.search(spec["release_time_regex"], text, re.I)
        if m and url_date is not None:
            hh, mm = _hm(m.group(1), m.group(2), m.group(3))
            return _ts(url_date, hh, mm), "release time printed in the document; date from the statement date"
        if url_date is not None:
            return _ts(url_date, 14, 0), "default 14:00 ET for a scheduled statement (no time printed)"
    if "default_release_time_et" in spec:
        d = release_date if release_date is not None else url_date
        if d is None:
            raise CorpusError(f"{family}: no release date")
        hh, mm = (int(x) for x in spec["default_release_time_et"].split(":"))
        return _ts(d, hh, mm), f"documented release time {spec['default_release_time_et']} ET on the {'calendar release' if release_date is not None else 'URL'} date"
    raise CorpusError(f"{family}: no availability rule")


def make_document(family: str, url: str, raw: bytes, url_date: Optional[pd.Timestamp], release_date: Optional[pd.Timestamp] = None,
                  sources: Optional[dict] = None) -> Document:
    spec = (sources or load_sources())["families"][family]
    text = pdf_text(raw) if spec.get("format") == "pdf" else html_text(raw)
    if len(text.split()) < 30:
        raise CorpusError(f"{family}: {url} has too little text ({len(text.split())} words)")
    t, src = available_at(family, spec, text, url_date, release_date)
    doc_id = f"{family}_{t.strftime('%Y%m%d')}"
    return Document(doc_id=doc_id, family=family, url=url, raw_sha256=hashlib.sha256(raw).hexdigest(),
                    available_at_et=t.isoformat(), available_at_source=src, role=spec["role"], text=text)


def chunks_for(doc: Document) -> List[dict]:
    rows = []
    for c in chunk_doc(doc.doc_id, doc.text):
        c.update({"available_at_et": doc.available_at_et, "role": doc.role, "family": doc.family})
        rows.append(c)
    return rows


def canaries(window_end: str, n: int = 3) -> List[dict]:
    """Synthetic canary chunks dated after the whole window. They must never be eligible or retrieved."""
    t = (pd.Timestamp(window_end) + pd.Timedelta(days=400)).tz_localize(ET) + pd.Timedelta(hours=8, minutes=30)
    words = ["inflation", "interest rates", "retail sales consumer spending", "employment payrolls", "industrial production", "monetary policy"]
    out = []
    for i in range(n):
        doc_id = f"canary_{i:02d}"
        text = f"{CANARY_TAG}. " + " ".join(words * 6) + f" {CANARY_TAG}."
        out.append({"doc_id": doc_id, "chunk_id": f"{doc_id}#c000", "text": text, "available_at_et": t.isoformat(),
                    "role": "canary", "family": "canary"})
    return out


def eligible(chunks: Iterable[dict], decision_time) -> List[dict]:
    t = pd.Timestamp(decision_time)
    return [c for c in chunks if pd.Timestamp(c["available_at_et"]) < t]


def audit(chunks: List[dict], decision_times: Iterable) -> Dict[str, object]:
    """Point-in-time audit over every decision: canaries never eligible; every eligible chunk predates the decision."""
    decision_times = list(decision_times)
    problems, n_checked = [], 0
    for dt in decision_times:
        el = eligible(chunks, dt)
        n_checked += len(el)
        bad = [c["chunk_id"] for c in el if c.get("role") == "canary" or CANARY_TAG in c["text"]]
        late = [c["chunk_id"] for c in el if pd.Timestamp(c["available_at_et"]) >= pd.Timestamp(dt)]
        if bad or late:
            problems.append({"decision_time": str(dt), "canaries_eligible": bad[:5], "late_chunks": late[:5]})
    return {"decisions": len(decision_times), "eligible_chunk_checks": n_checked, "problems": problems, "pass": not problems}
